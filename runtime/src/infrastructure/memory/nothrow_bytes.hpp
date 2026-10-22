#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <new>
#include <utility>

namespace isaac::runtime::memory {

// 贴图字节块：分配失败保留原块；移动和接收转码结果均不复制图像。
class NothrowBytes {
public:
    NothrowBytes() noexcept = default;
    NothrowBytes(const NothrowBytes&) = delete;
    NothrowBytes& operator=(const NothrowBytes&) = delete;
    NothrowBytes(NothrowBytes&& other) noexcept
        : data_(std::move(other.data_)), size_(std::exchange(other.size_, 0)) {}
    NothrowBytes& operator=(NothrowBytes&& other) noexcept {
        if (this != &other) {
            data_ = std::move(other.data_);
            size_ = std::exchange(other.size_, 0);
        }
        return *this;
    }
    [[nodiscard]] static NothrowBytes Adopt(std::uint8_t* data, std::size_t size) noexcept {
        NothrowBytes result;
        result.data_.reset(data);
        result.size_ = data != nullptr ? size : 0;
        return result;
    }
    [[nodiscard]] bool Resize(std::size_t size) noexcept {
        if (size == size_) {
            return true;
        }
        std::unique_ptr<std::uint8_t[]> next;
        if (size != 0) {
            next.reset(new (std::nothrow) std::uint8_t[size]);
            if (!next) {
                return false;
            }
        }
        data_ = std::move(next);
        size_ = size;
        return true;
    }
    [[nodiscard]] std::uint8_t* data() noexcept { return data_.get(); }
    [[nodiscard]] const std::uint8_t* data() const noexcept { return data_.get(); }
    [[nodiscard]] std::size_t size() const noexcept { return size_; }

private:
    std::unique_ptr<std::uint8_t[]> data_;
    std::size_t size_{0};
};

} // namespace isaac::runtime::memory
