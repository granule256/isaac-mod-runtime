"""门禁：`blocked_decision` 桶剩下的四条（批次 269，2026-10-02）。

## 这一桶的口径

作业单第〇节第 3 条把"要人为裁定"这一桶**作废**：**自己按 PC 契约与反汇编裁定 —— 要么实现、
要么进"无法恢复"清单**。本批四条全部选择"实现"，但**实现方式分两类**，区别很重要：

| API | 类 | 真值来源 | 判据 |
| --- | --- | --- | --- |
| `Isaac:RenderText` | 复用已有能力 | 与 `Isaac.RenderScaledText`（批次 026）**同一条绘制路径**，只把缩放固定成 `(1,1)` | 宿主上没有屏幕字体 ⇒ **什么都不画、不报错** |
| `Isaac:GetTextWidth` | 复用已有能力 | 同一份运行时默认字体（契约 `Isaac.md:441` 明说与 `RenderText` 同一个字体） | 量不出来 ⇒ `-1`（不是 0、不是 nil） |
| `Room:GetRenderMode` | **`Placeholder`** | **Switch 侧字段未取证** ⇒ 固定给 `RenderMode.RENDER_NORMAL`（`1`） | 返回 `1` 且不报错 |
| `Room:GetRenderSurfaceTopLeft` | **`Placeholder`** | **Switch 侧字段未取证** ⇒ 零向量 | 返回 `Vector(0,0)` 且不报错 |

★ 两条 `Placeholder` 的底线判据是**"给值而不是抛错"**：它们的调用点都在模组回调体里，
方法缺失会报 `attempt to call a nil value` ⇒ **整条回调被摘掉**（本项目最重的一档后果），
而 PC 上这两条根本不会失败。偏移取不到这件事逐条写在 `api_deviation.cpp` 的
`0x04010024` / `0x04010025` 里，**不藏**。

★ 本文件**不钉**"真机上那个渲染模式/表面位置到底是多少"——那要靠真机读数，属未取证，
不是主动取舍（第 11 条纪律：登记进作业单第九节，而不是停工）。
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
ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
FONT_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "font_api.cpp"
DEVIATION = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_deviation.cpp"

#: `(owner, 名字, 域内序号, 契约页:行)`
APIS = (
    ("Isaac", "RenderText", 0x0090, "Isaac.md:561"),
    ("Isaac", "GetTextWidth", 0x0091, "Isaac.md:439"),
    ("Room", "GetRenderMode", 0x0024, "Room.md:468"),
    ("Room", "GetRenderSurfaceTopLeft", 0x0025, "Room.md:478"),
)

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

namespace {

std::vector<unsigned char> g_ModuleBytes;
//: 一个"够大、可读"的假 Room：这几条处理器本身只做 `luaL_checkudata`，不读房间字段，
//: 所以只要有**一个能被 `Game():GetRoom()` 认下来的地址**就够了（与 `test_lua_room_gettype.py`
//: 的 `g_RoomStorage` 同一手法）。
std::uint64_t g_RoomStorage = 0;

void PublishEmptyModule() {
    // 盖住 `g_Game` 的槽：`ResolveRoom()` 会先 `EngineModuleBase() + 那个偏移` 去取槽。
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + 32, 0);
    LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(g_ModuleBytes.data()));
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = &g_RoomStorage;
    return GameRoomObservation::Success;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    PublishEmptyModule();
    LuaRuntime::SetGameBindings(0x1111, 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "room_render") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local room = Game():GetRoom()"
            " print('B269 mode=' .. tostring(room:GetRenderMode()))"
            " local v = room:GetRenderSurfaceTopLeft()"
            " print('B269 surface=' .. tostring(v.X) .. ',' .. tostring(v.Y) .. ',' .. type(v))"
            " print('B269 room_arity=' .. ok(function() return room:GetRenderMode(1) end)"
            "   .. ',' .. ok(function() return room:GetRenderSurfaceTopLeft(1) end))";
    } else if (std::strcmp(scenario, "text") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " print('B269 render_text=' .. ok(function()"
            "   return Isaac.RenderText('hi', 10, 20, 1, 1, 1, 1) end))"
            " print('B269 render_text_arity=' .. ok(function() return Isaac.RenderText('hi') end)"
            "   .. ',' .. ok(function() return Isaac.RenderText({}, 2, 3, 4, 5, 6, 7) end))"
            " print('B269 width=' .. tostring(Isaac.GetTextWidth('hello'))"
            "   .. ',' .. tostring(Isaac.GetTextWidth(42)))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b269.lua");
    static_cast<void>(result);
    return 0;
}
'''


class RenderGlueBatch269Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b269-")
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

    # ---------------------------------------------------------------- 宿主行为

    def test_room_render_placeholders_give_values_instead_of_errors(self):
        """两条 `Placeholder` 的底线：**给得出值、不抛错**。

        `GetRenderMode()` = `1`（`RenderMode.RENDER_NORMAL`）；`GetRenderSurfaceTopLeft()` =
        `Vector(0,0)` 且是 **Vector 对象**（不是 nil —— `nil.X` 会把回调打断）。
        """
        out = self.run_scenario("room_render")
        self.assertIn("B269 mode=1", out)
        self.assertIn("B269 surface=0.0,0.0,userdata", out)

    def test_room_render_placeholders_gate_their_arguments(self):
        """参数闸门：两条都是 0 参方法（`.const`），多给一个参数必须报错。

        ★ 为什么这条不能省：`Room` 是**对象方法**（`room:GetRenderMode()` ⇒ 栈上含 `self`），
        与 `Isaac` 那种全局表（不含 `self`）口径相反 —— 批次 249 就是栽在这一格。
        """
        out = self.run_scenario("room_render")
        self.assertIn("B269 room_arity=false,false", out)

    def test_render_text_degrades_silently_and_get_text_width_gives_minus_one(self):
        """宿主没有屏幕字体 ⇒ `RenderText` **什么都不画、不报错**；`GetTextWidth` 给 `-1`。

        ★ 这两条刻意**都不抛错**（第 11 条纪律）：它们的调用点都在模组回调体里，
        抛错会摘掉整条渲染回调；而 PC 上它们根本不会失败。
        ★ `GetTextWidth(-1)` 而不是 `0`：0 是"这段文字宽 0 像素"这个**有意义的答案**，
        模组会拿它算居中 —— 给 0 会静默把文字摆到错的位置。
        """
        out = self.run_scenario("text")
        self.assertIn("B269 render_text=true", out)
        self.assertIn("B269 width=-1,-1", out)

    def test_render_text_gates_its_arguments_and_keeps_the_lua_coercion(self):
        """参数闸门 + 数字→字符串的强制转换（`luaL_checklstring` 的口径，与 PC 一致）。

        `Isaac.RenderText({}, …)`（表）必须报错；而 `Isaac.GetTextWidth(42)` **不报错** ——
        PC 的绑定层同样走 `luaL_checklstring`，会把数字转成它的文本形式。
        """
        out = self.run_scenario("text")
        self.assertIn("B269 render_text_arity=false,false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_catalog_and_binding_rows_exist(self):
        catalog = CATALOG.read_text(encoding="utf-8")
        body = ISAAC_API.read_text(encoding="utf-8") + REMAINING_API.read_text(encoding="utf-8")
        domain = {"Isaac": 0x0E010000, "Room": 0x04010000}
        for owner, name, index, _page in APIS:
            with self.subTest(name):
                self.assertIn(
                    f'MakeId(ApiDomain::{owner}, 1, 0x{index:04X}), ApiDomain::{owner}, '
                    f'"{owner}", "{name}"',
                    catalog, f"catalog 里没有 {owner}:{name}（域内序号 0x{index:04x}）")
                self.assertRegex(
                    body, rf"\{{\s*(?i:0x{domain[owner] + index:08x}),\s*&\w*{name}\s*\}}",
                    f"绑定表里没有 0x{domain[owner] + index:08X} → {name}")

    def test_contract_pages_are_quoted_in_the_implementation(self):
        body = (ISAAC_API.read_text(encoding="utf-8")
                + REMAINING_API.read_text(encoding="utf-8"))
        for _owner, name, _index, page in APIS:
            with self.subTest(name):
                self.assertIn(page, body, f"{name} 的实现处没有引用契约 {page}")

    def test_render_text_and_get_text_width_share_one_font(self):
        """★ `GetTextWidth` 与 `RenderText` 必须是**同一个字体对象**。

        契约 `Isaac.md:441` 逐字：「based on the "terminus8" font (same font as used in
        Isaac.RenderText())」。判据落在实现上：量宽那条与绘制那条共用 `PushDefaultScreenFont`
        （同一份 registry 缓存），且**都不自己写第二个加载循环**。
        """
        font = FONT_API.read_text(encoding="utf-8")
        self.assertIn("bool MeasureTextWithDefaultFont(", font)
        self.assertIn("bool DrawScaledTextWithDefaultFont(", font)
        self.assertEqual(font.count("PushDefaultScreenFont(state)"), 2,
                         "绘制与量宽必须各自调用一次同一个字体获取助手（多一处 = 出现了第二份字体来源）")
        # 非 ASCII 判据只有一处实现（两处各写一份循环必然漂）。
        self.assertIn("bool TextHasNonAsciiByte(", font)
        self.assertEqual(font.count("TextHasNonAsciiByte(text, length)"), 2)

    def test_placeholders_are_registered_in_the_deviation_ledger(self):
        """★ 两条 `Placeholder` 必须在偏离台账里写清"值从哪来、后果是什么"。

        这是本批**唯一的风险控制**：给常量会让"字段没定位"这件事看起来正常，
        所以真机上必须能查到"这条为什么是常量、偏在哪"。
        """
        deviation = DEVIATION.read_text(encoding="utf-8")
        for entry in ("{0x04010024,", "{0x04010025,"):
            with self.subTest(entry):
                self.assertIn(entry, deviation, f"偏离台账里没有 {entry}")
        # ★ 2026-10-07（批次 388）：期望值 15 → 19。台账里的 Placeholder 条目后来**净 +4**：
        #   * 批次 269（本批，2026-10-02）加了 2 条 —— `0x04010024` / `0x04010025`（13 + 2 = 15）；
        #   * 批次 388（2026-10-07）**还清**了 `EntityPlayer:GetEffects`（`0x0E010047`，原为
        #     「恒返回空表」的 Placeholder）⇒ 少 1 条，但把它**剩下的 5 条方法级占位**单独登记到
        #     表末（`0x0E010106`..`0x0E01010A`：`ClearEffects` / `GetCollectibleEffect` /
        #     `GetNullEffect` / `GetTrinketEffect` / `GetEffectsList`）⇒ 多 5 条 ⇒ 净 +4（15 + 4 = 19）。
        #   证据：`docs/改动日志-20261007.md` 第一节（批次 388）与 `api_deviation.cpp` 里
        #   `0x0E010047` 的销账注释 + 表末那 5 条。
        #   这条断言**保留原保护价值**：它钉的是"台账里 Placeholder 的总数不许在无人记账的情况下漂" ——
        #   每当有批次新增/销账 Placeholder，就必须回来把这格数**连同理由**一起更新（本批就是如此）。
        # ★ 2026-10-07（批次 405）：期望值 19 → **18**。批次 404 **又还清一条** ——
        #   `Isaac.GetTrinketIdByName`（`0x0E01000F`，原为"恒返回 0"的 Placeholder）改成真实现，
        #   `api_deviation.cpp` 里那一条已删（旧文本原样留在注释里）。这是**还账**不是新偏离。
        #   批次 404 的门禁清单没跑到本模块（`--only lua_`），所以这格数当时没跟着动；
        #   批次 405 跑 `--only lua_` 时抓到（18 ≠ 19），按上面那条自我要求补上理由。
        #   证据：`docs/改动日志-20261007.md` 第二十节（批次 404）与 `api_deviation.cpp:660` 附近。
        self.assertEqual(deviation.count("ApiDeviationKind::Placeholder,"), 12,
                         "台账 Placeholder 条目数变了：13（初）+2（批次 269：0x04010024/025）"
                         "+4（批次 388 净增：销 0x0E010047、增 0x0E010106..0A）"
                         "-1（批次 404 销 0x0E01000F：GetTrinketIdByName）= 18")
        for page in ("Room.md:468", "Room.md:478"):
            self.assertIn(page, deviation)

# 2026-10-09：GetName恒nil桩已还清，Placeholder 18→17。

# 2026-10-09：临时效果五条占位还清，17→12；新行为用例独立覆盖真实对象与原生调用。
