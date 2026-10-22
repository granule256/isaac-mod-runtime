"""门禁（L3 资源层）：`EngineArrayOwner` 的所有权语义 + 贴图桥的所有权守恒（源码级）。

## 为什么要有它（批次 115 设计稿 §五，2026-09-29 落地）

`docs/设计-资源层-所有权与缓存-20260924.md` 把"引擎对象生命周期"列为框架缺的一项能力：
引擎分配的内存由我们释放、我们分配的交给引擎释放，过去靠**逐处手工配对 + 注释纪律**，
漏一条路就是泄漏（已实测发现贴图桥"成功返回合成路径"那条路没还 `mounted`），
改错一次是重复释放/悬垂（更严重）。

本门禁钉两件事：

1. **`EngineArrayOwner` 的行为**（真编译、真运行）：析构必还且只还一次；`Release()` 之后
   析构不再还；移动之后源对象不再还；空指针 / 空释放函数 ⇒ 不调。
2. **`small_caches.hpp` 两个容器的语义**（真编译、真运行）：定长环形的覆盖顺序；
   LRU 命中提权、预算淘汰从最久未用开始、**单条超预算不缓存**。
3. **贴图桥的所有权守恒**（源码级）：四条返回路径都必须显式交代"引擎分配的那块谁还/谁收"，
   `mounted` / `pngMounted` 不许出现"只计数不归还"的形状。
"""

import json
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "runtime" / "source" / "image_pcx_bridge_hook.cpp"
RESOURCES_DIR = ROOT / "runtime" / "src" / "infrastructure" / "resources"
ENGINE_ARRAY = RESOURCES_DIR / "engine_array.hpp"
SMALL_CACHES = RESOURCES_DIR / "small_caches.hpp"

#: 夹具：`EngineArrayOwner` 的四种语义，打 JSON。
OWNER_DRIVER = textwrap.dedent(
    r"""
    #include "infrastructure/resources/engine_array.hpp"
    #include <cstdio>
    #include <utility>

    using isaac::runtime::engine_resources::EngineArrayOwner;

    static int g_frees = 0;
    static unsigned long long g_last = 0;
    static void Free(void* p) {
        ++g_frees;
        g_last = reinterpret_cast<unsigned long long>(p);
    }

    int main() {
        {
            EngineArrayOwner owner(Free, reinterpret_cast<void*>(0x1234));
            (void)owner;
        }
        std::printf("dtor_frees_once %d\n", g_frees);
        g_frees = 0;

        {
            EngineArrayOwner owner(Free, reinterpret_cast<void*>(0x2345));
            void* released = owner.Release();
            std::printf("release_returns_pointer %d\n",
                        released == reinterpret_cast<void*>(0x2345) ? 1 : 0);
        }
        std::printf("release_dtor_no_free %d\n", g_frees);
        g_frees = 0;

        {
            EngineArrayOwner source(Free, reinterpret_cast<void*>(0x3456));
            EngineArrayOwner target(std::move(source));
            std::printf("move_source_empty %d\n", source.empty() ? 1 : 0);
        }
        std::printf("move_target_frees_once %d\n", g_frees);
        g_frees = 0;

        {
            EngineArrayOwner empty(Free, nullptr);
            EngineArrayOwner no_release(nullptr, reinterpret_cast<void*>(0x4567));
            (void)empty; (void)no_release;
        }
        std::printf("null_and_empty_no_free %d\n", g_frees);
        return 0;
    }
    """
)

#: 夹具：两个缓存容器的语义，打 JSON 行。
CACHE_DRIVER = textwrap.dedent(
    r"""
    #include "infrastructure/resources/small_caches.hpp"
    #include "infrastructure/resources/owned_bytes.hpp"
    #include <cstdio>
    #include <memory>
    #include <string>
    #include <vector>

    using isaac::runtime::engine_resources::BudgetedLruCache;
    using isaac::runtime::engine_resources::FixedRingStore;

    static std::size_t BytesOf(const std::vector<unsigned char>& v) { return v.size(); }
    static std::size_t SizeOf(std::size_t value) { return value; }
    static int cache_frees = 0;
    struct CacheFree {
        void operator()(int* pointer) const {
            ++cache_frees;
            delete pointer;
        }
    };
    struct MoveOnlyValue {
        std::size_t bytes{};
        std::unique_ptr<int, CacheFree> allocation{};
        MoveOnlyValue() = default;
        explicit MoveOnlyValue(std::size_t size) : bytes(size), allocation(new int(7)) {}
        MoveOnlyValue(MoveOnlyValue&&) = default;
        MoveOnlyValue& operator=(MoveOnlyValue&&) = default;
    };
    static std::size_t MoveBytesOf(const MoveOnlyValue& value) { return value.bytes; }
    struct KeyOps {
        static bool Equal(const std::string& a, const std::string& b) { return a == b; }
    };
    struct IntKeyOps {
        static bool Equal(const int& a, const int& b) { return a == b; }
    };

    int main() {
        // 定长环形：写入序覆盖最旧
        FixedRingStore<int, 3> ring;
        for (int i = 1; i <= 5; ++i) ring.Append(i);
        std::printf("ring_count %u\n", ring.count());
        std::printf("ring_slot0 %d\n", ring.at(0));  // 4（第 4 次写入落到槽 0）
        std::printf("ring_slot1 %d\n", ring.at(1));  // 5
        std::printf("ring_slot2 %d\n", ring.at(2));  // 3（未被覆盖）

        // LRU + 预算（场景刻意能区分"LRU"与"先进先出"）
        BudgetedLruCache<std::string, std::vector<unsigned char>, 4, KeyOps, decltype(&BytesOf)>
            cache(&BytesOf, 100);
        cache.Insert("a", std::vector<unsigned char>(20, 1));
        cache.Insert("b", std::vector<unsigned char>(30, 2));
        std::printf("lru_used_after_two %zu\n", cache.used_bytes());
        // 命中 a ⇒ a 变成最近使用（若按先进先出，接下来该淘汰的是 a，不是 b）
        cache.Find("a");
        cache.Insert("c", std::vector<unsigned char>(40, 3));
        cache.Insert("d", std::vector<unsigned char>(5, 4));
        std::printf("lru_used_before_evict %zu\n", cache.used_bytes());   // 95
        // 再插 e（10）⇒ 95+10 超预算 ⇒ 淘汰**最久未用**的那条（b，因为它从未被命中过）
        cache.Insert("e", std::vector<unsigned char>(10, 5));
        std::printf("lru_b_evicted %d\n", cache.Find("b") == nullptr ? 1 : 0);
        std::printf("lru_a_kept %d\n", cache.Find("a") != nullptr ? 1 : 0);
        std::printf("lru_used_after_evict %zu\n", cache.used_bytes());    // 75
        // 单条超预算 ⇒ 不缓存
        int inserted = cache.Insert("huge", std::vector<unsigned char>(500, 9)) ? 1 : 0;
        std::printf("lru_oversized_rejected %d\n", inserted == 0 ? 1 : 0);

        // 16 个空槽插入都必须受总预算限制，最旧条目按预算淘汰。
        constexpr std::size_t mib = 1024 * 1024;
        BudgetedLruCache<int, std::vector<unsigned char>, 16, IntKeyOps, decltype(&BytesOf)>
            budget_cache(&BytesOf, 24 * mib);
        int all_budget_entries_accepted = 1;
        for (int i = 0; i < 16; ++i) {
            all_budget_entries_accepted &= budget_cache.Insert(i, std::vector<unsigned char>(4 * mib, 1)) ? 1 : 0;
        }
        std::printf("empty_slots_respect_budget %d\n",
                    all_budget_entries_accepted && budget_cache.used_bytes() == 24 * mib ? 1 : 0);
        std::printf("empty_slots_used_bytes %zu\n", budget_cache.used_bytes());
        int budget_lru_correct = 1;
        for (int i = 0; i < 16; ++i) {
            budget_lru_correct &= (budget_cache.Find(i) != nullptr) == (i >= 10) ? 1 : 0;
        }
        std::printf("empty_slots_budget_lru %d\n", budget_lru_correct);

        // 替换同一键后需要为新尺寸腾预算，保留新值并淘汰最旧的其它值。
        BudgetedLruCache<int, std::vector<unsigned char>, 3, IntKeyOps, decltype(&BytesOf)>
            replace_cache(&BytesOf, 24 * mib);
        replace_cache.Insert(1, std::vector<unsigned char>(8 * mib, 1));
        replace_cache.Insert(2, std::vector<unsigned char>(8 * mib, 2));
        const int replacement_accepted = replace_cache.Insert(1, std::vector<unsigned char>(20 * mib, 3)) ? 1 : 0;
        std::printf("replacement_respects_budget %d\n",
                    replacement_accepted && replace_cache.used_bytes() == 20 * mib &&
                    replace_cache.Find(1) != nullptr && replace_cache.Find(2) == nullptr ? 1 : 0);
        std::printf("replacement_used_bytes %zu\n", replace_cache.used_bytes());
        const int oversized_replacement_rejected =
            replace_cache.Insert(1, std::vector<unsigned char>(25 * mib, 4)) ? 0 : 1;
        const auto* preserved_value = replace_cache.Find(1);
        std::printf("oversized_replacement_preserves_value %d\n",
                    oversized_replacement_rejected && preserved_value != nullptr &&
                    preserved_value->size() == 20 * mib && preserved_value->front() == 3 ? 1 : 0);

        // 槽位数也是硬上限：即使字节预算还有余量，也淘汰 LRU 后写入新键。
        BudgetedLruCache<int, std::vector<unsigned char>, 2, IntKeyOps, decltype(&BytesOf)>
            full_cache(&BytesOf, 100);
        full_cache.Insert(1, std::vector<unsigned char>(10, 1));
        full_cache.Insert(2, std::vector<unsigned char>(20, 2));
        full_cache.Find(1);  // 命中刷新顺序；槽位满时不能退化成先进先出。
        const int full_insert_accepted = full_cache.Insert(3, std::vector<unsigned char>(30, 3)) ? 1 : 0;
        std::printf("full_slots_evict_lru %d\n",
                    full_insert_accepted && full_cache.used_bytes() == 40 &&
                    full_cache.Find(1) != nullptr && full_cache.Find(2) == nullptr &&
                    full_cache.Find(3) != nullptr ? 1 : 0);

        // 零尺寸值仍然是一条有效缓存记录；计数不得因为其字节数为 0 而失配。
        BudgetedLruCache<int, std::vector<unsigned char>, 1, IntKeyOps, decltype(&BytesOf)>
            zero_cache(&BytesOf, 0);
        const int zero_insert_accepted = zero_cache.Insert(7, {}) ? 1 : 0;
        std::printf("zero_sized_entry_cached %d\n",
                    zero_insert_accepted && zero_cache.used_bytes() == 0 && zero_cache.Find(7) != nullptr ? 1 : 0);
        const int zero_replacement_accepted = zero_cache.Insert(8, {}) ? 1 : 0;
        std::printf("zero_sized_full_slot_evicted %d\n",
                    zero_replacement_accepted && zero_cache.Find(7) == nullptr &&
                    zero_cache.Find(8) != nullptr && zero_cache.used_bytes() == 0 ? 1 : 0);

        // used + bytes 可能溢出 size_t；在 SIZE_MAX 预算下仍应正确淘汰旧值。
        BudgetedLruCache<int, std::size_t, 2, IntKeyOps, decltype(&SizeOf)>
            overflow_cache(&SizeOf, static_cast<std::size_t>(-1));
        overflow_cache.Insert(1, static_cast<std::size_t>(-11));
        const int overflow_insert_accepted = overflow_cache.Insert(2, 20) ? 1 : 0;
        std::printf("budget_addition_overflow_safe %d\n",
                    overflow_insert_accepted && overflow_cache.used_bytes() == 20 &&
                    overflow_cache.Find(1) == nullptr && overflow_cache.Find(2) != nullptr ? 1 : 0);

        // 淘汰零尺寸旧值后仍须继续腾预算，替换为小值时则不得误淘汰其它值。
        BudgetedLruCache<int, std::size_t, 4, IntKeyOps, decltype(&SizeOf)>
            mixed_cache(&SizeOf, 100);
        mixed_cache.Insert(1, 0);
        mixed_cache.Insert(2, 30);
        mixed_cache.Insert(3, 40);
        mixed_cache.Insert(4, 80);
        std::printf("multiple_evictions_include_zero_bytes %d\n",
                    mixed_cache.used_bytes() == 80 && mixed_cache.Find(1) == nullptr &&
                    mixed_cache.Find(2) == nullptr && mixed_cache.Find(3) == nullptr &&
                    mixed_cache.Find(4) != nullptr ? 1 : 0);
        mixed_cache.Insert(5, 20);
        mixed_cache.Insert(4, 10);
        std::printf("smaller_replacement_keeps_other_entries %d\n",
                    mixed_cache.used_bytes() == 30 && mixed_cache.Find(4) != nullptr &&
                    mixed_cache.Find(5) != nullptr ? 1 : 0);

        // 缓存值可只移动：淘汰、替换、拒收和析构各自只能释放一次。
        {
            BudgetedLruCache<int, MoveOnlyValue, 1, IntKeyOps, decltype(&MoveBytesOf)>
                owned_cache(&MoveBytesOf, 100);
            MoveOnlyValue first(10);
            owned_cache.Insert(1, std::move(first));
            std::printf("cache_move_transfers_ownership %d\n",
                        first.allocation == nullptr && cache_frees == 0 &&
                        owned_cache.Find(1)->allocation != nullptr ? 1 : 0);
            const bool accepted = owned_cache.Insert(2, MoveOnlyValue(20));
            std::printf("cache_eviction_releases_once %d\n", accepted && cache_frees == 1 ? 1 : 0);
            owned_cache.Insert(2, MoveOnlyValue(30));
            std::printf("cache_replacement_releases_once %d\n", cache_frees == 2 ? 1 : 0);
            const bool rejected = !owned_cache.Insert(2, MoveOnlyValue(101));
            const auto* kept = owned_cache.Find(2);
            std::printf("cache_rejection_releases_input_only %d\n",
                        rejected && cache_frees == 3 && kept != nullptr && kept->bytes == 30 ? 1 : 0);
        }
        std::printf("cache_destructor_releases_remaining_once %d\n", cache_frees == 4 ? 1 : 0);
        return 0;
    }
    """
)


def host_compiler():
    for candidate in ("clang++", "g++"):
        if shutil.which(candidate):
            return candidate
    return None


def compile_and_run(driver: str, name: str, include_dirs) -> dict:
    compiler = host_compiler()
    if compiler is None:
        raise unittest.SkipTest("需要宿主 C++ 编译器")
    with tempfile.TemporaryDirectory(prefix=f"{name}-") as temporary:
        directory = Path(temporary)
        source = directory / "main.cpp"
        binary = directory / name
        source.write_text(driver, encoding="utf-8")
        command = [compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror"]
        for inc in include_dirs:
            command += ["-I", str(inc)]
        command += [str(source), "-o", str(binary)]
        compiled = subprocess.run(command, capture_output=True, text=True)
        if compiled.returncode != 0:
            raise RuntimeError(f"{name} 夹具编译失败：\n{compiled.stdout}{compiled.stderr}")
        run = subprocess.run([str(binary)], capture_output=True, text=True)
        if run.returncode != 0:
            raise RuntimeError(f"{name} 夹具运行失败：\n{run.stdout}{run.stderr}")
        out = {}
        for line in run.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2:
                out[parts[0]] = int(parts[1])
        return out


class EngineArrayOwnerTests(unittest.TestCase):
    """所有权语义（真编译、真运行）。"""

    @classmethod
    def setUpClass(cls):
        cls.cases = compile_and_run(OWNER_DRIVER, "engine_array_owner", [ROOT / "runtime" / "src"])

    def test_destructor_frees_exactly_once(self):
        self.assertEqual(self.cases["dtor_frees_once"], 1)

    def test_release_transfers_ownership(self):
        self.assertEqual(self.cases["release_returns_pointer"], 1)
        self.assertEqual(self.cases["release_dtor_no_free"], 0)

    def test_move_transfers_and_source_is_empty(self):
        self.assertEqual(self.cases["move_source_empty"], 1)
        self.assertEqual(self.cases["move_target_frees_once"], 1)

    def test_null_pointer_or_null_release_never_frees(self):
        self.assertEqual(self.cases["null_and_empty_no_free"], 0)


class SmallCacheTests(unittest.TestCase):
    """两个共用容器的语义。

    ★ 批次 422 起 `BudgetedLruCache` **不再**与批次 115 的原始实现"逐条一致"：
    预算改成"任一时点都不许超"（老实现只在槽全满后才看预算）—— 那是有意的修正。
    """

    @classmethod
    def setUpClass(cls):
        cls.cases = compile_and_run(CACHE_DRIVER, "small_caches", [ROOT / "runtime" / "src"])

    def test_ring_overwrites_oldest(self):
        self.assertEqual(self.cases["ring_count"], 5)
        self.assertEqual(self.cases["ring_slot0"], 4)
        self.assertEqual(self.cases["ring_slot1"], 5)
        self.assertEqual(self.cases["ring_slot2"], 3)

    def test_lru_budget_eviction_prefers_least_recently_used(self):
        self.assertEqual(self.cases["lru_used_after_two"], 50)
        self.assertEqual(self.cases["lru_used_before_evict"], 95)
        self.assertEqual(self.cases["lru_b_evicted"], 1, "预算满时必须淘汰最久未用的那条")
        self.assertEqual(self.cases["lru_a_kept"], 1, "刚命中过的不许被淘汰")
        self.assertEqual(self.cases["lru_used_after_evict"], 75)

    def test_oversized_entry_is_not_cached(self):
        self.assertEqual(self.cases["lru_oversized_rejected"], 1)

    def test_empty_slots_do_not_bypass_total_budget(self):
        self.assertEqual(self.cases["empty_slots_used_bytes"], 24 * 1024 * 1024)
        self.assertEqual(self.cases["empty_slots_respect_budget"], 1)
        self.assertEqual(self.cases["empty_slots_budget_lru"], 1)

    def test_replacement_evicts_other_entries_until_new_size_fits(self):
        self.assertEqual(self.cases["replacement_used_bytes"], 20 * 1024 * 1024)
        self.assertEqual(self.cases["replacement_respects_budget"], 1)

    def test_oversized_replacement_preserves_existing_value(self):
        self.assertEqual(self.cases["oversized_replacement_preserves_value"], 1)

    def test_full_slots_evict_lru_even_with_byte_budget_remaining(self):
        self.assertEqual(self.cases["full_slots_evict_lru"], 1)

    def test_zero_sized_entries_are_cached_and_evicted_by_slot_limit(self):
        self.assertEqual(self.cases["zero_sized_entry_cached"], 1)
        self.assertEqual(self.cases["zero_sized_full_slot_evicted"], 1)

    def test_budget_comparison_does_not_overflow_size_t(self):
        self.assertEqual(self.cases["budget_addition_overflow_safe"], 1)

    def test_multiple_evictions_handle_zero_sized_oldest_entries(self):
        self.assertEqual(self.cases["multiple_evictions_include_zero_bytes"], 1)

    def test_smaller_replacement_does_not_evict_other_entries(self):
        self.assertEqual(self.cases["smaller_replacement_keeps_other_entries"], 1)

    def test_move_only_values_are_released_exactly_once(self):
        for case in ("cache_move_transfers_ownership", "cache_eviction_releases_once",
                     "cache_replacement_releases_once", "cache_rejection_releases_input_only",
                     "cache_destructor_releases_remaining_once"):
            with self.subTest(case=case):
                self.assertEqual(self.cases[case], 1)


class BridgeOwnershipConservationTests(unittest.TestCase):
    """贴图桥：四条返回路径都要交代"引擎分配的那块谁还"。"""

    def setUp(self):
        self.text = BRIDGE.read_text(encoding="utf-8")
        marker = "EntryRelayContentGetMountedFilePathCallback(void* self, const char* path) {"
        self.body = self.text[self.text.index(marker):]

    def test_uses_engine_array_owner(self):
        self.assertIn("EngineArrayOwner", self.body,
                      "贴图桥必须用 EngineArrayOwner 持有引擎分配的挂载路径")

    def test_engine_allocations_are_owned_not_manually_freed(self):
        # `mounted` / `pngMounted` 不再出现"裸 operatorDeleteArray"的形状：
        # 归还动作一律由 owner 的析构 / Reset 完成。
        self.assertNotIn("operatorDeleteArray(mounted)", self.body)
        self.assertNotIn("operatorDeleteArray(pngMounted)", self.body)

    def test_synthetic_buffer_is_released_to_engine(self):
        # 我方分配、交引擎释放的那块必须显式 Release()（否则析构会去释放引擎要用的内存）。
        self.assertIn(".Release()", self.body,
                      "我方分配、交给引擎释放的合成路径必须显式 Release()")

    def test_success_path_no_longer_leaks(self):
        # 旧形状（只计数、不归还 mounted）必须消失。
        self.assertNotIn("++g_imagePcxDiag.pngOverrideWins;\n    }\n    return synthetic;", self.body)


if __name__ == "__main__":
    unittest.main()
