"""Strict UART acceptance, independent of Qt. Offline evidence is never hardware evidence."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import time

import scope_protocol as p

BAUDS = (115200, 230400, 460800, 921600)
ERROR_NAMES = ('crc', 'length', 'version', 'timeout', 'unknown', 'command', 'framing', 'overflow')
AUTO_TRIGGER = struct.pack('<BBhHhhIIHI', 6, 0, 0, 0, -2048, 2047, 1, 1, 16383, 2)
MASK64 = (1 << 64) - 1


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def save_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


class RealClock:
    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)


class VirtualClock:
    """Model time only; the report also records real elapsed wall time."""
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class Client:
    def __init__(self, link, baud, clock=None):
        self.link, self.baud, self.clock = link, baud, clock or RealClock()
        self.parser = p.Parser()
        self.sequence = 0
        self.requests = self.tx_bytes = self.rx_bytes = 0
        self.completed_requests = self.capture_attempts = 0
        self.transport_errors = {'sequence': 0, 'response_timeout': 0, 'capture_timeout': 0, 'echo_mismatch': 0}
        self.last_rx = bytearray()
        self.last_tx = b''
        self.baseline = None
        self.status_deltas = {}
        self.last_timestamp = None
        self.last_words = []
        self.captures = self.otr_samples = 0
        self.capabilities = 0

    def exchange(self, kind, payload=b'', stream=False):
        previous_errors = self.parser.errors.copy()
        seq = self.sequence
        self.sequence = (seq + 1) & 65535
        wire = p.encode(p.Frame(kind, sequence=seq, payload=payload))
        self.last_tx = wire
        require(self.link.write(wire) == len(wire), 'short serial write')
        self.requests += 1
        self.tx_bytes += len(wire)
        expected_seq = seq
        result = []
        raw_bytes = valid_bytes = 0
        deadline = self.clock.monotonic() + (8 + 16384 * 24 / self.baud if stream else 4)
        idle = self.clock.monotonic()
        while self.clock.monotonic() < deadline:
            data = self.link.read(max(1, min(self.link.in_waiting, 8192)))
            if not data:
                if self.clock.monotonic() - idle > 2:
                    self.parser.expire()
                    self.transport_errors['response_timeout'] += 1
                    raise TimeoutError('response missing/truncated; no retries or baud fallback')
                continue
            idle = self.clock.monotonic()
            self.rx_bytes += len(data)
            raw_bytes += len(data)
            self.last_rx.extend(data)
            del self.last_rx[:-65536]
            frames = self.parser.feed(data)
            require(self.parser.errors == previous_errors, 'PC parser CRC/length/version/timeout error')
            for index, frame in enumerate(frames):
                require(frame.kind == (kind | 0x80), 'unexpected response type')
                if frame.sequence != expected_seq:
                    self.transport_errors['sequence'] += 1
                    raise ValueError('response sequence gap/duplicate/reorder')
                require(not frame.flags & p.ERROR, 'device rejected request')
                valid_bytes += len(p.encode(frame))
                result.append(frame)
                expected_seq = (expected_seq + 1) & 65535
                if stream:
                    last = bool(frame.flags & p.LAST)
                    flags = p.RESPONSE | (p.FIRST if len(result) == 1 else 0) | (p.LAST if last else p.MORE)
                    require(frame.flags == flags, 'stream FIRST/MORE/LAST flags invalid')
                else:
                    require(frame.flags == p.RESPONSE, 'ordinary response flags invalid')
                    last = True
                if last:
                    require(index == len(frames)-1 and not self.parser.buffer and raw_bytes == valid_bytes
                            and not self.link.in_waiting, 'extra/garbage bytes or duplicate response')
                    if stream:
                        self.sequence = expected_seq
                        self.completed_requests += 1
                        return result
                    if kind == p.PING and frame.payload != payload:
                        self.transport_errors['echo_mismatch'] += 1
                        raise ValueError('echo payload mismatch')
                    if kind in (p.STOP, p.SINGLE, p.SET_TRIGGER):
                        require(frame.payload == b'\0', 'invalid command acknowledgement')
                    self.completed_requests += 1
                    return frame
        self.transport_errors['response_timeout'] += 1
        raise TimeoutError('response deadline exceeded')

    def handshake(self, expected_build):
        self.exchange(p.PING, b'UART_ACCEPTANCE_V1')
        frame = self.exchange(p.GET_VERSION)
        require(len(frame.payload) == 8 and frame.payload[:4] == b'\1\0\0\0', 'invalid version')
        build, = struct.unpack_from('<I', frame.payload, 4)
        require(build == expected_build, 'firmware build does not match expected build')
        caps = self.exchange(p.GET_CAPABILITIES).payload
        require(len(caps) == 8, 'invalid capability response')
        self.capabilities, buckets, roi = struct.unpack('<IHH', caps)
        require(self.capabilities&3==3 and not self.capabilities&~63 and (buckets, roi) == (800, 2048),
                'configuration readback and multires firmware required')
        return build

    def configuration(self):
        config = self.exchange(p.GET_CONFIG).payload
        require(len(config) == 48, 'configuration must be 48 bytes')
        length, pre = struct.unpack_from('<II', config)
        require(length == 16384 and pre < length, 'invalid record configuration')
        return config

    def status(self):
        frame = self.exchange(p.GET_STATUS)
        raw = frame.payload
        require(len(raw) == 48, 'invalid status length')
        length, pre = struct.unpack_from('<II', raw, 4)
        require(raw[0] & ~7 == 0 and raw[1:4] == b'\0\1\0' and length == 16384
                and pre < length and frame.sample_rate == 25000000, 'backend/status/sample rate error')
        counters = struct.unpack_from('<9I', raw, 12)
        if self.baseline is None:
            self.baseline = (counters, self.requests)
        before, requests = self.baseline
        self.status_deltas = {name: (value-old) & 0xffffffff
                              for name, value, old in zip(ERROR_NAMES, counters[:8], before[:8])}
        require(not any(self.status_deltas.values()), 'FPGA error counter increased: ' + str(self.status_deltas))
        accepted = (counters[8] - before[8]) & 0xffffffff
        require(accepted == (self.requests-requests) & 0xffffffff,
                'FPGA accepted-request count mismatch/reset')
        return raw[0], pre, counters

    def wave(self, start, count):
        frames = self.exchange(p.READ_WAVE, struct.pack('<II', start, count), stream=True)
        assembler = p.WaveAssembler()
        words = None
        for index, frame in enumerate(frames):
            require(10 <= len(frame.payload) <= 1024 and len(frame.payload) % 2 == 0, 'wave payload length')
            offset, total = struct.unpack_from('<II', frame.payload)
            require(total == 16384 and offset == start + len(assembler.words), 'wave offset/total gap')
            require(index == 0 or not frame.flags & p.FIRST, 'repeated FIRST')
            words = assembler.accept(frame)
        require(words is not None and len(words) == count and assembler.next_offset == start+count,
                'incomplete wave, early LAST or missing samples')
        require(assembler.rate == 25000000 and 0 <= assembler.trigger < 16384, 'wave metadata range')
        require(all(word & 0x7000 == 0 for word in words), 'reserved sample bits')
        identity = (assembler.base, assembler.rate, assembler.trigger)
        return words, identity

    def capture(self, full=False):
        self.capture_attempts += 1
        self.exchange(p.SINGLE)
        deadline = self.clock.monotonic() + 8
        while True:
            flags, pre, _ = self.status()
            if flags & 2 and not flags & 1:
                break
            if self.clock.monotonic() > deadline:
                self.transport_errors['capture_timeout'] += 1
                raise TimeoutError('capture timeout')
            self.clock.sleep(.01)
        env_frames = self.exchange(p.READ_ENVELOPE, struct.pack('<H', 800), stream=True)
        env = p.EnvelopeAssembler(env_frames[0].sequence, 800, 16384)
        entries = None
        for frame in env_frames:
            entries = env.accept(frame)
        require(entries is not None, 'incomplete envelope')
        count = 16384 if full else 2048
        start = 0 if full else max(0, min(pre-1024, 16384-2048))
        words, identity = self.wave(start, count)
        self.last_words = words
        require(identity == env.identity, 'envelope/ROI frozen-frame mismatch')
        if self.last_timestamp is not None:
            delta = (identity[0]-self.last_timestamp) & MASK64
            require(0 < delta < 1 << 63, 'stale/duplicate timestamp or board reset')
        self.last_timestamp = identity[0]
        for i, (lo, hi, otr) in enumerate(entries):
            a, b = i*16384//800, (i+1)*16384//800
            if a >= start and b <= start+count:
                bucket = words[a-start:b-start]
                samples = [2047-(word & 4095) for word in bucket]
                require((min(samples), max(samples), int(any(word & 32768 for word in bucket))) == (lo, hi, otr),
                        'envelope disagrees with raw samples')
        otr = sum(bool(word & 32768) for word in words)
        self.otr_samples += otr
        require(not otr and not any(entry[2] for entry in entries), 'ADC OTR observed')
        values = [2047-(word & 4095) for word in words]
        require(max(values)-min(values) >= 4, 'no usable loopback signal; check modules/SW0/DDS')
        if self.capabilities & p.CAP_FROZEN_ANALYSIS:
            measured = self.exchange(p.READ_MEASURE)
            spectral = self.exchange(p.READ_SPECTRUM)
            require(all((f.timestamp, f.sample_rate, f.trigger_index) == identity for f in (measured, spectral)),
                    'measurement/spectrum frozen-frame mismatch')
            m = p.decode_measurement(measured)
            p.decode_spectrum(spectral)
            require(not m['error'], 'measurement analysis error')
            if full:
                require((m['minimum'], m['maximum'], m['sum'], m['square_sum']) ==
                        (min(values), max(values), sum(values), sum(x*x for x in values)), 'full-record statistics mismatch')
        self.captures += 1
        return {'timestamp': identity[0], 'samples': count, 'minimum': min(values), 'maximum': max(values)}


class OfflineSerial:
    """Deterministic byte endpoint. It cannot open a port or qualify a hardware rate."""
    def __init__(self, baud, clock):
        self.baud, self.clock = baud, clock
        self.buffer = bytearray()
        self.closed = False
        self.good = 0
        self.timestamp = 1000000
        self.trigger = struct.pack('<BBhHhhIIHI', 0, 0, 0, 8, -100, 100, 1, 100, 100, 2)
        self.dds = struct.pack('<BBIIHi', 0, 1, 100000, 0, 819, 0)
        self.words = [2047-round(40*math.sin(i*2*math.pi/250)) for i in range(16384)]
        self.available = False
        self.fault = None

    @property
    def in_waiting(self):
        return len(self.buffer)

    def close(self):
        self.closed = True

    def read(self, count):
        if not self.buffer:
            self.clock.sleep(.02)
            return b''
        count = min(count, 137)  # exercise arbitrary USB fragmentation
        data = bytes(self.buffer[:count])
        del self.buffer[:count]
        self.clock.sleep(len(data)*10/self.baud)
        return data

    def write(self, wire):
        require(not self.closed, 'offline port closed')
        self.clock.sleep(len(wire)*10/self.baud)
        request, = p.Parser().feed(wire)
        self.good = (self.good+1) & 0xffffffff
        kind, payload = request.kind, b'\0'
        responses = []
        if kind == p.PING:
            payload = request.payload
        elif kind == p.GET_VERSION:
            payload = struct.pack('<II', 1, 0xA0261025)
        elif kind == p.GET_CAPABILITIES:
            payload = struct.pack('<IHH', 3, 800, 2048)
        elif kind == p.GET_CONFIG:
            payload = struct.pack('<II', 16384, 8192)+self.trigger+self.dds
        elif kind == p.SET_TRIGGER:
            self.trigger = request.payload
        elif kind == p.SINGLE:
            self.timestamp += 250000
            self.available = True
        elif kind == p.GET_STATUS:
            counters = [0]*8+[self.good]
            if self.fault == 'overflow':
                counters[7] = 1
            payload = bytes([4 | (2 if self.available else 0), 0, 1, 0])+struct.pack('<II9I', 16384, 8192, *counters)
        elif kind == p.READ_WAVE:
            start, count = struct.unpack('<II', request.payload)
            for i, offset in enumerate(range(start, start+count, 508)):
                words = self.words[offset:min(offset+508, start+count)]
                last = offset+len(words) == start+count
                data = struct.pack('<II', offset, 16384)+struct.pack('<'+'H'*len(words), *words)
                responses.append(p.Frame(0xb0, (request.sequence+i) & 65535,
                                         self.timestamp+offset, 25000000, 8192,
                                         p.RESPONSE | (p.FIRST if i == 0 else 0) | (p.LAST if last else p.MORE), data))
        elif kind == p.READ_ENVELOPE:
            buckets = []
            for i in range(800):
                values = [2047-(w & 4095) for w in self.words[i*16384//800:(i+1)*16384//800]]
                buckets.append((min(values), max(values), 0))
            for i, offset in enumerate(range(0, 800, 202)):
                data = struct.pack('<IIHH', offset, 16384, 800, 1)
                data += b''.join(p.ENVELOPE_BUCKET.pack(*bucket) for bucket in buckets[offset:offset+202])
                responses.append(p.Frame(0xb2, (request.sequence+i) & 65535, self.timestamp, 25000000, 8192,
                                         p.RESPONSE | (p.FIRST if i == 0 else 0) | (p.LAST if offset+202 >= 800 else p.MORE), data))
        if not responses:
            responses = [p.Frame(kind | 0x80, request.sequence, self.timestamp, 25000000, 8192, p.RESPONSE, payload)]
        if self.fault == 'gap' and len(responses) > 1:
            responses.pop(1)
        output = bytearray(b''.join(p.encode(frame) for frame in responses))
        if self.fault == 'crc':
            output[-1] ^= 1
        elif self.fault == 'drop':
            output.clear()
        elif self.fault == 'echo' and kind == p.PING:
            f = responses[0]
            output = bytearray(p.encode(p.Frame(f.kind, f.sequence, f.timestamp, f.sample_rate,
                                               f.trigger_index, f.flags, b'wrong')))
        elif self.fault == 'duplicate':
            output += bytes(output)
        elif self.fault == 'noise':
            output = b'noise'+output
        self.buffer.extend(output)
        return len(wire)


def qualifies(report):
    """Fail closed: no short/offline/interrupted/restoration-failed report can advertise a rate."""
    return (report.get('source') == 'hardware-uart' and report.get('verdict') == 'PASS'
            and report.get('restored') is True and report.get('recovery') == 'PASS'
            and report.get('soak_seconds', 0) >= 7200 and report.get('echo_seconds', 0) >= 600
            and report.get('echo_payload_bytes', 0) >= 1048576 and report.get('captures', 0) >= 2
            and report.get('firmware_sha256') is not None and bool(report.get('device_id'))
            and not any(report.get('pc_errors', {'missing': 1}).values())
            and not any(report.get('fpga_error_deltas', {'missing': 1}).values())
            and not any(report.get('transport_errors', {'missing': 1}).values())
            and report.get('unanswered_requests') == 0 and report.get('incomplete_captures') == 0)


def run_acceptance(output, baud, *, offline=True, port=None, device_id='', conditions='', firmware=None,
                   expected_build=0xA0261026, duration=7200, uart_duration=600, min_bytes=1048576,
                   seed=20261026, progress=print, link_factory=None, clock=None):
    require(baud in BAUDS, 'unsupported baud')
    require(all(math.isfinite(v) and v > 0 for v in (duration, uart_duration)) and min_bytes > 0,
            'durations and byte quota must be positive')
    if not offline:
        require(port and device_id and conditions and firmware and Path(firmware).is_file(),
                'hardware mode requires port, device ID, conditions and firmware artifact')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    clock = clock or (VirtualClock() if offline else RealClock())
    if link_factory is None:
        if offline:
            model = OfflineSerial(baud, clock)

            def link_factory():
                model.closed = False
                return model
        else:
            import serial
            link_factory = lambda: serial.Serial(port, baud, timeout=.02, write_timeout=3)
    wall_start = time.monotonic()
    report = {'format': 'scope-uart-acceptance-v1', 'source': 'offline-model' if offline else 'hardware-uart',
              'verdict': 'RUNNING', 'started_at': now(), 'baud': baud, 'port': port, 'device_id': device_id,
              'conditions': conditions, 'seed': seed, 'requested_soak_seconds': duration,
              'requested_echo_seconds': uart_duration, 'requested_echo_payload_bytes': min_bytes,
              'restored': False, 'recovery': 'NOT_RUN', 'echo_payload_bytes': 0, 'echo_seconds': 0,
              'soak_seconds': 0, 'captures': 0, 'qualified_bauds': [],
              'firmware_sha256': hashlib.sha256(Path(firmware).read_bytes()).hexdigest() if firmware else None,
              'firmware_artifact': str(Path(firmware).resolve()) if firmware else None,
              'time_basis': 'virtual model seconds' if offline else 'monotonic wall seconds',
              'source_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (Path(__file__), Path(p.__file__))},
              'limitations': ['No temperature sensor: conditions are operator observations.',
                              'Request/response snapshots, not a continuous ADC stream; no unrequested frames counted as lost.',
                              'Offline model does not implement FPGA FFT analysis.'] if offline else
                             ['No temperature sensor: conditions are operator observations.',
                              'Request/response snapshots, not a continuous ADC stream; no unrequested frames counted as lost.']}
    client = None
    original = None

    def checkpoint(event, **details):
        if client is not None:
            report.update(captures=client.captures, tx_bytes=client.tx_bytes, rx_bytes=client.rx_bytes,
                          protocol_responses=client.parser.good_frames, requests=client.requests,
                          completed_requests=client.completed_requests,
                          unanswered_requests=client.requests-client.completed_requests,
                          capture_attempts=client.capture_attempts,
                          incomplete_captures=client.capture_attempts-client.captures,
                          transport_errors=client.transport_errors.copy(),
                          pc_errors=client.parser.errors.copy(), fpga_error_deltas=client.status_deltas.copy(),
                          otr_samples=client.otr_samples)
        report['wall_elapsed_seconds'] = time.monotonic()-wall_start
        save_json(output/'report.json', report)
        with (output/'events.jsonl').open('a', encoding='utf-8') as log:
            log.write(json.dumps({'at': now(), 'event': event, 'captures': report['captures'],
                                  'echo_bytes': report['echo_payload_bytes'], 'soak_seconds': report['soak_seconds'],
                                  **details}, ensure_ascii=False)+'\n')
        progress(f"{event}: baud={baud}, captures={report['captures']}, echo={report['echo_payload_bytes']} B, soak={report['soak_seconds']:.1f} s")

    checkpoint('start')
    try:
        client = Client(link_factory(), baud, clock)
        report['build'] = hex(client.handshake(0xA0261025 if offline else expected_build))
        report['capabilities'] = client.capabilities
        client.exchange(p.STOP)
        original = client.configuration()
        report['original_configuration_hex'] = original.hex()
        require(original[33] == 1, 'DDS disabled; prepare established physical loopback first')
        _, _, baseline = client.status()
        report['fpga_baseline_counters'] = list(baseline)
        client.exchange(p.SET_TRIGGER, AUTO_TRIGGER)
        generator = random.Random(seed)
        start = clock.monotonic()
        next_checkpoint = start+30
        index = 0
        while clock.monotonic()-start < uart_duration or report['echo_payload_bytes'] < min_bytes:
            size = (64, 508, 1024, 1024)[index % 4]
            payload = generator.randbytes(size)
            client.exchange(p.PING, payload)
            report['echo_payload_bytes'] += size
            report['echo_seconds'] = clock.monotonic()-start
            index += 1
            if clock.monotonic() >= next_checkpoint:
                client.status()
                checkpoint('uart-progress')
                next_checkpoint = clock.monotonic()+30
        client.status()
        checkpoint('uart-complete')
        start = clock.monotonic()
        next_checkpoint = start+30
        while clock.monotonic()-start < duration:
            frame = client.capture(full=client.captures % 10 == 0)
            if client.captures == 1:
                (output/'first_full_wave.bin').write_bytes(struct.pack('<'+'H'*len(client.last_words), *client.last_words))
                report['first_full_frame'] = frame
            if offline:
                clock.sleep(10)  # explicitly model cadence; never sleep for hours in an offline check
            report['soak_seconds'] = clock.monotonic()-start
            if clock.monotonic() >= next_checkpoint:
                checkpoint('soak-progress', last_frame=frame)
                next_checkpoint = clock.monotonic()+30
        # Recovery is outside the uninterrupted soak period. No counter/parser resets.
        report['soak_captures'] = client.captures
        report['soak_protocol_responses'] = client.parser.good_frames
        client.exchange(p.STOP)
        client.capture(full=True)
        client.link.close()
        client.link = link_factory()
        client.handshake(0xA0261025 if offline else expected_build)
        client.status()
        client.capture(full=True)
        client.status()
        report['recovery'] = 'PASS'
        report['verdict'] = ('OFFLINE_PASS' if offline else
                             'PASS' if duration >= 7200 and uart_duration >= 600 and min_bytes >= 1048576
                             else 'SHORT_PASS')
    except KeyboardInterrupt:
        report.update(verdict='INTERRUPTED', error='User interrupted; no acceptance credit')
    except Exception as error:
        report.update(verdict='FAIL', error=repr(error))
    finally:
        if client is not None:
            if original is not None:
                try:
                    client.exchange(p.STOP)
                    client.exchange(p.SET_TRIGGER, original[8:32])
                    require(client.configuration() == original, 'configuration restoration readback mismatch')
                    client.status()
                    report['restored'] = True
                except Exception as error:
                    report.update(verdict='FAIL', restore_error=repr(error))
            try:
                client.link.close()
            except Exception as error:
                report.update(verdict='FAIL', close_error=repr(error))
            (output/'last_rx.bin').write_bytes(client.last_rx)
            (output/'last_tx.bin').write_bytes(client.last_tx)
            if client.last_words:
                (output/'last_wave.bin').write_bytes(struct.pack('<'+'H'*len(client.last_words), *client.last_words))
        checkpoint('finished')
        report['finished_at'] = now()
        if qualifies(report):
            report['qualified_bauds'] = [baud]
        save_json(output/'report.json', report)
        save_json(output/'stable_rates.json', {'source_report': str((output/'report.json').resolve()),
                  'qualified_bauds': report['qualified_bauds'], 'device_id': device_id,
                  'firmware_sha256': report['firmware_sha256'], 'build': report.get('build'),
                  'conditions': conditions, 'scope': 'Only this device, firmware artifact and recorded setup.'})
    return report
