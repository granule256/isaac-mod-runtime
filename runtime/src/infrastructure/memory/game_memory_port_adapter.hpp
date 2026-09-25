#pragma once

// `IGameMemoryPort` 的实现（架构诊断的"L1 引擎内存访问"）：把端口那四个入口落回
// `engine_field_access.hpp` 那一层原语上 —— 端口不另写一份指针算术。
//
// 背景：`src/ports/game_memory_port.hpp` 早在设计稿里就定义了这三个能力（读 / 解指针 / 调 thunk），
// 但一直**没有实现、没有调用点**（`docs/架构诊断-框架为什么失效-20260924.md` 第一节）。
// 本文件补上"实现"这一半。
//
// ## 与观察路径的分工（为什么不把 `game_observer.cpp` 也改成走端口）
//
// 端口这一层的失败是**两值**的（`Status::Ok` / 非 Ok），而 `game_observer` 一族必须把
// "链上某跳是**空指针**"与"链上某跳**不可读**"分成两档 —— 那个区分会作为状态码进崩溃报告
// （`OwnerNull`=39 / `OwnerUnreadable`=40 / `GameNull`=41 / `GameUnreadable`=42，见
// `hook_manager.cpp` 的 Stage6 上报）。套用两值接口会把这两档合并掉，等于**改真机上报语义**。
// 所以：观察路径用 `engine_field_access.hpp` 的自由函数（保住了逐档区分），
// 端口留给"不需要区分空/不可读"的消费方。
//
// ## 「这段地址可读吗」仍然由使用方注入
//
// 与 `engine_field_access.hpp` 同因（本文件不引 libnx）：判定要问内核，而 libnx 头不能进
// 同时包含 `<switch.h>` 的编译单元。所以适配器在**构造时**收一个判定函数。

#include "infrastructure/memory/engine_field_access.hpp"
#include "ports/game_memory_port.hpp"

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace isaac::runtime {

// 端口的默认实现：每次读都先过注入的可读性判定（设备侧是 `svcQueryMemory` 那一套，
// 命中区间缓存时不进内核）。
class GuardedGameMemoryPort final : public IGameMemoryPort {
public:
    explicit GuardedGameMemoryPort(engine_memory::ReadableCheck readable) noexcept
        : readable_(readable) {}

    [[nodiscard]] Status Read(std::uintptr_t address, void* target,
                              std::size_t size) noexcept override {
        if (target == nullptr || size == 0 || !engine_memory::RangeUsable(address, size) ||
            readable_ == nullptr || !readable_(address, size)) {
            return Status{StatusCode::InvalidArgument};
        }
        std::memcpy(target, reinterpret_cast<const void*>(address), size);
        return Status::Ok();
    }

    [[nodiscard]] Status ReadU64(std::uintptr_t address, std::uint64_t* value) noexcept override {
        if (value == nullptr) {
            return Status{StatusCode::InvalidArgument};
        }
        std::uint64_t loaded = 0;
        if (!engine_memory::ReadField(address, 0, &loaded, readable_, alignof(std::uint64_t))) {
            return Status{StatusCode::InvalidArgument};
        }
        *value = loaded;
        return Status::Ok();
    }

    [[nodiscard]] Status ResolvePointer(std::uintptr_t address,
                                        std::uintptr_t* value) noexcept override {
        if (value == nullptr || !engine_memory::LoadPointer(address, value, readable_)) {
            return Status{StatusCode::InvalidArgument};
        }
        return Status::Ok();
    }

    // `call.thunk` 必须已经由调用方验证是**可执行的模块代码**（本层不做代码段判定 ——
    // 与 `engine_field_access.hpp` 的 `CallUnaryMethod` 同一条分工）。
    [[nodiscard]] Status Call(const ThunkCall& call, std::uint64_t* result) noexcept override {
        if (call.thunk == 0 || call.argumentCount > 4) {
            return Status{StatusCode::InvalidArgument};
        }
        using Thunk = std::uint64_t (*)(std::uint64_t, std::uint64_t, std::uint64_t, std::uint64_t);
        const auto thunk = reinterpret_cast<Thunk>(call.thunk);
        const std::uint64_t returned =
            thunk(call.arguments[0], call.arguments[1], call.arguments[2], call.arguments[3]);
        if (result != nullptr) {
            *result = returned;
        }
        return Status::Ok();
    }

private:
    engine_memory::ReadableCheck readable_{nullptr};
};

// ---- 会话级默认实现（与 `ports/save_file_port.hpp` 的 `SessionSaveFilePort()` 同形）----------
//
// `inline` 变量（常量初始化，没有动态初始化顺序问题）—— 本模块用 `-nostartfiles` 链接，
// 刻意不用"函数内静态 + 守卫变量"那套。
//
// 还没接上（或构建里根本没接）⇒ 返回 nullptr ⇒ 消费方按"能力不可用"如实报，**不静默失败**，
// 也不要退回自己写指针算术 —— 那样就绕过了本层存在的意义。
inline IGameMemoryPort* g_engineMemoryPort = nullptr;

[[nodiscard]] inline IGameMemoryPort* EngineMemoryPort() noexcept {
    return g_engineMemoryPort;
}

inline void SetEngineMemoryPort(IGameMemoryPort* port) noexcept {
    g_engineMemoryPort = port;
}

} // namespace isaac::runtime