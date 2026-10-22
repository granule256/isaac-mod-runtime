"""离线量具行为回归：缺失、重叠字节、耗时口径与帧计数差分。"""
import contextlib
import importlib.util
import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_elf_syms import build_minimal_elf


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReadoutIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tool = load('read_device_state_via_gdb')

    def test_player_chain_executes_memory_reads_instead_of_echoing_them(self):
        tool = self.tool
        game_base, slot, game, begin, player = 0x10000000, 0x20000000, 0x30000000, 0x40000000, 0x50000000
        memory = {game_base + tool.PLAYER_CHAIN_GAME_SLOT: slot, slot: game,
                  game + tool.PLAYER_CHAIN_PLAYERS_BEGIN: begin, begin: player}

        class Session:
            def command(self, command):
                lines = command.splitlines()
                if len(lines) != 2:
                    # GDB echo只打印剩余正文；正文里的x命令不会被执行。
                    return command[5:].replace('\\n', '\n')
                tag = lines[0][9:].removesuffix('\\n')
                address = int(lines[1].split()[-1], 16)
                return f'TAG {tag}\n0x{address:x}:\t0x{memory.get(address, 0):016x}\n'

        address, route = tool.resolve_player_entity_address(Session(), game_base)
        self.assertEqual(address, player)
        self.assertIn('两级', route)

    def report(self, values):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.tool.report(values, 0, 0, 0)
        return out.getvalue()

    def test_real_mangled_names_resolve_live_and_peak(self):
        # 按 Itanium ABI 的真实标识符字符数拼 ELF，不复制量具配置里的名字。
        symbols = {'_ZN5isaac7runtime17g_FontStorageLiveE': (0x848a254, 4),
                   '_ZN5isaac7runtime21g_FontStorageLivePeakE': (0x848a250, 4)}
        with tempfile.TemporaryDirectory() as td:
            elf = Path(td) / 'runtime.elf'
            elf.write_bytes(build_minimal_elf(symbols))
            with contextlib.redirect_stdout(io.StringIO()):
                missing = self.tool.sync_syms_from_elf(elf)
        self.assertNotIn('g_FontStorageLive', missing)
        self.assertNotIn('g_FontStorageLivePeak', missing)
        self.assertEqual(self.tool.SYMS['g_FontStorageLive'], 0x848a254)

    def test_missing_font_count_is_not_zero_or_gc_success(self):
        out = self.report({'g_ModMenuMilestones': [0], 'g_FontStorageAllocations': [1090],
                           'g_FontStorageFailures': [577]})
        self.assertIn('当前活着 = 缺失', out)
        self.assertIn('峰值 = 缺失', out)
        self.assertNotIn('GC 看得见', out)
        self.assertNotIn('应当个位数', out)

    def test_real_zero_font_count_remains_zero(self):
        out = self.report({'g_ModMenuMilestones': [0], 'g_FontStorageLive': [0],
                           'g_FontStorageLivePeak': [431 << 32 | 12]})
        self.assertIn('当前活着 = 0', out)
        self.assertIn('峰值 = 12', out)

    def test_overlap_recovery_uses_verified_address_not_label_guess(self):
        # 417 原始一行：failures 的高32位覆盖相邻 peak，完全没有覆盖 live。
        base = 0x76aa381000
        self.tool.SYMS.update(g_FontStorageFailures=0x848a24c,
                              g_FontStorageLivePeak=0x848a250, g_FontStorageLive=0x848a254)
        raw = 'TAG g_FontStorageFailures\n0x76b280b24c:\t0x000001af00000241\n'
        values = self.tool.parse_words(raw)
        sources = self.tool.recover_font_storage_from_raw(raw, base, values)
        self.assertEqual(values['g_FontStorageLivePeak'], [431])
        self.assertNotIn('g_FontStorageLive', values)
        self.assertIn('0x76b280b250', sources['g_FontStorageLivePeak'])
        values = self.tool.parse_words(raw)
        self.tool.SYMS['g_FontStorageFailures'] += 4
        self.assertEqual(self.tool.recover_font_storage_from_raw(raw, base, values), {})

    def test_missing_syscall_time_does_not_report_zero_cost(self):
        out = self.report({'g_RuntimePerfCallbackCalls': [1], 'g_RuntimePerfCallbackTicks': [19200],
                           'g_RuntimePerfCallbackMaxTicks': [19200], 'g_RuntimePerfSyscalls': [10]})
        self.assertIn('引擎内存查询（svcQueryMemory）：缺失', out)
        self.assertNotIn('平均 0.0 µs', out)

    def test_u64_counter_does_not_consume_adjacent_words(self):
        out = self.report({'g_RuntimePerfCallbackCalls': [1, 999],
                           'g_RuntimePerfCallbackTicks': [19200],
                           'g_RuntimePerfCallbackMaxTicks': [19200],
                           'g_RuntimePerfSyscalls': [1], 'g_RuntimePerfSyscallTicks': [192]})
        self.assertIn('托管回调 1 次', out)

    def test_syscall_units_and_scope_do_not_double_count_callbacks(self):
        out = self.report({'g_RuntimePerfCallbackCalls': [1], 'g_RuntimePerfCallbackTicks': [192000],
                           'g_RuntimePerfCallbackMaxTicks': [192000],
                           'g_RuntimePerfSyscalls': [7711105],
                           'g_RuntimePerfSyscallTicks': [54844473]})
        self.assertIn('合计 2856.5 ms、平均 0.370 µs', out)
        self.assertNotIn('其中"读引擎内存"占回调总耗时', out)
        self.assertIn('不能与回调耗时相加', out)

    def test_all_api_total_is_inclusive_not_unique_interface_cost(self):
        record = struct.pack('<QQQQIIII', 7, 1, 19200, 19200, 0, 1, 0, 0)
        out = self.report({'g_RuntimePerfCallbackCalls': [0],
                           'perf_api_buckets': [int.from_bytes(record[i:i+8], 'little')
                                                for i in range(0, len(record), 8)],
                           'g_RuntimePerfApiTotalCalls': [2], 'g_RuntimePerfApiTotalTicks': [38400]})
        self.assertIn('含引擎段及嵌套计时', out)
        self.assertNotIn('与回调耗时直接对账', out)

    def test_truncated_profile_skips_incomplete_record(self):
        full = struct.pack('<Ii24s48s', 2, 12, b'f', b'@mod.lua')
        raw = full + struct.pack('<Ii', 3, 20)
        values = {'perf_profile_buckets': [int.from_bytes(raw[i:i+8], 'little')
                                           for i in range(0, len(raw), 8)]}
        with contextlib.redirect_stdout(io.StringIO()):
            rows = self.tool.profile_records(values)
        self.assertEqual(rows, [(2, 12, 'f', '@mod.lua')])

    def test_absent_bucket_is_not_proof_callback_never_ran(self):
        raw = struct.pack('<QQQQIIII', 2, 1, 19200, 19200, 0, 1, 0, 0)
        out = self.report({'g_RuntimePerfCallbackCalls': [1],
                           'perf_buckets': [int.from_bytes(raw[i:i+8], 'little')
                                            for i in range(0, len(raw), 8)]})
        self.assertNotIn('缺席/0 次 = 这一家的这个事件确实没被派发过', out)

    def test_dynamic_persistence_reads_descriptor_then_pointer_not_inline_payload(self):
        self.tool.MOD_DATA_CACHE_BYTES = 40
        self.tool.SYMS['g_ModDataCache'] = 0x100
        requests, _ = self.tool.build_requests(0x1000, 0x2000, 0)
        self.assertIn(('mod_data_descriptor', 0x1100, 5), requests)
        self.assertFalse(any(tag in ('mod_data_tail', 'mod_data_head') for tag, _, _ in requests))
        commands = '\n'.join(self.tool.mod_data_payload_commands(0x1000))
        self.assertIn('0x1100', commands)
        self.assertIn('0x1110', commands)
        self.assertIn('8192', commands)
        self.assertIn('bx', commands)

    def test_dynamic_persistence_report_decodes_records_without_api_sequence(self):
        record = struct.pack('<QQII', 1, 2, 3, 3) + b'abc'
        raw = 'TAG mod_data_head_bytes\n0x9000: ' + ' '.join(f'0x{b:02x}' for b in record) + '\n'
        values = self.tool.parse_words(raw)
        values['mod_data_descriptor'] = [0x9000, len(record), len(record), 5, 0x101]
        out = self.report(values)
        self.assertIn('generation=5、payload=27 字节', out)
        self.assertIn('模组数据记录 1 条', out)
        self.assertIn('abc', out)
        self.assertNotIn('重启后再读一次 generation 应当继续增大', out)


class FrameCounterTests(unittest.TestCase):
    def setUp(self):
        self.tool = load('perf_frame_rate')

    def test_u32_rollover_keeps_small_forward_delta(self):
        self.assertEqual(self.tool.frame_interval(0, 0xfffffff0, 1, 0x20), (1, 48, 48.0))

    def test_counter_reset_is_not_negative_or_huge_fps(self):
        self.assertIsNone(self.tool.frame_interval(0, 300, 1, 10))

    def test_missing_sample_and_invalid_time_have_no_rate(self):
        self.assertIsNone(self.tool.frame_interval(0, None, 1, 10))
        self.assertIsNone(self.tool.frame_interval(1, 10, 0, 20))

    def test_short_game_pointer_read_does_not_use_slot_as_game(self):
        class Device:
            base_confirmed = True
            base = 0x1000
            def __init__(self, elf): pass
            def sym(self, name): return 0x10
            def read(self, address, size):
                return {0x1010: struct.pack('<Q', 0x2000),
                        0x2000 + self_slot: struct.pack('<Q', 0x3000)}.get(address, b'')
        self_slot = self.tool.GAME_SLOT
        with patch.dict(sys.modules, {'nxc_mem': type('NxcMem', (), {'Device': Device})}), \
             patch.object(sys, 'argv', ['perf_frame_rate.py', '--elf', 'fake.elf', '--seconds', '0.001', '--samples', '1']), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = self.tool.main()
        self.assertEqual(result, 4)


if __name__ == '__main__':
    unittest.main()
