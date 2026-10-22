#pragma once
#include <cstddef>
#include <cstdint>
#include <memory>
#include <new>
#include <utility>
namespace isaac::runtime::engine_resources {
// 单一所有者、无异常分配，缓存移动接管原转码输出，绝不复制字节。
class OwnedBytes {
    std::unique_ptr<std::uint8_t[]> bytes_;
    std::size_t size_=0;
public:
    OwnedBytes() noexcept=default;
    OwnedBytes(std::uint8_t* data,std::size_t size) noexcept:bytes_(data),size_(size) {}
    OwnedBytes(OwnedBytes&&)=default;
    OwnedBytes& operator=(OwnedBytes&&)=default;
    bool Resize(std::size_t size) noexcept {
        std::unique_ptr<std::uint8_t[]> data(new (std::nothrow) std::uint8_t[size]);
        if(!data) return false;
        bytes_=std::move(data);size_=size;return true;
    }
    std::uint8_t* data() noexcept {return bytes_.get();}
    const std::uint8_t* data() const noexcept {return bytes_.get();}
    std::size_t size() const noexcept {return size_;}
};
}
