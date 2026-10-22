"""71：五个原始参数、首表延迟读取、空表不跳修正及u16写回。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import build_lua_harness
from .test_lua_event_callbacks import HARNESS, SOURCE

MAIN = r'''
int main(int argc,char** argv) {
 if(argc!=2)return 99;
 std::string value=argv[1];
 std::string script=R"lua(
 local m=RegisterMod('room-spawn',1);m:AddCallback(1,function() end)
 _probe={first=0,last=0,tail=0};_firstResult={6,200,8}
 local function check(_,t,v,s,index,seed)
  assert(t==5 and v==65535 and s==65534 and index==42 and seed==4294967295)
 end
 m:AddCallback(71,function(...) check(...);_probe.first=_probe.first+1;return _firstResult end)
 m:AddCallback(71,function(...) check(...);_probe.last=_probe.last+1;return )lua";
 if(value=="discarded_meta") {
  auto at=script.find("_firstResult={6,200,8}");
  script.replace(at,std::strlen("_firstResult={6,200,8}"),"_firstResult=setmetatable({}, {__index=function() error('discarded table') end})");
  script+="{9,300,10}";
 } else if(value=="late_mutation") script+="(function() _firstResult[2]=999;return nil end)()";
 else {
  const auto at=script.find("return _firstResult end");
  script.replace(at,std::strlen("return _firstResult end"),"return nil end");
  script+=value;
 }
 script+=R"lua( end)
 m:AddCallback(71,function(...) check(...);_probe.tail=_probe.tail+1 end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@room-spawn.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 const auto out=LuaRuntime::DispatchPreRoomEntitySpawnModifying(5,65535,65534,42,0xffffffffU);
 const bool firstStops=value=="discarded_meta"||value=="late_mutation";
 const bool tailRuns=value=="nil";
 const bool invalid=value=="discarded_meta" || value=="{5,'bad'}" || value=="{5,1.5}" || value.find("error(")!=std::string::npos;
 if(LuaRuntime::TakeCallbackError()!=invalid)return 2;
 double n=0;
 if(!Counter("first",&n)||n!=1||!Counter("last",&n)||n!=(firstStops?0:1))return 3;
 if(!Counter("tail",&n)||n!=(tailRuns?1:0))return 14;
 if(value=="{}" || value=="{[4]=99}" || invalid) {
  if(out.present||out.type!=5||out.variant!=65535||out.subType!=65534)return 4;
 } else if(value=="{nil,400}") {
  if(!out.present||out.type!=5||out.variant!=400||out.subType!=65534)return 5;
 } else if(value=="{5,-1,65537}") {
  if(!out.present||out.type!=5||out.variant!=65535||out.subType!=1)return 6;
 } else if(value=="late_mutation") {
  if(!out.present||out.type!=6||out.variant!=200||out.subType!=8)return 7;
 } else if(value=="nil" || value=="false" || value=="42") {
  if(out.present||out.type!=5||out.variant!=65535||out.subType!=65534)return 8;
 } else if(value=="{4294967296,65536,0}") {
  if(!out.present||out.type!=0||out.variant!=0||out.subType!=0)return 9;
 } else if(value=="{5}") {
  if(!out.present||out.type!=5||out.variant!=65535||out.subType!=65534)return 10;
 } else if(!out.present||out.type!=9||out.variant!=300||out.subType!=10)return 11;
 const auto again=LuaRuntime::DispatchPreRoomEntitySpawnModifying(5,65535,65534,42,0xffffffffU);
 if(LuaRuntime::TakeCallbackError()!=invalid||again.present!=out.present||again.type!=out.type||again.variant!=out.variant||again.subType!=out.subType)return 12;
 if(!Counter("tail",&n)||n!=(tailRuns?2:0))return 13;
 if(!Counter("first",&n)||n!=2||!Counter("last",&n)||n!=(firstStops?0:2))return 15;
 bool unused=false;static_cast<void>(Flag("unused",&unused));static_cast<void>(Player());static_cast<void>(Collider());
}
'''
class PreRoomEntitySpawnTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-pre-room-spawn-')
  cls.binary=build_lua_harness(source_root=SOURCE,workdir=Path(cls.tmp.name),harness_source='#include <string>\n'+HARNESS[:HARNESS.index('int main(')]+MAIN)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_first_non_nil_original_arguments_empty_u16_and_protected_reads(self):
  for value in ('discarded_meta','late_mutation','{9,300,10}','{nil,400}','{}','{[4]=99}',
      'nil','false','42',"{5,'bad'}",'{5,1.5}','{5,-1,65537}',"{'9',300.0,10}",
      '{4294967296,65536,0}','{5}',
      "setmetatable({}, {__index=function(_,i) assert(_probe.tail==0 and _probe.last==_probe.first);return ({9,300,10})[i] end})",
      "setmetatable({}, {__index=function() error('index failure') end})"):
   with self.subTest(value=value):
    result=subprocess.run([str(self.binary),value],capture_output=True,text=True)
    self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
