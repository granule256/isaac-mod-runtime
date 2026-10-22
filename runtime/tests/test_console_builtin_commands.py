"""真实Lua控制台命令：同一状态、标准输出、错误恢复和近似命令分派。"""
import re,subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from . import test_console_long_commands as console_fixture
from .test_support import build_lua_harness
MAIN=r'''
#include "console_callback_hook.hpp"
#include "infrastructure/console/console_bridge.hpp"
#include <cassert>
static std::string output;
void Command(std::initializer_list<const char*> words);
bool nested{};
static void Print(void*,const void* head,std::uint32_t,std::uint32_t){auto* h=static_cast<const unsigned char*>(head);std::string part(isaac::runtime::console::EngineStringData(h),isaac::runtime::console::EngineStringSize(h));output+=part;if(nested&&part=="outer"){nested=false;Command({"l","print('inner')"});}}
void Command(std::initializer_list<const char*> words){
 std::vector<std::array<unsigned char,24>> tokens(words.size());std::size_t i=0;
 for(auto* word:words){assert(isaac::runtime::console::BuildBorrowedCommandString(word,strlen(word),tokens[i++].data()));}
 isaac::runtime::ConsoleCommandView v{tokens.data(),tokens.size(),nullptr,Print};LuaRuntime::DispatchExecuteCommand(v);
}
int main(){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);LuaRuntime::ObserveGameThread();
 assert(LuaRuntime::InitializeFromBuffer("standalone=0",12,"@empty.lua")==LuaRuntime::LuaInitResult::Success);
 Command({"l","standalone=9;","print('no-callback')"});assert(output=="no-callback\n");output.clear();
 double standalone{};assert(LuaRuntime::ReadLuaGlobalNumber("standalone",&standalone)&&standalone==9);
 const char* script="counter=0;local m=RegisterMod('builtin-test',1);m:AddCallback(22,function(_,cmd,args) counter=counter+100;return cmd..':'..args end)";
 assert(LuaRuntime::InitializeFromBuffer(script,strlen(script),"@builtins.lua")==LuaRuntime::LuaInitResult::Success);
 Command({"lua","counter=counter+1;","print('Hello',","42)"});
 assert(output=="Hello\t42\n");double counter{};assert(LuaRuntime::ReadLuaGlobalNumber("counter",&counter)&&counter==1);
 output.clear();Command({"l","counter=counter+2;","Isaac.ConsoleOutput('direct')"});assert(output=="direct");
 assert(LuaRuntime::ReadLuaGlobalNumber("counter",&counter)&&counter==3);
 output.clear();Command({"luamem"});assert(output.find("Lua mem usage: ")==0&&output.find(" KB and ")!=std::string::npos&&output.ends_with(" bytes\n"));
 output.clear();Command({"lua","local","="});assert(output.find("console")!=std::string::npos);
 output.clear();Command({"l","error('user-error')"});assert(output.find("user-error")!=std::string::npos);
 output.clear();Command({"l","counter=counter+4;","print('still-alive')"});assert(output=="still-alive\n");
 assert(LuaRuntime::ReadLuaGlobalNumber("counter",&counter)&&counter==7);
 // 回调执行中print同样被本次命令捕获，结束后不能留下输出接收者。
 output.clear();Command({"luax","argument"});assert(output=="luax:argument");assert(LuaRuntime::ReadLuaGlobalNumber("counter",&counter)&&counter==107);
 output.clear();assert(LuaRuntime::InitializeFromBuffer("print('outside')",16,"@outside.lua")==LuaRuntime::LuaInitResult::Success);assert(output.empty());
 output.clear();Command({"lua","print(tostring(Game():GetFrameCount()))"});assert(!output.empty());
 // 大输出、多参数和tostring错误不遗留输出作用域或Lua栈。
 output.clear();Command({"lua","print(string.rep('x',10000),","'tail')"});assert(output==std::string(10000,'x')+"\ttail\n");
 output.clear();Command({"lua","print(setmetatable({},","{__tostring=function()","error('tostring-error')","end}))"});assert(output.find("tostring-error")!=std::string::npos);
 output.clear();Command({"lua","print()"});assert(output=="\n");
 output.clear();nested=true;Command({"l","print('outer')"});assert(output=="outerinner\n\n"&&!nested);
 assert(!LuaRuntime::ConsoleCommandOutputActive());
 assert(!LuaRuntime::TakeCallbackError());
 return 0;
}
'''
class ConsoleBuiltinCommandTests(unittest.TestCase):
 def test_lua_memory_and_output_in_shared_runtime(self):
  with tempfile.TemporaryDirectory(prefix='isaac-console-builtins-') as tmp:
   source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
   source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(tmp),harness_source=source)
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)

 def test_clear_uses_native_ownership_and_restores_output(self):
  code=r'''#include "infrastructure/console/console_clear.hpp"
#include <cassert>
#include <array>
using namespace isaac::runtime::console;
unsigned calls{};
void Clear(void* p){auto* b=static_cast<unsigned char*>(p);std::uintptr_t target{};std::memcpy(&target,b+0x150,8);assert(target==0);std::uint64_t size=1;std::memcpy(b+0x78,&size,8);++calls;}
int main(){std::array<unsigned char,0x180> object{};std::uint64_t target=0x12345,history=12,commands=7;
std::memcpy(object.data()+0x150,&target,8);std::memcpy(object.data()+0x78,&history,8);std::memcpy(object.data()+0xa8,&commands,8);
assert(!ClearVisibleConsole(nullptr,Clear)&&!ClearVisibleConsole(object.data(),nullptr)&&calls==0);
assert(ClearVisibleConsole(object.data(),Clear)&&calls==1);std::uint64_t after{},count{};std::memcpy(&after,object.data()+0x150,8);std::memcpy(&count,object.data()+0xa8,8);assert(after==target&&count==commands);std::memcpy(&count,object.data()+0x78,8);assert(count==1);}
'''
  with tempfile.TemporaryDirectory(prefix='isaac-console-clear-') as tmp:
   p=Path(tmp);(p/'stdfloat').write_text('#pragma once\nnamespace std {using float16_t=float;using float128_t=long double;}\n');(p/'test.cpp').write_text(code)
   r=subprocess.run([console_fixture.host_compilers()[1],'-std=c++23','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(console_fixture.SOURCE),'-I',str(console_fixture.SOURCE.parent/'src'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
