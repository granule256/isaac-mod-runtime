"""锁定1.60原模组入口与递归include：执行真实生产Lua加载路径；宿主原生替身不等于真机验收。"""
import unittest, subprocess, tempfile, re
from pathlib import Path
from unittest.mock import patch
from . import test_lua_entity_player as fixture
from . import test_support
MOD=Path('/Users/kelinls/code/github/isaac mod/analysis/mod-sources/RepentancePlus/repentanceplus')
NATIVE=r'''
#include "interfaces/lua/rplus_content_names.hpp"
#include "interfaces/lua/rplus_content_names_guards.hpp"
#include "program/mod_content_names.hpp"
#include <filesystem>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
#include <fstream>
#include <iterator>
#include <set>
#include <cstdlib>
std::set<std::string> scriptReads,assetReads;
std::string ReadFile(const std::string& p){std::ifstream f(p,std::ios::binary);return {(std::istreambuf_iterator<char>(f)),{}};}
std::string ModPath(const char* p){std::string s=p;const std::string prefix="rom:/isaac_mods/mods/RPlus/";if(s.starts_with(prefix))s.erase(0,prefix.size());if(s.starts_with("resources/"))s.erase(0,10);auto path=std::string("@MOD@/")+"resources/"+s;if(!ReadFile(path).empty())return path;
 const std::string base="@BASE@/";
 if(!ReadFile(base+"rp_patch/resources/"+s).empty())return base+"rp_patch/resources/"+s;
 return base+"resources/"+s;}
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&,const char* p,u8* out,std::size_t capacity,std::size_t* length){
 std::string name=p;const std::string prefix="rom:/isaac_mods/mods/RPlus/";
 if(!name.starts_with(prefix))return TextReadResult::OpenFailed;name.erase(0,prefix.size());
 auto data=ReadFile(std::string("@MOD@/")+name);if(data.empty())return TextReadResult::OpenFailed;
 *length=data.size();if(data.size()>capacity)return TextReadResult::LengthOutOfRange;
 std::memcpy(out,data.data(),data.size());if(name.ends_with(".lua"))scriptReads.insert(name);return TextReadResult::Success;
}
}
void SpriteCtor(void* p){std::memset(p,0,0x158);float one=1;float color[11]={1,1,1,1};std::memcpy((char*)p+0x144,&one,4);std::memcpy((char*)p+0xdc,&one,4);std::memcpy((char*)p+0xe0,&one,4);std::memcpy((char*)p+0xe8,color,44);}
void Destroy(void*){}
void Play(void*,const char*,bool){}
void SetNamedFrame(void* p,const char*,int frame){std::memcpy((char*)p+0x50,&frame,4);}
void SetFrame(void* p,int frame){std::memcpy((char*)p+0x50,&frame,4);}
const char* NativeString(const void* raw){const auto* p=static_cast<const unsigned char*>(raw);return p[0]&1?*reinterpret_cast<const char* const*>(p+16):reinterpret_cast<const char*>(p+1);}
void* Assign(void* raw,const char* s){auto* v=static_cast<std::uintptr_t*>(raw);const auto size=std::strlen(s);auto* text=static_cast<char*>(std::malloc(size+1));std::memcpy(text,s,size+1);v[0]=((size+16)&~std::uintptr_t(15))|1;v[1]=size;v[2]=reinterpret_cast<std::uintptr_t>(text);return raw;}
void Delete(void* p){std::free(p);}
void LoadSprite(void*,const void* raw,bool){const auto* path=NativeString(raw);const auto file=ModPath(path);auto data=ReadFile(file);if(data.empty()){std::fprintf(stderr,"ASSET_UNAVAILABLE %s -> %s\n",path,file.c_str());std::exit(41);}assetReads.insert(file);}
void FontCtor(void* p){std::memset(p,0,0x48);}
bool FontLoad(void*,const char* path,const char*){auto file=ModPath(path);auto data=ReadFile(file);if(data.empty()){std::fprintf(stderr,"FONT_UNAVAILABLE %s -> %s\n",path,file.c_str());return false;}assetReads.insert(file);return true;}
int main(){
 static_cast<void>(&CorruptVtable);static_cast<void>(&PublishNullCostumes);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&ExpectNumber);static_cast<void>(kScriptTemplate);
 CreateBlocks();FillPlayer(true);PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));WriteWord(g_OwnerSlotBytes,0,AddressOf(g_GameBytes));PublishPlayers({AddressOf(g_PlayerBytes)});LuaRuntime::SetEngineModuleBase(g_EngineBase);
 g_ManagerBytes.assign(kManagerEntityConfigOffset+0xb0,0);g_ManagerSlotBytes.assign(8,0);
 WriteWord(g_ManagerSlotBytes,0,AddressOf(g_ManagerBytes));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(g_ManagerSlotBytes));
 WriteWord(g_ManagerBytes,kManagerEntityConfigOffset,AddressOf(g_ManagerBytes)+kManagerEntityConfigOffset+8);
 namespace guard=isaac::runtime::content_names;auto bytes=[&](auto offset,const auto& v){std::memcpy(g_ModuleBytes.data()+offset,v.data(),v.size());};
 bytes(guard::kPillVectorEntry,guard::kPillVectorGuard);bytes(guard::kPillNameEntry,guard::kPillNameGuard);bytes(guard::kEntityTreeEntry,guard::kEntityTreeGuard);bytes(guard::kEntityValueEntry,guard::kEntityValueGuard);bytes(guard::kEntityNameEntry,guard::kEntityNameGuard);bytes(guard::kEntitySizeEntry,guard::kEntitySizeGuard);bytes(guard::kEntityIdsEntry,guard::kEntityIdsGuard);
 if(!isaac::runtime::RefreshRuntimeContentNames())return 42;
 const auto items=ReadFile("@MOD@/content/items.xml"),pocket=ReadFile("@MOD@/content/pocketitems.xml");
 static_cast<void>(isaac::runtime::IngestModContentXml(isaac::runtime::ModContentFileKind::Items,"RPlus",items.data(),items.size()));
 static_cast<void>(isaac::runtime::IngestModContentXml(isaac::runtime::ModContentFileKind::PocketItems,"RPlus",pocket.data(),pocket.size()));
 LuaRuntime::LuaSpriteBindings sb{};sb.ctor=SpriteCtor;sb.destructor_=Destroy;sb.play=Play;sb.setFrameNamed=SetNamedFrame;sb.setFrame=SetFrame;sb.load=LoadSprite;sb.libcxxStringAssign=Assign;sb.gameOperatorDelete=Delete;LuaRuntime::SetSpriteBindings(sb);
 LuaRuntime::LuaFontBindings fb{};fb.ctor=FontCtor;fb.destructor_=Destroy;fb.load=FontLoad;LuaRuntime::SetFontBindings(fb);
 unsigned syntaxCount=0;auto* parser=luaL_newstate();if(!parser)return 44;
 for(const auto& file:std::filesystem::recursive_directory_iterator("@MOD@")){
  if(!file.is_regular_file()||file.path().extension()!=".lua")continue;
  const auto code=ReadFile(file.path().string());if(luaL_loadbufferx(parser,code.data(),code.size(),file.path().string().c_str(),"t")){
   std::fprintf(stderr,"SYNTAX %s\n",lua_tostring(parser,-1));return 45;}
  lua_pop(parser,1);++syntaxCount;
 }
 lua_close(parser);if(syntaxCount!=53)return 46;
 auto main=ReadFile("@MOD@/main.lua");
 main+=R"lua(
_rplus_boot={events=0};for id=0,73 do if #Isaac.GetCallbacks(id)>0 then _rplus_boot.events=_rplus_boot.events+1 end end assert(_rplus_boot.events>=43,'registered event families missing');assert(type(CustomHealthAPI)=='table' and type(RepentancePlusMod)=='table');)lua";GameFileReader::Bindings files{};
 auto result=LuaRuntime::InitializeManifestMod(main.data(),main.size(),"@RPlus/main.lua","rom:/isaac_mods/mods/RPlus",files);
 char error[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::printf("BOOT=%u SCRIPTS=%zu SYNTAX=53 ASSETS=%zu ERROR=%s\n",unsigned(result),scriptReads.size()+1,assetReads.size(),error);
 return result==LuaRuntime::LuaInitResult::Success?0:1;
}
'''
class RPlusFullBootTests(unittest.TestCase):
 def test_unmodified_v160_main_and_recursive_scripts(self):
  with tempfile.TemporaryDirectory(prefix='rplus-full-boot-') as d:
   s=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+NATIVE.replace('@MOD@',str(MOD)).replace('@BASE@',str(next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1'))))
   s=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',s,count=1)
   flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
   with patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
    exe=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=s)
   r=subprocess.run([str(exe)],capture_output=True,text=True);print(r.stdout+r.stderr,flush=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
