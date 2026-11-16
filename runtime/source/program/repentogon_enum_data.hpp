// Pinned REPENTOGON Lua enums required by Reverie: Make Good Omissions.
// Source: REPENTOGON resources/scripts/enums_ex.lua, SHA-256 6937ac3c527fdffc8c07775138c499866080f1f1e66130d28bc2594b885cf2f0.
// Generated from the selected top-level tables; keep values in source order.
#pragma once

#include <cstddef>
#include <cstdint>

namespace RepentogonLuaEnumData {
struct Value { const char* key; std::int64_t value; };
struct Table { const char* name; const Value* values; std::size_t count; };

inline constexpr Value kAddHealthTypeValues[] = {
    {"NONE", 0},
    {"RED", 1},
    {"MAX", 2},
    {"SOUL", 4},
    {"BLACK", 8},
    {"ETERNAL", 16},
    {"GOLDEN", 32},
    {"BONE", 64},
    {"ROTTEN", 128},
    {"BROKEN", 256},
};

inline constexpr Value kEntityTagValues[] = {
    {"FLY", 1},
    {"SPIDER", 2},
    {"GHOST", 8},
    {"NOREROLL", 16},
    {"CANSACRIFICE", 32},
    {"EXPLOSIVE_SOUL", 64},
    {"HOMING_SOUL", 128},
    {"BRIMSTONE_SOUL", 256},
    {"NODELIRIUM", 512},
};

inline constexpr Value kFollowerPriorityValues[] = {
    {"DEFAULT", 0},
    {"SHOOTER", 1},
    {"DEFENSIVE", 2},
    {"SHOOTER_SPECIAL", 3},
    {"INCUBUS", 10},
    {"KING_BABY", 9999},
};

inline constexpr Value kGridPoopVariantValues[] = {
    {"NORMAL", 0},
    {"RED", 1},
    {"CHUNKY", 2},
    {"CORN", 2},
    {"GOLDEN", 3},
    {"RAINBOW", 4},
    {"BLACK", 5},
    {"HOLY", 6},
    {"WHITE", 6},
    {"GIANT_TL", 7},
    {"GIANT_TR", 8},
    {"GIANT_BL", 9},
    {"GIANT_BR", 10},
    {"CHARMING", 11},
};

inline constexpr Value kHealthTypeValues[] = {
    {"DEFAULT", 0},
    {"RED", 0},
    {"SOUL", 1},
    {"LOST", 2},
    {"NO_HEALTH", 2},
    {"COIN", 3},
    {"KEEPER", 3},
    {"BONE", 4},
};

inline constexpr Value kImGuiCallbackValues[] = {
    {"Clicked", 0},
    {"Hovered", 1},
    {"Active", 2},
    {"Focused", 3},
    {"Visible", 4},
    {"Edited", 5},
    {"Activated", 6},
    {"Deactivated", 7},
    {"DeactivatedAfterEdit", 8},
    {"ToggledOpen", 9},
    {"Render", 10},
};

inline constexpr Value kImGuiDataValues[] = {
    {"Label", 0},
    {"Value", 1},
    {"ListValues", 2},
    {"Min", 3},
    {"Max", 4},
    {"HintText", 5},
    {"ColorValues", 6},
};

inline constexpr Value kImGuiElementValues[] = {
    {"Window", 0},
    {"Menu", 1},
    {"MenuItem", 2},
    {"Popup", 3},
    {"CollapsingHeader", 4},
    {"TreeNode", 5},
    {"Separator", 6},
    {"SeparatorText", 7},
    {"Text", 8},
    {"TextWrapped", 9},
    {"BulletText", 10},
    {"SameLine", 11},
    {"Button", 12},
    {"SmallButton", 13},
    {"InputInt", 14},
    {"InputFloat", 15},
    {"DragInt", 16},
    {"DragFloat", 17},
    {"SliderInt", 18},
    {"SliderFloat", 19},
    {"ColorEdit", 20},
    {"TabBar", 21},
    {"Tab", 22},
    {"Checkbox", 23},
    {"RadioButton", 24},
    {"Combobox", 25},
    {"InputText", 26},
    {"InputTextWithHint", 27},
    {"InputTextMultiline", 28},
    {"InputController", 29},
    {"InputKeyboard", 30},
    {"PlotLines", 31},
    {"PlotHistogram", 32},
};

inline constexpr Value kImGuiNotificationTypeValues[] = {
    {"INFO", 0},
    {"SUCCESS", 1},
    {"WARNING", 2},
    {"ERROR", 3},
};

inline constexpr Value kMinimapStateValues[] = {
    {"NORMAL", 0},
    {"EXPANDED", 1},
    {"EXPANDED_OPAQUE", 2},
};

inline constexpr Value kMouseButtonValues[] = {
    {"LEFT", 0},
    {"RIGHT", 1},
    {"SCROLLWHEEL", 2},
    {"BACK", 3},
    {"FORWARD", 4},
};

inline constexpr Value kPauseMenuStatesValues[] = {
    {"CLOSED", 0},
    {"OPEN", 1},
    {"OPTIONS", 2},
};

inline constexpr Value kPillCardSlotValues[] = {
    {"PRIMARY", 0},
    {"SECONDARY", 1},
    {"TERTIARY", 2},
    {"QUATERNARY", 3},
};

inline constexpr Value kPlayerVariantValues[] = {
    {"PLAYER", 0},
    {"FOUND_SOUL", 1},
    {"CO_OP_BABY", 1},
};

inline constexpr Value kPocketItemTypeValues[] = {
    {"PILL", 0},
    {"CARD", 1},
    {"ACTIVE_ITEM", 2},
};

inline constexpr Value kPressurePlateVariantValues[] = {
    {"ROOM_CLEAR", 0},
    {"REWARD", 1},
    {"GREED_MODE", 2},
    {"MINES_PUZZLE", 3},
    {"RAIL_PLATE", 3},
    {"KILL_SWITCH", 9},
    {"EVENT_GROUP_0", 10},
    {"EVENT_0", 10},
    {"EVENT_GROUP_1", 11},
    {"EVENT_1", 11},
    {"EVENT_GROUP_2", 12},
    {"EVENT_2", 12},
    {"EVENT_GROUP_3", 13},
    {"EVENT_3", 13},
};

inline constexpr Value kSlotVariantValues[] = {
    {"SLOT_MACHINE", 1},
    {"BLOOD_DONATION_MACHINE", 2},
    {"TEMPERANCE_MACHINE", 2},
    {"FORTUNE_TELLING_MACHINE", 3},
    {"BEGGAR", 4},
    {"DEVIL_BEGGAR", 5},
    {"SHELL_GAME", 6},
    {"KEY_MASTER", 7},
    {"DONATION_MACHINE", 8},
    {"BOMB_BUM", 9},
    {"SHOP_RESTOCK_MACHINE", 10},
    {"GREED_DONATION_MACHINE", 11},
    {"MOMS_DRESSING_TABLE", 12},
    {"BATTERY_BUM", 13},
    {"HOME_CLOSET_PLAYER", 14},
    {"HELL_GAME", 15},
    {"CRANE_GAME", 16},
    {"CONFESSIONAL", 17},
    {"ROTTEN_BEGGAR", 18},
};

inline constexpr Table kTables[] = {
    {"AddHealthType", kAddHealthTypeValues, sizeof(kAddHealthTypeValues) / sizeof(kAddHealthTypeValues[0])},
    {"EntityTag", kEntityTagValues, sizeof(kEntityTagValues) / sizeof(kEntityTagValues[0])},
    {"FollowerPriority", kFollowerPriorityValues, sizeof(kFollowerPriorityValues) / sizeof(kFollowerPriorityValues[0])},
    {"GridPoopVariant", kGridPoopVariantValues, sizeof(kGridPoopVariantValues) / sizeof(kGridPoopVariantValues[0])},
    {"HealthType", kHealthTypeValues, sizeof(kHealthTypeValues) / sizeof(kHealthTypeValues[0])},
    {"ImGuiCallback", kImGuiCallbackValues, sizeof(kImGuiCallbackValues) / sizeof(kImGuiCallbackValues[0])},
    {"ImGuiData", kImGuiDataValues, sizeof(kImGuiDataValues) / sizeof(kImGuiDataValues[0])},
    {"ImGuiElement", kImGuiElementValues, sizeof(kImGuiElementValues) / sizeof(kImGuiElementValues[0])},
    {"ImGuiNotificationType", kImGuiNotificationTypeValues, sizeof(kImGuiNotificationTypeValues) / sizeof(kImGuiNotificationTypeValues[0])},
    {"MinimapState", kMinimapStateValues, sizeof(kMinimapStateValues) / sizeof(kMinimapStateValues[0])},
    {"MouseButton", kMouseButtonValues, sizeof(kMouseButtonValues) / sizeof(kMouseButtonValues[0])},
    {"PauseMenuStates", kPauseMenuStatesValues, sizeof(kPauseMenuStatesValues) / sizeof(kPauseMenuStatesValues[0])},
    {"PillCardSlot", kPillCardSlotValues, sizeof(kPillCardSlotValues) / sizeof(kPillCardSlotValues[0])},
    {"PlayerVariant", kPlayerVariantValues, sizeof(kPlayerVariantValues) / sizeof(kPlayerVariantValues[0])},
    {"PocketItemType", kPocketItemTypeValues, sizeof(kPocketItemTypeValues) / sizeof(kPocketItemTypeValues[0])},
    {"PressurePlateVariant", kPressurePlateVariantValues, sizeof(kPressurePlateVariantValues) / sizeof(kPressurePlateVariantValues[0])},
    {"SlotVariant", kSlotVariantValues, sizeof(kSlotVariantValues) / sizeof(kSlotVariantValues[0])},
};

inline const Table* Tables(std::size_t* count) {
    if (count != nullptr) *count = sizeof(kTables) / sizeof(kTables[0]);
    return kTables;
}
} // namespace RepentogonLuaEnumData
