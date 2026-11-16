#include "interfaces/lua/repentogon_imgui_api.hpp"

#include "interfaces/lua/font_api.hpp"
#include "interfaces/lua/runtime_perf.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "lua_runtime_state.hpp"

#include <algorithm>
#include <array>
#include <cfloat>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <string>
#include <string_view>
#include <utility>

extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}

namespace isaac::runtime {
namespace {

constexpr std::size_t kMaxElements = 256;
constexpr std::size_t kMaxCallbacks = 11;
constexpr std::size_t kMaxOptions = 16;
constexpr std::size_t kMaxNotifications = 16;
constexpr std::size_t kNotificationBytes = 128;
constexpr std::size_t kFrameLines = 96;
constexpr std::size_t kLineBytes = 256;

enum class ElementKind : std::uint8_t {
    Invalid,
    Menu,
    MenuItem,
    Window,
    TabBar,
    Tab,
    Text,
    TextWrapped,
    Separator,
    SeparatorText,
    SameLine,
    Button,
    Checkbox,
    Combobox,
    SliderInteger,
    InputFloat,
};

enum class CallbackKind : std::uint8_t {
    Clicked = 0,
    Edited = 5,
    Render = 10,
};

enum class LineStyle : std::uint8_t {
    Title,
    Header,
    Normal,
    Selected,
    Help,
    Info,
    Success,
    Warning,
    Error,
};

struct Element {
    Element() { callbackRefs.fill(LUA_NOREF); }

    std::string id;
    std::string label;
    std::string help;
    std::string tooltip;
    ElementKind kind{ElementKind::Invalid};
    int parent{-1};
    int linkedWindow{-1};
    bool visible{};
    bool checked{};
    int selectedIndex{};
    int intValue{};
    float floatValue{};
    float minimum{-FLT_MAX};
    float maximum{FLT_MAX};
    float step{1.0F};
    float stepFast{100.0F};
    std::array<std::string, kMaxOptions> options{};
    std::size_t optionCount{};
    std::array<int, kMaxCallbacks> callbackRefs{};
    std::uint32_t clickCount{};
    bool active{};
};

struct Notification {
    std::array<char, kNotificationBytes> text{};
    std::uint32_t remainingMilliseconds{};
    std::uint8_t severity{};
};

struct FrameLine {
    std::array<char, kLineBytes> text{};
    LineStyle style{LineStyle::Normal};
    int focusElement{-1};
};

struct Frame {
    std::array<FrameLine, kFrameLines> lines{};
    std::size_t count{};
};

lua_State* g_state{};
std::array<Element, kMaxElements> g_elements{};
std::size_t g_elementCount{};
bool g_visible{};
int g_openWindow{-1};
int g_selected{-1};
int g_activeTabIndex{};
std::array<Notification, kMaxNotifications> g_notifications{};
std::size_t g_notificationStart{};
std::size_t g_notificationCount{};
int g_fontRef{LUA_NOREF};
void* g_fontObject{};
bool g_fontAttempted{};
ImGuiRuntimeMetrics g_metrics{};

constexpr float kNormalScale = 0.86F;
constexpr float kTitleScale = 1.05F;
constexpr float kRowSpacing = 20.0F;

bool IsCallbackReference(int reference) noexcept {
    return reference != LUA_NOREF && reference != LUA_REFNIL;
}

void UnrefCallback(int* reference) noexcept {
    if (g_state != nullptr && reference != nullptr && IsCallbackReference(*reference)) {
        luaL_unref(g_state, LUA_REGISTRYINDEX, *reference);
    }
    if (reference != nullptr) {
        *reference = LUA_NOREF;
    }
}

void ClearRetainedState(bool releaseLuaReferences) noexcept {
    for (std::size_t index = 0; index < g_elementCount; ++index) {
        Element& element = g_elements[index];
        if (releaseLuaReferences) {
            for (int& reference : element.callbackRefs) {
                UnrefCallback(&reference);
            }
        } else {
            element.callbackRefs.fill(LUA_NOREF);
        }
        element = Element{};
    }
    g_elementCount = 0;
    g_openWindow = -1;
    g_selected = -1;
    g_activeTabIndex = 0;
    g_visible = false;
    g_notifications = {};
    g_notificationStart = 0;
    g_notificationCount = 0;
    if (releaseLuaReferences && g_state != nullptr && IsCallbackReference(g_fontRef)) {
        luaL_unref(g_state, LUA_REGISTRYINDEX, g_fontRef);
    }
    g_fontRef = LUA_NOREF;
    g_fontObject = nullptr;
    g_fontAttempted = false;
    g_metrics = {};
}

int FindElementById(std::string_view id) noexcept {
    if (id.empty()) {
        return -1;
    }
    for (std::size_t index = 0; index < g_elementCount; ++index) {
        if (g_elements[index].active && g_elements[index].id == id) {
            return static_cast<int>(index);
        }
    }
    return -1;
}

bool ValidElement(int index) noexcept {
    return index >= 0 && static_cast<std::size_t>(index) < g_elementCount &&
           g_elements[static_cast<std::size_t>(index)].active;
}

Element* ElementAt(int index) noexcept {
    return ValidElement(index) ? &g_elements[static_cast<std::size_t>(index)] : nullptr;
}

int AddElementRecord(ElementKind kind, std::string id, std::string label, int parent) noexcept {
    if (g_elementCount >= g_elements.size()) {
        return -1;
    }
    const int index = static_cast<int>(g_elementCount++);
    Element& element = g_elements[static_cast<std::size_t>(index)];
    element = Element{};
    element.kind = kind;
    element.id = std::move(id);
    element.label = std::move(label);
    element.parent = parent;
    element.active = true;
    return index;
}

bool IsControl(ElementKind kind) noexcept {
    switch (kind) {
        case ElementKind::Button:
        case ElementKind::Checkbox:
        case ElementKind::Combobox:
        case ElementKind::SliderInteger:
        case ElementKind::InputFloat:
            return true;
        default:
            return false;
    }
}

bool IsTextLike(ElementKind kind) noexcept {
    return kind == ElementKind::Text || kind == ElementKind::TextWrapped;
}

std::string_view CheckText(lua_State* state, int index, const char* owner) {
    const char* text = luaL_checkstring(state, index);
    if (text == nullptr) {
        luaL_error(state, "%s expects a string", owner);
    }
    return std::string_view(text, std::strlen(text));
}

int RequireElementId(lua_State* state, int index, const char* owner) {
    const std::string_view id = CheckText(state, index, owner);
    if (id.empty()) {
        luaL_error(state, "%s requires a non-empty element id", owner);
    }
    const int element = FindElementById(id);
    if (element < 0) {
        luaL_error(state, "%s: no element '%s' exists", owner, std::string(id).c_str());
    }
    return element;
}

int RequireParent(lua_State* state, int index, const char* owner) {
    const std::string_view id = CheckText(state, index, owner);
    const int parent = FindElementById(id);
    if (parent < 0) {
        luaL_error(state, "%s: parent element '%s' does not exist", owner,
                   std::string(id).c_str());
    }
    return parent;
}

int CheckCallback(lua_State* state, int index, const char* owner) {
    if (lua_isnoneornil(state, index)) {
        return LUA_NOREF;
    }
    if (!lua_isfunction(state, index)) {
        luaL_error(state, "%s callback must be a function or nil", owner);
    }
    lua_pushvalue(state, index);
    return luaL_ref(state, LUA_REGISTRYINDEX);
}

void SetElementCallback(Element& element, CallbackKind kind, int reference) noexcept {
    int& slot = element.callbackRefs[static_cast<std::size_t>(kind)];
    if (slot == reference) {
        return;
    }
    UnrefCallback(&slot);
    slot = reference;
}

bool CallbackData(lua_State* state, const Element& element) {
    switch (element.kind) {
        case ElementKind::Checkbox:
            lua_pushboolean(state, element.checked ? 1 : 0);
            return true;
        case ElementKind::Combobox:
            lua_pushinteger(state, element.selectedIndex);
            if (element.selectedIndex >= 0 &&
                static_cast<std::size_t>(element.selectedIndex) < element.optionCount) {
                lua_pushstring(
                    state,
                    element.options[static_cast<std::size_t>(element.selectedIndex)].c_str());
            } else {
                lua_pushstring(state, "");
            }
            return true;
        case ElementKind::SliderInteger:
            lua_pushinteger(state, element.intValue);
            return true;
        case ElementKind::InputFloat:
            lua_pushnumber(state, static_cast<lua_Number>(element.floatValue));
            return true;
        default:
            lua_pushnumber(state, static_cast<lua_Number>(element.clickCount));
            return true;
    }
}

void InvokeCallback(Element& element, CallbackKind kind) noexcept {
    if (g_state == nullptr) {
        return;
    }
    const std::size_t callbackIndex = static_cast<std::size_t>(kind);
    const int reference = element.callbackRefs[callbackIndex];
    if (!IsCallbackReference(reference)) {
        return;
    }
    const int base = lua_gettop(g_state);
    if (!lua_checkstack(g_state, 4)) {
        return;
    }
    lua_rawgeti(g_state, LUA_REGISTRYINDEX, reference);
    if (!lua_isfunction(g_state, -1)) {
        lua_settop(g_state, base);
        UnrefCallback(&element.callbackRefs[callbackIndex]);
        return;
    }

    int arguments = 0;
    if (kind == CallbackKind::Edited) {
        static_cast<void>(CallbackData(g_state, element));
        arguments = element.kind == ElementKind::Combobox ? 2 : 1;
    } else if (kind == CallbackKind::Clicked) {
        lua_pushnumber(g_state, static_cast<lua_Number>(element.clickCount));
        arguments = 1;
    }

    ++g_metrics.lastCallbackCalls;
    const int status = lua_pcallk(g_state, arguments, 0, 0, 0, nullptr);
    if (status != LUA_OK) {
        const char* error = lua_tostring(g_state, -1);
        if (error != nullptr) {
            LuaRuntime::RecordLuaErrorText(error, std::strlen(error));
        }
    }
    lua_settop(g_state, base);
}

void RequireSupportedCallbackType(lua_State* state, int type) {
    if (type != static_cast<int>(CallbackKind::Clicked) &&
        type != static_cast<int>(CallbackKind::Edited) &&
        type != static_cast<int>(CallbackKind::Render)) {
        luaL_error(state,
                   "ImGui callback type %d is outside the retained MGO subset "
                   "(Clicked, Edited, Render)",
                   type);
    }
}

ElementKind MapElementType(lua_State* state, int type) {
    switch (type) {
        case 2:
            return ElementKind::MenuItem;
        case 6:
            return ElementKind::Separator;
        case 7:
            return ElementKind::SeparatorText;
        case 8:
            return ElementKind::Text;
        case 9:
            return ElementKind::TextWrapped;
        case 11:
            return ElementKind::SameLine;
        default:
            luaL_error(state,
                       "ImGuiElement %d is outside the retained MGO subset "
                       "(MenuItem, Separator, SeparatorText, Text, TextWrapped, SameLine)",
                       type);
            return ElementKind::Invalid;
    }
}

int FindFirstChild(int parent, ElementKind kind) noexcept {
    for (std::size_t index = 0; index < g_elementCount; ++index) {
        const Element& element = g_elements[index];
        if (element.active && element.parent == parent && element.kind == kind) {
            return static_cast<int>(index);
        }
    }
    return -1;
}

int ActiveTabBar(int window) noexcept {
    return FindFirstChild(window, ElementKind::TabBar);
}

int TabAt(int tabBar, int ordinal) noexcept {
    if (ordinal < 0) {
        return -1;
    }
    int found = 0;
    for (std::size_t index = 0; index < g_elementCount; ++index) {
        const Element& element = g_elements[index];
        if (element.active && element.parent == tabBar && element.kind == ElementKind::Tab) {
            if (found == ordinal) {
                return static_cast<int>(index);
            }
            ++found;
        }
    }
    return -1;
}

int TabCount(int tabBar) noexcept {
    int count = 0;
    for (std::size_t index = 0; index < g_elementCount; ++index) {
        const Element& element = g_elements[index];
        if (element.active && element.parent == tabBar && element.kind == ElementKind::Tab) {
            ++count;
        }
    }
    return count;
}

int ContentParent(int window) noexcept {
    const int tabBar = ActiveTabBar(window);
    if (tabBar < 0) {
        return window;
    }
    const int count = TabCount(tabBar);
    if (count <= 0) {
        return window;
    }
    g_activeTabIndex = std::clamp(g_activeTabIndex, 0, count - 1);
    const int tab = TabAt(tabBar, g_activeTabIndex);
    return tab >= 0 ? tab : window;
}

int FirstControlIn(int parent) noexcept {
    for (std::size_t index = 0; index < g_elementCount; ++index) {
        const Element& element = g_elements[index];
        if (element.active && element.parent == parent && IsControl(element.kind)) {
            return static_cast<int>(index);
        }
    }
    return -1;
}

void EnsureWindowSelection() noexcept {
    if (!ValidElement(g_openWindow)) {
        g_openWindow = -1;
        g_selected = -1;
        return;
    }
    const int content = ContentParent(g_openWindow);
    Element* selected = ElementAt(g_selected);
    if (selected == nullptr || selected->parent != content || !IsControl(selected->kind)) {
        g_selected = FirstControlIn(content);
    }
}

int NextControlIn(int content, int current, int direction) noexcept {
    const int count = static_cast<int>(g_elementCount);
    if (count == 0 || direction == 0) {
        return -1;
    }
    int cursor = current;
    for (int attempt = 0; attempt < count; ++attempt) {
        cursor += direction;
        if (cursor < 0) {
            cursor = count - 1;
        } else if (cursor >= count) {
            cursor = 0;
        }
        const Element& element = g_elements[static_cast<std::size_t>(cursor)];
        if (element.active && element.parent == content && IsControl(element.kind)) {
            return cursor;
        }
    }
    return -1;
}

int RootMenuCount() noexcept {
    int count = 0;
    for (std::size_t index = 0; index < g_elementCount; ++index) {
        const Element& element = g_elements[index];
        if (element.active && element.kind == ElementKind::MenuItem) {
            ++count;
        }
    }
    return count;
}

int RootItemAt(int ordinal) noexcept {
    int found = 0;
    for (std::size_t index = 0; index < g_elementCount; ++index) {
        const Element& element = g_elements[index];
        if (element.active && element.kind == ElementKind::MenuItem) {
            if (found == ordinal) {
                return static_cast<int>(index);
            }
            ++found;
        }
    }
    return -1;
}

int RootSelectedOrdinal() noexcept {
    const int count = RootMenuCount();
    for (int ordinal = 0; ordinal < count; ++ordinal) {
        if (RootItemAt(ordinal) == g_selected) {
            return ordinal;
        }
    }
    return -1;
}

void EnsureRootSelection() noexcept {
    Element* selected = ElementAt(g_selected);
    if (selected != nullptr && selected->kind == ElementKind::MenuItem) {
        return;
    }
    g_selected = RootItemAt(0);
}

void MoveRootSelection(int direction) noexcept {
    const int count = RootMenuCount();
    if (count <= 0) {
        g_selected = -1;
        return;
    }
    int ordinal = RootSelectedOrdinal();
    if (ordinal < 0) {
        ordinal = 0;
    } else {
        ordinal = (ordinal + direction + count) % count;
    }
    g_selected = RootItemAt(ordinal);
}

void OpenLinkedWindow(int menuIndex) noexcept {
    Element* item = ElementAt(menuIndex);
    if (item == nullptr || item->kind != ElementKind::MenuItem ||
        !ValidElement(item->linkedWindow)) {
        return;
    }
    g_openWindow = item->linkedWindow;
    g_activeTabIndex = 0;
    Element* window = ElementAt(g_openWindow);
    if (window != nullptr) {
        window->visible = true;
    }
    g_selected = FirstControlIn(ContentParent(g_openWindow));
}

void CloseOpenWindow() noexcept {
    if (Element* window = ElementAt(g_openWindow); window != nullptr) {
        window->visible = false;
    }
    g_openWindow = -1;
    g_selected = -1;
}

void SwitchTab(int direction) noexcept {
    if (!ValidElement(g_openWindow)) {
        return;
    }
    const int tabBar = ActiveTabBar(g_openWindow);
    const int count = TabCount(tabBar);
    if (count <= 1) {
        return;
    }
    g_activeTabIndex = (g_activeTabIndex + direction + count) % count;
    g_selected = FirstControlIn(ContentParent(g_openWindow));
}

void SetCheckboxValue(Element& element, bool value) noexcept {
    if (element.checked == value) {
        return;
    }
    element.checked = value;
    InvokeCallback(element, CallbackKind::Edited);
}

void SetComboboxValue(Element& element, int value) noexcept {
    if (element.optionCount == 0) {
        return;
    }
    const int maximum = static_cast<int>(element.optionCount) - 1;
    value = std::clamp(value, 0, maximum);
    if (element.selectedIndex == value) {
        return;
    }
    element.selectedIndex = value;
    InvokeCallback(element, CallbackKind::Edited);
}

void SetSliderValue(Element& element, int value) noexcept {
    const int minimum = static_cast<int>(element.minimum);
    const int maximum = static_cast<int>(element.maximum);
    value = std::clamp(value, std::min(minimum, maximum), std::max(minimum, maximum));
    if (element.intValue == value) {
        return;
    }
    element.intValue = value;
    InvokeCallback(element, CallbackKind::Edited);
}

void SetFloatValue(Element& element, float value) noexcept {
    if (element.floatValue == value) {
        return;
    }
    element.floatValue = value;
    InvokeCallback(element, CallbackKind::Edited);
}

bool AdjustSelected(int direction) noexcept {
    Element* element = ElementAt(g_selected);
    if (element == nullptr) {
        return false;
    }
    switch (element->kind) {
        case ElementKind::Checkbox:
            SetCheckboxValue(*element, !element->checked);
            return true;
        case ElementKind::Combobox:
            SetComboboxValue(*element, element->selectedIndex + direction);
            return true;
        case ElementKind::SliderInteger:
            SetSliderValue(*element, element->intValue + direction);
            return true;
        case ElementKind::InputFloat:
            SetFloatValue(*element, element->floatValue +
                                        static_cast<float>(direction) * element->step);
            return true;
        default:
            return false;
    }
}

bool ActivateSelected() noexcept {
    Element* element = ElementAt(g_selected);
    if (element == nullptr) {
        return false;
    }
    switch (element->kind) {
        case ElementKind::MenuItem:
            OpenLinkedWindow(g_selected);
            return true;
        case ElementKind::Button:
            ++element->clickCount;
            InvokeCallback(*element, CallbackKind::Clicked);
            return true;
        case ElementKind::Checkbox:
            SetCheckboxValue(*element, !element->checked);
            return true;
        case ElementKind::Combobox:
            if (element->optionCount > 0) {
                const int next =
                    (element->selectedIndex + 1) % static_cast<int>(element->optionCount);
                SetComboboxValue(*element, next);
            }
            return true;
        case ElementKind::SliderInteger:
            SetSliderValue(*element, element->intValue + 1);
            return true;
        case ElementKind::InputFloat:
            SetFloatValue(*element, element->floatValue + element->step);
            return true;
        default:
            return false;
    }
}

bool NextSiblingOfKind(int elementIndex, ElementKind* kind) noexcept {
    const Element* element = ElementAt(elementIndex);
    if (element == nullptr || kind == nullptr) {
        return false;
    }
    for (std::size_t index = static_cast<std::size_t>(elementIndex) + 1;
         index < g_elementCount; ++index) {
        const Element& candidate = g_elements[index];
        if (!candidate.active || candidate.parent != element->parent ||
            candidate.kind == ElementKind::SameLine) {
            continue;
        }
        *kind = candidate.kind;
        return true;
    }
    return false;
}

bool TextIsControlLabel(int elementIndex) noexcept {
    ElementKind next{ElementKind::Invalid};
    return NextSiblingOfKind(elementIndex, &next) && IsControl(next);
}

std::string_view PreviousTextLabel(int elementIndex) noexcept {
    const Element* element = ElementAt(elementIndex);
    if (element == nullptr) {
        return {};
    }
    for (int index = elementIndex - 1; index >= 0; --index) {
        const Element& candidate = g_elements[static_cast<std::size_t>(index)];
        if (!candidate.active || candidate.parent != element->parent ||
            candidate.kind == ElementKind::SameLine) {
            continue;
        }
        if (IsTextLike(candidate.kind)) {
            return candidate.label;
        }
        break;
    }
    return {};
}

std::size_t Utf8CodepointBytes(unsigned char lead) noexcept {
    if ((lead & 0x80U) == 0) {
        return 1;
    }
    if ((lead & 0xE0U) == 0xC0U) {
        return 2;
    }
    if ((lead & 0xF0U) == 0xE0U) {
        return 3;
    }
    if ((lead & 0xF8U) == 0xF0U) {
        return 4;
    }
    return 1;
}

std::string_view StripLeadingPrivateIcon(std::string_view text) noexcept {
    while (!text.empty() && (text.front() == ' ' || text.front() == '\t')) {
        text.remove_prefix(1);
    }
    if (text.size() >= 3) {
        const auto* bytes = reinterpret_cast<const unsigned char*>(text.data());
        const unsigned codepoint =
            ((static_cast<unsigned>(bytes[0]) & 0x0FU) << 12U) |
            ((static_cast<unsigned>(bytes[1]) & 0x3FU) << 6U) |
            (static_cast<unsigned>(bytes[2]) & 0x3FU);
        if (bytes[0] >= 0xE0U && codepoint >= 0xE000U && codepoint <= 0xF8FFU) {
            text.remove_prefix(3);
            while (!text.empty() && (text.front() == ' ' || text.front() == '\t')) {
                text.remove_prefix(1);
            }
        }
    }
    return text;
}

void CopyClipped(std::string_view text, std::size_t maxCodepoints, char* out,
                 std::size_t capacity) noexcept {
    if (out == nullptr || capacity == 0) {
        return;
    }
    text = StripLeadingPrivateIcon(text);
    std::size_t written = 0;
    std::size_t codepoints = 0;
    while (!text.empty() && codepoints < maxCodepoints) {
        if (text.front() == '\n' || text.front() == '\r') {
            break;
        }
        const std::size_t bytes =
            std::min(Utf8CodepointBytes(static_cast<unsigned char>(text.front())), text.size());
        if (written + bytes + 1 >= capacity) {
            break;
        }
        std::memcpy(out + written, text.data(), bytes);
        written += bytes;
        text.remove_prefix(bytes);
        ++codepoints;
    }
    out[written] = '\0';
}

void AddFormattedLine(Frame& frame, LineStyle style, int focusElement, const char* format, ...) {
    if (frame.count >= frame.lines.size() || format == nullptr) {
        return;
    }
    FrameLine& line = frame.lines[frame.count++];
    line.style = style;
    line.focusElement = focusElement;
    va_list arguments;
    va_start(arguments, format);
    std::vsnprintf(line.text.data(), line.text.size(), format, arguments);
    va_end(arguments);
}

void AddTextLine(Frame& frame, LineStyle style, int focusElement, bool selected,
                 std::string_view text) {
    char clipped[kLineBytes]{};
    CopyClipped(text, 58, clipped, sizeof(clipped));
    AddFormattedLine(frame, style, focusElement, "%s%s", selected ? "> " : "  ", clipped);
}

void AddWrappedText(Frame& frame, LineStyle style, std::string_view text) {
    text = StripLeadingPrivateIcon(text);
    if (text.empty()) {
        return;
    }
    std::size_t lineStart = 0;
    int emitted = 0;
    while (lineStart < text.size() && emitted < 3 && frame.count < frame.lines.size()) {
        std::size_t cursor = lineStart;
        std::size_t codepoints = 0;
        while (cursor < text.size() && codepoints < 54 && text[cursor] != '\n' &&
               text[cursor] != '\r') {
            cursor += std::min(Utf8CodepointBytes(static_cast<unsigned char>(text[cursor])),
                               text.size() - cursor);
            ++codepoints;
        }
        AddTextLine(frame, style, -1, false, text.substr(lineStart, cursor - lineStart));
        ++emitted;
        lineStart = cursor;
        while (lineStart < text.size() &&
               (text[lineStart] == '\n' || text[lineStart] == '\r' ||
                text[lineStart] == ' ' || text[lineStart] == '\t')) {
            ++lineStart;
        }
    }
}

std::string_view ControlLabel(int elementIndex) noexcept {
    const Element& element = g_elements[static_cast<std::size_t>(elementIndex)];
    const std::string_view previous = PreviousTextLabel(elementIndex);
    if (!previous.empty()) {
        return previous;
    }
    return element.label;
}

void AddControlLine(Frame& content, int elementIndex) {
    const Element& element = g_elements[static_cast<std::size_t>(elementIndex)];
    const bool selected = elementIndex == g_selected;
    const LineStyle style = selected ? LineStyle::Selected : LineStyle::Normal;
    char body[kLineBytes]{};
    const std::string_view label = StripLeadingPrivateIcon(ControlLabel(elementIndex));

    switch (element.kind) {
        case ElementKind::Checkbox:
            std::snprintf(body, sizeof(body), "[%c] %.*s", element.checked ? 'x' : ' ',
                          static_cast<int>(label.size()), label.data());
            break;
        case ElementKind::Combobox: {
            const char* value =
                element.selectedIndex >= 0 &&
                        static_cast<std::size_t>(element.selectedIndex) < element.optionCount
                    ? element.options[static_cast<std::size_t>(element.selectedIndex)].c_str()
                    : "<unset>";
            std::snprintf(body, sizeof(body), "%.*s: %s", static_cast<int>(label.size()),
                          label.data(), value);
            break;
        }
        case ElementKind::SliderInteger: {
            const std::string_view suffix = StripLeadingPrivateIcon(element.label);
            std::snprintf(body, sizeof(body), "%.*s: %d%s%.*s",
                          static_cast<int>(label.size()), label.data(), element.intValue,
                          suffix.empty() ? "" : " ",
                          static_cast<int>(suffix.size()), suffix.data());
            break;
        }
        case ElementKind::InputFloat:
            std::snprintf(body, sizeof(body), "%.*s: %.3f", static_cast<int>(label.size()),
                          label.data(), static_cast<double>(element.floatValue));
            break;
        case ElementKind::Button: {
            const std::string_view button =
                label.empty() ? std::string_view{"Reset"} : label;
            std::snprintf(body, sizeof(body), "[ %.*s ]", static_cast<int>(button.size()),
                          button.data());
            break;
        }
        default:
            std::snprintf(body, sizeof(body), "%.*s", static_cast<int>(label.size()),
                          label.data());
            break;
    }
    AddTextLine(content, style, elementIndex, selected, body);
}

void BuildRootFrame(Frame& frame) {
    for (std::size_t index = 0; index < g_elementCount; ++index) {
        const Element& menu = g_elements[index];
        if (!menu.active || menu.kind != ElementKind::Menu) {
            continue;
        }
        const std::string_view title = StripLeadingPrivateIcon(menu.label);
        char line[kLineBytes]{};
        std::snprintf(line, sizeof(line), "== %.*s ==", static_cast<int>(title.size()),
                      title.data());
        AddFormattedLine(frame, LineStyle::Title, -1, "%s", line);
        for (std::size_t childIndex = 0; childIndex < g_elementCount; ++childIndex) {
            const Element& child = g_elements[childIndex];
            if (!child.active || child.parent != static_cast<int>(index) ||
                child.kind != ElementKind::MenuItem) {
                continue;
            }
            AddTextLine(frame, static_cast<int>(childIndex) == g_selected
                                   ? LineStyle::Selected
                                   : LineStyle::Normal,
                        static_cast<int>(childIndex), static_cast<int>(childIndex) == g_selected,
                        child.label);
        }
    }
    if (frame.count == 0) {
        AddFormattedLine(frame, LineStyle::Help, -1, "  No retained ImGui menus are registered.");
    }
}

void BuildTabHeader(Frame& frame, int window) {
    const int tabBar = ActiveTabBar(window);
    const int count = TabCount(tabBar);
    if (tabBar < 0 || count <= 0) {
        return;
    }
    char line[kLineBytes]{};
    std::size_t used = 0;
    const int written = std::snprintf(line, sizeof(line), "Tabs: ");
    if (written < 0) {
        return;
    }
    used = std::min(static_cast<std::size_t>(written), sizeof(line) - 1);
    for (int tabIndex = 0; tabIndex < count && used + 4 < sizeof(line); ++tabIndex) {
        const int tab = TabAt(tabBar, tabIndex);
        if (tab < 0) {
            continue;
        }
        const std::string_view label =
            StripLeadingPrivateIcon(g_elements[static_cast<std::size_t>(tab)].label);
        const bool active = tabIndex == g_activeTabIndex;
        const int appended = std::snprintf(line + used, sizeof(line) - used, "%s%.*s%s%s",
                                           active ? "[" : "", static_cast<int>(label.size()),
                                           label.data(), active ? "]" : "",
                                           tabIndex + 1 == count ? "" : "  ");
        if (appended < 0) {
            break;
        }
        used += std::min(static_cast<std::size_t>(appended), sizeof(line) - used - 1);
    }
    AddFormattedLine(frame, LineStyle::Header, -1, "%s", line);
}

void BuildWindowContent(Frame& content, int parent) {
    for (std::size_t index = 0; index < g_elementCount; ++index) {
        const Element& element = g_elements[index];
        if (!element.active || element.parent != parent) {
            continue;
        }
        switch (element.kind) {
            case ElementKind::Text:
            case ElementKind::TextWrapped:
                if (!TextIsControlLabel(static_cast<int>(index))) {
                    AddWrappedText(content, LineStyle::Normal, element.label);
                }
                break;
            case ElementKind::Separator:
                AddFormattedLine(content, LineStyle::Help, -1, "  --------------------------------");
                break;
            case ElementKind::SeparatorText:
                AddTextLine(content, LineStyle::Header, -1, false, element.label);
                break;
            case ElementKind::SameLine:
            case ElementKind::Menu:
            case ElementKind::MenuItem:
            case ElementKind::Window:
            case ElementKind::TabBar:
            case ElementKind::Tab:
            case ElementKind::Invalid:
                break;
            default:
                AddControlLine(content, static_cast<int>(index));
                break;
        }
    }
}

std::size_t SelectedContentLine(const Frame& content) noexcept {
    for (std::size_t index = 0; index < content.count; ++index) {
        if (content.lines[index].focusElement == g_selected) {
            return index;
        }
    }
    return 0;
}

void AppendVisibleContent(Frame& frame, const Frame& content, std::size_t maximumRows) {
    if (content.count <= maximumRows) {
        for (std::size_t index = 0; index < content.count; ++index) {
            frame.lines[frame.count++] = content.lines[index];
        }
        return;
    }
    const std::size_t selected = SelectedContentLine(content);
    std::size_t start = selected > maximumRows / 3 ? selected - maximumRows / 3 : 0;
    if (start + maximumRows > content.count) {
        start = content.count - maximumRows;
    }
    if (start > 0) {
        AddFormattedLine(frame, LineStyle::Help, -1, "  ^ more above ^");
    }
    const std::size_t available = frame.lines.size() - frame.count;
    const std::size_t rows = std::min(maximumRows, available);
    for (std::size_t index = 0; index < rows && start + index < content.count; ++index) {
        frame.lines[frame.count++] = content.lines[start + index];
    }
    if (start + rows < content.count && frame.count < frame.lines.size()) {
        AddFormattedLine(frame, LineStyle::Help, -1, "  v more below v");
    }
}

void AppendSelectedHelp(Frame& frame) {
    const Element* selected = ElementAt(g_selected);
    if (selected == nullptr) {
        AddFormattedLine(frame, LineStyle::Help, -1,
                         "  Up/Down select  Left/Right edit  Accept activate  Back close");
        return;
    }
    const std::string_view text =
        !selected->help.empty() ? std::string_view(selected->help)
                                : std::string_view(selected->tooltip);
    if (text.empty()) {
        AddFormattedLine(frame, LineStyle::Help, -1,
                         "  Up/Down select  Left/Right edit  Accept activate  Back close");
        return;
    }
    char clipped[kLineBytes]{};
    CopyClipped(text, 72, clipped, sizeof(clipped));
    AddFormattedLine(frame, LineStyle::Help, -1, "  Help: %s", clipped);
}

LineStyle NotificationStyle(std::uint8_t severity) noexcept {
    switch (severity) {
        case 1:
            return LineStyle::Success;
        case 2:
            return LineStyle::Warning;
        case 3:
            return LineStyle::Error;
        default:
            return LineStyle::Info;
    }
}

const char* SeverityName(std::uint8_t severity) noexcept {
    switch (severity) {
        case 1:
            return "SUCCESS";
        case 2:
            return "WARNING";
        case 3:
            return "ERROR";
        default:
            return "INFO";
    }
}

void AppendNotifications(Frame& frame) {
    const std::size_t visible = std::min<std::size_t>(g_notificationCount, 4);
    for (std::size_t index = 0; index < visible && frame.count < frame.lines.size(); ++index) {
        const Notification& notification =
            g_notifications[(g_notificationStart + index) % kMaxNotifications];
        AddFormattedLine(frame, NotificationStyle(notification.severity), -1, "  [%s] %s",
                         SeverityName(notification.severity), notification.text.data());
    }
}

void InvokeRenderCallbacks() {
    if (!ValidElement(g_openWindow)) {
        return;
    }
    const int content = ContentParent(g_openWindow);
    const std::size_t count = g_elementCount;
    for (std::size_t index = 0; index < count; ++index) {
        Element& element = g_elements[index];
        if (element.active && element.parent == content && IsControl(element.kind)) {
            InvokeCallback(element, CallbackKind::Render);
        }
    }
}

Frame BuildFrame(const ImGuiViewport& viewport) {
    Frame frame{};
    if (ValidElement(g_openWindow)) {
        EnsureWindowSelection();
        const std::string_view title =
            StripLeadingPrivateIcon(g_elements[static_cast<std::size_t>(g_openWindow)].label);
        char line[kLineBytes]{};
        std::snprintf(line, sizeof(line), "== %.*s ==", static_cast<int>(title.size()),
                      title.data());
        AddFormattedLine(frame, LineStyle::Title, -1, "%s", line);
        BuildTabHeader(frame, g_openWindow);

        Frame content{};
        BuildWindowContent(content, ContentParent(g_openWindow));
        const float usableHeight = std::max(viewport.height - 112.0F, 120.0F);
        const std::size_t maximumRows = std::clamp<std::size_t>(
            static_cast<std::size_t>(usableHeight / (kRowSpacing * std::max(viewport.scale, 0.5F))),
            5, 24);
        AppendVisibleContent(frame, content, maximumRows);
        if (content.count == 0) {
            AddFormattedLine(frame, LineStyle::Help, -1, "  This page has no controls.");
        }
        AppendSelectedHelp(frame);
    } else {
        EnsureRootSelection();
        BuildRootFrame(frame);
        AddFormattedLine(frame, LineStyle::Help, -1,
                         "  Up/Down select  Accept open  Back close");
    }
    AppendNotifications(frame);
    return frame;
}

void UpdateNotificationLifetimes(std::uint32_t elapsedMilliseconds) noexcept {
    std::size_t index = 0;
    while (index < g_notificationCount) {
        Notification& notification =
            g_notifications[(g_notificationStart + index) % kMaxNotifications];
        if (notification.remainingMilliseconds <= elapsedMilliseconds) {
            for (std::size_t move = index; move + 1 < g_notificationCount; ++move) {
                g_notifications[(g_notificationStart + move) % kMaxNotifications] =
                    g_notifications[(g_notificationStart + move + 1) % kMaxNotifications];
            }
            --g_notificationCount;
            continue;
        }
        notification.remainingMilliseconds -= elapsedMilliseconds;
        ++index;
    }
}

bool TextIsAscii(std::string_view text) noexcept {
    for (const unsigned char byte : text) {
        if (byte >= 0x80U) {
            return false;
        }
    }
    return true;
}

bool EnsureOverlayFont() noexcept {
    if (g_state == nullptr) {
        return false;
    }
    if (g_fontObject != nullptr) {
        return true;
    }
    if (g_fontAttempted) {
        return false;
    }
    if (LuaRuntime::FontCtorThunk() == nullptr || LuaRuntime::FontDestructorThunk() == nullptr ||
        LuaRuntime::FontLoadThunk() == nullptr ||
        LuaRuntime::FontDrawStringScaledUTF8Thunk() == nullptr ||
        LuaRuntime::FontDrawStringScaledThunk() == nullptr) {
        return false;
    }
    g_fontAttempted = true;
    if (lua_gettop(g_state) != 0) {
        return false;
    }

    lua_pushcfunction(g_state, CreateFontHandle);
    if (lua_pcallk(g_state, 0, 1, 0, 0, nullptr) != LUA_OK) {
        lua_settop(g_state, 0);
        return false;
    }
    auto* handle = static_cast<LuaRuntime::FontHandle*>(lua_touserdata(g_state, -1));
    if (handle == nullptr || handle->font == nullptr) {
        lua_settop(g_state, 0);
        return false;
    }
    const bool loaded =
        LuaRuntime::FontLoadThunk()(handle->font, "font/cjk/lanapixel.fnt", nullptr);
    if (!loaded) {
        lua_settop(g_state, 0);
        return false;
    }
    g_fontObject = handle->font;
    g_fontRef = luaL_ref(g_state, LUA_REGISTRYINDEX);
    return g_fontRef != LUA_NOREF;
}

bool DrawNativeText(const char* text, float x, float y, float scale, const float* rgba) noexcept {
    if (g_state == nullptr || text == nullptr || rgba == nullptr) {
        return false;
    }
    if (EnsureOverlayFont() && g_fontObject != nullptr) {
        if (TextIsAscii(text)) {
            LuaRuntime::FontDrawStringScaledThunk()(g_fontObject, text, x, y, scale, scale, rgba,
                                                    0, false);
        } else {
            LuaRuntime::FontDrawStringScaledUTF8Thunk()(g_fontObject, text, x, y, scale, scale,
                                                        rgba, 0, false);
        }
        return true;
    }
    if (!TextIsAscii(text)) {
        return false;
    }
    return DrawScaledTextWithDefaultFont(g_state, text, std::strlen(text), x, y, scale, scale,
                                         rgba[0], rgba[1], rgba[2], rgba[3]);
}

std::array<float, 4> ColorForStyle(LineStyle style) noexcept {
    switch (style) {
        case LineStyle::Title:
            return {1.00F, 0.82F, 0.30F, 1.0F};
        case LineStyle::Header:
            return {0.62F, 0.86F, 1.00F, 1.0F};
        case LineStyle::Selected:
            return {1.00F, 0.95F, 0.46F, 1.0F};
        case LineStyle::Help:
            return {0.66F, 0.74F, 0.82F, 1.0F};
        case LineStyle::Info:
            return {0.82F, 0.90F, 1.00F, 1.0F};
        case LineStyle::Success:
            return {0.45F, 1.00F, 0.55F, 1.0F};
        case LineStyle::Warning:
            return {1.00F, 0.78F, 0.30F, 1.0F};
        case LineStyle::Error:
            return {1.00F, 0.36F, 0.36F, 1.0F};
        default:
            return {0.92F, 0.94F, 0.96F, 1.0F};
    }
}

float ScaleForStyle(LineStyle style) noexcept {
    if (style == LineStyle::Title) {
        return kTitleScale;
    }
    if (style == LineStyle::Help) {
        return 0.72F;
    }
    return kNormalScale;
}

bool DrawFrame(const ImGuiViewport& viewport, const Frame& frame,
               const ImGuiDrawHooks& hooks) noexcept {
    const float x = viewport.x + 28.0F * std::max(viewport.scale, 0.25F);
    float y = viewport.y + 24.0F * std::max(viewport.scale, 0.25F);
    std::uint32_t drawn = 0;
    for (std::size_t index = 0; index < frame.count; ++index) {
        const FrameLine& line = frame.lines[index];
        const auto color = ColorForStyle(line.style);
        const float scale = ScaleForStyle(line.style) * std::max(viewport.scale, 0.25F);
        bool success = false;
        if (hooks.drawText != nullptr) {
            hooks.drawText(hooks.user, line.text.data(), x, y, scale, color.data());
            success = line.text[0] != '\0';
        } else {
            success = DrawNativeText(line.text.data(), x, y, scale, color.data());
        }
        if (success) {
            ++drawn;
        }
        y += kRowSpacing * std::max(viewport.scale, 0.25F);
    }
    g_metrics.lastTextCommands = drawn;
    return drawn != 0;
}

void InstallEnumTable(lua_State* state, const char* name,
                      std::initializer_list<std::pair<const char*, int>> values) {
    lua_newtable(state);
    for (const auto& [entryName, value] : values) {
        lua_pushinteger(state, value);
        lua_setfield(state, -2, entryName);
    }
    lua_setglobal(state, name);
}

int LuaCreateMenu(lua_State* state) {
    const std::string_view id = CheckText(state, 1, "ImGui.CreateMenu");
    if (id.empty()) {
        return luaL_error(state, "ImGui.CreateMenu requires a non-empty id");
    }
    if (FindElementById(id) >= 0) {
        return luaL_error(state, "ImGui.CreateMenu: element '%s' already exists",
                          std::string(id).c_str());
    }
    const std::string_view label = lua_isnoneornil(state, 2) ? id
                                                             : CheckText(state, 2,
                                                                         "ImGui.CreateMenu");
    if (AddElementRecord(ElementKind::Menu, std::string(id), std::string(label), -1) < 0) {
        return luaL_error(state, "ImGui element capacity is exhausted");
    }
    return 0;
}

int LuaCreateWindow(lua_State* state) {
    const std::string_view id = CheckText(state, 1, "ImGui.CreateWindow");
    if (id.empty()) {
        return luaL_error(state, "ImGui.CreateWindow requires a non-empty id");
    }
    if (FindElementById(id) >= 0) {
        return luaL_error(state, "ImGui.CreateWindow: element '%s' already exists",
                          std::string(id).c_str());
    }
    const std::string_view title = lua_isnoneornil(state, 2)
                                       ? id
                                       : CheckText(state, 2, "ImGui.CreateWindow");
    const int parent = lua_isnoneornil(state, 3)
                           ? -1
                           : RequireParent(state, 3, "ImGui.CreateWindow");
    const int window = AddElementRecord(ElementKind::Window, std::string(id),
                                        std::string(title), parent);
    if (window < 0) {
        return luaL_error(state, "ImGui element capacity is exhausted");
    }
    return 0;
}

int LuaLinkWindowToElement(lua_State* state) {
    const int window = RequireElementId(state, 1, "ImGui.LinkWindowToElement");
    const int trigger = RequireElementId(state, 2, "ImGui.LinkWindowToElement");
    Element& windowElement = g_elements[static_cast<std::size_t>(window)];
    if (windowElement.kind != ElementKind::Window) {
        return luaL_error(state, "ImGui.LinkWindowToElement: first argument is not a Window");
    }
    Element& triggerElement = g_elements[static_cast<std::size_t>(trigger)];
    if (triggerElement.kind != ElementKind::MenuItem &&
        triggerElement.kind != ElementKind::Button) {
        return luaL_error(state,
                          "ImGui.LinkWindowToElement: trigger must be a MenuItem or Button");
    }
    triggerElement.linkedWindow = window;
    windowElement.parent = triggerElement.kind == ElementKind::MenuItem ? -1
                                                                        : windowElement.parent;
    return 0;
}

int LuaAddElement(lua_State* state) {
    const int parent = RequireParent(state, 1, "ImGui.AddElement");
    const std::string_view id = CheckText(state, 2, "ImGui.AddElement");
    const int type = static_cast<int>(luaL_checkinteger(state, 3));
    const ElementKind kind = MapElementType(state, type);
    const std::string_view label =
        lua_isnoneornil(state, 4) ? std::string_view{}
                                  : CheckText(state, 4, "ImGui.AddElement");
    if (!id.empty() && FindElementById(id) >= 0) {
        return luaL_error(state, "ImGui.AddElement: element '%s' already exists",
                          std::string(id).c_str());
    }
    if (AddElementRecord(kind, std::string(id), std::string(label), parent) < 0) {
        return luaL_error(state, "ImGui element capacity is exhausted");
    }
    return 0;
}

int LuaAddTabBar(lua_State* state) {
    const int parent = RequireParent(state, 1, "ImGui.AddTabBar");
    const std::string_view id = CheckText(state, 2, "ImGui.AddTabBar");
    if (id.empty() || FindElementById(id) >= 0) {
        return luaL_error(state, "ImGui.AddTabBar requires a new, non-empty id");
    }
    if (AddElementRecord(ElementKind::TabBar, std::string(id), {}, parent) < 0) {
        return luaL_error(state, "ImGui element capacity is exhausted");
    }
    return 0;
}

int LuaAddTab(lua_State* state) {
    const int parent = RequireParent(state, 1, "ImGui.AddTab");
    if (g_elements[static_cast<std::size_t>(parent)].kind != ElementKind::TabBar) {
        return luaL_error(state, "ImGui.AddTab parent must be a TabBar");
    }
    const std::string_view id = CheckText(state, 2, "ImGui.AddTab");
    const std::string_view label = CheckText(state, 3, "ImGui.AddTab");
    if (id.empty() || FindElementById(id) >= 0) {
        return luaL_error(state, "ImGui.AddTab requires a new, non-empty id");
    }
    if (AddElementRecord(ElementKind::Tab, std::string(id), std::string(label), parent) < 0) {
        return luaL_error(state, "ImGui element capacity is exhausted");
    }
    return 0;
}

int LuaAddCallback(lua_State* state) {
    const int elementIndex = RequireElementId(state, 1, "ImGui.AddCallback");
    const int type = static_cast<int>(luaL_checkinteger(state, 2));
    RequireSupportedCallbackType(state, type);
    const int reference = CheckCallback(state, 3, "ImGui.AddCallback");
    SetElementCallback(g_elements[static_cast<std::size_t>(elementIndex)],
                       static_cast<CallbackKind>(type), reference);
    return 0;
}

int LuaUpdateData(lua_State* state) {
    const int elementIndex = RequireElementId(state, 1, "ImGui.UpdateData");
    const int dataType = static_cast<int>(luaL_checkinteger(state, 2));
    Element& element = g_elements[static_cast<std::size_t>(elementIndex)];
    switch (dataType) {
        case 0:
            element.label = std::string(CheckText(state, 3, "ImGui.UpdateData"));
            return 0;
        case 1:
            switch (element.kind) {
                case ElementKind::Checkbox:
                    element.checked = lua_toboolean(state, 3) != 0;
                    return 0;
                case ElementKind::Combobox:
                    element.selectedIndex = static_cast<int>(luaL_checkinteger(state, 3));
                    return 0;
                case ElementKind::SliderInteger:
                    element.intValue = static_cast<int>(luaL_checkinteger(state, 3));
                    return 0;
                case ElementKind::InputFloat:
                    element.floatValue = static_cast<float>(luaL_checknumber(state, 3));
                    return 0;
                default:
                    return luaL_error(state,
                                      "ImGui.UpdateData(Value) is unsupported for this element");
            }
        case 2: {
            if (!lua_istable(state, 3)) {
                return luaL_error(state, "ImGui.UpdateData(ListValues) expects a table");
            }
            const auto length = lua_rawlen(state, 3);
            element.optionCount = std::min<std::size_t>(length, kMaxOptions);
            for (std::size_t index = 0; index < element.optionCount; ++index) {
                lua_rawgeti(state, 3, static_cast<lua_Integer>(index + 1));
                const char* value = luaL_checkstring(state, -1);
                element.options[index] = value != nullptr ? value : "";
                lua_pop(state, 1);
            }
            return 0;
        }
        case 3:
            element.minimum = static_cast<float>(luaL_checknumber(state, 3));
            return 0;
        case 4:
            element.maximum = static_cast<float>(luaL_checknumber(state, 3));
            return 0;
        case 5:
            element.label = std::string(CheckText(state, 3, "ImGui.UpdateData"));
            return 0;
        default:
            return luaL_error(state, "ImGuiData %d is outside the retained MGO subset",
                              dataType);
    }
}

int LuaSetAuxiliaryText(lua_State* state, bool help) {
    const char* owner = help ? "ImGui.SetHelpmarker" : "ImGui.SetTooltip";
    const int elementIndex = RequireElementId(state, 1, owner);
    const std::string_view text = CheckText(state, 2, owner);
    Element& element = g_elements[static_cast<std::size_t>(elementIndex)];
    (help ? element.help : element.tooltip) = text;
    return 0;
}

int LuaSetHelpmarker(lua_State* state) {
    return LuaSetAuxiliaryText(state, true);
}

int LuaSetTooltip(lua_State* state) {
    return LuaSetAuxiliaryText(state, false);
}

int LuaPushNotification(lua_State* state) {
    const std::string_view text = CheckText(state, 1, "ImGui.PushNotification");
    const int severity = static_cast<int>(luaL_optinteger(state, 2, 0));
    if (severity < 0 || severity > 3) {
        return luaL_error(state, "ImGui.PushNotification severity must be 0..3");
    }
    const int lifetime = static_cast<int>(luaL_optinteger(state, 3, 5000));
    if (lifetime < 0) {
        return luaL_error(state, "ImGui.PushNotification lifetime must be non-negative");
    }
    std::size_t slot = 0;
    if (g_notificationCount < kMaxNotifications) {
        slot = (g_notificationStart + g_notificationCount) % kMaxNotifications;
        ++g_notificationCount;
    } else {
        slot = g_notificationStart;
        g_notificationStart = (g_notificationStart + 1) % kMaxNotifications;
    }
    Notification& notification = g_notifications[slot];
    std::snprintf(notification.text.data(), notification.text.size(), "%.*s",
                  static_cast<int>(text.size()), text.data());
    notification.remainingMilliseconds = static_cast<std::uint32_t>(lifetime);
    notification.severity = static_cast<std::uint8_t>(severity);
    return 0;
}

int LuaAddButton(lua_State* state) {
    const int parent = RequireParent(state, 1, "ImGui.AddButton");
    const std::string_view id = CheckText(state, 2, "ImGui.AddButton");
    if (id.empty() || FindElementById(id) >= 0) {
        return luaL_error(state, "ImGui.AddButton requires a new, non-empty id");
    }
    const std::string_view label = lua_isnoneornil(state, 3)
                                       ? std::string_view{}
                                       : CheckText(state, 3, "ImGui.AddButton");
    const int callback = CheckCallback(state, 4, "ImGui.AddButton");
    const bool small = lua_toboolean(state, 5) != 0;
    (void)small;
    const int element = AddElementRecord(ElementKind::Button, std::string(id),
                                         std::string(label), parent);
    if (element < 0) {
        return luaL_error(state, "ImGui element capacity is exhausted");
    }
    if (IsCallbackReference(callback)) {
        SetElementCallback(g_elements[static_cast<std::size_t>(element)],
                           CallbackKind::Clicked, callback);
    }
    return 0;
}

int LuaAddCheckbox(lua_State* state) {
    const int parent = RequireParent(state, 1, "ImGui.AddCheckbox");
    const std::string_view id = CheckText(state, 2, "ImGui.AddCheckbox");
    if (id.empty() || FindElementById(id) >= 0) {
        return luaL_error(state, "ImGui.AddCheckbox requires a new, non-empty id");
    }
    const std::string_view label = lua_isnoneornil(state, 3)
                                       ? std::string_view{}
                                       : CheckText(state, 3, "ImGui.AddCheckbox");
    const int callback = CheckCallback(state, 4, "ImGui.AddCheckbox");
    const bool value = lua_toboolean(state, 5) != 0;
    const int element =
        AddElementRecord(ElementKind::Checkbox, std::string(id), std::string(label), parent);
    if (element < 0) {
        return luaL_error(state, "ImGui element capacity is exhausted");
    }
    g_elements[static_cast<std::size_t>(element)].checked = value;
    if (IsCallbackReference(callback)) {
        SetElementCallback(g_elements[static_cast<std::size_t>(element)],
                           CallbackKind::Edited, callback);
    }
    return 0;
}

int LuaAddCombobox(lua_State* state) {
    const int parent = RequireParent(state, 1, "ImGui.AddCombobox");
    const std::string_view id = CheckText(state, 2, "ImGui.AddCombobox");
    if (id.empty() || FindElementById(id) >= 0) {
        return luaL_error(state, "ImGui.AddCombobox requires a new, non-empty id");
    }
    const std::string_view label = lua_isnoneornil(state, 3)
                                       ? std::string_view{}
                                       : CheckText(state, 3, "ImGui.AddCombobox");
    const int callback = CheckCallback(state, 4, "ImGui.AddCombobox");
    if (!lua_istable(state, 5)) {
        return luaL_error(state, "ImGui.AddCombobox options must be a table");
    }
    const int selected = static_cast<int>(luaL_optinteger(state, 6, 0));
    const int element =
        AddElementRecord(ElementKind::Combobox, std::string(id), std::string(label), parent);
    if (element < 0) {
        return luaL_error(state, "ImGui element capacity is exhausted");
    }
    Element& record = g_elements[static_cast<std::size_t>(element)];
    const auto length = lua_rawlen(state, 5);
    record.optionCount = std::min<std::size_t>(length, kMaxOptions);
    for (std::size_t index = 0; index < record.optionCount; ++index) {
        lua_rawgeti(state, 5, static_cast<lua_Integer>(index + 1));
        const char* value = luaL_checkstring(state, -1);
        record.options[index] = value != nullptr ? value : "";
        lua_pop(state, 1);
    }
    record.selectedIndex =
        record.optionCount > 0
            ? std::clamp(selected, 0, static_cast<int>(record.optionCount) - 1)
            : 0;
    if (IsCallbackReference(callback)) {
        SetElementCallback(record, CallbackKind::Edited, callback);
    }
    return 0;
}

int LuaAddSliderInteger(lua_State* state) {
    const int parent = RequireParent(state, 1, "ImGui.AddSliderInteger");
    const std::string_view id = CheckText(state, 2, "ImGui.AddSliderInteger");
    if (id.empty() || FindElementById(id) >= 0) {
        return luaL_error(state, "ImGui.AddSliderInteger requires a new, non-empty id");
    }
    const std::string_view label = lua_isnoneornil(state, 3)
                                       ? std::string_view{}
                                       : CheckText(state, 3,
                                                   "ImGui.AddSliderInteger");
    const int callback = CheckCallback(state, 4, "ImGui.AddSliderInteger");
    const int value = static_cast<int>(luaL_optinteger(state, 5, 0));
    const int minimum = static_cast<int>(luaL_optinteger(state, 6, 0));
    const int maximum = static_cast<int>(luaL_optinteger(state, 7, 100));
    const int element = AddElementRecord(ElementKind::SliderInteger, std::string(id),
                                         std::string(label), parent);
    if (element < 0) {
        return luaL_error(state, "ImGui element capacity is exhausted");
    }
    Element& record = g_elements[static_cast<std::size_t>(element)];
    record.minimum = static_cast<float>(minimum);
    record.maximum = static_cast<float>(maximum);
    record.intValue = std::clamp(value, std::min(minimum, maximum), std::max(minimum, maximum));
    if (IsCallbackReference(callback)) {
        SetElementCallback(record, CallbackKind::Edited, callback);
    }
    return 0;
}

int LuaAddInputFloat(lua_State* state) {
    const int parent = RequireParent(state, 1, "ImGui.AddInputFloat");
    const std::string_view id = CheckText(state, 2, "ImGui.AddInputFloat");
    if (id.empty() || FindElementById(id) >= 0) {
        return luaL_error(state, "ImGui.AddInputFloat requires a new, non-empty id");
    }
    const std::string_view label = lua_isnoneornil(state, 3)
                                       ? std::string_view{}
                                       : CheckText(state, 3, "ImGui.AddInputFloat");
    const int callback = CheckCallback(state, 4, "ImGui.AddInputFloat");
    const float value = static_cast<float>(luaL_optnumber(state, 5, 0));
    const float step = static_cast<float>(luaL_optnumber(state, 6, 1));
    const float fast = static_cast<float>(luaL_optnumber(state, 7, 100));
    const int element = AddElementRecord(ElementKind::InputFloat, std::string(id),
                                         std::string(label), parent);
    if (element < 0) {
        return luaL_error(state, "ImGui element capacity is exhausted");
    }
    Element& record = g_elements[static_cast<std::size_t>(element)];
    record.floatValue = value;
    record.step = step;
    record.stepFast = fast;
    if (IsCallbackReference(callback)) {
        SetElementCallback(record, CallbackKind::Edited, callback);
    }
    return 0;
}

int LuaShow(lua_State* state) {
    if (lua_gettop(state) > 1) {
        return luaL_error(state, "ImGui.Show accepts no arguments");
    }
    g_visible = true;
    return 0;
}

int LuaHide(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "ImGui.Hide accepts no arguments");
    }
    g_visible = false;
    return 0;
}

int LuaIsVisible(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "ImGui.IsVisible accepts no arguments");
    }
    lua_pushboolean(state, g_visible ? 1 : 0);
    return 1;
}

void InstallImGuiTable(lua_State* state) {
    lua_newtable(state);
    const luaL_Reg functions[] = {
        {"CreateMenu", LuaCreateMenu},
        {"CreateWindow", LuaCreateWindow},
        {"LinkWindowToElement", LuaLinkWindowToElement},
        {"AddElement", LuaAddElement},
        {"AddTabBar", LuaAddTabBar},
        {"AddTab", LuaAddTab},
        {"AddButton", LuaAddButton},
        {"AddCheckbox", LuaAddCheckbox},
        {"AddCombobox", LuaAddCombobox},
        {"AddSliderInteger", LuaAddSliderInteger},
        {"AddInputFloat", LuaAddInputFloat},
        {"AddCallback", LuaAddCallback},
        {"UpdateData", LuaUpdateData},
        {"SetHelpmarker", LuaSetHelpmarker},
        {"SetTooltip", LuaSetTooltip},
        {"PushNotification", LuaPushNotification},
        {"Show", LuaShow},
        {"Hide", LuaHide},
        {"IsVisible", LuaIsVisible},
    };
    for (const auto& entry : functions) {
        lua_pushcfunction(state, entry.func);
        lua_setfield(state, -2, entry.name);
    }
    lua_setglobal(state, "ImGui");

    lua_getglobal(state, "Isaac");
    if (lua_istable(state, -1)) {
        lua_pushcfunction(state, LuaShow);
        lua_setfield(state, -2, "OpenConsole");
    }
    lua_pop(state, 1);
}

}  // namespace

int RegisterRepentogonImGuiApi(lua_State* state) noexcept {
    if (state == nullptr) {
        return 0;
    }
    if (g_state == state) {
        ClearRetainedState(true);
    } else {
        ClearRetainedState(false);
        g_state = state;
    }

    InstallImGuiTable(state);
    InstallEnumTable(
        state, "ImGuiElement",
        {{"Window", 0},       {"Menu", 1},          {"MenuItem", 2},
         {"Popup", 3},        {"CollapsingHeader", 4}, {"TreeNode", 5},
         {"Separator", 6},    {"SeparatorText", 7}, {"Text", 8},
         {"TextWrapped", 9},  {"BulletText", 10},   {"SameLine", 11},
         {"Button", 12},      {"SmallButton", 13},  {"InputInt", 14},
         {"InputFloat", 15},  {"DragInt", 16},      {"DragFloat", 17},
         {"SliderInt", 18},   {"SliderFloat", 19},  {"ColorEdit", 20},
         {"TabBar", 21},      {"Tab", 22},          {"Checkbox", 23},
         {"RadioButton", 24}, {"Combobox", 25},     {"InputText", 26},
         {"InputTextWithHint", 27}, {"InputTextMultiline", 28},
         {"InputController", 29}, {"InputKeyboard", 30},
         {"PlotLines", 31},   {"PlotHistogram", 32}, {"ProgressBar", 33}});
    InstallEnumTable(state, "ImGuiCallback",
                     {{"Clicked", 0}, {"Hovered", 1}, {"Active", 2}, {"Focused", 3},
                      {"Visible", 4}, {"Edited", 5}, {"Activated", 6},
                      {"Deactivated", 7}, {"DeactivatedAfterEdit", 8},
                      {"ToggledOpen", 9}, {"Render", 10}});
    InstallEnumTable(state, "ImGuiData",
                     {{"Label", 0}, {"Value", 1}, {"ListValues", 2}, {"Min", 3},
                      {"Max", 4}, {"HintText", 5}, {"ColorValues", 6}});
    InstallEnumTable(state, "ImGuiNotificationType",
                     {{"INFO", 0}, {"SUCCESS", 1}, {"WARNING", 2}, {"ERROR", 3}});
    return 0;
}

void ResetRepentogonImGui(lua_State* state) noexcept {
    if (state != nullptr && g_state != nullptr && state != g_state) {
        return;
    }
    ClearRetainedState(state != nullptr && state == g_state);
    g_state = nullptr;
}

void SetRepentogonImGuiVisible(bool visible) noexcept {
    g_visible = visible;
    if (visible) {
        if (ValidElement(g_openWindow)) {
            EnsureWindowSelection();
        } else {
            EnsureRootSelection();
        }
    }
}

bool RepentogonImGuiVisible() noexcept {
    return g_visible;
}

bool RepentogonImGuiAvailable() noexcept {
    return g_state != nullptr && g_elementCount != 0;
}

bool UpdateRepentogonImGui(const ImGuiInputFrame& input) noexcept {
    if (!g_visible) {
        return false;
    }
    UpdateNotificationLifetimes(input.elapsedMilliseconds);
    bool consumed = false;

    if (input.back) {
        if (ValidElement(g_openWindow)) {
            CloseOpenWindow();
            EnsureRootSelection();
        } else {
            g_visible = false;
        }
        consumed = true;
    } else if (ValidElement(g_openWindow)) {
        EnsureWindowSelection();
        if (input.previousTab) {
            SwitchTab(-1);
            consumed = true;
        }
        if (input.nextTab) {
            SwitchTab(1);
            consumed = true;
        }
        if (input.up) {
            const int next = NextControlIn(ContentParent(g_openWindow), g_selected, -1);
            if (next >= 0) {
                g_selected = next;
            }
            consumed = true;
        }
        if (input.down) {
            const int next = NextControlIn(ContentParent(g_openWindow), g_selected, 1);
            if (next >= 0) {
                g_selected = next;
            }
            consumed = true;
        }
        if (input.left) {
            consumed = AdjustSelected(-1) || consumed;
        }
        if (input.right) {
            consumed = AdjustSelected(1) || consumed;
        }
        if (input.accept) {
            consumed = ActivateSelected() || consumed;
        }
    } else {
        EnsureRootSelection();
        if (input.up || input.down) {
            MoveRootSelection(input.up ? -1 : 1);
            consumed = true;
        }
        if (input.accept) {
            Element* selected = ElementAt(g_selected);
            if (selected != nullptr && selected->kind == ElementKind::MenuItem) {
                OpenLinkedWindow(g_selected);
            }
            consumed = true;
        }
    }
    return consumed;
}

bool DrawRepentogonImGui(const ImGuiViewport& viewport) noexcept {
    return DrawRepentogonImGui(viewport, ImGuiDrawHooks{});
}

bool DrawRepentogonImGui(const ImGuiViewport& viewport, const ImGuiDrawHooks& hooks) noexcept {
    if (!g_visible || g_state == nullptr || viewport.width <= 0.0F || viewport.height <= 0.0F) {
        return false;
    }
    const int stackTop = lua_gettop(g_state);
    if (hooks.drawText == nullptr && stackTop != 0) {
        return false;
    }
    g_metrics.lastCallbackCalls = 0;
    g_metrics.lastTextCommands = 0;
    const std::uint64_t started = RuntimePerfTick();
    InvokeRenderCallbacks();
    const Frame frame = BuildFrame(viewport);
    const std::uint64_t finishedBuild = RuntimePerfTick();
    if (started != 0 && finishedBuild >= started) {
        const std::uint64_t micros =
            (finishedBuild - started) * 1000000ULL / RuntimePerfTicksPerSecond();
        g_metrics.lastBuildMicroseconds =
            static_cast<std::uint32_t>(std::min<std::uint64_t>(micros, UINT32_MAX));
    }
    return DrawFrame(viewport, frame, hooks);
}

ImGuiRuntimeMetrics RepentogonImGuiMetrics() noexcept {
    std::uint32_t callbacks = 0;
    for (std::size_t index = 0; index < g_elementCount; ++index) {
        for (const int reference : g_elements[index].callbackRefs) {
            if (IsCallbackReference(reference)) {
                ++callbacks;
            }
        }
    }
    g_metrics.elementCount = static_cast<std::uint32_t>(g_elementCount);
    g_metrics.callbackCount = callbacks;
    return g_metrics;
}

}  // namespace isaac::runtime
