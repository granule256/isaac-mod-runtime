"""零占洞后端必须：只经 entry_relay 安装、不调用旧安装器、失败不重试、无阻塞 token。

两类断言：
  * 源码契约（文本）：只经 `TryInstallEntryRelay` 安装、一个旧 IPS 安装器都不引用、
    不出现阻塞 token、不出现 `std::atomic<bool>`；
  * 行为契约（宿主机编译真实适配器 + 打桩的 entry_relay）：纯判定
    `EvaluateEntryRelayBinding` 的每条拒绝理由，以及"判定拒绝时绝不去碰
    `entry_relay`／目标字节"这条安全性质（打桩的 `TryInstallEntryRelay` 记录调用次数，
    让它成为可观测行为）。
    注意：回调表要等 Task 4 接线，所以**成功路径在此之前不可达**，驱动只覆盖
    "未接线 → 拒绝且零调用"这一段；成功路径的判定逻辑由纯函数用例直接覆盖。

"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELAY = ROOT / "runtime" / "src" / "infrastructure" / "relay"
SRC = ROOT / "runtime" / "src"
SOURCE = ROOT / "runtime" / "source"

# 安装路径上禁止出现的阻塞 token（`smInitialize`/`fsInitialize`/`fopen(`），
# 以及本项目对 libnx/exlaunch 头与 bool 原子量的两道门禁。
FORBIDDEN_TOKENS = ("smInitialize", "fsInitialize", "fopen(", "lib/nx", "<switch.h>",
                    "std::atomic<bool>")


def forbidden_tokens_in(text):
    """返回 text 里命中的被禁 token。扫描判据抽成纯函数，本文件的
    `test_forbidden_token_scan_has_teeth` 会用反例证明它不是恒真断言。"""
    return [token for token in FORBIDDEN_TOKENS if token in text]


class EntryRelayAdapterContractTests(unittest.TestCase):
    def test_adapter_only_installs_through_entry_relay(self):
        text = (RELAY / "entry_relay_hook_adapter.cpp").read_text(encoding="utf-8")
        self.assertIn("TryInstallEntryRelayWithPublisher(", text)
        for legacy in ("TryInstallManagerUpdateHook", "TryInstallManagerRenderHook",
                       "TryInstallPreGetCollectibleRelay", "TryInstallManagerPresentRelay",
                       "TryInstallRebuildMountPointsRelay"):
            self.assertNotIn(legacy, text, f"零占洞后端不得引用旧 IPS 安装器 {legacy}")

    def test_adapter_has_no_blocking_tokens_and_no_bool_atomics(self):
        sources = sorted(RELAY.glob("*.cpp"))
        self.assertTrue(sources, "relay 目录下必须有适配器实现，空集合会让本测试恒真")
        for file in sources:
            text = file.read_text(encoding="utf-8")
            for token in forbidden_tokens_in(text):
                self.fail(f"{file} 含被禁 token {token}")

    def test_adapter_maps_failure_without_retry(self):
        text = (RELAY / "entry_relay_hook_adapter.cpp").read_text(encoding="utf-8")
        self.assertIn("EntryRelayFailure::WriteVerifyFailed", text,
                      "WriteVerifyFailed 是不可恢复语义，必须显式处理而不是重试")
        body = text.split("Status EntryRelayHookAdapter::Install")[1]
        # ★ 批次 396（2026-10-07）：**必须只取 `Install` 这一个函数体**。
        #   批次 385 在同文件后半加了**另一条平行路径** `TryInstallEntryRelayEarly`（早装），
        #   它里面也有一次 `TryInstallEntryRelay(`。不切开就会把两个函数的计数混在一起
        #   ⇒ 这条断言从 385 起就恒假（1 → 2）。判据本身没变：仍是"每个挂点只尝试安装一次、
        #   失败即返回、不得循环重试"，只是把范围钉到它真正要检的那个函数上。
        body = body.split("bool EntryRelayHookAdapter::IsInstalled")[0]
        self.assertNotIn("for (", body, "安装失败不得重试")
        self.assertNotIn("while (", body, "安装失败不得重试")
        self.assertEqual(body.count("TryInstallEntryRelayWithPublisher("), 1,
                         "每个挂点只允许尝试安装一次（失败即返回，不得循环重试）")

    def test_pure_evaluator_is_host_testable(self):
        header = (RELAY / "entry_relay_binding.hpp").read_text(encoding="utf-8")
        self.assertIn("EvaluateEntryRelayBinding", header)
        self.assertIn("constexpr", header)
        # 地址判定必须是编译期可求值的 constexpr（宿主机测试与编译期自证共用同一份逻辑）
        self.assertIn("constexpr bool IsHookableEntryAddress(", header)
        self.assertIn("static_assert(!IsHookableEntryAddress(", header,
                      "纯判定必须带反例自证，否则无法证明判据不是恒真")
        for token in ("svcQueryMemory", "RwPages", "mrs "):
            self.assertNotIn(token, header, "纯判定头不得碰系统")

    def test_forbidden_token_scan_has_teeth(self):
        """自证：扫描判据必须对反例报错，否则上面那条测试是空断言。"""
        self.assertEqual(forbidden_tokens_in("int main() { return 0; }"), [])
        self.assertEqual(forbidden_tokens_in("\tauto flag = std::atomic<bool>{};\n"),
                         ["std::atomic<bool>"])
        self.assertIn("fopen(", forbidden_tokens_in('FILE* f = fopen("a", "rb");'))
        self.assertIn("smInitialize", forbidden_tokens_in("smInitialize();"))
        # 常量表本身不许被悄悄缩水
        for token in ("smInitialize", "fsInitialize", "fopen(", "std::atomic<bool>"):
            self.assertIn(token, FORBIDDEN_TOKENS)

    def test_ledger_constants_come_from_the_shared_ledger(self):
        """入口型挂点必须引用台账里的既有常量名，不得自造第二套真值源。"""
        text = (RELAY / "entry_relay_hook_adapter.cpp").read_text(encoding="utf-8")
        for constant in ("kManagerUpdateFileOffset", "kManagerUpdateExpectedBytes",
                         "kManagerRenderFileOffset", "kManagerRenderExpectedBytes",
                         "kPreGetCollectibleRelayOffset",
                         "kPreGetCollectibleRelayExpectedOriginal",
                         "kRebuildContentMountPointsOffset",
                         "kRebuildContentMountPointsExpectedBytes",
                         # 批次 102 的四路事件中继
                         "kEntityPlayerUseActiveItemOffset",
                         "kEntityPlayerUseActiveItemExpectedBytes",
                         "kEntityPlayerUseCardOffset",
                         "kEntityPlayerUseCardExpectedBytes",
                         "kEntityPlayerUsePillOffset",
                         "kEntityPlayerUsePillExpectedBytes",
                         "kGameExitOffset",
                         "kGameExitExpectedBytes",
                         # 批次 103 的掉落物碰撞中继
                         "kEntityPickupHandleCollisionOffset",
                         "kEntityPickupHandleCollisionExpectedBytes",
                         # 批次 104 的房间生成实体中继
                         "kRoomSpawnEntityOffset",
                         "kRoomSpawnEntityExpectedBytes"):
            self.assertIn(constant, text, f"绑定表必须引用台账常量 {constant}")

    def test_adapter_does_not_extend_the_port(self):
        """`LastFailureCode()` 是本适配器的自有诊断接口，不得动 `IHookPort`。"""
        port = (SRC / "ports" / "hook_port.hpp").read_text(encoding="utf-8")
        self.assertNotIn("LastFailureCode", port, "端口接口不因诊断信息而改动")
        header = (RELAY / "entry_relay_hook_adapter.hpp").read_text(encoding="utf-8")
        self.assertIn("LastFailureCode", header)
        self.assertIn("public IHookPort", header)


ADAPTER_DRIVER = r"""
#include "infrastructure/relay/entry_relay_hook_adapter.hpp"
#include "relay/smart_pointer_shim.hpp"
// 批次 397：桩函数的签名要用 `RelayVector2Hfa`（`FireTear` 的按值 HFA 形参）⇒ 需要常量头。
// 适配器实现本身也 include 它，所以这里引同一个头是与生产构建一致的写法。
#include "runtime_constants.hpp"
#include "relay/entry_relay.hpp"

#include <cstdint>
#include <cstdio>

using isaac::runtime::BindingVerdict;
using isaac::runtime::EntryRelayBinding;
using isaac::runtime::EntryRelayFallbackEntry;
using isaac::runtime::EntryRelayHookAdapter;
using isaac::runtime::EvaluateEntryRelayBinding;
using isaac::runtime::HookId;
using isaac::runtime::HookTarget;
using isaac::runtime::Original;
using isaac::runtime::StatusCode;

// ---- entry_relay 的打桩实现：只用于观察适配器怎么调用它 ----
namespace isaac::runtime::relay {

bool g_stubResult = false;
std::uint32_t g_stubFailure = 0;
isaac::runtime::HookId g_expectedPublishedHook = isaac::runtime::HookId::ImagePcxLoad;
bool g_originalVisibleWhenArmed = false;
std::size_t g_stubCalls = 0;
std::uintptr_t g_stubTarget = 0;
std::uintptr_t g_stubCallback = 0;
const void* g_stubExpected = nullptr;
void (*g_afterPublication)() = nullptr;

bool TryInstallEntryRelay(std::uintptr_t target, const void* expectedEntry16,
                          std::uintptr_t callback, std::uintptr_t* outOriginalEntry) {
    ++g_stubCalls;
    g_stubTarget = target;
    g_stubExpected = expectedEntry16;
    g_stubCallback = callback;
    if (!g_stubResult) {
        return false;
    }
    *outOriginalEntry = 0x7100A00020u;  // 槽 + kSlotFallbackOffset
    g_originalVisibleWhenArmed = isaac::runtime::EntryRelayFallbackEntry(g_expectedPublishedHook) == *outOriginalEntry;
    return true;
}

bool TryInstallEntryRelayWithPublisher(std::uintptr_t target,const void* expected,
    std::uintptr_t callback,EntryRelayOriginalPublisher publish,void* context,std::uintptr_t* out) {
    if (!TryInstallEntryRelay(target,expected,callback,out)) return false;
    if (!publish(*out,context)) {g_stubFailure=ToFailureCode(EntryRelayFailure::OriginalPublicationRejected);return false;}
    if (g_afterPublication != nullptr) g_afterPublication();
    return true;
}

std::size_t InstalledCount() { return g_stubResult ? 1u : 0u; }
std::uint32_t LastFailure() { return g_stubFailure; }

}  // namespace isaac::runtime::relay

// `RegisterEntryRelayCallbacks`（entry_relay_hook_adapter.cpp）把四路回调接成
// `EntryRelayManagerUpdateCallback` / `EntryRelayManagerRenderCallback` /
// `EntryRelayPreGetCollectibleCallback` / `EntryRelayRebuildMountPointsCallback`，这些符号在真实构建里
// 由 hook_manager.cpp 定义；本宿主机驱动只编译适配器本身，故在此提供桩定义，仅用于满足链接
// （驱动**不调用**注册函数，所以四个回调槽仍为空 —— 这正是下面"未接线必须被拒绝"用例的前提）。
extern "C" void EntryRelayManagerRenderCallback(void* self) {
    (void)self;
}

extern "C" void EntryRelayManagerUpdateCallback(void* self) {
    (void)self;
}

extern "C" std::uint32_t EntryRelayPreGetCollectibleCallback(void* itemPool, std::uint32_t itemPoolType,
                                                             std::uint32_t seed,
                                                             std::uint32_t noDecrease,
                                                             std::uint32_t defaultItem) {
    (void)itemPool;
    (void)itemPoolType;
    (void)seed;
    (void)noDecrease;
    (void)defaultItem;
    return 0;
}

extern "C" void EntryRelayRebuildMountPointsCallback() {}

// 批次 102 加的四路事件中继（同样只编译适配器 ⇒ 桩定义满足链接）。
extern "C" void EntryRelayPressurePlateAnimationCallback(void*,bool){}

extern "C" std::uint64_t EntryRelayUseActiveItemCallback(void* player, std::uint32_t item,
                                                std::uint32_t useFlags, std::int32_t activeSlot,
                                                std::int32_t customVarData) {
    (void)player;
    (void)item;
    (void)useFlags;
    (void)activeSlot;
    (void)customVarData;
    return 0;
}

extern "C" void EntryRelayUseCardCallback(void* player, std::uint32_t card,
                                          std::uint32_t useFlags) {
    (void)player;
    (void)card;
    (void)useFlags;
}

extern "C" void EntryRelayUsePillCallback(void* player, std::uint32_t pillEffect,
                                          std::uint32_t pillColor, std::uint32_t useFlags) {
    (void)player;
    (void)pillEffect;
    (void)pillColor;
    (void)useFlags;
}

extern "C" void EntryRelayGameExitCallback(void* game, std::uint32_t shouldSave) {
    (void)game;
    (void)shouldSave;
}

extern "C" std::uint64_t EntryRelayPickupCollisionCallback(void* pickup, void* collider,
                                                  std::uint32_t low) {
    (void)pickup;
    (void)collider;
    (void)low;
    return 0;
}

extern "C" std::uint64_t EntryRelayRoomEntitySpawnCallback(void* room, std::uint32_t gridIndex,
                                                  const void* entry, std::uint32_t seed,
                                                  void** outEntity, std::uint32_t flags) {
    (void)room;
    (void)gridIndex;
    (void)entry;
    (void)seed;
    (void)outEntity;
    (void)flags;
    return 0;
}

// 贴图桥（2026-09-21）：`.pcx` 缺失而同名 `.png` 存在时在内存里转码兜底。宿主驱动只验证接线，
// 不跑真机逻辑，所以桩直接返回 false（即「不接管」）。
extern "C" bool EntryRelayImagePcxLoadCallback(void* self, const char* path) {
    (void)self;
    (void)path;
    return false;
}

// 贴图桥 v2（2026-09-21）：返回 16 字节 SmartPointer（sret）。桩全零 = 「空指针、未接管」；
// 垫片类型的形状由 hook_catalog/adapter 的声明一致性测试另行钉住。
// 注意：宿主桩也必须用同一垫片类型（`isaac::runtime::relay::SmartPointerShim`），
// 否则 sret ABI 对不上。
#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wreturn-type-c-linkage"
#endif
extern "C" isaac::runtime::relay::SmartPointerShim EntryRelayImageManagerLoadFileCallback(
    void* self, const char* path, void* descriptor, int flag) {
    (void)self;
    (void)path;
    (void)descriptor;
    (void)flag;
    return {};
}
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

// 贴图桥 v4：IContentManager::GetMountedFilePath。桩返回空（文件不在任何挂载点），
// 驱动只验证接线，不跑真机逻辑。
extern "C" char* EntryRelayContentGetMountedFilePathCallback(void* self, const char* path) {
    (void)self;
    (void)path;
    return nullptr;
}

// 批次 077（模组页搬生产）：三个入口中继的桩。夹具同样只验证接线（`g_hookCallbacks`
// 里那三格应当等于这三个函数的地址），不跑真机逻辑 —— 它们是"尾调用入口桩"，
// 真实实现要求"原函数跑过、状态没变"，在宿主机上无法成立。
extern "C" void EntryRelayMenuGameRenderCallback(void* self) { (void)self; }
extern "C" void EntryRelayMenuTitleRenderCallback(void* self) { (void)self; }
extern "C" void EntryRelayMenuManagerSetStateCallback(void* self, std::int32_t state) {
    (void)self;
    (void)state;
}

// 批次 098（成就闸门，挂 `SetReadOnly`）：同一个入口中继。夹具同样只验证接线
// （`g_hookCallbacks` 那一格应当等于这个函数的地址），不跑真机逻辑 ——
// 它要求"调引擎原函数"，宿主机上没有。
extern "C" void EntryRelayPersistentGameDataSetReadOnlyCallback(void* self,
                                                               std::uint32_t readOnly) {
    (void)self;
    (void)readOnly;
}

// 批次 147（模组 content 加载闸门，挂 `ModManager::LoadConfigs` 入口）：夹具同样只验证接线
// （`g_hookCallbacks` 那一格应当等于这个函数的地址），不跑真机逻辑 ——
// 它要求"读引擎的 `ModEntry` 表 + 调原函数"，宿主机上没有。
extern "C" void EntryRelayModManagerLoadConfigsCallback(void* self) { (void)self; }

// 批次 363（`ANM2::Load` 入口中继）：同样只满足链接（夹具只验证接线 —— `g_hookCallbacks`
// 那一格应当等于这个函数的地址），不跑真机逻辑：它要读引擎的挂载点表与动画缓存，
// 宿主机上没有那些东西。
extern "C" void EntryRelayAnm2LoadCallback(void* anm2, const void* name,
                                           std::uint32_t loadGraphics) {
    (void)anm2;
    (void)name;
    (void)loadGraphics;
}

// 批次 390（2026-10-07，`MC_INPUT_ACTION` 的三条查询中继）：★ 那批**漏了这三个桩**，
// 于是这个用例从 390 起就是"链接失败"的存量红（`--only hook_` 匹配不到本模块名，没人发现）。
// 批次 396 一并补齐：同 Anm2Load 一样，只满足链接（夹具只验证 `g_hookCallbacks` 那一格
// 等于这个函数的地址），不跑真机逻辑。
extern "C" bool EntryRelayManagerIsActionPressedCallback(void* manager, std::uint32_t action,
                                                         std::uint32_t controller,
                                                         void* entity) {
    (void)manager; (void)action; (void)controller; (void)entity; return false;
}
extern "C" bool EntryRelayManagerIsActionTriggeredCallback(void* manager, std::uint32_t action,
                                                           std::uint32_t controller,
                                                           void* entity) {
    (void)manager; (void)action; (void)controller; (void)entity; return false;
}
extern "C" float EntryRelayManagerGetActionValueCallback(void* manager, std::uint32_t action,
                                                         std::uint32_t controller,
                                                         void* entity) {
    (void)manager; (void)action; (void)controller; (void)entity; return 0.0F;
}

// 批次 396（2026-10-07，`MC_ENTITY_TAKE_DMG` 的四条 + `MC_EVALUATE_CACHE`）：同样只满足链接。
// 真机逻辑要读引擎实体（`ReadEntityIdentity`）与玩家缓存掩码，宿主机上没有那些东西。
extern "C" std::uint64_t EntryRelayEntityTakeDamageCallback(void* entity, float amount,
                                                            std::uint64_t damageFlags,
                                                            const void* sourceRef,
                                                            std::int32_t countdownFrames) {
    (void)entity; (void)amount; (void)damageFlags; (void)sourceRef; (void)countdownFrames;
    return 0;
}
extern "C" std::uint64_t EntryRelayEntityPlayerTakeDamageCallback(void* entity, float amount,
                                                                  std::uint64_t damageFlags,
                                                                  const void* sourceRef,
                                                                  std::int32_t countdownFrames) {
    (void)entity; (void)amount; (void)damageFlags; (void)sourceRef; (void)countdownFrames;
    return 0;
}
extern "C" std::uint64_t EntryRelayEntityPickupTakeDamageCallback(void* entity, float amount,
                                                                  std::uint64_t damageFlags,
                                                                  const void* sourceRef,
                                                                  std::int32_t countdownFrames) {
    (void)entity; (void)amount; (void)damageFlags; (void)sourceRef; (void)countdownFrames;
    return 0;
}
extern "C" std::uint64_t EntryRelayEntitySlotTakeDamageCallback(void* entity, float amount,
                                                                std::uint64_t damageFlags,
                                                                const void* sourceRef,
                                                                std::int32_t countdownFrames) {
    (void)entity; (void)amount; (void)damageFlags; (void)sourceRef; (void)countdownFrames;
    return 0;
}
extern "C" void EntryRelayEvaluateItemsCallback(void* player) { (void)player; }

// 批次 397（2026-10-07，补全回调第 2 批）：同样只满足链接（夹具只验证 `g_hookCallbacks` 那一格
// 等于这个函数的地址）。真机逻辑要读引擎实体（`ReadEntityIdentity`）与游戏结束状态，宿主机上没有。
extern "C" void EntryRelayEntityPlayerInitCallback(void*,std::uint32_t,std::uint32_t,std::uint32_t,std::uint32_t) {}
extern "C" void EntryRelayGameStartStageTransitionCallback(void*,bool,int,void*) {}
extern "C" void EntryRelayEntityKillCallback(void* entity) { (void)entity; }
#include "room_spawn_internal_hook.hpp"
namespace isaac::runtime {
std::uint32_t RoomFixSpawnCtorInternalCallback(relay::InternalHookContext&,const void*) noexcept {return 0;}
static std::uintptr_t g_managerOriginal=0;
bool PublishManagerUpdateEntryRelayOriginal(std::uintptr_t original)noexcept{g_managerOriginal=original;return true;}
// 本夹具不执行UseActiveItem；实际五处安装及失败由专用测试覆盖。
bool TryInstallUseItemNativeBoundaries(const HookTarget&)noexcept{return false;}
}
extern "C" std::uint64_t EntryRelayFamiliarCollisionCallback(void*, void*, std::uint32_t) { return 0; }
extern "C" std::uint64_t EntryRelayNpcCollisionCallback(void*, void*, std::uint32_t) { return 0; }
extern "C" std::uint64_t EntryRelayPlayerCollisionCallback(void*, void*, std::uint32_t) { return 0; }
extern "C" std::uint64_t EntryRelayTearCollisionCallback(void*, void*, std::uint32_t) { return 0; }
extern "C" std::uint64_t EntryRelayProjectileCollisionCallback(void*, void*, std::uint32_t) { return 0; }
extern "C" std::uint64_t EntryRelayKnifeCollisionCallback(void*, void*, std::uint32_t) { return 0; }
extern "C" std::uint64_t EntryRelayBombCollisionCallback(void*, void*, std::uint32_t) { return 0; }
extern "C" std::int32_t EntryRelayItemPoolGetPillCallback(void*, std::uint32_t) { return 0; }
extern "C" std::int32_t EntryRelayItemPoolGetPillEffectCallback(void*, std::uint32_t, void*) { return 0; }
extern "C" std::uint64_t EntryRelayGameDevolveEnemyCallback(void*, void*) { return 0; }
extern "C" void* EntryRelayGameSpawnExCallback(void*, std::int32_t, std::uint32_t, const void*, const void*, void*, std::uint32_t, std::uint32_t, std::uint32_t) { return nullptr; }
extern "C" void EntryRelayNpcRenderCallback(void*, const void*) {}
extern "C" void EntryRelayNpcDeathRemoveCallback(void* npc, void* forwarded) {
    (void)npc;
    (void)forwarded;
}
extern "C" void EntryRelayGameEndCallback(void* game, std::int32_t ending) {
    (void)game;
    (void)ending;
}
extern "C" void* EntryRelayFireTearCallback(void* player, const void* position,
                                            RelayVector2Hfa velocity, std::uint32_t flags,
                                            void* source, float damageMultiplier) {
    (void)player; (void)position; (void)velocity; (void)flags; (void)source; (void)damageMultiplier;
    return nullptr;
}

// 适配器里 `RebuildMountPoints` 那一格会把安装结果交给贴图桥的记账函数
// （批次 357；定义在 `source/image_pcx_bridge_hook.cpp`）。夹具只编译适配器本身，
// 所以这里同样给一个桩满足链接 —— 它不参与任何判定。
namespace isaac::runtime::bridge {
void NoteRebuildMountPointsEntryRelay(bool installed, unsigned failureCode) noexcept {
    (void)installed;
    (void)failureCode;
}
// 适配器里 `Anm2Load` 那一格同样会把安装结果交给记账函数
// （批次 365；定义在 `source/anm2_load_override_hook.cpp`。批次 363 只定义、没有调用点
//  ⇒ 读数里"中继装上没有"恒写"未试"，是 2026-10-05 真机读数当场抓到的自相矛盾）。
// 夹具只编译适配器本身，所以这里同样给一个桩满足链接 —— 它不参与任何判定。
void NoteAnm2LoadRelayInstalled(bool installed, unsigned failureCode) noexcept {
    (void)installed;
    (void)failureCode;
}
}  // namespace isaac::runtime::bridge

static int g_failures = 0;

static void Check(bool condition, const char* label) {
    if (!condition) {
        std::printf("FAIL %s\n", label);
        ++g_failures;
    }
}

int main() {
    const std::uint8_t expected[16] = {0xFD, 0x7B, 0xBF, 0xA9, 0xFD, 0x03, 0x00, 0x91,
                                       0x08, 0x98, 0x8D, 0x52, 0x68, 0x00, 0xA0, 0x72};
    std::uintptr_t fallback = 0;
    HookTarget target{};
    target.base = 0x7100000000u;
    target.codeSize = 0x700000u;
    target.imageSize = 0x800000u;

    EntryRelayHookAdapter adapter;
    Check(!adapter.IsInstalled(HookId::ManagerUpdate), "初始未安装");
    Check(EntryRelayFallbackEntry(HookId::ManagerUpdate) == 0, "未安装时没有回退入口");
    Check(EntryRelayFallbackEntry(HookId::Count) == 0, "越界 HookId 取回退入口必须为 0");
    Check(static_cast<void (*)()>(Original<void (*)()>(HookId::ManagerUpdate)) == nullptr,
          "Original<Fn>() 必须能把回退入口转成函数指针（此处为 0）");

    // 回调未接线：必须响亮失败，并且**一次都不许调用 entry_relay**（目标字节保持原样）。
    isaac::runtime::relay::g_stubCalls = 0;
    const auto unwired = adapter.Install(HookId::ManagerUpdate, target);
    Check(unwired.code() == StatusCode::Rejected, "回调未接线必须被拒绝");
    Check(isaac::runtime::relay::g_stubCalls == 0,
          "回调未接线时不得触碰 entry_relay / 目标字节");
    Check(adapter.LastFailureCode() == 1, "拒绝时失败码 = 1（InvalidAddress 口径）");
    Check(!adapter.IsInstalled(HookId::ManagerUpdate), "拒绝后不得报告已安装");

    // ManagerPresent 的靶点是 `bl` 调用点，本后端不实现（走 GOT 槽改写）。
    isaac::runtime::relay::g_stubCalls = 0;
    const auto present = adapter.Install(HookId::ManagerPresent, target);
    Check(present.code() == StatusCode::Rejected, "ManagerPresent 不属于本后端");
    Check(isaac::runtime::relay::g_stubCalls == 0, "ManagerPresent 不得调用 entry_relay");
    Check(adapter.LastFailureCode() == 1, "ManagerPresent 拒绝时失败码 = 1");

    isaac::runtime::relay::g_stubCalls = 0;
    Check(adapter.Install(HookId::RoomEntitySpawn,target).code() == StatusCode::Rejected,
          "71内部上下文ABI不能绕过routing安装到旧Roomspawn入口");
    Check(isaac::runtime::relay::g_stubCalls == 0 && adapter.LastFailureCode() == 1 &&
          !adapter.IsInstalled(HookId::RoomEntitySpawn) && EntryRelayFallbackEntry(HookId::RoomEntitySpawn) == 0,
          "旧后端直接调用71必须拒绝且不改入口/回退记录");

    // 非法 id 是参数错误；空 target 走纯判定 → Rejected（失败码 1），同样不碰 entry_relay。
    Check(adapter.Install(HookId::Count, target).code() == StatusCode::InvalidArgument,
          "HookId::Count 是参数错误");
    HookTarget empty{};
    isaac::runtime::relay::g_stubCalls = 0;
    Check(adapter.Install(HookId::ManagerUpdate, empty).code() == StatusCode::Rejected,
          "空 target 必须被拒绝");
    Check(isaac::runtime::relay::g_stubCalls == 0, "空 target 不得触碰 entry_relay");
    Check(adapter.LastFailureCode() == 1, "空 target 拒绝时失败码 = 1");

    // ---- 纯判定：每条拒绝理由都要能被反例触发 ----
    const EntryRelayBinding good{"Manager::Update", 0x3F8DB8u, expected,
                                 reinterpret_cast<void*>(0x7100055120u), &fallback};
    std::uintptr_t address = 0;
    Check(EvaluateEntryRelayBinding(good, target, &address) == BindingVerdict::Ok,
          "合法绑定必须通过");
    Check(address == target.base + 0x3F8DB8u, "判定的产物是 base + offset");

    EntryRelayBinding broken = good;
    broken.callback = nullptr;
    Check(EvaluateEntryRelayBinding(broken, target, &address) == BindingVerdict::Rejected,
          "回调未接线必须拒绝");
    broken = good;
    broken.expectedEntry16 = nullptr;
    Check(EvaluateEntryRelayBinding(broken, target, &address) == BindingVerdict::Rejected,
          "缺版本 guard 必须拒绝");
    broken = good;
    broken.fallbackEntry = nullptr;
    Check(EvaluateEntryRelayBinding(broken, target, &address) == BindingVerdict::Rejected,
          "缺回退入口存储必须拒绝");
    broken = good;
    broken.offset = 0;
    Check(EvaluateEntryRelayBinding(broken, target, &address) == BindingVerdict::Rejected,
          "offset 0 必须拒绝");
    Check(EvaluateEntryRelayBinding(good, target, nullptr) == BindingVerdict::Rejected,
          "缺输出参数必须拒绝");
    broken = good;
    broken.offset = 0x3F8DBAu;  // 未 4 字节对齐的入口
    Check(EvaluateEntryRelayBinding(broken, target, &address) == BindingVerdict::Rejected,
          "入口必须 4 字节对齐");
    broken = good;
    broken.offset = 0xFF8u;  // 16 字节跨页（与 entry_relay 的门禁一致）
    Check(EvaluateEntryRelayBinding(broken, target, &address) == BindingVerdict::Rejected,
          "入口 16 字节不得跨 4 KiB 页");
    broken = good;
    broken.offset = 0x700000u;  // 正好落在代码窗口之外
    Check(EvaluateEntryRelayBinding(broken, target, &address) == BindingVerdict::Rejected,
          "入口必须落在代码窗口内");
    HookTarget nullBase{};
    nullBase.codeSize = 0x700000u;
    Check(EvaluateEntryRelayBinding(good, nullBase, &address) == BindingVerdict::Rejected,
          "base 为 0 必须拒绝");
    HookTarget noCode{};
    noCode.base = 0x7100000000u;
    Check(EvaluateEntryRelayBinding(good, noCode, &address) == BindingVerdict::Rejected,
          "codeSize 为 0 必须拒绝");
    HookTarget wrapping{};
    wrapping.base = 0xFFFFFFFFFFFFFF00u;
    wrapping.codeSize = 0x700000u;
    Check(EvaluateEntryRelayBinding(good, wrapping, &address) == BindingVerdict::Rejected,
          "地址回绕必须拒绝");

    isaac::runtime::RegisterEntryRelayCallbacks();
    const HookId inputIds[]={HookId::ManagerIsActionPressed,HookId::ManagerIsActionTriggered,HookId::ManagerGetActionValue};
    const std::uintptr_t inputOffsets[]={kManagerIsActionPressedOffset,kManagerIsActionTriggeredOffset,kManagerGetActionValueOffset};
    const void* inputGuards[]={kManagerIsActionPressedExpectedBytes.data(),kManagerIsActionTriggeredExpectedBytes.data(),kManagerGetActionValueExpectedBytes.data()};
    for(unsigned i=0;i<3;++i){
        static_cast<void>(adapter.Install(inputIds[i],target));
        Check(isaac::runtime::relay::g_stubTarget==target.base+inputOffsets[i] &&
              isaac::runtime::relay::g_stubExpected==inputGuards[i],
              "输入必须拦Manager高层并保留Entity实参，而不是底层unsigned*出参");
    }
    isaac::runtime::relay::g_stubResult=true;
    Check(adapter.Install(HookId::GameStartStageTransition,target).ok() &&
          adapter.IsInstalled(HookId::GameStartStageTransition),
          "首层沙漏过渡必须实际安装到新入口中继");
    Check(isaac::runtime::relay::g_stubTarget==target.base+kApi200GameStartStageTransitionOffset &&
          isaac::runtime::relay::g_stubExpected==kApi200GameStartStageTransitionExpectedBytes.data() &&
          isaac::runtime::relay::g_stubCallback==reinterpret_cast<std::uintptr_t>(&EntryRelayGameStartStageTransitionCallback) &&
          EntryRelayFallbackEntry(HookId::GameStartStageTransition)==0x7100A00020u,
          "新入口偏移、16字节、回调ABI与回退槽必须全部接线");
    isaac::runtime::relay::g_afterPublication=+[]{
        Check(EntryRelayFallbackEntry(HookId::ManagerUpdate)==0x7100A00020u &&
              isaac::runtime::g_managerOriginal==0x7100A00020u,
              "入口可达时registry与ManagerUpdate::Orig已经发布");
    };
    std::uintptr_t roomOut=0x1234;
    isaac::runtime::relay::g_stubCalls=0;
    Check(!isaac::runtime::TryInstallEntryRelayEarly(HookId::RoomEntitySpawn,target,&roomOut) &&
          isaac::runtime::relay::g_stubCalls==0 && roomOut==0x1234 &&
          EntryRelayFallbackEntry(HookId::RoomEntitySpawn)==0 && !isaac::runtime::EntryRelayInstalledEarly(HookId::RoomEntitySpawn),
          "71禁止early旧ABI安装且不许写任何安装内容");
    isaac::runtime::relay::g_stubResult=true;
    Check(adapter.Install(HookId::ManagerUpdate,target).ok() && adapter.IsInstalled(HookId::ManagerUpdate),
          "ManagerUpdate在publisher发布后完成安装");

    if (g_failures == 0) {
        std::printf("ADAPTER_DRIVER_OK\n");
    }
    return g_failures == 0 ? 0 : 1;
}
"""


class EntryRelayAdapterBehaviorTests(unittest.TestCase):
    """在宿主机上编译**真实的适配器实现**，用打桩的 entry_relay 观察它的行为。"""

    @classmethod
    def setUpClass(cls):
        if shutil.which("c++") is None:
            raise unittest.SkipTest("宿主机没有 c++，无法编译纯判定与适配器行为测试")
        cls._temporary = tempfile.TemporaryDirectory(prefix="isaac-entry-relay-adapter-")
        directory = Path(cls._temporary.name)
        driver = directory / "adapter_driver.cpp"
        driver.write_text(ADAPTER_DRIVER.lstrip(), encoding="utf-8")
        binary = directory / "adapter_driver"
        build = subprocess.run(
            ["c++", "-std=c++23", "-Wall", "-Wextra", "-Werror",
             "-I", str(SRC), "-I", str(SOURCE),
             str(driver), str(RELAY / "entry_relay_hook_adapter.cpp"),
             "-o", str(binary)],
            text=True, capture_output=True,
        )
        if build.returncode != 0:
            raise AssertionError(f"适配器在宿主机上编译失败：\n{build.stdout}{build.stderr}")
        cls._run = subprocess.run([str(binary)], text=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "_temporary", None) is not None:
            cls._temporary.cleanup()

    def test_adapter_behavior_on_the_host(self):
        self.assertEqual(self._run.returncode, 0, self._run.stdout + self._run.stderr)
        self.assertIn("ADAPTER_DRIVER_OK", self._run.stdout)
        self.assertEqual(self._run.stdout.strip(), "ADAPTER_DRIVER_OK",
                         "驱动不得留下任何 FAIL 行")


if __name__ == "__main__":
    unittest.main()
