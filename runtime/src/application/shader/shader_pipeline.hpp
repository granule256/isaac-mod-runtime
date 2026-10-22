#pragma once
#include <cstddef>
#include <cstdint>
#include <string_view>
namespace isaac::runtime {
struct ShaderAttribute {const char* name;std::uint32_t format;std::uint32_t padding;};
static_assert(sizeof(ShaderAttribute)==16);
struct ShaderParameter {const char* name;std::uint32_t components;std::uint32_t offset;};
struct ShaderProgramView {
 const char* owner;const char* name;const char* vertex;const char* fragment;
 const ShaderAttribute* attributes;const ShaderParameter* parameters;
 std::size_t attributeCount;std::size_t parameterCount;std::size_t strideFloats;
};
struct ShaderTarget {void* image;void* control;};
struct ShaderFrameInfo {
 ShaderTarget previous;std::uint32_t width,height;float scale;bool previousFlag;
 // 原生投影可以取整，不能用窗口像素/Scale重新推算。
 float projectionWidth{},projectionHeight{};
};
// 函数表只需常量初始化；不在-nostartfiles模块里创建有全局构造的虚拟对象。
struct ShaderBackend {
 bool (*compile)(const ShaderProgramView&,void**);
 void (*destroy)(void*);
 bool (*frameInfo)(ShaderFrameInfo*);
 bool (*createTarget)(unsigned,unsigned,const char*,ShaderTarget*);
 void (*releaseTarget)(ShaderTarget*);
 void (*target)(const ShaderTarget&,bool);
 void (*clear)();
 bool (*standardVertices)(const ShaderTarget&,const ShaderFrameInfo&,float*,std::size_t);
 void (*draw)(const ShaderTarget&,void*,const float*,unsigned,unsigned);
 void (*drain)();
 void (*flushPending)(){};
};
using ShaderValueProvider=bool (*)(const ShaderProgramView&,float*,std::uintptr_t);
enum class ShaderPipelineError : unsigned {None,Xml,Type,OutOfMemory,NativeCompile,Busy,Target,Values};
struct ShaderPipelineStats {std::size_t programs,bytes;std::uint64_t frames,passes,valueFailures;ShaderPipelineError error;};
bool LoadShaderXml(std::string_view owner,std::string_view xml,const ShaderBackend&) noexcept;
void UnloadShaderPrograms() noexcept;
void SetShaderValueProvider(ShaderValueProvider) noexcept;
bool BeginShaderFrame() noexcept;
// 原版真正选择屏幕后接管该目标；后续Push/Pop自然保存并恢复捕获图。
bool CaptureShaderScreenTarget() noexcept;
void FinishShaderFrame(std::uintptr_t manager) noexcept;
void AbortShaderFrame() noexcept;
ShaderPipelineStats ShaderPipelineStatsSnapshot() noexcept;
}
