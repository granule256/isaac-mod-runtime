"""宿主门禁：`Room` 四条**位置类**方法的**参数闸门与失败降级**（批次 259，2026-10-01）。

## 这个测试能在宿主上验什么

四条方法与批次 249 的三条一样是**手写处理器**（返回 `Vector2`，通用跳板只支持标量返回）。
宿主上没有引擎，所以"引擎有没有按我们交的指针读到坐标"**验不了** —— 那条只能真机。

但这条链路里**宿主能验、也最容易写错**的那一段是可验的：**参数闸门**。

做法：故意在假模块里**不写入口指纹**（`EngineEntryWordMatches` 必然失败）⇒ 四条处理器一律走
"降级"分支，**永远不会跳到引擎**（假模块的字节是 0，跳进去就是 UDF 崩溃 ⇒ 这个测试只要不崩，
就反证了降级路径确实生效）。于是在同一套 harness 里可以安全地验：

* **参数个数**：`GetClampedPosition(Vector)` 少一个 ⇒ 报错；`FindFreeTilePosition(Vector,f,f)`
  多一个 ⇒ 报错；`FindFreePickupSpawnPosition()` 少到 0 个 ⇒ 报错；多到 5 个 ⇒ 报错；
* **尾部可省**：`FindFreePickupSpawnPosition(Vector)` 与 `(Vector,f,bool)` 与 `(Vector,f,bool,bool)`
  **都必须能过**（契约 `Room.md:78` 三个缺省值；语料里三种实参都有）；
* **参数类型**：`Pos` 只收 `Vector` 句柄 —— 传数字 / `nil` / 字符串必须报错
  （传别的指针会让引擎把别处内存当坐标读，**不报错**，比降级严重得多）；
* **失败降级**：拿不到引擎方法时压 `Vector(0,0)`、**不压 nil、不报错**。

## 宿主验不了什么（别把这里的绿当成"值对"）

引擎真的被调到之后返回什么坐标、`GetClampedPosition` 的四个 `Margin` 引擎怎么用 —— 都只能真机。
存档 README 的"未验"一节列了它们。
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

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "interfaces/lua/engine_call_trampoline.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;

void WriteWord(std::vector<unsigned char>& block, std::size_t offset, std::uint64_t value) {
    std::memcpy(block.data() + offset, &value, sizeof(value));
}

void PublishFakeModuleWithoutEntryWords() {
    // ★ 模块要**盖住所有会被问到的偏移**（否则 `IsEngineMemoryReadable` 先失败，虽然结论一样，
    //   但那样就分不清"读不到"与"指纹不对"了）。这里铺到最大的那条偏移 + 16 字节。
    const std::size_t moduleSize = kRoomFindFreeTilePositionOffset + 16;
    g_ModuleBytes.assign(moduleSize, 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_RoomBytes.assign(0x40, 0);
    // ★★ **故意不写任何入口指纹** ⇒ `ResolveRoomVectorMethod` / `CallRoomDoorSlotPosition`
    //    一律在 `EngineEntryWordMatches` 处失败 ⇒ 四条处理器全部走降级分支，不会跳到引擎。
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
    PublishFakeModuleWithoutEntryWords();
    LuaRuntime::SetGameBindings(reinterpret_cast<std::uintptr_t>(g_OwnerSlotBytes.data()), 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "ok") == 0) {
        // 六次调用全部走"合法参数"路径 ⇒ 全部应降级成 Vector(0,0)，且**一次都不许报错**。
        script =
            "local room = Game():GetRoom()"
            " local function show(v) return type(v)..':'..string.format('%.1f', v.X)"
            "                             ..','..string.format('%.1f', v.Y) end"
            " local a = room:FindFreePickupSpawnPosition(Vector(120, 240), 0, true, false)"
            " local b = room:FindFreePickupSpawnPosition(Vector(120, 240))"
            " local c = room:FindFreePickupSpawnPosition(Vector(120, 240), 40, true)"
            " local d = room:GetClampedPosition(Vector(120, 240), 16)"
            " local e = room:FindFreeTilePosition(Vector(120, 240), 0.5)"
            " local f = room:GetDoorSlotPosition(3)"
            " print('POSARGS ok='..show(a)..'|'..show(b)..'|'..show(c))"
            " print('POSARGS ok2='..show(d)..'|'..show(e)..'|'..show(f))";
    } else if (std::strcmp(scenario, "arity") == 0) {
        script =
            "local room = Game():GetRoom()"
            " local function ok(f) return tostring(select(1, pcall(f))) end"
            " local a = ok(function() return room:GetClampedPosition(Vector(1, 2)) end)"
            " local b = ok(function() return room:FindFreeTilePosition(Vector(1, 2), 1, 2) end)"
            " local c = ok(function() return room:FindFreePickupSpawnPosition() end)"
            " local d = ok(function() return room:GetDoorSlotPosition() end)"
            " local e = ok(function()"
            "     return room:FindFreePickupSpawnPosition(Vector(1, 2), 0, true, false, 1) end)"
            " print('POSARGS arity='..a..','..b..','..c..','..d..','..e)";
    } else if (std::strcmp(scenario, "bad_argument") == 0) {
        script =
            "local room = Game():GetRoom()"
            " local function ok(f) return tostring(select(1, pcall(f))) end"
            " local a = ok(function() return room:GetClampedPosition(42, 1) end)"
            " local b = ok(function() return room:FindFreeTilePosition(nil, 1) end)"
            " local c = ok(function() return room:FindFreePickupSpawnPosition('x') end)"
            " local d = ok(function() return room:GetDoorSlotPosition(Vector(1, 2)) end)"
            " print('POSARGS bad='..a..','..b..','..c..','..d)";
    } else if (std::strcmp(scenario, "convention") == 0) {
        // ★★ 这一格是**批次 249 那个真实缺陷的回归闸门**：手写处理器收到的实参个数
        //    必须按"栈上含 `self`"算（`AttachOwnerMethods` 挂的是普通 `lua_CFunction`）。
        //    249 的三条写成了不含 `self` ⇒ 每一句都抛错。四条新方法 + 249 的三条一起钉。
        script =
            "local room = Game():GetRoom()"
            " local function ok(f) return tostring(select(1, pcall(f))) end"
            " print('POSARGS conv='..ok(function() return room:GetCenterPos() end)"
            "   ..','..ok(function() return room:GetGridPosition(0) end)"
            "   ..','..ok(function() return room:GetRandomPosition(0) end))"
            " print('POSARGS conv2='..ok(function()"
            "     return room:FindFreePickupSpawnPosition(Vector(1, 2)) end)"
            "   ..','..ok(function() return room:GetClampedPosition(Vector(1, 2), 0) end)"
            "   ..','..ok(function() return room:FindFreeTilePosition(Vector(1, 2), 0) end)"
            "   ..','..ok(function() return room:GetDoorSlotPosition(0) end))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@posargs.lua");
    static_cast<void>(result);
    return 0;
}
'''


class LuaRoomPositionFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-posargs-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario: str) -> str:
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_every_method_degrades_to_a_zero_vector_without_erroring(self):
        """六次合法调用都必须给出 `Vector(0,0)`（不是 nil、不报错）。

        ★ 同时这也是"没有跳到引擎"的反证：假模块里没有入口指纹，一旦哪条路径漏了那道校验，
        它就会跳进全是 0 的假模块字节（UDF）把进程打崩 —— 这个用例返回码就不是 0 了。
        """
        out = self.run_scenario("ok")
        self.assertIn(
            "POSARGS ok=userdata:0.0,0.0|userdata:0.0,0.0|userdata:0.0,0.0", out)
        self.assertIn(
            "POSARGS ok2=userdata:0.0,0.0|userdata:0.0,0.0|userdata:0.0,0.0", out)

    def test_arity_is_enforced_including_the_optional_tail(self):
        """少参数 / 多参数都要报错；`FindFreePickupSpawnPosition` 的 1..4 个必须都能过。

        ★ 这条**只验拒绝**（5 个场景全 false）。"1 个参数能过"那半条由 `ok` 场景里
        `FindFreePickupSpawnPosition(Vector)` / `(Vector,40,true)` 两次成功调用证明。
        """
        out = self.run_scenario("arity")
        self.assertIn("POSARGS arity=false,false,false,false,false", out)

    def test_non_vector_position_and_non_integer_slot_are_rejected(self):
        """`Pos` 只收 Vector 句柄；`Slot` 只收整数 —— 传别的类型必须报错。"""
        out = self.run_scenario("bad_argument")
        self.assertIn("POSARGS bad=false,false,false,false", out)

    def test_arguments_exclude_self_for_every_room_vector_method(self):
        """★★ 回归闸门：手写处理器的**参数个数含 `self`**（方法调用栈上 `[1]` 就是房间句柄）。

        批次 249 的三条（`GetCenterPos` / `GetGridPosition` / `GetRandomPosition`）把这件事写错了
        （按"不含 `self`"检查）⇒ 模组每一次调用都拿到 Lua 错误 —— 而一条 Lua 错误会把**整条模组
        回调**摘掉，这是本项目最重的一档后果。批次 259 修掉它们，并用这一格把规矩钉住：
        七条方法**都必须能跑通**（它们都会降级成 `Vector(0,0)`，不会因为参数个数被挡）。
        """
        out = self.run_scenario("convention")
        self.assertIn("POSARGS conv=true,true,true", out)
        self.assertIn("POSARGS conv2=true,true,true,true", out)


if __name__ == "__main__":
    unittest.main()
