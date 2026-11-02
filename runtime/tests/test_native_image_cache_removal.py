"""Exercise the native smart-pointer compaction failure and safe ownership transfer."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#if __has_include("native_image_cache_removal.hpp")
#include "native_image_cache_removal.hpp"
#define HAS_FIX 1
#else
namespace isaac::runtime {
struct ImageCacheEntry { void* image; void* control; };
struct ImageCacheBucket { ImageCacheEntry* begin; ImageCacheEntry* end; ImageCacheEntry* capacity; };
}
#endif
using namespace isaac::runtime;
struct Image { unsigned refs=1; bool alive=true; unsigned destroyed=0; };
ImageCacheEntry storage[8]{};
ImageCacheBucket bucket{storage,storage,storage+8};
unsigned depth=0,maxDepth=0,originals=0;
void remove(Image*);
void release(ImageCacheEntry pair) {
 auto* p=static_cast<Image*>(pair.control);if(!p)return;
 assert(p->alive && p->refs);
 if(!--p->refs){p->alive=false;++p->destroyed;}
 else if(p->refs==1)remove(p);
}
// Native 4D351C..4D35D0 increments the next entry then decrements the old
// entry, notifying at refcount one before publishing the shorter vector.
void original(Image* p) {
 assert(!p || p->alive);++originals;
 auto* found=std::find_if(bucket.begin,bucket.end,[&](auto& e){return e.image==p;});
 if(found==bucket.end)return;
 for(auto* at=found;at+1<bucket.end;++at){
  auto next=at[1];++static_cast<Image*>(next.control)->refs;
  auto old=*at;*at=next;release(old);
 }
 release(bucket.end[-1]);--bucket.end;
}
void remove(Image* p) {
 ++depth;maxDepth=std::max(maxDepth,depth);
 if(depth>16)std::exit(72);
#ifdef HAS_FIX
 DetachImageCacheEntry(bucket,p,[&]{original(p);},release);
#else
 original(p);
#endif
 --depth;
}
int main() {
 // Cache-only images following an erased image must not notify during moves.
 Image a,b,c;storage[0]={&a,&a};storage[1]={&b,&b};storage[2]={&c,&c};bucket.end=storage+3;
 remove(&a);assert(!a.alive && a.destroyed==1 && b.refs==1 && c.refs==1);
 assert(bucket.end==storage+2 && storage[0].image==&b && storage[1].image==&c);
 remove(&c);remove(&b);assert(bucket.end==storage && b.destroyed==1 && c.destroyed==1);
 // Remaining external owners keep their image live after cache removal.
 Image external;external.refs=2;storage[0]={&external,&external};bucket.end=storage+1;
 remove(&external);assert(external.alive && external.refs==1 && bucket.end==storage);
 release({&external,&external});assert(external.destroyed==1);
 // Null/missing entries retain native cleanup and do not release other owners.
 const auto before=originals;remove(static_cast<Image*>(nullptr));assert(originals==before+1);
 Image missing;remove(&missing);assert(missing.refs==1 && missing.alive);
 assert(maxDepth<=2);
}
'''

class NativeImageCacheRemovalTests(unittest.TestCase):
    def test_compaction_publishes_consistent_cache_before_notifications(self):
        with tempfile.TemporaryDirectory(prefix='image-cache-remove-') as tmp:
            p=Path(tmp);(p/'check.cpp').write_text(HARNESS)
            result=subprocess.run(['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror',
                '-I'+str(ROOT/'runtime/source'),str(p/'check.cpp'),'-o',str(p/'check')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(p/'check')],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,'native removal recursed before publishing the cache: '+result.stdout+result.stderr)

    def test_native_intercept_guards_lock_and_real_notification_calls(self):
        nro=os.environ.get('ISAAC_TEST_NRO')
        if not nro:self.skipTest('original NRO fixture not configured')
        stubs={
            'module_finder.hpp':'''#pragma once
#include <array>
#include <cstdint>
#include <cstddef>
struct TargetModule {std::uintptr_t base;std::size_t size;std::array<unsigned char,32> buildId;
bool Contains(std::uintptr_t p,std::size_t n)const{return p>=base && p-base<=size && n<=size-(p-base);}};
''',
            'runtime_constants.hpp':'#pragma once\n#include <array>\ninline constexpr std::array<unsigned char,32> kTargetBuildId{};\n',
            'relay/entry_relay.hpp':'''#pragma once
#include <cstdint>
namespace isaac::runtime::relay {using EntryRelayOriginalPublisher=bool(*)(std::uintptr_t,void*)noexcept;
bool TryInstallEntryRelayWithPublisher(std::uintptr_t,const void*,std::uintptr_t,EntryRelayOriginalPublisher,void*,std::uintptr_t* =nullptr);}
''',
            'infrastructure/memory/engine_field_access.hpp':'''#pragma once
#include <cstdint>
#include <cstring>
namespace isaac::runtime::engine_memory {
inline bool EngineMemoryReadable(std::uintptr_t a,std::size_t){return a!=0;}
inline bool EngineMemoryWritable(std::uintptr_t a,std::size_t){return a!=0;}
inline void* AsObject(std::uintptr_t a){return reinterpret_cast<void*>(a);}
inline std::uintptr_t AddressOf(const void* p){return reinterpret_cast<std::uintptr_t>(p);}
template<class T>bool ReadAt(std::uintptr_t a,T*p,bool(*check)(std::uintptr_t,std::size_t)){if(!check(a,sizeof(T)))return false;std::memcpy(p,reinterpret_cast<void*>(a),sizeof(T));return true;}}
''',
            'infrastructure/call/engine_call_access.hpp':'''#pragma once
#include "infrastructure/memory/engine_field_access.hpp"
std::uintptr_t Resolve(std::uintptr_t);
namespace isaac::runtime::engine_call {
template<class F>F AsFunction(std::uintptr_t a){return reinterpret_cast<F>(Resolve(a));}
template<class F>std::uintptr_t AddressOfFunction(F f){return reinterpret_cast<std::uintptr_t>(f);}
inline bool VerifyEntryBytes(std::uintptr_t a,const void*p,std::size_t n,bool(*r)(std::uintptr_t,std::size_t)){return r(a,n)&&!std::memcmp(reinterpret_cast<void*>(a),p,n);}}
'''}
        native=r'''
#define __SWITCH__ 1
#include <vector>
#include <fstream>
#include <iterator>
#include <cassert>
#include "native_image_cache_removal.cpp"
using namespace isaac::runtime;
struct Image {std::uintptr_t* vtable;unsigned refs=1,destroyed=0;bool alive=true;};
std::vector<unsigned char> module;ImageCacheEntry entries[8]{};
ImageCacheBucket bucket{entries,entries,entries+8};
struct Manager {ImageCacheBucket* buckets;std::uint64_t lock;} manager{&bucket,0};
unsigned locks=0,unlocks=0,originals=0,published=0,depth=0,maxdepth=0,lockDepth=0;
std::uintptr_t base(){return reinterpret_cast<std::uintptr_t>(module.data());}
void lock(void*,unsigned){++locks;++lockDepth;}
void unlock(void*){++unlocks;assert(lockDepth);--lockDepth;}
const char* path(void*){return "fixture";}
unsigned hash(const char*,bool){return 0;}
bool decrement(void* p){auto& i=*static_cast<Image*>(p);assert(i.alive&&i.refs);if(!--i.refs){i.alive=false;++i.destroyed;return false;}return true;}
void notify(ImageCacheEntry* p){if(static_cast<Image*>(p->control)->refs==1)IsaacModRuntime_RemoveImageCacheEntry(&manager,p->image);}
void original(void*,void* p){
 assert(lockDepth);assert(!p||static_cast<Image*>(p)->alive);++originals;
 for(auto* e=bucket.begin;e!=bucket.end;++e)assert(e->image!=p);
 ++depth;maxdepth=std::max(maxdepth,depth);assert(depth<=2);--depth;
}
std::uintptr_t Resolve(std::uintptr_t a){
 switch(a-base()) {
 case 0x670580:return reinterpret_cast<std::uintptr_t>(lock);
 case 0x670590:return reinterpret_cast<std::uintptr_t>(unlock);
 case 0x670550:return reinterpret_cast<std::uintptr_t>(path);
 case 0x680450:return reinterpret_cast<std::uintptr_t>(hash);
 default:return a;
 }}
namespace isaac::runtime::relay {
bool TryInstallEntryRelayWithPublisher(std::uintptr_t target,const void*,std::uintptr_t,EntryRelayOriginalPublisher publisher,void*ctx,std::uintptr_t*){
 assert(target==base()+0x4d32f8);++published;return publisher(reinterpret_cast<std::uintptr_t>(original),ctx);
}}
int main(int argc,char**argv){
 assert(argc==2);std::ifstream f(argv[1],std::ios::binary);module={std::istreambuf_iterator<char>(f),{}};module.resize(0xb00000);
 unsigned count=1;std::uintptr_t callback=reinterpret_cast<std::uintptr_t>(notify);
 auto countp=reinterpret_cast<std::uintptr_t>(&count),notifyp=reinterpret_cast<std::uintptr_t>(&callback);
 std::memcpy(module.data()+0xaad518,&countp,8);std::memcpy(module.data()+0xaac6a8,&notifyp,8);
 TargetModule target{base(),module.size(),kTargetBuildId};
 module[0x4d3550]^=1;assert(!InstallNativeImageCacheRemovalFix(target)&&published==0);module[0x4d3550]^=1;
 assert(InstallNativeImageCacheRemovalFix(target)&&NativeImageCacheRemovalFixReady()&&published==1);
 assert(InstallNativeImageCacheRemovalFix(target)&&published==1);
 std::uintptr_t vtable[5]{};vtable[4]=reinterpret_cast<std::uintptr_t>(decrement);
 Image a{vtable},b{vtable},c{vtable};entries[0]={&a,&a};entries[1]={&b,&b};entries[2]={&c,&c};bucket.end=entries+3;
 IsaacModRuntime_RemoveImageCacheEntry(&manager,&a);
 assert(a.destroyed==1&&b.refs==1&&c.refs==1&&bucket.end==entries+2);
 IsaacModRuntime_RemoveImageCacheEntry(&manager,&b);IsaacModRuntime_RemoveImageCacheEntry(&manager,&c);
 Image shared{vtable};shared.refs=2;entries[0]={&shared,&shared};bucket.end=entries+1;
 IsaacModRuntime_RemoveImageCacheEntry(&manager,&shared);
 assert(shared.refs==1&&shared.alive&&bucket.end==entries);
 assert(locks==unlocks&&lockDepth==0&&originals==5&&g_ImageCacheRemovalState[2]==4&&g_ImageCacheRemovalState[3]==0);
}
'''
        with tempfile.TemporaryDirectory(prefix='native-image-intercept-') as tmp:
            p=Path(tmp)
            for name,text in stubs.items():
                file=p/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(text)
            (p/'native_image_cache_removal.cpp').write_text((ROOT/'runtime/source/native_image_cache_removal.cpp').read_text())
            (p/'check.cpp').write_text(native)
            result=subprocess.run(['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I'+str(p),
                '-I'+str(ROOT/'runtime/source'),str(p/'check.cpp'),'-o',str(p/'check')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(p/'check'),nro],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
