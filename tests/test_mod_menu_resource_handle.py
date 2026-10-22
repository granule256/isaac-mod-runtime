"""编译生产统计函数的 ARM 分支，模拟内核有限句柄表验证所有权。"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ResourceHandleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / 'runtime/source/mod_menu_native.cpp').read_text()
        function = source.split('void NoteHeapUsagePeriodically() noexcept {', 1)[1]
        function = 'void NoteHeapUsagePeriodically() noexcept {' + function.split('\n}\n', 1)[0] + '\n}\n'
        fields = sorted(set(re.findall(r'g_ModMenuState\.(\w+)', function)))
        enums = sorted(set(re.findall(r'\b(?:InfoType_|MemType_)\w+', function)))
        prefix = r'''
#include <cstdint>
#include <cstdio>
#include <set>
#include <string>
using u64 = std::uint64_t; using u32 = std::uint32_t; using Handle = u32;
#define __aarch64__ 1
#define R_SUCCEEDED(x) ((x) == 0)
#define R_FAILED(x) ((x) != 0)
constexpr Handle INVALID_HANDLE=0, CUR_PROCESS_HANDLE=0xffff8001;
constexpr u32 LimitableResource_Memory=0, MemState_Type=0xff;
struct mallinfo { int arena=100, fordblks=40, uordblks=60, ordblks=1, hblks=0, keepcost=0; };
struct mallinfo mallinfo() { return {}; }
namespace isaac::runtime::bridge { u32 ImagePcxCacheUsedBytes() { return 123; } }
namespace LuaRuntime { u32 LuaStateMemoryBytes() { return 456; } }
struct MemoryInfo { u64 addr=0, size=0; u32 type=0; };
int svcQueryMemory(MemoryInfo*, u32*, u64) { return 1; }
std::set<Handle> handles;
int acquired=0, closed=0, getCalls=0, invalidClose=0, limitCalls=0, currentCalls=0;
bool failGet=false, zeroHandle=false, failLimit=false, failCurrent=false;
u64 limit=1000, current=100;
'''
        prefix += '\nenum { ' + ', '.join(enums) + ' };\n'
        prefix += 'struct State { ' + ''.join('u32 ' + f + '=0;' for f in fields) + ' } g_ModMenuState;\n'
        prefix += r'''
int svcGetInfo(u64* out, u32 type, Handle handle, u64) {
    if (type != InfoType_ResourceLimit) { *out=200; return 0; }
    ++getCalls;
    if (handle != INVALID_HANDLE) return 1;
    if (failGet) { *out=99; return 1; }
    if (zeroHandle) { *out=0; return 0; }
    if (handles.size() >= 8) return 0xD201;
    Handle h=1; while (handles.count(h)) ++h;
    handles.insert(h); *out=h; ++acquired; return 0;
}
int svcGetResourceLimitLimitValue(u64* out, Handle h, u32) {
    ++limitCalls; if (!handles.count(h) || failLimit) return 1;
    *out=limit; return 0;
}
int svcGetResourceLimitCurrentValue(u64* out, Handle h, u32) {
    ++currentCalls; if (!handles.count(h) || failCurrent) return 1;
    *out=current; return 0;
}
int svcCloseHandle(Handle h) {
    ++closed; if (!handles.erase(h)) { ++invalidClose; return 1; } return 0;
}
'''
        suffix = r'''
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr,"FAIL line %d: %s (acquired=%d closed=%d live=%zu)\n", __LINE__, #x, acquired, closed, handles.size()); return 1; } } while(0)
int main(int argc, char** argv) {
    std::string scenario=argv[1];
    if (scenario=="cadence") {
        g_ModMenuState.drivenFrames=59; NoteHeapUsagePeriodically(); CHECK(getCalls==0); return 0;
    }
    failGet=scenario=="get_failure"; zeroHandle=scenario=="zero_handle";
    failLimit=scenario=="limit_failure"; failCurrent=scenario=="current_failure";
    if (scenario=="zero_limit") limit=0;
    if (scenario=="overflow_limit") limit=0x100000000ULL;
    if (scenario=="overflow_current") current=0x100000000ULL;
    if (scenario=="zero_current") current=0;
    int rounds=scenario=="sustained" ? 10000 : 1;
    for (int i=0; i<rounds; ++i) {
        g_ModMenuState.drivenFrames=static_cast<u32>(i)*60;
        NoteHeapUsagePeriodically();
        const u32 sentinel=0xffffffffU;
        CHECK(g_ModMenuState.resourceLimitMemoryBytes == ((failGet || zeroHandle || failLimit || limit==0 || limit>sentinel) ? sentinel : limit));
        CHECK(g_ModMenuState.resourceMemoryUsedBytes == ((failGet || zeroHandle || failCurrent || current>sentinel) ? sentinel : current));
    }
    CHECK(invalidClose==0);
    if (failGet || zeroHandle) { CHECK(acquired==0); CHECK(closed==0); CHECK(limitCalls==0); CHECK(currentCalls==0); }
    else { CHECK(acquired==rounds); CHECK(closed==rounds); CHECK(limitCalls==rounds); CHECK(currentCalls==rounds); }
    CHECK(handles.empty());
    std::printf("PASS %s: rounds=%d acquired=%d closed=%d live=%zu\n", scenario.c_str(),rounds,acquired,closed,handles.size());
    return 0;
}
'''
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cpp = Path(cls.tmp.name) / 'resource_handle.cpp'
        cls.binary = Path(cls.tmp.name) / 'resource_handle'
        cpp.write_text(prefix + function + suffix)
        subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', str(cpp), '-o', str(cls.binary)], check=True)

    def test_production_resource_handle_ownership(self):
        for scenario in ('sustained', 'limit_failure', 'current_failure', 'get_failure', 'zero_handle', 'zero_limit', 'overflow_limit', 'overflow_current', 'zero_current', 'cadence'):
            with self.subTest(scenario=scenario):
                result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
                print(result.stdout + result.stderr, end='')
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
