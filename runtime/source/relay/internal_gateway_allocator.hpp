#pragma once

#include <cstddef>

namespace isaac::runtime::relay {

// 只管理安装期位置；已提交位置即使发布失败也不回收。
class InternalGatewayAllocator final {
public:
    struct Allocation {
        std::size_t index{};
        std::size_t offset{};
        std::size_t end{};
        bool valid{false};
    };

    InternalGatewayAllocator() noexcept = default;
    InternalGatewayAllocator(const InternalGatewayAllocator&) = delete;
    InternalGatewayAllocator& operator=(const InternalGatewayAllocator&) = delete;
    InternalGatewayAllocator(InternalGatewayAllocator&&) = delete;
    InternalGatewayAllocator& operator=(InternalGatewayAllocator&&) = delete;

    Allocation Plan(bool pageAligned) const noexcept {
        if (count_ >= 32) return {};
        const std::size_t offset = pageAligned ? (cursor_ + 0xfff) & ~std::size_t{0xfff} : cursor_;
        if (offset > 0x10000 - 32) return {};
        return {count_, offset, offset + 32, true};
    }

    bool Commit(const Allocation& allocation) noexcept {
        if (!allocation.valid || (!Matches(allocation, Plan(false)) && !Matches(allocation, Plan(true))))
            return false;
        ++count_;
        cursor_ = allocation.end;
        return true;
    }

    std::size_t count() const noexcept { return count_; }
    std::size_t used() const noexcept { return cursor_; }

private:
    static bool Matches(const Allocation& a, const Allocation& b) noexcept {
        return b.valid && a.index == b.index && a.offset == b.offset && a.end == b.end;
    }

    std::size_t count_{};
    std::size_t cursor_{};
};

} // namespace isaac::runtime::relay
