"""Manual external-reference DC calibration. Opening this dialog sends no commands."""
from datetime import datetime
from pathlib import Path
import os

from PySide6 import QtWidgets
import absolute_calibration as ac


class AbsoluteCalibrationDialog(QtWidgets.QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.points = []
        self.folder = None
        self.setWindowTitle('外部参考直流电压标定')
        self.resize(940, 670)
        layout = QtWidgets.QVBoxLayout(self)
        note = QtWidgets.QLabel(
            '可载入已有标定参数，或使用独立电压参考重新标定。本窗口不设置硬件输出。\n'
            '保持原 ADC 量程，在 ADC 输入端保持连接和负载不变，测量稳定直流的实际电压。\n'
            '先添加至少3个拟合点（负、近零、正），再添加至少2个不同电压的独立验证点（负、正）。\n'
            '每点先完成新的完整 SINGLE 并 STOP，再录入同时测得的参考读数。禁止使用 DAC 理论电压。\n'
            '校正仅影响显示与导出，触发设置仍使用标称电压；直流标定不授予交流或全量程精度。')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QtWidgets.QFormLayout()
        self.instrument = QtWidgets.QLineEdit()
        self.instrument.setPlaceholderText('型号、编号；误差界限依据/校准信息')
        self.conditions = QtWidgets.QLineEdit()
        self.conditions.setPlaceholderText('接线、负载、供电、预热、温度；条件改变后重新标定')
        self.role = QtWidgets.QComboBox()
        self.role.addItems(['拟合点', '独立验证点'])
        self.reference = QtWidgets.QDoubleSpinBox()
        self.reference.setRange(-4.9, 4.9)
        self.reference.setDecimals(6)
        self.reference.setSuffix(' V')
        self.reference_error = QtWidgets.QDoubleSpinBox()
        self.reference_error.setRange(0, 100)
        self.reference_error.setDecimals(4)
        self.reference_error.setSuffix(' mV')
        self.reference_error.setToolTip('根据参考仪器在该档位和读数下的规格填写最大误差界限；未知或零时不能标定。')
        self.tolerance = QtWidgets.QDoubleSpinBox()
        self.tolerance.setRange(.001, 100)
        self.tolerance.setDecimals(3)
        self.tolerance.setValue(10)
        self.tolerance.setSuffix(' mV')
        self.tolerance.setToolTip('本次直流点检的目标误差限，不是设备已有精度；包含拟合残差和参考误差裕量。')
        form.addRow('参考仪器与依据', self.instrument)
        form.addRow('标定条件', self.conditions)
        form.addRow('当前点用途', self.role)
        form.addRow('独立实测读数', self.reference)
        form.addRow('参考最大误差界限', self.reference_error)
        form.addRow('直流点检目标误差限', self.tolerance)
        layout.addLayout(form)
        self.measured = QtWidgets.QCheckBox('此读数来自独立仪器，测量位置为保持负载连接的 ADC 输入端')
        layout.addWidget(self.measured)
        row = QtWidgets.QHBoxLayout()
        self.add_button = QtWidgets.QPushButton('添加当前完整帧')
        self.add_button.clicked.connect(self.add_point)
        remove = QtWidgets.QPushButton('移除选中点')
        remove.clicked.connect(self.remove_point)
        row.addWidget(self.add_button)
        row.addWidget(remove)
        row.addStretch()
        layout.addLayout(row)
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['用途', '参考 / V', 'ADC 均码', '噪声 / 码', '帧时间戳'])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, 1)
        self.status = QtWidgets.QLabel('可载入已有标定参数，或添加本轮参考测量点')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QtWidgets.QHBoxLayout()
        build = QtWidgets.QPushButton('验证、保存并载入')
        build.clicked.connect(self.publish)
        load = QtWidgets.QPushButton('载入已有标定证据…')
        load.clicked.connect(self.load)
        close = QtWidgets.QPushButton('关闭')
        close.clicked.connect(self.accept)
        for button in (build, load, close):
            row.addWidget(button)
        layout.addLayout(row)

    def add_point(self):
        owner = self.owner
        try:
            ac.require(not owner.is_demo() and owner.hardware_connected and owner.worker is not None
                       and owner.can_configure() and not owner._commands_pending,
                       '请连接硬件，采集新的完整直流帧后 STOP 并等待接收结束')
            frame = owner.current
            ac.require(frame is not None and frame.timestamp == owner.device_frame_identity,
                       '当前记录不属于设备的最新冻结帧')
            ac.require(not any(point['timestamp'] == frame.timestamp for point in self.points),
                       '该帧已添加；每个拟合/验证点需要重新采集')
            ac.require(len(self.points) < 32, '每轮最多32点')
            metadata = {'reference_volts': self.reference.value(),
                            'reference_error_volts': self.reference_error.value()/1000,
                            'role': 'fit' if self.role.currentIndex() == 0 else 'check',
                            'device_id': owner.worker.device_identity, 'instrument': self.instrument.text(),
                            'conditions': self.conditions.text(), 'externally_measured': self.measured.isChecked()}
            # Validate before creating even a draft session directory.
            ac.point_from_frame(frame, **metadata)
            if self.folder is None:
                self.folder = owner.profile_path.parent/'absolute_calibration_runs'/(
                    datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+os.urandom(4).hex())
            self.points.append(ac.save_point(self.folder, frame, **metadata))
            self.refresh()
            self.measured.setChecked(False)
            self.status.setText(f'已保存{len(self.points)}点原始证据；尚未通过独立验证，未应用校正。')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.status.setText('未添加：'+str(exc))

    def refresh(self):
        self.table.setRowCount(len(self.points))
        for row, point in enumerate(self.points):
            values = ('拟合' if point['role'] == 'fit' else '独立验证', f"{point['reference_volts']:.6f}",
                      f"{point['mean_raw']:.4f}", f"{point['std_raw']:.4f}", str(point['timestamp']))
            for col, value in enumerate(values):
                self.table.setItem(row, col, QtWidgets.QTableWidgetItem(value))

    def remove_point(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.points):
            self.points.pop(row)
            self.refresh()
            self.status.setText('已从草稿移除；已保存的原始证据保留。重新验证后才能发布。')

    def publish(self):
        try:
            ac.require(self.folder is not None, '没有外部参考测量，不能生成绝对标定参数')
            report = ac.fit(self.points, self.folder, self.tolerance.value()/1000)
            path = self.folder/'calibration.json'
            ac.save_profile(path, report)
            self.owner.install_absolute_profile(path)
            errors = [v for v in report['verification'] if v['role'] == 'check']
            before = max(abs(v['before_error_volts']) for v in errors)*1000
            after = max(abs(v['after_error_volts']) for v in errors)*1000
            self.status.setText(f'直流点检通过并保存；验证点最大误差 {before:.3f} → {after:.3f} mV。\n'
                                f'适用范围及条件见标定记录；主窗口勾选后才应用。\n{path}')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.status.setText('未发布：'+str(exc))

    def load(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, '载入外部参考标定及原始证据',
                                                      str(self.owner.profile_path.parent), 'JSON (*.json)')
        if not path:
            return
        try:
            self.owner.install_absolute_profile(Path(path))
            self.status.setText('已重新核验原始证据并载入；仅在设备、固件与样本范围匹配时可应用。')
        except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError) as exc:
            self.status.setText('载入失败，原参数保留：'+str(exc))
