#pragma once

#include <cstddef>

namespace isaac::runtime::relay {

// 与引擎 `SmartPointer<ImageBase>` 同形（16 字节、两个指针：对象 + 控制块）的**返回值垫片**。
//
// 为什么需要：`ImageManager::LoadImage` 两个重载都按 Itanium ABI 经 x8（sret）返回这个
// 16 字节值；入口中继回调要「以目标函数的身份返回」，就必须用同一形状声明回调。
//
// 关键设计：
// * 复制构造**用户提供但只做逐字拷贝** —— 用户提供的复制构造让类型「为调用目的非平凡」
//   （正是 sret ABI 的触发条件），而逐字拷贝意味着**绝不动引擎的引用计数**；
// * 析构保持隐式平凡 —— 我们这侧永远不会误放引擎对象；所有权随 16 字节的搬运整体转移；
// * `return f();` 走 C++17 强制拷贝省略：引擎构造的返回值直接落进调用方的返回槽，
//   中途不经过任何复制/移动，也没有临时对象的析构。
struct SmartPointerShim {
    void* pointer{nullptr};
    void* control{nullptr};

    SmartPointerShim() = default;
    SmartPointerShim(const SmartPointerShim& other) noexcept
        : pointer(other.pointer), control(other.control) {}
    SmartPointerShim& operator=(const SmartPointerShim& other) noexcept {
        pointer = other.pointer;
        control = other.control;
        return *this;
    }
};

static_assert(sizeof(SmartPointerShim) == 16, "必须与引擎 SmartPointer 同为 16 字节");

}  // namespace isaac::runtime::relay
