#include "mod_image_resources.hpp"

#include "image_pcx_bridge_hook.hpp"
#include "infrastructure/relay/entry_relay_binding.hpp"
#include "infrastructure/relay/entry_relay_hook_adapter.hpp"
#include "relay/entry_relay.hpp"

namespace isaac::runtime::bridge {

ModImageResourcesState g_ModImageResourcesState{};
static_assert(sizeof(ModImageResourcesState) == 20);

namespace {
std::uintptr_t g_PreparedModuleBase = 0;
const GameFileReader::Bindings* g_PreparedFiles = nullptr;
GameFileReader::ImagePcxBindings* g_PreparedImages = nullptr;
GameFileReader::Bindings g_FileSnapshot{};
GameFileReader::ImagePcxBindings g_ImageSnapshot{};

bool Fail(std::uint32_t failure) noexcept {
    g_ModImageResourcesState.failure.store(failure, std::memory_order_relaxed);
    g_ModImageResourcesState.phase.store(3, std::memory_order_release);
    return false;
}

// 早装与普通安装各有成功表；回退地址只证明已发布，不能代替安装成功。
bool Installed(HookId id) noexcept {
    return EntryRelayInstalledEarly(id) || EntryRelayInstalled(id);
}
} // namespace

bool PrepareModImageResources(const TargetModule& module,
                             const GameFileReader::Bindings* files,
                             GameFileReader::ImagePcxBindings* images) noexcept {
    auto& state = g_ModImageResourcesState;
    state.calls.fetch_add(1, std::memory_order_relaxed);
    std::uint32_t expected = 0;
    if (!state.phase.compare_exchange_strong(expected, 1, std::memory_order_acq_rel)) {
        // 不等待、不重写入口、不把准备中的绑定当作已经就绪。
        return expected == 2 && module.base == g_PreparedModuleBase &&
               files == g_PreparedFiles && images == g_PreparedImages;
    }
    if (module.base == 0 || module.buildId != kTargetBuildId || files == nullptr ||
        images == nullptr || files->construct == nullptr || files->openRead == nullptr ||
        files->getLength == nullptr || files->read == nullptr || files->close == nullptr ||
        files->destroy == nullptr) {
        return Fail(1);
    }
    GameFileReader::ImagePcxBindings verified{};
    if (!GameFileReader::VerifyImagePcxBindings(module, &verified)) {
        state.bindingMask.store(GameFileReader::LastImagePcxBindingMask(),
                                std::memory_order_relaxed);
        return Fail(2);
    }
    if (!Installed(HookId::ContentGetMountedFilePath) ||
        EntryRelayFallbackEntry(HookId::ContentGetMountedFilePath) == 0) {
        return Fail(3);
    }
    // 回退入口在改写目标前已公布；用实际成功状态判断，不能把回退地址当成功判据。
    if (!Installed(HookId::ImagePcxLoad)) {
        const HookTarget target{module.base, module.textSize, module.size, module.buildId};
        std::uintptr_t original = 0;
        if (!TryInstallEntryRelayEarly(HookId::ImagePcxLoad, target, &original)) {
            state.relayFailure.store(relay::LastFailure(), std::memory_order_relaxed);
            return Fail(4);
        }
    }
    // 激活顺序：核对所有依赖 → 安装读取入口 → 发布绑定 → 发布就绪状态。
    // 在Attach之前路径回调仍保持原版答案，不会生成无法被消费的替换路径。
    *images = verified;
    g_FileSnapshot = *files;
    g_ImageSnapshot = verified;
    Attach(&g_FileSnapshot, &g_ImageSnapshot);
    g_PreparedModuleBase = module.base;
    g_PreparedFiles = files;
    g_PreparedImages = images;
    state.phase.store(2, std::memory_order_release);
    return true;
}

} // namespace isaac::runtime::bridge
