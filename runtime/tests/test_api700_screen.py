"""屏幕比例动态真值与距离反变换。"""
import unittest
from .test_api400_params import run_main
MAIN=r'''
#include "lua_object_handles.hpp"
#include <cstdio>
#include <cstring>
using namespace isaac::runtime;
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();g_ModuleBytes.resize(kIsaacPointScaleSlotOffset+0x100);g_EngineBase=AddressOf(g_ModuleBytes);FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);std::vector<unsigned char> point(4);WriteAt<float>(point,0,3.5F);WriteWord(g_ModuleBytes,kIsaacPointScaleSlotOffset,AddressOf(point));
const char*script=R"lua(assert(Isaac.GetScreenPointScale()==3.5);local v=Isaac.ScreenToWorldDistance(Vector(6.5,-13));assert(v.X==10 and v.Y==-20);local back=Isaac.WorldToScreenDistance(v);assert(back.X==6.5 and back.Y==-13);assert(not pcall(function()Isaac.ScreenToWorldDistance({})end)))lua";
if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@api700-screen.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t i=0;i<n;++i)std::fprintf(stderr,"%s\n",e[i].text);return 1;}
WriteAt<float>(point,0,4.25F);const char*updated="assert(Isaac.GetScreenPointScale()==4.25)";if(LuaRuntime::InitializeFromBuffer(updated,std::strlen(updated),"@api700-screen-update.lua")!=LuaRuntime::LuaInitResult::Success)return 2;
WriteWord(g_ModuleBytes,kIsaacPointScaleSlotOffset,0);const char*missing="local ok,e=pcall(Isaac.GetScreenPointScale);assert(not ok and e:find('unavailable'))";if(LuaRuntime::InitializeFromBuffer(missing,std::strlen(missing),"@api700-screen-missing.lua")!=LuaRuntime::LuaInitResult::Success)return 3;
return 0;}
'''
class ScreenConsumer(unittest.TestCase):
 def test_public_dynamic_scale_and_inverse_distance(self):
  r=run_main(MAIN);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
