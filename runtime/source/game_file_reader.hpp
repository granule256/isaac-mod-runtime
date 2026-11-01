#pragma once

#include "module_finder.hpp"
#include "runtime_constants.hpp"
// v2：sret 返回值垫片（必须在所有命名空间之外 include！）
#include "relay/smart_pointer_shim.hpp"

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

struct ScriptPathResolver;

struct Bindings {
    ConstructFn construct{nullptr};
    OpenReadFn openRead{nullptr};
    GetLengthFn getLength{nullptr};
    ReadFn read{nullptr};
    CloseFn close{nullptr};
    DestroyFn destroy{nullptr};
    ScriptPathResolver* scriptPathResolver{nullptr};
};

// 贴图桥用到的引擎入口（`ImagePcxLoad` 入口中继挂点的兜底依赖）。`z_stream*` 在设备侧没有
// `<zlib.h>`，所以这里把 zlib 三个符号按「`void*` 透传」声明（调用方负责保证底层结构布局一致）；
// 实际解压由 `hook_manager.cpp` 里的 `ImagePcxInflateOne` 用标准 64 位 `z_stream`（112 字节）发起。
//
// v2（2026-09-21 下午）：新增 `imageManagerLoadMemory` —— 五参「从内存加载」重载
// （`0x4d2654`），v2 兜底把转好的 PCX 字节喂给它，由引擎自己建对象、写缓存、返回 SmartPointer
// （经 `SmartPointerShim` 的 sret ABI 返回，见 `smart_pointer_shim.hpp`）。
using ImagePcxInMemoryLoadFn = bool (*)(void*, const uint8_t*, std::uint32_t, const char*);
using ZlibInflateInit2Fn = int (*)(void*, int, const char*, int);
using ZlibInflateFn = int (*)(void*, int);
using ZlibInflateEndFn = int (*)(void*);
using ImageManagerLoadMemoryFn = isaac::runtime::relay::SmartPointerShim (*)(
    void*, const uint8_t*, std::uint32_t, const char*, const char*, void*);
// v3：挂载解析 + 游戏侧 `operator delete[]`（见 runtime_constants.hpp 的「贴图桥 v3」段）。
// `File::OpenRead` 对打开失败是直接 Abort（真机 01789974615），所以兜底必须先解析挂载、
// 不存在就放弃，绝不能盲开。
using ContentManagerGetMountedFilePathFn = char* (*)(void*, const char*);
using GameOperatorDeleteArrayFn = void (*)(void*);
using GameOperatorNewArrayFn = void* (*)(std::size_t);

struct ImagePcxBindings {
    ImagePcxInMemoryLoadFn inMemoryLoad{nullptr};  // `Load(const uint8_t*,uint32_t,const char*)`
    ZlibInflateInit2Fn inflateInit2{nullptr};      // zlib `inflateInit2_`
    ZlibInflateFn inflate{nullptr};                // zlib `inflate`
    ZlibInflateEndFn inflateEnd{nullptr};          // zlib `inflateEnd`
    ImageManagerLoadMemoryFn imageManagerLoadMemory{nullptr};  // v2：五参内存版 LoadImage
    void* contentManager{nullptr};                 // v3：`g_ContentManager`（GOT 槽读出）
    ContentManagerGetMountedFilePathFn getMountedFilePath{nullptr};  // v3：挂载解析
    GameOperatorDeleteArrayFn operatorDeleteArray{nullptr};          // v3：还内存
    GameOperatorNewArrayFn operatorNewArray{nullptr};                // v4：造合成路径
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
// 贴图桥（`ImagePcxLoad`）兜底依赖的引擎入口校验：四个偏移（内存版 Load + 三个 zlib 符号）
// 全部对上守卫才返回 true；失败只让 `.png`→`.pcx` 兜底静默失效，不影响 Mod 安装。
bool VerifyImagePcxBindings(const TargetModule& module, ImagePcxBindings* bindings);
// 贴图桥绑定的**逐靶点**结果掩码（第 n 位 = 第 n 个靶点没过；0 = 全过）。
// 为什么逐个记：2026-09-21 真机踩过"一个新靶点没过 ⇒ 整套绑定被放弃 ⇒ 功能静默失效"，
// 而读数只看得到"8 个指针全空"、分不清是哪一个靶点的问题。
//   位 0 inMemoryLoad / 1 inflateInit2 / 2 inflate / 3 inflateEnd / 4 imageManagerLoadMemory
//   5 getMountedFilePath / 6 operatorDeleteArray / 7 operatorNewArray / 8 contentManager(GOT)
std::uint32_t LastImagePcxBindingMask() noexcept;
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
