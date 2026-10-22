"""守卫常量必须与真实游戏镜像逐字节一致。

`hook_manager.cpp` 的每个 `Verify*` 都用 `memcmp` 精确比较 16 字节守卫：**抄错一个字节就等于
静默关掉一个绑定**，没有日志也没有报错。2026-09-13 就是这样发现 `kGameIsGreedModeExpectedBytes`
第 10 字节写成 `0xB8`（真值 `0x68`）的——`Game:IsGreedMode` 在真机上从未可用。
`tools/verify_runtime_constants_against_nro.py` 是同一套判据，两个入口共用 `check()`。

★ 2026-09-29（批次 210）**又抓到同一类事故的另一个入口**，两处都补进判据：

* `kKageIsButtonPressedDiscriminator` 那条 4 字节判别式被写成了**反汇编里指令字的字面顺序**
  （`F9 40 19 08`）而不是**内存字节序**（`08 19 40 F9`）⇒ 真机上守卫永远不比中 ⇒
  `Input.IsButtonTriggered` / `IsButtonPressed` 整条哑掉（恒答 false），MCM"按右摇杆开菜单"
  永远没反应。校验器**当时没比它，因为数组后缀表里没有 `Discriminator`**（工具的两个洞见
  `tools/verify_runtime_constants_against_nro.py` 的模块注释）。现在后缀表含
  `ExpectedBytes / ExpectedEntry / ExpectedOriginal / Discriminator`，判别式比在
  "入口偏移 + 判别式偏移"上。
* 偏移侧基名有两种剥法都试 ⇒ `kImageManagerLoadFileOffset`、`kSaveDataDeleteFileOffset`
  这两条**从来没比过**的守卫也进了比对（`checked` 141 → 147）。
"""

import unittest
from pathlib import Path
from unittest import mock

from tools.verify_runtime_constants_against_nro import DISCRIMINATOR_OFFSETS, check


ROOT = Path(__file__).resolve().parents[2]
CONSTANTS = ROOT / "runtime/source/runtime_constants.hpp"
NRO = (
    ROOT
    / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    / "Program #0/1/.nro/Repentance.nro"
)


class GuardCheckerTests(unittest.TestCase):
    """Judge the judge: the checker must fail on a wrong byte and accept a patch target."""

    CONSTANTS_TEXT = """
inline constexpr uintptr_t kFakeEntryOffset = 0x10;
inline constexpr std::array<u8, 4> kFakeEntryExpectedBytes = {
    0x11, 0x22, 0x33, 0x44,
};
inline constexpr uintptr_t kFakePatchedOffset = 0x40;
inline constexpr std::array<u8, 4> kFakePatchedExpectedBytes = {
    0xAA, 0xBB, 0xCC, 0xDD,
};
inline constexpr uintptr_t kFakeOrphanCodeOffset = 0x60;
inline constexpr std::array<u8, 4> kFakeOrphanExpectedBytes = {
    0x55, 0x66, 0x77, 0x88,
};
inline constexpr uintptr_t kFakeEntry2Offset = 0x20;
inline constexpr uintptr_t kFakeEntry2DiscriminatorOffset = 0x8;
inline constexpr std::array<u8, 4> kFakeEntry2Discriminator = {
    0xDE, 0xAD, 0xBE, 0xEF,
};
"""

    def image(self) -> bytes:
        data = bytearray(0x80)
        data[0x10:0x14] = bytes.fromhex("11223344")
        data[0x40:0x44] = bytes.fromhex("AABBCCDD")
        data[0x60:0x64] = bytes.fromhex("55667788")
        data[0x28:0x2C] = bytes.fromhex("DEADBEEF")
        return bytes(data)

    def test_matching_guard_passes_and_patch_target_is_classified_not_failed(self):
        report = check(self.CONSTANTS_TEXT, self.image(), patched={0x40})
        self.assertEqual(report["failures"], [])
        self.assertEqual(report["checked"], 2)
        self.assertEqual(report["matched"], 1)
        self.assertEqual(report["patched_image"], 1)
        # `kFakeOrphanExpectedBytes` locates its bytes at `...CodeOffset`, which the exact-base
        # pairing deliberately does not guess; it is reported instead of force-paired.
        # `kFakeEntry2Discriminator` 还没登记判别式偏移（见 `DISCRIMINATOR_OFFSETS`）⇒ 同样进
        # `unpaired_arrays`，**绝不静默跳过**（静默跳过正是 2026-09-29 那次事故的成因）。
        self.assertEqual(report["unpaired_arrays"],
                         ["kFakeEntry2Discriminator", "kFakeOrphanExpectedBytes"])

    def test_discriminator_is_compared_at_entry_plus_the_discriminator_offset(self):
        """判别式比在"入口偏移 + 判别式偏移"上（不是入口自己那几个字节）。"""
        registry = dict(DISCRIMINATOR_OFFSETS)
        registry["kFakeEntry2Discriminator"] = "kFakeEntry2DiscriminatorOffset"
        with mock.patch.dict("tools.verify_runtime_constants_against_nro.DISCRIMINATOR_OFFSETS",
                             registry, clear=True):
            report = check(self.CONSTANTS_TEXT, self.image(), patched=set())
        self.assertEqual(report["failures"], [])
        self.assertEqual(report["checked"], 3)
        self.assertEqual(report["matched"], 3)          # 0x10 / 0x20+0x8 / 0x60 三处都对上
        # 登记之后判别式不再落进 `unpaired_arrays`（剩下的那个孤儿是故意不配的）
        self.assertEqual(report["unpaired_arrays"], ["kFakeOrphanExpectedBytes"])

    def test_byte_reversed_discriminator_is_reported(self):
        """★ 2026-09-29 那个真 bug 的形状：**字节序写反**（指令字的字面顺序 vs 内存字节序）。

        `kKageIsButtonPressedDiscriminator` 曾写成 `{0xF9,0x40,0x19,0x08}`（真值 `08 19 40 F9`）
        ⇒ 真机上守卫永远不比中 ⇒ `Input.IsButtonTriggered` 整条哑掉。这里用同一形状钉住判据：
        把 4 字节整体倒过来 ⇒ 必须判红，并且报出两个值。
        """
        registry = dict(DISCRIMINATOR_OFFSETS)
        registry["kFakeEntry2Discriminator"] = "kFakeEntry2DiscriminatorOffset"
        text = self.CONSTANTS_TEXT.replace(
            "0xDE, 0xAD, 0xBE, 0xEF", "0xEF, 0xBE, 0xAD, 0xDE")
        with mock.patch.dict("tools.verify_runtime_constants_against_nro.DISCRIMINATOR_OFFSETS",
                             registry, clear=True):
            report = check(text, self.image(), patched=set())
        self.assertEqual(len(report["failures"]), 1)
        failure = report["failures"][0]
        self.assertEqual(failure["array"], "kFakeEntry2Discriminator")
        self.assertEqual(failure["status"], "mismatch")
        self.assertEqual(failure["expected_hex"], "EFBEADDE")
        self.assertEqual(failure["actual_hex"], "DEADBEEF")
        self.assertEqual(failure["offset"], 0x20 + 0x8)

    def test_guard_whose_base_ends_with_file_still_pairs(self):
        """基名自己以 `File` 结尾的偏移（`kXxxFileOffset`）也要配得上 —— 两种剥法都试。

        2026-09-29 实测：`kImageManagerLoadFileOffset` / `kSaveDataDeleteFileOffset` 这两条
        守卫因为只按最长后缀剥一次而**从来没跟镜像比过**。
        """
        text = """
inline constexpr uintptr_t kFakeLoadFileOffset = 0x30;
inline constexpr std::array<u8, 4> kFakeLoadFileExpectedBytes = {
    0x01, 0x02, 0x03, 0x04,
};
"""
        data = bytearray(0x80)
        data[0x30:0x34] = bytes.fromhex("01020304")
        report = check(text, bytes(data), patched=set())
        self.assertEqual(report["failures"], [])
        self.assertEqual(report["checked"], 1)
        self.assertEqual(report["unpaired_arrays"], [])

    def test_single_wrong_byte_is_reported_with_both_values(self):
        text = self.CONSTANTS_TEXT.replace("0x33", "0xB8")
        report = check(text, self.image(), patched=set())
        self.assertEqual(len(report["failures"]), 1)
        failure = report["failures"][0]
        self.assertEqual(failure["offset_name"], "kFakeEntryOffset")
        self.assertEqual(failure["status"], "mismatch")
        self.assertEqual(failure["actual_hex"], "11223344")
        self.assertEqual(failure["expected_hex"], "1122B844")

    def test_declared_size_must_match_the_listed_bytes(self):
        text = self.CONSTANTS_TEXT.replace(
            "std::array<u8, 4> kFakeEntryExpectedBytes", "std::array<u8, 6> kFakeEntryExpectedBytes"
        )
        report = check(text, self.image(), patched=set())
        self.assertEqual([entry["status"] for entry in report["failures"]], ["declared-size-mismatch"])

    def test_out_of_range_offset_is_a_failure(self):
        text = self.CONSTANTS_TEXT.replace("kFakeEntryOffset = 0x10", "kFakeEntryOffset = 0x1000")
        report = check(text, self.image(), patched=set())
        self.assertEqual([entry["status"] for entry in report["failures"]], ["out-of-range"])


@unittest.skipUnless(NRO.exists(), "user-provided Switch dump is not present")
class RuntimeConstantsAgainstNroTests(unittest.TestCase):
    def test_every_pairable_guard_matches_the_pristine_game_image(self):
        report = check(CONSTANTS.read_text(encoding="utf-8"), NRO.read_bytes())
        self.assertEqual(
            report["failures"], [],
            "守卫与镜像不符：" + ", ".join(
                f"{entry['offset_name']} 常量={entry['expected_hex']} 镜像={entry.get('actual_hex')}"
                for entry in report["failures"]
            ),
        )
        # A vacuous pass (nothing paired) must not be possible.
        self.assertGreaterEqual(report["matched"], 30)
        # ★ 2026-09-29（批次 210）：**"没比过"必须看得见**。
        # `unpaired_arrays` 里只允许出现"我们写进去的中继/上下文载荷"那一族（名字含 `Relay`，
        # 或以 `ContextExpectedBytes` 结尾）—— 它们描述的是**打补丁后**的镜像，原始镜像里没有，
        # 由各自的"写完读回自校验"钉住（`test_entry_relay_ledger.py` 等）。别的名字落进来 ⇒ 判红：
        # 那说明新加了一个守卫常量而它没被比过 —— 本批补的两个洞（`*Discriminator` 后缀不进
        # `ARRAY_PATTERN`、基名以 `File` 结尾时配不上）就是这么静默存在了很久的。
        offenders = [
            name for name in report["unpaired_arrays"]
            if "Relay" not in name and not name.endswith("ContextExpectedBytes")
        ]
        self.assertEqual(
            offenders, [],
            "这些守卫常量没有被比过（名字后缀不在 ARRAY_SUFFIXES 里？基名配不上偏移？）："
            + repr(offenders),
        )
        # 比过且对上的条数下限：2026-09-29 实测 147 条比过、132 条对上（15 条是 patched-image）。
        # 改窄判据（少比一类常量）会掉下去 ⇒ 判红。
        self.assertGreaterEqual(report["matched"], 130)


if __name__ == "__main__":
    unittest.main()
