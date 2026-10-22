"""实体生成的七个实参与首个非nil返回、局部覆盖及错误恢复。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_support import build_lua_harness
from .test_lua_event_callbacks import HARNESS,SOURCE
MAIN=r'''
int main(int argc,char** argv){
 if(argc!=2)return 99;
 const char* result=argv[1];
 std::string script=R"lua(
local m=RegisterMod('spawn',1);m:AddCallback(1,function() end)
_probe={first=0,last=0,tail=0}
_firstResult={6,200,8,99}
local function check(_,t,v,s,pos,vel,owner,seed)
 assert(t==5 and v==100 and s==7 and pos.X==12 and pos.Y==34 and vel.X==-5 and vel.Y==6)
 assert(type(owner)=='userdata' and seed==4294967295)
end
m:AddCallback(24,function(...) check(...);_probe.first=_probe.first+1;return _firstResult end)
m:AddCallback(24,function(...) check(...);_probe.last=_probe.last+1;return )lua";
 if(std::strcmp(result,"discarded_meta")==0){
  const auto at=script.find("_firstResult={6,200,8,99}");script.replace(at,std::strlen("_firstResult={6,200,8,99}"),"_firstResult=setmetatable({}, {__index=function() error('discarded table') end})");
  script+="{9,300,10,77}";
 } else if(std::strcmp(result,"late_mutation")==0) script+="(function() _firstResult[2]=999;return nil end)()";
 else {
  // 转换/局部字段场景让第一条nil，以保留第二条的全部转换覆盖。
  const auto at=script.find("return _firstResult end");
  script.replace(at,std::strlen("return _firstResult end"),"return nil end");
  script+=result;
 }
 script+=R"lua( end)
m:AddCallback(24,function(...) check(...);_probe.tail=(_probe.tail or 0)+1 end)
)lua";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@spawn.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 const float pos[]={12,34},vel[]={-5,6};
 const auto out=LuaRuntime::DispatchPreEntitySpawn(5,100,7,pos,vel,Player(),0xffffffffU);
 const bool firstStops=std::strcmp(result,"discarded_meta")==0||std::strcmp(result,"late_mutation")==0;
 const bool tailRuns=std::strcmp(result,"nil")==0;
 const bool invalid=std::strcmp(result,"discarded_meta")==0||std::strcmp(result,"{5, 'bad'}")==0||std::strstr(result,"error(")!=nullptr||std::strcmp(result,"{5, 1.5}")==0;
 if(LuaRuntime::TakeCallbackError()!=invalid)return 2;
 double n=0;if(!Counter("first",&n)||n!=1||!Counter("last",&n)||n!=(firstStops?0:1))return 3;
 if(!Counter("tail",&n)||n!=(tailRuns?1:0))return 8;
 if(std::strcmp(result,"{9,300,10,77}")==0||std::strstr(result,"return ({9,")!=nullptr){if(!out.present||out.type!=9||out.variant!=300||out.subType!=10||out.seed!=77)return 4;}
 else if(std::strcmp(result,"{nil,400}")==0){if(!out.present||out.type!=5||out.variant!=400||out.subType!=7||out.seed!=0xffffffffU)return 5;}
 else if(std::strcmp(result,"{}")==0){if(!out.present||out.type!=5||out.variant!=100||out.subType!=7||out.seed!=0xffffffffU)return 6;}
 else if(std::strcmp(result,"late_mutation")==0){if(!out.present||out.type!=6||out.variant!=200||out.subType!=8||out.seed!=99)return 13;}
 else if(invalid){if(out.present||out.type!=5||out.variant!=100||out.subType!=7||out.seed!=0xffffffffU)return 14;}
 else if(std::strcmp(result,"{5, 4294967296}")==0){if(!out.present||out.type!=5||out.variant!=0||out.subType!=7||out.seed!=0xffffffffU)return 10;}
 else if(std::strcmp(result,"{5, -2147483649}")==0){if(!out.present||out.type!=5||out.variant!=2147483647U||out.subType!=7||out.seed!=0xffffffffU)return 11;}
 else if(std::strcmp(result,"{'9',300.0,10,77}")==0){if(!out.present||out.type!=9||out.variant!=300||out.subType!=10||out.seed!=77)return 12;}
 else if(std::strcmp(result,"{5,-1,-1,-1}")==0){if(!out.present||out.type!=5||out.variant!=0xffffffffU||out.subType!=0xffffffffU||out.seed!=0xffffffffU)return 9;}
 else {if(out.present||out.type!=5||out.variant!=100||out.subType!=7||out.seed!=0xffffffffU)return 7;}
 const auto again=LuaRuntime::DispatchPreEntitySpawn(5,100,7,pos,vel,Player(),0xffffffffU);
 if(LuaRuntime::TakeCallbackError()!=invalid||again.present!=out.present||again.type!=out.type||again.variant!=out.variant||again.subType!=out.subType||again.seed!=out.seed)return 15;
 if(!Counter("tail",&n)||n!=(tailRuns?2:0))return 16;
 if(!Counter("first",&n)||n!=2||!Counter("last",&n)||n!=(firstStops?0:2))return 17;
 bool unused=false;static_cast<void>(Flag("unused",&unused));static_cast<void>(Collider());
 return 0;
}
'''
class PreEntitySpawnTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-pre-spawn-')
  cls.binary=build_lua_harness(source_root=SOURCE,workdir=Path(cls.tmp.name),harness_source='#include <string>\n'+HARNESS[:HARNESS.index('int main(')]+MAIN)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_first_non_nil_table_partial_fields_and_error_recovery(self):
  for value in ('discarded_meta','late_mutation','{9,300,10,77}','{nil,400}','{}','nil','false',"{5, 'bad'}", "{5,-1,-1,-1}", "{5, -2147483649}", "{5, 4294967296}", "{5, 1.5}", "{'9',300.0,10,77}", "setmetatable({}, {__index=function(_, i) return ({9,300,10,77})[i] end})", "setmetatable({}, {__index=function() error('index failure') end})"):
   with self.subTest(value=value):
    r=subprocess.run([str(self.binary),value],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
