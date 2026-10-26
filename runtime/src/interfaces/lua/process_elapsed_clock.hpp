#pragma once
#include <cstdint>
namespace isaac::runtime {
// 固定PC Windows CRT clock计量自初始化经过的毫秒；VM重载不能重置进程时钟。
struct ProcessElapsedClock {
    std::uint64_t start{};
    bool initialized{};
    void Start(std::uint64_t now) noexcept {
        if (!initialized) { start = now; initialized = true; }
    }
    double Seconds(std::uint64_t now, std::uint64_t frequency) const noexcept {
        if (!initialized || now < start || frequency < 1000 || frequency % 1000)
            return -0.001;
        const auto milliseconds = (now - start) / (frequency / 1000);
        return milliseconds <= 2147483647ULL ? static_cast<double>(milliseconds) / 1000.0 : -0.001;
    }
};
}
