"""A missing real Init observer must fail the production installation service."""
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "runtime/src"
BUILD = ROOT.parents[1] / "data/build/architecture-required-test"
DRIVER = r'''
#include "application/runtime/hook_install_service.hpp"
#include <array>
#include <cstdio>
#include <cstring>
using namespace isaac::runtime;

struct RejectInit final : IHookPort {
    explicit RejectInit(HookId id) : rejected(id) {}
    HookId rejected;
    std::array<unsigned, kHookIdCount> attempts{};
    Status Install(HookId id, const HookTarget&) noexcept override {
        ++attempts[static_cast<unsigned>(id)];
        return id == rejected ? Status{StatusCode::Rejected} : Status::Ok();
    }
    bool IsInstalled(HookId id) const noexcept override {
        return id != rejected && attempts[static_cast<unsigned>(id)] != 0;
    }
};

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const auto rejected = std::strcmp(argv[1], "EntityInit") == 0 ? HookId::EntityInit :
        std::strcmp(argv[1], "EntityTearInit") == 0 ? HookId::EntityTearInit :
        std::strcmp(argv[1], "EntityEffectInit") == 0 ? HookId::EntityEffectInit : HookId::Count;
    if (rejected == HookId::Count) return 91;
    RejectInit hooks(rejected);
    HookInstallService service(hooks);
    ModuleInfo module{};
    module.valid = true;
    module.base = 0x1000;
    module.textSize = 0x100;
    module.imageSize = 0x200;
    HookInstallReport report{};
    const auto result = service.InstallProductionHooks(module, &report);
    if (result.code() != StatusCode::Rejected || report.productionReady()) {
        std::fprintf(stderr, "%s rejection did not block production readiness\n",
                     NameOf(rejected).data());
        return 1;
    }
    if (report.OutcomeOf(rejected) != HookOutcome::Failed ||
        report.FirstFailureSlot() != static_cast<unsigned>(rejected) + 1) return 2;
    if (hooks.attempts[static_cast<unsigned>(rejected)] != 1) return 3;
    for (const auto& point : kHookCatalog) {
        if (!point.required && hooks.attempts[static_cast<unsigned>(point.id)] != 0) {
            std::fprintf(stderr, "optional %s attempted after required Init failure\n",
                         point.name.data());
            return 4;
        }
    }
}
'''


class RequiredNativeInitHooksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BUILD.mkdir(parents=True, exist_ok=True)
        driver = BUILD / "required_native_init_hooks.cpp"
        driver.write_text(DRIVER)
        cls.binary = BUILD / "required_native_init_hooks"
        compiled = subprocess.run([
            "clang++", "-std=c++23", "-Wall", "-Wextra", "-Werror",
            "-I", str(SRC), str(driver),
            str(SRC / "application/runtime/hook_install_service.cpp"),
            "-o", str(cls.binary),
        ], capture_output=True, text=True)
        if compiled.returncode:
            raise AssertionError(compiled.stdout + compiled.stderr)

    def test_each_init_rejection_blocks_loading_before_optional_hooks(self):
        for name in ("EntityInit", "EntityTearInit", "EntityEffectInit"):
            with self.subTest(hook=name):
                result = subprocess.run([str(self.binary), name],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
