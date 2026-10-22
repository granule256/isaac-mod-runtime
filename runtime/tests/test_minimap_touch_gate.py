"""门禁：批次 193「原生右上角小地图只响应手指停在上面的拖拽」不许悄悄退化。

## 背景（用户诉求）

Switch 版游戏**自己**那套触摸处理只看"手指 ID 与上一帧相同"、不看手指在哪 ⇒ 屏幕上
**任意位置**的拖动都会平移/缩放右上角的**原生小地图**（玩 GoodTrip 的地图时被它干扰）。
用户原话：「原本的 ns 自己的右上角小地图是**全局触摸**都会影响到这个小地图，
能不能改成**局部触摸**的」。

批次 193 只改 `Minimap::Update` 里的 **3 条指令**（3 个 4 字节字），一台真机只看一次行为，
所以门禁要挡住的正是"改一个字节就改坏游戏"以及"后人以为第 3 处多余而删掉"这两类退化。

★ 2026-10-14 更正：第三处恢复原版长按门控，不是独立全屏摸十次收文字；
原文保留作历史记录，原生CPU行为验证另见 test_minimap_native_longpress.py。

## 这一层能验什么、验不了什么

* **能验**：补丁表（偏移 + 期望原值 + 新值）被钉住；新值的**机器码**同时与
  ①本题里独立实现的 AArch64 参考编码器、②devkitA64 真汇编器（有 docker 时）一致；
  期望原值与仓库里的游戏镜像逐字一致；守卫语义（现场不符 ⇒ **一个字节都不写**）；
  接线（安装器复用入口中继那套 4 字节改写，不是第二套写代码的办法）。
* **验不了**：真机上"小地图真的只对局部触摸响应"、以及"摸屏幕仍然自动收道具文字" ——
  **只能真机**（与其它引擎行为同一性质）。本模块只保证"我们改的就是那三条指令、
  口径一个字节都没漂"。
"""

import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
HEADER = SOURCE / "patch" / "minimap_touch_gate.hpp"
IMPLEMENTATION = SOURCE / "patch" / "minimap_touch_gate.cpp"
HOOK_MANAGER = SOURCE / "hook_manager.cpp"
ENTRY_RELAY_HEADER = SOURCE / "relay" / "entry_relay.hpp"
ENTRY_RELAY_IMPL = SOURCE / "relay" / "entry_relay.cpp"
ELF = ROOT / "runtime" / ".gdbsym-artifacts" / "runtime.elf"
NRO = (
    ROOT
    / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    / "Program #0/1/.nro/Repentance.nro"
)
DOCKER_IMAGE = "devkitpro/devkita64:latest"

#: ★★ 口径本身：偏移 + 期望原值 + 新值。
#: 这三行就是"改什么"的全部内容，**硬编码在这里**（而不是从被测代码里再读一遍）——
#: 被测代码改一个字节，这条就红。来源：父线程 Ghidra 反汇编 + 本机游戏镜像逐字核对。
EXPECTED_PATCHES = [
    (0x41CCC4, 0x52800034, 0xD503201F),  # mov w20,#1 → nop
    (0x41CCCC, 0x34000908, 0x36000914),  # cbz w8 → tbz w20,#0（落点仍是 0x41CDEC）
    (0x41CE68, 0x36000134, 0x36000134),  # 保留原版tbz w20,#0：长按计数/ShowName共用
]

#: 游戏镜像里应当看到的**邻居**指令（用来钉住"这三处确实是那三条指令"，
#: 而不是"某个地址上恰好有同样的字"）。
EXPECTED_NEIGHBOURS = {
    0x41CC78: 0x2A080294,  # orr  w20, w20, w8      —— 小地图矩形的那个 w20 来源，本批不动
    0x41CCC8: 0x17FFFFCA,  # b    0x41CBF0          —— #1 后面的循环回边（所以 #1 是"置位后立刻回边"）
    0x41CE60: 0xB943C3E8,  # ldr  w8, [sp, #960]    —— #3 处 w8 的来源：本帧触摸点数
    0x41CE64: 0xB90B2268,  # str  w8, [x19, #2848]  —— 存进 Minimap + 0xb20（上一帧点数）
}

#: 三个落点（`tbz`/`cbz` 的目标）：拖拽跳过点与计数跳过点。
DRAG_SKIP_ADDRESS = 0x41CDEC
COUNTER_SKIP_ADDRESS = 0x41CE8C
TBZ_PC = 0x41CCCC
CBZ_COUNTER_PC = 0x41CE68

NOP = 0xD503201F

#: 四个诊断量（名字与类型要稳定：父线程要把它们加进读数工具）。
DIAGNOSTIC_NAMES = (
    "g_MinimapTouchGateState",
    "g_MinimapTouchGateApplied",
    "g_MinimapTouchGateGuardMismatch",
    "g_MinimapTouchGateFailureCode",
)


# --------------------------------------------------------------------------
# 独立实现的 AArch64 参考编码器 / 解码器（**不复用**被测代码里的任何实现）
# --------------------------------------------------------------------------


def sign_extend(value: int, bits: int) -> int:
    if value & (1 << (bits - 1)):
        return value - (1 << bits)
    return value


def encode_movz_32(rd: int, imm16: int) -> int:
    """`movz Wd, #imm16`（32 位）：sf=0(31)、10(30:29)、100101(28:23)、hw=00(22:21)、imm16(20:5)、Rd。"""
    return 0x52800000 | ((imm16 & 0xFFFF) << 5) | (rd & 0x1F)


def encode_tbz(rt: int, bit: int, delta: int) -> int:
    """`tbz Wt, #bit, label`：b5(31)、011011(30:25)、b40(23:19)、imm14(18:5)、Rt(4:0)。"""
    return (
        0x36000000
        | ((bit & 0x20) << 26)
        | ((bit & 0x1F) << 19)
        | (((delta >> 2) & 0x3FFF) << 5)
        | (rt & 0x1F)
    )


def encode_cbz(rt: int, delta: int, sf: int = 0) -> int:
    """`cbz Wt/Xt, label`：sf(31)、011010(30:25)、op=0(24)、imm19(23:5)、Rt(4:0)。"""
    return 0x34000000 | ((sf & 1) << 31) | (((delta >> 2) & 0x7FFFF) << 5) | (rt & 0x1F)


def decode_pcrel19_target(word: int, pc: int) -> int:
    """`cbz`/`cbnz`/`tbz`/`tbnz`/`b.cond`（imm19 在 23:5；tbz/tbnz 是 imm14 在 18:5）。"""
    if (word & 0x7F000000) in (0x36000000, 0x37000000):
        return pc + (sign_extend((word >> 5) & 0x3FFF, 14) << 2)
    return pc + (sign_extend((word >> 5) & 0x7FFFF, 19) << 2)


def decode_register(word: int) -> int:
    return word & 0x1F


def decode_landing_at(word: int, pc: int) -> int:
    """解码条件分支的落点（`pc` = 这条指令自己的地址）。"""
    return decode_pcrel19_target(word, pc)


def decode_conditional_kind(word: int) -> str:
    """把 `cbz`/`cbnz`/`tbz`/`tbnz` 区分开（本批要拿它证明第 3 处"看的是哪个寄存器"）。"""
    for mask, value, name in (
        (0x7F000000, 0x34000000, "cbz"),
        (0x7F000000, 0x35000000, "cbnz"),
        (0x7F000000, 0x36000000, "tbz"),
        (0x7F000000, 0x37000000, "tbnz"),
    ):
        if (word & mask) == value:
            return name
    return ""


def parse_patch_table(text: str) -> list[tuple[int, int, int]]:
    """读出头文件里的补丁表 `{offset, expected, patched}`。"""
    body = re.search(r"kMinimapTouchGatePatches\s*=\s*\{\{(.*?)\}\};", text, re.DOTALL)
    if body is None:
        raise AssertionError("头文件里找不到 kMinimapTouchGatePatches 补丁表")
    return [
        (int(offset, 16), int(expected, 16), int(patched, 16))
        for offset, expected, patched in re.findall(
            r"\{\s*(0x[0-9A-Fa-f]+)u\s*,\s*(0x[0-9A-Fa-f]+)u\s*,\s*(0x[0-9A-Fa-f]+)u\s*\}",
            body.group(1),
        )
    ]


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        probe = subprocess.run(
            ["docker", "image", "inspect", DOCKER_IMAGE],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


class PatchTableTests(unittest.TestCase):
    """补丁表本身：三个字段都是口径，改一个字节就会改坏游戏。"""

    @classmethod
    def setUpClass(cls):
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.table = parse_patch_table(cls.header)

    def test_table_is_exactly_the_verified_three_words(self):
        self.assertEqual(self.table, EXPECTED_PATCHES)
        self.assertEqual(len(self.table), 3)
        # 三处偏移必须互不相同、且都 4 字节对齐（它们是三条独立指令的地址）。
        offsets = [entry[0] for entry in self.table]
        self.assertEqual(len(set(offsets)), 3)
        for offset in offsets:
            self.assertEqual(offset % 4, 0, hex(offset))

    def test_patched_words_match_an_independent_encoder(self):
        """新值必须等于**本题独立实现**的编码器对目标操作数的编码（不比对魔数收工）。"""
        nop_patched = self.table[0][2]
        tbz_patched = self.table[1][2]
        counter_patched = self.table[2][2]

        self.assertEqual(nop_patched, NOP, "第 1 处必须是 nop")
        self.assertEqual(
            tbz_patched, encode_tbz(20, 0, DRAG_SKIP_ADDRESS - TBZ_PC),
            "第 2 处必须是 tbz w20, #0, 0x41cdec",
        )
        self.assertEqual(
            counter_patched, encode_tbz(20, 0, COUNTER_SKIP_ADDRESS - CBZ_COUNTER_PC),
            "第 3 处必须保留 tbz w20, #0, 0x41ce8c",
        )

    def test_expected_words_are_the_instructions_we_think_they_are(self):
        """期望原值也要解码核对：它决定"我们在什么现场才允许改"。"""
        _o1, expected1, _p1 = self.table[0]
        _o2, expected2, _p2 = self.table[1]
        _o3, expected3, _p3 = self.table[2]
        self.assertEqual(expected1, encode_movz_32(20, 1), "第 1 处的原值该是 mov w20, #1")
        self.assertEqual(decode_conditional_kind(expected2), "cbz")
        self.assertEqual(decode_register(expected2), 8, "第 2 处的原值看的是 w8")
        self.assertEqual(
            decode_pcrel19_target(expected2, TBZ_PC), DRAG_SKIP_ADDRESS,
            "第 2 处原值的落点必须是那个拖拽跳过点",
        )
        self.assertEqual(decode_conditional_kind(expected3), "tbz")
        self.assertEqual(decode_register(expected3), 20, "第 3 处的原值看的是 w20")
        self.assertEqual(
            decode_pcrel19_target(expected3, CBZ_COUNTER_PC), COUNTER_SKIP_ADDRESS,
            "第 3 处原值的落点必须是那个计数跳过点",
        )

    def test_patch_two_keeps_the_original_landing(self):
        """★ 第 2 处的语义等价：原指令与新指令**落点相同**。

        原来 `cbz w8` 是"本帧触摸点数为 0 就跳过"；触摸点数为 0 时循环没跑、`w20` 必然为 0，
        所以换成 `tbz w20, #0` 之后"点数为 0"这条路径照样跳过 —— 只是顺带加上了矩形门控。
        """
        _o, expected, patched = self.table[1]
        self.assertEqual(decode_landing_at(expected, TBZ_PC), decode_landing_at(patched, TBZ_PC))
        self.assertEqual(decode_landing_at(patched, TBZ_PC), DRAG_SKIP_ADDRESS)
        # 而且判据换成了 w20 的 bit0（`tbz w20, #0`），不再是"点数"。
        self.assertEqual(decode_conditional_kind(patched), "tbz")
        self.assertEqual(decode_register(patched), 20)
        self.assertEqual((patched >> 19) & 0x3F, 0, "tbz 的位号必须是 #0")

    def test_patch_one_removes_the_middle_region_assignment(self):
        """★ 第 1 处必须把"中间游戏区 ⇒ w20 = 1"这条置位拿掉，而且是 `nop`。

        拿掉之后 `w20` 只剩小地图矩形那一个来源（0x41cc78 的 `orr w20, w20, w8`），
        第 2 处的门控才等于"手指在小地图矩形内"。
        """
        _o, expected, patched = self.table[0]
        self.assertEqual(expected, encode_movz_32(20, 1))
        self.assertEqual(decode_register(expected), 20)
        self.assertEqual(patched, NOP)
        self.assertNotEqual(patched, expected)
        self.assertNotEqual(decode_register(patched), 20, "nop 不写任何寄存器")

    def test_patch_three_preserves_native_map_hold_counter_gate(self):
        """★★ 第 3 处的存在意义（防止后人以为它多余而删掉）。

        0x41ce68 那句 `tbz w20, #0` 属于**另一个功能**：「摸屏幕累计 10 次就自动收起道具
        说明文字」（0x41ce6c 起：计数 +1，到 10 就调 0x67a610）。第 1 处之后 `w20` 只反映
        "手指在小地图矩形内" ⇒ 若不同时改第 3 处，那个功能会变成"只有摸小地图才收文字"
        —— 把用户没要求改的行为改坏。

        所以第 3 处必须改成看**本帧触摸点数**：`w8`（0x41ce60 从 `[sp, #960]` 读出、
        0x41ce64 刚存进 `Minimap + 0xb20`）。下面同时用编码与头文件注释两路钉住这一点。
        ★ 2026-10-14 更正：以上是历史误解；必须保留w20长按计数门控。
        """
        _o, expected, patched = self.table[2]
        self.assertEqual(decode_conditional_kind(expected), "tbz", "原值看的是 w20")
        self.assertEqual(decode_register(expected), 20)
        self.assertEqual(decode_conditional_kind(patched), "tbz", "保留原生按住门控")
        self.assertEqual(decode_register(patched), 20, "仍看w20：ACTION_MAP或局部触摸")
        self.assertEqual(patched, expected, "第三处不再修改原版机器码")
        self.assertEqual(decode_landing_at(patched, CBZ_COUNTER_PC), COUNTER_SKIP_ADDRESS)
        # 注释与断言双保险：删掉/改回第 3 处时，这条注释也必须在（它解释了为什么不能删）。
        for marker in ("#3", "2026-10-14 更正", "Level::ShowName(true)", "ACTION_MAP"):
            self.assertIn(marker, self.header, f"头文件里关于第 3 处的说明少了「{marker}」")

    def test_header_explains_the_deliberate_semantics_change(self):
        """第 2 处的语义变化与"刻意不用起点字段"这两个决定必须留在注释里（免得被当成 bug 改回去）。"""
        for marker in ("TouchEvent+0x08", "手指当前在小地图矩形内"):
            self.assertIn(marker, self.header, f"头文件缺少「{marker}」的说明")


class NeighbourInstructionTests(unittest.TestCase):
    """拿仓库里的游戏镜像把"这三处确实是我们以为的那三条指令"钉死。"""

    @classmethod
    def setUpClass(cls):
        if not NRO.exists():
            raise unittest.SkipTest("仓库里没有游戏镜像（公开仓库不带游戏资源）")
        cls.image = NRO.read_bytes()

    def test_expected_words_are_what_the_game_image_holds(self):
        for offset, expected, _patched in EXPECTED_PATCHES:
            actual = struct.unpack_from("<I", self.image, offset)[0]
            self.assertEqual(actual, expected, f"{offset:#x} 处的原值与补丁表不符")

    def test_neighbours_pin_the_patch_sites(self):
        """邻居指令决定"这三处是那三条"：置位后立刻回边、w8 在那里是触摸点数。"""
        for offset, expected in EXPECTED_NEIGHBOURS.items():
            actual = struct.unpack_from("<I", self.image, offset)[0]
            self.assertEqual(actual, expected, f"邻居 {offset:#x} 不符（补丁位置可能挪了）")

    def test_patch_three_reads_w8_which_is_the_touch_count(self):
        """第 3 处那一点上 `w8` 确实是触摸点数：紧邻的两条指令一起把它钉住。"""
        load = struct.unpack_from("<I", self.image, 0x41CE60)[0]   # ldr w8, [sp, #960]
        store = struct.unpack_from("<I", self.image, 0x41CE64)[0]  # str w8, [x19, #2848]
        self.assertEqual(load, 0xB943C3E8)
        self.assertEqual(store, 0xB90B2268)
        # `ldr w8, [sp, #960]`：imm12 在 21:10、`ldr` 按 4 字节缩放 ⇒ 偏移 = imm12 × 4。
        self.assertEqual(((load >> 10) & 0xFFF) * 4, 960, "读的是那格触摸点数")
        # `str w8, [x19, #2848]`：0xb20 = 2848 = `Minimap + 0xb20`（上一帧触摸点数）。
        self.assertEqual(((store >> 10) & 0xFFF) * 4, 0xB20, "存的是 Minimap 里那格点数")
        self.assertEqual(decode_register(load), 8)
        self.assertEqual(decode_register(store), 8)

    def test_patch_one_sits_on_the_middle_region_path(self):
        """第 1 处所在的路径：置位之后紧接着就是循环回边（0x41ccc8 → 0x41cbf0）。"""
        branch = struct.unpack_from("<I", self.image, 0x41CCC8)[0]
        self.assertEqual(branch, 0x17FFFFCA)
        target = 0x41CCC8 + (sign_extend(branch & 0x03FFFFFF, 26) << 2)
        self.assertEqual(target, 0x41CBF0, "第 1 处之后必须立刻回到循环头")

    def test_rect_source_of_w20_is_untouched(self):
        """小地图矩形的那个 `w20` 来源（0x41cc78）**本批一个字都不改**。"""
        self.assertEqual(struct.unpack_from("<I", self.image, 0x41CC78)[0], 0x2A080294)  # orr w20,w20,w8


class AssemblerAgreementTests(unittest.TestCase):
    """新值必须与**真汇编器**一致（有 devkitA64 容器时跑；没有就跳过）。"""

    ASSEMBLY = """
    .text
    .org 0x41ccc4
    nop
    .org 0x41cccc
    tbz w20, #0, skip_drag
    .org 0x41cdec
skip_drag:
    .org 0x41ce68
    tbz w20, #0, skip_counter
    .org 0x41ce8c
skip_counter:
"""

    def test_patched_words_match_devkita64(self):
        if not docker_available():
            self.skipTest("没有 devkitpro/devkita64 容器（真汇编器核对跳过）")
        with tempfile.TemporaryDirectory(prefix="isaac-minimap-as-") as directory:
            workdir = Path(directory)
            (workdir / "gate.s").write_text(self.ASSEMBLY.lstrip(), encoding="utf-8")
            command = (
                ". /opt/devkitpro/devkita64.sh && "
                "aarch64-none-elf-as -o /t/gate.o /t/gate.s && "
                "aarch64-none-elf-objdump -d /t/gate.o"
            )
            try:
                done = subprocess.run(
                    ["docker", "run", "--rm", "-v", f"{workdir}:/t", DOCKER_IMAGE,
                     "bash", "-lc", command],
                    capture_output=True, text=True, timeout=300,
                )
            except (OSError, subprocess.SubprocessError) as error:  # pragma: no cover - 环境问题
                self.skipTest(f"容器起不来（真汇编器核对跳过）：{error}")
            if done.returncode != 0:
                self.skipTest(f"汇编/反汇编没成功（跳过）：{done.stdout}{done.stderr}")
            assembled = {}
            for line in done.stdout.splitlines():
                match = re.match(r"\s*([0-9a-f]+):\s+([0-9a-f]{8})\s", line)
                if match:
                    assembled[int(match.group(1), 16)] = int(match.group(2), 16)
        for offset, _expected, patched in EXPECTED_PATCHES:
            self.assertIn(offset, assembled, f"反汇编里没有 {offset:#x}（.org 布局变了？）")
            self.assertEqual(assembled[offset], patched,
                             f"{offset:#x} 的新值与真汇编器不符")


HARNESS = r'''
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

#include "patch/minimap_touch_gate.hpp"
#include "relay/entry_relay.hpp"

using namespace isaac::runtime;

int main() {
    int failures = 0;
    auto check = [&](bool ok, const char* what) {
        if (!ok) { std::printf("FAIL %s\n", what); ++failures; }
    };

    // ---- 1) ★★ 守卫语义：现场不符 ⇒ **一个字节都不写** ----
    // 用合成缓冲喂**真机同款**改写函数（真机上喂的是 RwPages 的可写别名）。
    for (std::size_t index = 0; index < kMinimapTouchGatePatches.size(); ++index) {
        const MinimapTouchGatePatch& patch = kMinimapTouchGatePatches[index];
        // 1a) 现场是**别的东西**（把期望原值改一位即可）⇒ 必须拒绝，且缓冲逐字节不变。
        const std::uint32_t wrong = patch.expected ^ 0x1u;
        std::vector<std::uint8_t> buffer(sizeof(std::uint32_t), 0);
        std::memcpy(buffer.data(), &wrong, sizeof(wrong));
        const std::vector<std::uint8_t> before = buffer;
        check(relay::RewriteCodeWordInBuffer(buffer.data(), patch.expected, patch.patched) ==
                  relay::CodeWordPatchFailure::GuardMismatch,
              "a mismatching word must be rejected");
        check(buffer == before, "a rejected patch must not touch the buffer");

        // 1b) 现场就是期望原值 ⇒ 写入新字（小端），返回 None。
        std::vector<std::uint8_t> good(sizeof(std::uint32_t), 0);
        std::memcpy(good.data(), &patch.expected, sizeof(patch.expected));
        check(relay::RewriteCodeWordInBuffer(good.data(), patch.expected, patch.patched) ==
                  relay::CodeWordPatchFailure::None,
              "a matching word must be accepted");
        std::uint32_t written = 0;
        std::memcpy(&written, good.data(), sizeof(written));
        check(written == patch.patched, "the buffer must hold the new word (little endian)");
    }

    // ---- 2) 空指针不是"成功" ----
    check(relay::RewriteCodeWordInBuffer(nullptr, 0, 0) ==
              relay::CodeWordPatchFailure::InvalidAddress,
          "a null buffer must be rejected");

    // ---- 3) 三处守卫的判据本身（真机路径与这里共用同一份）----
    std::array<std::uint32_t, kMinimapTouchGatePatchCount> current{};
    for (std::size_t index = 0; index < current.size(); ++index) {
        current[index] = kMinimapTouchGatePatches[index].expected;
    }
    check(FirstMinimapTouchGateGuardMismatch(current) == 0, "all-matching must report 0");
    check(CountMinimapTouchGateGuardMismatches(current) == 0, "all-matching count must be 0");
    for (std::size_t index = 0; index < current.size(); ++index) {
        current[index] ^= 0xFFu;
        check(FirstMinimapTouchGateGuardMismatch(current) ==
                  static_cast<std::uint32_t>(index) + 1u,
              "must report the first mismatching entry (1-based)");
        check(CountMinimapTouchGateGuardMismatches(current) == 1, "single mismatch counts once");
        current[index] ^= 0xFFu;
    }
    current[0] ^= 1u;
    current[2] ^= 1u;
    check(FirstMinimapTouchGateGuardMismatch(current) == 1, "the first of two must win");
    check(CountMinimapTouchGateGuardMismatches(current) == 2, "two mismatches count twice");

    // ---- 4) 诊断量的枚举值与失败码打包口径稳定（父线程的读数工具按这些值判读）----
    check(static_cast<std::uint32_t>(MinimapTouchGateState::kNotTried) == 0, "state 0");
    check(static_cast<std::uint32_t>(MinimapTouchGateState::kInstalled) == 1, "state 1");
    check(static_cast<std::uint32_t>(MinimapTouchGateState::kFailed) == 2, "state 2");
    check(static_cast<std::uint32_t>(MinimapTouchGateFailureKind::kModuleInvalid) == 1, "kind 1");
    check(static_cast<std::uint32_t>(MinimapTouchGateFailureKind::kGuardMismatch) == 2, "kind 2");
    check(static_cast<std::uint32_t>(MinimapTouchGateFailureKind::kWriteFailed) == 3, "kind 3");
    check(MakeMinimapTouchGateFailureCode(MinimapTouchGateFailureKind::kGuardMismatch, 2) == 0x202,
          "failure code = (index << 8) | kind");
    check(g_MinimapTouchGateState.load() == 0 && g_MinimapTouchGateApplied.load() == 0 &&
              g_MinimapTouchGateGuardMismatch.load() == 0 &&
              g_MinimapTouchGateFailureCode.load() == 0,
          "host: the counters start at 0 (nothing is installed here)");

    if (failures != 0) {
        std::printf("MINIMAP_TOUCH_GATE_CHECKS_FAILED %d\n", failures);
        return 1;
    }
    std::printf("MINIMAP_TOUCH_GATE_CHECKS_PASSED\n");
    return 0;
}
'''


def host_compiler() -> str | None:
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return found
    return None


def code_of(source: str) -> str:
    """只保留代码、剔掉 `//` 行注释。

    本项目的注释里**大量引用被禁止的写法**（本文件就有一条"RwPages 可写别名"的说明，
    那是解释"复用哪套机制"的话）⇒ 直接对全文断言 `assertNotIn` 会被这些注释本身判红，
    而那与实现无关。断言要盯的是**代码**。
    """
    return "\n".join(line.split("//", 1)[0] for line in source.splitlines())


class GuardSemanticsTests(unittest.TestCase):
    """宿主机上能验的那一半：守卫语义与判据（真值只能真机）。"""

    def test_host_semantics(self):
        compiler = host_compiler()
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-minimap-gate-") as directory:
            workdir = Path(directory)
            source = workdir / "harness.cpp"
            source.write_text(HARNESS.lstrip(), encoding="utf-8")
            binary = workdir / "harness"
            build = subprocess.run(
                [compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-I", str(SOURCE),
                 str(source), "-o", str(binary)],
                text=True, capture_output=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("MINIMAP_TOUCH_GATE_CHECKS_PASSED", run.stdout)


class WiringTests(unittest.TestCase):
    """接线：复用既有写代码机制、装在一次启动路径上、守卫排在写入之前。"""

    @classmethod
    def setUpClass(cls):
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.implementation = IMPLEMENTATION.read_text(encoding="utf-8")
        cls.hook_manager = HOOK_MANAGER.read_text(encoding="utf-8")

    def test_installer_reuses_the_entry_relay_word_rewriter(self):
        """不许发明第二套写代码的办法：改写只能走入口中继那个 4 字节原语。"""
        code = code_of(self.implementation)
        self.assertIn("relay::TryRewriteCodeWord(", code)
        self.assertIn('#include "relay/entry_relay.hpp"', code)
        for forbidden in ("RwPages", "JIT_CREATE", "armDCacheFlush", "armICacheInvalidate"):
            self.assertNotIn(forbidden, code,
                             f"安装器自己碰了 {forbidden} —— 应当复用 entry_relay 里的原语")

    def test_entry_relay_gained_the_generic_word_rewriter(self):
        """原语本身在入口中继那一侧：RwPages + Flush + 只读读回（与入口改写同一条路）。"""
        implementation = ENTRY_RELAY_IMPL.read_text(encoding="utf-8")
        self.assertIn("CodeWordPatchFailure TryRewriteCodeWord(", implementation)
        self.assertIn("exl::util::RwPages pages(target, sizeof(std::uint32_t));", implementation)
        self.assertIn("pages.Flush();", implementation)
        # 既有行为不许动：入口 16 字节那条路照旧。
        self.assertIn("exl::util::RwPages entryPages(target, kEntryPatchBytes);", implementation)
        header = ENTRY_RELAY_HEADER.read_text(encoding="utf-8")
        self.assertIn("constexpr CodeWordPatchFailure RewriteCodeWordInBuffer(", header)
        self.assertIn("GuardMismatch = 2", header)

    def test_guard_is_evaluated_before_any_write(self):
        """全有或全无：三处一起核对，**核对排在任何一次改写之前**。"""
        body = self.implementation
        guard = body.index("FirstMinimapTouchGateGuardMismatch(current)")
        write = body.index("relay::TryRewriteCodeWord(")
        self.assertLess(guard, write, "守卫必须排在写入之前")
        between = body[guard:write]
        self.assertIn("return false;", between, "守卫不符那条路径必须直接返回，不能继续往下写")
        self.assertIn("ReadWord(address, &current[index])", body,
                      "现场原值要从游戏代码段读出来核对")
        # 读不出来（地址非法/不可读）也走同一条"一处都不写"的路径，且可读性判据用框架那一份
        # （【不许自己再抄一份 svcQueryMemory —— 存量冻结台账：新功能走框架接口】）。
        self.assertIn("engine_memory::EngineMemoryReadable", body)

    def test_installer_is_called_from_the_module_startup_path(self):
        install = self.hook_manager[
            self.hook_manager.index("DefaultManifestInstallResult TryInstallDefaultManifestMod"):
            self.hook_manager.index("uintptr_t target_address(uintptr_t base, uintptr_t offset)")
        ]
        self.assertIn("isaac::runtime::InstallMinimapTouchGate(module.base, module.textSize);",
                      install, "模块启动路径上必须真的调用它")
        self.assertIn('#include "patch/minimap_touch_gate.hpp"', self.hook_manager)

    def test_diagnostics_have_stable_names_and_types(self):
        """四个诊断量：父线程要把它们加进读数工具，名字与类型不许变。"""
        for name in DIAGNOSTIC_NAMES:
            self.assertIn(f"inline std::atomic<std::uint32_t> {name}{{0}};", self.header, name)

    def test_elf_exposes_the_diagnostics_when_a_build_exists(self):
        """构建产物里必须有这四个符号（名字 = `isaac::runtime` 命名空间下的 mangling）。

        没有产物就跳过；**有产物却缺符号 ⇒ 红**：那说明 `.gdbsym-artifacts/runtime.elf`
        不是这一版源码编出来的（读数工具会拿着过期偏移解释现场）。
        """
        if not ELF.exists():
            self.skipTest(f"没有本地构建产物 {ELF.relative_to(ROOT)}")
        import importlib.util

        spec = importlib.util.spec_from_file_location("elf_syms", ROOT / "tools" / "elf_syms.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        symbols = module.load_symbols(ELF.read_bytes())
        for name in DIAGNOSTIC_NAMES:
            mangled = f"_ZN5isaac7runtime{len(name)}{name}E"
            self.assertIn(mangled, symbols, f"构建产物里没有 {name}（{mangled}）")
            self.assertEqual(symbols[mangled][1], 4, f"{name} 应当是 4 字节的 u32 原子量")


if __name__ == "__main__":
    unittest.main()
