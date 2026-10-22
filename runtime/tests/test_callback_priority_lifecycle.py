"""登记时的PC number顺序、删除生命周期及量具布局。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include <array>
#include <cstddef>
#include <limits>
#define private public
#include "application/callback/callback_registry.hpp"
#undef private
#include "application/callback/callback_dispatcher.hpp"
#include <cstdio>
using namespace isaac::runtime;
static_assert(sizeof(CallbackDescriptor) == 20);
static_assert(sizeof(CallbackRegistry) == 0x2d08);
static_assert(offsetof(CallbackRegistry, count_) == 0x2d00);
static CallbackDescriptor Entry(CallbackId id, int ref, unsigned owner=1) {
    CallbackDescriptor d{};d.id=id;d.luaReference=ref;d.modReference=ref;
    d.owner={static_cast<std::uint16_t>(owner),1};d.affinity=ThreadAffinity::Any;return d;
}
static bool Order(const CallbackRegistry& r, CallbackId id, const char* expected) {
    std::size_t found=0;
    for(std::size_t p=0;p<r.Count();++p) {
        auto* d=r.AtIndex(r.DispatchIndexAt(p));
        if(!d || d->id!=id)continue;
        if(!expected[found] || d->luaReference!=expected[found++])return false;
    }
    return !expected[found];
}
struct Invoker : ICallbackInvoker {
    char seen[257]{};std::size_t count{};
    Status Invoke(const CallbackDescriptor&) noexcept override {return Status::Ok();}
    Status InvokeCollecting(const CallbackDescriptor& d, CallbackReturn* r) noexcept override {
        seen[count++]=static_cast<char>(d.luaReference);r->called=true;return Status::Ok();
    }
};
int main() {
    CallbackRegistry r;
    const double nan=std::numeric_limits<double>::quiet_NaN();
    const auto add=[&](CallbackId id,int ref,CallbackPriorityValue p,unsigned owner=1,std::int64_t filter=CallbackRegistry::kNoCallbackFilter) {
        return r.Register(Entry(id,ref,owner),filter,p).ok();
    };
    if(!add(20,'A',0,1,8)||!add(21,'X',nan)||!add(20,'B',1,2,7)||
       !add(21,'Y',-1)||!add(20,'C',nan,2,7)||!add(20,'D',0,2,7))return 1;
    if(!Order(r,20,"CADB")||!Order(r,21,"YX"))return 2;
    // 原登记坐标保持：At/AtIndex与FilterAt/PriorityAt仍按追加位置。
    if(r.At(20,0)->luaReference!='A'||r.AtIndex(2)->luaReference!='B'||
       r.FilterAt(2)!=7||r.PriorityAt(2)!=1)return 3;
    Invoker invoker;CallbackDispatcher dispatcher{r,invoker};
    const auto filtered=dispatcher.DispatchFiltered(20,ThreadAffinity::Any,7);
    if(filtered.invoked!=3||invoker.seen[0]!='C'||invoker.seen[1]!='D'||invoker.seen[2]!='B')return 4;
    if(r.Remove(20,{1,1})!=1||!Order(r,20,"CDB")||!Order(r,21,"YX"))return 5;
    if(r.RemoveOwner({2,1})!=3||!Order(r,20,"")||!Order(r,21,"YX")||r.Count()!=2)return 6;
    if(!add(20,'E',-0.25)||!add(20,'F',-0.25)||!Order(r,20,"EF"))return 7;
    if(r.RemoveAtIndex(99)!=0||!Order(r,20,"EF"))return 8;
    r.Reset();
    constexpr auto maximum=std::numeric_limits<std::int64_t>::max();
    constexpr auto minimum=std::numeric_limits<std::int64_t>::min();
    if(!add(20,'A',maximum)||!add(20,'B',maximum-1,2)||
       !add(20,'C',minimum+1)||!add(20,'D',minimum,2)||!Order(r,20,"DCBA"))return 13;
    if(!r.PriorityAt(0).isInteger||r.PriorityAt(0).integer!=maximum)return 14;
    if(r.RemoveOwner({2,1})!=2||!Order(r,20,"CA"))return 15;
    r.Reset();
    if(r.Count()!=0||!add(20,'A',nan)||!add(20,'B',0)||!Order(r,20,"BA"))return 9;
    r.Reset();
    for(std::size_t i=0;i<CallbackRegistry::kCapacity;++i) {
        if(!add(20,static_cast<int>(i+1),-static_cast<double>(i)))return 10;
    }
    if(add(20,999,0)||r.DispatchIndexAt(0)!=255||r.DispatchIndexAt(255)!=0)return 11;
    if(r.RemoveAtIndex(128)!=1||r.DispatchIndexAt(0)!=254||r.Count()!=255)return 12;
    std::printf("descriptor=20 registry=0x%zx count=0x%zx lifecycle=ok\n",sizeof(r),offsetof(CallbackRegistry,count_));
    return 0;
}
'''


class CallbackPriorityLifecycleTests(unittest.TestCase):
    def test_persistent_order_lifecycle_and_layout(self):
        with tempfile.TemporaryDirectory(prefix='isaac-priority-life-') as directory:
            directory = Path(directory)
            source = directory / 'priority.cpp'
            source.write_text(HARNESS)
            binary = directory / 'priority'
            command = ['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                       '-I', str(ROOT / 'runtime/src'), str(source),
                       str(ROOT / 'runtime/src/application/callback/callback_registry.cpp'),
                       str(ROOT / 'runtime/src/application/callback/callback_dispatcher.cpp'),
                       '-o', str(binary)]
            build = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())


if __name__ == '__main__':
    unittest.main()
