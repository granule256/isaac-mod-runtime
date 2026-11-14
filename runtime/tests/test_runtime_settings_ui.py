"""Focused host checks for the title Runtime Settings state and labels."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include "runtime_settings_ui.hpp"
#include "title_notice_state.hpp"

#include <cstdio>
#include <cstring>

using namespace isaac::runtime::title;

namespace {
int failures = 0;
void Check(bool value, const char* label) {
    if (!value) {
        std::printf("FAIL %s\n", label);
        ++failures;
    }
}
void Press(State& state, unsigned key) {
    state.Tick(true, true, false, key);
    state.Tick(true, true, false, 0);
}
}  // namespace

int main() {
    {
        State state;
        Check(!state.BlocksTitleInput(), "idle title does not capture input");
        state.Tick(true, true, false, Right);
        Check(state.focus() == Focus::Notice, "right focuses the announcement entry");
        Check(state.BlocksTitleInput(), "focused announcement blocks title start");
        state.Tick(true, true, false, 0);
        state.Tick(true, true, false, Right);
        Check(state.focus() == Focus::Settings, "right again focuses Runtime Settings");
        state.Tick(true, true, false, 0);
        state.Tick(true, true, false, Confirm);
        Check(state.open(), "confirm opens Runtime Settings");
        Check(state.BlocksTitleInput(), "open modal blocks title start");
        Check(state.ConsumeAction() == Action::OpenSettings, "opening is a one-shot action");
        Check(state.ConsumeAction() == Action::None, "open action is consumed once");
        state.Tick(true, true, false, 0);
        state.Tick(true, true, false, Down);
        Check(state.selected() == Row::Repentogon, "down selects REPENTOGON");
        state.Tick(true, true, false, 0);
        state.Tick(true, true, false, Confirm);
        Check(state.ConsumeAction() == Action::ToggleRepentogon, "confirm toggles selected row");
        state.Tick(true, true, false, Confirm);
        Check(state.ConsumeAction() == Action::None, "held confirm does not repeat");
        state.Tick(true, true, false, 0);
        state.Tick(true, true, false, Back);
        Check(!state.open(), "back closes the modal");
        Check(state.BlocksTitleInput(), "closing frame still captures back");
        state.Tick(true, true, false, 0);
        Check(!state.BlocksTitleInput(), "released back restores title navigation");
        state.Tick(true, true, false, Right);
        Check(state.focus() == Focus::Notice, "focus can be acquired again");
        state.Tick(true, false, false, 0);
        Check(state.focus() == Focus::Notice,
              "focus remains while local availability is waiting");
        state.Tick(true, true, true, 0);
        Check(state.focus() == Focus::None,
              "the mandatory announcement owns Runtime Settings input");
    }
    {
        State state;
        Press(state, Right);
        state.Tick(true, true, false, Confirm);
        Check(state.ConsumeAction() == Action::OpenNotice,
              "confirm on the first entry opens the announcement");
        Check(!state.open(), "announcement is not owned by Runtime Settings");
        state.Tick(true, true, true, 0);
        Check(state.focus() == Focus::None && !state.open(),
              "announcement openness resets the settings focus");
    }
    {
        State state;
        Press(state, Right);
        Press(state, Right);
        Press(state, Confirm);
        Check(state.ConsumeAction() == Action::OpenSettings, "settings open action is one-shot");
        Press(state, Confirm);  // Console toggle
        Check(state.ConsumeAction() == Action::ToggleConsole, "console row toggles first");
        Press(state, Up);
        Press(state, Up);
        Check(state.selected() == Row::Console, "up from top does not leave the two rows");
        state.Tick(false, false, false, Right);
        Check(!state.open() && state.focus() == Focus::None,
              "leaving title fully resets modal and focus");
    }
    {
        SettingView view{};
        view.consoleActive = true;
        view.consoleRequested = true;
        Check(DisplayValueFor(view, Row::Console) == DisplayValue::On,
              "settled console on");
        view.consolePending = true;
        Check(DisplayValueFor(view, Row::Console) == DisplayValue::OnPending,
              "console pending still reports effective on");
        view.consolePending = false;
        view.consoleSaveFailed = true;
        Check(DisplayValueFor(view, Row::Console) == DisplayValue::SaveFailed,
              "console persistence failure has priority");

        SettingView rgon{};
        rgon.repentogonRequested = true;
        rgon.repentogonActive = false;
        rgon.repentogonReloadRequired = true;
        Check(DisplayValueFor(rgon, Row::Repentogon) == DisplayValue::OnReload,
              "requested on with inactive VM is restart required, never active");
        rgon.repentogonReloadRequired = false;
        Check(DisplayValueFor(rgon, Row::Repentogon) == DisplayValue::Unavailable,
              "failed startup is unavailable, not a pending configuration restart");
        rgon.repentogonReloadRequired = true;
        rgon.repentogonActive = true;
        rgon.repentogonRequested = false;
        Check(DisplayValueFor(rgon, Row::Repentogon) == DisplayValue::OffReload,
              "requested off with active VM is restart required");
        rgon.repentogonPending = true;
        Check(DisplayValueFor(rgon, Row::Repentogon) == DisplayValue::OffPending,
              "pending takes precedence over reload while saving");
    }
    Check(std::strcmp(EntryLabel(0), "Runtime Settings") == 0,
          "English entry uses Runtime Settings");
    Check(std::strstr(EntryLabel(0), "Compatibility") == nullptr &&
              std::strstr(EntryLabel(0), "Layer") == nullptr,
          "English entry never uses the compatibility-layer literal");
    Check(std::strcmp(EntryLabel(7), "\u517c\u5bb9\u5c42\u8bbe\u7f6e") == 0,
          "Chinese follows the existing locale wording");
    Check(std::strcmp(ValueLabel(DisplayValue::OnReload, 0), "On - restart required") == 0,
          "reload state is explicit");
    Check(std::strcmp(ValueLabel(DisplayValue::SaveFailed, 0), "Save failed") == 0,
          "save failure is explicit");
    Check(kRuntimeSettingsLayout.rowY[0] < kRuntimeSettingsLayout.rowY[1] &&
              kRuntimeSettingsLayout.titleY < kRuntimeSettingsLayout.rowY[0] &&
              kRuntimeSettingsLayout.rowY[1] < kRuntimeSettingsLayout.footerY,
          "modal layout order is title, Console, REPENTOGON, footer");
    Check(kRuntimeSettingsLayout.paperScale > 0.0F &&
              kRuntimeSettingsLayout.paperScale < 1.0F,
          "settings reuse the notice paper as a smaller modal");
    const float halfPaperHeight = 108.0F * kRuntimeSettingsLayout.paperScale;
    Check(kRuntimeSettingsLayout.titleY > -halfPaperHeight &&
              kRuntimeSettingsLayout.footerY < halfPaperHeight,
          "all modal rows remain inside the scaled notice paper");
    {
        isaac::runtime::notice::State notice;
        notice.SetSeenVersion(true);
        notice.Tick(0, true, true, 3);
        notice.Tick(Right, true, true, 3);
        notice.Tick(0, true, true, 3);
        notice.Tick(Right, true, true, 3);
        Check(notice.Settings().focus() == Focus::Settings,
              "title notice state owns the second entry focus");
        notice.Tick(0, true, true, 3);
        notice.Tick(Confirm, true, true, 3);
        Check(notice.Settings().open(), "notice state opens the Runtime Settings modal");
        Check(notice.Settings().ConsumeAction() == Action::OpenSettings,
              "the native owner sees the open action once");
        notice.Tick(0, true, true, 3);
        notice.Tick(Down, true, true, 3);
        notice.Tick(0, true, true, 3);
        notice.Tick(Confirm, true, true, 3);
        Check(notice.Settings().ConsumeAction() == Action::ToggleRepentogon,
              "modal toggles are exposed to the native adapter");
        Check(notice.BlocksTitleConfirm(),
              "Runtime Settings remains inside the announcement authority gate");
    }
    return failures == 0 ? 0 : 1;
}
'''


class RuntimeSettingsUiTests(unittest.TestCase):
    def test_state_capture_status_and_labels(self):
        compiler = next((shutil.which(name) for name in ("c++", "clang++", "g++")
                         if shutil.which(name)), None)
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="runtime-settings-ui-") as tmp:
            root = Path(tmp)
            (root / "test.cpp").write_text(HARNESS)
            built = subprocess.run(
                [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                 "-I", str(ROOT / "runtime/source"), str(root / "test.cpp"),
                 "-o", str(root / "test")],
                capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            ran = subprocess.run([str(root / "test")], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)


if __name__ == "__main__":
    unittest.main()
