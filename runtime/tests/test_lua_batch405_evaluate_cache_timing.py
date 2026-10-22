"""门禁：`MC_EVALUATE_CACHE` 的**派发时机**必须是"跑完原函数之后"（批次 405，2026-10-07）。

## 这一批修的两个原因（同一批做，缺一个就白干）

真机读数（卡上批次 402）里，自定义角色 Trinity 的属性调整**完全不生效**，错误环是：

    [8 MC_EVALUATE_CACHE] rom:/isaac_mods/mods/Trinity/main.lua:85:
        EntityPlayer fields are read-only except Velocity/Position/HitPoints/MaxHitPoints...
    [8 MC_EVALUATE_CACHE] rom:/isaac_mods/mods/Trinity/main.lua:116: 同上

`Trinity/main.lua` 在自己的 `MC_EVALUATE_CACHE` 处理器里写 `player.Damage` / `player.MoveSpeed` /
`player.Luck` / `player.MaxFireDelay`（PC 上都是可写变量）。于是：

1. **可写白名单缺这六格** ⇒ 模组写就抛错 ⇒ 整条回调被派发器摘掉。
2. ★★ **派发时机错了**：引擎的 `Entity_Player::EvaluateItems` 对这几格是**清零 + 重建**
   （`CACHE_DAMAGE` 置位先 `str wzr,[x19,#0x1844]` 再累加），而它内部没有这条回调的派发点
   ⇒ 我们若在**入口先派发、再跑原函数**，模组写进去的值会在同一次重算里被覆盖。
   PC 侧是引擎**重算之后**派发（契约反复写 "Only change this in MC_EVALUATE_CACHE"）。

本模块钉的就是第 2 条的**顺序与快照语义**（第 1 条的行为判据在
`test_lua_entity_player.py` 的 `valid` 场景，源码判据在 `test_engine_write_channel.py`）。

## 判据怎么做到"可观测"而不是"读源码"

`hook_manager.cpp` 那个中继在宿主机上编不出来（拖着 exlaunch/libnx）。顺序与快照语义抽进了
`interfaces/lua/evaluate_cache_dispatch.hpp` 的纯模板 `DispatchEvaluateCacheAfterOriginal`，
三个动作换成可注入回调 ⇒ 用它自己的真实实现 + **假原函数 / 假派发**逐条钉住：

* **顺序**：假原函数先记一次、假派发后记一次 ⇒ 顺序串必须是 `01`；
* **模组的写没被覆盖**：假原函数把假字段设成 111、假派发把它设成 222 ⇒ 终值必须是 222
  （若派发在 original 之前，这里会是 111）；
* **派发读到的是新值**：假派发在进函数时读那个字段 ⇒ 必须是 111（证明它确实跑在 original 之后）；
* **快照**：`readFlags` 给 0b101、假原函数**清掉** flags ⇒ 仍必须恰好派发 bit0 与 bit2 各一次；
* **读不到掩码**：`readFlags` 返回 false ⇒ 仍跑原函数、但一位都不派发。
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "runtime" / "src"
SOURCE = ROOT / "runtime" / "source"
HEADER = SRC / "interfaces" / "lua" / "evaluate_cache_dispatch.hpp"
HOOK_MANAGER = SOURCE / "hook_manager.cpp"
ISAAC_API = SRC / "interfaces" / "lua" / "isaac_api.cpp"
CONSTANTS = SOURCE / "runtime_constants.hpp"

DRIVER = r"""
#include "interfaces/lua/evaluate_cache_dispatch.hpp"
#include <cstdint>
#include <cstdio>
#include <vector>

namespace {

// 假装是引擎里那个"模组会写、原函数会重算"的属性格。
int g_field = 0;
// 假装是 `_cacheFlags`（原函数会把脏位清掉）。
int g_flags = 0;
// 0 = 原函数跑过、1 = 派发跑过。
std::vector<int> g_order;
int g_originalCalls = 0;
int g_dispatchSeenField = -1;
std::vector<int> g_bits;

void Reset() {
    g_field = 0;
    g_flags = 0;
    g_order.clear();
    g_originalCalls = 0;
    g_dispatchSeenField = -1;
    g_bits.clear();
}

void Dump(const char* label) {
    std::printf("%s.order=", label);
    for (int item : g_order) std::printf("%d", item);
    std::printf("\n%s.original_calls=%d\n", label, g_originalCalls);
    std::printf("%s.dispatch_seen_field=%d\n", label, g_dispatchSeenField);
    std::printf("%s.final_field=%d\n", label, g_field);
    std::printf("%s.bits=", label);
    for (int bit : g_bits) std::printf("%d,", bit);
    std::printf("\n%s.bit_count=%zu\n", label, g_bits.size());
}

}  // namespace

int main() {
    // ① 顺序 + "派发读到新值" + "模组的写存活"：只用一个位，避免多次派发互相干扰。
    Reset();
    g_flags = 0x1;  // bit0
    isaac::runtime::DispatchEvaluateCacheAfterOriginal(
        [](std::uint32_t* out) {
            *out = static_cast<std::uint32_t>(g_flags);
            return true;
        },
        []() {
            // 假原函数：先记顺序，再"重算"字段（111），最后清掉脏位（模拟引擎行为）。
            g_order.push_back(0);
            g_originalCalls += 1;
            g_field = 111;
            g_flags = 0;
        },
        [](std::int32_t bit) {
            // 假派发：进来先读字段（证明它跑在原函数之后），再写模组想要的值。
            g_order.push_back(1);
            g_dispatchSeenField = g_field;
            g_field = 222;
            g_bits.push_back(bit);
        });
    Dump("ordered");

    // ② 逐位过滤用调用前快照：原函数清掉 flags 后，bit0 与 bit2 仍各自派发一次。
    Reset();
    g_flags = 0x5;  // bit0 + bit2
    isaac::runtime::DispatchEvaluateCacheAfterOriginal(
        [](std::uint32_t* out) {
            *out = static_cast<std::uint32_t>(g_flags);
            return true;
        },
        []() { g_flags = 0; },
        [](std::int32_t bit) { g_bits.push_back(bit); });
    Dump("snapshot");

    // ③ 掩码读不到 ⇒ 仍跑原函数，但一位都不派发。
    Reset();
    isaac::runtime::DispatchEvaluateCacheAfterOriginal(
        [](std::uint32_t*) { return false; },
        []() { g_originalCalls += 1; },
        [](std::int32_t) { g_bits.push_back(99); });
    Dump("unreadable");

    // ④ ★★★ 批次 409（2026-10-08）：派发给模组的实参必须是 `CacheFlag` 的**值**，不是位序号。
    //    模组拿它与 `CacheFlag.CACHE_XXX` 比（值 = 1/2/4/8/16/…/1024）。
    //    这里按位置把"值"打出来，与 `doc_lua_enum_data.cpp` 的表逐值对齐。
    std::printf("values=");
    for (int bit : {0, 1, 2, 3, 4, 5, 10}) {
        std::printf("%d,", isaac::runtime::CacheFlagValueForBit(bit));
    }
    std::printf("\n");
    return 0;
}
"""


def find_compiler():
    for candidate in (os.environ.get("CXX"), "clang++", "g++"):
        if candidate and shutil.which(candidate):
            return shutil.which(candidate)
    return None


class EvaluateCacheTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = find_compiler()
        cls.output = {}
        cls.compile_error = None
        if cls.compiler is None:
            return
        cls.tempdir = tempfile.TemporaryDirectory(prefix="eval_cache_timing_")
        source = Path(cls.tempdir.name) / "evaluate_cache_timing_driver.cpp"
        source.write_text(DRIVER.lstrip(), encoding="utf-8")
        binary = Path(cls.tempdir.name) / "driver"
        build = subprocess.run(
            [cls.compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror",
             "-I", str(SOURCE), "-I", str(SRC), "-o", str(binary), str(source)],
            capture_output=True, text=True,
        )
        if build.returncode != 0:
            cls.compile_error = build.stderr.strip() or build.stdout.strip()
            return
        run = subprocess.run([str(binary)], capture_output=True, text=True)
        if run.returncode != 0:
            cls.compile_error = f"driver 退出码 {run.returncode}: {run.stderr.strip()}"
            return
        for line in run.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                cls.output[key] = value

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "tempdir", None) is not None:
            cls.tempdir.cleanup()

    def require_driver(self):
        if self.compiler is None:
            self.skipTest("宿主机没有可用的 C++ 编译器（clang++/g++），跳过真实头文件执行测试")
        if self.compile_error:
            self.fail(f"头文件在宿主机编译/执行失败：{self.compile_error}")

    # ------------------------------------------------------------------
    # 行为判据（宿主机编译并执行真实头文件）
    # ------------------------------------------------------------------

    def test_dispatch_happens_after_original(self):
        """② 派发必须在 `original` 之后（顺序串 = 01）。"""
        self.require_driver()
        self.assertEqual(self.output["ordered.order"], "01",
                         "派发必须发生在原函数之后（顺序串应为 01，先派发再跑原函数是 10）")
        self.assertEqual(self.output["ordered.original_calls"], "1")

    def test_dispatch_sees_the_recomputed_value(self):
        """② 回调读到的应当是引擎重算后的新值（111），不是更早的旧值。"""
        self.require_driver()
        self.assertEqual(self.output["ordered.dispatch_seen_field"], "111",
                         "派发跑在原函数之前时，回调只会读到旧值（0）")

    def test_module_write_survives_after_the_original(self):
        """② 模组写进去的值必须在假原函数之后仍然存活（终值 = 模组写的 222，不是 original 的 111）。"""
        self.require_driver()
        self.assertEqual(self.output["ordered.final_field"], "222",
                         "模组的写在同一次重算里被覆盖 ⇒ 就是 Trinity 属性不生效的病根")

    def test_bit_filtering_uses_the_pre_call_snapshot(self):
        """③ 逐位过滤用**调用前快照**：原函数清掉 flags 后，bit0/bit2 仍各自派发一次。"""
        self.require_driver()
        self.assertEqual(self.output["snapshot.bits"], "0,2,",
                         "置过的位（0 与 2）必须都派发到，且用调用前快照，不是原函数清空后的 0")
        self.assertEqual(self.output["snapshot.bit_count"], "2")

    def test_unreadable_flags_still_run_original_without_dispatch(self):
        """掩码读不到 ⇒ 原函数照跑、但一位都不派发（不编造 CacheFlag）。"""
        self.require_driver()
        self.assertEqual(self.output["unreadable.original_calls"], "1")
        self.assertEqual(self.output["unreadable.bit_count"], "0")

    def test_dispatched_argument_is_the_cache_flag_value_not_the_bit_index(self):
        """★★★ 批次 409（2026-10-08）：派发/过滤用的实参必须是 `CacheFlag` 的**值**（`1 << bit`）。

        这是真机上"Isaiah 伤害 3.50（应 2.75）、速度 1.00（应 1.10）"的根因：
        中继原来把位序号（0/1/2…）当 `cacheFlag` 交给模组，而模组拿它与 `CacheFlag.CACHE_XXX`
        的**值**比 ⇒ `CACHE_SPEED(16)` / `CACHE_LUCK(1024)` 要的位序号根本不存在 ⇒ 永不触发；
        `CACHE_DAMAGE(1)` 撞到射速位（位序号 1）⇒ 值写进去又被下一次伤害重算覆盖。
        """
        self.require_driver()
        self.assertEqual(
            self.output["values"], "1,2,4,8,16,32,1024,",
            "`CacheFlagValueForBit` 必须与 `doc_lua_enum_data.cpp` 的 CacheFlag 表逐值一致"
            "（CACHE_DAMAGE=1 / FIREDELAY=2 / SHOTSPEED=4 / RANGE=8 / SPEED=16 / "
            "TEARFLAG=32 / LUCK=1024）")

    def test_relay_converts_the_bit_to_a_cache_flag_value(self):
        """接线：中继那一步必须做转换，而不是把位序号直接交出去。"""
        hook = HOOK_MANAGER.read_text(encoding="utf-8")
        body = hook[hook.index("extern \"C\" void EntryRelayEvaluateItemsCallback(void* player) {"):]
        body = body[:body.index("\n}\n") + 3]
        self.assertIn("CacheFlagValueForBit(", body,
                      "中继必须用 `CacheFlagValueForBit` 把位序号换成 CacheFlag 的值")
        self.assertNotIn("DispatchEvaluateCache(address, bit)", body,
                         "`DispatchEvaluateCache(address, bit)` 是把**位序号**当 CacheFlag 交出去"
                         "（409 修掉的那个 bug）")

    # ------------------------------------------------------------------
    # 接线判据（防止"设施做了、中继没用它"）
    # ------------------------------------------------------------------

    def test_relay_uses_the_ordering_helper(self):
        hook = HOOK_MANAGER.read_text(encoding="utf-8")
        self.assertIn('#include "interfaces/lua/evaluate_cache_dispatch.hpp"', hook,
                      "中继必须用这个可测的顺序助手，而不是自己再抄一遍顺序")
        body = hook[hook.index("extern \"C\" void EntryRelayEvaluateItemsCallback(void* player) {"):]
        body = body[:body.index("\n}\n") + 3]
        self.assertIn("DispatchEvaluateCacheAfterOriginal(", body,
                      "EntryRelayEvaluateItemsCallback 必须调用顺序助手")
        # 旧的"入口先派发"内联循环必须已经不在这个中继里（否则会派发两次 / 又跑回错误时机）。
        self.assertNotIn("for (std::int32_t bit = 0; bit < 32; ++bit)", body,
                         "中继里还留着旧的内联派发循环 ⇒ 会派发两次且时机仍错")

    def test_helper_takes_the_snapshot_before_running_original(self):
        header = HEADER.read_text(encoding="utf-8")
        body = header[header.index("DispatchEvaluateCacheAfterOriginal"):]
        body = body[body.index("{") + 1:]
        snapshot = body.index("readFlags(&mask)")
        run = body.index("original();")
        first_dispatch = body.index("dispatch(bit)")
        self.assertLess(snapshot, run, "快照必须在跑原函数之前")
        self.assertLess(run, first_dispatch, "逐位派发必须在跑原函数之后")
        # 原函数**不得**出现在任何一次派发之后（旧时机正好是反过来）。
        self.assertNotIn("original();", body[first_dispatch:],
                         "原函数在派发之后才跑 ⇒ 又会覆盖模组的写（本批要修的时机）")
        # 逐位过滤用的是快照 `mask`，不是重新读的掩码。
        self.assertIn("mask & (static_cast<std::uint32_t>(1U) << bit)", body)

    def test_writable_stat_fields_and_message_are_declared(self):
        """白名单确实开了这六格，且拒写文案列出了它们的名字。"""
        api = ISAAC_API.read_text(encoding="utf-8")
        body = api[api.index("int EntityNewIndex("):]
        body = body[:body.index("\n}\n") + 3]
        for field, constant in (
                ("MaxFireDelay", "kEntityPlayerMaxFireDelayOffset"),
                ("ShotSpeed", "kEntityPlayerShotSpeedOffset"),
                ("Damage", "kEntityPlayerDamageOffset"),
                ("MoveSpeed", "kEntityPlayerMoveSpeedOffset"),
                ("Luck", "kEntityPlayerLuckOffset"),
                ("TearRange", "kEntityPlayerTearRangeOffset"),
        ):
            with self.subTest(field=field):
                self.assertIn(f'"{field}"', body, f"{field} 必须有可写分支")
                self.assertIn(constant, body, f"{field} 必须用具名偏移常量")
        for field in ("Damage", "MoveSpeed", "MaxFireDelay", "ShotSpeed", "Luck", "TearRange"):
            self.assertIn(field, body, f"拒写文案必须列出 {field}")

    def test_shot_speed_constant_has_evidence(self):
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("inline constexpr uintptr_t kEntityPlayerShotSpeedOffset = 0x1838;", constants)
        block = constants[constants.index("// `ShotSpeed`（float，批次 405"):]
        block = block[:block.index("inline constexpr uintptr_t kEntityPlayerShotSpeedOffset")]
        for witness in ("0x279660", "0x43274C"):
            self.assertIn(witness, block, f"`ShotSpeed` 的证据里缺了 {witness}")


if __name__ == "__main__":
    unittest.main()
