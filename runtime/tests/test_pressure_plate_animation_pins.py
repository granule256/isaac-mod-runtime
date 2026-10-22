"""压力板动画字段必须写原生指针，并按对象与模组生命周期持有 Lua 字符串。"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_api700_grid as grid
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness, layered_lua_runtime_sources


def run(main):
    prefix = fixture.HARNESS[:fixture.HARNESS.index('int main(')]
    prefix = re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '', prefix, count=1)
    prefix = prefix.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}',
                            'void*GridTestRoom();\nGameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {*room=GridTestRoom();return GameRoomObservation::Success;}')
    source = fixture.SOURCE.parent / 'src/interfaces/lua/api700_grid.cpp'
    extra = () if source in layered_lua_runtime_sources(fixture.SOURCE) else (source,)
    with tempfile.TemporaryDirectory(prefix='pressure-pins-') as directory:
        binary = build_lua_harness(source_root=fixture.SOURCE, workdir=Path(directory),
                                   harness_source=prefix + '\n#define API700_GRID_LOCAL\n' + main,
                                   extra_sources=extra)
        return subprocess.run([str(binary)], capture_output=True, text=True)


EXTRA = r'''
static lua_Alloc savedAlloc;static void* savedAllocContext;static int allocRemaining;
static void* FailingAllocator(void*ud,void*p,size_t oldSize,size_t newSize){if(newSize>oldSize){if(allocRemaining<=0)return nullptr;--allocRemaining;}return savedAlloc(ud,p,oldSize,newSize);}
static int SetterUnderOom(lua_State*L){lua_settable(L,1);return 0;}
static int TestOom(lua_State*L){const int budget=static_cast<int>(luaL_checkinteger(L,1));std::uintptr_t before{};std::memcpy(&before,plateGrid.data()+0x2f8,8);lua_pushcfunction(L,SetterUnderOom);lua_getglobal(L,"plate");lua_pushliteral(L,"NextGreedAnimation");lua_pushvalue(L,2);savedAlloc=lua_getallocf(L,&savedAllocContext);allocRemaining=budget;lua_setallocf(L,FailingAllocator,savedAllocContext);const int result=lua_pcall(L,3,0,0);lua_setallocf(L,savedAlloc,savedAllocContext);std::uintptr_t after{};std::memcpy(&after,plateGrid.data()+0x2f8,8);if(result){assert(after==before);lua_pop(L,1);}else assert(after==reinterpret_cast<std::uintptr_t>(lua_tostring(L,2)));lua_pushboolean(L,result==LUA_OK);return 1;}
static std::vector<unsigned char>secondPlate(0x400);
static void SetupSecondPlate(lua_State*L){secondPlate=plateGrid;WriteAt<std::uint32_t>(secondPlate,kGridEntityGridIndexOffset,23);WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+23*8,AddressOf(secondPlate));auto*h=static_cast<LuaRuntime::GridEntityHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::GridEntityHandle)));*h={};h->entity=secondPlate.data();luaL_getmetatable(L,LuaRuntime::kGridEntityMetatable);lua_setmetatable(L,-2);lua_setglobal(L,"plate2");}
static const char originalAnimation[] = "OriginalGreed";
static const char writerAnimation[] = "NativeGreed";
static const char replacementAnimation[] = "ReplacementGreed";
static int NativeEquals(lua_State*L){std::uintptr_t current{};std::memcpy(&current,plateGrid.data()+0x2f8,8);if(lua_isnil(L,1))lua_pushboolean(L,current==0);else lua_pushboolean(L,current==reinterpret_cast<std::uintptr_t>(luaL_checkstring(L,1)));return 1;}
static int NativeText(lua_State*L){const char*current{};std::memcpy(&current,plateGrid.data()+0x2f8,8);if(current)lua_pushstring(L,current);else lua_pushnil(L);return 1;}
static int SetOriginal(lua_State*L){WriteWord(plateGrid,0x2f8,reinterpret_cast<std::uintptr_t>(originalAnimation));RefreshPressurePlateAnimationPinAfterNativeWrite(L,AddressOf(plateGrid));return 0;}
static int SilentNativeWrite(lua_State*){WriteWord(plateGrid,0x2f8,reinterpret_cast<std::uintptr_t>(writerAnimation));return 0;}
static int NativeWrite(lua_State*L){WriteWord(plateGrid,0x2f8,reinterpret_cast<std::uintptr_t>(writerAnimation));RefreshPressurePlateAnimationPinAfterNativeWrite(L,AddressOf(plateGrid));return 0;}
static int RestorePins(lua_State*L){RestorePressurePlateAnimationPins(L,lua_isnoneornil(L,1)?nullptr:luaL_checkstring(L,1));return 0;}
static int ForgetPin(lua_State*L){ForgetPressurePlateAnimationPinBeforeDestroy(L,AddressOf(plateGrid));return 0;}
static int HasPins(lua_State*L){lua_pushboolean(L,HasPressurePlateAnimationPins());return 1;}
static int RefreshPin(lua_State*L){RefreshPressurePlateAnimationPinAfterNativeWrite(L,AddressOf(plateGrid));return 0;}
static int InvalidRoom(lua_State*L){WriteWord(g_RoomBytes,8,0xdeadbeef);WriteWord(plateGrid,0x2f8,reinterpret_cast<std::uintptr_t>(replacementAnimation));RestorePressurePlateAnimationPins(L,nullptr);WriteWord(g_RoomBytes,8,0);return 0;}
static int InvalidSlot(lua_State*L){WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+21*8,0);RestorePressurePlateAnimationPins(L,nullptr);WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+21*8,AddressOf(plateGrid));return 0;}
static int DestroyAfterSlotRemoval(lua_State*L){WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+21*8,0);ForgetPressurePlateAnimationPinBeforeDestroy(L,AddressOf(plateGrid));WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+21*8,AddressOf(plateGrid));return 0;}
'''
SCRIPT = r'''
assert(plate.NextGreedAnimation==nil and not hasPins())
setOriginal()
for budget=0,35 do
  local ok=testOom(budget,string.rep('FirstPin',20)..budget)
  if ok then assert(hasPins());restorePins() else assert(not hasPins()) end
  assert(nativeText()=='OriginalGreed')
end
plate.NextGreedAnimation=nil
local long=string.rep('Greed',300)
plate.NextGreedAnimation=long
assert(nativeEquals(long) and hasPins())
collectgarbage('collect');assert(plate.NextGreedAnimation==long and nativeEquals(long))
refreshPin();assert(hasPins() and nativeEquals(long)) -- 尚未被原生覆盖不可释放。
plate.NextGreedAnimation=12345;assert(plate.NextGreedAnimation=='12345' and nativeEquals('12345'))
plate.NextGreedAnimation=nil;assert(nativeEquals(nil) and not hasPins())
assert(not pcall(function() plate.NextGreedAnimation={} end))
assert(not pcall(function() door.NextGreedAnimation='Wrong' end))
assert(not pcall(function() poop.NextGreedAnimation='Wrong' end))
setOriginal();assert(plate.NextGreedAnimation=='OriginalGreed')
assert(load("plate.NextGreedAnimation='FromA'",'@rom:/isaac_mods/mods/A/main.lua'))()
assert(hasPins() and nativeText()=='FromA')
restorePins('rom:/isaac_mods/mods/B');assert(hasPins() and nativeText()=='FromA')
assert(load("plate.NextGreedAnimation='FromB'",'@rom:/isaac_mods/mods/B/main.lua'))()
restorePins('rom:/isaac_mods/mods/A');assert(hasPins() and nativeText()=='FromB')
restorePins('rom:/isaac_mods/mods/B');assert(not hasPins() and nativeText()=='OriginalGreed')
plate.NextGreedAnimation='Console';restorePins('rom:/isaac_mods/mods/A');assert(hasPins())
restorePins();assert(not hasPins() and nativeText()=='OriginalGreed')
plate.NextGreedAnimation='NativeReplacesThis';nativeWrite();assert(not hasPins() and nativeText()=='NativeGreed')
restorePins();assert(nativeText()=='NativeGreed')
setOriginal();plate.NextGreedAnimation='SilentNative';silentNativeWrite();restorePins();assert(not hasPins() and nativeText()=='NativeGreed')
setOriginal();plate.NextGreedAnimation='SilentDestroy';silentNativeWrite();forgetPin();assert(not hasPins() and nativeText()=='NativeGreed')
setOriginal();plate.NextGreedAnimation='DestroyThis';forgetPin();assert(not hasPins() and nativeText()=='OriginalGreed')
plate.NextGreedAnimation='DestructorOutsideRoom';destroyAfterSlotRemoval();assert(not hasPins() and nativeText()=='OriginalGreed')
plate.NextGreedAnimation='InvalidRoom';invalidRoom();assert(not hasPins() and nativeText()=='ReplacementGreed')
setOriginal();local held='InvalidSlot';plate.NextGreedAnimation=held;invalidSlot();assert(not hasPins() and nativeEquals(held))
setOriginal();collectgarbage('collect');local before=collectgarbage('count')
for i=1,150 do plate.NextGreedAnimation=string.rep('X',65536)..i end
collectgarbage('collect');assert(collectgarbage('count')-before<200)
assert(#plate.NextGreedAnimation==65539)
restorePins();assert(not hasPins() and nativeText()=='OriginalGreed')
local oomFailures,oomSuccesses=0,0
for budget=0,35 do
  plate.NextGreedAnimation='PreviousPinnedString'
  local ok=testOom(budget,string.rep('Y',128)..budget)
  if ok then oomSuccesses=oomSuccesses+1 else oomFailures=oomFailures+1 end
  assert(hasPins())
  restorePins();assert(not hasPins() and nativeText()=='OriginalGreed')
end
assert(oomFailures>0 and oomSuccesses>0)
assert(load("plate.NextGreedAnimation='ObjectA'",'@rom:/isaac_mods/mods/A/main.lua'))()
assert(load("plate2.NextGreedAnimation='ObjectB'",'@rom:/isaac_mods/mods/B/main.lua'))()
restorePins('rom:/isaac_mods/mods/A');assert(hasPins() and nativeText()=='OriginalGreed' and plate2.NextGreedAnimation=='ObjectB')
restorePins('rom:/isaac_mods/mods/B');assert(not hasPins() and plate2.NextGreedAnimation==nil)
local directory=string.rep('LongRoot',70)
assert(load("plate.NextGreedAnimation='LongRootAnimation'",'@rom:/isaac_mods/mods/'..directory..'/scripts/main.lua'))()
restorePins('rom:/isaac_mods/mods/'..directory);assert(not hasPins() and nativeText()=='OriginalGreed')
'''


class PressurePlatePins(unittest.TestCase):
    def test_real_native_field_and_lifetime(self):
        main = grid.MAIN.replace('int main(){', EXTRA + '\nint main(){')
        main = main.replace('const char*script=R"lua(',
            'SetupSecondPlate(L);for(const auto&r:{std::pair<const char*,lua_CFunction>{"silentNativeWrite",SilentNativeWrite},{"testOom",TestOom},{"nativeEquals",NativeEquals},{"nativeText",NativeText},{"setOriginal",SetOriginal},{"nativeWrite",NativeWrite},{"restorePins",RestorePins},{"forgetPin",ForgetPin},{"hasPins",HasPins},{"refreshPin",RefreshPin},{"invalidRoom",InvalidRoom},{"invalidSlot",InvalidSlot},{"destroyAfterSlotRemoval",DestroyAfterSlotRemoval}}){lua_pushcfunction(L,r.second);lua_setglobal(L,r.first);}\nconst char*script=R"lua(')
        main = main.replace('local extra=door.ExtraSprite;', SCRIPT + '\nlocal extra=door.ExtraSprite;')
        # lua_close 对仍存在的 console pin 必须回收计数；关闭前不清，专门测 GC 兜底。
        main = main.replace('lua_close(L);assert(ownedDestructors==0);',
                            '''if(luaL_dostring(L,"plate.NextGreedAnimation=string.rep('Z',64)"))return 5;assert(HasPressurePlateAnimationPins());lua_close(L);assert(!HasPressurePlateAnimationPins());assert(ownedDestructors==0);''')
        result = run(main)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
