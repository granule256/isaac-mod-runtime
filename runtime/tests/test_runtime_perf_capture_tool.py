import struct
import unittest
from pathlib import Path
import base64
from unittest import mock

from tools import runtime_perf_capture as perf


def snapshot(tick, count, overflow=0, generation=1):
    header = dict.fromkeys(perf.HEADER_FIELDS, 0)
    header.update(magic=perf.MAGIC, version=1, headerBytes=224, bucketBytes=48,
                  callbackCapacity=1, apiCapacity=1, tick=tick, tickFrequency=1000,
                  generation=generation, callbackCalls=count,
                  callbackOverflow=overflow, flags=11)
    body = struct.pack('<28Q', *(header[k] for k in perf.HEADER_FIELDS))
    body += struct.pack('<4Q4I', (1 << 48) | (2 << 32) | 13,
                        count - overflow, 100 * count, 100, 0, 0, 0, 0)
    body += bytes(48)
    return perf.decode_snapshot(body)


class RuntimePerfCaptureToolTests(unittest.TestCase):
    def test_frame_trace_keeps_gc_as_overlay_and_exposes_unknown_time(self):
        rows = struct.pack('<14Q', 20, 2, 12, 1, 1, 4, 3, 10, 2, 1, 1, 1, 5, 0)
        report = perf.summarize_frame_trace(rows, 1000)
        self.assertEqual(report['over_budget']['frames'], 1)
        self.assertEqual(report['over_budget']['mean_phase_ms']['lua_managed'], 12)
        self.assertEqual(report['over_budget']['mean_budgeted_gc_ms'], 3)
        self.assertEqual(report['max_ms'], 20)
        with self.assertRaisesRegex(ValueError, 'phase totals'):
            perf.summarize_frame_trace(struct.pack('<7Q', 1, 2, 3, 4, 5, 6, 0), 1000)

    def test_coverage_is_explicit_and_owner_is_not_a_directory_index(self):
        report = perf.summarize(snapshot(1000, 10), snapshot(2000, 110, 25), {2: 'StageAPI'})
        self.assertEqual(report['callback_calls_per_second'], 100)
        self.assertEqual(report['callback_coverage'], .75)
        self.assertEqual(report['callback_overflow'], 25)
        self.assertEqual(report['callbacks'][0]['owner_name'], 'StageAPI')
        self.assertEqual(report['callbacks'][0]['event'], 13)
        self.assertIn('inclusive', report['timing_semantics'])
        self.assertIn('disabled', report['api_timing_scope'])

    def test_epoch_change_and_bad_layout_are_rejected(self):
        with self.assertRaises(ValueError):
            perf.summarize(snapshot(1000, 10), snapshot(2000, 20, generation=2), {})
        with self.assertRaises(ValueError):
            perf.decode_snapshot(bytes(224))
        with self.assertRaises(ValueError):
            perf.decode_snapshot(struct.pack('<28Q', perf.MAGIC, 999, *([0] * 26)))

    def test_counter_reset_is_rejected(self):
        with self.assertRaises(ValueError):
            perf.summarize(snapshot(1000, 100), snapshot(2000, 10), {})

    def test_summary_does_not_claim_callback_attribution_coverage(self):
        a, b = snapshot(1000, 10), snapshot(2000, 110)
        a['header']['flags'] = b['header']['flags'] = 3
        report = perf.summarize(a, b, {})
        self.assertFalse(report['callback_attribution_enabled'])
        self.assertIsNone(report['callback_coverage'])

    def test_process_change_aborts_before_memory_write(self):
        reader = perf.PerfReader.__new__(perf.PerfReader)
        reader.pid = 245
        reader.current_pid = lambda: 246
        with self.assertRaisesRegex(RuntimeError, 'before memory writes'):
            reader.capture()

    def test_callback_labels_come_from_runtime_catalog(self):
        labels = perf.load_callback_names(Path(__file__).resolve().parents[2])
        self.assertEqual(labels[13], 'MC_INPUT_ACTION')
        self.assertEqual(labels[1], 'MC_POST_UPDATE')

    def test_attribution_uses_target_clock_deadline_and_stops_its_own_window(self):
        reader = perf.PerfReader.__new__(perf.PerfReader)
        reader.pid = 5
        reader.attribution_until = 123
        reader.current_pid = lambda: 5
        reader.capture = lambda: (b'', snapshot(1000, 10))
        writes = []
        reader.q = lambda address: writes[-1] if writes else 0
        reader.write_attribution_until = writes.append
        reader.arm_attribution(8)
        self.assertEqual(writes, [24000])
        reader.stop_attribution()
        self.assertEqual(writes, [24000, 0])

    def test_stale_layout_is_rejected_before_any_write(self):
        sdk, main, gateway = 0x300000, 0x100000, 0x200000
        syms = {'isaac_internal_hook_context': (0x100, 32), 'exl_main': (0x200, 64),
                'IsaacModRuntime_CreateProceduralItemWithCpuPixels': (0x300, 64),
                'g_RuntimePerfLayout': (0x400, 128),
                'g_RuntimePerfCaptureRequest': (0x500, 8),
                'g_RuntimePerfCaptureDone': (0x508, 8),
                'g_RuntimePerfAttributionUntil': (0x510, 8),
                'g_RuntimePerfSnapshot': (0x1000, 49376), 'g_ModOwnerNames': (0x20000, 16512)}
        # All code fingerprints match, but the live descriptor moved Request.
        descriptor = struct.pack('<16Q', 0x3154594c465052, 1, 128, 49376, 224, 48,
                                 512, 512, 258, 64, sdk + 0x400, sdk + 0x518,
                                 sdk + 0x508, sdk + 0x510, sdk + 0x1000, sdk + 0x20000)

        class Transport:
            writes = []

            def call(self, method, **params):
                if method == 'title.current':
                    return [dict(running='application', pid='1', program_id='0x010021C000B6A000')]
                if method == 'mem.info':
                    return [dict(main_base=hex(main))]
                if method == 'mem.write':
                    self.writes.append(params)
                    raise RuntimeError('unsafe write reached')
                address, size = int(params['addr'], 16), params['size']
                raw = {main + 0x86ff0: bytes.fromhex('5000005800021fd6') + struct.pack('<Q', gateway),
                       gateway + 24: struct.pack('<Q', sdk + 0x100),
                       sdk + 0x200: b'x' * 64, sdk + 0x300: b'x' * 64,
                       sdk + 0x400: descriptor}.get(address, bytes(size))
                return [base64.b64encode(raw).decode()]

        transport = Transport()
        with mock.patch.object(Path, 'read_bytes', return_value=b'elf'), \
                mock.patch.object(perf, 'load_symbols', return_value=syms), \
                mock.patch.object(perf, 'read_vaddr', return_value=b'x' * 64):
            with self.assertRaises(RuntimeError):
                perf.PerfReader(transport, Path('runtime.elf')).capture()
        self.assertEqual(transport.writes, [])


if __name__ == '__main__':
    unittest.main()
