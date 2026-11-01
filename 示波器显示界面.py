"""EGO1 单通道示波器上位机。

运行：python 示波器显示界面.py
依赖：PySide6、pyqtgraph、numpy、pyserial（见 PC/ui/requirements.txt）。
默认使用演示数据；真实串口复用 PC/protocol/scope_protocol.py 的 v1 协议。
UI 包含闭环自检与相对校准、触发感知的多分辨率采集两个创新点。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
import queue
import struct
import sys
import threading
import time
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

try:
    import numpy as np
    import pyqtgraph as pg
    from PySide6 import QtCore, QtGui, QtWidgets
    import serial
    from serial.tools import list_ports
except ImportError as exc:
    raise SystemExit(
        f"缺少界面依赖：{exc}\n请运行：python -m pip install -r PC/ui/requirements.txt"
    ) from exc

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "PC" / "protocol"))
import scope_protocol as proto
import hardware_calibration as hwcal
import awg
import summary_report
import absolute_calibration as abscal
sys.path.insert(0, str(ROOT / 'PC' / 'ui'))
from absolute_calibration_dialog import AbsoluteCalibrationDialog

SCALE = 10.0 / 4095
PC_RELEASE = '2026.11.01-r6'
OVERLOAD_ACCEPTANCE = '真实模拟过载验收：已完成'
OVERLOAD_CONFIRMATION = '依据用户于2026-10-30确认：已在老师帮助下完成验证。'
CYAN, GOLD = "#37d8c7", "#ffc568"
TRIGGERS = ["上升沿", "下降沿", "窗口进入", "窗口离开", "正脉宽", "负脉宽", "欠幅", "过幅", "OTR"]
TIME_DIVS = [1e-7, 2e-7, 5e-7, 1e-6, 2e-6, 5e-6, 1e-5, 2e-5, 5e-5,
             1e-4, 2e-4, 5e-4, 1e-3, 2e-3]
VOLT_DIVS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0]


def read_hardware_profile(path):
    """Load local confirmed settings as data, independently of demo settings."""
    if not path.exists():
        return {}
    if path.stat().st_size > 16384:
        raise ValueError("硬件参数文件过大")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != "scope-ui-hardware-v1":
        raise ValueError("硬件参数文件格式无效")
    specifications = {
        "trigger": {"kind": (0, 8, int), "threshold": (-5, 5, float),
                    "hysteresis": (0, 2, float), "low": (-5, 5, float), "high": (-5, 5, float),
                    "width_min": (4e-8, 1, float), "width_max": (4e-8, 1, float),
                    "amplitude": (0, 10, float), "observation": (2, 16384, int)},
        "dds": {"wave": (0, 3, int), "frequency": (0, 12500000, float),
                "amplitude": (0, 1, float), "phase": (0, 359.999, float),
                "offset": (-8192, 8191, int)},
    }
    result = {}
    for section, fields in specifications.items():
        if section not in data:
            continue
        values = data[section]
        if not isinstance(values, dict):
            raise ValueError(f"硬件参数 {section} 无效")
        parsed = {}
        for name, (low, high, kind) in fields.items():
            value = values.get(name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not low <= value <= high
                    or kind is int and not isinstance(value, int)):
                raise ValueError(f"硬件参数 {section}.{name} 无效")
            parsed[name] = value
        if section == "dds":
            if type(values.get("enable")) is not bool:
                raise ValueError("硬件参数 dds.enable 无效")
            parsed["enable"] = values["enable"]
        else:
            if parsed["kind"] in (2, 3) and parsed["low"] + parsed["hysteresis"] >= parsed["high"] - parsed["hysteresis"]:
                raise ValueError("保存的触发窗口无效")
            if parsed["kind"] in (4, 5) and parsed["width_min"] > parsed["width_max"]:
                raise ValueError("保存的触发脉宽无效")
        result[section] = parsed
    return result


def configure_fonts(app):
    """Qt offscreen 在 Windows 上可能无法枚举字体，按需载入系统字体。"""
    if sys.platform == "win32" and "Microsoft YaHei UI" not in QtGui.QFontDatabase.families():
        folder = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts"
        for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "consola.ttf", "seguisym.ttf"):
            path = folder / name
            if path.is_file():
                QtGui.QFontDatabase.addApplicationFont(str(path))
    app.setFont(QtGui.QFont("Microsoft YaHei UI", 9))


def eng(value: float, unit: str = "", digits: int = 3) -> str:
    if not math.isfinite(value):
        return "—"
    if value == 0:
        return f"0 {unit}".strip()
    for multiplier, prefix in [(1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""),
                               (1e-3, "m"), (1e-6, "µ"), (1e-9, "n")]:
        if abs(value) >= multiplier:
            return f"{value / multiplier:.{digits}g} {prefix}{unit}".strip()
    return f"{value:.{digits}g} {unit}".strip()






def capture_clipped(frame):
    """检查整帧统计、已读原始样本和包络中的削顶或超量程。"""
    raw = frame.words & 4095
    summary_clipped = frame.fpga_saturation is not None and frame.fpga_saturation['saturated_samples'] > 0
    envelope_clipped = frame.overview is not None and any(otr or lo == -2048 or hi == 2047
                                                         for lo, hi, otr in frame.overview.buckets)
    return bool(summary_clipped or envelope_clipped or np.any(frame.words & 0x8000) or np.any(raw == 0) or np.any(raw == 4095))


@dataclass(frozen=True)
class HardwareEnvelope:
    buckets: tuple
    length: int
    rate: int
    trigger: int
    timestamp: int

    def __post_init__(self):
        entries = tuple(tuple(b) for b in self.buckets)
        if (not 1 <= self.length <= 16384 or not 0 <= self.trigger < self.length
                or not 0 < self.rate <= 125000000 or not 0 <= self.timestamp < 1 << 64
                or not 1 <= len(entries) <= min(800, self.length)
                or any(len(b) != 3 or not -2048 <= b[0] <= b[1] <= 2047 or b[2] not in (0, 1) for b in entries)):
            raise ValueError('板端包络元数据或样本无效')
        object.__setattr__(self, 'buckets', entries)

    def arrays(self):
        values = np.asarray(self.buckets)
        edges = np.arange(len(values)+1, dtype=np.int64)*self.length//len(values)
        centers = ((edges[:-1]+edges[1:]-1)/2-self.trigger)/self.rate
        # signed_sample = 2047-raw; the existing nominal voltage has a half-code offset.
        lo = (values[:, 0]+0.5)*SCALE
        hi = (values[:, 1]+0.5)*SCALE
        return centers, lo, hi


@dataclass(frozen=True)
class Capture:
    words: np.ndarray
    rate: int
    trigger: int
    timestamp: int
    source: str
    reason: str = "上升沿"
    overview: HardwareEnvelope | None = None
    record_offset: int = 0
    fpga_measurement: dict | None = None
    fpga_spectrum: dict | None = None
    fpga_saturation: dict | None = None
    firmware_build: int | None = None
    record_length: int | None = None

    def __post_init__(self):
        words = np.asarray(self.words)
        if (words.ndim != 1 or not 1 <= words.size <= 16384
                or words.dtype.kind not in "ui" or np.any(words < 0) or np.any(words > 65535)):
            raise ValueError("样本必须为 1～16384 个 16 位整数")
        if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, np.integer))
               for v in (self.rate, self.trigger, self.timestamp)):
            raise ValueError("采样率、触发索引和时间戳必须为整数")
        valid_trigger = 0 <= self.trigger < len(words)
        if self.overview is not None:
            env = self.overview
            valid_trigger = (self.source == "硬件 UART" and self.rate == env.rate
                             and 0 <= self.record_offset <= env.length-len(words)
                             and self.trigger+self.record_offset == env.trigger
                             and self.timestamp == (env.timestamp+self.record_offset) % (1 << 64))
        elif self.record_offset != 0 and self.record_length is None:
            valid_trigger = False
        if self.record_length is not None and (
                any(isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, np.integer))
                    for v in (self.record_length, self.record_offset))
                or not len(words) <= self.record_length <= 16384
                or not 0 <= self.record_offset <= self.record_length-len(words)
                or (self.overview is not None and self.record_length != self.overview.length)):
            valid_trigger = False
        if not 0 < self.rate <= 125000000 or not valid_trigger or not 0 <= self.timestamp < 1 << 64:
            raise ValueError("采样率、触发索引或时间戳越界")
        if np.any(words & 0x7000):
            raise ValueError("样本保留位必须为零")
        raw = np.array(words, dtype=np.uint16, copy=True)
        raw.setflags(write=False)
        object.__setattr__(self, "words", raw)

    def volts(self) -> np.ndarray:
        # 按模块手册取反；原始码始终保留在 words 中。
        return (4095 - (self.words & 0x0FFF).astype(np.int32)) * SCALE - 5.0

    def times(self) -> np.ndarray:
        return (np.arange(len(self.words)) - self.trigger) / self.rate


def envelope(t: np.ndarray, y: np.ndarray, columns: int = 800):
    """对每个桶保留 min/max，连同最后一个样本，绝不使用普通抽点。"""
    count = min(columns, len(y))
    edges = np.arange(count + 1, dtype=np.int64) * len(y) // count
    lo = np.minimum.reduceat(y, edges[:-1])
    hi = np.maximum.reduceat(y, edges[:-1])
    centers = (t[edges[:-1]] + t[edges[1:] - 1]) / 2
    return centers, lo, hi


def measure(y: np.ndarray, rate: int, hysteresis: float = 0.02) -> dict:
    """带迟滞的交越测频；不足两个完整周期时返回无效频率。"""
    low, high = float(y.min()), float(y.max())
    level = (low + high) / 2
    h = min(max(hysteresis / 2, SCALE), (high - low) / 4)
    states = np.where(y <= level-h, -1, np.where(y >= level+h, 1, 0))
    nonzero = np.flatnonzero(states)
    rises = np.flatnonzero(np.diff(states[nonzero]) == 2)
    # 一次找出全部零交越，再向量化匹配每个 Schmitt 上升区间的最后一个交越。
    crossings = np.flatnonzero((y[:-1] < level) & (y[1:] >= level))
    accepted = np.empty(0)
    if len(rises) and len(crossings):
        positions = np.searchsorted(crossings, nonzero[rises+1], side="left") - 1
        valid = positions >= 0
        k = crossings[np.maximum(positions, 0)]
        k = k[valid & (k >= nonzero[rises])]
        accepted = k + (level-y[k])/(y[k+1]-y[k])
    frequency, duty = math.nan, math.nan
    if len(accepted) >= 3 and high - low >= 4 * SCALE:
        period = (accepted[-1] - accepted[0]) / (len(accepted) - 1)
        intervals = np.diff(accepted)
        # 非周期噪声的随机交越不应被当成有效直流频率。
        if np.std(intervals)/period <= 0.15:
            frequency = rate / period
            section = y[math.ceil(accepted[0]):math.ceil(accepted[-1])]
            if len(section):
                duty = float(np.mean(section >= level) * 100)
    return {"vpp": high-low, "rms": float(np.sqrt(np.mean(y*y))), "mean": float(y.mean()),
            "minimum": low, "maximum": high, "frequency": frequency, "duty": duty,
            "period": 1/frequency if math.isfinite(frequency) else math.nan}


def spectrum(y: np.ndarray, rate: int, n: int, use_hann: bool):
    if n != 1024 or len(y) < 1024:
        raise ValueError("FFT 固定 1024 点，需要至少 1024 个原始样本")
    window = .5-.5*np.cos(2*np.pi*np.arange(n)/n) if use_hann else np.ones(n)
    bins = np.fft.rfft((y[:n] - np.mean(y[:n])) * window)
    amplitude = np.abs(bins) * 2 / window.sum()
    amplitude[0] /= 2
    amplitude[-1] /= 2
    db = 20 * np.log10(np.maximum(amplitude / 5, 1e-8))
    f = np.fft.rfftfreq(n, 1 / rate)
    first, last = (2, 511) if use_hann else (1, 512)
    peak = int(np.argmax(amplitude[first:last]) + first)
    harmonics = []
    for h in range(2,6):
        if peak >= 4 and h*peak < 511:
            k = int(np.argmax(amplitude[h*peak-1:h*peak+2])+h*peak-1)
            harmonics.append((h, float(f[k]), float(amplitude[k])))
    return f, db, peak, harmonics, rate / n


class CsvExportWorker(QtCore.QThread):
    completed = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def __init__(self, path, frame, calibration=None, calibration_metadata=None):
        super().__init__()
        self.path, self.frame, self.calibration = Path(path), frame, calibration
        self.calibration_metadata = calibration_metadata or {}

    def run(self):
        temporary = None
        try:
            frame = self.frame
            with tempfile.NamedTemporaryFile(mode="w", newline="", encoding="utf-8-sig",
                                             dir=self.path.parent, prefix=".scope-", suffix=".tmp", delete=False) as file:
                temporary = Path(file.name)
                writer = csv.writer(file)
                writer.writerow(["# source", frame.source, "sample_rate_hz", frame.rate, "trigger_index", frame.trigger,
                                 "first_sample_timestamp", frame.timestamp, "display_calibrated", self.calibration is not None,
                                 "record_offset", frame.record_offset, "record_length",
                                 frame.record_length or (frame.overview.length if frame.overview is not None else len(frame.words)),
                                 "scope", "raw-roi" if frame.overview is not None or (frame.record_length or len(frame.words)) > len(frame.words) else "full-raw",
                                 'voltage_calibration', json.dumps(self.calibration_metadata, ensure_ascii=False)])
                writer.writerow(["index", "time_from_trigger_s", "raw_word", "raw_code_12bit", "otr", "nominal_voltage_v", "display_voltage_v"])
                for start in range(0, len(frame.words), 512):
                    if self.isInterruptionRequested():
                        return
                    raw = frame.words[start:start+512]
                    indices = np.arange(start, start+len(raw))
                    nominal = (4095-(raw & 4095).astype(np.int32))*SCALE-5
                    displayed = ((nominal-self.calibration[0])/self.calibration[1]
                                 if self.calibration else nominal)
                    writer.writerows(zip(indices.tolist(), ((indices-frame.trigger)/frame.rate).tolist(), raw.tolist(),
                                         (raw & 4095).tolist(), (raw >> 15).tolist(), nominal.tolist(), displayed.tolist()))
                    # CSV 数值格式化持有 GIL；分批主动让出，避免后台导出饿死 GUI。
                    time.sleep(0.002)
            if not self.isInterruptionRequested():
                os.replace(temporary, self.path)
                temporary = None
                self.completed.emit(str(self.path))
        except (OSError, ValueError) as exc:
            self.failed.emit(f"错误：CSV 保存失败 · {exc}")
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def read_fingerprint(path):
    """只接受有限大小的 JSON 数值数据，失败前不修改当前基线。"""
    with open(path, "rb") as file:
        content = file.read(1024*1024+1)
    if len(content) > 1024*1024:
        raise ValueError("指纹文件超过 1 MB")
    data = json.loads(content.decode("utf-8-sig"))
    if not isinstance(data, dict) or data.get("format") != "scope-ui-fingerprint-v1" or data.get("source") != "software-demo":
        raise ValueError("指纹格式或来源不匹配")
    values = data.get("calibration")
    if not isinstance(values, dict):
        raise ValueError("缺少校准参数")
    result = {}
    for key, low, high in [("offset", -10, 10), ("gain", 1e-6, 100), ("noise", 0, 10)]:
        number = values.get(key)
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not low <= number <= high or not math.isfinite(number):
            raise ValueError(f"校准参数 {key} 无效")
        result[key] = float(number)
    return result


def read_hardware_fingerprint(path):
    with open(path,'rb') as file:
        content = file.read(2*1024*1024+1)
    if len(content)>2*1024*1024:
        raise ValueError('指纹超过 2 MiB')
    return hwcal.validate_fingerprint(json.loads(content.decode('utf-8-sig')))


def write_hardware_fingerprint(path,data):
    hwcal.validate_fingerprint(data)
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,
                                         prefix='.scope-hardware-',suffix='.tmp',delete=False) as file:
            temporary = Path(file.name)
            json.dump(data,file,ensure_ascii=False,indent=2,allow_nan=False)
        os.replace(temporary,path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


class TriggerWaitExpired(TimeoutError):
    """A responsive device did not produce a frame within the user's wait."""


class LocalControlActive(ValueError):
    """The panel owns the backend; UART itself remains usable."""


class SerialWorker(QtCore.QThread):
    """串行请求/响应；UART 阻塞和二进制重组全部在后台线程执行。"""
    summary_ready = QtCore.Signal(str)
    awg_ready = QtCore.Signal(object)
    frame_ready = QtCore.Signal(object)
    status_ready = QtCore.Signal(object)
    message = QtCore.Signal(str)
    fault = QtCore.Signal(str)
    command_done = QtCore.Signal()
    command_confirmed = QtCore.Signal(int, object)
    connected = QtCore.Signal(bool)
    baud_ready = QtCore.Signal(int)
    cycle_done = QtCore.Signal()
    progress = QtCore.Signal(int)
    capabilities_ready = QtCore.Signal(object)
    identity_ready = QtCore.Signal(object)
    dds_configuration_ready = QtCore.Signal(object)
    configuration_ready = QtCore.Signal(object)
    local_control = QtCore.Signal()
    trigger_wait_expired = QtCore.Signal(str)
    roi_ready = QtCore.Signal(object, object)
    roi_done = QtCore.Signal()
    calibration_progress = QtCore.Signal(int,str,str)
    calibration_result = QtCore.Signal(object)

    def __init__(self, port: str, baud: int):
        super().__init__()
        self.port, self.baud = port, baud
        self.tasks = queue.Queue(maxsize=16)
        self._task_lock = threading.Lock()
        self._queued_names = set()
        self.stop_requested = threading.Event()
        self.shutdown = threading.Event()
        self.cancel_capture = threading.Event()
        self.sequence = 0
        self.trigger_kind = 0
        self.stream_mode = None
        self.parser = proto.Parser()
        self.link = None
        self.capabilities = 0
        self.device_identity = port
        self.build_id = None
        self.panel_owns_control = False

    def submit(self, name, payload=None):
        if name not in ("capture", "status", "command", "roi", "calibration", "awg", "summary"):
            raise ValueError(f"不支持的串口任务：{name}")
        with self._task_lock:
            if self.shutdown.is_set() or (name in ("status", "capture", "roi", "calibration") and name in self._queued_names):
                return False
            try:
                self.tasks.put_nowait((name, payload))
            except queue.Full:
                return False
            self._queued_names.add(name)
            return True

    def request_stop(self):
        self.cancel_capture.set()
        self.stop_requested.set()

    def exchange(self, kind, payload=b"", wave=False, record_length=None, envelope_buckets=None, overview=None, restoring=False):
        seq = self.sequence
        self.sequence = (seq + 1) & 0xFFFF
        wire = proto.encode(proto.Frame(kind, sequence=seq, payload=payload))
        if self.link.write(wire) != len(wire):
            raise OSError("串口写入不完整，命令未确认")
        assembler = proto.WaveAssembler()
        env_assembler = (proto.EnvelopeAssembler(seq, envelope_buckets, record_length)
                         if envelope_buckets is not None else None)
        start, count = struct.unpack_from("<II", payload) if wave else (0, 0)
        total_length = record_length if record_length is not None else count
        if wave and (count < 1 or start+count > total_length):
            raise ValueError("波形请求范围无效")
        deadline = time.monotonic() + (8 + count * 24 / self.baud if wave else 3)
        last_byte = time.monotonic()
        previous_progress = -1
        while time.monotonic() < deadline:
            if not restoring and (self.shutdown.is_set() or ((wave or env_assembler is not None) and self.cancel_capture.is_set())):
                raise InterruptedError("捕获已取消")
            data = self.link.read(max(1, min(self.link.in_waiting, 8192)))
            if data:
                last_byte = time.monotonic()
                frames = self.parser.feed(data)
            elif time.monotonic() - last_byte > 2:
                self.parser.expire()
                raise TimeoutError("设备响应超时；请检查固件、端口与波特率")
            else:
                continue
            for frame in frames:
                if not frame.flags & proto.RESPONSE:
                    continue
                if frame.kind == kind | 0x80 and frame.sequence == seq and frame.flags & proto.ERROR:
                    code = frame.payload[0] if frame.payload else -1
                    if code == 6:
                        self.panel_owns_control = True
                        raise LocalControlActive('显示屏控制中；SW7 ON 后自动连接电脑。')
                    raise ValueError(f"固件拒绝命令 0x{kind:02X}，状态码 {code}")
                if env_assembler is not None and frame.kind == 0xB2:
                    entries = env_assembler.accept(frame)
                    self.sequence = env_assembler.next_sequence
                    self.progress.emit(int(100*len(env_assembler.buckets)/env_assembler.expected_buckets))
                    if entries is not None:
                        base, rate, trigger = env_assembler.identity
                        return HardwareEnvelope(tuple(entries), record_length, rate, trigger, base)
                    continue
                if wave and frame.kind == 0xB0:
                    # FIRST 必须回显当前请求序号，忽略被取消请求的残余包。
                    if not assembler.active and (not frame.flags & proto.FIRST or frame.sequence != seq):
                        continue
                    if frame.flags & proto.ERROR or frame.flags & ~(proto.RESPONSE | proto.FIRST | proto.MORE | proto.LAST):
                        raise ValueError("波形响应标志无效")
                    if assembler.active and frame.flags & proto.FIRST:
                        raise ValueError("波形传输中重复 FIRST，拒绝拼接不同快照")
                    if len(frame.payload) < 10:
                        raise ValueError("波形响应缺少样本")
                    offset, total = struct.unpack_from("<II", frame.payload)
                    expected_offset = assembler.next_offset if assembler.active else start
                    if total != total_length or offset != expected_offset or not start <= offset < start+count:
                        raise ValueError("波形总长度或偏移与请求不一致")
                    words = assembler.accept(frame)
                    self.sequence = assembler.next_sequence
                    progress = min(100, int(len(assembler.words) * 100 / count))
                    if progress != previous_progress:
                        self.progress.emit(progress)
                        previous_progress = progress
                    if assembler.next_offset > start+count:
                        raise ValueError("波形超出请求范围")
                    if words is None and assembler.next_offset >= start+count:
                        raise ValueError("波形到达请求末尾但未标记 LAST")
                    if words is not None:
                        if len(words) != count:
                            raise ValueError("波形总点数与请求不一致")
                        # 样本保留位和元数据范围由 Capture 统一校验。
                        return Capture(words, assembler.rate, assembler.trigger-start,
                                       (assembler.base+start) & ((1 << 64)-1),
                                       "硬件 UART", TRIGGERS[self.trigger_kind],
                                       overview=overview, record_offset=start,firmware_build=self.build_id,
                                       record_length=total_length)
                elif not wave and frame.kind == kind | 0x80 and frame.sequence == seq:
                    if frame.flags != proto.RESPONSE:
                        raise ValueError("普通响应带有非法标志")
                    if kind in (proto.SET_RECORD, proto.SET_TRIGGER, proto.SINGLE, proto.STOP, proto.SET_DDS, proto.SET_CAPTURE_MODE, proto.RUN, proto.RELEASE_FRAME, proto.SET_DIAGNOSTIC) and frame.payload != b"\x00":
                        raise ValueError("设备状态响应无效，命令未确认")
                    if kind == proto.PING and frame.payload != payload:
                        raise ValueError("PING 回显不匹配")
                    if kind == proto.GET_VERSION and (len(frame.payload) != 8 or frame.payload[:4] != b"\x01\x00\x00\x00"):
                        raise ValueError("不支持的设备版本")
                    if kind == proto.STOP:
                        self.stream_mode = None
                    return frame
        raise TimeoutError("命令等待时间超限")

    def read_status(self):
        frame = self.exchange(proto.GET_STATUS)
        if len(frame.payload) != 48:
            raise ValueError("状态响应应为 48 字节")
        p = frame.payload
        length, pre = struct.unpack_from("<II", p, 4)
        if p[0] & ~7 or p[2:4] != b"\x01\x00" or length != 16384 or pre >= length or frame.sample_rate > 125000000:
            raise ValueError("设备状态字段或协议版本无效")
        result = {"flags": p[0], "backend_error": p[1], "length": length, "pre": pre,
                  "rate": frame.sample_rate, "counters": struct.unpack_from("<9I", p, 12),
                  "pc_crc": self.parser.errors["crc"]}
        self.status_ready.emit(result)
        return result

    def capture(self, timeout, preview_points=None, multires_buckets=None, acquisition_mode=None):
        if self.cancel_capture.is_set():
            raise InterruptedError("捕获已取消")
        if acquisition_mode in (0,1) and not self.capabilities & proto.CAP_CAPTURE_MODES:
            raise ValueError("该固件尚未提供 AUTO/NORMAL 模式，请使用 SINGLE 或加载三模式固件")
        if acquisition_mode in (0,1) and self.capabilities & proto.CAP_CAPTURE_MODES:
            if self.stream_mode != acquisition_mode:
                self.exchange(proto.STOP)
                self.exchange(proto.SET_CAPTURE_MODE, proto.capture_mode_payload(acquisition_mode))
                self.exchange(proto.RUN)
                self.stream_mode = acquisition_mode
            else:
                self.exchange(proto.RELEASE_FRAME)
        else:
            if self.stream_mode is not None:
                self.exchange(proto.STOP)
            self.exchange(proto.SINGLE)
        deadline = time.monotonic() + timeout
        while acquisition_mode == 1 or time.monotonic() < deadline:
            if self.cancel_capture.is_set() or self.shutdown.is_set():
                raise InterruptedError("捕获已取消")
            state = self.read_status()
            if state["backend_error"]:
                raise ValueError(f"采集后端错误：{state['backend_error']}")
            if state["flags"] & 2 and not state["flags"] & 1:
                length = state["length"]
                overview = None
                if multires_buckets is not None and self.capabilities & 1:
                    overview = self.exchange(proto.READ_ENVELOPE, struct.pack('<H', multires_buckets),
                                             record_length=length, envelope_buckets=multires_buckets)
                    preview_points = min(2048, length)
                count = length if preview_points is None else min(length, preview_points)
                if self.capabilities & proto.CAP_FROZEN_ANALYSIS:
                    count = max(1024,count)
                start = max(0, min(state["pre"]-count//2, length-count))
                frame = self.exchange(proto.READ_WAVE, struct.pack("<II", start, count),
                                      wave=True, record_length=length, overview=overview)
                if self.capabilities & proto.CAP_FROZEN_ANALYSIS:
                    measured = self.exchange(proto.READ_MEASURE)
                    spectral = self.exchange(proto.READ_SPECTRUM)
                    identity = ((frame.timestamp-start) % (1 << 64), frame.rate, frame.trigger+start)
                    if any((f.timestamp,f.sample_rate,f.trigger_index) != identity for f in (measured,spectral)):
                        raise ValueError('FPGA 摘要与冻结帧身份不匹配')
                    m, spec = proto.decode_measurement(measured), proto.decode_spectrum(spectral)
                    if m['error']:
                        raise ValueError('FPGA 冻结帧分析失败')
                    frame = replace(frame,fpga_measurement=m,fpga_spectrum=spec)
                if self.capabilities & proto.CAP_SATURATION:
                    saturated=self.exchange(proto.READ_SATURATION)
                    identity=((frame.timestamp-start) % (1 << 64),frame.rate,frame.trigger+start)
                    if (saturated.timestamp,saturated.sample_rate,saturated.trigger_index)!=identity:
                        raise ValueError('饱和统计与冻结帧身份不匹配')
                    frame=replace(frame,fpga_saturation=proto.decode_saturation(saturated))
                self.frame_ready.emit(frame)
                return frame
            self.cancel_capture.wait(0.002 if preview_points is not None else 0.12)
        self.exchange(proto.STOP)
        if acquisition_mode == 0:
            # AUTO should complete even without an edge; do not misdiagnose it.
            raise TimeoutError("AUTO 未生成采集帧；请检查 SW0、模块供电及采样时钟，采集已停止")
        detail = ""
        if self.capabilities & 2:
            cfg = hwcal.decode_configuration(self.exchange(proto.GET_CONFIG).payload)
            kind, _, threshold, hysteresis, *_ = struct.unpack('<BBhHhhIIHI', cfg['trigger'])
            detail = f"；触发条件：{TRIGGERS[kind]}"
            if kind in (0, 1):
                low, high = (threshold-hysteresis+.5)*SCALE, (threshold+hysteresis+.5)*SCALE
                detail += f"，需跨过 {low*1000:.2f}～{high*1000:.2f} mV"
            if not cfg['enabled']:
                detail += "；板端 DDS 未启用，闭环需应用 DDS 配置"
            elif not cfg['amplitude']:
                detail += "；板端 DDS 幅度为 0 码，闭环没有交流输出，请设置非零幅度并应用 DDS 配置"
            elif not cfg['frequency']:
                detail += "；板端 DDS 频率为 0 Hz，直流不会持续产生边沿"
        raise TriggerWaitExpired("单次等待结束：未收到所选触发，采集已停止" + detail +
                                 "；可选择 AUTO 后点 RUN 查看实际输入，或调整触发条件后重新 SINGLE")

    def read_roi(self, frame, start, count):
        if self.shutdown.is_set() or self.cancel_capture.is_set():
            raise InterruptedError('ROI 读取已取消')
        if frame.overview is None or not 1 <= count <= 2048:
            raise ValueError('ROI 请求需要有效板端概览且不得超过 2048 点')
        result = self.exchange(proto.READ_WAVE, struct.pack('<II', start, count), wave=True,
                               record_length=frame.overview.length, overview=frame.overview)
        result = replace(result,fpga_measurement=frame.fpga_measurement,fpga_spectrum=frame.fpga_spectrum,fpga_saturation=frame.fpga_saturation)
        self.roi_ready.emit(frame, result)
        return result

    def open_link(self):
        candidates = (921600, 115200) if self.baud == 921600 else (self.baud,)
        for index, baud in enumerate(candidates):
            self.baud = baud
            self.parser = proto.Parser()
            self.link = serial.Serial(self.port, baud, timeout=0.01, write_timeout=2)
            self.link.reset_input_buffer()
            try:
                self.exchange(proto.PING, b"SCOPE_UI")
                version = self.exchange(proto.GET_VERSION)
                self.build_id=struct.unpack_from('<I',version.payload,4)[0]
                self.capabilities = 0
                if struct.unpack_from('<I', version.payload, 4)[0] & 0x80000000:
                    caps = self.exchange(proto.GET_CAPABILITIES)
                    if len(caps.payload) != 8:
                        raise ValueError('设备能力响应长度无效')
                    flags, max_buckets, max_roi = struct.unpack('<IHH', caps.payload)
                    if flags & ~63 or (flags & 1 and (max_buckets != 800 or max_roi != 2048)):
                        raise ValueError('设备多分辨率能力字段无效')
                    self.capabilities = flags
                self.capabilities_ready.emit(self.capabilities)
                self.identity_ready.emit(self.build_id)
                if self.capabilities & 2:
                    configuration = hwcal.decode_configuration(self.exchange(proto.GET_CONFIG).payload)
                    self.dds_configuration_ready.emit(configuration['dds'])
                    capture_mode = (proto.decode_capture_configuration(self.exchange(proto.GET_CAPTURE_CONFIG))[0]
                                    if self.capabilities & proto.CAP_CAPTURE_MODES else 2)
                    self.configuration_ready.emit((configuration, capture_mode))
                if self.capabilities & awg.CAPABILITY:self.awg_ready.emit(awg.status(self))
                self.device_identity = next((item.hwid for item in list_ports.comports() if item.device == self.port),self.port)
                self.baud_ready.emit(baud)
                self.message.emit(f"串口连接成功 · {baud} bit/s · 固件 0x{self.build_id:08X} · 能力 {self.capabilities}")
                return
            except TimeoutError:
                self.link.close()
                if self.shutdown.is_set() or index == len(candidates)-1:
                    raise
                self.message.emit("高速握手未响应，正在尝试旧固件 115200。")

    def run(self):
        try:
            self.open_link()
            self.read_status()
            self.connected.emit(True)
            while not self.shutdown.is_set():
                if self.stop_requested.is_set():
                    self.exchange(proto.STOP)
                    self.stop_requested.clear()
                try:
                    name, data = self.tasks.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    if name == "capture":
                        if isinstance(data, tuple):
                            self.capture(*data)
                        else:
                            self.capture(data)
                    elif name == "roi":
                        self.read_roi(*data)
                    elif name == "calibration":
                        folder = ROOT/'PC/calibration_runs'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+os.urandom(4).hex())
                        result = hwcal.run_closed_loop(self,folder,self.device_identity,baseline=data,
                                                       progress=self.calibration_progress.emit)
                        self.calibration_result.emit(result)
                    elif name == "summary":
                        version=self.exchange(proto.GET_VERSION)
                        build=struct.unpack_from('<I',version.payload,4)[0]
                        status=self.read_status()
                        live={"build": build,"capabilities": self.capabilities,"port": self.port,"baud": self.baud,
                            "device_id": self.device_identity,"sample_rate": status['rate'],"counters": list(status['counters']),
                            "pc_errors": dict(self.parser.errors),"captured_at": datetime.now().astimezone().isoformat()}
                        try:
                            summary_report.export(data['path'],ROOT,live,data['measurement'])
                        except (OSError,ValueError) as exc:
                            self.message.emit(f'汇总报告导出失败：{exc}')
                        else:
                            self.summary_ready.emit(data['path'])
                    elif name == "awg":
                        if not self.capabilities & awg.CAPABILITY:raise ValueError('当前固件不支持任意波形下载')
                        self.exchange(proto.STOP)
                        configuration=self.exchange(proto.GET_CONFIG).payload
                        disabled=bytearray(configuration[32:48]);disabled[1]=0
                        awg.ack(self,proto.SET_DDS,bytes(disabled))
                        if data['action']=='upload':
                            result=awg.upload(self,data['values'],self.progress.emit)
                            self.message.emit('1024点波形表已提交，板端读回逐字节一致；输出保持关闭，请应用DDS配置。')
                        else:
                            awg.ack(self,awg.SELECT,bytes([int(data['selected'])]))
                            awg.ack(self,proto.SET_DDS,data['payload'])
                            configuration = hwcal.decode_configuration(self.exchange(proto.GET_CONFIG).payload)
                            if configuration['dds'] != data['payload']:
                                raise ValueError('DDS 配置读回与已提交参数不一致')
                            result=awg.status(self)
                            self.command_confirmed.emit(proto.SET_DDS, data['payload'])
                            self.dds_configuration_ready.emit(configuration['dds'])
                            self.message.emit('任意波形/DDS输出配置已确认')
                        self.awg_ready.emit(result)
                    elif name == "status":
                        self.read_status()
                    else:
                        kind, payload = data
                        self.exchange(kind, payload)
                        if kind == proto.SET_TRIGGER:
                            self.trigger_kind = payload[0]
                        self.command_confirmed.emit(kind, payload)
                        self.message.emit(f"配置已确认 · 命令 0x{kind:02X}")
                except InterruptedError:
                    if not self.shutdown.is_set():
                        self.parser.buffer.clear()
                        self.exchange(proto.STOP)
                        self.stop_requested.clear()
                        self.message.emit("采集已停止")
                except TriggerWaitExpired as exc:
                    # capture() has already confirmed STOP. Keep the connection
                    # and distinguish an absent trigger from a transport fault.
                    self.trigger_wait_expired.emit(str(exc))
                except LocalControlActive:
                    raise
                except (ValueError, TimeoutError) as exc:
                    # 失败后不把旧帧当作下一次采集；由用户重新 RUN。
                    self.cancel_capture.set()
                    self.parser.buffer.clear()
                    if name == "capture" and not self.shutdown.is_set():
                        # STOP 无法确认时结束连接，避免残留数据继续污染下一个请求。
                        self.exchange(proto.STOP)
                        self.stop_requested.clear()
                    self.fault.emit(f"错误：{exc}")
                finally:
                    with self._task_lock:
                        self._queued_names.discard(name)
                    if name in ("command", "awg", "summary"):
                        self.command_done.emit()
                    if name == "capture":
                        self.cycle_done.emit()
                    if name == "roi":
                        self.roi_done.emit()
        except LocalControlActive:
            self.local_control.emit()
        except (serial.SerialException, OSError, ValueError, TimeoutError, InterruptedError) as exc:
            if not self.shutdown.is_set():
                self.fault.emit(f"错误：串口连接中断 · {exc}")
        finally:
            if self.link is not None and self.link.is_open:
                # 软件退出只请求 STOP，不修改 module_enable 或冒充硬件高阻控制。
                try:
                    if not self.panel_owns_control:
                        self.link.write(proto.encode(proto.Frame(proto.STOP, sequence=self.sequence)))
                except (serial.SerialException, OSError):
                    pass
                try:
                    self.link.close()
                except (serial.SerialException, OSError):
                    pass
            self.connected.emit(False)


class FocusWheelMixin:
    """未聚焦的参数控件把滚轮交还滚动面板，避免滚动时误改 DDS/触发值。"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class ScopeComboBox(FocusWheelMixin, QtWidgets.QComboBox):
    pass


class ScopeDoubleSpinBox(FocusWheelMixin, QtWidgets.QDoubleSpinBox):
    pass


class ScopeSpinBox(FocusWheelMixin, QtWidgets.QSpinBox):
    pass


class VoltageInput(QtWidgets.QWidget):
    """可选 mV/V 的输入框；对外取值与信号始终使用 V。"""
    valueChanged = QtCore.Signal(float)

    def __init__(self, low, high, value):
        super().__init__()
        self._low, self._high = low, high
        self._volts = float(np.clip(value, low, high))
        self._scale = 0.001
        self.spinbox = ScopeDoubleSpinBox()
        self.spinbox.setKeyboardTracking(False)
        self.spinbox.setSingleStep(1.0)
        self.spinbox.setMinimumWidth(0)
        self.spinbox.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.unit_combo = ScopeComboBox()
        self.unit_combo.addItem("mV", 0.001)
        self.unit_combo.addItem("V", 1.0)
        self.unit_combo.setFixedWidth(62)
        self.unit_combo.setToolTip("切换单位时保持实际电压不变；箭头每次调节 1 个当前单位。")
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        row.addWidget(self.spinbox, 1)
        row.addWidget(self.unit_combo)
        self.setFocusProxy(self.spinbox)
        self._show_value()
        self.spinbox.valueChanged.connect(self._edited)
        self.unit_combo.currentIndexChanged.connect(self._unit_changed)

    def value(self):
        return self._volts

    def setValue(self, volts):
        self.spinbox.setValue(volts / self._scale)

    def _edited(self, displayed):
        volts = round(displayed * self._scale, 9)
        if volts != self._volts:
            self._volts = volts
            self.valueChanged.emit(volts)

    def _unit_changed(self):
        # 先按旧单位提交尚未离开编辑框的输入，再切换显示比例。
        self.spinbox.interpretText()
        self._scale = self.unit_combo.currentData()
        self._show_value()

    def _show_value(self):
        with QtCore.QSignalBlocker(self.spinbox):
            self.spinbox.setDecimals(3 if self._scale == 0.001 else 6)
            self.spinbox.setRange(self._low / self._scale, self._high / self._scale)
            self.spinbox.setValue(self._volts / self._scale)


STYLE = """
QMainWindow, QWidget { background:#0c121d; color:#dbe5f3; font-family:'Microsoft YaHei UI','Segoe UI'; font-size:13px; }
QWidget#header { background:#111b2b; border:1px solid #233248; border-radius:10px; }
QWidget#header QLabel { background:transparent; }
QLabel#title { font-size:36px; font-weight:700; color:#f0f7ff; }
QFrame#headerStatus { background:#132336; border:1px solid #2b435d; border-radius:9px; }
QFrame#headerStatus QLabel { background:transparent; font-size:16px; color:#dbe5f3; }
QFrame#headerStatus QLabel#headerCapture { color:#68e4cf; font-weight:600; }
QFrame#headerStatus QFrame#headerDivider { background:#344b64; border:0; }
QLabel#subtitle { color:#91a4be; font-size:12px; }
QLabel#badge { background:#153332; color:#68e4cf; padding:7px 13px; border:1px solid #23514c; border-radius:13px; font-size:12px; }
QLabel#metricValue { font-family:'Consolas','Microsoft YaHei UI'; font-size:29px; font-weight:600; color:#eaf3ff; }
QLabel#metricTitle { color:#91a4be; font-size:12px; }
QFrame#metric { background:#131e2e; border:1px solid #26364b; border-radius:9px; }
QFrame#metric QLabel { background:transparent; }
QGroupBox { background:#111b29; border:1px solid #27374d; border-radius:8px; margin-top:14px; padding:15px 12px 12px; font-weight:600; }
QGroupBox QLabel { background:transparent; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px; color:#c5d5e9; }
QPushButton { background:#1b2a3e; border:1px solid #34465e; border-radius:6px; padding:8px 13px; min-height:18px; }
QPushButton:hover { background:#2a405b; border-color:#4d779b; }
QPushButton:pressed { background:#183848; }
QPushButton:disabled { color:#59677b; background:#182131; border-color:#263146; }
QPushButton#primary { color:#062e2a; background:#37d8c7; border-color:#37d8c7; font-weight:700; }
QPushButton#stop { color:#ffa68f; }
QComboBox, QDoubleSpinBox, QSpinBox { background:#0d1726; border:1px solid #34465e; border-radius:5px; padding:6px; min-height:20px; }
QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover { border-color:#55718f; }
QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus { border-color:#37d8c7; }
QComboBox QAbstractItemView { background:#1a293e; selection-background-color:#245e68; }
QCheckBox { spacing:7px; }
QCheckBox#cursorOption { border:1px solid #405671; border-radius:5px; padding:9px 10px; background:#132033; }
QCheckBox#cursorOption:hover { border-color:#37d8c7; background:#172d3b; }
QCheckBox#cursorOption::indicator { width:18px; height:18px; border:2px solid #9cafc9; border-radius:3px; background:#101c2d; }
QCheckBox#cursorOption::indicator:checked { border-color:#37d8c7; image:url("__CHECKBOX_CHECK__"); }
QCheckBox#calibrationOption::indicator { width:18px; height:18px; border:2px solid #9cafc9; border-radius:3px; background:#101c2d; }
QCheckBox#calibrationOption::indicator:checked { background:#101c2d; border-color:#9cafc9; image:url("__CHECKBOX_CHECK__"); }
QCheckBox#calibrationOption::indicator:disabled { border-color:#526176; background:#182131; }
QCheckBox#calibrationOption:disabled { color:#91a4be; }
QTabWidget::pane { background:#0c1421; border:1px solid #29384f; border-radius:8px; }
QTabBar::tab { background:#0c121d; color:#91a4be; padding:10px 18px; border-bottom:2px solid transparent; }
QTabBar::tab:selected { color:#37d8c7; background:#1b2b40; border-bottom:2px solid #37d8c7; }
QTabWidget#controlTabs::pane { border:0; background:#0c121d; }
QTabWidget#controlTabs QTabBar::tab { padding:10px 13px; }
QTabBar::tab:hover { color:#e5eefb; }
QTableWidget { background:#121e30; gridline-color:#26364b; border:1px solid #29384f; selection-background-color:#23535d; }
QHeaderView::section { background:#203047; color:#aabbd2; border:0; padding:6px; }
QPlainTextEdit { background:#101b2b; color:#9eafc6; border:1px solid #29384f; border-radius:5px; }
QProgressBar { background:#18263b; border:1px solid #2a3e56; border-radius:4px; text-align:center; }
QProgressBar::chunk { background:#248d87; }
QStatusBar { background:#141e30; color:#8c9eb8; }
QScrollArea { border:0; }
QScrollBar:vertical { background:#101b2b; width:8px; }
QScrollBar::handle:vertical { background:#34465e; border-radius:4px; min-height:30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:none; }
QSplitter::handle { background:#0c121d; width:12px; }
QToolTip { color:#e7eef9; background:#26364b; border:1px solid #4c688c; }
"""
STYLE = STYLE.replace('__CHECKBOX_CHECK__', (ROOT/'PC/ui/assets/checkbox_check.svg').as_posix())


class ContentHeightTable(QtWidgets.QTableWidget):
    """结果按内容换行并展开全部行，由页面统一处理垂直滚动。"""
    def __init__(self, rows, columns):
        super().__init__(rows, columns)
        self.setWordWrap(True)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self._fit_timer = QtCore.QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(self._fit_content)
        self.model().dataChanged.connect(self._schedule_fit)
        self.horizontalHeader().sectionResized.connect(self._schedule_fit)
        self.horizontalHeader().geometriesChanged.connect(self._schedule_fit)

    def _schedule_fit(self, *_):
        if not self._fit_timer.isActive():
            self._fit_timer.start(0)

    def _fit_content(self):
        self.resizeRowsToContents()
        height = self.horizontalHeader().height() + self.verticalHeader().length() + 2*self.frameWidth()
        if self.horizontalHeader().length() > self.viewport().width():
            height += self.horizontalScrollBar().sizeHint().height()
        if self.height() != height:
            self.setFixedHeight(height)

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_fit()


class ScopeWindow(QtWidgets.QMainWindow):
    def __init__(self, profile_path=None):
        super().__init__()
        self.setWindowTitle(f"示波器显示界面 · EGO1 闭环测量平台 · PC {PC_RELEASE}")
        self.resize(1480, 940)
        self.setMinimumSize(1120, 760)
        self.worker = None
        self.hardware_connected = False
        self.device_rate = None
        self.device_dds_enabled = False
        self.profile_path = Path(profile_path) if profile_path is not None else ROOT / "PC/ui/hardware_profile.json"
        self._profile_requests = {}
        profile_error = None
        try:
            self._hardware_profile = read_hardware_profile(self.profile_path)
        except (OSError, ValueError, UnicodeError) as exc:
            self._hardware_profile = {}
            profile_error = str(exc)
        self.running = False
        self.single_pending = False
        self.capture_busy = False
        self.current = None
        self._cached_frame = None
        self._cached_calibration = None
        self._data_cache = {}
        self._dirty_tabs = {0, 1, 2}
        self._history_dirty = True
        self._roi_signature = None
        self._fft_rate = None
        self._commands_pending = 0
        self._closing = False
        self.csv_worker = None
        self.history = []
        self.capture_count = 0
        self.demo_ticks = 0
        self.rng = np.random.default_rng(2026)
        self.calibration = None
        self.baseline = None
        self.hardware_calibration = None
        self.absolute_calibration = None
        self.absolute_calibration_path = None
        self.absolute_dialog = None
        self.measurement_dialog = None
        self.hardware_baseline = None
        self.hardware_baseline_path = self.profile_path.with_name('hardware_calibration_baseline.json')
        baseline_error = None
        if self.hardware_baseline_path.exists():
            try:
                self.hardware_baseline = read_hardware_fingerprint(self.hardware_baseline_path)
            except (OSError,ValueError,TypeError,KeyError,RecursionError) as exc:
                baseline_error = str(exc)
        self.hardware_calibration_valid = False
        self.hardware_calibration_busy = False
        self._local_control = False
        self._handoff_resume = False
        self._calibration_start_pending = False
        self.auto_previous = None
        self.cal_step = -1
        self.demo_wait_started = time.monotonic()
        self.device_capabilities = 0
        self.device_build = None
        self.roi_busy = False
        self.device_frame_identity = None
        self.roi_timer = QtCore.QTimer(self)
        self.roi_timer.setSingleShot(True)
        self.roi_timer.setInterval(33)
        self.roi_timer.timeout.connect(self.render_roi)
        self._build()
        self.handoff_timer = QtCore.QTimer(self)
        self.handoff_timer.setInterval(1200)
        self.handoff_timer.timeout.connect(self.poll_handoff)
        self.ownership_probe_timer = QtCore.QTimer(self)
        self.ownership_probe_timer.setInterval(1000)
        self.ownership_probe_timer.timeout.connect(self.poll_ownership)
        self.ownership_probe_timer.start()
        self.apply_axes()
        self.tabs.currentChanged.connect(self.render_visible_tab)
        self.setStyleSheet(STYLE)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(100)
        self.timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.timeout.connect(self.update_header_status)
        self.timer.start()
        self.cal_timer = QtCore.QTimer(self)
        self.cal_timer.setInterval(160)
        self.cal_timer.timeout.connect(self.calibration_tick)
        self.refresh_ports()
        self.receive_capture(self.demo_capture(force=True))
        self.set_running(True)
        self.log("演示模式已就绪；当前波形和校准数据均为软件生成。")
        if profile_error:
            self.log(f"未载入硬件参数：{profile_error}；请重新应用有效配置。")
        if baseline_error:
            self.log('未载入实物基线：'+baseline_error)
        elif self.hardware_baseline is not None:
            self.log('已载入实物健康基线；连接匹配设备并重新自检后才允许应用校正。')
        default_voltage_profile = (ROOT if profile_path is None else self.profile_path.parent) / '校正参数.json'
        if default_voltage_profile.is_file():
            try:
                self.install_absolute_profile(default_voltage_profile)
                self.log('已自动载入固定电压校正参数；连接匹配设备后自动应用。')
            except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError) as exc:
                self.log('固定电压校正参数未载入：'+str(exc))

    @staticmethod
    def label(text, name=None):
        widget = QtWidgets.QLabel(text)
        if name:
            widget.setObjectName(name)
        return widget

    @staticmethod
    def button(text, callback, name=None):
        widget = QtWidgets.QPushButton(text)
        widget.clicked.connect(callback)
        if name:
            widget.setObjectName(name)
        return widget

    @staticmethod
    def combo(values):
        widget = ScopeComboBox()
        widget.addItems(values)
        return widget

    @staticmethod
    def spin(low, high, value, suffix="", decimals=3):
        widget = ScopeDoubleSpinBox()
        widget.setRange(low, high)
        widget.setDecimals(decimals)
        widget.setValue(value)
        widget.setSuffix(suffix)
        widget.setKeyboardTracking(False)
        return widget

    @staticmethod
    def group(title, parent):
        box = QtWidgets.QGroupBox(title)
        form = QtWidgets.QFormLayout(box)
        form.setSpacing(8)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        parent.addWidget(box)
        return form

    @staticmethod
    def plot(title, x="时间", xunit="s", y="幅度", yunit="V"):
        plot = pg.PlotWidget(title=title, background="#0c1421")
        plot.setLabel("bottom", x, units=xunit)
        plot.setLabel("left", y, units=yunit)
        plot.showGrid(x=True, y=True, alpha=0.17)
        plot.getPlotItem().setMenuEnabled(False)
        plot.getPlotItem().hideButtons()
        for axis in ("bottom", "left"):
            plot.getAxis(axis).setPen("#485c77")
            plot.getAxis(axis).setTextPen("#8c9eb8")
        return plot

    def _build(self):
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        outer = QtWidgets.QVBoxLayout(root)
        outer.setContentsMargins(18, 12, 18, 8)
        outer.setSpacing(10)
        header = QtWidgets.QWidget(objectName="header")
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(18, 12, 18, 12)
        header_layout.setSpacing(22)
        header.setMinimumHeight(88)
        self.header_title = self.label("闭环示波器", "title")
        header_layout.addWidget(self.header_title)
        header_layout.addStretch(1)
        self.device_info = self.label('', 'subtitle')
        self.device_info.hide()
        status_panel = QtWidgets.QFrame(objectName='headerStatus')
        status_layout = QtWidgets.QHBoxLayout(status_panel)
        status_layout.setContentsMargins(18, 13, 18, 13)
        status_layout.setSpacing(18)
        self.header_capture = self.label('等待采集', 'headerCapture')
        self.header_rate = self.label('采样率 —')
        self.header_record = self.label('记录长度 —')
        for index, widget in enumerate((self.header_capture, self.header_rate, self.header_record)):
            if index:
                divider = QtWidgets.QFrame(objectName='headerDivider')
                divider.setFixedSize(1, 20)
                status_layout.addWidget(divider)
            status_layout.addWidget(widget)
        self.header_rate.setToolTip('当前采样率')
        self.header_record.setToolTip('完整采集记录长度')
        header_layout.addWidget(status_panel)
        self.badge = self.label("●  演示数据", "badge")
        header_layout.addWidget(self.badge)
        outer.addWidget(header)

        bar = QtWidgets.QHBoxLayout()
        self.source = self.combo(["演示模式", "硬件串口"])
        self.source.setToolTip("演示模式：电脑生成模拟波形。硬件串口：读取真实硬件的完整16384点；多分辨率页可单独读取板端概览和ROI。")
        self.source.currentIndexChanged.connect(self.source_changed)
        self.port = self.combo([])
        self.port.setMinimumWidth(130)
        self.port.setMaximumWidth(270)
        self.baud = self.combo(["921600", "115200"])
        self.baud.setToolTip("当前实物固件使用 921600 bit/s；115200 仅供旧固件兼容。普通连接可回退，实际速率以握手结果为准。")
        self.connect_button = self.button("连接设备", self.toggle_connect)
        self.run_button = self.button("▶  RUN", lambda: self.set_running(True), "primary")
        self.stop_button = self.button("■  STOP", self.stop_capture, "stop")
        self.single_button = self.button("▸  SINGLE", self.single)
        self.single_button.setToolTip("严格等待所选触发，一次后保持；此按钮不使用 AUTO 超时触发。无信号预览请选择 AUTO 后点 RUN。")
        self.state_label = self.label("RUN · 等待数据")
        for widget in [self.source, self.port, self.baud, self.button("刷新", self.refresh_ports),
                       self.connect_button]:
            bar.addWidget(widget)
        bar.addStretch()
        outer.addLayout(bar)
        actions = QtWidgets.QHBoxLayout()
        for widget in [self.run_button, self.stop_button, self.single_button, self.state_label]:
            actions.addWidget(widget)
        actions.addStretch()
        self.csv_button = self.button("波形 CSV", self.export_csv)
        self.csv_button.setToolTip("导出当前读回样本的时间、原始ADC码、原始OTR位和电压；STOP后导出。")
        actions.addWidget(self.csv_button)
        self.summary_button=self.button("工程汇总 CSV",self.export_summary)
        self.summary_button.setEnabled(False)
        self.summary_button.setToolTip("连接实物并STOP后导出测量、时序、资源和通信证据；历史测试按固件区分。")
        actions.addWidget(self.summary_button)
        actions.addWidget(self.button("界面 PNG", self.export_png))
        outer.addLayout(actions)

        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)
        main = QtWidgets.QWidget()
        content = QtWidgets.QVBoxLayout(main)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(10)
        cards = QtWidgets.QHBoxLayout()
        self.metrics = {}
        for key, title in [("vpp", "峰峰值 · Vpp"), ("rms", "有效值 · RMS"),
                           ("frequency", "频率 · Frequency"), ("duty", "占空比 · Duty")]:
            card = QtWidgets.QFrame(objectName="metric")
            col = QtWidgets.QVBoxLayout(card)
            col.setContentsMargins(18, 12, 18, 12)
            col.setSpacing(6)
            col.addWidget(self.label(title, "metricTitle"))
            value = self.label("—", "metricValue")
            self.metrics[key] = value
            col.addWidget(value)
            cards.addWidget(card)
        content.addLayout(cards)
        self.tabs = QtWidgets.QTabWidget()
        content.addWidget(self.tabs, 1)
        self.build_wave_tab()
        self.build_spectrum_tab()
        self.build_multires_tab()
        self.build_calibration_tab()
        self.summary = self.label("采样率 25 MSPS  |  12 bit  |  记录 16,384 点  |  测量：PC 原始快照计算")
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("color:#8c9eb8; padding:5px;")
        content.addWidget(self.summary)
        split.addWidget(main)

        self.control_tabs = QtWidgets.QTabWidget(objectName="controlTabs")
        self.control_tabs.setMinimumWidth(320)
        self.control_tabs.setMaximumWidth(380)
        self.side_panel = self.control_tabs
        self.control_layouts = {}
        for key, title in (("capture", "采集"), ("trigger", "触发"), ("output", "输出"), ("tools", "工具")):
            area = QtWidgets.QScrollArea()
            area.setWidgetResizable(True)
            area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            page = QtWidgets.QWidget()
            area.setWidget(page)
            column = QtWidgets.QVBoxLayout(page)
            column.setContentsMargins(2, 8, 8, 4)
            column.setSpacing(12)
            self.control_layouts[key] = column
            self.control_tabs.addTab(area, title)
        self.side_layout = self.control_layouts["capture"]
        self.build_controls()
        split.addWidget(self.control_tabs)
        split.setStretchFactor(0, 1)
        split.setSizes([1080, 350])
        self.footer = self.label("快照 0  |  CRC 0")
        self.statusBar().addWidget(self.footer, 1)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedWidth(150)
        self.progress.setFormat("接收 %p%")
        self.statusBar().addPermanentWidget(self.progress)

    def build_wave_tab(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        line = QtWidgets.QHBoxLayout()
        line.addWidget(self.label("●  CH1  采集输入", "badge"))
        self.saturation_label = self.label("整帧饱和统计 —")
        line.addStretch()
        line.addWidget(self.saturation_label)
        layout.addLayout(line)
        self.wave_plot = self.plot("时域波形 · 鼠标滚轮缩放 / 拖动平移")
        self.wave_curve = self.wave_plot.plot(pen=pg.mkPen(CYAN, width=1), antialias=False)
        self.wave_curve.setClipToView(True)
        self.wave_curve.setDownsampling(auto=True, method="peak")
        self.trigger_line = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(GOLD, style=QtCore.Qt.PenStyle.DashLine),
                                            label="T", labelOpts={"position": 0.95, "color": GOLD})
        self.level_line = pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen(GOLD, style=QtCore.Qt.PenStyle.DashLine))
        self.level_line.sigPositionChangeFinished.connect(self.drag_trigger)
        self.wave_plot.addItem(self.trigger_line)
        self.wave_plot.addItem(self.level_line)
        self.time_cursors = [pg.InfiniteLine(pos=p, angle=90, movable=True, pen=pg.mkPen("#a69bff"),
                                            label=label) for p, label in [(-5e-6, "A"), (5e-6, "B")]]
        self.volt_cursors = [pg.InfiniteLine(pos=p, angle=0, movable=True, pen=pg.mkPen("#df88ca"),
                                            label=label) for p, label in [(-1.0, "Y1"), (1.0, "Y2")]]
        for cursor in self.time_cursors + self.volt_cursors:
            self.wave_plot.addItem(cursor)
            cursor.hide()
            cursor.sigPositionChanged.connect(self.update_cursors)
        layout.addWidget(self.wave_plot, 1)
        self.cursor_readout = self.label("光标关闭 · T 为触发位置，虚线为触发电平")
        self.extra_measure = self.label("最大值 —   最小值 —   均值 —   周期 —")
        layout.addWidget(self.cursor_readout)
        layout.addWidget(self.extra_measure)
        self.tabs.addTab(page, "时域波形")

    def build_spectrum_tab(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.label("FFT 点数"))
        self.fft_size = self.label("1024 点 · 固定")
        self.fft_window = self.combo(["Hann 窗", "矩形窗"])
        self.fft_window.currentIndexChanged.connect(self.fft_changed)
        row.addWidget(self.fft_size)
        row.addWidget(self.fft_window)
        row.addStretch()
        row.addWidget(self.label("PC 快照分析 · 0 dBFS = 5 V 峰值", "subtitle"))
        layout.addLayout(row)
        self.fft_plot = self.plot("单边幅度谱", "频率", "Hz", "幅度", "dBFS")
        self.fft_curve = self.fft_plot.plot(pen=pg.mkPen(CYAN, width=1.5), fillLevel=-160, brush="#123d4140")
        self.fft_plot.setYRange(-120, 5)
        layout.addWidget(self.fft_plot, 1)
        self.fft_info = self.label("—")
        self.fft_info.setWordWrap(True)
        self.fft_info.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.fft_info.setStyleSheet('padding:8px 4px;')
        layout.addWidget(self.fft_info)
        fft_note = self.label("青色频谱由 PC 对当前读回窗口计算；下方 FPGA 摘要取完整冻结帧前 1024 点，固定 Hann 窗。低频测频以整帧时域测量为准。", "subtitle")
        fft_note.setWordWrap(True)
        layout.addWidget(fft_note)
        self.tabs.addTab(page, "FFT 频谱")

    def build_multires_tab(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        row = QtWidgets.QHBoxLayout()
        self.multires_mode = QtWidgets.QCheckBox("板端概览 + 按需原始 ROI")
        self.multires_mode.setChecked(True)
        self.multires_columns = self.combo(["100", "200", "400", "800"])
        self.multires_columns.setCurrentIndex(3)
        row.addWidget(self.multires_mode)
        row.addWidget(self.label("概览桶数"))
        row.addWidget(self.multires_columns)
        self.envelope_export_button = self.button("保存板端概览 CSV", self.export_envelope_csv)
        self.envelope_export_button.setEnabled(False)
        row.addWidget(self.envelope_export_button)
        row.addStretch()
        layout.addLayout(row)
        self.roi_status = self.label("SINGLE/RUN 获取新帧；STOP 后拖动选区读取原始细节（最多 2048 点）。", "subtitle")
        self.roi_status.setWordWrap(True)
        layout.addWidget(self.roi_status)
        self.envelope_info = self.label("创新点二 · 全记录 min/max 包络 + 触发附近原始 ROI")
        self.envelope_info.setWordWrap(True)
        layout.addWidget(self.envelope_info)
        self.overview = self.plot("全记录概览 · 拖动选区查看原始细节")
        self.env_curve = self.overview.plot(pen=pg.mkPen(CYAN, width=1))
        self.roi_region = pg.LinearRegionItem(values=(-20e-6, 20e-6), brush="#37d8c722",
                                              pen=pg.mkPen(GOLD))
        self.overview.addItem(self.roi_region)
        self.roi_region.sigRegionChanged.connect(self.schedule_roi)
        self.roi_region.sigRegionChangeFinished.connect(self.request_hardware_roi)
        layout.addWidget(self.overview, 2)
        self.roi_plot = self.plot("ROI 原始样本")
        self.roi_curve = self.roi_plot.plot(pen=pg.mkPen(GOLD, width=1), antialias=False)
        self.roi_curve.setClipToView(True)
        self.roi_curve.setDownsampling(auto=True, method="peak")
        layout.addWidget(self.roi_plot, 2)
        layout.addWidget(self.label("快照历史 · 点击记录可冻结查看（PC 缓存最近 16 帧）", "subtitle"))
        self.history_table = QtWidgets.QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(["帧号", "首样本时间戳 / tick", "触发原因", "点数"])
        self.history_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.history_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setMaximumHeight(160)
        self.history_table.cellClicked.connect(self.select_history)
        layout.addWidget(self.history_table)
        self.tabs.addTab(page, "多分辨率采集")

    def build_calibration_tab(self):
        page = QtWidgets.QWidget()
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        layout = QtWidgets.QVBoxLayout(page)
        layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        self.cal_note = self.label('')
        note = self.cal_note
        note.setWordWrap(True)
        note.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        note.setStyleSheet("color:#aabbd2; padding:10px; background:#17283b; border-radius:5px;")
        note.hide()
        self.cal_button_tooltip = '连接 OUTA → IN，保持旋钮不动；完成后恢复原设置。'
        absolute_row = QtWidgets.QHBoxLayout()
        self.absolute_button = self.button('载入电压校正参数…', self.load_absolute_profile)
        # Internal selection state for the existing render/export pipeline.
        # External-reference calibration is now automatic, with no visible switch.
        self.apply_absolute = QtWidgets.QCheckBox(self)
        self.apply_absolute.hide()
        self.apply_absolute.setEnabled(False)
        self.apply_absolute.toggled.connect(self.absolute_toggled)
        absolute_row.addWidget(self.absolute_button)
        absolute_row.addStretch()
        layout.addLayout(absolute_row)
        self.absolute_status = self.label('外部参考电压校正：可载入已有标定参数')
        self.absolute_status.setWordWrap(True)
        self.absolute_status.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        layout.addWidget(self.absolute_status)
        row = QtWidgets.QHBoxLayout()
        self.cal_button = self.button("运行演示自检", self.start_calibration, "primary")
        self.cal_button.setToolTip(self.cal_button_tooltip)
        self.cal_cancel_button = self.button("取消自检并恢复", self.cancel_calibration)
        self.cal_cancel_button.setEnabled(False)
        self.rebuild_baseline = QtWidgets.QCheckBox('重建相对基线')
        self.rebuild_baseline.setObjectName('calibrationOption')
        self.rebuild_baseline.setToolTip('可选：下次实物闭环自检时，用当前接线和旋钮位置重新建立相对基线。')
        self.baseline_button = self.button("保存健康指纹", self.save_fingerprint)
        self.load_baseline_button = self.button("载入指纹并比较", self.load_fingerprint)
        self.apply_cal = QtWidgets.QCheckBox("显示应用相对校准")
        self.apply_cal.setObjectName('calibrationOption')
        self.apply_cal.toggled.connect(lambda checked: self.apply_absolute.setChecked(False) if checked else None)
        self.apply_cal.toggled.connect(self.render_current)
        self.apply_cal.setEnabled(False)
        for widget in [self.cal_button, self.cal_cancel_button, self.rebuild_baseline]:
            row.addWidget(widget)
        row.addStretch()
        layout.addLayout(row)
        baseline_row = QtWidgets.QHBoxLayout()
        for widget in [self.baseline_button, self.load_baseline_button, self.apply_cal]:
            baseline_row.addWidget(widget)
        baseline_row.addStretch()
        layout.addLayout(baseline_row)
        self.relative_calibration_hint = self.label('')
        self.relative_calibration_hint.setWordWrap(True)
        layout.addWidget(self.relative_calibration_hint)
        self.cal_progress = QtWidgets.QProgressBar()
        self.cal_progress.setValue(0)
        layout.addWidget(self.cal_progress)
        self.cal_table = ContentHeightTable(7, 3)
        self.cal_table.verticalHeader().setVisible(False)
        self.cal_table.verticalHeader().setDefaultSectionSize(28)
        self.cal_table.setHorizontalHeaderLabels(["步骤", "状态", "结果 / 说明"])
        self.cal_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.cal_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.cal_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.cal_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        for row, title in enumerate(["1  中码零点", "2  多点直流拟合", "3  幅度线性", "4  组合幅频响应",
                                     "5  噪声与谐波", "6  保存校准参数", "7  健康指纹比较"]):
            for col, value in enumerate([title, "待运行", "—"]):
                self.cal_table.setItem(row, col, QtWidgets.QTableWidgetItem(value))
        layout.addWidget(self.cal_table)
        self.cal_comparison_note = self.label('校准前后对比')
        self.cal_comparison_note.setWordWrap(True)
        self.cal_comparison_note.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        layout.addWidget(self.cal_comparison_note)
        self.cal_comparison = ContentHeightTable(2,4)
        self.cal_comparison.setHorizontalHeaderLabels(['独立验证点','相对目标 / mV','校准前误差 / mV','校准后误差 / mV'])
        self.cal_comparison.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.cal_comparison.verticalHeader().setVisible(False)
        self.cal_comparison.verticalHeader().setDefaultSectionSize(28)
        self.cal_comparison.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        for row,title in enumerate(('零点复测','+512 DAC 码（未参与拟合）')):
            for col,value in enumerate((title,'—','—','—')):
                self.cal_comparison.setItem(row,col,QtWidgets.QTableWidgetItem(value))
        layout.addWidget(self.cal_comparison)
        self.response_plot = self.plot("组合幅频响应 · 软件演示", "频率", "Hz", "相对增益", "dB")
        self.response_plot.setMinimumHeight(240)
        self.response_plot.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Ignored)
        self.response_plot.setLogMode(x=True)
        self.response_plot.getAxis("bottom").enableAutoSIPrefix(False)
        self.response_plot.getAxis("bottom").setTicks([[(3, "1k"), (4, "10k"), (5, "100k"), (6, "1M")]])
        self.response_curve = self.response_plot.plot(pen=pg.mkPen(CYAN, width=2), symbol="o", symbolSize=5)
        layout.addWidget(self.response_plot, 1)
        self.cal_result = self.label("未执行自检")
        self.cal_result.setWordWrap(True)
        self.cal_result.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        layout.addWidget(self.cal_result)
        self.tabs.addTab(scroll, "闭环自检与校准")

    def build_controls(self):
        form = self.group("采集与显示", self.side_layout)
        self.rate_label = self.label("25 MSPS · 演示")
        self.rate_label.setToolTip("硬件采样率只读；v1 不支持运行时切换 ADC 时钟。")
        form.addRow("ADC 采样率", self.rate_label)
        self.record = self.label("16384 点 · BRAM 固定")
        self.pretrigger = self.spin(0, 100, 50, " %", 0)
        form.addRow("记录长度", self.record)
        form.addRow("预触发比例", self.pretrigger)
        form.addRow(self.button("应用记录配置", self.apply_record))
        self.timebase = self.combo([eng(v, "s") + "/div" for v in TIME_DIVS])
        self.timebase.setCurrentIndex(5)
        self.volts_div = self.combo([eng(v, "V") + "/div" for v in VOLT_DIVS])
        self.volts_div.setCurrentIndex(5)
        self.display_center = VoltageInput(-10, 10, 0)
        self.timebase.currentIndexChanged.connect(self.apply_axes)
        self.volts_div.currentIndexChanged.connect(self.apply_axes)
        self.display_center.valueChanged.connect(self.apply_axes)
        form.addRow("水平时基", self.timebase)
        form.addRow("垂直刻度", self.volts_div)
        form.addRow("垂直中心", self.display_center)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.button("Autoscale", self.autoscale))
        self.undo_button = self.button("撤销", self.undo_autoscale)
        self.undo_button.setEnabled(False)
        row.addWidget(self.undo_button)
        form.addRow(row)

        form = self.group("采集控制", self.side_layout)
        self.acquisition_mode = self.combo(["AUTO · 超时自动触发", "NORMAL · 等待所选触发", "SINGLE · 单次保持"])
        self.acquisition_mode.setCurrentIndex(0)
        self.acquisition_mode.setToolTip("AUTO 无触发时由 FPGA 等待 100 ms 后触发；NORMAL 仅按所选条件触发；SINGLE 一次后保持。")
        form.addRow("采集模式", self.acquisition_mode)
        form = self.group("数字触发", self.control_layouts["trigger"])
        self.trigger_form = form
        self.trigger_box = form.parentWidget()
        self.trigger_type = self.combo(TRIGGERS)
        self.threshold = VoltageInput(-5, 5, 0)
        self.hysteresis = VoltageInput(0, 2, 0.04)
        self.win_low = VoltageInput(-5, 5, -0.5)
        self.win_high = VoltageInput(-5, 5, 0.5)
        self.width_min = self.spin(0.04, 1e6, 1, " µs", 2)
        self.width_max = self.spin(0.04, 1e6, 20, " µs", 2)
        self.amp_limit = VoltageInput(0, 10, 1)
        self.amp_limit.setToolTip("幅度门限为峰峰值，可选择 mV 或 V。")
        self.observation = ScopeSpinBox()
        self.observation.setRange(2, 16384)
        self.observation.setValue(1024)
        self.timeout = self.spin(1, 120, 5, " s", 0)
        for title, widget in [("类型", self.trigger_type), ("电平", self.threshold), ("迟滞", self.hysteresis),
                              ("窗口下限", self.win_low), ("窗口上限", self.win_high),
                              ("脉宽下限", self.width_min), ("脉宽上限", self.width_max),
                              ("幅度门限", self.amp_limit), ("观察点数", self.observation), ("单次等待上限", self.timeout)]:
            form.addRow(title, widget)
        self.trigger_type.currentIndexChanged.connect(self.trigger_fields_changed)
        self.threshold.valueChanged.connect(lambda v: self.level_line.setValue(v))
        form.addRow(self.button("应用触发配置", self.apply_trigger))
        self.trigger_fields_changed()

        form = self.group("DDS · AD9767 通道 A", self.control_layouts["output"])
        self.dds_wave = self.combo(["正弦波", "方波", "三角波", "直流", "任意波形表"])
        self.dds_freq = self.spin(0, 12500, 100, " kHz", 3)
        self.dds_freq.setToolTip('12.5 MHz 是数字设置上限。2026-10-29 固定旋钮、819码峰值闭环实测：'
                                '10 kHz～12.49 MHz 的已测频点通过基础检查；相对100 kHz幅度在±3 dB内的已测频点至8 MHz。'
                                '频点之间未逐点验收，不代表独立DAC质量或连续带宽。12.5 MHz仅作边界观察，详见使用说明。')
        self.dds_validation_note = self.label('闭环已测频点：10 kHz～12.49 MHz\n相对幅度±3 dB的已测频点至8 MHz', 'subtitle')
        self.dds_validation_note.setWordWrap(True)
        self.dds_validation_note.setToolTip('2026-10-29历史实测，峰值819码、固定旋钮。'
                                          '正弦为基础采样检查，方波/三角仅为基波检查；不是连续带宽或独立DAC质量保证。')
        self.dds_amplitude = self.spin(0, 100, 40, " %", 1)
        self.dds_phase = self.spin(0, 359.999, 0, " °", 1)
        self.dds_offset = ScopeSpinBox()
        self.dds_offset.setRange(-8192, 8191)
        self.dds_offset.setValue(0)
        self.dds_enable = QtWidgets.QCheckBox("启用数字波形输出")
        self.dds_enable.setChecked(True)
        for title, widget in [("波形", self.dds_wave), ("频率", self.dds_freq), ("数字幅度", self.dds_amplitude),
                              ("相位", self.dds_phase), ("中码偏移 / LSB", self.dds_offset)]:
            form.addRow(title, widget)
        form.addRow(self.dds_enable)
        form.addRow(self.dds_validation_note)
        form.addRow(self.button("应用 DDS 配置", self.apply_dds))
        self.awg_button=self.button("下载任意波形 CSV…",self.download_awg)
        form.addRow(self.awg_button)
        self.awg_label=self.label("波形表：未查询 · 选择1024点 CSV 文件", "subtitle")
        self.awg_label.setWordWrap(True)
        form.addRow(self.awg_label)
        self.awg_values=None

        note = self.label("数字幅度为 DAC 码比例；实际输出电压由闭环实测。\n直流 0 LSB 偏移对应中码 8192。", "subtitle")
        note.setWordWrap(True)
        form.addRow(note)

        form = self.group("光标与诊断", self.control_layouts["tools"])
        self.cursor_time = QtWidgets.QCheckBox("时间光标 A / B")
        self.cursor_volt = QtWidgets.QCheckBox("电压光标 Y1 / Y2")
        for option in (self.cursor_time, self.cursor_volt):
            option.setObjectName('cursorOption')
            option.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.cursor_time.toggled.connect(self.toggle_cursors)
        self.cursor_volt.toggled.connect(self.toggle_cursors)
        self.glitch = QtWidgets.QCheckBox("演示窄毛刺")
        self.glitch.setToolTip("在演示数据中加入单样本毛刺，用于查看 min/max 保峰效果。")
        form.addRow(self.cursor_time)
        form.addRow(self.cursor_volt)
        form.addRow(self.glitch)
        form.addRow(self.button("读取设备状态", self.request_status))
        self.overload_acceptance_label = self.label(OVERLOAD_ACCEPTANCE)
        self.overload_acceptance_label.setWordWrap(True)
        self.overload_acceptance_label.setToolTip(OVERLOAD_CONFIRMATION)
        self.overload_acceptance_label.hide()
        self.logs = QtWidgets.QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(120)
        self.logs.setMaximumHeight(110)
        form.addRow(self.logs)
        for column in self.control_layouts.values():
            column.addStretch()
        self.demo_dds = self.dds_config()
        self.demo_record = (16384, 0.5)
        self.demo_trigger = self.trigger_config()

    def log(self, message):
        self.logs.appendPlainText(datetime.now().strftime("%H:%M:%S  ") + message)
        self.statusBar().showMessage(message, 9000)

    def serial_fault(self, message):
        self.running = self.single_pending = False
        self._profile_requests.clear()
        if self.worker:
            self.worker.cancel_capture.set()
        self.state_label.setText("STOP · 查看诊断")
        self.log(message)

    def trigger_wait_finished(self, message):
        self.running = self.single_pending = False
        self.state_label.setText("STOP · 未收到触发")
        self.log(message)

    def receive_dds_configuration(self, payload):
        wave, enabled, frequency, phase, peak, offset = struct.unpack('<BBIIHi', payload)
        self.dds_wave.setCurrentIndex(wave)
        self.dds_enable.setChecked(bool(enabled))
        self.dds_freq.setValue(frequency/1000)
        self.dds_phase.setValue(phase*360/(1 << 32))
        self.dds_amplitude.setValue(peak*100/8191)
        self.dds_offset.setValue(offset)
        self.device_dds_enabled = bool(enabled)
        self.log(f"板端 DDS 已读回：{frequency} Hz，峰值 {peak} 码；修改后需点击应用 DDS 配置。")

    def command_finished(self):
        self._commands_pending = max(0, self._commands_pending-1)

    def submit_command(self, kind, payload, remember=True):
        if self.worker.submit("command", (kind, payload)):
            self._commands_pending += 1
            if remember and kind in (proto.SET_TRIGGER, proto.SET_DDS):
                # Snapshot at submission; later edits must not be saved as ACKed.
                settings = self.trigger_config() if kind == proto.SET_TRIGGER else self.dds_config()
                self._profile_requests[(kind, bytes(payload))] = settings
        else:
            self.log("设备请求队列已满，请等待确认后重试。")

    def remember_confirmed_command(self, kind, payload):
        settings = self._profile_requests.pop((kind, bytes(payload)), None)
        if settings is None or self.is_demo():
            return
        section = "trigger" if kind == proto.SET_TRIGGER else "dds"
        self._hardware_profile[section] = settings
        if section == "dds":
            self.hardware_calibration_valid = False
            self.apply_cal.setChecked(False)
            self.update_calibration_controls()
            self.device_dds_enabled = settings["enable"]
        temporary = None
        try:
            self.profile_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.profile_path.parent,
                                             prefix=".scope-profile-", suffix=".tmp", delete=False) as file:
                temporary = Path(file.name)
                json.dump({"format": "scope-ui-hardware-v1", **self._hardware_profile}, file,
                          ensure_ascii=False, indent=2)
            os.replace(temporary, self.profile_path)
        except OSError as exc:
            self.log(f"设备配置已确认，但参数保存失败：{exc}")
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def restore_hardware_controls(self):
        cfg = self._hardware_profile.get("trigger")
        if cfg:
            self.trigger_type.setCurrentIndex(cfg["kind"])
            for widget, name, scale in [(self.threshold, "threshold", 1), (self.hysteresis, "hysteresis", 1),
                    (self.win_low, "low", 1), (self.win_high, "high", 1),
                    (self.width_min, "width_min", 1e6), (self.width_max, "width_max", 1e6),
                    (self.amp_limit, "amplitude", 1), (self.observation, "observation", 1)]:
                widget.setValue(cfg[name] * scale)
        cfg = self._hardware_profile.get("dds")
        if cfg:
            self.dds_wave.setCurrentIndex(cfg["wave"])
            self.dds_freq.setValue(cfg["frequency"] / 1000)
            self.dds_amplitude.setValue(cfg["amplitude"] * 100)
            self.dds_phase.setValue(cfg["phase"])
            self.dds_offset.setValue(cfg["offset"])
            self.dds_enable.setChecked(cfg["enable"])
        if self._hardware_profile:
            self.log("已载入上次确认的硬件参数；连接后恢复触发，DDS 输出需手动应用。")

    def is_demo(self):
        return self.source.currentIndex() == 0





    def refresh_ports(self):
        previous = self.port.currentData()
        self.port.clear()
        try:
            for item in list_ports.comports():
                self.port.addItem(f"{item.device} · {item.description}", item.device)
        except (OSError, serial.SerialException) as exc:
            self.log(f"错误：串口枚举失败 · {exc}")
        if self.port.count() == 0:
            self.port.addItem("未检测到串口", None)
        index = self.port.findData(previous)
        if index >= 0:
            self.port.setCurrentIndex(index)
        self.port.setEnabled(not self.is_demo() and self.worker is None)
        self.baud.setEnabled(not self.is_demo() and self.worker is None)
        if self.worker is None:
            self.connect_button.setEnabled(not self.is_demo())

    def source_changed(self):
        self.apply_absolute.setChecked(False)
        self.stop_capture()
        if self.is_demo():
            self.acquisition_mode.setEnabled(True)
            if self.acquisition_mode.count() > 3:
                self.acquisition_mode.removeItem(3)
                self.acquisition_mode.setCurrentIndex(0)
        self.timer.setInterval(100)
        self.level_line.setVisible(True)
        self.trigger_box.setEnabled(True)
        self.device_frame_identity = None
        self.hardware_calibration_valid = False
        self.update_cursors()
        if not self.is_demo():
            self.restore_hardware_controls()
        self.current = None
        self._cached_frame = None
        self._data_cache.clear()
        self._roi_signature = self._fft_rate = None
        self.auto_previous = None
        self.undo_button.setEnabled(False)
        self.roi_timer.stop()
        self.device_rate = None
        self.history.clear()
        self.history_table.setRowCount(0)
        self.wave_curve.clear()
        self.fft_curve.clear()
        self.env_curve.clear()
        self.roi_curve.clear()
        self.envelope_export_button.setEnabled(False)
        self.csv_button.setText("波形 CSV")
        self.apply_cal.setChecked(False)
        self.show_calibration_comparison(None)
        self.response_curve.clear()
        self.response_plot.setTitle('组合幅频响应 · 等待当前数据源自检')
        self.update_calibration_controls()
        self.glitch.setEnabled(self.is_demo())
        self.glitch.setVisible(self.is_demo())
        self.summary_button.setEnabled(not self.is_demo())
        self.refresh_ports()
        self.badge.setText("●  演示数据" if self.is_demo() else "○  硬件未连接")
        self.device_build = None
        self.update_device_info()
        self.rate_label.setText("— · 等待设备回报" if not self.is_demo() else "25 MSPS · 演示")
        self.summary.setText("等待新数据 · 显示测量来自 PC 原始快照计算")
        self.footer.setText("等待新数据")
        self.saturation_label.setText("整帧饱和统计 —")
        self.extra_measure.setText("最大值 —   最小值 —   均值 —   周期 —")
        for label in self.metrics.values():
            label.setText("—")
        if self.is_demo():
            self.receive_capture(self.demo_capture(force=True))
        self.log("已切换到" + self.source.currentText())

    def toggle_connect(self):
        if self.worker is not None:
            self.stop_capture()
            self.worker.shutdown.set()
            self.connect_button.setEnabled(False)
            self.connect_button.setText("正在断开…")
            return
        port = self.port.currentData()
        if not port:
            self.log("错误：未检测到串口，请连接 EGO1 后刷新")
            return
        self.worker = SerialWorker(port, int(self.baud.currentText()))
        self.worker.connected.connect(self.connection_changed)
        self.worker.baud_ready.connect(lambda baud: self.baud.setCurrentText(str(baud)))
        self.worker.capabilities_ready.connect(self.receive_capabilities)
        self.worker.identity_ready.connect(self.receive_identity)
        self.worker.awg_ready.connect(self.receive_awg)
        self.worker.summary_ready.connect(lambda path:self.log("汇总报告已保存 · "+path))
        self.worker.roi_ready.connect(self.receive_roi)
        self.worker.roi_done.connect(self.roi_finished)
        self.worker.calibration_progress.connect(self.receive_calibration_progress)
        self.worker.calibration_result.connect(self.receive_hardware_calibration)
        self.worker.frame_ready.connect(self.receive_capture)
        self.worker.status_ready.connect(self.receive_status)
        self.worker.message.connect(self.log)
        self.worker.fault.connect(self.serial_fault)
        self.worker.trigger_wait_expired.connect(self.trigger_wait_finished)
        self.worker.dds_configuration_ready.connect(self.receive_dds_configuration)
        self.worker.configuration_ready.connect(self.receive_backend_configuration)
        self.worker.local_control.connect(self.handle_local_control)
        self.worker.command_done.connect(self.command_finished)
        self.worker.command_confirmed.connect(self.remember_confirmed_command)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.cycle_done.connect(self.cycle_finished)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()
        self.source.setEnabled(False)
        self.port.setEnabled(False)
        self.baud.setEnabled(False)
        self.connect_button.setText("正在握手…")
        self.connect_button.setEnabled(False)

    def connection_changed(self, connected):
        returning = connected and self._local_control
        self.hardware_connected = connected
        self.hardware_calibration_valid = False
        self.apply_cal.setChecked(False)
        self.apply_absolute.setChecked(False)
        self.badge.setText("●  硬件已连接" if connected else "○  硬件未连接")
        if connected:
            self._local_control = False
            self.handoff_timer.stop()
            self.state_label.setText('STOP · 已连接')
            self.connect_button.setText("断开设备")
            self.connect_button.setEnabled(True)
            self.log('已读取板端参数；电脑与显示屏切换不自动覆盖触发或输出设置。')
            if not self.device_dds_enabled:
                self.log("板端 DDS 未启用：OUTA→IN 闭环请先点击“应用 DDS 配置”；外部信号源可直接采集。")
        else:
            self.device_capabilities = 0
            self.device_frame_identity = None
            self.roi_busy = False
            self.running = False
            self.single_pending = False
            self.capture_busy = False
            self.state_label.setText('LOCAL · 显示屏控制中' if self._local_control else 'STOP · 未连接')
            if self._local_control:self.badge.setText('●  显示屏控制')
        self.update_calibration_controls()
        self.update_device_info()

        self.auto_apply_absolute_profile()
        if returning and self._handoff_resume:
            QtCore.QTimer.singleShot(150, self.resume_handoff)

    def receive_backend_configuration(self, data):
        cfg, mode = data
        kind,_,threshold,hysteresis,low,high,wmin,wmax,amplitude,observation = struct.unpack('<BBhHhhIIHI',cfg['trigger'])
        values = ((self.trigger_type,kind),(self.threshold,(threshold+.5)*SCALE),
                  (self.hysteresis,hysteresis*SCALE),(self.win_low,(low+.5)*SCALE),
                  (self.win_high,(high+.5)*SCALE),(self.width_min,wmin/25),
                  (self.width_max,wmax/25),(self.amp_limit,amplitude*SCALE),
                  (self.observation,observation),(self.pretrigger,cfg['pre']*100/(cfg['length']-1)),
                  (self.acquisition_mode,mode))
        for widget,value in values:
            blocker = QtCore.QSignalBlocker(widget)
            if isinstance(widget, QtWidgets.QComboBox):widget.setCurrentIndex(value)
            else:widget.setValue(value)
            del blocker
        self._hardware_profile['trigger'] = self.trigger_config()
        self.trigger_fields_changed()

    def handle_local_control(self):
        if not self._local_control:
            self._handoff_resume = self.running and self.acquisition_mode.currentIndex()!=2
            self.log('已交给显示屏控制；SW7 ON 后自动重连并读取当前板端参数。')
        self._local_control = True
        self.running = self.single_pending = False
        self.state_label.setText('LOCAL · 显示屏控制中')
        self.badge.setText('●  显示屏控制')
        self.handoff_timer.start()
        self.update_header_status()

    def poll_handoff(self):
        if self._closing or self.is_demo():
            self.handoff_timer.stop()
            return
        if self._local_control and self.worker is None:
            self.baud.setCurrentText('921600')
            self.toggle_connect()

    def poll_ownership(self):
        if (not self._closing and self.hardware_connected and not self.running
                and not self.capture_busy and not self.roi_busy and not self._commands_pending
                and not self.hardware_calibration_busy and not self._calibration_start_pending):
            self.request_status()

    def resume_handoff(self):
        if self.hardware_connected and self._handoff_resume and not self._closing:
            self._handoff_resume = False
            if self.acquisition_mode.currentIndex()!=2:self.set_running(True)

    def auto_apply_absolute_profile(self):
        if self.hardware_connected and not self.is_demo() and self.absolute_calibration is not None:
            report = self.absolute_calibration
            if (getattr(self.worker, 'device_identity', None) == report['device_id']
                    and abscal.firmware_matches(report, self.device_build)
                    and self.device_rate == report['rate']):
                self.apply_absolute.setChecked(True)
                self.log('已自动应用固定外部参考直流校正。')

    def receive_identity(self, build):
        self.device_build = build
        self.update_device_info()

    def update_device_info(self):
        if self.is_demo():
            text = "软件演示 · 25 MSPS / 12 bit / 16K · 不连接设备"
        elif not self.hardware_connected:
            text = "等待设备 · 固定25 MSPS / 12 bit / 16K · 连接后读取实际固件与能力"
        else:
            build = f"0x{self.device_build:08X}" if self.device_build is not None else "读取中"
            features = [name for flag, name in ((1, "包络/ROI"), (2, "配置读回"),
                        (4, "测量/FFT"), (8, "三模式"), (16, "整帧饱和"), (32, "任意波形"))
                        if self.device_capabilities & flag]
            text = f"固件 {build} · 25 MSPS / 12 bit / 16K · " + " / ".join(features)
        self.device_info.setToolTip(text)
        if not self.is_demo() and self.hardware_connected:
            text = f"{build}  ·  25 MSPS  ·  12 bit  ·  16K\n" + " / ".join(features)
        self.device_info.setText(text)
        self.header_title.setToolTip(text)
        self.update_header_status()

    def update_header_status(self):
        available = self.is_demo() or self.hardware_connected
        if not available:
            state = '显示屏控制' if self._local_control else '正在连接' if self.worker is not None else '等待连接'
        elif self.hardware_calibration_busy or self._calibration_start_pending or self.cal_step >= 0:
            state = '闭环自检'
        elif self.single_pending:
            state = '等待触发'
        else:
            state = '正在采集' if self.running else '波形已暂停'
        rate = self.current.rate if self.is_demo() and self.current is not None else self.device_rate
        self.header_capture.setText(state)
        self.header_rate.setText('采样率 '+eng(rate, 'SPS') if available and rate else '采样率 —')
        self.header_record.setText('记录长度 16 K 点' if available else '记录长度 —')

    def worker_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self._commands_pending = 0
        self._profile_requests.clear()
        self.device_rate = None
        self.source.setEnabled(True)
        self.connect_button.setText("连接设备")
        self.connect_button.setEnabled(True)
        self.port.setEnabled(True)
        self.baud.setEnabled(True)
        if self.hardware_calibration_busy:
            self.hardware_calibration_busy = False
            self.cal_step = -1
            self.side_panel.setEnabled(True)
            self.cal_result.setText("自检连接已中断；请确认 DDS/触发恢复状态后重新连接并测试。")
        self.update_calibration_controls()

    def receive_status(self, state):
        self.device_dds_enabled = bool(state["flags"] & 4)
        if state["rate"]:
            self.device_rate = state["rate"]
            self.rate_label.setText(eng(state["rate"], "SPS") + " · 设备")
        c = state["counters"]
        self.footer.setText(f"快照 {self.capture_count}  |  PC CRC {state['pc_crc']}  |  FPGA CRC {c[0]}"
                            f"  |  超时 {c[3]}  |  RX 溢出 {c[7]}  |  后端错误 {state['backend_error']}")

    def request_status(self):
        if self.is_demo():
            self.log(f"演示状态 · 快照 {self.capture_count} · 无真实串口统计")
        elif self.hardware_connected:
            self.worker.submit("status")
        else:
            self.log("错误：请先连接设备")

    def set_running(self, value):
        if value:
            if self._closing or self._calibration_start_pending or self.cal_step >= 0:
                return False
            if self.capture_busy or self.roi_busy or self._commands_pending:
                self.log("请等待当前接收或配置确认完成后再启动采集。")
                return False
            if not self.is_demo() and not self.hardware_connected:
                self.log("错误：请先连接设备")
                return False
            self.demo_wait_started = time.monotonic()
        self.running = value
        self.single_pending = False
        self.state_label.setText("RUN · 连续快照" if value else "STOP · 已冻结")
        if value and self.acquisition_mode.currentIndex() == 2:
            self.running = False
            self.single_pending = True
            self.state_label.setText("SINGLE · 等待触发")
        self.update_header_status()
        return True

    def stop_capture(self):
        self.set_running(False)
        if self.worker is not None:
            self.worker.request_stop()

    def single(self):
        if not self.set_running(True):
            return
        self.running = False
        self.single_pending = True
        self.state_label.setText("SINGLE · 等待触发")
        self.tick()

    def tick(self):
        if self.cal_step >= 0 or not (self.running or self.single_pending):
            return
        if self.is_demo():
            frame = self.demo_capture(force=(self.acquisition_mode.currentIndex() == 0
                and not self.single_pending and time.monotonic()-self.demo_wait_started >= 0.1))
            if frame is not None:
                self.receive_capture(frame)
                self.demo_wait_started = time.monotonic()
                if self.single_pending:
                    self.single_pending = False
                    self.state_label.setText("STOP · 单次完成")
            elif (self.single_pending or self.acquisition_mode.currentIndex() != 1) and time.monotonic() - self.demo_wait_started >= self.timeout.value():
                self.stop_capture()
                self.log("等待触发超时；请检查触发门限与演示信号")
            else:
                self.state_label.setText("WAIT · 等待触发")
        elif self.hardware_connected and not self.capture_busy:
            self.capture_busy = True
            self.progress.setValue(0)
            self.worker.cancel_capture.clear()
            request = self.timeout.value()
            if self.tabs.currentIndex() == 2 and self.multires_mode.isChecked():
                request = (request, None, int(self.multires_columns.currentText()))
            mode = 2 if self.single_pending else self.acquisition_mode.currentIndex()
            if mode == 3:
                mode = None
            if mode == 2:
                self.running = False
                self.single_pending = True
            args = request if isinstance(request, tuple) else (request,)
            request = (*args, *([None]*(3-len(args))), mode)
            if not self.worker.submit("capture", request):
                self.capture_busy = False

    def cycle_finished(self):
        self.capture_busy = False
        if self.single_pending:
            self.single_pending = False
            self.state_label.setText("STOP · 单次结束")

    def trigger_fields_changed(self):
        kind = self.trigger_type.currentIndex()
        for widget in [self.win_low, self.win_high]:
            widget.setEnabled(kind in (2, 3))
            self.trigger_form.setRowVisible(widget, kind in (2, 3))
        for widget in [self.width_min, self.width_max]:
            widget.setEnabled(kind in (4, 5))
            self.trigger_form.setRowVisible(widget, kind in (4, 5))
        for widget in [self.amp_limit, self.observation]:
            widget.setEnabled(kind in (6, 7))
            self.trigger_form.setRowVisible(widget, kind in (6, 7))

    def trigger_config(self):
        return {"kind": self.trigger_type.currentIndex(), "threshold": self.threshold.value(),
                "hysteresis": self.hysteresis.value(), "low": self.win_low.value(), "high": self.win_high.value(),
                "width_min": self.width_min.value()*1e-6, "width_max": self.width_max.value()*1e-6,
                "amplitude": self.amp_limit.value(), "observation": self.observation.value()}

    def dds_config(self):
        return {"wave": self.dds_wave.currentIndex(), "frequency": self.dds_freq.value()*1000,
                "amplitude": self.dds_amplitude.value()/100, "phase": self.dds_phase.value(),
                "offset": self.dds_offset.value(), "enable": self.dds_enable.isChecked()}

    def can_configure(self):
        if self.running or self.capture_busy or self.roi_busy or self.single_pending or self._calibration_start_pending or self.cal_step >= 0:
            self.log("请先 STOP，待当前接收结束后应用配置。")
            return False
        if not self.is_demo() and not self.hardware_connected:
            self.log("错误：请先连接设备")
            return False
        return True

    def apply_record(self):
        if not self.can_configure():
            return
        length = 16384
        ratio = self.pretrigger.value()/100
        if self.is_demo():
            self.demo_record = length, ratio
            self.log(f"演示记录已应用 · {length:,} 点 · 预触发 {ratio:.0%}")
        else:
            self.submit_command(proto.SET_RECORD, struct.pack("<II", length, round(ratio*1e6)))

    def trigger_payload(self, cfg):
        # FPGA signed13 使用 2047-raw，与电压换算相差半个 LSB。
        code = lambda v: int(np.clip(round(v/SCALE - 0.5), -4096, 4095))
        if not self.is_demo() and cfg["kind"] in (4, 5) and not self.device_rate:
            raise ValueError("尚未获得设备采样率，请先读取设备状态")
        rate = (25000000
                if self.is_demo() else self.device_rate or 25000000)
        h = round(cfg["hysteresis"]/SCALE)
        lo, hi = code(cfg["low"]), code(cfg["high"])
        if cfg["kind"] in (2, 3) and lo+h >= hi-h:
            raise ValueError("窗口必须满足：下限 + 迟滞 < 上限 - 迟滞")
        minimum, maximum = max(1, round(cfg["width_min"]*rate)), max(1, round(cfg["width_max"]*rate))
        if cfg["kind"] in (4, 5) and minimum > maximum:
            raise ValueError("脉宽下限不能大于上限")
        return struct.pack("<BBhHhhIIHI", cfg["kind"], 0, code(cfg["threshold"]), h, lo, hi,
                           minimum, maximum, round(cfg["amplitude"]/SCALE), cfg["observation"])

    def apply_trigger(self):
        if not self.can_configure():
            return
        cfg = self.trigger_config()
        try:
            payload = self.trigger_payload(cfg)
        except ValueError as exc:
            self.log(f"错误：{exc}")
            return
        if self.is_demo():
            self.demo_trigger = cfg
            self.log("演示触发已应用 · " + TRIGGERS[cfg["kind"]])
        else:
            self.submit_command(proto.SET_TRIGGER, payload)

    def receive_awg(self,result):
        self.awg_label.setText(f"波形表：{'已校验' if result['valid'] else '未下载'} · {'已选择' if result['selected'] else '标准DDS'} · CRC {result['active_crc']:04X}")
        if result.get('valid'):self.dds_wave.setCurrentIndex(4 if result['selected'] else min(self.dds_wave.currentIndex(),3))
        self.device_dds_enabled=False if result.get('uploading') else self.device_dds_enabled

    def download_awg(self):
        if not self.can_configure() or self._commands_pending:return
        if not self.is_demo() and not self.device_capabilities & awg.CAPABILITY:
            self.log('当前固件不支持任意波形下载，请加载支持该功能的镜像。');return
        path,_=QtWidgets.QFileDialog.getOpenFileName(self,'选择任意波形文件',str(ROOT/'任意波形.csv'),'CSV (*.csv);;文本 (*.txt)')
        if not path:return
        try:values=awg.load_table(path)
        except (ValueError,OSError) as exc:self.log(f'波形表文件无效：{exc}');return
        if self.is_demo():
            self.awg_values=values;self.awg_label.setText('演示波形表已加载 · 1024点');return
        if self.worker.submit('awg',{"action": 'upload',"values": values}):
            self._commands_pending+=1
            self.dds_enable.setChecked(False)
            self.device_dds_enabled=False
            self.awg_label.setText('下载并核对板端读回中…')

    def apply_dds(self):
        if not self.can_configure():
            return
        cfg = self.dds_config()
        if cfg['wave']==4 and self.is_demo() and self.awg_values is None:
            self.log('请先加载任意波形表');return
        if self.is_demo():
            self.demo_dds = cfg
            self.log("演示 DDS 参数已应用")
        else:
            phase = round(cfg["phase"]/360 * (1 << 32)) & 0xFFFFFFFF
            # 幅度使用相对中码的半摆幅；100% 对应 8191 LSB，避免无偏置时数字削顶。
            payload = struct.pack("<BBIIHi", min(cfg["wave"],3), int(cfg["enable"]), round(cfg["frequency"]),
                                  phase, round(cfg["amplitude"]*8191), cfg["offset"])
            if self.device_capabilities & awg.CAPABILITY:
                if self.worker.submit('awg',{"action": 'apply',"selected": cfg['wave']==4,"payload": payload}):
                    self._commands_pending+=1
                    if cfg['wave'] != 4:
                        self._profile_requests[(proto.SET_DDS, bytes(payload))] = cfg
            elif cfg['wave']==4:self.log('当前固件不支持任意波形表')
            else:self.submit_command(proto.SET_DDS, payload)

    def demo_capture(self, force=False):
        rate = 25000000
        length, ratio = self.demo_record
        pre = int(math.floor((length-1)*ratio + 0.5))
        cfg = self.demo_dds
        phase = np.arange(length*2)/rate * cfg["frequency"] + cfg["phase"]/360 + 0.137
        if cfg["wave"] == 4:
            ideal=np.asarray(self.awg_values)[np.floor((phase%1)*1024).astype(int)]/32767
        elif cfg["wave"] == 0:
            ideal = np.sin(2*np.pi*phase)
        elif cfg["wave"] == 1:
            ideal = np.where(phase % 1 < 0.5, 1., -1.)
        elif cfg["wave"] == 2:
            ideal = 1 - 4*np.abs(phase % 1 - 0.5)
        else:
            ideal = np.zeros(length*2)
        signal = (ideal * cfg["amplitude"]*3.2 + cfg["offset"]/8192*3.2) if cfg["enable"] else np.zeros(length*2)
        y = signal * 0.973 + 0.027 + self.rng.normal(0, 0.003, length*2)
        if self.glitch.isChecked():
            y[length//2+97] += 2.8
            y[length+length//2+97] += 2.8
        trigger = self.demo_trigger
        kind, level, h = trigger["kind"], trigger["threshold"], trigger["hysteresis"]
        # 演示使用有迟滞的理想信号判决，噪声保留在原始快照中。
        z = signal * 0.973 + 0.027
        candidates = np.array([], dtype=int)
        if kind in (0, 1):
            above = z >= level
            candidates = np.flatnonzero((~above[:-1] & above[1:]) if kind == 0 else (above[:-1] & ~above[1:])) + 1
            if z.min() > level-h/2 or z.max() < level+h/2:
                candidates = np.array([], dtype=int)
        elif kind in (2, 3):
            inside = (z >= trigger["low"]+h) & (z <= trigger["high"]-h)
            candidates = np.flatnonzero((~inside[:-1] & inside[1:]) if kind == 2 else (inside[:-1] & ~inside[1:]))+1
        elif kind in (4, 5):
            active = z >= level if kind == 4 else z < level
            changes = np.diff(np.r_[False, active, False].astype(np.int8))
            starts, ends = np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)
            widths = (ends-starts)/rate
            candidates = ends[(starts > 0) & (ends < len(z)) &
                              (widths >= trigger["width_min"]) & (widths <= trigger["width_max"])]
        elif kind in (6, 7):
            size = trigger["observation"]
            edges = np.arange(1, (len(z)-1)//size+1)*size
            spans = np.ptp(z[:len(edges)*size].reshape(-1, size), axis=1)
            candidates = edges[spans < trigger["amplitude"] if kind == 6 else spans > trigger["amplitude"]]
        elif kind == 8:
            candidates = np.flatnonzero(np.abs(y) > 5)
        candidates = candidates[(candidates >= pre) & (candidates <= len(y) - (length-pre))]
        if not len(candidates) and not force:
            return None
        at = int(candidates[0]) if len(candidates) else length//2
        start = max(0, min(at-pre, len(y)-length))
        segment = y[start:start+length]
        raw = np.clip(np.rint(4095 - (segment+5)/SCALE), 0, 4095).astype(np.uint16)
        raw |= (np.abs(segment) > 5).astype(np.uint16) << 15
        self.demo_ticks += length + rate//10
        return Capture(raw, rate, at-start, self.demo_ticks, "软件演示", TRIGGERS[kind] if len(candidates) else "预览")

    def display_data(self):
        calibration = self.active_display_calibration()
        if self._cached_frame is not self.current or calibration != self._cached_calibration:
            self._cached_frame = self.current
            self._cached_calibration = calibration
            self._data_cache = {}
            if self.current is not None:
                y = self.current.volts()
                if calibration:
                    y = (y-calibration[0])/calibration[1]
                self._data_cache.update(t=self.current.times(), y=y)
        return self._data_cache

    def active_display_calibration(self):
        if self.apply_absolute.isChecked():
            report = self.absolute_calibration
            device_id = getattr(self.worker, 'device_identity', None)
            if (not self.is_demo() and self.hardware_connected and report is not None
                    and abscal.applicable(report, self.current, device_id)):
                return report['display_offset'], report['display_gain']
            return None
        if not self.apply_cal.isChecked():
            return None
        if self.is_demo() and self.calibration:
            return self.calibration['offset'],self.calibration['gain']
        if (not self.is_demo() and self.hardware_connected and self.hardware_calibration_valid
                and self.hardware_calibration and self.current is not None and self.current.source == '硬件 UART'):
            values = self.current.volts()
            report = self.hardware_calibration
            means = [v['mean_code'] for v in report['dc_points']]
            margin = max(2*SCALE,4*report['noise'])
            low,high = (min(means)+0.5)*SCALE-margin,(max(means)+0.5)*SCALE+margin
            if self.current.overview is not None:
                _,lows,highs = self.current.overview.arrays()
                if float(lows.min()) < low or float(highs.max()) > high:
                    return None
            if float(values.min()) < low or float(values.max()) > high:
                return None
            return self.hardware_calibration['offset'],self.hardware_calibration['gain']
        return None

    def display_volts(self):
        return self.display_data()["y"]

    def current_measurement(self):
        data = self.display_data()
        if "measurement" not in data:
            m = self.current.fpga_measurement
            if m is not None and self.apply_absolute.isChecked() and self.active_display_calibration():
                report = self.absolute_calibration
                multiplier = -report['slope_volts_per_raw']
                bias = 2047*report['slope_volts_per_raw']+report['intercept_volts']
                mean_x, mean_x2 = m['sum']/m['count'], m['square_sum']/m['count']
                frequency = m['frequency'] if m['period_valid'] else math.nan
                data['measurement'] = {'vpp': multiplier*m['vpp'],
                    'rms': math.sqrt(max(0, multiplier**2*mean_x2+2*multiplier*bias*mean_x+bias**2)),
                    'mean': multiplier*mean_x+bias, 'minimum': multiplier*m['minimum']+bias,
                    'maximum': multiplier*m['maximum']+bias, 'frequency': frequency,
                    'period': m['period_q16']/65536/self.current.rate if m['period_valid'] else math.nan,
                    'duty': m['duty_ppm']/10000 if m['duty_valid'] else math.nan}
            elif m is not None and not self.active_display_calibration():
                # Hardware signed ADC units are half a code below the nominal
                # voltage mapping. Use exact moments to retain that correction.
                frequency = m['frequency'] if m['period_valid'] else math.nan
                data['measurement'] = {"vpp": m['vpp']*SCALE,
                    "rms": math.sqrt(max(0,(m['square_sum']+m['sum']+m['count']*.25)/m['count']))*SCALE,
                    "mean": (m['sum']/m['count']+.5)*SCALE,"minimum": (m['minimum']+.5)*SCALE,
                    "maximum": (m['maximum']+.5)*SCALE,"frequency": frequency,
                    "period": m['period_q16']/65536/self.current.rate if m['period_valid'] else math.nan,
                    "duty": m['duty_ppm']/10000 if m['duty_valid'] else math.nan}
            else:
                data['measurement'] = measure(data['y'],self.current.rate)
        return data['measurement']

    def receive_capture(self, frame):
        if frame.source != ("软件演示" if self.is_demo() else "硬件 UART"):
            return
        # STOP 或选择历史后，不让已经排入 Qt 信号队列的旧帧覆盖冻结画面。
        if not self.is_demo() and not (self.hardware_connected and (self.running or self.single_pending)):
            return
        self.current = frame
        if not self.is_demo():
            self.device_frame_identity = (frame.overview.timestamp if frame.overview is not None
                                          else (frame.timestamp-frame.record_offset) % (1 << 64))
        self.capture_count += 1
        self.history.insert(0, (self.capture_count, frame))
        del self.history[16:]
        self._history_dirty = True
        self.render_current()
        if self.is_demo():
            self.footer.setText(f"演示快照 {self.capture_count}  |  CRC —（未连接硬件）  |  原始 ADC 码已保留")
        self.progress.setValue(100)
        if self.running:
            self.state_label.setText("RUN · 连续快照")

    def render_current(self, *_):
        if self.current is None:
            return
        frame = self.current
        self.envelope_export_button.setEnabled(frame.overview is not None)
        self.csv_button.setText("ROI CSV" if frame.overview is not None else "波形 CSV")
        y = self.display_volts()
        result = self.current_measurement()
        self.metrics["vpp"].setText(eng(result["vpp"], "V"))
        self.metrics["rms"].setText(eng(result["rms"], "V"))
        self.metrics["frequency"].setText(eng(result["frequency"], "Hz"))
        self.metrics["duty"].setText(f"{result['duty']:.2f} %" if math.isfinite(result["duty"]) else "—")
        self.extra_measure.setText(f"最大值 {eng(result['maximum'], 'V')}     最小值 {eng(result['minimum'], 'V')}"
                                   f"     均值 {eng(result['mean'], 'V')}     周期 {eng(result['period'], 's')}")
        saturation=frame.fpga_saturation
        provenance="FPGA"
        if saturation is None and len(frame.words)==16384 and frame.overview is None:
            raw=frame.words&4095
            mask=(raw==0)|(raw==4095)
            saturation={'saturated_samples':int(mask.sum()),
                'events':int(np.count_nonzero(mask & ~np.r_[False,mask[:-1]])),
                'diagnostic':False}
            provenance="演示" if self.is_demo() else "PC 完整帧"
        if saturation is None:
            self.saturation_label.setText("整帧饱和统计 — · 需要支持整帧计数的固件")
        else:
            diagnostic=" · 板内诊断帧" if saturation['diagnostic'] else ""
            self.saturation_label.setText(f"整帧饱和样本 {saturation['saturated_samples']:,} / 16,384"
                f" · 连续事件 {saturation['events']:,} · {provenance}{diagnostic}")
        self.saturation_label.setToolTip("整帧原始 ADC 码为 0 或 4095 的样本计一次；连续区间计一次事件。帧首和帧尾不相连。")
        self.summary.setText(f"{frame.source}  |  {eng(frame.rate, 'SPS')}  |  12 bit"
                             f"  |  当前读回 {len(y):,} 点 / {eng(len(y)/frame.rate, 's')}  |  PC 快照测量")
        if frame.overview is not None:
            self.summary.setText(f"硬件板端概览 {frame.overview.length:,} 点  |  原始 ROI 细节"
                                 f"  |  {eng(frame.rate, 'SPS')}  |  PC 曲线来自 ROI")
        if frame.fpga_measurement is not None and not self.active_display_calibration():
            self.summary.setText(self.summary.text().replace("  |  PC 快照测量", ""))
            self.summary.setText(self.summary.text()+"  |  测量：FPGA 整帧测量16384点 / 655.36 µs · FFT摘要：FPGA前1024点")
        if not self.is_demo() and self.apply_absolute.isChecked():
            text = ('外部参考直流校正' if self.active_display_calibration()
                    else '外部参考校正未应用 · 设备、范围或异常状态不匹配')
            self.summary.setText(self.summary.text()+'  |  '+text)
        elif not self.is_demo() and self.active_display_calibration():
            self.summary.setText(self.summary.text()+"  |  闭环相对基线校正（非绝对校准）")
        elif not self.is_demo() and self.apply_cal.isChecked() and self.hardware_calibration_valid:
            self.summary.setText(self.summary.text()+"  |  当前幅度超出实测校准范围，未应用校正")
        self.rate_label.setText(eng(frame.rate, "SPS") + (" · 演示" if self.is_demo() else " · 设备"))
        self._dirty_tabs.update((0, 1, 2))
        self.render_visible_tab()

    def render_visible_tab(self, *_):
        index = self.tabs.currentIndex()
        if self.current is None or index not in self._dirty_tabs:
            return
        if index == 0:
            data = self.display_data()
            self.wave_curve.setData(data["t"], data["y"])
        elif index == 1:
            self.render_spectrum()
        elif index == 2:
            self.render_envelope()
            self.refresh_history()
        self._dirty_tabs.discard(index)

    def refresh_history(self):
        if not self._history_dirty:
            return
        self.history_table.setUpdatesEnabled(False)
        try:
            self.history_table.setRowCount(len(self.history))
            for row, (number, item) in enumerate(self.history):
                size = (f"{item.overview.length:,} / ROI {len(item.words):,}" if item.overview is not None
                        else f"{len(item.words):,}")
                first_timestamp = item.overview.timestamp if item.overview is not None else item.timestamp
                for col, value in enumerate([number, first_timestamp, item.reason, size]):
                    cell = self.history_table.item(row, col)
                    if cell is None:
                        self.history_table.setItem(row, col, QtWidgets.QTableWidgetItem(str(value)))
                    else:
                        cell.setText(str(value))
        finally:
            self.history_table.setUpdatesEnabled(True)
        self._history_dirty = False

    def fft_changed(self, *_):
        self._dirty_tabs.add(1)
        self.render_visible_tab()

    def apply_axes(self, *_):
        horizontal = TIME_DIVS[self.timebase.currentIndex()]
        vertical = VOLT_DIVS[self.volts_div.currentIndex()]
        self.wave_plot.setXRange(-5*horizontal, 5*horizontal, padding=0)
        center = self.display_center.value()
        self.wave_plot.setYRange(center-4*vertical, center+4*vertical, padding=0)
        # 网格间隔匹配面板的 s/div、V/div。
        self.wave_plot.getAxis("bottom").setTickSpacing(horizontal, horizontal/5)
        self.wave_plot.getAxis("left").setTickSpacing(vertical, vertical/5)

    def fpga_spectrum_text(self):
        spec = self.current.fpga_spectrum
        if spec is None:
            return ''
        hardware = (f"FPGA 冻结帧前 1024 点 · 周期 Hann 窗 · Δf {eng(self.current.rate/1024,'Hz')}"
                    + (f" · 主峰 {eng(spec['frequency'],'Hz')} / {eng(spec['amplitude']*SCALE,'V')}"
                       if spec['valid'] else " · 主峰无效"))
        hardware += "\nFPGA 谐波峰值："+" · ".join(
            f"H{h['order']} {eng(h['frequency'],'Hz')} / {eng(h['amplitude']*SCALE,'V')}" if h['valid'] else f"H{h['order']} —"
            for h in spec['harmonics'])
        if self.apply_absolute.isChecked():
            hardware += ' · FPGA 幅值为标称换算；PC 曲线按当前显示校正'
        if spec['clipped']:
            hardware += " · 幅度超出有效范围"
        return hardware

    def render_spectrum(self, *_):
        if self.current is None:
            return
        hardware = self.fpga_spectrum_text()
        if len(self.current.words) < 1024:
            self.fft_curve.clear()
            text = "当前窗口不足 1024 点，请选择完整采集或扩大窗口。"
            self.set_spectrum_info(hardware+"\n"+text if hardware else text)
            return
        data = self.display_data()
        key = (1024,self.fft_window.currentIndex() == 0)
        if data.get("fft_key") != key:
            data["fft_key"] = key
            data["fft"] = spectrum(data["y"],self.current.rate,*key)
        f,db,peak,harmonics,spacing = data["fft"]
        self.fft_curve.setData(f,db)
        if self._fft_rate != self.current.rate:
            self._fft_rate = self.current.rate
            self.fft_plot.setXRange(0,self.current.rate/2,padding=0)
        text = (f"PC 当前原始窗口 · 主峰 {eng(f[peak],'Hz')} | Δf = {eng(spacing,'Hz')}"
                f" | 1024 点 · {self.fft_window.currentText()}")
        if harmonics:
            text += "\n谐波幅度（PC）："+" · ".join(f"H{h} {eng(a,'V')}" for h,_,a in harmonics)
        if np.ptp(data['y'][:1024]) < 8*SCALE:
            text = "PC 信号幅度不足，主峰无效 | Δf = "+eng(spacing,'Hz')
        if hardware:
            text = hardware+"\n"+text
        self.set_spectrum_info(text)

    def set_spectrum_info(self, text):
        rows = []
        columns = 4 if self.tabs.width() >= 1050 else 2
        span = columns+1
        for line in text.splitlines():
            if '谐波峰值：' in line or '谐波幅度（PC）：' in line:
                title, values = line.split('：', 1)
                parts = values.split(' · ')
                for start in range(0, min(4,len(parts)), columns):
                    cells = ''.join('<td style="padding:6px 24px 6px 0;">'+html.escape(value)+'</td>'
                                    for value in parts[start:start+columns])
                    rows.append('<tr><td style="padding:6px 22px 6px 0;color:#91a4be;">'
                                +(html.escape(title) if start == 0 else '')+'</td>'+cells+'</tr>')
                if parts[4:]:
                    rows.append(f'<tr><td colspan="{span}" style="padding:4px 0;color:#91a4be;">'
                                +html.escape(' · '.join(parts[4:]))+'</td></tr>')
            else:
                rows.append(f'<tr><td colspan="{span}" style="padding:7px 0;">'+html.escape(line)+'</td></tr>')
        self.fft_info.setText('<table cellspacing="0" cellpadding="0">'+''.join(rows)+'</table>')

    def render_envelope(self):
        if self.current is None:
            return
        data = self.display_data()
        t, y = data["t"], data["y"]
        if self.current.overview is not None:
            env = self.current.overview
            centers, lo, hi = env.arrays()
            correction = self.active_display_calibration()
            if correction:
                lo,hi = (lo-correction[0])/correction[1],(hi-correction[0])/correction[1]
            self.env_curve.setData(np.repeat(centers, 2), np.column_stack((lo, hi)).ravel(), connect="pairs")
            signature = (env.timestamp, env.length, len(env.buckets))
            if self._roi_signature != signature:
                self._roi_signature = signature
                begin, end = -env.trigger/env.rate, (env.length-1-env.trigger)/env.rate
                self.overview.setXRange(begin, end, padding=0.02)
                self.overview.setYRange(float(lo.min())-0.02, float(hi.max())+0.02, padding=0.05)
                with QtCore.QSignalBlocker(self.roi_region):
                    self.roi_region.setBounds((begin, end))
                    self.roi_region.setRegion((float(t[0]), float(t[-1])))
            wire = len(env.buckets)*5 + math.ceil(len(env.buckets)/202)*40
            roi_wire = len(y)*2 + math.ceil(len(y)/508)*36
            full_wire = env.length*2 + math.ceil(env.length/508)*36
            self.envelope_info.setText(f"FPGA 实物包络 · {env.length:,} 点 → {len(env.buckets)} 桶 min/max"
                                       f" · 当前原始 ROI 细节\n"
                                       f"响应字节：概览 {wire:,} B + ROI {roi_wire:,} B；完整原始帧 {full_wire:,} B"
                                       f"（当前组合约 {full_wire/(wire+roi_wire):.1f}×，不含请求及状态包）")
            self.render_roi()
            return
        if "envelope" not in data:
            data["envelope"] = envelope(t, y)
        centers, lo, hi = data["envelope"]
        self.env_curve.setData(np.repeat(centers, 2), np.column_stack((lo, hi)).ravel(), connect="pairs")
        signature = (len(y), self.current.rate, self.current.trigger)
        if self._roi_signature != signature:
            self._roi_signature = signature
            self.overview.setXRange(float(t[0]), float(t[-1]), padding=0.02)
            self.overview.setYRange(float(y.min())-0.1, float(y.max())+0.1, padding=0.05)
            roi_count = min(1024, len(y))
            first = min(max(self.current.trigger-roi_count//2, 0), len(y)-roi_count)
            with QtCore.QSignalBlocker(self.roi_region):
                self.roi_region.setBounds((float(t[0]), float(t[-1])))
                self.roi_region.setRegion((float(t[first]), float(t[first+roi_count-1])))
        full, compressed = len(y)*2, len(centers)*4
        origin = "PC 从完整快照生成" if not self.is_demo() else "软件演示"
        self.envelope_info.setText(f"{origin} · {len(y):,} 原始点 → {len(centers)} 列 min/max · "
                                   f"纯样本负载 {full:,} B → {compressed:,} B（{full/compressed:.1f}×）\n"
                                   "当前视图在 PC 计算包络；启用“板端概览 + 按需原始 ROI”后重新采集，可读取 FPGA 包络。")
        self.render_roi()

    def schedule_roi(self, *_):
        if not self.roi_timer.isActive():
            self.roi_timer.start()

    def render_roi(self, *_):
        if self.current is None:
            return
        low, high = self.roi_region.getRegion()
        data = self.display_data()
        t = data["t"]
        if self.current.overview is not None and (low < t[0]-0.5/self.current.rate or high > t[-1]+0.5/self.current.rate):
            self.roi_curve.clear()
            self.roi_status.setText("选区未缓存；STOP 后释放选区可读取当前冻结帧（最多 2048 点）。")
            return
        start = max(0, int(np.searchsorted(t, low)))
        stop = min(len(t), int(np.searchsorted(t, high, side="right")))
        if stop <= start:
            return
        y = data["y"]
        self.roi_curve.setData(t[start:stop], y[start:stop])
        self.roi_plot.setXRange(float(t[start]), float(t[stop-1]) + 1/self.current.rate, padding=0)
        self.roi_plot.enableAutoRange(axis="y")
        if self.current.overview is not None:
            self.roi_status.setText(f"已缓存原始 ROI：帧索引 {self.current.record_offset+start}～"
                                    f"{self.current.record_offset+stop-1}；历史只含概览及已读取 ROI。")

    def receive_capabilities(self, flags):
        self.device_capabilities = flags
        if flags & proto.CAP_CAPTURE_MODES:
            if self.acquisition_mode.count() > 3:
                self.acquisition_mode.removeItem(3)
                self.acquisition_mode.setCurrentIndex(0)
            self.acquisition_mode.setEnabled(True)
            self.trigger_box.setEnabled(True)
        else:
            if self.acquisition_mode.count() == 3:
                self.acquisition_mode.addItem("旧固件 · PC 单次轮询")
            self.acquisition_mode.setCurrentIndex(3)
            self.acquisition_mode.setEnabled(False)
            self.log("当前固件仅支持 PC 连续请求单次；AUTO/NORMAL 需要三模式固件。")
        self.log("设备支持板端包络与原始 ROI。" if flags & 1 else
                 "当前固件不支持板端包络；多分辨率页将读取完整快照并在 PC 计算。")
        self.update_device_info()
        self.update_calibration_controls()

    def request_hardware_roi(self, *_):
        frame = self.current
        if frame is None or frame.overview is None:
            return
        if self.hardware_calibration_busy or self.running or self.capture_busy or self.roi_busy or self._commands_pending:
            self.roi_status.setText("请先 STOP，等待当前接收完成后再拖动 ROI 选区。")
            return
        env = frame.overview
        if not self.hardware_connected or self.worker is None or self.device_frame_identity != env.timestamp:
            self.roi_status.setText("该历史帧只保留已缓存 ROI；重新 SINGLE 可获取可浏览的新冻结帧。")
            return
        low, high = self.roi_region.getRegion()
        start = max(0, min(env.length-1, int(math.ceil(low*env.rate+env.trigger-1e-7))))
        stop = max(start+1, min(env.length, int(math.floor(high*env.rate+env.trigger+1e-7))+1))
        count = min(2048, stop-start)
        if stop-start > 2048:
            start = min(env.length-count, start+(stop-start-count)//2)
        with QtCore.QSignalBlocker(self.roi_region):
            self.roi_region.setRegion(((start-env.trigger)/env.rate, (start+count-1-env.trigger)/env.rate))
        self.worker.cancel_capture.clear()
        if self.worker.submit("roi", (frame, start, count)):
            self.roi_busy = True
            self.roi_status.setText(f"正在读取冻结帧 ROI：{start}～{start+count-1}…")

    def receive_roi(self, previous, frame):
        if self.running or self.current is not previous or not self.hardware_connected:
            return
        if self.device_frame_identity != frame.overview.timestamp:
            return
        self.current = frame
        self.history = [(n, frame if item is previous else item) for n, item in self.history]
        self._history_dirty = True
        self._roi_signature = None
        self.render_current()

    def roi_finished(self):
        self.roi_busy = False

    def export_envelope_csv(self):
        frame = self.current
        if frame is None or frame.overview is None:
            return
        env = frame.overview
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "保存板端概览", str(ROOT/"板端概览.csv"), "CSV (*.csv)")
        if not path:
            return
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", newline="", encoding="utf-8-sig", dir=Path(path).parent,
                                             prefix=".scope-envelope-", suffix=".tmp", delete=False) as file:
                temporary = Path(file.name)
                writer = csv.writer(file)
                writer.writerow(["# source", "FPGA envelope", "record_length", env.length, "sample_rate_hz", env.rate,
                                 "trigger_index", env.trigger, "first_sample_timestamp", env.timestamp])
                writer.writerow(["bucket", "first_index", "last_index", "minimum_signed_code", "maximum_signed_code",
                                 "otr_any", "minimum_nominal_v", "maximum_nominal_v"])
                for i, (lo, hi, otr) in enumerate(env.buckets):
                    writer.writerow([i, i*env.length//len(env.buckets), (i+1)*env.length//len(env.buckets)-1,
                                     lo, hi, otr, (lo+0.5)*SCALE, (hi+0.5)*SCALE])
            os.replace(temporary, path)
            temporary = None
            self.log("板端概览 CSV 已保存 · " + path)
        except (OSError, ValueError) as exc:
            self.log("错误：板端概览 CSV 保存失败 · " + str(exc))
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def select_history(self, row, _column):
        if 0 <= row < len(self.history):
            self.stop_capture()
            self.current = self.history[row][1]
            self.render_current()
            self.state_label.setText(f"STOP · 历史快照 #{self.history[row][0]}")

    def drag_trigger(self):
        self.threshold.setValue(float(np.clip(self.level_line.value(), -5, 5)))
        self.log("触发电平已编辑；STOP 后点击“应用触发配置”发送。")

    def toggle_cursors(self):
        bounds = self.wave_plot.viewRange()
        for index, cursor in enumerate(self.time_cursors):
            cursor.setVisible(self.cursor_time.isChecked())
            if self.cursor_time.isChecked():
                cursor.setValue(bounds[0][0] + (index+1)*(bounds[0][1]-bounds[0][0])/3)
        for index, cursor in enumerate(self.volt_cursors):
            cursor.setVisible(self.cursor_volt.isChecked())
            if self.cursor_volt.isChecked():
                cursor.setValue(bounds[1][0] + (index+1)*(bounds[1][1]-bounds[1][0])/3)
        self.update_cursors()

    def update_cursors(self, *_):
        values = []
        if self.cursor_time.isChecked():
            delta = abs(self.time_cursors[1].value()-self.time_cursors[0].value())
            values.append(f"Δt {eng(delta, 's')}     1/Δt {eng(1/delta if delta > 1e-15 else math.nan, 'Hz')}")
        if self.cursor_volt.isChecked():
            delta = abs(self.volt_cursors[1].value()-self.volt_cursors[0].value())
            values.append(f"ΔV {eng(delta, 'V')}")
        hint = "光标关闭 · T 为触发位置，虚线为触发电平"
        self.cursor_readout.setText("     |     ".join(values) if values else hint)

    def autoscale(self):
        if self.current is not None and (self.running or self.capture_busy or self.roi_busy):
            if getattr(self, '_autoscale_pending', False):
                return
            resume = self.running
            self._autoscale_pending = True
            self.stop_capture()
            self._finish_autoscale(resume, time.monotonic()+10)
            return
        if self.current is None or not self.can_configure():
            return
        self.auto_previous = (self.timebase.currentIndex(), self.volts_div.currentIndex(),
                              self.threshold.value(), self.hysteresis.value(), self.trigger_type.currentIndex(),
                              self.display_center.value())
        result = self.current_measurement()
        measured = measure(self.display_volts(), self.current.rate,
                           hysteresis=max(2*SCALE, result['vpp']*.02))
        frequency = result['frequency'] if math.isfinite(result['frequency']) else measured['frequency']
        horizontal = 3/(frequency*10) if math.isfinite(frequency) and frequency > 0 else len(self.current.words)/self.current.rate/10
        # Aim for six vertical divisions, with headroom for every recorded sample.
        candidates = [i for i,v in enumerate(VOLT_DIVS) if result['vpp']/v <= 7.6]
        self.volts_div.setCurrentIndex(min(candidates, key=lambda i:abs(result['vpp']/VOLT_DIVS[i]-6))
                                      if candidates else len(VOLT_DIVS)-1)
        self.timebase.setCurrentIndex(int(np.argmin(np.abs(np.log(np.array(TIME_DIVS)/horizontal)))))
        self.threshold.setValue((result["maximum"]+result["minimum"])/2)
        self.display_center.setValue((result["maximum"]+result["minimum"])/2)
        self.hysteresis.setValue(max(2*SCALE, min(2, result["vpp"]*0.03)))
        self.trigger_type.setCurrentIndex(0)
        self.apply_trigger()
        self.undo_button.setEnabled(True)
        self.log(f"Autoscale 已选择 · {self.timebase.currentText()} · {self.volts_div.currentText()} · "
                 f"触发 {self.threshold.value():.3f} V · 迟滞 {self.hysteresis.value():.3f} V；可撤销。")

    def _finish_autoscale(self, resume, deadline, applied=False):
        if self._closing or time.monotonic() > deadline:
            self._autoscale_pending = False
            return
        busy = self.capture_busy or self.roi_busy or self._commands_pending
        busy = busy or (self.worker is not None and self.worker.stop_requested.is_set())
        if busy:
            QtCore.QTimer.singleShot(40, lambda:self._finish_autoscale(resume, deadline, applied))
            return
        if not applied:
            self.autoscale()
            self._finish_autoscale(resume, deadline, True)
            return
        self._autoscale_pending = False
        if resume:
            self.set_running(True)

    def undo_autoscale(self):
        if self.auto_previous is None or not self.can_configure():
            return
        t, v, level, h, kind, center = self.auto_previous
        self.timebase.setCurrentIndex(t)
        self.volts_div.setCurrentIndex(v)
        self.threshold.setValue(level)
        self.hysteresis.setValue(h)
        self.trigger_type.setCurrentIndex(kind)
        self.display_center.setValue(center)
        self.apply_trigger()
        self.auto_previous = None
        self.undo_button.setEnabled(False)
        self.log("已恢复 Autoscale 前的显示及触发参数。")

    def start_calibration(self):
        if not self.is_demo():
            self.start_hardware_calibration()
            return
        self.stop_capture()
        self.cal_step = 0
        self.apply_cal.setChecked(False)
        self.calibration = None
        self.source.setEnabled(False)
        self.cal_button.setEnabled(False)
        self.cal_progress.setValue(0)
        self.show_calibration_comparison(None)
        self.response_curve.clear()
        self.cal_rng = np.random.default_rng(42)
        self.cal_points = np.linspace(-2.4, 2.4, 9)
        self.cal_samples = self.cal_points[:, None]*0.973 + 0.027 + self.cal_rng.normal(0, 0.003, (9, 4096))
        for row in range(7):
            self.cal_table.item(row, 1).setText("待运行")
            self.cal_table.item(row, 2).setText("—")
        self.cal_timer.start()
        self.update_calibration_controls()
        self.log("演示自检开始 · 软件模拟组合链路，无硬件输出命令。")

    def update_calibration_controls(self):
        active = self.hardware_calibration_busy or self._calibration_start_pending or self.cal_step >= 0
        supported = self.hardware_connected and bool(self.device_capabilities & 2)
        self.cal_button.setText('运行演示自检' if self.is_demo() else '运行实物闭环自检')
        self.cal_button.setEnabled(not active and (self.is_demo() or supported))
        self.cal_cancel_button.setEnabled(active)
        self.baseline_button.setEnabled(not active)
        self.load_baseline_button.setEnabled(not active)
        self.rebuild_baseline.setVisible(not self.is_demo())
        self.rebuild_baseline.setEnabled(not active)
        self.apply_cal.setText('显示应用演示校准' if self.is_demo() else '显示应用闭环相对校准')
        self.apply_cal.setEnabled(not active and ((self.is_demo() and self.calibration is not None)
                                  or (not self.is_demo() and self.hardware_calibration_valid and supported))
                                  and not self.apply_absolute.isChecked())
        if self.apply_absolute.isChecked():
            relative_hint = '已应用外部电压校正'
        elif not self.is_demo() and not self.hardware_calibration_valid:
            relative_hint = '自检通过后可启用相对校准'
        else:
            relative_hint = '相对校准可用'
        self.relative_calibration_hint.setText(relative_hint)
        self.apply_cal.setToolTip(relative_hint)
        self.absolute_button.setEnabled(not active)
        self.apply_absolute.setEnabled(not active and not self.is_demo() and self.hardware_connected
                                       and self.absolute_calibration is not None)
        self.run_button.setEnabled(not active)
        self.single_button.setEnabled(not active)
        for index in (0,1,2):
            self.tabs.setTabEnabled(index,not active)

    def load_absolute_profile(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, '载入电压校正参数', str(self.profile_path.parent), 'JSON (*.json)')
        if not path:
            return
        try:
            self.install_absolute_profile(Path(path))
        except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError) as exc:
            QtWidgets.QMessageBox.warning(self, '载入失败', '原参数保留：'+str(exc))

    def open_absolute_calibration(self):
        # Keep a modeless draft while the operator uses the main window to set
        # each DC input and acquire a fresh frame. Reopening retains prior points.
        if self.absolute_dialog is None:
            self.absolute_dialog = AbsoluteCalibrationDialog(self)
        self.absolute_dialog.show()
        self.absolute_dialog.raise_()
        self.absolute_dialog.activateWindow()

    def open_measurement_guide(self):
        if self.measurement_dialog is None:
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle('实物测量与验收说明')
            dialog.resize(940, 720)
            layout = QtWidgets.QVBoxLayout(dialog)
            self.measurement_state = self.label('')
            self.measurement_state.setWordWrap(True)
            layout.addWidget(self.measurement_state)
            self.measurement_browser = QtWidgets.QTextBrowser()
            self.measurement_browser.setOpenLinks(False)
            self.measurement_browser.setOpenExternalLinks(False)
            layout.addWidget(self.measurement_browser, 1)
            close = self.button('关闭', dialog.accept)
            layout.addWidget(close)
            self.measurement_dialog = dialog
        build = f'0x{self.device_build:08X}' if self.hardware_connected and self.device_build is not None else '未连接/未读取'
        self.measurement_state.setText(f'PC {PC_RELEASE} · 当前板端版本：{build}\n'
                                      +OVERLOAD_ACCEPTANCE+'\n'+self.absolute_status.text())
        path = ROOT/'PC/ui/实物测量说明.md'
        try:
            self.measurement_browser.setMarkdown(path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError) as exc:
            self.measurement_browser.setPlainText('无法读取完整清单：'+str(exc)+'\n请查看工作区docs/verification目录。')
        self.measurement_dialog.show()
        self.measurement_dialog.raise_()
        self.measurement_dialog.activateWindow()

    def install_absolute_profile(self, path):
        # Validate every raw evidence file and recompute before changing state.
        report = abscal.load_profile(path)
        self.apply_absolute.setChecked(False)
        self.absolute_calibration = report
        self.absolute_calibration_path = str(Path(path).resolve())
        self.absolute_calibration_sha256 = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        low, high = report['voltage_range']
        self.absolute_status.setText(f'已载入外部参考直流标定 · {low:.4f}～{high:.4f} V · '
                                    f'点检目标 {report["tolerance_volts"]*1000:.3f} mV')
        self.auto_apply_absolute_profile()
        self.update_calibration_controls()
        self.render_current()

    def absolute_toggled(self, checked):
        if checked:
            self.apply_cal.setChecked(False)
        self.update_calibration_controls()
        self.render_current()

    def voltage_calibration_metadata(self):
        correction = self.active_display_calibration()
        if self.apply_absolute.isChecked() and correction is not None:
            report = self.absolute_calibration
            return {"mode": 'external-reference-dc', "profile": self.absolute_calibration_path,
                        "profile_sha256": self.absolute_calibration_sha256,
                        "status": report['status'], "range_volts": report['voltage_range'],
                        "tolerance_volts": report['tolerance_volts'], "scope": report['scope'],
                        "slope_volts_per_raw": report['slope_volts_per_raw'], "intercept_volts": report['intercept_volts']}
        if correction is not None:
            return {"mode": 'relative', "absolute_calibrated": False}
        return {"mode": 'nominal', "absolute_calibrated": False}

    def start_hardware_calibration(self):
        if self.hardware_calibration_busy or self._calibration_start_pending:return
        if not self.hardware_connected or self.worker is None or not self.device_capabilities & 2:
            self.cal_result.setText('请先选择硬件串口并点击“连接设备”，握手成功后再运行实物自检。')
            self.log(self.cal_result.text());return
        self._calibration_start_pending=True
        self._calibration_wait_started=time.monotonic()
        self.running=self.single_pending=False
        self.worker.request_stop()
        self.state_label.setText('SELFTEST · 正在停止采集')
        self.cal_result.setText('正在停止采集并等待当前接收/配置完成，随后自动开始实物闭环自检…')
        self.update_calibration_controls()
        self._wait_calibration_idle()

    def _wait_calibration_idle(self):
        if not self._calibration_start_pending:return
        if self._closing or not self.hardware_connected or self.worker is None:
            self._calibration_start_pending=False
            self.cal_result.setText('自检启动已取消：设备连接已关闭。')
            self.update_calibration_controls();return
        ready=not (self.capture_busy or self.roi_busy or self._commands_pending or self.worker.stop_requested.is_set())
        if ready:
            self._calibration_start_pending=False
            self._begin_hardware_calibration();return
        if time.monotonic()-self._calibration_wait_started>15:
            self._calibration_start_pending=False
            self.cal_result.setText('自检未启动：等待采集停止超过15秒，请检查串口状态后重试。')
            self.update_calibration_controls();return
        QtCore.QTimer.singleShot(40,self._wait_calibration_idle)

    def _begin_hardware_calibration(self):
        self.running = self.single_pending = False
        self.apply_cal.setChecked(False)
        self.hardware_calibration_valid = False
        self.worker.cancel_capture.clear()
        self.hardware_calibration_busy = True
        self.tabs.setCurrentIndex(3)
        self.cal_step = 0
        self.cal_progress.setValue(0)
        self.show_calibration_comparison(None)
        self.response_curve.clear()
        for row in range(7):
            self.cal_table.item(row,1).setText('待运行 · 实物')
            self.cal_table.item(row,2).setText('—')
        self.side_panel.setEnabled(False)
        baseline = None if self.rebuild_baseline.isChecked() else self.hardware_baseline
        self._calibration_rebuild = baseline is None
        self.update_calibration_controls()
        if not self.worker.submit('calibration',baseline):
            self.hardware_calibration_busy = False
            self.cal_step = -1
            self.side_panel.setEnabled(True)
            self.update_calibration_controls()
            self.log('自检任务提交失败，请等待串口空闲后重试。')
            return
        self.state_label.setText('SELFTEST · 实物闭环自检')
        self.cal_result.setText('正在使用真实 DDS→ADC 链路；将保存原始记录，完成或取消后恢复原配置。')
        self.log('实物闭环自检开始：中码、九点直流、四档正弦、七点扫频；不改写 Flash。')

    def cancel_calibration(self):
        if self._calibration_start_pending:
            self._calibration_start_pending=False
            self.cal_result.setText('已取消自检启动；未进入自检输出流程。')
            self.update_calibration_controls()
        elif self.hardware_calibration_busy:
            self.worker.request_stop()
            self.cal_result.setText('已请求取消；等待当前传输结束并恢复原 DDS/触发配置…')
        elif self.cal_step >= 0:
            self.cal_timer.stop()
            self.cal_step = -1
            self.calibration = None
            self.show_calibration_comparison(None)
            self.response_curve.clear()
            self.source.setEnabled(True)
            self.update_calibration_controls()

    def receive_calibration_progress(self,step,text,status):
        if not self.hardware_calibration_busy:
            return
        self.cal_table.item(step,1).setText(status)
        self.cal_table.item(step,2).setText(text)
        self.cal_table.item(step,2).setToolTip(text)
        self.cal_progress.setValue(round((step+(status.startswith('完成')))*100/7))

    def receive_hardware_calibration(self,result):
        self.hardware_calibration_busy = False
        self.cal_step = -1
        self.side_panel.setEnabled(True)
        self.state_label.setText('STOP · 自检完成' if result['status']=='PASS' else 'STOP · 自检未完成')
        self.device_frame_identity = None
        if result['status']=='PASS' and result['restored']:
            self.hardware_calibration = hwcal.validate_fingerprint(result)
            self.hardware_calibration_valid = True
            try:
                if getattr(self,'_calibration_rebuild',False) or self.hardware_baseline is None:
                    if self.hardware_baseline is not None:
                        write_hardware_fingerprint(Path(result['output_dir'])/'previous_baseline.json',self.hardware_baseline)
                    write_hardware_fingerprint(self.hardware_baseline_path,result)
                    self.hardware_baseline = result.copy()
                write_hardware_fingerprint(self.profile_path.with_name('hardware_calibration_last.json'),result)
                self.log('实物校准参数已保存；下次自检将与保存的实测基线比较。')
            except (OSError,ValueError) as exc:
                self.log('实测参数有效，但默认参数文件保存失败：'+str(exc))
            self.rebuild_baseline.setChecked(False)
            self.response_curve.setData(result['response_frequency'],result['response_db'])
            self.response_plot.setTitle('组合幅频响应 · 实物测量，相对 100 kHz')
            self.show_calibration_comparison(result.get('before_after'),'实物独立复测')
            self.cal_progress.setValue(100)
            self.cal_result.setText('自检通过 · 原配置已恢复')
            self.cal_result.setToolTip('记录：'+result['output_dir'])
        else:
            self.show_calibration_comparison(None)
            detail = result.get('restore_error',result.get('error','未知错误'))
            self.cal_result.setText(f"自检{result['status']}：{detail}\n原配置{'已恢复' if result['restored'] else '未能确认恢复，请检查连接及输出'}；未生成可应用校准。")
            self.log(self.cal_result.text())
        self.update_calibration_controls()
        self.log('自检原始数据与报告：'+result['output_dir'])

    def save_hardware_fingerprint(self):
        if not self.hardware_calibration_valid or self.hardware_calibration is None or self.hardware_calibration_busy:
            self.log('请先成功完成一次实物自检并确认恢复原配置。')
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self,'保存实物健康指纹',str(ROOT/'实物健康指纹.json'),'JSON (*.json)')
        if not path:
            return
        temporary = None
        try:
            hwcal.validate_fingerprint(self.hardware_calibration)
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=Path(path).parent,
                                             prefix='.scope-hardware-',suffix='.tmp',delete=False) as file:
                temporary = Path(file.name)
                json.dump(self.hardware_calibration,file,ensure_ascii=False,indent=2,allow_nan=False)
            os.replace(temporary,path)
            temporary = None
            self.hardware_baseline = self.hardware_calibration.copy()
            write_hardware_fingerprint(self.hardware_baseline_path,self.hardware_baseline)
            self.log('实物健康指纹已保存 · '+path)
        except (OSError,ValueError) as exc:
            self.log('实物指纹保存失败：'+str(exc))
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def load_hardware_fingerprint(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self,'载入实物健康指纹',str(ROOT),'JSON (*.json)')
        if not path:
            return
        try:
            result = read_hardware_fingerprint(path)
            if self.worker is not None and self.hardware_connected and result['device_id']!=self.worker.device_identity:
                raise ValueError('指纹不属于当前设备')
            self.hardware_baseline = result
            self.cal_result.setText(self.compare_fingerprint())
            self.log('已载入真实硬件基线；下一次实物自检将比较并计算相对增益。')
        except (OSError,ValueError,KeyError,TypeError,RecursionError) as exc:
            self.log('实物指纹读取失败：'+str(exc))

    def calibration_tick(self):
        step = self.cal_step
        if step < 0:
            return
        if step == 0:
            text = f"中码 8192 · 零点 {self.cal_samples[4].mean()*1000:.3f} mV"
        elif step == 1:
            gain, offset = np.polyfit(self.cal_points, self.cal_samples.mean(axis=1), 1)
            self.calibration = {"gain": float(gain), "offset": float(offset),
                                "noise": float(np.std(self.cal_samples-self.cal_samples.mean(axis=1, keepdims=True)))}
            text = f"9 点拟合 · 增益 {gain:.6f} · 偏置 {offset*1000:.3f} mV · 极性正向"
        elif step == 2:
            monotonic = bool(np.all(np.diff(self.cal_samples.mean(axis=1)) > 0))
            text = f"单调性 {'通过' if monotonic else '失败'} · 当前模拟幅度未削顶 · OTR 未强制触发"
        elif step == 3:
            frequencies = np.array(hwcal.FREQUENCIES)
            db = -10*np.log10(1+(frequencies/4e6)**2)
            db -= db[3]
            self.response_curve.setData(frequencies, db)
            self.response_plot.setTitle('组合幅频响应 · 软件演示，相对 100 kHz')
            self.calibration["response_frequency"] = frequencies.tolist()
            self.calibration["response_db"] = db.tolist()
            text = "10 kHz ～ 1 MHz · 七点模拟组合幅频响应，相对 100 kHz"
        elif step == 4:
            noise = self.calibration['noise']
            text = f"零输入噪声 {noise*1000:.3f} mV RMS · 谐波请查看1024点FFT摘要"
        elif step == 5:
            self.apply_cal.setEnabled(True)
            # Independent simulated observations, excluded from the nine fit points.
            zero = float((0.027+self.cal_rng.normal(0,0.003,4096)).mean())
            expected = 512/819*2.4
            holdout = float((expected*0.973+0.027+self.cal_rng.normal(0,0.003,4096)).mean())
            self.calibration['before_after'] = hwcal.relative_comparison(
                self.calibration['offset'],self.calibration['gain'],zero,holdout,expected)
            self.show_calibration_comparison(self.calibration['before_after'],'软件演示独立复测')
            text = "相对校准参数就绪 · 原始 ADC 码保持不变 · 可勾选应用到显示"
        else:
            text = self.compare_fingerprint()
        self.cal_table.item(step, 1).setText("完成 · 演示")
        self.cal_table.item(step, 1).setForeground(QtGui.QColor(CYAN))
        self.cal_table.item(step, 2).setText(text)
        self.cal_table.item(step, 2).setToolTip(text)
        self.cal_progress.setValue(round((step+1)*100/7))
        self.cal_step += 1
        if self.cal_step == 7:
            self.cal_step = -1
            self.cal_timer.stop()
            self.cal_button.setEnabled(True)
            self.source.setEnabled(True)
            self.update_calibration_controls()
            self.cal_result.setText("演示完成 · 以上为模拟组合链路相对结果，不能当作实物验收。")
            self.log("演示闭环自检完成，可保存健康指纹并比较相对偏移。")

    def show_calibration_comparison(self,comparison,source=''):
        for row,key in enumerate(('zero','dc_holdout')):
            values = comparison[key] if comparison else None
            for col,field in enumerate(('expected_volts','before_error_volts','after_error_volts'),1):
                self.cal_comparison.item(row,col).setText(f"{values[field]*1000:+.4f}" if values else '—')
        self.cal_comparison_note.setText(
            f'校准前后对比 · {source} · 同一原始帧，仅改变显示换算；目标为组合链路相对基线'
            if comparison else '校准前后对比 · 等待当前数据源独立复测')

    def compare_fingerprint(self):
        if not self.is_demo():
            if self.hardware_calibration is None:
                return '请先完成实物闭环自检。'
            return hwcal.fingerprint_delta(self.hardware_calibration,self.hardware_baseline)
        if not self.calibration:
            return "请先完成演示自检。"
        if not self.baseline:
            return "尚无基线 · 保存健康指纹后可比较偏移"
        delta_offset = (self.calibration["offset"]-self.baseline["offset"])*1000
        delta_gain = (self.calibration["gain"]/self.baseline["gain"]-1)*100
        delta_noise = (self.calibration["noise"]-self.baseline["noise"])*1000
        return f"相对指纹 · 零点 Δ{delta_offset:+.3f} mV · 增益 Δ{delta_gain:+.4f}% · 噪声 Δ{delta_noise:+.3f} mV RMS"

    def save_fingerprint(self):
        if not self.is_demo():
            self.save_hardware_fingerprint()
            return
        if not self.calibration or self.cal_step >= 0:
            self.log("请先完成一次演示自检，再保存健康指纹。")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "保存演示健康指纹", str(ROOT/"演示健康指纹.json"), "JSON (*.json)")
        if path:
            try:
                data = {"format": "scope-ui-fingerprint-v1", "source": "software-demo",
                        "created": datetime.now().isoformat(), "calibration": self.calibration}
                Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                self.baseline = self.calibration.copy()
                self.log("健康指纹已保存 · " + path)
            except OSError as exc:
                self.log(f"错误：保存失败 · {exc}")

    def load_fingerprint(self):
        if not self.is_demo():
            self.load_hardware_fingerprint()
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "载入演示健康指纹", str(ROOT), "JSON (*.json)")
        if not path:
            return
        try:
            values = read_fingerprint(path)
            self.baseline = values
            self.cal_result.setText(self.compare_fingerprint())
            self.log("健康指纹已载入 · " + self.compare_fingerprint())
        except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError) as exc:
            self.log(f"错误：指纹读取失败 · {exc}")

    def report_measurement(self):
        frame=self.current
        if frame is None:return None
        return {"firmware_build": frame.firmware_build,"source": frame.source,
            "timestamp": (frame.timestamp-frame.record_offset)%(1<<64),"record_offset": frame.record_offset,
            "record_length": frame.record_length or (frame.overview.length if frame.overview else len(frame.words)),"read_samples": len(frame.words),
            "rate": frame.rate,"trigger_index": frame.trigger+frame.record_offset,
            "pc": measure(frame.volts(),frame.rate),"fpga": frame.fpga_measurement,
            "spectrum": frame.fpga_spectrum,"saturation": frame.fpga_saturation,
            "voltage_calibration": self.voltage_calibration_metadata(),
            "display_pc": self.current_measurement()}

    def export_summary(self):
        if not self.can_configure() or self._commands_pending:return
        if self.is_demo():
            self.log('汇总报告需要真实设备连接；演示数据不生成实物时序/资源/误码结论。');return
        measurement=self.report_measurement()
        path,_=QtWidgets.QFileDialog.getSaveFileName(self,'导出测量/时序/资源/误码汇总',str(ROOT/'示波器汇总报告.csv'),'CSV (*.csv)')
        if not path:return
        if self.worker.submit('summary',{"path": path,"measurement": measurement}):
            self._commands_pending+=1
            self.log('正在查询设备状态并生成汇总报告…')

    def export_csv(self):
        if self.csv_worker is not None:
            self.log("已有 CSV 正在保存，请稍候。")
            return
        if self.current is None:
            self.log("尚无快照可保存。")
            return
        # 在弹出模态文件框之前锁定快照及显示参数；文件框内 Qt 仍可能接收新帧。
        frame = self.current
        calibration = self.active_display_calibration()
        calibration_metadata = self.voltage_calibration_metadata()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "保存原始快照", str(ROOT/"示波器快照.csv"), "CSV (*.csv)")
        if not path:
            return
        if self.csv_worker is not None or self._closing:
            return
        self.csv_worker = CsvExportWorker(path, frame, calibration, calibration_metadata)
        self.csv_worker.completed.connect(lambda path: self.log("CSV 已保存 · " + path))
        self.csv_worker.failed.connect(self.log)
        self.csv_worker.finished.connect(self.csv_finished)
        self.csv_button.setEnabled(False)
        self.csv_worker.start()
        self.log("正在后台保存 CSV…")

    def csv_finished(self):
        self.csv_worker.deleteLater()
        self.csv_worker = None
        self.csv_button.setEnabled(True)

    def export_png(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "保存当前界面", str(ROOT/"示波器界面.png"), "PNG (*.png)")
        if path:
            if self.grab().save(path, "PNG"):
                self.log("PNG 已保存 · " + path)
            else:
                self.log("错误：PNG 保存失败，请检查文件路径")

    def closeEvent(self, event):
        self._closing = True
        self.running = self.single_pending = False
        self.timer.stop()
        self.cal_timer.stop()
        self.roi_timer.stop()
        pending = False
        if self.worker is not None and self.worker.isRunning():
            self.worker.shutdown.set()
            self.worker.cancel_capture.set()
            pending = True
        if self.csv_worker is not None and self.csv_worker.isRunning():
            self.csv_worker.requestInterruption()
            pending = True
        if pending:
            # 不在 GUI 线程 wait；保持事件循环可响应，线程释放资源后再销毁窗口。
            self.state_label.setText("正在关闭…")
            event.ignore()
            QtCore.QTimer.singleShot(50, self.close)
            return
        event.accept()


def main():
    parser = argparse.ArgumentParser(description="EGO1 单通道示波器显示界面")
    parser.add_argument("--screenshot", type=Path, help="保存演示界面截图后退出（可用于无硬件验证）")
    parser.add_argument("--hardware", action="store_true", help="启动到硬件串口采集模式")
    parser.add_argument("--multires", action="store_true", help="启动到多分辨率采集页")
    parser.add_argument("--calibration", action="store_true", help="启动到实物闭环自检页（连接后手动开始）")
    parser.add_argument("--offline", action="store_true", help="使用软件演示数据，可与 --calibration 配合离线自检")
    parser.add_argument("--port", help="预选串口，例如 COM12")
    parser.add_argument("--baud", type=int, choices=(115200,921600), help="预选波特率，115200仅供旧固件兼容")
    args = parser.parse_args()
    pg.setConfigOptions(antialias=True, foreground="#aabbd2", background="#0c1421")
    app = QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName("示波器显示界面")
    configure_fonts(app)
    window = ScopeWindow()
    if args.hardware and not args.offline:
        window.source.setCurrentIndex(1)
    if args.multires:
        window.tabs.setCurrentIndex(2)
    if args.calibration:
        if not args.hardware and not args.offline:
            window.source.setCurrentIndex(1)
        window.tabs.setCurrentIndex(3)
    if args.baud:
        window.baud.setCurrentText(str(args.baud))
    if args.port:
        index = window.port.findData(args.port)
        if index >= 0:
            window.port.setCurrentIndex(index)
        else:
            window.port.setCurrentIndex(-1)
            window.log(f"未检测到指定串口 {args.port}，请刷新后重新选择。")
    window.show()
    if args.screenshot:
        def save():
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            success = window.grab().save(str(args.screenshot), "PNG")
            print(f"screenshot: {args.screenshot} ({'OK' if success else 'FAILED'})")
            window.close()
            app.exit(0 if success else 1)
        QtCore.QTimer.singleShot(1000, save)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
