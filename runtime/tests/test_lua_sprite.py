"""`Sprite`（引擎侧 `IsaacRepentance::ANM2`）第一步的行为测试（宿主可跑）。

覆盖：对象归属（我们分配/析构/释放）、`IsLoaded` 读引擎标志、`SetFrame` 两个重载的分派、
各方法参数与返回值原样透传、`Render`/`RenderLayer` 把 `Vector` 值按引用送到原生入口、
以及 `__gc` 恰好调用一次析构。

原生对象尺寸 `0x158` 的**出处**不在宿主侧（宿主不需要真实对象），而由
`tools/stage155_anm2_size_audit.py` 的分配步长分析给出，真机由探针校验。
"""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import layered_lua_runtime_sources
except ImportError:
    from test_support import layered_lua_runtime_sources


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include "game_observer.hpp"
// 批次 214：`Sprite:GetLayerCount` / `GetDefaultAnimationName` 读的是"引擎对象里的哪一格"，
// 断言必须用**同一批常量**（否则测试会把偏移的错误模型抄一遍，正是 207 那批踩过的坑）。
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {
    return GameIsPausedObservation::ThunkUnavailable;
}
GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t, std::uint32_t*) {
    return GameLevelStageObservation::GameUnreadable;
}
GameIsGreedModeObservation ObserveGameIsGreedMode(uintptr_t, uintptr_t) {
    return GameIsGreedModeObservation::MethodUnavailable;
}
GameIsAscentObservation ObserveLevelIsAscent(uintptr_t, uintptr_t) {
    return GameIsAscentObservation::MethodUnavailable;
}
GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**) {
    return GameItemPoolObservation::GameUnreadable;
}
GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {
    return GameRoomObservation::RoomUnreadable;
}
GameRoomObservation ReadCurrentGameRoomType(uintptr_t, std::uint32_t*) {
    return GameRoomObservation::RoomUnreadable;
}
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&, const char*, u8*, std::size_t, std::size_t*) {
    return TextReadResult::OpenFailed;
}
}

namespace {

// 假的原生 `ANM2`：对象尺寸与对齐按审计结论（0x158 / 16），ctor 在偏移 0 写入魔数，
// `+0x149` 是引擎自己的"已加载"标志（由脚本通过 `SPRITE_FLAG` 控制）。
constexpr std::uint64_t kSpriteMagic = 0x414E4D3253505231ULL;  // "ANM2SPR1"
// 对象大小按审计结论 `0x158`（`+0x149` 是引擎自己的"已加载"标志，由 `Sprite:IsLoaded` 直接读）。
constexpr std::size_t kSpriteSize = 0x158;

int g_ctorCalls = 0;
int g_dtorCalls = 0;
int g_updateCalls = 0;
int g_isPlayingAnyCalls = 0;
int g_isFinishedAnyCalls = 0;
// 批次 214：`Sprite:Reset()` 的原生替身被调了几次，以及最近一次构造出来的对象是谁
// （构造时就要把 `Sprite+0x30` 的 ANM2 指针装上 —— 脚本是在 ctor 之后才读那两格的）。
int g_resetCalls = 0;
//: 假的 `ANM2`：`+0xB0` 层数、`+0x98` 动画表数组、`+0xA0` 动画个数；数组第一条记录的开头
//: 就是那条动画名（libc++ 短串：首字节 = `长度<<1`、内容内联在 `+1`）。步长按常量 `0x150`。
alignas(16) unsigned char g_fakeAnm2[0x200] = {};
alignas(16) unsigned char g_fakeAnimations[2 * kAnim2AnimationStride] = {};
constexpr std::uint32_t kFakeLayerCount = 3;
constexpr const char* kFakeDefaultAnimation = "Default";
struct Call {
    char name[64];
    int flag;
    int number;
    int calls;
};
Call g_play{};
Call g_setAnimation{};
Call g_setFrameNamed{};
Call g_setFrame{};
Call g_setLayerFrame{};
Call g_playRandom{};
//: 批次 279：overlay 三条的记录（`PlayOverlay` 用 name+flag、`SetLastFrame` 只数次数、
//: `SetOverlayFrame` 用 name+帧号）。
Call g_playOverlay{};
Call g_setOverlayFrame{};
int g_setLastFrameCalls = 0;
//: 批次 280：`Stop` 的次数。
int g_stopCalls = 0;
struct RenderCall {
    int layer;
    float positionX;
    float positionY;
    float topLeftX;
    float topLeftY;
    float bottomRightX;
    float bottomRightY;
    int calls;
};
RenderCall g_render{};
RenderCall g_renderLayer{};

int g_texelCalls = 0;
LuaRuntime::SpriteTexelColor FakeGetTexel(void* self, LuaRuntime::SpriteTexelVector sample,
                                         LuaRuntime::SpriteTexelVector render, float threshold, int layer) {
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(81);
    ++g_texelCalls;
    return {sample.x / 10.0F + render.x, sample.y / 10.0F + render.y, threshold, layer / 10.0F};
}

void FakeCtor(void* self) {
    std::memset(self, 0, kSpriteSize);
    *static_cast<std::uint64_t*>(self) = kSpriteMagic;
    // 批次 214：构造出来的 Sprite 立刻指向那块假 ANM2（脚本随后就会问层数与默认动画名）。
    *reinterpret_cast<std::uintptr_t*>(static_cast<unsigned char*>(self) + kSpriteAnm2Offset) =
        reinterpret_cast<std::uintptr_t>(g_fakeAnm2);
    // ANM2::AnmCache::Load2实际将声明的DefaultAnimation写入this+0x18。
    // 故意与动画表第一条Default不同；Custom Bossbar用数字字符串作为宽度。
    static constexpr char defaultName[] = "110";
    auto* bytes = static_cast<unsigned char*>(self);
    bytes[0x18] = 3U << 1;
    std::memcpy(bytes + 0x19, defaultName, sizeof(defaultName));
    ++g_ctorCalls;
}

// 批次 214：`ANM2::Reset()` 的替身（真实入口 `0x4A4724`，宿主上没有引擎映像）。
void FakeReset(void* self) {
    if (self == nullptr) std::exit(57);
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(58);
    ++g_resetCalls;
}

void FakeDtor(void* self) {
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) {
        std::exit(31);
    }
    ++g_dtorCalls;
}

void Record(Call* call, const char* text, int flag, int number) {
    std::snprintf(call->name, sizeof(call->name), "%s", text == nullptr ? "" : text);
    call->flag = flag;
    call->number = number;
    ++call->calls;
}

void FakePlay(void* self, const char* name, bool force) {
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(32);
    Record(&g_play, name, force ? 1 : 0, 0);
}

bool FakeSetAnimation(void* self, const char* name, bool reset) {
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(33);
    Record(&g_setAnimation, name, reset ? 1 : 0, 0);
    // 返回"是否成功"；`reset` 标志单独由宿主断言，避免两者混在一个返回值里。
    return true;
}


// 批次 279：overlay 三条的假实现（都验 `self` 上的魔数 —— 与既有假函数同一道关）。
void FakePlayOverlay(void* self, const char* name, bool force) {
    if (self == nullptr) std::exit(59);
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(60);
    Record(&g_playOverlay, name, force ? 1 : 0, 0);
}

void FakeSetLastFrame(void* self) {
    if (self == nullptr) std::exit(61);
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(62);
    ++g_setLastFrameCalls;
}

void FakeSetOverlayFrame(void* self, const char* name, int frame) {
    if (self == nullptr) std::exit(63);
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(64);
    Record(&g_setOverlayFrame, name, 0, frame);
}

void FakeStop(void* self) {
    if (self == nullptr) std::exit(65);
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(66);
    ++g_stopCalls;
}

// ---- 批次 283：四条「按名字查询」的假实现 ------------------------------------------------
//
// ★ 这四条与上面 overlay 三条的**关键区别**：第二个参数是 **libc++ 的 24 字节
//   `std::string` 对象**（引擎侧只有 `std::string const&` 那一份签名），所以这里要用既有的
//   `CheckNativeString` 验它装的正是刚刚 `assign` 进去的那个名字 —— 那一句就是"字符串桥真的
//   被走到了"的判据（overlay 三条走的是 `char const*`，压根没有这一跳）。
// ★ 判据刻意**不用** `CheckNativeString`（那个是拿"最后一次 assign 的路径"去比）：字符串桥
//   是**按路径缓存**的，同一个名字第二次出现时不会再过 `assign` ⇒ 拿"最后一次 assign"去比
//   会误判。这里改成**直接把交下来的那块对象解码出来** —— 判据更强（验的是对象内容本身），
//   而且完全不依赖缓存行为。
// （解码规则与下面假 `assign` 写进去的形式严格互逆，见那一节的注释。）
const char* DecodeNativeString(const void* object, char* buffer, std::size_t capacity) {
    buffer[0] = '\0';
    if (object == nullptr) {
        return buffer;
    }
    const auto* bytes = static_cast<const unsigned char*>(object);
    const auto* words = static_cast<const std::uint64_t*>(object);
    const char* data = nullptr;
    std::size_t length = 0;
    if ((words[0] & 1ULL) == 0) {
        data = reinterpret_cast<const char*>(bytes + 1);
        length = static_cast<std::size_t>(bytes[0] >> 1);
    } else {
        length = static_cast<std::size_t>(words[1]);
        data = reinterpret_cast<const char*>(words[2]);
    }
    if (data == nullptr) {
        return buffer;
    }
    if (length >= capacity) {
        length = capacity - 1;
    }
    std::memcpy(buffer, data, length);
    buffer[length] = '\0';
    return buffer;
}

char g_lastQueryName[64] = {};
int g_overlayPlayingCalls = 0;
int g_overlayFinishedCalls = 0;
int g_eventTriggeredCalls = 0;
int g_wasEventTriggeredCalls = 0;
//: 省参数的调用必须落到"空串"那条路（引擎在 `IsOverlayPlaying`@0xAC04 /
//: `IsOverlayFinished`@0xACF0 对空名字有专门分支，直接给 true）。
int g_emptyNameQueries = 0;

void RecordQueryName(const void* nativeString, int exitCode) {
    if (nativeString == nullptr) std::exit(exitCode);
    DecodeNativeString(nativeString, g_lastQueryName, sizeof(g_lastQueryName));
    if (g_lastQueryName[0] == '\0') {
        ++g_emptyNameQueries;
    }
}

bool FakeIsOverlayPlaying(const void* self, const void* nativeString) {
    if (*static_cast<const std::uint64_t*>(self) != kSpriteMagic) std::exit(67);
    RecordQueryName(nativeString, 68);
    ++g_overlayPlayingCalls;
    return std::strcmp(g_lastQueryName, "Nope") != 0;
}

bool FakeIsOverlayFinished(const void* self, const void* nativeString) {
    if (*static_cast<const std::uint64_t*>(self) != kSpriteMagic) std::exit(69);
    RecordQueryName(nativeString, 70);
    ++g_overlayFinishedCalls;
    return std::strcmp(g_lastQueryName, "Nope") != 0;
}

bool FakeIsEventTriggered(const void* self, const void* nativeString) {
    if (*static_cast<const std::uint64_t*>(self) != kSpriteMagic) std::exit(71);
    RecordQueryName(nativeString, 72);
    ++g_eventTriggeredCalls;
    return std::strcmp(g_lastQueryName, "Attack") == 0;
}

bool FakeWasEventTriggered(const void* self, const void* nativeString) {
    if (*static_cast<const std::uint64_t*>(self) != kSpriteMagic) std::exit(73);
    RecordQueryName(nativeString, 74);
    ++g_wasEventTriggeredCalls;
    return std::strcmp(g_lastQueryName, "Nope") != 0;
}

void FakeSetFrameNamed(void* self, const char* name, int frame) {
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(34);
    Record(&g_setFrameNamed, name, 0, frame);
}

void FakeSetFrame(void* self, int frame) {
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(35);
    Record(&g_setFrame, "", 0, frame);
}

int FakeGetFrame(const void* self) {
    if (*static_cast<const std::uint64_t*>(self) != kSpriteMagic) std::exit(36);
    return 7;
}

void FakeSetLayerFrame(void* self, int layer, int frame) {
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(37);
    Record(&g_setLayerFrame, "", layer, frame);
}

int FakeGetLayerFrame(void* self, int layer) {
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(38);
    return layer + 100;
}

void FakeUpdate(void* self) {
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(39);
    ++g_updateCalls;
}

// 引擎语义（`ANM2::IsPlaying(char const*)` / `IsFinished(char const*)`）：**空名字**表示
// "只看当前动画在不在播"，所以省参数的调用必须传空串而不是 nullptr。
bool FakeIsPlaying(const void* self, const char* name) {
    if (*static_cast<const std::uint64_t*>(self) != kSpriteMagic) std::exit(40);
    if (name == nullptr) std::exit(43);
    if (name[0] == '\0') { ++g_isPlayingAnyCalls; return true; }
    return std::strcmp(name, "Idle") == 0;
}

bool FakeIsFinished(const void* self, const char* name) {
    if (*static_cast<const std::uint64_t*>(self) != kSpriteMagic) std::exit(41);
    if (name == nullptr) std::exit(44);
    if (name[0] == '\0') { ++g_isFinishedAnyCalls; return false; }
    return std::strcmp(name, "Done") == 0;
}

void FakePlayRandom(void* self, unsigned int seed) {
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(42);
    Record(&g_playRandom, "", 0, static_cast<int>(seed));
}

void RecordRender(RenderCall* call, int layer, const void* position, const void* topLeft,
                  const void* bottomRight) {
    const auto* p = static_cast<const float*>(position);
    const auto* t = static_cast<const float*>(topLeft);
    const auto* b = static_cast<const float*>(bottomRight);
    call->layer = layer;
    call->positionX = p[0];
    call->positionY = p[1];
    call->topLeftX = t[0];
    call->topLeftY = t[1];
    call->bottomRightX = b[0];
    call->bottomRightY = b[1];
    ++call->calls;
}

void FakeRender(void* self, const void* position, const void* topLeft, const void* bottomRight) {
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(43);
    RecordRender(&g_render, -1, position, topLeft, bottomRight);
}

void FakeRenderLayer(void* self, int layer, const void* position, const void* topLeft,
                     const void* bottomRight) {
    if (*static_cast<std::uint64_t*>(self) != kSpriteMagic) std::exit(44);
    RecordRender(&g_renderLayer, layer, position, topLeft, bottomRight);
}

// 假的 libc++ `basic_string::assign(char const*)`：只验证**调用序列与内容**（零初始化 → assign(路径)
// → 把同一个对象交给 Load）。真实的 libc++ SSO 布局由真机探针校验，宿主侧不假装知道它。
char g_lastAssignedPath[256] = {};
int g_assignCalls = 0;
int g_loadCalls = 0;
int g_loadGraphicsCalls = 0;
int g_replaceCalls = 0;
int g_replaceLayer = -1;
const void* g_lastStringObject = nullptr;
void* g_stringObjects[4] = {};
int g_stringObjectCount = 0;

// 假 `basic_string::assign`：短路径写成 libc++ 的短串形式（首字节 = size<<1、内容内联），
// 长路径写成 `__long`（首字最低位 = 1、数据指针在偏移 16）并 malloc 一份 —— 这样可以验证
// "长路径必须用**游戏自己的** operator delete 释放，而不是本模块的 free"。
int g_releasedLongStrings = 0;
void* g_lastReleased = nullptr;

void FakeOperatorDelete(void* pointer) {
    ++g_releasedLongStrings;
    g_lastReleased = pointer;
    std::free(pointer);
}

void* FakeAssign(void* object, const char* text) {
    if (object == nullptr || text == nullptr) std::exit(51);
    std::snprintf(g_lastAssignedPath, sizeof(g_lastAssignedPath), "%s", text);
    ++g_assignCalls;
    auto* bytes = static_cast<unsigned char*>(object);
    const std::size_t length = std::strlen(text);
    std::memset(bytes, 0, 24);
    if (length <= 22) {
        bytes[0] = static_cast<unsigned char>(length << 1);
        std::memcpy(bytes + 1, text, length);
    } else {
        char* copy = static_cast<char*>(std::malloc(length + 1));
        std::memcpy(copy, text, length + 1);
        auto* words = reinterpret_cast<std::uint64_t*>(bytes);
        words[0] = (length + 1) | 1ULL;   // long 标志在最低位
        words[1] = length;
        words[2] = reinterpret_cast<std::uint64_t>(copy);
    }
    return object;
}

// 按 libc++ 的真实布局校验原生字符串对象装的是 `g_lastAssignedPath`：
// 短串首字节 = size<<1、内容内联在 +1；长串首字最低位 = 1、大小在 +8、数据指针在 +16。
void CheckNativeString(const void* nativeString, int code) {
    if (nativeString == nullptr) std::exit(code);
    const auto* bytes = static_cast<const unsigned char*>(nativeString);
    const auto* words = static_cast<const std::uint64_t*>(nativeString);
    const std::size_t length = std::strlen(g_lastAssignedPath);
    if ((words[0] & 1ULL) == 0) {
        if (bytes[0] != (length << 1)) std::exit(code);
        if (std::strncmp(reinterpret_cast<const char*>(bytes + 1), g_lastAssignedPath, length) != 0) {
            std::exit(code);
        }
        return;
    }
    if (words[1] != length) std::exit(code);
    const auto* data = reinterpret_cast<const char*>(words[2]);
    if (data == nullptr || std::strcmp(data, g_lastAssignedPath) != 0) std::exit(code);
}

void FakeLoad(void* self, const void* nativeString, bool loadGraphics) {
    if (*static_cast<const std::uint64_t*>(self) != kSpriteMagic) std::exit(52);
    CheckNativeString(nativeString, 53);
    g_lastStringObject = nativeString;
    if (g_stringObjectCount < 4) {
        g_stringObjects[g_stringObjectCount] = const_cast<void*>(nativeString);
    }
    ++g_stringObjectCount;
    g_play.flag = loadGraphics ? 1 : 0;  // 复用字段记录 bool 实参
    ++g_loadCalls;
}

void FakeLoadGraphics(void* self) {
    if (*static_cast<const std::uint64_t*>(self) != kSpriteMagic) std::exit(54);
    ++g_loadGraphicsCalls;
}

void FakeReplaceSpritesheet(void* self, int layer, const void* nativeString) {
    if (*static_cast<const std::uint64_t*>(self) != kSpriteMagic) std::exit(55);
    CheckNativeString(nativeString, 56);
    g_replaceLayer = layer;
    ++g_replaceCalls;
}

const char* kScript = R"lua(@SCRIPT@)lua";

int Report(int code) {
    std::printf("SPRITE_FAIL code=%d ctor=%d dtor=%d update=%d play=%s/%d setAnim=%s/%d "
                "setFrameNamed=%s/%d setFrame=%d layer=%d/%d random=%d render=%.1f,%.1f tl=%.1f,%.1f "
                "br=%.1f,%.1f renderLayer=%d %.1f,%.1f reset=%d overlay=%s/%d last=%d oframe=%s/%d\n",
                code, g_ctorCalls, g_dtorCalls, g_updateCalls, g_play.name, g_play.flag,
                g_setAnimation.name, g_setAnimation.flag, g_setFrameNamed.name,
                g_setFrameNamed.number, g_setFrame.number, g_setLayerFrame.flag,
                g_setLayerFrame.number, g_playRandom.number, g_render.positionX, g_render.positionY,
                g_render.topLeftX, g_render.topLeftY, g_render.bottomRightX, g_render.bottomRightY,
                g_renderLayer.layer, g_renderLayer.positionX, g_renderLayer.positionY,
                g_resetCalls, g_playOverlay.name, g_playOverlay.flag, g_setLastFrameCalls,
                g_setOverlayFrame.name, g_setOverlayFrame.number);
    return code;
}

} // namespace

int main() {
    LuaRuntime::LuaSpriteBindings bindings{};
    bindings.ctor = &FakeCtor;
    if (std::getenv("TEXEL_MISSING") == nullptr) bindings.getTexel = &FakeGetTexel;
    bindings.destructor_ = &FakeDtor;
    bindings.play = &FakePlay;
    bindings.setAnimation = &FakeSetAnimation;
    bindings.setFrameNamed = &FakeSetFrameNamed;
    bindings.setFrame = &FakeSetFrame;
    bindings.getFrame = &FakeGetFrame;
    bindings.setLayerFrame = &FakeSetLayerFrame;
    bindings.getLayerFrame = &FakeGetLayerFrame;
    bindings.update = &FakeUpdate;
    bindings.isPlaying = &FakeIsPlaying;
    bindings.isFinished = &FakeIsFinished;
    bindings.render = &FakeRender;
    bindings.renderLayer = &FakeRenderLayer;
    bindings.playRandom = &FakePlayRandom;
    // 批次 279：overlay 三条（同一个 `LuaSpriteBindings` 结构，槽数 22 → 25）。
    bindings.playOverlay = &FakePlayOverlay;
    bindings.setLastFrame = &FakeSetLastFrame;
    bindings.setOverlayFrame = &FakeSetOverlayFrame;
    // 批次 280：`Stop`（槽数 25 → 26）。
    bindings.stop = &FakeStop;
    // 批次 283：四条「按名字查询」（槽数 26 → 30）。
    bindings.isOverlayPlaying = &FakeIsOverlayPlaying;
    bindings.isOverlayFinished = &FakeIsOverlayFinished;
    bindings.isEventTriggered = &FakeIsEventTriggered;
    bindings.wasEventTriggered = &FakeWasEventTriggered;
    bindings.load = &FakeLoad;
    bindings.loadGraphics = &FakeLoadGraphics;
    bindings.replaceSpritesheet = &FakeReplaceSpritesheet;
    bindings.libcxxStringAssign = &FakeAssign;
    bindings.gameOperatorDelete = &FakeOperatorDelete;
    // 批次 214：`Sprite:Reset()` 走的是**同一个** `LuaSpriteBindings`（第 21 个槽）。
    bindings.reset = &FakeReset;
    LuaRuntime::SetSpriteBindings(bindings);

    // 批次 214：把假 `ANM2` 填好 —— 层数、动画表数组、动画个数，以及**第一条**动画的名字。
    // 第二条名字故意不同，用来证明 `GetDefaultAnimationName` 取的是第一条而不是随便一条。
    *reinterpret_cast<std::uint32_t*>(g_fakeAnm2 + kAnim2LayerCountOffset) = kFakeLayerCount;
    *reinterpret_cast<std::uintptr_t*>(g_fakeAnm2 + kAnim2AnimationArrayOffset) =
        reinterpret_cast<std::uintptr_t>(g_fakeAnimations);
    *reinterpret_cast<std::uint32_t*>(g_fakeAnm2 + kAnim2AnimationCountOffset) = 2;
    {
        const std::size_t length = std::strlen(kFakeDefaultAnimation);
        g_fakeAnimations[0] = static_cast<unsigned char>(length << 1);
        std::memcpy(g_fakeAnimations + 1, kFakeDefaultAnimation, length);
        const char* second = "Walk";
        const std::size_t secondLength = std::strlen(second);
        unsigned char* record = g_fakeAnimations + kAnim2AnimationStride;
        record[0] = static_cast<unsigned char>(secondLength << 1);
        std::memcpy(record + 1, second, secondLength);
    }

    const auto result = LuaRuntime::InitializeFromBuffer(kScript, std::strlen(kScript), "@sprite.lua");
    if (result != LuaRuntime::LuaInitResult::Success) return 2;
    LuaRuntime::DispatchPostUpdate();
    if (LuaRuntime::TakeCallbackError()) return 3;

    // 脚本里的断言（用退出码报告，方便定位）。
    if (g_ctorCalls != 1) return Report(11);
    if (std::strcmp(g_play.name, "Idle") != 0 || g_play.flag != 1 || g_play.calls != 1) return Report(12);
    if (std::strcmp(g_setAnimation.name, "Walk") != 0 || g_setAnimation.flag != 0) return Report(13);
    // 记的是**最后一次**调用的实参 ⇒ 这两条现在覆盖"整值浮点也被接受"那一次
    // （`9.0`/`10.0` 分别走两个重载，`calls == 2` 证明整数形式那一次也真的调到了原生入口）。
    if (std::strcmp(g_setFrameNamed.name, "Walk") != 0 || g_setFrameNamed.number != 10) return Report(14);
    if (g_setFrame.number != 9 || g_setFrame.calls != 2) return Report(15);
    if (g_setLayerFrame.flag != 2 || g_setLayerFrame.number != 9) return Report(16);
    if (g_updateCalls != 2) return Report(17);
    // 省掉动画名的两次调用必须走"空串"路径（引擎语义：只看当前动画）
    if (g_isPlayingAnyCalls != 1) return Report(18);
    if (g_isFinishedAnyCalls != 1) return Report(19);
    if (g_playRandom.number != 1234) return Report(18);
    if (g_render.calls != 1 || g_render.positionX != 10.0f || g_render.positionY != 20.0f ||
        g_render.topLeftX != 0.0f || g_render.topLeftY != 0.0f || g_render.bottomRightX != 0.0f ||
        g_render.bottomRightY != 0.0f) {
        return Report(19);
    }
    if (g_renderLayer.calls != 1 || g_renderLayer.layer != 3 || g_renderLayer.positionX != 1.0f ||
        g_renderLayer.positionY != 2.0f || g_renderLayer.topLeftX != -1.0f ||
        g_renderLayer.bottomRightX != 5.0f) {
        return Report(20);
    }
    std::printf("SPRITE_ASSIGN calls=%d\n", g_assignCalls);
    // 3 次常规 Load + 40 次"塞满缓存"的长路径 Load
    if (g_loadCalls != 3 + 40) return Report(22);
    if (g_loadGraphicsCalls != 1) return Report(23);
    // 2 次 `ReplaceSpritesheet`：一次真实路径（层 4）、一次**空串**（层 1，EID 的清层用法）。
    if (g_replaceCalls != 2 || g_replaceLayer != 1) return Report(24);
    // 同一路径的两次 Load 必须复用同一个原生字符串对象；不同路径必须换一个（缓存按路径键控）。
    // 前三次（三个不同路径）必须各自拿到一个对象；后面 40 次长路径会复用/轮转缓存，所以只看 >= 3。
    if (g_stringObjectCount < 3) return Report(25);
    if (g_stringObjects[0] != g_stringObjects[1]) return Report(26);
    if (g_stringObjects[2] == g_stringObjects[0]) return Report(27);
    // 三个**不同**路径 -> 恰好三次 assign（同路径的第二次 Load 命中缓存，不再 assign）
    // +1：`ReplaceSpritesheet(1, '')` 也要建一次原生字符串（空串是一条独立缓存条目）。
    // ★ 批次 283 再加 **5**：四条「按名字查询」用了 5 个不同的名字
    //   （Burst / Nope / Attack / Other / Hurt），每个新路径各一次 `assign`；
    //   而**省参数**那两次传的是空串，命中上面那条空串缓存 ⇒ 不再 assign。
    //   ⇒ 这条断言顺带钉住了"字符串桥是按路径缓存的"这件事本身。
    if (g_assignCalls != 3 + 40 + 1 + 5) return Report(28);
    // 缓存塞满 40 条长路径后，必须有条目被释放，而且走的是游戏自己的 operator delete。
    if (g_releasedLongStrings < 8) return Report(29);
    if (g_lastReleased == nullptr) return Report(30);
    if (g_dtorCalls != 1) return Report(21);
    // 批次 214：`sprite:Reset()` 恰好调到原生入口一次，且拿到的就是我们构造的那个对象。
    if (g_resetCalls != 1) return Report(31);
    // 批次 279：overlay 三条必须把实参**原样**送到原生入口（名字 / 布尔 / 帧号），
    // 而且各自恰好一次（形状错的那些在脚本里已被 `pcall` 拦下）。
    if (g_playOverlay.calls != 1 || std::strcmp(g_playOverlay.name, "Anim0") != 0 ||
        g_playOverlay.flag != 1) {
        return Report(41);
    }
    if (g_setLastFrameCalls != 1) return Report(42);
    if (g_setOverlayFrame.calls != 1 || std::strcmp(g_setOverlayFrame.name, "Walk") != 0 ||
        g_setOverlayFrame.number != 3) {
        return Report(43);
    }
    // 批次 280：`Stop` 恰好一次。
    if (g_stopCalls != 1) return Report(44);
    // 批次 283：四条「按名字查询」。
    //   * 每条恰好调到原生入口一次（形状错的那些在脚本里已被 `pcall` 拦下）；
    //   * ★ 其中 `IsOverlayPlaying` / `IsOverlayFinished` 各多一次**省参数**调用 ⇒
    //     那两次必须落到"空串"路径（`g_emptyNameQueries == 2`）—— 这是"PC 的无参重载
    //     在引擎里就是空名字"这条判断的宿主侧判据（真机侧再确认返回值）。
    if (g_overlayPlayingCalls != 3 || g_overlayFinishedCalls != 3) return Report(45);
    if (g_eventTriggeredCalls != 2 || g_wasEventTriggeredCalls != 2) return Report(46);
    if (g_emptyNameQueries != 2) return Report(47);
    // 最后记下的名字应当是 `WasEventTriggered` 那一次的实参（脚本里的顺序是固定的）。
    if (std::strcmp(g_lastQueryName, "Nope") != 0) return Report(48);
    std::printf("SPRITE_QUERY overlay=%d/%d event=%d/%d empty=%d last=%s\n",
                g_overlayPlayingCalls, g_overlayFinishedCalls, g_eventTriggeredCalls,
                g_wasEventTriggeredCalls, g_emptyNameQueries, g_lastQueryName);
    std::printf("SPRITE_OVERLAY overlay=%s/%d last=%d oframe=%s/%d stop=%d\n", g_playOverlay.name,
                g_playOverlay.flag, g_setLastFrameCalls, g_setOverlayFrame.name,
                g_setOverlayFrame.number, g_stopCalls);
    std::printf("SPRITE_OK ctor=%d dtor=%d update=%d any=%d/%d released=%d reset=%d\n", g_ctorCalls,
                g_dtorCalls, g_updateCalls, g_isPlayingAnyCalls, g_isFinishedAnyCalls,
                g_releasedLongStrings, g_resetCalls);
    return 0;
}
'''


SCRIPT = r'''
local mod = RegisterMod('Sprite', 1)

local function near(actual, expected, label)
  if math.abs(actual - expected) > 0.0005 then
    error(label .. ': expected ' .. expected .. ', got ' .. actual)
  end
end

mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
  local ok, err = pcall(function()
  local sprite = Sprite()
  -- 刚构造的 Sprite 没有加载图形（引擎自己的标志 +0x149）
  if sprite:IsLoaded() then error('a fresh Sprite must not report IsLoaded') end

  -- 字符串桥：同一路径两次 Load 必须复用同一个原生字符串对象（缓存），另加一次不同路径。
  sprite:Load('gfx/probe147.anm2', true)
  sprite:Load('gfx/probe147.anm2', true)
  sprite:Load('gfx/other.anm2', false)
  sprite:LoadGraphics()
  sprite:ReplaceSpritesheet(4, 'gfx/replaced.png')
  -- ★ 空串是**合法**参数（2026-09-12 真机报告 `01789225234` 定案）：EID 的
  -- `loadCustomSprites` 先用空串清掉某一层的图集替换、再用真实路径替换。旧实现把空串
  -- 当成"建字符串失败"抛 Lua 错误 ⇒ 整条描述构建被打断（进到道具范围内什么都不显示）。
  -- 这条断言就是钉住"空串不再报错"。
  sprite:ReplaceSpritesheet(1, '')

  sprite:Play('Idle', true)
  if not sprite:SetAnimation('Walk', false) then error('SetAnimation must return the native bool') end
  sprite:SetFrame(5)
  sprite:SetFrame('Walk', 6)
  -- 整值浮点：Lua 的 `/` **永远**产生浮点，模组很容易把算过的帧号传进来；
  -- PC 的绑定走 `luaL_checkinteger`（接受 3.0），我们此前用 `lua_isinteger` 会拒 ——
  -- 2026-09-18 真机就是这条把 EID 的药丸描述整条拒掉（屏幕上"什么信息都没有"）。
  sprite:SetFrame(9.0)
  sprite:SetFrame('Walk', 10.0)
  if sprite:GetFrame() ~= 7 then error('GetFrame must return the native value') end
  sprite:SetLayerFrame(2, 9)
  if sprite:GetLayerFrame(4) ~= 104 then error('GetLayerFrame must return the native value') end
  sprite:Update()
  sprite:Update()
  if not sprite:IsPlaying('Idle') then error('IsPlaying(Idle)') end
  if sprite:IsPlaying('Walk') then error('IsPlaying(Walk) must be false') end
  if not sprite:IsFinished('Done') then error('IsFinished(Done)') end
  -- PC 文档形参是 [0, 1]：省掉动画名也必须可用，且传下去的是**空串**（引擎的"只看当前动画"语义）
  if not sprite:IsPlaying() then error('IsPlaying() must ask for the current animation') end
  if sprite:IsFinished() then error('IsFinished() must be false in the fake') end
  sprite:PlayRandom(1234)

  -- 批次 214：中文版 MCM（工坊 2494192799）的 `scripts/filepathhelper.lua` 要的三条。
  -- 它用 `GetDefaultAnimationName() ~= '' or GetLayerCount() > 0` 判断"这条路径是不是真 anm2"，
  -- 紧接着调 `Reset()` —— 三行**都不在 pcall 里** ⇒ 缺任何一条都会把它整条回调打断。
  if sprite:GetLayerCount() ~= 3 then
    error('GetLayerCount must read ANM2+0xB0, got ' .. tostring(sprite:GetLayerCount()))
  end
  -- 声明默认动画110与动画表首项Default故意不同，禁止再将表首当默认值。
  if sprite:GetDefaultAnimationName() ~= '110' then
    error('GetDefaultAnimationName must read declared DefaultAnimation 110, got '
      .. tostring(sprite:GetDefaultAnimationName()))
  end
  local length = sprite:GetDefaultAnimationName()
  local rightClamp = Vector(length - 50 / 100 * length, 0)
  if rightClamp.X ~= 55 then error('Custom Bossbar half-health width must be 55') end
  sprite:Reset()

  -- 批次 279：overlay 三条（`PlayOverlay` 12 处 / `SetLastFrame` 6 处 / `SetOverlayFrame` 1 处）。
  -- 三条都走 `char const*` 重载（避开 libc++ `std::string` 桥）。
  sprite:PlayOverlay('Anim0', true)
  sprite:SetLastFrame()
  sprite:SetOverlayFrame('Walk', 3)
  -- 批次 280：`Stop()` + `GetDefaultAnimation()`（契约说它与 `…Name` 同一件事）
  sprite:Stop()
  if sprite:GetDefaultAnimation() ~= sprite:GetDefaultAnimationName() then
    error('GetDefaultAnimation must agree with GetDefaultAnimationName')
  end
  if sprite:GetDefaultAnimation() ~= '110' then
    error('GetDefaultAnimation must read declared DefaultAnimation 110')
  end
  if pcall(function() return sprite:Stop(1) end) then
    error('Stop accepts no arguments')
  end
  if pcall(function() return sprite:GetDefaultAnimation(1) end) then
    error('GetDefaultAnimation accepts no arguments')
  end
  -- 批次 283：四条「按名字查询」。★ 它们走的是**另一条字符串路** —— 引擎侧只有
  -- `std::string const&` 那一份签名（**没有** `char const*` 重载可选）⇒ 必须过 libc++ 字符串桥；
  -- 宿主把交下去的那块对象**解码回来**比对，验的就是"桥真的被走到了"，而且不依赖桥内部的缓存行为。
  -- ★ PC 给 `IsOverlayPlaying` / `IsOverlayFinished` **各写了两个重载**（`(name)` 与 `()`）
  --   ⇒ 省参数必须可用，且传下去的是**空串**：引擎对空名字有专门分支
  --   （`IsOverlayPlaying`@0xAC04 / `IsOverlayFinished`@0xACF0 都是 `mov w0, #1`）。
  if not sprite:IsOverlayPlaying('Burst') then error('IsOverlayPlaying(Burst)') end
  if sprite:IsOverlayPlaying('Nope') then error('IsOverlayPlaying(Nope) must be false') end
  if not sprite:IsOverlayPlaying() then error('IsOverlayPlaying() must ask for any overlay') end
  if not sprite:IsOverlayFinished('Burst') then error('IsOverlayFinished(Burst)') end
  if sprite:IsOverlayFinished('Nope') then error('IsOverlayFinished(Nope) must be false') end
  if not sprite:IsOverlayFinished() then error('IsOverlayFinished() must ask for any overlay') end
  if not sprite:IsEventTriggered('Attack') then error('IsEventTriggered(Attack)') end
  if sprite:IsEventTriggered('Other') then error('IsEventTriggered(Other) must be false') end
  if not sprite:WasEventTriggered('Hurt') then error('WasEventTriggered(Hurt)') end
  if sprite:WasEventTriggered('Nope') then error('WasEventTriggered(Nope) must be false') end
  -- ★ 而 `IsEventTriggered` / `WasEventTriggered` **没有**无参重载 ⇒ 省参数必须报错。
  if pcall(function() return sprite:IsEventTriggered() end) then
    error('IsEventTriggered must require the event name (PC has no zero-arg overload)')
  end
  if pcall(function() return sprite:WasEventTriggered() end) then
    error('WasEventTriggered must require the event name (PC has no zero-arg overload)')
  end
  -- 形状闸门：非字符串也必须报错（PC 的绑定层同样会拒）。
  if pcall(function() return sprite:IsOverlayPlaying(1) end) then
    error('IsOverlayPlaying must reject a non-string name')
  end
  -- 形状闸门：下面四种必须报错（模组写错了，PC 也会报）
  if pcall(function() return sprite:PlayOverlay('Anim0') end) then
    error('PlayOverlay must require the force flag')
  end
  if pcall(function() return sprite:PlayOverlay(1, true) end) then
    error('PlayOverlay must reject a non-string name')
  end
  if pcall(function() return sprite:SetLastFrame(1) end) then
    error('SetLastFrame accepts no arguments')
  end
  if pcall(function() return sprite:SetOverlayFrame('Walk') end) then
    error('SetOverlayFrame must require the frame number')
  end

  -- `Sprite:GetTexel`（2026-09-12）：EID 的 `IsAltChoice`（`main.lua:230`）用它逐像素比对
  -- 底座贴图，PC 签名是 `GetTexel(Vector SamplePos, Vector RenderPos = Vector.Zero,
  -- float AlphaThreshold = 0, int LayerID = 0)`，返回 KColor。
  -- 缺这个方法就是"调 nil"、整条渲染链被派发器摘除（真机报告 `01789211565`）。
  --
  -- ★ 本轮（动作一）把它从"恒返回不透明白色"的占位换成**调用引擎自己的
  -- `ANM2::GetTexel`**（偏移 `0xC074`，HFA 按值传 s0..s3、返回值走 x8）。
  -- 2026-10-20：宿主假入口返回随参数变化的非白 RGBA，验证真实 Lua 绑定、
  -- 默认参数和所有分量；缺入口的独立运行必须明确报错，不得返回伪造像素。
  local okTexel, texel = pcall(function() return sprite:GetTexel(Vector(1, 2)) end)
  if okTexel then
    near(texel.Red, 0.1, 'default sample x')
    near(texel.Green, 0.2, 'default sample y')
    near(texel.Blue, 0, 'default threshold')
    near(texel.Alpha, 0, 'default layer')
    local full = sprite:GetTexel(Vector(3, 4), Vector(0.25, -0.125), 0.75, 6)
    near(full.Red, 0.55, 'sample/render x')
    near(full.Green, 0.275, 'sample/render y')
    near(full.Blue, 0.75, 'threshold')
    near(full.Alpha, 0.6, 'layer and alpha')
    print('TEXEL_NATIVE_OK')
  else
    if not tostring(texel):find('entry') then error('missing entry error must be clear') end
    print('TEXEL_MISSING_OK')
  end
  -- 参数**类型**不对仍必须报错（与其它成员同一口径）：阈值必须是数字、层号必须是整数。
  if pcall(function() return sprite:GetTexel(Vector(1, 2), Vector(0, 0), 'nope', 1) end) then
    error('GetTexel must reject a non-number alpha threshold')
  end
  if pcall(function() return sprite:GetTexel(Vector(1, 2), Vector(0, 0), 1, 1.5) end) then
    error('GetTexel must reject a non-integer layer id')
  end

  -- Render 的 clamp 参数有默认值（Vector.Zero），位置是 Vector 值类型
  sprite:Render(Vector(10, 20))
  sprite:RenderLayer(3, Vector(1, 2), Vector(-1, 0), Vector(5, 0))

  -- 参数类型不对必须报错，而不是把垃圾送进原生入口
  local bad = {
    function() return sprite:Play() end,
    function() return sprite:Play(1, true) end,
    function() return sprite:SetFrame() end,
    function() return sprite:SetFrame('Walk') end,
    function() return sprite:SetFrame(1, 2, 3) end,
    function() return sprite:Render() end,
    function() return sprite:Render(1, 2) end,
    function() return sprite:RenderLayer(1, Vector(0, 0), Vector(0, 0), Vector(0, 0), 5) end,
    function() return sprite:GetLayerFrame('x') end,
    function() return sprite:Update(1) end,
    function() return sprite:IsPlaying(1) end,
    function() return sprite:IsPlaying('Idle', 1) end,
    function() return sprite:IsFinished(1) end,
    function() return sprite:Load() end,
    function() return sprite:Load(1, true) end,
    function() return sprite:ReplaceSpritesheet(1) end,
    function() return sprite:LoadGraphics(1) end,
    -- 批次 214 的三条：都是零参数（PC 的 REPENTOGON 签名没有形参）
    function() return sprite:Reset(1) end,
    function() return sprite:GetLayerCount(1) end,
    function() return sprite:GetDefaultAnimationName(1) end,
  }
  for index, call in ipairs(bad) do
    if pcall(call) then error('expected an error from bad call #' .. index) end
  end

  -- 长路径（> 22 字节）会走 libc++ 的 `__long`：缓存（32 条）塞满后，最旧一条必须用
  -- **游戏自己的** operator delete 释放（本模块的 free 会踩坏堆）。
  for index = 1, 40 do
    sprite:Load('gfx/items/collectibles/probe_long_path_padding_' .. index .. '.anm2', true)
  end

  -- 显式回收：析构必须恰好一次（handle 幂等）
  sprite = nil
  collectgarbage('collect')
  collectgarbage('collect')
  end)
  if not ok then print('SPRITE_LUA_ERROR: ' .. tostring(err)) end
end)
'''


class LuaSpriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-sprite-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "lua_sprite_harness.cpp"
        harness.write_text(HARNESS.replace("@SCRIPT@", SCRIPT).lstrip())
        lua_root = SOURCE / "third_party/lua-5.3.3/src"
        excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
        lua_objects = []
        for lua_source in sorted(lua_root.glob("*.c")):
            if lua_source.name in excluded:
                continue
            output = temporary / f"{lua_source.stem}.o"
            build = subprocess.run(
                ["cc", "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root), "-c",
                 str(lua_source), "-o", str(output)], text=True, capture_output=True,
            )
            if build.returncode != 0:
                raise AssertionError(build.stdout + build.stderr)
            lua_objects.append(output)
        cls.harness = temporary / "lua_sprite_harness"
        build = subprocess.run(
            ["c++", "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
             "-DEXL_LAYERED_RUNTIME=1", "-DEXL_LOAD_KIND=Module",
             "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
             "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
             "-I", str(lua_root), str(harness),
             *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
             *map(str, lua_objects), "-o", str(cls.harness)],
            text=True, capture_output=True,
        )
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_sprite_step_one_marshals_arguments_and_owns_its_object(self):
        result = subprocess.run([str(self.harness)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("SPRITE_LUA_ERROR", result.stdout)
        self.assertIn("SPRITE_OK ctor=1 dtor=1 update=2", result.stdout)
        self.assertIn("TEXEL_NATIVE_OK", result.stdout)
        self.assertIn("released=", result.stdout)
        #: 批次 279：overlay 三条的实参必须原样到达原生入口。
        self.assertIn("SPRITE_OVERLAY overlay=Anim0/1 last=1 oframe=Walk/3 stop=1",
                      result.stdout)
        #: 批次 283：四条「按名字查询」。★ 数字的意思：
        #:   `overlay=3/3` —— `IsOverlayPlaying` / `IsOverlayFinished` 各被调到**三次**
        #:     （两个名字 + 一次省参数，对应 PC 的两个重载）；
        #:   `event=2/2`   —— `IsEventTriggered` / `WasEventTriggered` 各两次
        #:     （它们**没有**无参重载 ⇒ 两次都带名字）；
        #:   `empty=2`     —— 恰好两次把**空串**交到原生入口（就是那两个省参数的重载）；
        #:   `last=Nope`   —— 最后交下去的那条名字。
        self.assertIn("SPRITE_QUERY overlay=3/3 event=2/2 empty=2 last=Nope", result.stdout)
        #: 批次 283 顺带钉住"字符串桥按路径缓存"：常规 3 条 + 长路径 40 条 + 空串 1 条
        #: + 本批的 5 个新名字（Burst / Nope / Attack / Other / Hurt）= 49 次 `assign`。
        self.assertIn("SPRITE_ASSIGN calls=49", result.stdout)

    def test_missing_texel_entry_raises_instead_of_making_white_pixels(self):
        import os
        result = subprocess.run([str(self.harness)], text=True, capture_output=True,
                                env={**os.environ, "TEXEL_MISSING": "1"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("SPRITE_LUA_ERROR", result.stdout)
        self.assertIn("TEXEL_MISSING_OK", result.stdout)
        self.assertNotIn("TEXEL_NATIVE_OK", result.stdout)

    def test_sprite_object_size_and_alignment_come_from_the_stride_audit(self):
        constants = (SOURCE / "runtime_constants.hpp").read_text(encoding="utf-8")
        self.assertIn("inline constexpr std::size_t kSpriteObjectSize = 0x158;", constants)
        self.assertIn("inline constexpr std::size_t kSpriteObjectAlignment = 16;", constants)
        self.assertIn("inline constexpr std::size_t kSpriteLoadedFlagOffset = 0x149;", constants)
        # 每个入口都要有守卫，且守卫必须与镜像逐字节一致（由守卫核对工具覆盖）。
        # 批次 214 加 `Reset`（`ANM2::Reset @0x4A4724`，守卫 16 字节）。
        for name in ("Ctor", "Destructor", "Play", "SetAnimation", "SetFrameNamed", "SetFrame",
                     "GetFrame", "SetLayerFrame", "GetLayerFrame", "Update", "IsPlaying",
                     "IsFinished", "Reset", "Render", "RenderLayer", "PlayRandom",
                     #: 批次 279 / 280
                     "PlayOverlay", "SetLastFrame", "SetOverlayFrame", "Stop",
                     #: 批次 283（四条「按名字查询」）
                     "IsOverlayPlaying", "IsOverlayFinished", "IsEventTriggered",
                     "WasEventTriggered"):
            with self.subTest(entry=name):
                self.assertIn(f"kSprite{name}Offset", constants)
                self.assertIn(f"kSprite{name}ExpectedBytes", constants)


if __name__ == "__main__":
    unittest.main()
