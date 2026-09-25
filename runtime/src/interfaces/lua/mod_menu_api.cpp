#include "interfaces/lua/mod_menu_api.hpp"

#include "application/mod/mod_toggle_service.hpp"

#include <array>
#include <atomic>
#include <cstring>
#include "interfaces/lua/lua_integer_argument.hpp"
#include "interfaces/lua/owner_binding.hpp"

#include <string_view>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {

// 菜单脚本的里程碑位图（`Report` 写入；调试桩读它就能分辨卡在哪一步）。
std::atomic<std::uint32_t> g_ModMenuMilestones{0};
std::atomic<std::uint32_t> g_ModMenuReportCount{0};
std::atomic<std::uint32_t> g_ModMenuLastCode{0};

namespace {

constexpr char kModMenuOwner[] = "RuntimeMods";

// 菜单最多显示几个模组：与"一次能加载几个"同一个容量（`kModManifestCapacity`）。
// 扫描一次超过这个数本来就会报 `CapacityExceeded`，所以这里也不该出现更多条目。
constexpr std::size_t kMaximumMenuEntries = kModManifestCapacity;

struct MenuEntry {
    ModToggleName directory{};
    bool active{false};
};

std::array<MenuEntry, kMaximumMenuEntries> g_entries{};
std::size_t g_entryCount{0};
ModToggleService* g_toggles{nullptr};

void CopyName(ModToggleName* target, std::string_view name) noexcept {
    const std::size_t length =
        name.size() < target->size() - 1 ? name.size() : target->size() - 1;
    std::memcpy(target->data(), name.data(), length);
    (*target)[length] = '\0';
}

std::string_view LeafName(std::string_view path) noexcept {
    while (!path.empty() && path.back() == '/') {
        path.remove_suffix(1);
    }
    const std::size_t slash = path.rfind('/');
    return slash == std::string_view::npos ? path : path.substr(slash + 1);
}

std::size_t FindEntry(std::string_view directory) noexcept {
    for (std::size_t index = 0; index < g_entryCount; ++index) {
        if (directory == std::string_view(g_entries[index].directory.data())) {
            return index;
        }
    }
    return g_entryCount;
}

// `RuntimeMods.List()` -> 数组；每项 `{ Directory = <string>, Enabled = <bool>, Active = <bool> }`。
int RuntimeModsList(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "RuntimeMods.List accepts no arguments");
    }
    lua_createtable(state, static_cast<int>(g_entryCount), 0);
    for (std::size_t index = 0; index < g_entryCount; ++index) {
        const MenuEntry& entry = g_entries[index];
        const bool enabled =
            g_toggles == nullptr || g_toggles->IsEnabled(entry.directory.data());
        lua_createtable(state, 0, 3);
        lua_pushstring(state, entry.directory.data());
        lua_setfield(state, -2, "Directory");
        lua_pushboolean(state, enabled ? 1 : 0);
        lua_setfield(state, -2, "Enabled");
        lua_pushboolean(state, entry.active ? 1 : 0);
        lua_setfield(state, -2, "Active");
        lua_rawseti(state, -2, static_cast<lua_Integer>(index + 1));
    }
    return 1;
}

// `RuntimeMods.SetEnabled(directory, enabled)` -> boolean（只改内存，落盘要另调 Save）。
int RuntimeModsSetEnabled(lua_State* state) {
    if (lua_gettop(state) != 2 || lua_type(state, 1) != LUA_TSTRING ||
        lua_type(state, 2) != LUA_TBOOLEAN) {
        return luaL_error(state, "RuntimeMods.SetEnabled accepts a directory name and a boolean");
    }
    const char* directory = lua_tostring(state, 1);
    const bool enabled = lua_toboolean(state, 2) != 0;
    if (g_toggles == nullptr) {
        lua_pushboolean(state, 0);
        return 1;
    }
    // 只允许改**这一批扫描到的**模组：名字打错时不要往状态文件里塞一个永远不生效的条目。
    if (FindEntry(directory == nullptr ? std::string_view{} : std::string_view(directory)) >=
        g_entryCount) {
        return luaL_error(state, "RuntimeMods.SetEnabled: unknown mod directory");
    }
    // 只改内存：落盘由脚本显式调 `RuntimeMods.Save()`（菜单里"退出时保存"），
    // 这样"改了但没保存"是脚本能表达的状态，而不是被隐藏起来的副作用。
    const Status status = g_toggles->SetEnabled(directory, enabled);
    lua_pushboolean(state, status.ok() ? 1 : 0);
    return 1;
}

// `RuntimeMods.Save()` -> boolean：写进游戏存档分区（写完由适配器提交）。
int RuntimeModsSave(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "RuntimeMods.Save accepts no arguments");
    }
    if (g_toggles == nullptr) {
        lua_pushboolean(state, 0);
        return 1;
    }
    const Status status = g_toggles->Save();
    lua_pushboolean(state, status.ok() ? 1 : 0);
    return 1;
}

// `RuntimeMods.Report(code)` -> 无返回值：菜单脚本上报"走到哪一步"（见头文件说明）。
int RuntimeModsReport(lua_State* state) {
    if (lua_gettop(state) != 1 || !isaac::runtime::IsIntegerArgument(state, 1)) {
        return luaL_error(state, "RuntimeMods.Report accepts one integer milestone code");
    }
    const auto code = static_cast<std::uint32_t>(lua_tointeger(state, 1));
    g_ModMenuMilestones.fetch_or(1u << (code & 31u), std::memory_order_relaxed);
    g_ModMenuReportCount.fetch_add(1, std::memory_order_relaxed);
    g_ModMenuLastCode.store(code, std::memory_order_relaxed);
    return 0;
}

// `RuntimeMods.Reload()` -> boolean：从存档重新读一遍（外部改过状态文件时用）。
int RuntimeModsReload(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "RuntimeMods.Reload accepts no arguments");
    }
    if (g_toggles == nullptr) {
        lua_pushboolean(state, 0);
        return 1;
    }
    const Status status = g_toggles->Load();
    lua_pushboolean(state, status.ok() ? 1 : 0);
    return 1;
}

// 绑定表：id 的高字节是 domain（`ModMenu` = 16 ⇒ 0x10），与目录里的 `MakeId` 一一对应。
// 用这张表（而不是逐个 `lua_setfield`）是为了和别族同形：目录与实现的对应关系由
// `AttachOwnerMethods` 一处保证，门禁也按同一种形态核对。
constexpr LuaHandlerBinding kModMenuHandlers[] = {
    {0x10010001, &RuntimeModsList},
    {0x10010002, &RuntimeModsSetEnabled},
    {0x10010003, &RuntimeModsSave},
    {0x10010004, &RuntimeModsReload},
    {0x10010005, &RuntimeModsReport},
};

} // namespace

int RegisterModMenuApi(lua_State* state) noexcept {
    if (state == nullptr) {
        return 0;
    }
    lua_newtable(state);
    static_cast<void>(AttachOwnerMethods(state, kModMenuOwner, kModMenuHandlers,
                                         sizeof(kModMenuHandlers) / sizeof(kModMenuHandlers[0])));
    lua_setglobal(state, kModMenuOwner);
    return 1;
}

namespace {
//: 模组发现**是否已经出过结果**（`ModMenuPublishDiscovered` 调过一次就是 true）。
//: ★ 用于「禁成就」的 **fail-closed** 判定：还没出结果时不能当成「没有模组」，
//:   否则游戏刚起来那几秒（加载阶段）的解锁会漏过去。
bool g_discoveryDone = false;
}  // namespace

void ModMenuPublishDiscovered(const ResolvedManifestModBatch& batch) noexcept {
    g_discoveryDone = true;
    g_entryCount = 0;
    for (std::size_t index = 0; index < batch.count && g_entryCount < kMaximumMenuEntries;
         ++index) {
        const char* root = batch.mods[index].modRoot;
        const std::string_view name = LeafName(root == nullptr ? std::string_view{}
                                                              : std::string_view(root));
        if (name.empty()) {
            continue;
        }
        CopyName(&g_entries[g_entryCount].directory, name);
        g_entries[g_entryCount].active = false;
        ++g_entryCount;
    }
}

void ModMenuMarkActive(const ResolvedManifestModBatch& batch) noexcept {
    for (std::size_t index = 0; index < batch.count; ++index) {
        const char* root = batch.mods[index].modRoot;
        const std::string_view name = LeafName(root == nullptr ? std::string_view{}
                                                              : std::string_view(root));
        const std::size_t entry = FindEntry(name);
        if (entry < g_entryCount) {
            g_entries[entry].active = true;
        }
    }
}

void ModMenuAttachToggles(ModToggleService* service) noexcept {
    g_toggles = service;
}

// ---- 读面（C++ 侧访问器）：与 `RuntimeMods.List()` 同一份数据、同一套口径 ----------------
// 这三条刻意做成"薄"的：真正的口径在 `ModMenuPublishDiscovered` / `g_toggles` 那一处，
// 这里只是把它交给 C++ 调用方（原生模组页），不引入第二份判断。
std::size_t ModMenuDiscoveredCount() noexcept { return g_entryCount; }

bool ModMenuDiscoveryDone() noexcept { return g_discoveryDone; }

const char* ModMenuDiscoveredDirectory(std::size_t index) noexcept {
    return index < g_entryCount ? g_entries[index].directory.data() : nullptr;
}

bool ModMenuDiscoveredEnabled(const char* directory) noexcept {
    if (g_toggles == nullptr) {
        return true;  // 开关服务没接上 ⇒ 一律当"开着"（与 `RuntimeMods.List()` 同口径）
    }
    return g_toggles->IsEnabled(directory == nullptr ? std::string_view{}
                                                    : std::string_view(directory));
}

std::size_t ModMenuActiveCount() noexcept {
    // "实际加载"的判据 = `ModMenuMarkActive` 标出来的那批（只有真的加载了的模组才会被标）。
    // 为什么不用 `ModMenuDiscoveredEnabled`：那是**开关状态**，关掉之后要重启游戏才生效，
    // 用它会在"关了开关但还没重启"的那一局里判成"不开模组"。
    // ★ 2026-09-24 批次 107：它**不再是**「禁成就」的判据（那条改成 PC 口径的
    //   `ModMenuEnabledCount`），现在只作为读数/诊断用。
    std::size_t active = 0;
    for (std::size_t index = 0; index < g_entryCount; ++index) {
        if (g_entries[index].active) {
            ++active;
        }
    }
    return active;
}

std::size_t ModMenuEnabledCount() noexcept {
    // PC 口径：数"**处于启用状态**"的真实模组（`ModManager::AchievementsLocked()` 走的就是
    // 列表里每一项的启用位）。用 `ModMenuDiscoveredEnabled` 而不是 `g_entries[].active` ——
    // 后者是"开机时加载过"，前者是"现在开着"（页面开关一改就变，不需要重启）。
    // 两者的差别正是真机漏判的那一种情形，说明与判据都写在头文件那一段。
    std::size_t enabled = 0;
    for (std::size_t index = 0; index < g_entryCount; ++index) {
        if (ModMenuDiscoveredEnabled(g_entries[index].directory.data())) {
            ++enabled;
        }
    }
    return enabled;
}

ModMenuDiscoveredReading ModMenuDiscoveredForReading() noexcept {
    // 位图一格只装得下 32 条 —— 清单容量涨到 33 以上就得在读数那边加格。
    // 这里用 static_assert 挡住（**不许静默截断**：截断了读数会撒谎，而这一格存在的理由就是别撒谎）。
    static_assert(kMaximumMenuEntries <= 32,
                  "发现清单容量超过 32 ⇒ 位图一格装不下，状态面的 [42]/[43] 要加格");
    ModMenuDiscoveredReading reading{};
    reading.count = static_cast<std::uint32_t>(g_entryCount);
    for (std::size_t index = 0; index < g_entryCount; ++index) {
        const std::uint32_t bit = 1U << static_cast<unsigned>(index);
        // 与 `ModMenuEnabledCount()` 走**同一个** `ModMenuDiscoveredEnabled`（同一份口径，不另算一遍）。
        if (ModMenuDiscoveredEnabled(g_entries[index].directory.data())) {
            reading.enabledMask |= bit;
        }
        if (g_entries[index].active) {
            reading.activeMask |= bit;
        }
    }
    return reading;
}

// ---- 写面（C++ 侧）：与上面两个 Lua 处理器逐条同形 ------------------------------------------
bool ModMenuSetEnabled(const char* directory, bool enabled) noexcept {
    if (g_toggles == nullptr) {
        return false;
    }
    // 与 Lua 侧同一条纪律：只允许改**这一批扫描到的**模组。
    if (FindEntry(directory == nullptr ? std::string_view{} : std::string_view(directory)) >=
        g_entryCount) {
        return false;
    }
    return g_toggles->SetEnabled(directory, enabled).ok();
}

bool ModMenuSaveToggles() noexcept {
    if (g_toggles == nullptr) {
        return false;
    }
    return g_toggles->Save().ok();
}

} // namespace isaac::runtime
