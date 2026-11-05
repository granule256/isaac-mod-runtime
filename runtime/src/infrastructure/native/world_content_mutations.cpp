#include "infrastructure/native/world_content_mutations.hpp"

namespace isaac::runtime {
namespace {
// Native mutation completion and managed consumers execute on the game thread.
WorldContentSnapshot g_Contents{1, 1, 0, 0, 0, 0};
}

WorldContentSnapshot CaptureWorldContentSnapshot() noexcept { return g_Contents; }

void RecordWorldContentMutation(WorldContentMutation kind) noexcept {
    const auto version = ++g_Contents.version;
    if (kind == WorldContentMutation::PickupsRerolled) g_Contents.pickupsVersion = version;
    else g_Contents.collectiblesVersion = version;
}

void BeginWorldContentFloor() noexcept {
    ++g_Contents.floorEpoch;
    g_Contents.scopeStartVersion = ++g_Contents.version;
    g_Contents.pickupsVersion = g_Contents.collectiblesVersion = 0;
}

void BeginWorldContentRun() noexcept {
    ++g_Contents.worldEpoch;
    BeginWorldContentFloor();
}

} // namespace isaac::runtime
