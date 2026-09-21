"""ContentMountService 宿主行为测试（假 Port 注入，不碰引擎）。

设计约束：引擎在内容重载时会**清空并重建**整个挂载点表，所以 Mod 的
`resources/`、`content/` 必须能在重建后被重新挂上。这个服务因此要记住挂过
哪些 Mod 目录，并在 `RemountAll()` 里原样重放；它自己持有这份记录，因为重建
回调可能在任何一次 Mod 加载请求之外发生。
"""

import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "runtime" / "src"

#: 模组的挂载叶子（**顺序 = 挂载次序 = 优先级次序**：本引擎后挂者优先）。
#: `resources-dlc3` 是 PC 的**忏悔层**（2026-09-21 加）：PC 模组覆盖忏悔资源时整包都放这一层
#: （实例：`visible tinted rocks` 的 23 张 `gfx/grid/rocks_*.png`），不挂 = 静默不生效。
MOD_LEAVES = (
    "resources",
    "resources/gfx",
    "content",
    "content/gfx",
    "resources-dlc3",
    "resources-dlc3/gfx",
)


def expected_mounts(prefix: str) -> str:
    return ",".join(f"{prefix}/{leaf}" for leaf in MOD_LEAVES)


DRIVER = textwrap.dedent(
    r"""
    #include "application/mod/content_mount_service.hpp"
    #include "ports/content_mount_port.hpp"

    #include <cstdio>
    #include <cstring>
    #include <string>
    #include <vector>

    using namespace isaac::runtime;

    namespace {

    int failures = 0;
    void Check(bool condition, const char* what) {
        if (!condition) { std::printf("FAILED_CHECK %s\n", what); ++failures; }
    }

    struct Call {
        std::string directory;
        std::string leaf;
    };

    struct FakePort final : IContentMountPort {
        std::vector<Call> calls;
        std::size_t failAt{static_cast<std::size_t>(-1)};

        Status MountModDirectory(std::string_view modDirectory,
                                 std::string_view leaf) noexcept override {
            if (calls.size() == failAt) {
                return Status{StatusCode::NotFound};
            }
            calls.push_back(Call{std::string{modDirectory}, std::string{leaf}});
            return Status::Ok();
        }
    };

    std::string Rendered(const std::vector<Call>& calls) {
        std::string out;
        for (const Call& call : calls) {
            if (!out.empty()) { out += ","; }
            out += call.directory + "/" + call.leaf;
        }
        return out;
    }

    }  // namespace

    int main() {
        // 1. 注册一个 Mod：全部叶子（`__LEAVES__`）都要挂，顺序固定。
        //    `*/gfx` 那两个是给 ANM2 内部的 `<Spritesheet Path>` 用的：引擎把挂载点直接拼在
        //    路径前面，而 .anm2 里写的是相对 gfx 目录的裸文件名。
        //    `resources-dlc3`（+`/gfx`）是 PC 的忏悔层，**排在最后**（后挂者优先 ⇒ 它压过
        //    本体两层与模组自己的 `resources`，与 PC 的层序一致）。
        {
            FakePort port;
            ContentMountService service{port};
            Check(service.RegisterMod("rom:/isaac_mods/mods/MuteOnPause/").ok(), "register ok");
            Check(Rendered(port.calls) == "__EXPECT_MUTEONPAUSE__",
                  "registers every leaf in order");
            Check(service.mod_count() == 1, "one mod recorded");
            Check(service.mod_directory(0) == "rom:/isaac_mods/mods/MuteOnPause/", "directory recorded");
        }

        // 2. 重复注册是幂等的：不重复挂、也不重复记录。
        {
            FakePort port;
            ContentMountService service{port};
            Check(service.RegisterMod("rom:/isaac_mods/mods/EID/").ok(), "first register");
            Check(service.RegisterMod("rom:/isaac_mods/mods/EID/").ok(), "second register");
            Check(port.calls.size() == __LEAF_COUNT__, "no duplicate mounts");
            Check(service.mod_count() == 1, "no duplicate record");
        }

        // 3. RemountAll 在引擎重建后原样重放每个 Mod 的全部叶子。
        {
            FakePort port;
            ContentMountService service{port};
            Check(service.RegisterMod("rom:/isaac_mods/mods/A/").ok(), "register A");
            Check(service.RegisterMod("rom:/isaac_mods/mods/B/").ok(), "register B");
            port.calls.clear();
            Check(service.RemountAll().ok(), "remount ok");
            Check(Rendered(port.calls) == "__EXPECT_A__,__EXPECT_B__",
                  "remount replays every mod in order");
        }

        // 4. Clear 丢弃记录，并且不再重放。
        {
            FakePort port;
            ContentMountService service{port};
            Check(service.RegisterMod("rom:/isaac_mods/mods/A/").ok(), "register before clear");
            service.Clear();
            Check(service.mod_count() == 0, "cleared");
            port.calls.clear();
            Check(service.RemountAll().ok(), "remount after clear");
            Check(port.calls.empty(), "cleared service mounts nothing");
        }

        // 5. 挂载失败的 Mod 不被记住：重建回调不该永远重试一个坏 Mod。
        {
            FakePort port;
            port.failAt = 1;  // 第二个叶子失败
            ContentMountService service{port};
            Check(!service.RegisterMod("rom:/isaac_mods/mods/Broken/").ok(), "failed mount reports failure");
            Check(service.mod_count() == 0, "failed mod is not recorded");
            port.failAt = static_cast<std::size_t>(-1);
            port.calls.clear();
            Check(service.RemountAll().ok(), "remount after failure");
            Check(port.calls.empty(), "nothing to remount");
        }

        // 6. 参数与容量边界。
        {
            FakePort port;
            ContentMountService service{port};
            Check(service.RegisterMod("").code() == StatusCode::InvalidArgument, "empty rejected");
            const std::string tooLong(ContentMountService::kMaxDirectoryLength + 1, 'x');
            Check(service.RegisterMod(tooLong).code() == StatusCode::CapacityExceeded,
                  "over-long directory rejected");
            for (std::size_t index = 0; index < ContentMountService::kMaxMods; ++index) {
                Check(service.RegisterMod("rom:/isaac_mods/mods/mod" + std::to_string(index) + "/").ok(), "fill capacity");
            }
            Check(service.RegisterMod("oneTooMany").code() == StatusCode::CapacityExceeded,
                  "capacity enforced");
        }

        // 7. 会话实例发布/取回（重建回调唯一的入口）。
        {
            FakePort port;
            ContentMountService service{port};
            Check(SessionContentMountService() == nullptr, "no session service by default");
            SetSessionContentMountService(&service);
            Check(SessionContentMountService() == &service, "session service published");
            SetSessionContentMountService(nullptr);
            Check(SessionContentMountService() == nullptr, "session service cleared");
        }

        if (failures != 0) {
            std::printf("CONTENT_MOUNT_FAILURES %d\n", failures);
            return 1;
        }
        std::printf("CONTENT_MOUNT_CHECKS_PASSED\n");
        return 0;
    }
    """
)


def host_compiler():
    for candidate in ("clang++", "g++"):
        if shutil.which(candidate):
            return candidate
    return None


class ContentMountServiceTests(unittest.TestCase):
    def test_service_contract_on_host(self):
        compiler = host_compiler()
        if compiler is None:
            self.skipTest("需要宿主 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="runtime-content-mount-") as temporary:
            directory = Path(temporary)
            source = directory / "content_mount.cpp"
            binary = directory / "content_mount"
            source.write_text(
                DRIVER.replace("__EXPECT_MUTEONPAUSE__",
                               expected_mounts("rom:/isaac_mods/mods/MuteOnPause/"))
                .replace("__EXPECT_A__", expected_mounts("rom:/isaac_mods/mods/A/"))
                .replace("__EXPECT_B__", expected_mounts("rom:/isaac_mods/mods/B/"))
                .replace("__LEAF_COUNT__", str(len(MOD_LEAVES)))
                .replace("__LEAVES__", "、".join(MOD_LEAVES)),
                encoding="utf-8")
            compile_result = subprocess.run(
                [
                    compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-I", str(SRC),
                    str(source),
                    str(SRC / "application" / "mod" / "content_mount_service.cpp"),
                    "-o", str(binary),
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run_result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run_result.returncode, 0, run_result.stdout + run_result.stderr)
            self.assertIn("CONTENT_MOUNT_CHECKS_PASSED", run_result.stdout)

    def test_adapter_verifies_guards_before_any_engine_call(self):
        """适配器必须先逐字节校验守卫，且只引用 runtime_constants 里的常量。"""
        adapter = (SRC / "infrastructure" / "content" /
                   "engine_content_mount_adapter.cpp").read_text(encoding="utf-8")
        for required in (
            "kContentMountPointPathCtorExpectedBytes",
            "kContentMountPointPathDtorExpectedBytes",
            "kContentAddMountPointExpectedBytes",
            "kContentManagerSlotOffset",
            "RelativeToApplicationRoot",
            "std::memcmp(",
        ):
            with self.subTest(required=required):
                self.assertIn(required, adapter)
        # 守卫不通过时不得触碰引擎：ResolveEngineCalls 在任一门禁失败时返回无效结果。
        self.assertIn("return calls;", adapter)
        # 引擎调用只能出现在解析成功之后。
        self.assertLess(adapter.index("GuardedCode(*module"), adapter.index("calls.addMountPoint("))
        # 适配器不得自己拼 `resources`/`content` 之外的 Mod 语义（叶子名归应用层）。
        constants = (ROOT / "runtime" / "source" / "runtime_constants.hpp").read_text(
            encoding="utf-8"
        )
        self.assertIn('kRebuildContentMountPointsOffset = 0x3B3510', constants)
        self.assertIn('kModAddressRootPrefix', constants)
        self.assertIn("kContentManagerSlotOffset = 0xAAC748", constants)

    def test_service_owns_the_mod_directory_contract(self):
        """叶子名（PC Mod 契约）在应用层，适配器只负责挂到内容根。"""
        header = (SRC / "application" / "mod" / "content_mount_service.hpp").read_text(
            encoding="utf-8"
        )
        self.assertIn('std::string_view{"resources"}', header)
        self.assertIn('std::string_view{"content"}', header)
        # ANM2 的贴图路径是相对 gfx 目录的裸名，必须有 gfx 挂载点才解析得到。
        self.assertIn('std::string_view{"resources/gfx"}', header)
        self.assertIn('std::string_view{"content/gfx"}', header)
        # 2026-09-21：PC 的忏悔层（`resources-dlc3`）——PC 模组覆盖忏悔资源时整包放在这一层，
        # 不挂就是"静默不生效"（用户真机实例：`visible tinted rocks` 的 23 张石头贴图）。
        self.assertIn('std::string_view{"resources-dlc3"}', header)
        self.assertIn('std::string_view{"resources-dlc3/gfx"}', header)
        # 顺序也是契约的一部分：后挂者优先 ⇒ dlc3 两个叶子必须在最后（压过模组自己的 `resources`）。
        self.assertLess(header.index('std::string_view{"resources-dlc3"}'),
                        header.index('std::string_view{"resources-dlc3/gfx"}'))
        self.assertGreater(header.index('std::string_view{"resources-dlc3"}'),
                           header.index('std::string_view{"content/gfx"}'))
        adapter = (SRC / "infrastructure" / "content" /
                   "engine_content_mount_adapter.cpp").read_text(encoding="utf-8")
        self.assertNotIn('"resources"', adapter)
        self.assertNotIn('"content"', adapter)


if __name__ == "__main__":
    unittest.main()
