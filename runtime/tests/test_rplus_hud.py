"""HUD原生提示消费与CHAPI共享类包装，不把文字只存在Lua表。"""
import unittest, subprocess, tempfile, re
from pathlib import Path
from . import test_lua_entity_player as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''#include "interfaces/lua/game_api.hpp"
static int renders=0,itemCalls=0,fortuneCalls=0;
static void CheckHud(void* self){if(reinterpret_cast<std::uintptr_t>(self)!=AddressOf(g_GameBytes)+kGameHudObjectOffset)std::exit(51);}
static void Render(void* self){CheckHud(self);++renders;}
static void Text(void* self,const char*a,const char*b,bool hidden,bool curse){CheckHud(self);if(std::string(a)!="生命提示"||std::string(b)!="新道具"||hidden||!curse)std::exit(52);++itemCalls;}
static void Fortune(void* self,const void* raw){CheckHud(self);auto* list=static_cast<const std::uintptr_t*>(raw);auto* node=reinterpret_cast<const std::uintptr_t*>(list[1]);for(std::size_t i=0;i<list[2];++i){if(node==list)std::exit(53);if(std::string(reinterpret_cast<const char*>(node[4]),node[3])!=std::to_string(i+1))std::exit(54);node=reinterpret_cast<const std::uintptr_t*>(node[1]);}if(node!=list||list[2]!=5)std::exit(55);++fortuneCalls;}
int main(){
 static_cast<void>(&CorruptVtable);static_cast<void>(&PublishNullCostumes);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&ExpectNumber);static_cast<void>(kScriptTemplate);
 CreateBlocks();FillPlayer(true);PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));WriteWord(g_OwnerSlotBytes,0,AddressOf(g_GameBytes));PublishPlayers({AddressOf(g_PlayerBytes)});LuaRuntime::SetEngineModuleBase(g_EngineBase);
 isaac::runtime::SetHudNativeTestBindings({Render,Text,Fortune});
 std::string script=R"lua(local m=RegisterMod('rplus-hud',1);local cls=getmetatable(HUD).__class;assert(type(cls.Render)=='function');local original=cls.Render;local old=cls.__index;local called=0;rawset(cls,'__index',function(self,k)if k=='Render' then return function(s)called=called+1;original(s)end end return old(self,k)end);m:AddCallback(1,function()
 local hud=Game():GetHUD();assert(getmetatable(hud)==cls);hud:Render();assert(called==1);hud:ShowItemText('生命提示','新道具',true);hud:ShowFortuneText('1','2','3','4','5');_hud_ok=1
 end))lua";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@rplus-hud.lua")!=LuaRuntime::LuaInitResult::Success)return 1;LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 2;
 return renders==1&&itemCalls==1&&fortuneCalls==1&&ExpectNumber("_hud_ok",1)?0:3;
}'''
class HudConsumerTests(unittest.TestCase):
 def test_real_hud_text_list_consumer_and_class_override(self):
  with tempfile.TemporaryDirectory(prefix='rplus-hud-') as work:
   s=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
   s=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',s,count=1)
   exe=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(work),harness_source=s)
   r=subprocess.run([str(exe)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
