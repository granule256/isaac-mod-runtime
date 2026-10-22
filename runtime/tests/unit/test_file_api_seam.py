"""文件读写接口必须保持低耦合：**单一注入点 + 消费者不得绕过它 + 缺提供方是一等状态**。

为什么钉住这几条：文件能力是**注入**进来的。只要「注入点唯一、消费者只认接口、没有提供方时
显式报 `Unavailable`」成立，换提供方就只需换一个实现，不必翻遍运行时。

**2026-09-17 用户指令定下的口径**（本文件按新口径改写）：
> 将之后所有的持久化都走存档分区，直接将存档分区持久化作为当前持久化的默认实现，做到解耦合，
> 以后统一调用同样的接口。

因此接口本体从「宿主插件四个裸函数的句柄式包装」（`IFilePort`）换成**整文件语义的持久化端口**
`src/ports/save_file_port.hpp` 的 `ISaveFilePort`（`Read`/`Write`/`Remove`/`Exists`），
默认且当前唯一的实现是**游戏存档分区**（`EngineSaveFileAdapter`，直连 `nn::fs`）；
消费者（`mod_persistence.hpp` 是当前唯一的生产消费者，Lua 侧那 6 个模组数据入口都经它）
一律通过 `SessionSaveFilePort()` 取端口。

线程纪律也一并挪进端口实现：存档分区适配器**默认拒绝一切操作**，只有游戏线程上的代码能打开它
（`AllowFromGameThread()`）—— 2026-09-16 那次「在 worker 线程上调 `nn::fs` 导致每次开机必崩」
的教训，从此由端口统一兜住，消费者不必各自再记一遍。

背景仍是一条实测事实：运行时**自己**直接写 SD 卡从来没成功过，所以消费方必须依赖注入，
不能自己另找一条路。
"""

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "source"
SRC = ROOT / "src"
PERSISTENCE = SOURCE / "mod_persistence.hpp"
PORT = SRC / "ports" / "save_file_port.hpp"
ADAPTER = SRC / "infrastructure" / "persistence" / "engine_save_file_adapter.hpp"
ADAPTER_CPP = SRC / "infrastructure" / "persistence" / "engine_save_file_adapter.cpp"
WIRING = SOURCE / "hook_manager.cpp"
PROVIDER = SOURCE / "saltynx_runtime_bridge.cpp"
PLUGIN = SRC / "host_plugin" / "saltynx_host_plugin.cpp"

CONSUMERS = (
    "mod_persistence.hpp",
    "persistence_trace.cpp",
    "persistence_event_journal.cpp",
    "persistence_event_journal.hpp",
    "manager_update_hook_audit.cpp",
    "manager_update_hook_audit.hpp",
)

FORBIDDEN_IO = ("fopen(", "fwrite(", "fread(", "fclose(", "fsdev", "nx_fs", "nn::fs")

#: 会话默认端口的注入点只允许出现在**一处**生产代码里（模组加载路径，那里才证明得了
#: 「我们在游戏线程上」）。测试驱动自己会调用它，但测试不在这份 `production_sources()` 里。
INJECTION_CALL = re.compile(r"\bSetSessionSaveFilePort\(")
#: 打开线程硬闸同样只允许在这一处（与注入点是同一处，便于审计）。
#: 只认"对某个对象调用"的形态（`x.AllowFromGameThread()`）—— 适配器自己那份是定义，不算调用点。
GATE_CALL = re.compile(r"\.\s*AllowFromGameThread\(\)")


def strip_comments(text: str) -> str:
    """去掉 C/C++ 注释：判据只针对**代码**，注释里提到函数名不该判红。"""
    without_block = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", without_block)


def production_sources():
    """运行时生产源文件；排除构建/部署产物目录与测试驱动。"""
    for base in (SOURCE, SRC):
        for path in base.rglob("*"):
            if path.suffix not in (".cpp", ".hpp"):
                continue
            if any(part.startswith(("build-", "deploy-")) for part in path.parts):
                continue
            if "tests" in path.parts:
                continue
            yield path


class FileApiSeamTests(unittest.TestCase):
    def test_the_port_is_the_only_interface(self):
        """接口面本身就是替换契约：整文件语义的四个操作。"""
        text = PORT.read_text(encoding="utf-8")
        self.assertIn("class ISaveFilePort", text)
        for member in ("Read", "Write", "Remove", "Exists"):
            self.assertRegex(text, rf"\b{member}\(", member)

    def test_the_save_partition_port_is_the_default(self):
        """默认实现必须是「游戏存档分区」，并且只有一族注入点函数。"""
        text = PORT.read_text(encoding="utf-8")
        for token in ("g_sessionSaveFilePort", "SessionSaveFilePort", "SetSessionSaveFilePort"):
            self.assertIn(token, text, token)
        self.assertIn("EngineSaveFileAdapter", ADAPTER.read_text(encoding="utf-8"),
                      "存档分区适配器必须实现这个端口（它就是默认提供方）")

    def test_mod_persistence_consumes_only_the_port(self):
        """消费者只认端口：不得再自己持一份实现、也不得再判「哪条路可用」。"""
        text = PERSISTENCE.read_text(encoding="utf-8")
        self.assertIn('#include "ports/save_file_port.hpp"', text)
        for token in ("SessionSaveFilePort", "HasFileApi", "kStateName"):
            self.assertIn(token, text, token)
        # 旧形状必须彻底消失：句柄式端口、裸函数表、插件绝对路径（同样只看代码，不看注释）。
        code = strip_comments(text)
        for gone in ("IFilePort", "ConfigureFileApi", "ConfigureFilePort", "g_filePort",
                     "g_rawFunctions", "RawFilePort", "sdmc:", "/SaltySD/"):
            self.assertNotIn(gone, code, f"mod_persistence.hpp 里不该再有旧形状：{gone}")

    def test_the_injection_point_is_single(self):
        """只允许一处注入（并且同时是打开线程硬闸的那一处）。"""
        injectors = set()
        gate_openers = set()
        for path in production_sources():
            # 端口头文件里那份是**定义**（inline 函数本身），不是调用点；注释也不算（只看代码）。
            if path.name == "save_file_port.hpp":
                continue
            text = strip_comments(path.read_text(encoding="utf-8"))
            if INJECTION_CALL.search(text):
                injectors.add(path.name)
            if GATE_CALL.search(text):
                gate_openers.add(path.name)
        self.assertEqual(injectors, {WIRING.name},
                         "会话默认端口的注入点必须唯一（只有模组加载路径能证明自己在游戏线程上）")
        self.assertEqual(gate_openers, {WIRING.name},
                         "线程硬闸只允许在注入点那一处打开")

    def test_the_adapter_refuses_until_the_game_thread_opens_it(self):
        """线程纪律在端口实现里，不能只靠调用方自觉。"""
        header = ADAPTER.read_text(encoding="utf-8")
        source = ADAPTER_CPP.read_text(encoding="utf-8")
        self.assertIn("AllowFromGameThread", header)
        self.assertIn("allowed_", header)
        # 每个操作都要经过 `Resolve()`，而闸门判断必须在它最前面、且在缓存判定之前 ——
        # 否则「未允许」会被缓存成永久失败，游戏线程再打开也没用。
        self.assertIn("if (!allowed_)", source)
        self.assertLess(source.index("if (!allowed_)"), source.index("static Calls calls{}"),
                        "闸门必须在缓存判定之前（未允许不能被缓存）")

    def test_consumers_do_not_open_files_behind_the_interface(self):
        """消费方不得自己调 libc/libnx/引擎的文件函数 —— 那会让替换实现漏掉它们。"""
        for name in CONSUMERS:
            path = SOURCE / name
            if not path.is_file():
                continue
            # 注释里提到这些名字（例如解释"为什么不能用 nn::fs"）不算绕过 —— 只看代码。
            text = strip_comments(path.read_text(encoding="utf-8"))
            for token in FORBIDDEN_IO:
                self.assertNotIn(
                    token, text, f"{name} 直接使用了 {token}，绕过了注入的文件 API"
                )

    def test_plugin_file_functions_are_no_longer_used_for_persistence(self):
        """宿主插件那条路不再是持久化通道（持久化由运行时在游戏线程上自己读写）。"""
        text = PROVIDER.read_text(encoding="utf-8")
        self.assertNotIn("ModPersistence::ConfigureFileApi", text,
                         "持久化不再走插件注册的裸文件函数")

    def test_new_records_keep_content_and_transport_apart(self):
        """新增记录必须内容/落盘分离：`Build...` 不落盘，`Append...` 只负责送出去。"""
        text = PLUGIN.read_text(encoding="utf-8")
        self.assertIn("void BuildHandoverStartRecord", text)
        builder = text.split("void BuildHandoverStartRecord", 1)[1].split("\n}", 1)[0]
        self.assertNotIn("AppendRecord(", builder, "内容构造函数不得自己落盘")
        writer = text.split("void AppendHandoverStartRecord", 1)[1].split("\n}", 1)[0]
        self.assertIn("BuildHandoverStartRecord(", writer)
        self.assertIn("AppendRecord(", writer)


DRIVER = r"""
#include "mod_persistence.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string_view>
#include <string>
#include <vector>

// 假提供方：内存里的"存档分区"。它证明**任何 ISaveFilePort 实现都能被接上**，
// 不需要游戏在场 —— 这正是"以后换提供方"要的性质。
class MemoryStore final : public isaac::runtime::ISaveFilePort {
public:
    std::vector<char> bytes;
    bool exists = false;
    int writes = 0;
    int reads = 0;
    std::string lastName{};

    [[nodiscard]] isaac::runtime::Status Read(std::string_view name, char* out,
                                              std::size_t capacity,
                                              std::size_t* size) noexcept override {
        ++reads;
        lastName = name;
        if (size == nullptr) {
            return isaac::runtime::Status{isaac::runtime::StatusCode::InvalidArgument};
        }
        *size = 0;
        if (!exists) {
            return isaac::runtime::Status{isaac::runtime::StatusCode::NotFound};
        }
        if (bytes.size() > capacity) {
            return isaac::runtime::Status{isaac::runtime::StatusCode::CapacityExceeded};
        }
        std::memcpy(out, bytes.data(), bytes.size());
        *size = bytes.size();
        return isaac::runtime::Status::Ok();
    }

    [[nodiscard]] isaac::runtime::Status Write(std::string_view name,
                                               std::string_view data) noexcept override {
        ++writes;
        lastName = name;
        bytes.assign(data.begin(), data.end());
        exists = true;
        return isaac::runtime::Status::Ok();
    }

    [[nodiscard]] isaac::runtime::Status Remove(std::string_view name) noexcept override {
        lastName = name;
        bytes.clear();
        exists = false;
        return isaac::runtime::Status::Ok();
    }

    [[nodiscard]] isaac::runtime::Status Exists(const char*, bool* out) noexcept override {
        if (out != nullptr) {
            *out = exists;
        }
        return isaac::runtime::Status::Ok();
    }
};

// "能力缺失"：所有操作返回 Unsupported —— 正是存档分区适配器**闸门未打开**时的行为。
class GatedStore final : public isaac::runtime::ISaveFilePort {
public:
    [[nodiscard]] isaac::runtime::Status Read(std::string_view, char*, std::size_t,
                                              std::size_t*) noexcept override {
        return isaac::runtime::Status{isaac::runtime::StatusCode::Unsupported};
    }
    [[nodiscard]] isaac::runtime::Status Write(std::string_view,
                                               std::string_view) noexcept override {
        return isaac::runtime::Status{isaac::runtime::StatusCode::Unsupported};
    }
    [[nodiscard]] isaac::runtime::Status Remove(std::string_view) noexcept override {
        return isaac::runtime::Status{isaac::runtime::StatusCode::Unsupported};
    }
    [[nodiscard]] isaac::runtime::Status Exists(const char*, bool*) noexcept override {
        return isaac::runtime::Status{isaac::runtime::StatusCode::Unsupported};
    }
};

static int failures = 0;
static void Check(bool condition, const char* what) {
    if (!condition) {
        std::printf("FAILED_CHECK %s\n", what);
        ++failures;
    }
}

int main() {
    constexpr std::uint64_t kNamespace = 0x1122334455667788ULL;
    const char* kValue = "hello-mod-data";
    const std::size_t kValueLength = std::strlen(kValue);
    const char* loaded = nullptr;
    std::size_t length = 0;
    bool has = false;

    // (1) 没有提供方：能力缺失必须是一等状态。
    isaac::runtime::SetSessionSaveFilePort(nullptr);
    ModPersistence::ResetCacheForTesting();
    Check(!ModPersistence::IsFileApiReady(), "no_provider_reports_not_ready");
    Check(ModPersistence::SaveModData(kNamespace, kValue, kValueLength) ==
              ModPersistence::Result::Unavailable, "save_without_provider_is_unavailable");
    Check(ModPersistence::LoadModData(kNamespace, &loaded, &length) ==
              ModPersistence::Result::Unavailable, "load_without_provider_is_unavailable");
    Check(ModPersistence::HasModData(kNamespace, &has) == ModPersistence::Result::Unavailable,
          "has_without_provider_is_unavailable");

    // (2) 端口在、但拒绝服务（存档分区适配器的闸门没打开）：同样报能力缺失。
    GatedStore gated;
    isaac::runtime::SetSessionSaveFilePort(&gated);
    ModPersistence::ResetCacheForTesting();
    Check(ModPersistence::IsFileApiReady(), "gated_port_is_registered");
    Check(ModPersistence::SaveModData(kNamespace, kValue, kValueLength) ==
              ModPersistence::Result::Unavailable, "gated_port_save_is_unavailable");
    ModPersistence::ResetCacheForTesting();
    Check(ModPersistence::LoadModData(kNamespace, &loaded, &length) ==
              ModPersistence::Result::Unavailable, "gated_port_load_is_unavailable");

    // (3) 接上内存存档：保存/读取/存在性/删除全程走端口，且**整文件一次写**。
    MemoryStore store;
    isaac::runtime::SetSessionSaveFilePort(&store);
    ModPersistence::ResetCacheForTesting();
    Check(ModPersistence::IsFileApiReady(), "provider_reports_ready");
    Check(ModPersistence::LoadModData(kNamespace, &loaded, &length) ==
              ModPersistence::Result::Missing, "empty_store_reports_missing");
    Check(ModPersistence::SaveModData(kNamespace, kValue, kValueLength) ==
              ModPersistence::Result::Success, "save_succeeds_through_port");
    Check(store.writes == 1, "port_saw_exactly_one_whole_file_write");
    Check(store.lastName == "isaac-mod-1122334455667788-s0-a.bin", "port_got_the_relative_file_name");
    // 容器头由消费者自己构造（内容/落盘分离），端口只搬运字节。
    Check(store.bytes.size() > 8 && std::memcmp(store.bytes.data(), "ISMODST3", 8) == 0,
          "container_header_written_by_consumer");
    has = false;
    Check(ModPersistence::HasModData(kNamespace, &has) == ModPersistence::Result::Success && has,
          "has_after_save");
    loaded = nullptr;
    length = 0;
    Check(ModPersistence::LoadModData(kNamespace, &loaded, &length) ==
              ModPersistence::Result::Success, "load_after_save");
    Check(loaded != nullptr && length == kValueLength &&
              std::memcmp(loaded, kValue, length) == 0, "round_trip_payload");
    Check(ModPersistence::RemoveModData(kNamespace) == ModPersistence::Result::Success,
          "remove_succeeds_through_port");
    has = true;
    Check(ModPersistence::HasModData(kNamespace, &has) == ModPersistence::Result::Success && !has,
          "has_after_remove");

    // (4) 存档里的内容是垃圾 ⇒ 报损坏，而不是当成"没有数据"。
    MemoryStore corrupt;
    corrupt.exists = true;
    corrupt.bytes.assign(64, 'x');
    isaac::runtime::SetSessionSaveFilePort(&corrupt);
    ModPersistence::ResetCacheForTesting();
    Check(ModPersistence::LoadModData(kNamespace, &loaded, &length) ==
              ModPersistence::Result::Corrupt, "garbage_store_reports_corrupt");

    // (5) 超过容器上限 ⇒ TooLarge，不写半截（也**不会**把请求交给端口）。
    MemoryStore bounded;
    isaac::runtime::SetSessionSaveFilePort(&bounded);
    ModPersistence::ResetCacheForTesting();
    const char huge = 'y';
    Check(ModPersistence::SaveModData(kNamespace, &huge, ModPersistence::kMaximumFileSize) ==
              ModPersistence::Result::TooLarge, "oversized_payload_is_rejected");
    Check(bounded.writes == 0, "oversized_payload_never_reaches_the_port");

    if (failures == 0) {
        std::printf("SEAM_DRIVER_OK\n");
    }
    return failures == 0 ? 0 : 1;
}
"""


class FileApiSeamBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("c++") is None:
            raise unittest.SkipTest("宿主机没有 c++")
        cls._temporary = tempfile.TemporaryDirectory(prefix="isaac-file-seam-")
        directory = Path(cls._temporary.name)
        driver = directory / "file_seam_driver.cpp"
        driver.write_text(DRIVER.lstrip(), encoding="utf-8")
        binary = directory / "file_seam_driver"
        build = subprocess.run(
            ["c++", "-std=c++23", "-Wall", "-Wextra", "-Werror", "-I", str(SRC), "-I", str(SOURCE),
             str(driver), "-o", str(binary)],
            text=True, capture_output=True,
        )
        if build.returncode != 0:
            raise AssertionError(f"文件缝驱动在宿主机上编译失败：\n{build.stdout}{build.stderr}")
        cls._run = subprocess.run([str(binary)], text=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "_temporary", None) is not None:
            cls._temporary.cleanup()

    def test_seam_behavior_on_the_host(self):
        self.assertEqual(self._run.returncode, 0, self._run.stdout + self._run.stderr)
        self.assertEqual(self._run.stdout.strip(), "SEAM_DRIVER_OK")


if __name__ == "__main__":
    unittest.main()
