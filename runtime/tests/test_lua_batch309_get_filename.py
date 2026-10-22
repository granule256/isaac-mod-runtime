"""门禁：`Sprite:GetFilename()`（批次 309，2026-10-03）—— 读 `Sprite + 0x08` 那个 libc++ `std::string`。

## 这一条是什么

| API | 契约 | 引擎侧 | 语料调用点 |
| --- | --- | --- | --- |
| `Sprite:GetFilename()` | `Sprite.md:68/70`（`:79` 的例子给出返回值形如 `gfx/001.000_Player.anm2`） | `Sprite + kSpriteFilenameOffset`（`+0x08`）的 libc++ `std::string` | 4 |

★ 谁在调：`BOIStageAPI15` 拿它当**字典键**（`StageAPI.NonOverrideTrapdoors[grid:GetSprite():GetFilename()]`）
与 `== ""` 判断、`ChallengeAPI` 把它喂回 `Sprite:Load(path, true)`。

## 凭什么说 `+0x08` 是文件名（两处具名证据）

* **写入口** `Sprite::LoadAnimationsFile(char const*, char const*) @ 0x4A48B4`：
  `add x0, x0, #0x8` + `bl std::string::assign(char const*)` ⇒ 传进来的路径**整串** assign 进 `this+0x08`
  （紧接着 `strb w8(1), [x19, #0x48]` 是旁边那个"已加载"字节、`mov w0,#1` 返回 true）；
* **构造函数** `Sprite::Sprite() @ 0x4A4658`：`ldr x8,[…+0x390]`（`_ZTVSprite`）+ `add x8,x8,#0x10`
  + `stp x8, xzr, [x0]` ⇒ `[this+0]=vptr`、**`[this+8]=0`**（空串）—— 与"没加载过的 Sprite，
  `GetFilename()` 答 `""`"一致（语料正是拿 `== ""` 判"还没加载"）。

★ PC 侧的绑定 `GetFilename` 在 `isaac-ng.exe` 的名字表里**没有被引用**（`push 引用 0 处`）⇒ PC 的偏移读不到；
本条的判定完全靠 Switch 侧这两处具名函数。

## 宿主验到了什么、没验到什么

* **验到**：
  - **短串**（libc++ SSO 内联）与**长串**（堆上指针）**两条路径都能读**：
    夹具用 `Sprite()` 的构造函数桩把 SSO 头按两种布局分别写进 `+0x08`；
  - ★★ **`GetFilename()` 的返回值必须与写进去的**逐字节**相同**（用它当字典键/与 `""` 比较）；
  - ★ **空串 ⇒ 答 `""`（不是 nil）**（构造函数把 `+0x08` 清 0 的那一支）；
  - ★ **超长（超过我们的缓冲上限 256）⇒ 答 `""`，而不是被砍掉尾巴的错名**
    —— 静默截断会给出"看着像真的错键"，模组拿它查字典会**静默走错分支**；
  - **参数闸门**：多给实参报错、消息里现拼出 `Sprite:GetFilename`；接收者不是 Sprite ⇒ 报错。
* **没验**：真机上 `+0x08` 就是那个文件名（宿主里夹具与实现引用同一个常量）⇒ 真机项 = 作业单 **V59**。
"""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness

SOURCE = Path(__file__).resolve().parent.parent / "source"
ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
SPRITE_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "sprite_api.cpp"
SPRITE_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "sprite_api.hpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

#: 域内序号 / 绑定行 id。
API_INDEX = 0x001F
BINDING_ID = 0x0D01001F
OFFSET_NAME = "kSpriteFilenameOffset"
CONTRACT = "Sprite.md:68/70"

#: 夹具里三种写法的内容。
SHORT_TEXT = "gfx/rock.anm2"                       # 13 字符 ⇒ 走 SSO 内联那条
LONG_TEXT = "gfx/001.000_Player.anm2"              # 契约例子（23 字符）⇒ 走堆上指针那条
HUGE_LENGTH = 300                                  # 超过我们的 256 上限 ⇒ 应当答空串


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

// 夹具：`Sprite()` 在宿主上会走我们注入的 `ctor` 桩 —— 那个桩拿到的正是运行时刚分配出来的
// 那块内存（`kSpriteObjectSize + slack`），所以"构造时 `+0x08` 是什么"由**桩**决定，
// 与真机上 `Sprite::Sprite()` 的 `stp x8, xzr, [x0]` 对应。
//   * 短串：首字节 = 长度 << 1、内容从 `+0x1` 起；
//   * 长串：首字节 bit0 = 1、长度在 `+0x8`、数据指针在 `+0x10`；
//   * 空串：首字节 = 0。
namespace {

std::vector<unsigned char> g_HeapText;   // 长串的数据放在这里（模拟引擎堆）
std::string g_Text;
int g_Form = 0;                          // 0 = 空串，1 = 短串，2 = 长串，3 = 超长长串

void WriteFilenameInto(void* self) {
    auto* base = static_cast<unsigned char*>(self) + kSpriteFilenameOffset;
    std::memset(base, 0, 24);
    if (g_Form == 0) {
        return;                                     // 首字节 0 = 空串
    }
    if (g_Form == 1) {
        base[0] = static_cast<unsigned char>(g_Text.size() << 1);
        std::memcpy(base + 1, g_Text.data(), g_Text.size());
        return;
    }
    //: 长串：length 只写"声明长度"（超长那一档故意写得比实际数据长 —— 这正是要验的：
    //: 我们**不许**按声明长度硬读、也不许截断）。
    const std::size_t declared = (g_Form == 3) ? HUGE_LENGTH : g_Text.size();
    std::uint64_t length = declared;
    std::memcpy(base + 8, &length, sizeof(length));
    //: ★ 长串标志**必须先置**：第一版把它写在两个分支的**后面**，超长那一档提前 return
    //:   ⇒ 首字节仍是 0（被当成空短串）⇒ 那一路其实没被走到，用例成了"空过的"。
    //:   （这个 bug 是被"能红验证"当场抓出来的：去掉长度校验后用例**没红** ⇒ 说明它没在测那件事。）
    base[0] = 0x01;
    if (g_Form == 3) {
        g_HeapText.assign(declared, 'x');
        g_HeapText[declared - 1] = '\0';
        const std::uintptr_t pointer = reinterpret_cast<std::uintptr_t>(g_HeapText.data());
        std::memcpy(base + 0x10, &pointer, sizeof(pointer));
        return;
    }
    const std::uintptr_t pointer = reinterpret_cast<std::uintptr_t>(g_Text.data());
    std::memcpy(base + 0x10, &pointer, sizeof(pointer));
}

void FakeCtor(void* self) { WriteFilenameInto(self); }
void FakeDestructor(void*) {}
void FakeOperatorDelete(void*) {}

}  // namespace

// 共享默认桩（本场景只关心 Sprite，其余一律"读不到"）。
GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {
    return GameIsPausedObservation::ThunkUnavailable;
}
GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t, std::uint32_t*) {
    return GameLevelStageObservation::GameUnreadable;
}
GameIsGreedModeObservation ObserveGameIsGreedMode(uintptr_t, uintptr_t) {
    return GameIsGreedModeObservation::MethodUnavailable;
}
GameIsAscentObservation ObserveLevelIsAscent(uintptr_t, uintptr_t) {
    return GameIsAscentObservation::MethodUnavailable;
}
GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**) {
    return GameItemPoolObservation::GameUnreadable;
}
GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room != nullptr) *room = nullptr;
    return GameRoomObservation::RoomUnreadable;
}
GameRoomObservation ReadCurrentGameRoomType(uintptr_t, std::uint32_t*) {
    return GameRoomObservation::RoomUnreadable;
}

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2) return 90;
    const char* scenario = argv[1];

    if (std::strcmp(scenario, "empty") == 0) {
        g_Form = 0;
    } else if (std::strcmp(scenario, "short") == 0) {
        g_Form = 1; g_Text = SHORT_TEXT_VALUE;
    } else if (std::strcmp(scenario, "long") == 0) {
        g_Form = 2; g_Text = LONG_TEXT_VALUE;
    } else if (std::strcmp(scenario, "huge") == 0) {
        g_Form = 3; g_Text = "x";
    } else if (std::strcmp(scenario, "args") == 0 || std::strcmp(scenario, "badrecv") == 0) {
        g_Form = 2; g_Text = LONG_TEXT_VALUE;
    } else {
        return 91;
    }

    LuaRuntime::LuaSpriteBindings bindings{};
    bindings.ctor = &FakeCtor;
    bindings.destructor_ = &FakeDestructor;
    bindings.gameOperatorDelete = &FakeOperatorDelete;
    LuaRuntime::SetSpriteBindings(bindings);

    static const char* kRead =
        "local s = Sprite()"
        " print('B309 kind=' .. type(s) .. ',' .. type(s.GetFilename))"
        " local name = s:GetFilename()"
        " print('B309 name=' .. tostring(name) .. ' t=' .. type(name) .. ' len=' .. tostring(#name))";
    static const char* kArgs =
        "local s = Sprite()"
        " local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function msg(f) return tostring(select(2, pcall(f))) end"
        " print('B309 extra=' .. ok(function() return s:GetFilename(1) end))"
        " print('B309 extramsg=' .. msg(function() return s:GetFilename(1) end))"
        " print('B309 okone=' .. ok(function() return s:GetFilename() end))";
    static const char* kBadRecv =
        "local s = Sprite()"
        " local f = s.GetFilename"
        " local function ok(g) return tostring(select(1, pcall(g))) end"
        " local function msg(g) return tostring(select(2, pcall(g))) end"
        " print('B309 table=' .. ok(function() return f({}) end))"
        " print('B309 tablemsg=' .. msg(function() return f({}) end))";

    const char* script = nullptr;
    if (std::strcmp(scenario, "args") == 0) {
        script = kArgs;
    } else if (std::strcmp(scenario, "badrecv") == 0) {
        script = kBadRecv;
    } else {
        script = kRead;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b309.lua");
    static_cast<void>(result);
    return 0;
}
'''
HARNESS = (HARNESS
           .replace("SHORT_TEXT_VALUE", '"' + SHORT_TEXT + '"')
           .replace("LONG_TEXT_VALUE", '"' + LONG_TEXT + '"')
           .replace("HUGE_LENGTH", str(HUGE_LENGTH)))


class SpriteGetFilenameBatch309Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b309-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario):
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    @staticmethod
    def value(out, label):
        match = re.search(rf"^{re.escape(label)}=(\S+)$", out, re.M)
        if match is None:
            raise AssertionError(f"输出里没有 {label} 那一行：\n{out}")
        return match.group(1)

    @staticmethod
    def read_name(out):
        """从 `B309 name=<串> t=<type> len=<n>` 那一行里取三段（串本身可能含空格）。"""
        match = re.search(r"^B309 name=(.*) t=(\S+) len=(\S+)$", out, re.M)
        if match is None:
            raise AssertionError(f"输出里没有 B309 name 那一行：\n{out}")
        return match.group(1), match.group(2), match.group(3)

    # ---------------------------------------------------------------- 行为（宿主）

    def test_short_string_is_read_verbatim(self):
        """★ libc++ 的**内联（短串）**布局：首字节 = 长度 << 1、内容从 `+0x1` 起。"""
        out = self.run_scenario("short")
        self.assertIn("B309 kind=userdata,function", out)
        name, kind, length = self.read_name(out)
        self.assertEqual(name, SHORT_TEXT)
        self.assertEqual(kind, "string")
        self.assertEqual(length, str(len(SHORT_TEXT)))

    def test_long_string_is_read_verbatim(self):
        """★ **长串**布局：首字节 bit0 = 1、长度在 `+0x8`、数据指针在 `+0x10`。

        ★ 用契约 `Sprite.md:79` 那个例子（`gfx/001.000_Player.anm2`，23 字符 ⇒ 超出 libc++ 的内联容量）
        —— 语料里文件名正是这么长。
        """
        out = self.run_scenario("long")
        name, kind, length = self.read_name(out)
        self.assertEqual(name, LONG_TEXT)
        self.assertEqual(kind, "string")
        self.assertEqual(length, str(len(LONG_TEXT)))

    def test_empty_string_stays_empty(self):
        """★★ 没加载过（构造函数把 `+0x08` 清 0）⇒ 答 **`""`**，**不是 nil**。

        ★ 语料 `customgrids.lua:547` 正是拿 `sprite:GetFilename() == ""` 判"还没加载"、
        `callbacks.lua:292` 拿它当字典键（`nil` 会让 `t[nil]` 直接报错、摘掉整条回调）。
        """
        out = self.run_scenario("empty")
        name, kind, length = self.read_name(out)
        self.assertEqual((name, kind, length), ("", "string", "0"))

    def test_over_long_name_is_empty_not_truncated(self):
        """★★ 声明长度超过我们的缓冲上限（256）⇒ 答 **`""`**，**不许**答一个被砍掉尾巴的名字。

        ★ 理由：截断出来的文件名"看着像真的"，模组拿它查字典会**静默走错分支** ——
        本项目反复记的"看起来像真值的错值"那一类，比"读不到"危险得多。
        """
        out = self.run_scenario("huge")
        name, kind, length = self.read_name(out)
        self.assertEqual((name, kind, length), ("", "string", "0"),
                         "超长的名字必须答空串，不许答被截断的错名")

    def test_argument_gate_and_bad_receiver(self):
        """参数闸门：只收接收者；接收者不是 `Sprite` ⇒ 报错。"""
        out = self.run_scenario("args")
        self.assertIn("B309 extra=false", out)
        self.assertIn("Sprite:GetFilename accepts no arguments", out)
        self.assertIn("B309 okone=true", out)

        out = self.run_scenario("badrecv")
        self.assertIn("B309 table=false", out)
        #: 消息里有空格 ⇒ 不能按 `\S+` 那套取；直接找特征串。
        self.assertIn("IsaacRuntime.Sprite expected", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 绑定行 / 契约引用 / 偏移常量字面值 / 复用既有的串读取 / 不静默截断。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        sprite = SPRITE_API.read_text(encoding="utf-8")
        header = SPRITE_HEADER.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        self.assertIn(
            f'MakeId(ApiDomain::Sprite, 1, 0x{API_INDEX:04X}), ApiDomain::Sprite, "Sprite", '
            f'"GetFilename"',
            catalog, "目录里没有 Sprite:GetFilename")
        self.assertIn(CONTRACT, catalog, f"目录行的注释里没有引用契约 {CONTRACT}")
        self.assertIn(f"{{0x{BINDING_ID:08X}, &SpriteGetFilename}}", sprite,
                      f"绑定表里没有 0x{BINDING_ID:08X} → SpriteGetFilename")
        #: 声明在**头文件**里（与 `SpriteGetAnimation` 同一条处理：定义在命名空间作用域）。
        self.assertIn("int SpriteGetFilename(lua_State* state);", header)

        #: ★ 复用既有的 libc++ 串读取（不许在本条里再抄一遍 SSO 判断）。
        block = sprite[sprite.index("int SpriteGetFilename(lua_State* state) {"):]
        block = block[:block.index("\n}\n")]
        self.assertIn("ReadLibcxxStringAt", block, "必须复用既有的 SSO 串读取")
        self.assertIn(OFFSET_NAME, block, "必须读那个具名偏移常量")
        self.assertNotIn(">> 1", block, "不许在本条里自己解 SSO 头")
        #: 读不到 / 空串 ⇒ 压空串（不是 nil）。
        self.assertIn('lua_pushliteral(state, "")', block)

        #: ★ 偏移常量写死 + 两处具名证据留在常量段里。
        self.assertRegex(constants, rf"inline constexpr uintptr_t {OFFSET_NAME}\s*=\s*0x08;")
        self.assertIn("0x4A48B4", constants, "取证里必须留下 `LoadAnimationsFile` 的地址")
        self.assertIn("std::string::assign", constants, "取证里必须留下 assign 那一句")
        self.assertIn("0x4A4658", constants, "取证里必须留下构造函数的地址")

        #: ★★ 上限由调用方给 + **长度校验**（防静默截断）—— 这两句都在共享读取函数里。
        shared = sprite[sprite.index("bool ReadLibcxxStringAt("):]
        shared = shared[:shared.index("\n}\n")]
        self.assertIn("declared", shared, "共享读取函数必须做声明长度校验")
        self.assertIn("capacity - 1", shared, "上限必须由调用方给")
        self.assertNotIn("kAnimationNameCapacity ?", shared,
                         "不该再用动画名那一档上限去夹文件名")


if __name__ == "__main__":
    unittest.main()
