#pragma once

#include <cstddef>
#include <cstdint>
#include <utility>

// ============================================================================
// 资源层（L3）设施（二）：两个共用缓存容器
// ============================================================================
//
// 设计稿：`docs/设计-资源层-所有权与缓存-20260924.md`（批次 115）§四。
//
// **要治的问题**：三个功能各自造了一份缓存设施（贴图桥的"合成路径环形"与"转码结果缓存"、
// 模组页的 `g_Sources/g_Entries`）。本文件把**贴图桥内部那两份**收成共用容器 ——
// 行为必须**逐条不变**（条数、预算、淘汰顺序、**以及"键是固定大小的字符数组、不额外堆分配"**）。
//
// ★ **键存储刻意保持"值语义 + 固定大小"**：原实现用 `char[256]` 作键（避免每个键一次堆分配）。
// 换成 `std::string` 会**改变分配行为**（本项目的资源层纪律是"行为逐条不变"）⇒
// 因此 `Key` 保持"平凡可拷贝"的小结构，比较用调用方给的 `KeyOps`。
//
// ★ `mod_menu_native.cpp` 的 `g_Sources/g_Entries` **本轮不动**：它那处同时**直接写引擎的
// `std::vector` 三元组**，那是"写引擎容器"这一类风险，与"缓存设施去重"不是同一件事。
//
// **为什么是 header-only / 全 inline**：同 `engine_array.hpp`（宿主夹具不含新 `.cpp`）。
namespace isaac::runtime::engine_resources {

// ---------------------------------------------------------------------------
// FixedRingStore<T, N>：定长环形，**值语义**（写进去的是副本），按写入序覆盖最旧
// ---------------------------------------------------------------------------
//
// 用途（贴图桥的合成记录）：`文件名 → 该 .png 的真实挂载路径`。存的是**副本**，
// **不做所有权追踪** —— 存指针就是耦合（设计稿 §四"明确不做"）。
//
// `Append` 的落槽规则与现实现 `(++count - 1) % N` 完全一致；`count` 单调递增不取模。
//: `AppendAt(seq, value)` 接受**外部给定的写入序**（调用方自己持有计数器，例如桥侧那个
//: `std::atomic<uint32_t>`）——这样"写入序是原子的"这条既有语义原样保留，容器只管落槽与覆盖。
template <typename T, std::size_t N>
class FixedRingStore {
public:
    static_assert(N > 0, "环形至少一个槽位");

    //: 写入一个副本，返回它落在哪个槽（写入序由本对象自增）。
    std::size_t Append(const T& value) noexcept {
        return AppendAt(count_, value);
    }

    //: 写入一个副本，**写入序由调用方给**（`seq` 从 0 开始、单调递增）。
    std::size_t AppendAt(std::uint32_t seq, const T& value) noexcept {
        const std::size_t slot = seq % N;
        items_[slot] = value;
        if (seq + 1 > count_) {
            count_ = seq + 1;  // count = 已写入的条数（与现实现同义）
        }
        return slot;
    }

    [[nodiscard]] std::uint32_t count() const noexcept { return count_; }

    [[nodiscard]] T& at(std::size_t slot) noexcept { return items_[slot % N]; }
    [[nodiscard]] const T& at(std::size_t slot) const noexcept { return items_[slot % N]; }

    [[nodiscard]] static constexpr std::size_t capacity() noexcept { return N; }

private:
    T items_[N]{};
    std::uint32_t count_{0};
};

// ---------------------------------------------------------------------------
// BudgetedLruCache<Key, Value, N, KeyOps, BytesOf>
//   —— LRU + 总字节预算，超预算从最久未用开始淘汰
// ---------------------------------------------------------------------------
//
// 用途（贴图桥的转码结果缓存）：键 = `.png` 的真实挂载路径，值 = 转好的 PCX 字节。
// 语义：
//   * 命中 ⇒ 记 `lastUse`（单调递增时钟）；
//   * **任一超限 ⇒ 从最久未用开始淘汰**：①总字节超预算（不管还有没有空槽）、②一条空槽都没有；
//   * **单条超预算 ⇒ 不缓存**（宁可每次重转，也不撑爆堆）。
//
// ★★ 2026-10-10（批次 422）：第 2 条**原来是错的** —— 老实现"有空槽就直接返回"，
//   于是预算只在 N 个槽全满后才生效（真机实占 30.88 MB / 预算 24 MiB）。见 `ReserveSlot`。
//   ⇒ 现在**不再与批次 115 的原始实现逐条一致**，这是有意的修正，不是回归。
//
// ★ **不做线程安全**：现实现也不做（调用都在同一个引擎线程）。
// ★ `KeyOps` 提供 `static bool Equal(const Key&, const Key&)`；`Key` 必须平凡可拷贝。
template <typename Key, typename Value, std::size_t N, typename KeyOps, typename BytesOf>
class BudgetedLruCache {
public:
    using Clock = std::uint64_t;

    explicit BudgetedLruCache(BytesOf bytes_of, std::size_t budget_bytes) noexcept
        : bytes_of_(bytes_of), budget_bytes_(budget_bytes) {}

    //: 找一条；命中则刷新 `lastUse`（这是"最近使用"的定义）。
    Value* Find(const Key& key) noexcept {
        for (std::size_t i = 0; i < N; ++i) {
            if (entries_[i].used && KeyOps::Equal(entries_[i].key, key)) {
                entries_[i].last_use = ++clock_;
                return &entries_[i].value;
            }
        }
        return nullptr;
    }

    //: 插入/替换一条；单条超预算 ⇒ 不缓存（返回 false）。
    bool Insert(const Key& key, Value value) noexcept {
        const std::size_t bytes = bytes_of_(value);
        if (bytes > budget_bytes_) {
            return false;
        }
        std::size_t slot = kNpos;
        for (std::size_t i = 0; i < N; ++i) {
            if (entries_[i].used && KeyOps::Equal(entries_[i].key, key)) {
                slot = i;
                break;
            }
        }
        if (slot != kNpos) {
            used_bytes_ -= entries_[slot].bytes;
            entries_[slot] = Entry{};
        }
        slot = ReserveSlot(bytes);
        if (slot == kNpos) return false;
        entries_[slot].used = true;
        entries_[slot].key = key;
        entries_[slot].value = std::move(value);
        entries_[slot].bytes = bytes;
        entries_[slot].last_use = ++clock_;
        used_bytes_ += bytes;
        return true;
    }

    // 工作空间与常驻缓存分开计算；压力时先释放最久未用的所有者。
    void TrimToBytes(std::size_t keep) noexcept {
        while(used_bytes_>keep) {
            std::size_t victim=kNpos;
            for(std::size_t i=0;i<N;++i)
                if(entries_[i].used && (victim==kNpos || entries_[i].last_use<entries_[victim].last_use)) victim=i;
            if(victim==kNpos) break;
            used_bytes_-=entries_[victim].bytes;
            entries_[victim]=Entry{};
        }
    }

    [[nodiscard]] std::size_t used_bytes() const noexcept { return used_bytes_; }
    [[nodiscard]] static constexpr std::size_t capacity() noexcept { return N; }
    [[nodiscard]] std::size_t budget_bytes() const noexcept { return budget_bytes_; }

private:
    struct Entry {
        Key key{};
        Value value{};
        std::size_t bytes{0};
        Clock last_use{0};
        bool used{false};
    };

    static constexpr std::size_t kNpos = static_cast<std::size_t>(-1);

    //: 腾出一个能放下 `bytes` 的槽（先用空槽；满了就从最久未用开始淘汰）。
    //:
    //: ★★ 2026-10-10（批次 422）：**预算与槽数是两条独立的限制，任一超限都要淘汰**。
    //:   老实现第一步写的是 `if (!used) return i;` —— **有空槽就直接返回、根本不看预算**，
    //:   于是"总字节超预算"这条**只有 N 个槽全满之后才生效**。
    //:   真机实证：贴图桥那个缓存 N=32、预算 24 MiB，实测**实占 30.88 MB**
    //:   （32 条 × 平均 0.97 MB）—— 与"槽满才淘汰"严丝合缝。
    //:   现在改成：**只要 ①总字节超预算 或 ②一条空槽都没有，就淘汰最久未用的那条**。
    //:   （② 是原来就漏的：槽满但没超预算时，老实现会走到"找不到空槽 ⇒ 返回 kNpos ⇒
    //:     `Insert` 直接失败"，白白丢一次缓存。）
    [[nodiscard]] std::size_t ReserveSlot(std::size_t bytes) noexcept {
        for (;;) {
            std::size_t free_slot = kNpos;
            for (std::size_t i = 0; i < N; ++i) {
                if (!entries_[i].used) {
                    free_slot = i;
                    break;
                }
            }
            if (free_slot != kNpos && bytes <= budget_bytes_ - used_bytes_) {
                return free_slot;
            }
            std::size_t victim = kNpos;
            for (std::size_t i = 0; i < N; ++i) {
                if (!entries_[i].used) {
                    continue;
                }
                if (victim == kNpos || entries_[i].last_use < entries_[victim].last_use) {
                    victim = i;
                }
            }
            if (victim == kNpos) {
                // 一条可淘汰的都没有还超预算 ⇒ 只可能是 `bytes > budget_bytes_`
                // （`Insert` 已经挡掉这种情况）⇒ 如实放弃，不做无谓循环。
                return kNpos;
            }
            used_bytes_ -= entries_[victim].bytes;
            entries_[victim] = Entry{};
        }
    }

    Entry entries_[N]{};
    std::size_t used_bytes_{0};
    Clock clock_{0};
    BytesOf bytes_of_;
    std::size_t budget_bytes_;
};

}  // namespace isaac::runtime::engine_resources
