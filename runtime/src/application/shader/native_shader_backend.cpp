#include "application/shader/native_shader_backend.hpp"
#include "application/shader/native_clear_probe.hpp"
#include "application/shader/shader_screen_hook.hpp"
#include "application/shader/native_shader_guards.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "relay/smart_pointer_shim.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
#include "interfaces/lua/runtime_perf.hpp"
#include <cstdlib>
#include <cstring>
namespace isaac::runtime {
// 只在游戏线程累加，供不暂停的内存采样读取。顺序：FrameInfo/Target/Clear/Standard/Draw/Flush/Drain。
__attribute__((visibility("hidden"))) std::uint64_t g_NativeShaderPerf[7][3]{};
namespace {
struct PerfScope {
 unsigned index;std::uint64_t start;
 explicit PerfScope(unsigned i):index(i),start(RuntimePerfTick()){}
 ~PerfScope(){const auto spent=RuntimePerfTick()-start;auto* row=g_NativeShaderPerf[index];++row[0];row[1]+=spent;if(spent>row[2])row[2]=spent;}
};
using namespace shader_native;
std::uintptr_t g_VerifiedBase{};
struct NativeProgram {void* shader;};
struct NativeBlend {std::uint64_t fields[2];};
// KAGE Color的复制构造为非平凡：CreateProceduralImage的颜色实参通过指针寄存器传递，不能按HFA传s0..s3。
struct NativeColor {
 float fields[4];
 NativeColor() noexcept:fields{0,0,0,0}{}
 NativeColor(const NativeColor& other) noexcept {std::memcpy(fields,other.fields,sizeof(fields));}
};
static_assert(sizeof(NativeBlend)==16&&sizeof(NativeColor)==16);
bool Read(std::uintptr_t address,void* out,std::size_t bytes) {
 if(!engine_memory::EngineMemoryReadable(address,bytes))return false;
 std::memcpy(out,engine_memory::AsObject(address),bytes);return true;
}
template<class T> bool At(std::uintptr_t address,T* out){return Read(address,out,sizeof(T));}
bool Verified() {
 const auto base=LuaRuntime::EngineModuleBase();if(!base)return false;if(base==g_VerifiedBase)return true;
 for(const auto* entry : {&kCtor,&kDtor,&kInitialize,&kTarget,&kGetTarget,&kClear,&kCreateImage,&kReleaseImage,
     &kRender,&kBlend,&kWidth,&kHeight,&kPaddedWidth,&kPaddedHeight,&kFlush,&kSync,
     &kBufferVerify,&kBufferSwap,&kFlushPending}) {
  if(base>UINTPTR_MAX-entry->offset||!engine_call::VerifyEntryBytes(base+entry->offset,entry->bytes.data(),entry->bytes.size(),engine_memory::EngineMemoryReadable))return false;
 }
 g_VerifiedBase=base;return true;
}
template<class Fn>Fn Method(const Entry& entry){return engine_call::AsFunction<Fn>(g_VerifiedBase+entry.offset);}
void* Graphics(){std::uintptr_t pointer{};return At(g_VerifiedBase+0xAAC6E8,&pointer)?engine_memory::AsObject(pointer):nullptr;}
void* Images(){std::uintptr_t pointer{};return At(g_VerifiedBase+0xAAC758,&pointer)?engine_memory::AsObject(pointer):nullptr;}
void Drain() {
 PerfScope perf(6);
 if(!Verified()){return;}
 auto* graphics=Graphics();if(!graphics){return;}
 // 4F2D28..3C（Shutdown）及4F3B94..A0（end_scene）使用同一内嵌Queue，装载/释放时才等待，帧上不加Sync。
 auto* queue=engine_memory::AsObject(engine_memory::AddressOf(graphics)+0x3A38);
 Method<void(*)(void*)>(kFlush)(queue);Method<void(*)(void*)>(kSync)(queue);
}
bool Compile(const ShaderProgramView& view,void** out) {
 if(!out||!Verified()||!InstallShaderScreenHook(g_VerifiedBase)){return false;}
 *out=nullptr;
 auto* block=static_cast<unsigned char*>(std::malloc(sizeof(NativeProgram)+0x260+15));if(!block)return false;
 auto* program=reinterpret_cast<NativeProgram*>(block);
 program->shader=engine_memory::AsObject((engine_memory::AddressOf(block+sizeof(NativeProgram))+15)&~std::uintptr_t(15));
 Method<void(*)(void*)>(kCtor)(program->shader);
 struct InitData {const char* vertex;const char* fragment;};const InitData data{view.vertex,view.fragment};
 const bool success=Method<bool(*)(void*,const ShaderAttribute*,const InitData*)>(kInitialize)(program->shader,view.attributes,&data);
 if(!success){Method<void(*)(void*)>(kDtor)(program->shader);std::free(block);return false;}
 *out=program;return true;
}
void Destroy(void* raw){if(!raw)return;auto* program=static_cast<NativeProgram*>(raw);if(Verified())Method<void(*)(void*)>(kDtor)(program->shader);std::free(raw);}
bool GlobalUnsigned(std::uintptr_t slot,std::uint32_t* value){std::uintptr_t p{};return At(g_VerifiedBase+slot,&p)&&p&&At(p,value);}
bool GlobalFloat(std::uintptr_t slot,float* value){std::uintptr_t p{};return At(g_VerifiedBase+slot,&p)&&p&&At(p,value);}
bool FrameInfo(ShaderFrameInfo* out) {
 PerfScope perf(0);
 if(!out||!Verified()){return false;}
 static_cast<void>(InstallNativeClearProbe(g_VerifiedBase));
 auto* graphics=Graphics();if(!graphics){return false;}
 out->previous={};Method<void(*)(void*,void**,bool*)>(kGetTarget)(graphics,&out->previous.image,&out->previousFlag);
 if(out->previous.image){
  std::uintptr_t table{},width{},height{};if(!At(engine_memory::AddressOf(out->previous.image),&table)||!At(table+0x50,&width)||!At(table+0x58,&height))return false;
  out->width=engine_call::AsFunction<unsigned(*)(void*)>(width)(out->previous.image);
  out->height=engine_call::AsFunction<unsigned(*)(void*)>(height)(out->previous.image);
 }else if(!GlobalUnsigned(0xAAC7D0,&out->width)||!GlobalUnsigned(0xAAC7D8,&out->height))return false;
 // 与Shader::bind的正交投影读取同源，每帧一次，所有pass共用快照。
 return out->width&&out->height&&GlobalFloat(kIsaacPointScaleSlotOffset,&out->scale)&&out->scale>0&&
  GlobalFloat(0xAAC7C0,&out->projectionWidth)&&out->projectionWidth>0&&
  GlobalFloat(0xAAC7C8,&out->projectionHeight)&&out->projectionHeight>0;
}
bool Create(unsigned width,unsigned height,const char* name,ShaderTarget* out) {
 if(!out||!Verified()||!Images())return false;
 using CreateFn=relay::SmartPointerShim(*)(void*,unsigned,unsigned,const char*,unsigned,unsigned,NativeColor);
 // 与Game::CreateSurfaces@34C0BC..C4一致：flags0、RGBA格式2、透明色，非平凡返回使用x8 sret。
 const auto image=Method<CreateFn>(kCreateImage)(Images(),width,height,name,0,2,NativeColor{});
 *out={image.pointer,image.control};return out->image&&out->control;
}
void Release(ShaderTarget* target) {
 if(!target)return;
 if(target->control&&Verified())Method<bool(*)(void*)>(kReleaseImage)(target->control);
 *target={};
}
void Target(const ShaderTarget& target,bool flag){PerfScope perf(1);Method<void(*)(void*,void*,bool)>(kTarget)(Graphics(),target.image,flag);}
void Clear(){
 PerfScope perf(2);auto* graphics=Graphics();void* target{};
 // graphics是原Clear同一对象；只读当前目标，不改变参数或渲染顺序。
 if(graphics)std::memcpy(&target,static_cast<unsigned char*>(graphics)+0x20,sizeof(target));
 NativeClearProbeScope detail(target!=nullptr);Method<void(*)(void*)>(kClear)(graphics);
}
bool Standard(const ShaderTarget& source,const ShaderFrameInfo& frame,float* data,std::size_t stride) {
 PerfScope perf(3);
 if(!source.image||!data||stride<14||!(frame.scale>0)||
    !(frame.projectionWidth>0)||!(frame.projectionHeight>0))return false;
 const unsigned w=Method<unsigned(*)(void*)>(kWidth)(source.image),h=Method<unsigned(*)(void*)>(kHeight)(source.image);
 const unsigned pw=Method<unsigned(*)(void*)>(kPaddedWidth)(source.image),ph=Method<unsigned(*)(void*)>(kPaddedHeight)(source.image);
 if(!w||!h||!pw||!ph)return false;
 // PC871FF0..8720BD填入四种尺寸和POINTSCALE，XML参数从float14起；UV按图像实际/填充尺寸。
 const float u=static_cast<float>(w)/pw,v=static_cast<float>(h)/ph;
 // 目标以逻辑点投影；像素尺寸仍留在RenderData。原生反向深度清零后用GREATER，z=0会整屏被拒绝。
 const float width=frame.projectionWidth,height=frame.projectionHeight;
 const float xs[4]={0,width,width,0};
 const float ys[4]={0,0,height,height};
 const float us[4]={0,u,u,0},vs[4]={0,0,v,v};
 for(unsigned i=0;i<4;++i){auto* vertex=data+i*stride;vertex[0]=xs[i];vertex[1]=ys[i];vertex[2]=-1;
  for(unsigned j=3;j<7;++j){vertex[j]=1;}
  vertex[7]=us[i];vertex[8]=vs[i];
  vertex[9]=static_cast<float>(w);vertex[10]=static_cast<float>(h);vertex[11]=static_cast<float>(pw);vertex[12]=static_cast<float>(ph);vertex[13]=frame.scale;}
 return true;
}
void Draw(const ShaderTarget& source,void* raw,const float* vertices,unsigned count,unsigned stride) {
 PerfScope perf(4);
 // Clear已在原生begin_scene中同步前一次目标。两个私有图像的上传缓冲复用容量，不累计帧offset。
 const auto image=engine_memory::AddressOf(source.image);
 for(const auto offset : {0x438u,0x4A8u})Method<void(*)(void*)>(kBufferSwap)(engine_memory::AsObject(image+offset));
 Method<void(*)(void*,std::size_t)>(kBufferVerify)(engine_memory::AsObject(image+0x438),std::size_t(count)*stride);
 Method<void(*)(void*,std::size_t)>(kBufferVerify)(engine_memory::AsObject(image+0x4A8),6*sizeof(unsigned short));
 NativeBlend blend{};Method<void(*)(NativeBlend*,int)>(kBlend)(&blend,0); // 原生Opaque=ONE/ZERO，完整16B经x1/x2传递。
 // 原生开启背面剔除；屏幕坐标下的正面面积为负，必须与ImageBase原生四边形同向。
 const unsigned short indices[]={0,2,1,2,0,3};auto* program=static_cast<NativeProgram*>(raw);
 using DrawFn=void(*)(void*,NativeBlend,void*,const void*,int,unsigned,const unsigned short*,int);
 Method<DrawFn>(kRender)(source.image,blend,program->shader,vertices,static_cast<int>(count),stride,indices,6);
}
void FlushPending(){PerfScope perf(5);Method<void(*)(void*)>(kFlushPending)(Graphics());}
constexpr ShaderBackend kBackend{Compile,Destroy,FrameInfo,Create,Release,Target,Clear,Standard,Draw,Drain,FlushPending};
}
const ShaderBackend& NativeShaderBackend() noexcept{return kBackend;}
}
