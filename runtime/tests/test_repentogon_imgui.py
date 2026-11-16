"""The retained ImGui subset used by Reverie Make Good Omissions is functional."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from . import test_support

RUNTIME = Path(__file__).resolve().parents[1]
SOURCE = RUNTIME / "source"
IMGUI_API = RUNTIME / "src/interfaces/lua/repentogon_imgui_api.cpp"

DRIVER = r'''
#include "interfaces/lua/repentogon_imgui_api.hpp"

extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}

#include <cassert>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <string>

using namespace isaac::runtime;

static std::string captured;

static void Capture(void*, const char* text, float, float, float, const float*) {
    captured.append(text ? text : "");
    captured.push_back('\n');
}

static ImGuiInputFrame Press(ImGuiNavAction action) {
    ImGuiInputFrame frame{};
    switch (action) {
        case ImGuiNavAction::Up: frame.up = true; break;
        case ImGuiNavAction::Down: frame.down = true; break;
        case ImGuiNavAction::Left: frame.left = true; break;
        case ImGuiNavAction::Right: frame.right = true; break;
        case ImGuiNavAction::Accept: frame.accept = true; break;
        case ImGuiNavAction::Back: frame.back = true; break;
        case ImGuiNavAction::PreviousTab: frame.previousTab = true; break;
        case ImGuiNavAction::NextTab: frame.nextTab = true; break;
    }
    return frame;
}

static void Draw() {
    captured.clear();
    const ImGuiDrawHooks hooks{nullptr, &Capture};
    assert(DrawRepentogonImGui(ImGuiViewport{0.0F, 0.0F, 1280.0F, 720.0F}, hooks));
}

static void LuaNumber(lua_State* state, const char* expression) {
    const std::string code = std::string("assert(") + expression + ")";
    if (luaL_dostring(state, code.c_str()) != LUA_OK) {
        std::fprintf(stderr, "%s\n", lua_tostring(state, -1));
        std::abort();
    }
}

int main() {
    auto* state = luaL_newstate();
    assert(state);
    luaL_requiref(state, "_G", luaopen_base, 1);
    lua_pop(state, 1);
    luaL_requiref(state, LUA_TABLIBNAME, luaopen_table, 1);
    lua_pop(state, 1);
    assert(RegisterRepentogonImGuiApi(state) == 0);
    assert(RegisterRepentogonImGuiApi(state) == 0);

    const char* script = R"lua(
state = {
    chance = 20,
    flag = false,
    combo = 0,
    amount = 1.5,
    edits = 0,
    renders = 0,
    clicks = 0,
}

local required = {
    "CreateMenu", "CreateWindow", "LinkWindowToElement",
    "AddElement", "AddTabBar", "AddTab",
    "AddCheckbox", "AddCombobox", "AddSliderInteger", "AddInputFloat",
    "AddButton", "AddCallback", "UpdateData", "SetTooltip", "SetHelpmarker",
    "PushNotification", "Show", "Hide", "IsVisible",
}
for _, name in ipairs(required) do assert(type(ImGui[name]) == "function", name) end
assert(ImGuiElement.MenuItem == 2 and ImGuiElement.SeparatorText == 7)
assert(ImGuiElement.TextWrapped == 9 and ImGuiElement.SameLine == 11)
assert(ImGuiCallback.Clicked == 0 and ImGuiCallback.Edited == 5 and ImGuiCallback.Render == 10)
assert(ImGuiData.Value == 1)
assert(ImGuiNotificationType.ERROR == 3)

ImGui.CreateMenu("mgo", "MGO")
ImGui.AddElement("mgo", "settings", ImGuiElement.MenuItem, "Settings")
ImGui.CreateWindow("settings_window", "MGO Window")
ImGui.LinkWindowToElement("settings_window", "settings")
ImGui.AddTabBar("settings_window", "tabs")
ImGui.AddTab("tabs", "tab_options", "Options")
ImGui.AddTab("tabs", "tab_test", "Test")

ImGui.AddElement("tab_options", "", ImGuiElement.TextWrapped, "Chance")
ImGui.AddSliderInteger("tab_options", "chance", "%", nil, 20, 0, 100)
ImGui.AddCallback("chance", ImGuiCallback.Render, function()
    state.renders = state.renders + 1
    ImGui.UpdateData("chance", ImGuiData.Value, state.chance)
end)
ImGui.AddCallback("chance", ImGuiCallback.Edited, function(value)
    state.chance = value
    state.edits = state.edits + 1
end)
ImGui.SetHelpmarker("chance", "Edit chance")

ImGui.AddCheckbox("tab_options", "flag", "Flag")
ImGui.AddCallback("flag", ImGuiCallback.Edited, function(value)
    state.flag = value
end)
ImGui.AddCombobox("tab_options", "combo", "Mode", function(index)
    state.combo = index
end, {"A", "B", "C"}, 0, false)
ImGui.AddInputFloat("tab_options", "amount", "Amount", function(value)
    state.amount = value
end, 1.5, 0.5, 5)

ImGui.AddButton("tab_test", "apply", "Apply", function()
    state.clicks = state.clicks + 1
end)
)lua";

    if (luaL_dostring(state, script) != LUA_OK) {
        std::fprintf(stderr, "%s\n", lua_tostring(state, -1));
        return 1;
    }

    SetRepentogonImGuiVisible(true);
    assert(RepentogonImGuiVisible());
    Draw();
    assert(captured.find("MGO") != std::string::npos);
    assert(captured.find("Settings") != std::string::npos);
    assert(UpdateRepentogonImGui(Press(ImGuiNavAction::Accept)));

    Draw();
    assert(captured.find("MGO Window") != std::string::npos);
    assert(captured.find("Options") != std::string::npos);
    assert(UpdateRepentogonImGui(Press(ImGuiNavAction::Right)));
    Draw();
    assert(captured.find("Chance: 21") != std::string::npos);
    LuaNumber(state, "state.chance == 21 and state.edits == 1 and state.renders > 0");

    assert(UpdateRepentogonImGui(Press(ImGuiNavAction::Down)));
    assert(UpdateRepentogonImGui(Press(ImGuiNavAction::Accept)));
    Draw();
    assert(captured.find("[x] Flag") != std::string::npos);
    LuaNumber(state, "state.flag == true");

    assert(UpdateRepentogonImGui(Press(ImGuiNavAction::Down)));
    assert(UpdateRepentogonImGui(Press(ImGuiNavAction::Right)));
    Draw();
    assert(captured.find("Mode: B") != std::string::npos);
    LuaNumber(state, "state.combo == 1");

    assert(UpdateRepentogonImGui(Press(ImGuiNavAction::NextTab)));
    Draw();
    assert(captured.find("Test") != std::string::npos);
    assert(UpdateRepentogonImGui(Press(ImGuiNavAction::Accept)));
    LuaNumber(state, "state.clicks == 1");

    if (luaL_dostring(state, "ImGui.UpdateData('chance', ImGuiData.Value, 42)") != LUA_OK) {
        std::fprintf(stderr, "%s\n", lua_tostring(state, -1));
        return 1;
    }
    assert(UpdateRepentogonImGui(Press(ImGuiNavAction::PreviousTab)));
    Draw();
    LuaNumber(state, "state.renders > 0");

    if (luaL_dostring(state, "ImGui.PushNotification('blocked', ImGuiNotificationType.ERROR, 2500)") != LUA_OK) {
        std::fprintf(stderr, "%s\n", lua_tostring(state, -1));
        return 1;
    }
    Draw();
    assert(captured.find("[ERROR] blocked") != std::string::npos);

    if (luaL_dostring(state, "assert(not pcall(function() ImGui.UpdateData('missing', ImGuiData.Value, 1) end))") != LUA_OK) {
        std::fprintf(stderr, "%s\n", lua_tostring(state, -1));
        return 1;
    }

    ResetRepentogonImGui(state);
    lua_close(state);
    return 0;
}
'''


class RepentogonImGuiTests(unittest.TestCase):
    def test_native_action_edges_use_engine_not_lua_menu_ids(self):
        code = r'''
#include "interfaces/lua/repentogon_imgui_api.hpp"
#include <cassert>
using namespace isaac::runtime;
int main(){
 auto up=ImGuiInputFromEngineEdges(1U<<19);assert(up.up&&!up.down);
 auto down=ImGuiInputFromEngineEdges(1U<<20);assert(down.down&&!down.left);
 auto tab=ImGuiInputFromEngineEdges(1U<<21);assert(tab.previousTab&&!tab.right);
 auto right=ImGuiInputFromEngineEdges(1U<<18);assert(right.right);
}
'''
        with tempfile.TemporaryDirectory(prefix="imgui-input-") as folder:
            path=Path(folder);(path/'test.cpp').write_text(code)
            result=subprocess.run(['c++','-std=c++17','-I'+str(RUNTIME/'src'),
                str(path/'test.cpp'),'-o',str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_retained_menu_callbacks_and_navigation(self):
        with tempfile.TemporaryDirectory(prefix="repentogon-imgui-") as folder:
            extra_sources = (
                ()
                if IMGUI_API in test_support.layered_lua_runtime_sources(SOURCE)
                else (IMGUI_API,)
            )
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=DRIVER,
                extra_sources=extra_sources,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
