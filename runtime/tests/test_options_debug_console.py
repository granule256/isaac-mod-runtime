"""公开Options控制真实控制台开关、延迟存档与执行入口，不允许影子值。"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dist/api-remaining-recovery-20261026'
MAIN = r'''
#include "infrastructure/console/console_bridge.hpp"
#include <cassert>
using namespace isaac::runtime;
namespace console=isaac::runtime::console;
struct RecordingSave final:ISaveFilePort{
 unsigned reads{},writes{};std::string text="isaac-switch-console-state 1\nenabled=0\n";
 Status Read(std::string_view name,char*out,std::size_t capacity,std::size_t*n)noexcept override{
  ++reads;if(name!=kConsoleSwitchFileName)return Status{StatusCode::NotFound};assert(text.size()<=capacity);std::memcpy(out,text.data(),text.size());*n=text.size();return Status::Ok();
 }
 Status Write(std::string_view name,std::string_view value)noexcept override{assert(name==kConsoleSwitchFileName);++writes;text=value;return Status::Ok();}
 Status Remove(std::string_view)noexcept override{return Status::Ok();}
 Status Exists(const char*,bool*)noexcept override{return Status::Ok();}
};
static unsigned engineCalls{};
static void HostCtor(void*){}
static void HostInit(void*){}
static void HostRun(void*,const void* command,void* output,void* player){
 assert(player==nullptr);const auto*h=static_cast<const unsigned char*>(command);
 assert(std::string(console::EngineStringData(h),console::EngineStringSize(h))=="debug-console-test");
 std::memset(output,0,console::kEngineStringBytes);++engineCalls;
}
static bool Step(unsigned expected){
 LuaRuntime::DispatchPostUpdate();
 if(LuaRuntime::TakeCallbackError()){char error[1024]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::fprintf(stderr,"%s\n",error);return false;}
 return ExpectNumber("checked",expected);
}
int main(){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);LuaRuntime::ObserveGameThread();
 RecordingSave save;SetSessionSaveFilePort(&save);console::ConsoleSwitchTick();
 assert(save.reads==1&&save.writes==0&&!console::ConsoleSwitchEnabled()&&!console::Storage().switchReadPending);
 const char*script=R"lua(
 local m=RegisterMod('debug-console-option',1);checked=0
 m:AddCallback(1,function()
  local step=checked+1
  assert(rawget(Options,'DebugConsoleEnabled')==nil,'must not store shadow key')
  if step==1 then
   assert(Options.DebugConsoleEnabled==false,'must read persisted real console switch')
   for i=1,1000 do assert(Options.DebugConsoleEnabled==false) end
   Options.DebugConsoleEnabled=false;Options.DebugConsoleEnabled=nil
  elseif step==2 then
   assert(Options.DebugConsoleEnabled==true,'native switch changes must be visible')
   Options.DebugConsoleEnabled=false;assert(Options.DebugConsoleEnabled==false)
  elseif step==3 then
   for i=1,1000 do assert(Options.DebugConsoleEnabled==false) end
   Options.DebugConsoleEnabled=false;Options.DebugConsoleEnabled=nil
  elseif step==4 then
   Options.DebugConsoleEnabled=0;assert(Options.DebugConsoleEnabled==true,'Lua zero is truthy')
  elseif step==5 then
   for i=1,1000 do assert(Options.DebugConsoleEnabled==true);Options.DebugConsoleEnabled=0 end
  elseif step==6 then
   Options.DebugConsoleEnabled=nil;assert(Options.DebugConsoleEnabled==false,'Lua nil disables')
  elseif step==7 then
   Options.DebugConsoleEnabled='';assert(Options.DebugConsoleEnabled==true,'Lua empty string is truthy')
   Options.DebugConsoleEnabled={};assert(Options.DebugConsoleEnabled==true)
  end
  assert(rawget(Options,'DebugConsoleEnabled')==nil,'setter must not create shadow value')
  checked=step
 end)
 )lua";
 assert(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@options-debug-console.lua")==LuaRuntime::LuaInitResult::Success);
 const auto initialReads=save.reads,initialWrites=save.writes;
 if(!Step(1))return 1;
 assert(!console::ConsoleSwitchEnabled()&&!console::Storage().switchWritePending);
 assert(save.reads==initialReads&&save.writes==initialWrites);
 console::RequestConsoleSwitchWrite(true);console::ConsoleSwitchTick();assert(console::ConsoleSwitchEnabled());
 const auto reads=save.reads,writes=save.writes;
 if(!Step(2))return 2;
 assert(!console::ConsoleSwitchEnabled()&&console::Storage().switchWritePending&&!console::Storage().switchWriteValue);
 assert(save.reads==reads&&save.writes==writes);console::ConsoleSwitchTick();assert(save.writes==writes+1&&!ParseConsoleSwitch(save.text));
 // 同值setter不能重挂pending，也不能清掉既有控制设置的合并写延迟。
 const auto written=save.writes;assert(console::RequestConsoleControlsWrite({6,7,2}));assert(console::Storage().controlsWriteDelay==30);
 if(!Step(3))return 3;
 assert(console::Storage().switchWritePending&&console::Storage().controlsWriteDelay==30&&save.writes==written);
 if(!Step(4))return 4;
 assert(console::ConsoleSwitchEnabled()&&console::Storage().switchWritePending&&console::Storage().switchWriteValue&&console::Storage().controlsWriteDelay==0);
 assert(save.writes==written);console::ConsoleSwitchTick();assert(save.writes==written+1&&ParseConsoleSwitch(save.text));
 const auto settledReads=save.reads,settledWrites=save.writes;
 if(!Step(5))return 5;
 assert(!console::Storage().switchWritePending&&save.reads==settledReads&&save.writes==settledWrites);
 console::ConsoleSwitchTick();assert(save.reads==settledReads&&save.writes==settledWrites);
 console::EngineEntries entries{};entries.consoleCtor=HostCtor;entries.consoleInit=HostInit;entries.runCommand=HostRun;
 auto execute=[&](){return console::ExecuteCommand(entries,g_EngineBase,"debug-console-test",18);};
 assert(execute().status==console::ExecStatus::kOk&&engineCalls==1);
 if(!Step(6))return 6;
 const auto refusals=console::State().switchRefusals;
 assert(!console::ConsoleSwitchEnabled()&&execute().status==console::ExecStatus::kDisabledBySwitch&&engineCalls==1&&console::State().switchRefusals==refusals+1);
 if(!Step(7))return 7;
 assert(console::ConsoleSwitchEnabled()&&execute().status==console::ExecStatus::kOk&&engineCalls==2);
 assert(save.reads==settledReads&&save.writes==settledWrites);console::ConsoleSwitchTick();assert(save.writes==settledWrites+1&&ParseConsoleSwitch(save.text));
 SetSessionSaveFilePort(nullptr);return 0;
}
'''


class OptionsDebugConsoleTests(unittest.TestCase):
    def test_public_option_drives_real_storage_io_and_execution(self):
        source = fixture.HARNESS[:fixture.HARNESS.index('int main(')] + MAIN
        source = re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '', source, count=1)
        with tempfile.TemporaryDirectory(prefix='options-debug-console-') as tmp:
            binary = build_lua_harness(source_root=fixture.SOURCE, workdir=Path(tmp), harness_source=source)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            print(result.returncode, result.stdout + result.stderr, flush=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
