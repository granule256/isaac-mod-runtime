#pragma once

#include <cstdint>

namespace isaac::runtime::title {

enum Key : unsigned {
    Confirm = 1U << 0,
    Back = 1U << 1,
    Left = 1U << 2,
    Right = 1U << 3,
    Up = 1U << 4,
    Down = 1U << 5,
};

enum class Focus : std::uint8_t { None, Notice, Settings };
enum class Row : std::uint8_t { Console, Repentogon, Count };
enum class Action : std::uint8_t {
    None,
    OpenNotice,
    OpenSettings,
    ToggleConsole,
    ToggleRepentogon,
};

// The title screen owns both entries and their single modal. Input is edge based:
// callers pass the held-key mask from the same native action query used by the
// announcement, and one unopened key press can perform at most one action.
struct State {
    void Reset(unsigned keys = 0) noexcept {
        focus_ = Focus::None;
        row_ = Row::Console;
        action_ = Action::None;
        open_ = false;
        blocks_ = false;
        restoreFocus_ = false;
        restoreFocusTicks_ = 0;
        lastKeys_ = keys;
    }

    void ReturnFromNotice(unsigned keys) noexcept {
        Reset(keys);
        focus_ = Focus::Notice;
        blocks_ = true;
    }

    void Tick(bool title, bool available, bool announcementOpen, unsigned keys) noexcept {
        const unsigned pressed = keys & ~lastKeys_;
        lastKeys_ = keys;
        if (!title) {
            if (restoreFocus_ && restoreFocusTicks_ != 0) {
                --restoreFocusTicks_;
                blocks_ = true;
                return;
            }
            Reset(keys);
            return;
        }
        if (announcementOpen) {
            restoreFocus_ = false;
            focus_ = Focus::None;
            open_ = false;
            blocks_ = true;
            return;
        }
        if (restoreFocus_) {
            blocks_ = true;
            if (available && (keys & Back) == 0) {
                focus_ = Focus::Settings;
                restoreFocus_ = false;
                restoreFocusTicks_ = 0;
            } else if (restoreFocusTicks_ && --restoreFocusTicks_ == 0) {
                restoreFocus_ = false;
                focus_ = Focus::None;
            }
            return;
        }
        if (!available) {
            blocks_ = focus_ != Focus::None || open_;
            return;
        }
        if (open_) {
            blocks_ = true;
            if (pressed & Back) {
                open_ = false;
                focus_ = Focus::None;
                restoreFocus_ = true;
                restoreFocusTicks_ = 120;
                return;
            }
            if (pressed & Up) {
                row_ = Row::Console;
            } else if (pressed & Down) {
                row_ = Row::Repentogon;
            } else if (pressed & Confirm) {
                action_ = row_ == Row::Console ? Action::ToggleConsole : Action::ToggleRepentogon;
            }
            return;
        }

        if (focus_ == Focus::None) {
            if (pressed & Up) focus_ = Focus::Settings;
            else if (pressed & (Right | Down)) focus_ = Focus::Notice;
        } else if (focus_ == Focus::Notice) {
            if (pressed & Confirm) {
                action_ = Action::OpenNotice;
            } else if (pressed & Up) {
                focus_ = Focus::Settings;
            } else if (pressed & (Left | Right | Down | Back)) {
                focus_ = Focus::None;
            }
        } else {
            if (pressed & Confirm) {
                open_ = true;
                action_ = Action::OpenSettings;
            } else if (pressed & Down) {
                focus_ = Focus::Notice;
            } else if (pressed & (Left | Right | Up | Back)) {
                focus_ = Focus::None;
            }
        }
        blocks_ = focus_ != Focus::None || open_;
    }

    [[nodiscard]] Action ConsumeAction() noexcept {
        const Action action = action_;
        action_ = Action::None;
        return action;
    }
    [[nodiscard]] Action PeekAction() const noexcept { return action_; }
    [[nodiscard]] Focus focus() const noexcept { return focus_; }
    [[nodiscard]] Row selected() const noexcept { return row_; }
    [[nodiscard]] bool open() const noexcept { return open_; }
    [[nodiscard]] bool BlocksTitleInput() const noexcept { return blocks_; }

private:
    Focus focus_{Focus::None};
    Row row_{Row::Console};
    Action action_{Action::None};
    bool open_{};
    bool blocks_{};
    bool restoreFocus_{};
    unsigned restoreFocusTicks_{};
    unsigned lastKeys_{};
};

struct SettingView {
    bool consoleRequested{};
    bool consoleActive{};
    bool consolePending{};
    bool consoleSaveFailed{};
    bool repentogonRequested{};
    bool repentogonActive{};
    bool repentogonPending{};
    bool repentogonSaveFailed{};
    bool repentogonReloadRequired{};
};

enum class DisplayValue : std::uint8_t {
    On,
    Off,
    OnPending,
    OffPending,
    OnReload,
    OffReload,
    SaveFailed,
    Unavailable,
};

[[nodiscard]] inline DisplayValue DisplayValueFor(const SettingView& view, Row row) noexcept {
    const bool requested =
        row == Row::Console ? view.consoleRequested : view.repentogonRequested;
    const bool active = row == Row::Console ? view.consoleActive : view.repentogonActive;
    const bool pending = row == Row::Console ? view.consolePending : view.repentogonPending;
    const bool failed =
        row == Row::Console ? view.consoleSaveFailed : view.repentogonSaveFailed;
    const bool reload = row == Row::Repentogon && view.repentogonReloadRequired;
    if (failed) return DisplayValue::SaveFailed;
    if (pending) return requested ? DisplayValue::OnPending : DisplayValue::OffPending;
    if (reload) return requested ? DisplayValue::OnReload : DisplayValue::OffReload;
    if (row == Row::Repentogon && requested != active) return DisplayValue::Unavailable;
    return active ? DisplayValue::On : DisplayValue::Off;
}

[[nodiscard]] inline const char* EntryLabel(unsigned language) noexcept {
    switch (language) {
    case 1: return "Laufzeit-Einstellungen";
    case 2: return "Ajustes de ejecución";
    case 3: return "Paramètres d’exécution";
    case 4: return "実行環境設定";
    case 5: return "런타임 설정";
    case 6: return "Настройки среды";
    case 7: return "兼容层设置";
    default: return "Runtime Settings";
    }
}

[[nodiscard]] inline const char* FooterLabel(unsigned language) noexcept {
    switch (language) {
    case 1: return "A: umschalten  B: schliessen";
    case 2: return "A: cambiar  B: cerrar";
    case 3: return "A : changer  B : fermer";
    case 4: return "A: 切替  B: 閉じる";
    case 5: return "A: 전환  B: 닫기";
    case 6: return "A: переключить  B: закрыть";
    case 7: return "A 切换  B 关闭";
    default: return "A: toggle  B: close";
    }
}

[[nodiscard]] inline const char* ValueLabel(DisplayValue value, unsigned language) noexcept {
    if (language == 7) {
        switch (value) {
        case DisplayValue::On: return "开";
        case DisplayValue::Off: return "关";
        case DisplayValue::OnPending: return "开（保存中）";
        case DisplayValue::OffPending: return "关（保存中）";
        case DisplayValue::OnReload: return "开（需重启）";
        case DisplayValue::OffReload: return "关（需重启）";
        case DisplayValue::SaveFailed: return "保存失败";
        case DisplayValue::Unavailable: return "不可用";
        }
    }
    if (language == 4) {
        switch (value) {
        case DisplayValue::On: return "オン";
        case DisplayValue::Off: return "オフ";
        case DisplayValue::OnPending: return "オン（保存中）";
        case DisplayValue::OffPending: return "オフ（保存中）";
        case DisplayValue::OnReload: return "オン（再読込が必要）";
        case DisplayValue::OffReload: return "オフ（再読込が必要）";
        case DisplayValue::SaveFailed: return "保存失敗";
        case DisplayValue::Unavailable: return "利用不可";
        }
    }
    if (language == 5) {
        switch (value) {
        case DisplayValue::On: return "켜짐";
        case DisplayValue::Off: return "꺼짐";
        case DisplayValue::OnPending: return "켜짐 (저장 중)";
        case DisplayValue::OffPending: return "꺼짐 (저장 중)";
        case DisplayValue::OnReload: return "켜짐 (재로드 필요)";
        case DisplayValue::OffReload: return "꺼짐 (재로드 필요)";
        case DisplayValue::SaveFailed: return "저장 실패";
        case DisplayValue::Unavailable: return "사용 불가";
        }
    }
    switch (value) {
    case DisplayValue::On: return "On";
    case DisplayValue::Off: return "Off";
    case DisplayValue::OnPending: return "On - saving";
    case DisplayValue::OffPending: return "Off - saving";
    case DisplayValue::OnReload: return "On - restart required";
    case DisplayValue::OffReload: return "Off - restart required";
    case DisplayValue::SaveFailed: return "Save failed";
    case DisplayValue::Unavailable: return "Unavailable";
    }
    return "";
}

struct Layout {
    float paperScale;
    float textScale;
    float titleY;
    float rowY[2];
    float footerY;
    float rowLeft;
    float valueRight;
};

// Keep text at native size; only the blank paper is scaled.
inline constexpr Layout kRuntimeSettingsLayout{0.90F, 1.0F, -62.0F, {-30.0F, 3.0F}, 50.0F,
                                               -103.0F, 116.0F};

} // namespace isaac::runtime::title
