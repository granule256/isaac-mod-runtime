"""`Room:IsPositionInRoom(Vector, float)` —— 批次 252 续（"`Vector2 const&` 参数怎么过跳板"）。

## 这个测试解决什么问题

引擎里这几条收的是 **`Vector2 const&`**（mangled 名里的 `RKN4KAGE4Math7Vector2E`）——
也就是说 ABI 上它是一个**指针参数**（走 `x` 寄存器），**不是**按值的 HFA。
所以我们**不需要**动跳板，只要：把 Lua 的 `Vector` 拷进**我们自己栈上的 8 字节槽**，
再把**槽的地址**当作整数参数传出去。

这条链路里**宿主能验**的部分（也正是最容易写错的部分）：

* 参数个数与类型：传非 Vector 必须被挡下（否则引擎会拿一个别的指针当地址读）；
* 槽里的两个 float **就是** Lua 给的那两个值（`3.5` / `-2.25`，特意取"两个不同且非整"的值，
  这样"x/y 写反"或"只拷了一个"都会露馅）；
* `floats[0]` 必须是第二个参数（`7.0`）；
* `integers[1]` 必须是那个**槽的地址**（非 0、且解引用后能读到那两个 float）。

**宿主验不了**的是"引擎真的按这个地址读到了坐标"—— 宿主没有引擎，只能真机。
那一条写在存档 README 的"未验"里，不在这里假装验过。
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness

SOURCE = Path(__file__).resolve().parent.parent / "source"

# 特意选两个"不同、非整、含负数"的值：写反或漏拷都会让断言红。
VEC_X = 3.5
VEC_Y = -2.25
MARGIN = 7.0

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "interfaces/lua/engine_call_trampoline.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 这四个量由宿主桩（`engine_call_trampoline_host_stub.cpp`）**定义** ⇒ 这里只能声明，
// 不能再给初始值（那会变成重复符号，链接期报 4 个 duplicate symbol）。
extern "C" {
extern std::uint32_t g_HostEngineCallTrampolineCalls;
extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;
extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];
extern double g_HostEngineCallTrampolineLastFloats[8];
//: ★★ 批次 338（2026-10-04）：浮点槽按 **f32** 解释的读数（引擎在 `sN` 里读到的就是它）。
extern float g_HostEngineCallTrampolineLastFloat32[8];
}

namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;

void WriteWord(std::vector<unsigned char>& block, std::size_t offset, std::uint64_t value) {
    std::memcpy(block.data() + offset, &value, sizeof(value));
}

void PublishFakeRoom() {
    // ★★ 假模块必须**盖住引擎方法的偏移**：数据行机制在调进去之前会检查
    //    "模块基址 + 偏移"那 4 字节**可读**并且**等于入口指纹**；两者任一不成立就**静默降级**
    //    （跳板一次都不会被调用 ⇒ `calls=0`）。第一版这里只铺了 `kGameOwnerGlobalSlotOffset + 8`
    //    字节，于是 0x464560 处读不到 ⇒ 降级 ⇒ 测试报 `calls=0`（不是崩溃）。
    const std::size_t moduleSize =
        (kGameOwnerGlobalSlotOffset > kRoomIsPositionInRoomOffset ? kGameOwnerGlobalSlotOffset
                                                                 : kRoomIsPositionInRoomOffset) +
        16;
    g_ModuleBytes.assign(moduleSize, 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_RoomBytes.assign(0x40, 0);
    // 把那 4 字节入口指纹写上（数据行里核对的就是它）。
    std::memcpy(g_ModuleBytes.data() + kRoomIsPositionInRoomOffset,
                &kRoomIsPositionInRoomEntryWord, sizeof(kRoomIsPositionInRoomEntryWord));
    WriteWord(g_ModuleBytes, kGameOwnerGlobalSlotOffset,
              reinterpret_cast<std::uintptr_t>(g_OwnerSlotBytes.data()));
    WriteWord(g_OwnerSlotBytes, 0, reinterpret_cast<std::uintptr_t>(g_RoomBytes.data()));
    LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(g_ModuleBytes.data()));
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = g_RoomBytes.data();
    return GameRoomObservation::Success;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    PublishFakeRoom();
    LuaRuntime::SetGameBindings(reinterpret_cast<std::uintptr_t>(g_OwnerSlotBytes.data()), 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "ok") == 0) {
        script =
            "local room = Game():GetRoom()"
            " local r = room:IsPositionInRoom(Vector(VEC_X, VEC_Y), MARGIN)"
            " print('VECARGS done')";
    } else if (std::strcmp(scenario, "bad_argument") == 0) {
        // 传一个**不是 Vector** 的东西：必须被挡下（报 Lua 错），不能把一个别的指针当坐标地址传出去。
        script =
            "local room = Game():GetRoom()"
            " local ok, err = pcall(function() return room:IsPositionInRoom(42, 1) end)"
            " print('VECARGS bad ok='..tostring(ok))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@vecargs.lua");
    static_cast<void>(result);

    if (std::strcmp(scenario, "ok") == 0) {
        // ★ 先判地址非 0 再解引用：接收者没解析到时跳板根本不会被调用，
        //   `integers[1]` 就是 0 —— 直接解引用会**段错误**（把"没调"误报成崩溃）。
        const std::uint64_t slotAddress = g_HostEngineCallTrampolineLastIntegers[1];
        float slotX = 0.0F;
        float slotY = 0.0F;
        if (slotAddress != 0) {
            const auto* slot = reinterpret_cast<const float*>(
                static_cast<std::uintptr_t>(slotAddress));
            slotX = slot[0];
            slotY = slot[1];
        }
        std::printf("VECARGS calls=%u integers1_nonzero=%d floats0=%.6f slot=%.6f,%.6f\n",
                    g_HostEngineCallTrampolineCalls,
                    slotAddress != 0 ? 1 : 0,
                    static_cast<double>(g_HostEngineCallTrampolineLastFloat32[0]), slotX, slotY);
    }
    return 0;
}
'''


class LuaRoomVectorArgumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-vecargs-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS.replace("VEC_X", repr(VEC_X))
                                 .replace("VEC_Y", repr(VEC_Y))
                                 .replace("MARGIN", repr(MARGIN)),
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario: str) -> str:
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_vector_argument_is_copied_into_our_own_slot_and_passed_by_address(self):
        """`Vector2 const&` ⇒ 传指针：槽里必须是 Lua 给的那两个值，且地址非 0。

        三种错法都会被这一条抓住：① 忘了拷（槽里是 0）；② x/y 写反；③ 把 `Vector` 句柄
        或别的指针当参数传（那样 `floats[0]`/`integers[1]` 的形状就不对了）。
        """
        out = self.run_scenario("ok")
        self.assertIn(
            f"VECARGS calls=1 integers1_nonzero=1 floats0={MARGIN:.6f} "
            f"slot={VEC_X:.6f},{VEC_Y:.6f}",
            out,
        )

    def test_a_non_vector_argument_is_rejected(self):
        """传非 Vector 必须被挡下 —— 否则引擎会把一个**别的指针**当地址读坐标。"""
        out = self.run_scenario("bad_argument")
        self.assertIn("VECARGS bad ok=false", out)


if __name__ == "__main__":
    unittest.main()
