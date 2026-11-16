#pragma once

#include <cstdint>

struct lua_State;

namespace isaac::runtime {

// Retained text-mode ImGui compatibility for mods that build custom menus.
//
// Reverie's Make Good Omissions uses the REPENTOGON ImGui API as a configuration
// surface. This implementation keeps that element graph alive between frames and
// provides real navigation, editing, callbacks, notifications, and text drawing.
// It deliberately implements only the element and callback families used by that
// menu; unsupported REPENTOGON widget families fail at registration time instead
// of pretending to work.
//
// Parent integration:
//   * call RegisterRepentogonImGuiApi(L) once after the base Lua libraries and the
//     Font bindings are installed;
//   * call SetRepentogonImGuiVisible(true/false) with the console/overlay lifecycle;
//   * call UpdateRepentogonImGui(...) from the native update path with edge-triggered
//     navigation bits;
//   * call DrawRepentogonImGui(...) after the game (and console) render callbacks,
//     while the game render target is still active.
//
// The API is deliberately single-state: the hosted Isaac Lua VM owns one ImGui
// overlay. Registering another state replaces the previous registration.

enum class ImGuiNavAction : std::uint8_t {
    Up,
    Down,
    Left,
    Right,
    Accept,
    Back,
    PreviousTab,
    NextTab,
};

struct ImGuiInputFrame {
    // All fields are single-frame edges, not held-key state.
    bool up{};
    bool down{};
    bool left{};
    bool right{};
    bool accept{};
    bool back{};
    bool previousTab{};
    bool nextTab{};
    // Wall-clock elapsed since the previous update; used only to expire notifications.
    std::uint32_t elapsedMilliseconds{};
};

inline ImGuiInputFrame ImGuiInputFromEngineEdges(std::uint32_t edges) noexcept {
    ImGuiInputFrame frame{};
    // Native menu actions 17..22 correspond to Lua actions 20..25.
    frame.left=(edges&((1U<<0)|(1U<<17)))!=0;
    frame.right=(edges&((1U<<1)|(1U<<18)))!=0;
    frame.up=(edges&((1U<<2)|(1U<<19)))!=0;
    frame.down=(edges&((1U<<3)|(1U<<20)))!=0;
    frame.accept=(edges&(1U<<14))!=0;
    frame.back=(edges&(1U<<15))!=0;
    frame.previousTab=(edges&(1U<<21))!=0;
    frame.nextTab=(edges&(1U<<22))!=0;
    frame.elapsedMilliseconds=17;
    return frame;
}

struct ImGuiViewport {
    float x{};
    float y{};
    float width{};
    float height{};
    float scale{1.0F};
};

struct ImGuiDrawHooks {
    void* user{};
    // Draws one retained-menu line. The color is four floats (RGBA). The hook is
    // called only from the game thread and must leave the Lua stack unchanged.
    void (*drawText)(void* user, const char* text, float x, float y, float scale,
                     const float* rgba){};
};

struct ImGuiRuntimeMetrics {
    std::uint32_t elementCount{};
    std::uint32_t callbackCount{};
    std::uint32_t lastBuildMicroseconds{};
    std::uint32_t lastTextCommands{};
    std::uint32_t lastCallbackCalls{};
};

int RegisterRepentogonImGuiApi(lua_State* state) noexcept;

// Releases retained Lua callback references and clears the menu graph. Safe to
// call more than once. The parent should call this before closing the Lua state.
void ResetRepentogonImGui(lua_State* state) noexcept;

void SetRepentogonImGuiVisible(bool visible) noexcept;
[[nodiscard]] bool RepentogonImGuiVisible() noexcept;
[[nodiscard]] bool RepentogonImGuiAvailable() noexcept;

// Returns true when the frame consumed at least one navigation action.
[[nodiscard]] bool UpdateRepentogonImGui(const ImGuiInputFrame& input) noexcept;

// Default renderer: CJK overlay font first, then the existing default screen font
// for ASCII-only text. Returns false when nothing could be drawn.
[[nodiscard]] bool DrawRepentogonImGui(const ImGuiViewport& viewport) noexcept;

// Host/test renderer injection. Passing an empty hook restores the native renderer.
[[nodiscard]] bool DrawRepentogonImGui(const ImGuiViewport& viewport,
                                       const ImGuiDrawHooks& hooks) noexcept;

[[nodiscard]] ImGuiRuntimeMetrics RepentogonImGuiMetrics() noexcept;

}  // namespace isaac::runtime
