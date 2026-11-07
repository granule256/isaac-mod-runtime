#pragma once

#include <cstddef>
#include <cstdint>
#include <utility>

// ============================================================================
// 资源层（L3）设施（一）：`EngineArrayOwner` —— 跨边界数组的唯一持有方式
// ============================================================================
//
// 设计稿：`docs/设计-资源层-所有权与缓存-20260924.md`。
//
// **要治的问题**：引擎分配的内存由我们释放、我们分配的交给引擎释放 —— 这件事过去靠
// **逐处手工配对 + 注释纪律**，漏一条路就是泄漏，改错一次就是重复释放/悬垂（后者严重得多）。
// 已实测发现一条漏：贴图桥"成功返回合成路径"那条路没还引擎给的 `mounted`
// （`docs/问题与解决记录.md` 的「待修」一节）。
//
// **这个类型只做一件事**：把两种终止动作收在一个名字里 ——
//   * **析构 ⇒ 用引擎的释放函数还回去**（对应"引擎分配 / 我方释放"）；
//   * **`Release()` ⇒ 把裸指针交给引擎**（对应"我方分配 / 引擎释放"），之后本对象不再管它。
// 于是"提前 return 忘了还"这种错误**在类型上写不出来** —— 除非有人显式 `Release()`。
//
// **为什么是 header-only / 全 inline**：宿主门禁夹具**各自单独列源文件**编译运行时的一部分，
// 做成独立 `.cpp` 会链接期报未定义符号（与 L1/L2 同一条约束，见 `AGENTS.md`）。
//
// **为什么不做成模板 / 通用智能指针**：这里的释放函数是**运行期从绑定表拿到的**
// （`g_engineBindings->operatorDeleteArray`），不是编译期已知的类型信息，模板帮不上忙；
// 而且只允许有一条纪律，做成通用指针反而更容易被误用（设计稿 §三。
namespace isaac::runtime::engine_resources {

// 引擎释放函数指针的形状（`operator delete[]`），由调用方从绑定表里取。
using ReleaseFn = void (*)(void*);

class EngineArrayOwner {
public:
    // 空持有者（`pointer_ == nullptr` ⇒ 析构不调释放函数）。
    EngineArrayOwner() noexcept = default;

    // 接管一块由引擎分配器给出、需要我们还给引擎的数组；
    // `release == nullptr` 或 `pointer == nullptr` 时退化为"不管"（析构不调任何东西）。
    EngineArrayOwner(ReleaseFn release, void* pointer) noexcept
        : pointer_(pointer), release_(release) {}

    ~EngineArrayOwner() noexcept { Reset(); }

    EngineArrayOwner(const EngineArrayOwner&) = delete;
    EngineArrayOwner& operator=(const EngineArrayOwner&) = delete;

    EngineArrayOwner(EngineArrayOwner&& other) noexcept
        : pointer_(other.pointer_), release_(other.release_) {
        other.pointer_ = nullptr;
        other.release_ = nullptr;
    }

    EngineArrayOwner& operator=(EngineArrayOwner&& other) noexcept {
        if (this != &other) {
            Reset();
            pointer_ = other.pointer_;
            release_ = other.release_;
            other.pointer_ = nullptr;
            other.release_ = nullptr;
        }
        return *this;
    }

    // 只读用（不转移所有权）。
    [[nodiscard]] void* get() const noexcept { return pointer_; }
    [[nodiscard]] bool empty() const noexcept { return pointer_ == nullptr; }

    // 把裸指针交给引擎（由引擎负责释放），之后本对象不再管它。
    // 返回原指针，供 `return owner.Release();` 这种形状使用。
    [[nodiscard]] void* Release() noexcept {
        void* pointer = pointer_;
        pointer_ = nullptr;
        release_ = nullptr;
        return pointer;
    }

    // 提前归还（等价于析构；析构再调用是幂等的）。
    void Reset() noexcept {
        if (pointer_ != nullptr && release_ != nullptr) {
            release_(pointer_);
        }
        pointer_ = nullptr;
        release_ = nullptr;
    }

private:
    void* pointer_{nullptr};
    ReleaseFn release_{nullptr};
};

}  // namespace isaac::runtime::engine_resources