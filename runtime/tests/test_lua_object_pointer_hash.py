"""真实注册GetPtrHash的RoomDescriptor身份、StageAPI比较与失效边界。"""
import subprocess
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path
try:
    from . import test_support
    from .test_support import build_lua_harness
    from .test_lua_room_descriptor import HARNESS as DESCRIPTOR_HARNESS, SOURCE
except ImportError:
    import test_support
    from test_support import build_lua_harness
    from test_lua_room_descriptor import HARNESS as DESCRIPTOR_HARNESS, SOURCE

SCRIPT = r'''
local mod=RegisterMod('HashProbe',1)
local saved
mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function()
 if saved then
   assert(GetPtrHash(saved)==0,'stale descriptor must not retain a hash')
   print('INVALIDATED')
   return
 end
 local level=Game():GetLevel()
 local a=level:GetCurrentRoomDesc()
 local b=level:GetRoomByIdx(84)
 local c=level:GetRoomByIdx(97)
 assert(a~=b,'test requires independent wrappers')
 assert(GetPtrHash(a)~=0,'live descriptor hash is zero')
 assert(GetPtrHash(a)==GetPtrHash(b),'same native descriptor differs')
 assert(GetPtrHash(a)~=GetPtrHash(c),'different native descriptors collide')
 local nativeMode=level:GetRoomByIdx(84,1)~=nil
 assert(not EXPECT_NATIVE or nativeMode,'native dimensions rejected')
 local descriptors=nativeMode and {a,level:GetRoomByIdx(84,1),level:GetRoomByIdx(84,2)} or {a,c,level:GetRoomByIdx(71)}
 -- StageAPI.GetDimension的身份比较原算法；用三个真实不同描述符隔离维度选择。
 local StageAPI={}
 local shared={Level=level}
 -- 卡上source-stage-roomHandler.lua:1381的原GetDimension函数（仅无参分支不使用）。
 function StageAPI.GetDimension(roomDesc)
    if not roomDesc then
        local levelMap = StageAPI.GetCurrentLevelMap()
        if levelMap and StageAPI.CurrentLevelMapRoomID then
            return levelMap.Dimension
        end
    end
    roomDesc = roomDesc or shared.Level:GetCurrentRoomDesc()
    if roomDesc.GridIndex < 0 then return -2 end
    local hash = GetPtrHash(roomDesc)
    for dimension = 0, 2 do
        local dimensionDesc = shared.Level:GetRoomByIdx(roomDesc.SafeGridIndex, dimension)
        if GetPtrHash(dimensionDesc) == hash then return dimension end
    end
 end
 local function dimension(desc)
   if nativeMode then return StageAPI.GetDimension(desc) end
   local ptrHash=GetPtrHash(desc)
   for i=0,2 do
     if ptrHash==GetPtrHash(nativeMode and level:GetRoomByIdx(desc.SafeGridIndex,i) or descriptors[i+1]) then return i end
   end
 end
 for i=0,2 do assert(dimension(descriptors[i+1])==i,'dimension identity mismatch') end
 if nativeMode then
   print('NATIVE_DIMENSIONS')
   assert(GetPtrHash(level:GetRoomByIdx(999))~=0,'native static descriptor lost identity')
   assert(GetPtrHash(level:GetRoomByIdx(-100))~=0,'special descriptor lost identity')
   assert(StageAPI.GetDimension(level:GetRoomByIdx(-100))==-2,'off-grid classification changed')
   assert(GetPtrHash(level:GetRoomByIdx(666))==0,'unreadable descriptor accepted')
 else assert(GetPtrHash(level:GetRoomByIdx(999))==0,'empty descriptor has a hash') end
 assert(not pcall(GetPtrHash,nil) and not pcall(GetPtrHash,{}) and not pcall(GetPtrHash,7))
 assert(not pcall(GetPtrHash) and GetPtrHash(a,b)==GetPtrHash(a),'PC first-argument contract changed')
 saved=a
 print('IDENTITY_OK')
end)
'''
NATIVE = r'''
#include <cstdint>
#include <cstring>
#include <array>
#include "runtime_constants.hpp"
extern "C" const void* HashNativeRoom(const void* level,int index,int dimension) {
 static std::array<unsigned char,0x100> empty{}, special{};
 if(index==-100){std::memset(special.data(),0xff,8);return special.data();}
 if(index==999)return empty.data();
 if(index==666)return reinterpret_cast<const void*>(1);
 if(dimension<0)dimension=0;
 if(dimension>2)return empty.data();
 unsigned slot=static_cast<unsigned>(dimension);
 if(index==97)slot=1;
 if(index==71)slot=2;
 return static_cast<const unsigned char*>(level)+0x18+slot*0x100;
}
namespace isaac::runtime {
template<class Fn> Fn HashNativeFunction(std::uintptr_t) {return reinterpret_cast<Fn>(&HashNativeRoom);}
}
'''
HARNESS = DESCRIPTOR_HARNESS.replace(
    'if (std::strcmp(scenario, "top_level") == 0) {\n        script =',
    'if (true) {\n        script = R"HASH(' + SCRIPT + ')HASH";\n    } else if (std::strcmp(scenario, "top_level") == 0) {\n        script =', 1)
HARNESS = HARNESS.replace('    const char* script = nullptr;', r'''
    if(std::strcmp(scenario,"native")==0) {
        WriteAt<std::uint32_t>(g_ModuleBytes,kLevelGetRoomByIdxOffset,kLevelGetRoomByIdxEntryWord);
        for(unsigned slot=0;slot<3;++slot){WriteAt<std::uint32_t>(g_LevelBytes,0x18+slot*0x100,84);WriteAt<std::uint32_t>(g_LevelBytes,0x1c+slot*0x100,84);}
    }
    const char* script = nullptr;
''')
HARNESS = HARNESS.replace('    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@roomdesc.lua");',r'''
    const std::string initializedScript = std::string(std::strcmp(scenario,"native")==0 ? "EXPECT_NATIVE=true\n" : "") + script;
    const auto result = LuaRuntime::InitializeFromBuffer(initializedScript.data(),initializedScript.size(),"@roomdesc.lua");
''')
HARNESS = HARNESS.replace('    return 0;\n}\n', r'''
    if (std::strcmp(scenario,"native")==0) return 0;
    if (std::strcmp(scenario,"count_zero")==0) {
        WriteAt<std::uint32_t>(g_LevelBytes,0x21510,0);
    } else if (std::strcmp(scenario,"module_changed")==0) {
        LuaRuntime::SetEngineModuleBase(AddressOf(g_ModuleBytes)+8);
    } else if (std::strcmp(scenario,"owner_missing")==0) {
        WriteWord(g_GamePointerBytes,0,0);
    }
    LuaRuntime::DispatchPreGetCollectible(nullptr,0,0,1,0);
    if (LuaRuntime::TakeCallbackError()) {
        char buffer[512]={};
        const auto length=LuaRuntime::CopyLastLuaErrorText(buffer,sizeof(buffer));
        std::printf("LUA_ERROR(%.*s)\n",static_cast<int>(length),buffer);
        return 5;
    }
    return 0;
}
''',1)

class LuaObjectPointerHashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='isaac-object-hash-')
        path=SOURCE.parent/'src/interfaces/lua/remaining_api.cpp'
        instrumented=Path(cls.temporary.name)/'hash_remaining_api.cpp'
        code=path.read_text()
        if os.environ.get('HASH_DIMENSION_BASELINE'):
            baseline_guard='''    if (argumentCount == 3 && isaac::runtime::IsIntegerArgument(state, 3)) {
        const lua_Integer dimension = lua_tointegerx(state, 3, nullptr);
        if (dimension != 0 && dimension != -1) { lua_pushnil(state); return 1; }
    }
'''
            needle='    const lua_Integer requested = lua_tointegerx(state, 2, nullptr);'
            start=code.index('int LevelGetRoomByIdx(lua_State* state) {')
            code=code[:start]+code[start:].replace(needle,needle+'\n'+baseline_guard,1)
        # 宿主通用守卫只排除空指针；明确模拟地址1不可读，设备用svcQueryMemory。
        code=code.replace('return isaac::runtime::engine_memory::EngineMemoryReadable(address, length);',
            'return address != 1 && isaac::runtime::engine_memory::EngineMemoryReadable(address, length);')
        instrumented.write_text(NATIVE+code.replace('engine_call::AsFunction<LevelGetRoomByIdxFn>','HashNativeFunction<LevelGetRoomByIdxFn>'))
        sources=[instrumented if item==path else item for item in test_support.layered_lua_runtime_sources(SOURCE)]
        with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
            cls.binary=build_lua_harness(source_root=SOURCE,
                workdir=Path(cls.temporary.name)/'harness',harness_source=HARNESS)
    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()
    def test_descriptor_identity_dimensions_and_lifetime(self):
        for scenario in ('module_changed','owner_missing','native'):
            with self.subTest(scenario=scenario):
                result=subprocess.run([str(self.binary),scenario],text=True,capture_output=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('IDENTITY_OK',result.stdout)
                if scenario!='native': self.assertIn('INVALIDATED',result.stdout)
                else: self.assertIn('NATIVE_DIMENSIONS',result.stdout)
