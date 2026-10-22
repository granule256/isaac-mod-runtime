"""22真实Lua返回消费与命令token参数，不用人工内建命令名单。"""
import subprocess,tempfile,unittest,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
#include "console_callback_hook.hpp"
#include "infrastructure/console/console_bridge.hpp"
#include <cassert>
static std::string printed;
static void Print(void*,const void* head,std::uint32_t color,std::uint32_t duration){
 assert(color==0xffd3d3d3U && duration==150);auto* h=static_cast<const unsigned char*>(head);
 const char* p;std::size_t n;if(h[0]&1){memcpy(&n,h+8,8);memcpy(&p,h+16,8);}else{n=h[0]>>1;p=reinterpret_cast<const char*>(h+1);}printed.assign(p,n);
}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);LuaRuntime::ObserveGameThread();
 std::string script="_cmd={a=0,b=0};local m=RegisterMod('cmd',1);m:AddCallback(22,function(_,cmd,args) assert(cmd=='Test');assert(args=='apple 1 Pear test');_cmd.a=_cmd.a+1;";
 if(scene=="string")script+="return 'line1\\nline2'";
 else if(scene=="long")script+="return string.rep('x',10000)";
 else if(scene=="false")script+="return false";
 else if(scene=="error")script+="error('bad command')";
 else if(scene=="empty")script+="return ''";
 script+="\nend);m:AddCallback(22,function()_cmd.b=_cmd.b+1;return 'tail' end)";
 if(scene=="param")script+=";setmetatable(Isaac.GetCallbacks(22),{__matchParams=function(a,b) assert(a==-1);return true end})";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@cmd.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 const char* words[]={"Test","apple","1","Pear","test"};unsigned char tokens[5][24]{};
 for(unsigned i=0;i<5;++i){auto n=strlen(words[i]);tokens[i][0]=static_cast<unsigned char>(n<<1);memcpy(tokens[i]+1,words[i],n+1);}
 isaac::runtime::ConsoleCommandView v{};v.tokens=tokens;v.count=5;v.print=Print;
 LuaRuntime::DispatchExecuteCommand(v);
 double a{},b{};if(LuaRuntime::ReadLuaTableNumber("_cmd","a",&a)||LuaRuntime::ReadLuaTableNumber("_cmd","b",&b))return 2;
 if(a!=1 || b!=((scene=="nil"||scene=="param")?1:0))return 3;
 std::string want=scene=="string"?"line1\nline2":scene=="long"?std::string(10000,'x'):(scene=="nil"||scene=="param")?"tail":"";
 if(scene=="error"){if(printed.find("bad command")==std::string::npos)return 4;}
 else if(printed!=want)return 4;
 if(LuaRuntime::TakeCallbackError()!=(scene=="error"))return 5;
 return 0;
}
'''
class ConsoleExecuteCallbackTests(unittest.TestCase):
 def test_custom_command_bridge_exists(self):
  self.assertTrue((ROOT/'runtime/source/console_callback_hook.hpp').exists(),'未知命令消费桥尚未实现')
 def test_first_return_string_parameters_and_errors(self):
  if not (ROOT/'runtime/source/console_callback_hook.hpp').exists():self.fail('未知命令消费桥尚未实现')
  with tempfile.TemporaryDirectory(prefix='isaac-cmd-') as tmp:
   source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
   source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(tmp),harness_source=source)
   for scene in ('string','long','false','error','empty','nil','param'):
    with self.subTest(scene=scene):
     r=subprocess.run([str(binary),scene],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
