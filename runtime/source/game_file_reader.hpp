#pragma once

#include "module_finder.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cstddef>
#include <cstdint>

namespace GameFileReader {
// 模组文件读取要调的引擎入口：**声明类型只写一份**（2026-09-17，同 `lua_runtime_state.hpp`
// 那一批的做法）。为什么：这些入口是"我们手写签名、直接跳进游戏模块"的地方，签名写错就是崩游戏；
// 而在此之前，字段类型是 `uintptr_t`（谁都看不出期望什么参数），调用点各自再写一份 `using …Fn`
// 并 `reinterpret_cast`。现在字段本身就是那个函数指针类型，调用点直接调用，参数由编译器核对；
// ABI 体检也能顺着"`VerifyGameEntry(module, kXxxOffset, …, &verified.construct)`"读出声明类型。
using ConstructFn = void (*)(void*);
using OpenReadFn = bool (*)(void*, const char*);
using GetLengthFn = int (*)(const void*);
using ReadFn = int (*)(void*, void*, int, int);
using CloseFn = void (*)(void*);
using DestroyFn = void (*)(void*);
using OpenWriteFn = bool (*)(void*, const char*);
using WriteFn = int (*)(void*, const void*, int, int);

struct Bindings {
    ConstructFn construct{nullptr};
    OpenReadFn openRead{nullptr};
    GetLengthFn getLength{nullptr};
    ReadFn read{nullptr};
    CloseFn close{nullptr};
    DestroyFn destroy{nullptr};
};

struct WriteBindings {
    ConstructFn construct{nullptr};
    OpenWriteFn openWrite{nullptr};
    WriteFn write{nullptr};
    CloseFn close{nullptr};
    DestroyFn destroy{nullptr};
};

enum class ReadResult : std::uint32_t {
    Success,
    OpenFailed,
    LengthMismatch,
    ReadMismatch,
    ContentMismatch,
};

enum class ScriptReadResult : std::uint32_t {
    Success,
    OpenFailed,
    LengthOutOfRange,
    ReadMismatch,
};

bool VerifyBindings(const TargetModule& module, Bindings* bindings);
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 118
enum class WriteDiagnosticResult : std::uint32_t { Success, OpenFailed, WriteMismatch };
bool VerifyWriteBindings(const TargetModule& module, WriteBindings* bindings);
WriteDiagnosticResult WriteDiagnosticFile(const WriteBindings& bindings);
#endif
ReadResult ReadSentinel(const Bindings& bindings);
ScriptReadResult ReadScript(const Bindings& bindings,
                            std::array<u8, kRomfsLuaProbeMaximumLength>* buffer,
                            std::size_t* length);

#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
enum class TextReadResult : std::uint32_t {
    Success,
    InvalidArgument,
    OpenFailed,
    LengthOutOfRange,
    ReadMismatch,
};

TextReadResult ReadTextFile(const Bindings& bindings, const char* path,
                            u8* buffer, std::size_t capacity, std::size_t* length);
#endif
}
