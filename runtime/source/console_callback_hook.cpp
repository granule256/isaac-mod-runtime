#include "console_callback_hook.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include <cstring>
namespace isaac::runtime {
bool ReadConsoleToken(const ConsoleCommandView& view,std::size_t index,const char** text,std::size_t* length) noexcept {
    if(index>=view.count || index>UINTPTR_MAX/24)return false;
    const auto base=engine_memory::AddressOf(view.tokens);
    if(!base || base>UINTPTR_MAX-index*24-24)return false;
    const auto address=base+index*24;
    unsigned char header[24];
    if(!engine_memory::EngineMemoryReadable(address,24))return false;
    std::memcpy(header,engine_memory::AsObject(address),24);
    if(header[0]&1){std::memcpy(length,header+8,8);std::memcpy(text,header+16,8);}
    else{*length=header[0]>>1;if(*length>22)return false;*text=static_cast<const char*>(engine_memory::AsObject(address+1));}
    const auto pointer=engine_memory::AddressOf(*text);
    return pointer && *length<SIZE_MAX && pointer<=UINTPTR_MAX-*length-1 && engine_memory::EngineMemoryReadable(pointer,*length+1);
}
std::uint32_t ConsoleUnknownInternalCallback(relay::InternalHookContext& context,const void* bindings) noexcept {
    const auto& native=*static_cast<const ConsoleUnknownBindings*>(bindings);
    const bool unknown=native.compareResult ? static_cast<std::uint32_t>(context.x[0])!=0 : (context.nzcv&(1ULL<<30))==0;
    if(!unknown)return 1; // 原长度/比较条件不成立：继续copy内建命令原分支。
    const auto frame=context.x[29];
    std::uintptr_t begin{},end{};
    if(frame>=0x30 && engine_memory::ReadAt(frame-0x30,&begin,engine_memory::EngineMemoryReadable) &&
       engine_memory::ReadAt(frame-0x28,&end,engine_memory::EngineMemoryReadable) && end>=begin && (end-begin)%24==0) {
        ConsoleCommandView view{engine_memory::AsObject(begin),static_cast<std::size_t>((end-begin)/24),engine_memory::AsObject(context.x[28]),native.print};
        if(view.count)LuaRuntime::DispatchExecuteCommand(view);
    }
    return 0; // 原未知命令清理入口，保留vector析构和输出指针清理。
}
}
