"""颜色插值、染色与精灵原生44字节值的往返。"""
import unittest, subprocess, tempfile, re
from pathlib import Path
from . import test_lua_entity_player as fixture
from .test_support import build_lua_harness
MAIN=r'''static std::vector<void*> colorSprites;
static void ColorCtor(void* self){colorSprites.push_back(self);std::memset(self,0,0x158);float one=1;for(unsigned i=0;i<4;++i)std::memcpy(static_cast<char*>(self)+0xe8+4*i,&one,4);}
static void ColorDtor(void*){}
int main(){static_cast<void>(&CorruptVtable);static_cast<void>(&PublishNullCostumes);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&ExpectNumber);static_cast<void>(kScriptTemplate);
 CreateBlocks();FillPlayer(true);PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));WriteWord(g_OwnerSlotBytes,0,AddressOf(g_GameBytes));PublishPlayers({AddressOf(g_PlayerBytes)});LuaRuntime::SetEngineModuleBase(g_EngineBase);
 LuaRuntime::LuaSpriteBindings b{};b.ctor=ColorCtor;b.destructor_=ColorDtor;LuaRuntime::SetSpriteBindings(b);
 std::string script=R"lua(local m=RegisterMod('rplus-color',1);m:AddCallback(1,function()
 local a=Color(0,0,0,1,.1,.2,.3);a:SetColorize(.2,.4,.6,.8)
 local b=Color(1,1,1,1,.3,.4,.5);b:SetColorize(.6,.8,1,1)
 local c=Color.Lerp(a,b,.5);assert(math.abs(c.R-.5)<.00001);assert(math.abs(c.RO-.2)<.00001)
 local sprite=Sprite();sprite.Color=c;local round=sprite.Color
 local copied=Sprite();copied.Color=round;_roundsprites={sprite,copied}
 local out=Color.Lerp(a,b,2);assert(out.R==2,'PC extrapolation was clamped')
 assert(not pcall(function()Color.Lerp(a,b,false)end))
 _color_ok=1
 end))lua";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@rplus-color.lua")!=LuaRuntime::LuaInitResult::Success)return 1;LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 2;for(void* sp:colorSprites){float native[11];memcpy(native,static_cast<char*>(sp)+0xe8,sizeof(native));for(unsigned i=0;i<4;++i)if(std::abs(native[4+i]-(.4f+.2f*i-.1f*(i==3)))>.00001f)return 4;}return ExpectNumber("_color_ok",1)?0:3;
}'''
class ColorConsumerTests(unittest.TestCase):
 def test_original_color_interpolation_and_native_sprite_roundtrip(self):
  with tempfile.TemporaryDirectory(prefix='rplus-color-') as work:
   s=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
   s=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',s,count=1)
   exe=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(work),harness_source=s)
   r=subprocess.run([str(exe)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
