#pragma once

#include <cstdint>
#include <cstddef>

namespace isaac::runtime::notice {
using ActionQuery = bool (*)(void*, std::uint32_t, std::uint32_t, void*);
void Update(std::uint32_t menuState, float width, float height, ActionQuery query,
            const char* language = nullptr, void* systemFont = nullptr) noexcept;
void Render() noexcept;
void ConfigureComposite(std::uintptr_t base, std::size_t textSize) noexcept;
void ObserveMenu(std::uintptr_t menu, std::uint32_t state) noexcept;
void UpdateFailurePresentation(std::uint32_t state, float width, float height,
                               const char* language, void* systemFont) noexcept;
bool CanLeaveTitle(std::uintptr_t menu) noexcept;
bool BlocksTitleConfirm() noexcept;
} // namespace isaac::runtime::notice

// Phase/page/mode/hold/focus/resources/read/write/update/render/read-count/
// write-count/blocked-confirm/width/height/binding-stage/viewed-pages/can-hold-close.
// Game-thread diagnostics; viewed-pages is a mask, bit zero is page one.
// Appended: loaded-language/page-count/load-generation/live-sprites/failed-language/requested-language.
extern "C" std::uint32_t g_TitleNoticeState[24];
