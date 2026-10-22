#pragma once

#include <cmath>
#include <cstdint>
#include <limits>
#include <type_traits>

namespace isaac::runtime {

// Lua number有integer/float两种子类型，超过2^53的整数不能经double保存。
struct CallbackPriorityValue {
    union {
        std::int64_t integer;
        double number;
    };
    bool isInteger{true};

    constexpr CallbackPriorityValue() noexcept : integer(0) {}
    template <class Integer, std::enable_if_t<std::is_integral_v<Integer>, int> = 0>
    constexpr CallbackPriorityValue(Integer value) noexcept
        : integer(static_cast<std::int64_t>(value)) {}
    constexpr CallbackPriorityValue(double value) noexcept : number(value), isInteger(false) {}

private:
    // 复用vendor Lua5.3.3 lvm.c:59–60、281–311的精确分支规则。
    static bool FitsFloat(std::int64_t value) noexcept {
        constexpr std::int64_t limit = std::int64_t{1} << 53;
        return -limit <= value && value <= limit;
    }
    static bool IntegerLessFloat(std::int64_t integerValue, double floatValue) noexcept {
        if (!FitsFloat(integerValue)) {
            constexpr double minimum = static_cast<double>(std::numeric_limits<std::int64_t>::min());
            if (floatValue >= -minimum) return true;
            if (floatValue > minimum) return integerValue < static_cast<std::int64_t>(floatValue);
            return false; // float<=minint或NaN，不能做越界转换。
        }
        return static_cast<double>(integerValue) < floatValue;
    }
    static bool IntegerLessEqualFloat(std::int64_t integerValue, double floatValue) noexcept {
        if (!FitsFloat(integerValue)) {
            constexpr double minimum = static_cast<double>(std::numeric_limits<std::int64_t>::min());
            if (floatValue >= -minimum) return true;
            if (floatValue >= minimum) return integerValue <= static_cast<std::int64_t>(floatValue);
            return false;
        }
        return static_cast<double>(integerValue) <= floatValue;
    }

public:
    // 对应lvm.c:341–356 LEnum；浮点<=整数方向必须排除NaN再取反。
    friend bool operator<=(CallbackPriorityValue left, CallbackPriorityValue right) noexcept {
        if (left.isInteger) {
            return right.isInteger ? left.integer <= right.integer
                                   : IntegerLessEqualFloat(left.integer, right.number);
        }
        if (!right.isInteger) return left.number <= right.number;
        return !std::isnan(left.number) && !IntegerLessFloat(right.integer, left.number);
    }
    friend bool operator==(CallbackPriorityValue left, CallbackPriorityValue right) noexcept {
        return left <= right && right <= left;
    }
};

static_assert(sizeof(CallbackPriorityValue) == 16);
static_assert(std::numeric_limits<double>::digits == 53);
static_assert(std::numeric_limits<std::int64_t>::digits == 63);

} // namespace isaac::runtime
