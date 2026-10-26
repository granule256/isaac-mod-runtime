"""原生EHandle模型：ClearReferences提前清弱指针，独立于D2 lifetime token。"""
SUPPORT=r'''
#include <map>
#include <set>
namespace isaac::runtime {
__attribute__((weak)) void SetApi600EntityPtrNativeTestBindings(std::uintptr_t,std::uintptr_t) noexcept {}
}
static std::map<std::uintptr_t,std::set<std::uintptr_t*>> weakRefs;
static void SetWeak(void* raw,void* entity){auto*slot=static_cast<std::uintptr_t*>(raw);if(*slot){auto it=weakRefs.find(*slot);if(it!=weakRefs.end()){it->second.erase(slot);if(it->second.empty())weakRefs.erase(it);}}*slot=reinterpret_cast<std::uintptr_t>(entity);if(*slot)weakRefs[*slot].insert(slot);}
static void DestroyWeak(void* raw){SetWeak(raw,nullptr);}
static void ClearNativeWeak(std::uintptr_t entity){auto it=weakRefs.find(entity);if(it!=weakRefs.end()){for(auto*slot:it->second)*slot=0;weakRefs.erase(it);}}
static void ClearAllNativeWeak(){for(auto&entry:weakRefs)for(auto*slot:entry.second)*slot=0;weakRefs.clear();}
static std::size_t NativeWeakCount(std::uintptr_t entity){auto it=weakRefs.find(entity);return it==weakRefs.end()?0:it->second.size();}
static void InstallWeakBindings(){
 const unsigned char set[]={0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
 const unsigned char destroy[]={0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0x08,0x00,0x40,0xf9};
 std::memcpy(g_ModuleBytes.data()+0x677c0,set,16);std::memcpy(g_ModuleBytes.data()+0x4b1f1c,destroy,16);
 isaac::runtime::SetApi600EntityPtrNativeTestBindings(reinterpret_cast<std::uintptr_t>(&SetWeak),reinterpret_cast<std::uintptr_t>(&DestroyWeak));
 static_cast<void>(&ClearNativeWeak);static_cast<void>(&NativeWeakCount);
}
'''
def with_native_weak(main):
    main=main.replace('int main(){',SUPPORT+'\nint main(){',1)
    main=main.replace('const char*script=R"lua(', 'InstallWeakBindings();\nconst char*script=R"lua(',1)
    main=main.replace('RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));','ClearNativeWeak(AddressOf(g_Entities[kPlayer]));\nRetireEntityLifetime(AddressOf(g_Entities[kPlayer]));')
    main=main.replace('std::vector<unsigned char>other=g_ModuleBytes;', 'ClearAllNativeWeak();\nstd::vector<unsigned char>other=g_ModuleBytes;')
    return main
