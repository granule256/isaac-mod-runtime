"""Actual ItemOverlay state and custom giant-book assets, not dummy API presence."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / 'source'
DRIVER = PREFIX + r'''
#include "interfaces/lua/repentogon_item_overlay_api.hpp"
#include "interfaces/lua/repentogon_menu_world_api.hpp"
#include "interfaces/lua/repentogon_sprite_api.hpp"
#include "program/xml_data_store.hpp"
#include "runtime_constants.hpp"
#include <vector>
#include <string>
static std::vector<unsigned char> moduleBytes,gameSlot,game,layerBytes,layerData;
static unsigned shows{},loads{},graphics{},replaces{},updates{};
static int lastId{},lastDelay{};
static void* lastPlayer{};
static std::string path,texture,animation;
static bool force{};
template<class T>static void Put(std::vector<unsigned char>& out,size_t off,T v){std::memcpy(out.data()+off,&v,sizeof(v));}
static void* Sprite(){return game.data()+0x25db0+8;}
static void Show(void* object,int id,int delay,void* player){
 assert(object==game.data()+0x25db0);++shows;lastId=id;lastDelay=delay;lastPlayer=player;
 Put(game,0x25db0+4,id);Put(game,0x25db0+0x1478,delay);
}
static void* Assign(void* object,const char* text){
 const auto n=std::strlen(text);assert(n<23);std::memset(object,0,24);
 static_cast<unsigned char*>(object)[0]=n*2;std::memcpy(static_cast<char*>(object)+1,text,n);return object;
}
static const char* Text(const void* object){assert(!(static_cast<const unsigned char*>(object)[0]&1));return static_cast<const char*>(object)+1;}
static void Load(void* s,const void* str,bool enabled){assert(s==Sprite()&&enabled);path=Text(str);++loads;}
static void Graphics(void* s){assert(s==Sprite());++graphics;}
static void Replace(void* s,int id,const void* str){assert(s==Sprite()&&id==0);texture=Text(str);++replaces;}
static void Update(void* s){assert(s==Sprite());++updates;}
static void Play(void* s,const char* name,bool f){assert(s==Sprite());animation=name;force=f;}
static void* Layer(void* s,int id)noexcept{assert(s==Sprite()&&id>=0&&id<2);return layerBytes.data()+id*0xb0;}
static int ClearGame(lua_State*){Put(gameSlot,0,std::uintptr_t{});return 0;}
static void Extensions(lua_State* L)noexcept{lua_pushcfunction(L,ClearGame);lua_setglobal(L,"_clearGame");}
int main(){
 moduleBytes.resize(0xaad1b0+8);gameSlot.resize(8);game.resize(0x270000);
 layerBytes.resize(2*0xb0);layerData.resize(2*0x40);
 Put(moduleBytes,kGameOwnerGlobalSlotOffset,reinterpret_cast<std::uintptr_t>(gameSlot.data()));
 Put(gameSlot,0,reinterpret_cast<std::uintptr_t>(game.data()));
 Put(game,0x25db0+8+0xb0,2);
 for(int i=0;i<2;++i){
  Put(layerBytes,i*0xb0,reinterpret_cast<std::uintptr_t>(layerData.data()+i*0x40));
  layerData[i*0x40+8]=8;std::memcpy(layerData.data()+i*0x40+9,"poof",4);
  Put(layerBytes,i*0xb0+0x50+16,0.75f);
 }
 const unsigned char guard[]={0x3f,0xb8,0x00,0x71,0x88,0x0a,0x00,0x54,0xff,0x03,0x02,0xd1,0xfd,0x7b,0x02,0xa9};
 std::memcpy(moduleBytes.data()+0x3c5034,guard,16);
 LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(moduleBytes.data()));
 LuaRuntime::SetGameBindings(reinterpret_cast<std::uintptr_t>(moduleBytes.data())+kGameOwnerGlobalSlotOffset,0);
 LuaRuntime::ObserveGameThread();Files files(true);SetSessionSaveFilePort(&files);
 const repentogon::NativePort port{Ready,Ready,RepentogonMenuWorldSpriteAlive};repentogon::SetNativePort(&port);
 SetRepentogonItemOverlayNativeTestBinding(reinterpret_cast<std::uintptr_t>(&Show));
 SetRepentogonSpriteNativeTestBindings({nullptr,Layer,nullptr,nullptr});
 LuaRuntime::LuaSpriteBindings sprites{};sprites.load=Load;sprites.loadGraphics=Graphics;
 sprites.replaceSpritesheet=Replace;sprites.update=Update;sprites.play=Play;sprites.libcxxStringAssign=Assign;
 LuaRuntime::SetSpriteBindings(sprites);LuaRuntime::SetRuntimeExtensionInstaller(Extensions);
 const char* xml="<giantbook anm2root='g/'><entry name='Custom' anm2='Book.anm2' gfx='book.png' anim='Appear'><layer name='poof' r='255' g='192' b='203' a='180'/></entry></giantbook>";
 const char* base="<giantbook><entry id='46' name='Base'/></giantbook>";
 assert(xml_data::IngestXmlDataFile(xml_data::XmlDataFileKind::GiantBooks,"BaseGame",false,base,std::strlen(base)));
 assert(xml_data::IngestXmlDataFile(xml_data::XmlDataFileKind::GiantBooks,"Mod",true,xml,std::strlen(xml)));
 const char* script=R"lua(
assert(type(ItemOverlay)=='table')
local s=ItemOverlay.GetSprite()
assert(type(s)=='userdata' and s:GetLayerCount()==2)
assert(type(ItemOverlay.GetMegaMushPlayerSprite())=='userdata')
ItemOverlay.Show(1)
assert(ItemOverlay.GetOverlayID()==1 and ItemOverlay.GetDelay()==0 and ItemOverlay.GetPlayer()==nil)
ItemOverlay.Show(47,3,nil)
assert(ItemOverlay.GetOverlayID()==47 and ItemOverlay.GetDelay()==3)
assert(not pcall(function()ItemOverlay.Show({})end))
_clearGame();assert(not pcall(ItemOverlay.GetSprite))
assert(not pcall(function()s:GetLayerCount()end))
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@item-overlay.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[1024]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::fprintf(stderr,"%s\n",error);return 1;
 }
 assert(shows==2&&lastId==1&&lastDelay==3&&lastPlayer==nullptr);
 assert(loads==1&&replaces==1&&graphics==3&&updates==3);
 assert(path=="g/Book.anm2"&&texture=="g/book.png"&&animation=="Appear"&&!force);
 for(int i=0;i<2;++i){float color[5]{};std::memcpy(color,layerBytes.data()+i*0xb0+0x50,sizeof(color));
  assert(color[0]==1.f&&color[1]==192.f/255.f&&color[2]==203.f/255.f&&color[3]==180.f/255.f&&color[4]==0.75f);
 }
 assert(LuaRuntime::ShutdownForModReload());LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
 LuaRuntime::SetSpriteBindings({});repentogon::SetNativePort(nullptr);SetSessionSaveFilePort(nullptr);
}
'''


class ItemOverlayTests(unittest.TestCase):
    def test_custom_book_native_state_assets_tints_and_lifetime(self):
        with tempfile.TemporaryDirectory(prefix='item-overlay-') as folder:
            binary = test_support.build_lua_harness(source_root=SOURCE,
                workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
