"""REPENTOGON listener errors and return validation against main_ex.lua."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_support
from .test_repentogon_callbacks import RUNTIME_DRIVER, POLICY_DRIVER, SOURCE
from . import test_repentogon_callbacks as callbacks

CASES = r'''
    if(mode=="legacy_alias") {
        script+="assert(ModCallbacks.MC_HUD_POST_UPDATE==1021 and ModCallbacks.MC_HUD_POST_UPDATE==ModCallbacks.MC_POST_HUD_UPDATE);m:AddCallback(ModCallbacks.MC_HUD_POST_UPDATE,function()calls=calls+1 end)";
    }else if(mode=="pre_true"||mode=="pre_false"||mode=="pre_nil") {
        script+="m:AddCallback(1026,function()return "+mode.substr(4)+" end)";
    }else if(mode=="listener_error"||mode=="manual_error") {
        script+=R"lua(
m:AddCallback(1020,function()error('first listener failed')end)
m:AddCallback(1020,function()calls=calls+1 end)
)lua";
        if(mode=="manual_error")script+="assert(Isaac.RunCallback(1020)==nil);assert(calls==1)";
    }else if(mode=="bool_invalid"||mode=="manual_bool_invalid") {
        script+=R"lua(
m:AddCallback(1026,function()return 'not boolean' end)
m:AddCallback(1026,function()calls=calls+1;return true end)
m:AddCallback(1026,function()error('valid boolean must stop')end)
)lua";
        if(mode=="manual_bool_invalid")script+="assert(Isaac.RunCallback(1026)==true and calls==1)";
    }else if(mode=="vector_invalid"||mode=="manual_vector_invalid") {
        script+=R"lua(
m:AddCallback(1080,function()return RNG()end,7)
m:AddCallback(1080,function(_,e,v)calls=calls+1;assert(v.X==10);return Vector(1,2)end,7)
m:AddCallback(1080,function(_,e,v)calls=calls+1;assert(v.X==11 and v.Y==22);return Vector(2,3)end,7)
)lua";
        if(mode=="manual_vector_invalid")script+="local v=Isaac.RunCallbackWithParam(1080,7,{},Vector(10,20));assert(v.X==13 and v.Y==25 and calls==2)";
    }else if(mode=="sound_invalid"||mode=="manual_sound_invalid") {
        script+=R"lua(
m:AddCallback(1030,function()return {8,0.25,3,'bad loop',1.5,-0.5}end,5)
m:AddCallback(1030,function()calls=calls+1;return {8,0.25,3,true,1.5,-0.5}end,5)
m:AddCallback(1030,function()error('valid sound table must stop')end,5)
)lua";
        if(mode=="manual_sound_invalid")script+="local v=Isaac.RunCallbackWithParam(1030,5,5,0.5,2,false,1,0);assert(v[1]==8 and v[4]==true and calls==1)";
    }else if(mode=="sound_abi") {
        script+="m:AddCallback(1030,function()return {5,0.5,4294967297,false,1,0}end,5)";
    }else if(mode=="grid_userdata") {
        script+="m:AddCallback(1444,function()return RNG()end,4);m:AddCallback(1444,function()calls=calls+1 end,4)";
    }else if(mode=="sound_partial") {
        script+="m:AddCallback(1030,function()return {8}end,5);m:AddCallback(1030,function()error('valid partial table must stop')end,5)";
    }else if(mode=="grid_untyped"||mode=="update_untyped") {
        const auto id=mode=="grid_untyped"?1400:1160;
        const auto filter=mode=="grid_untyped"?4:7;
        script+="m:AddCallback("+std::to_string(id)+",function()return 'upstream does not type-check this ID' end,"+std::to_string(filter)+")";
        script+=";m:AddCallback("+std::to_string(id)+",function()error('untyped nonnil still stops')end,"+std::to_string(filter)+")";
    }else
'''
CHECKS = r'''
        if(mode=="legacy_alias") {
            send(1021);Check();assert(Number("calls")==1&&ExtendedCallbackCount()==106);
        }else if(mode=="pre_true"||mode=="pre_false"||mode=="pre_nil") {
            const auto r=send(1026);assert(r.hasBoolean==(mode!="pre_nil"));
            if(r.hasBoolean)assert(r.boolean==(mode=="pre_true"));Check();
        }else if(mode=="listener_error"||mode=="bool_invalid"||mode=="vector_invalid"||mode=="sound_invalid"||mode.rfind("manual_",0)==0) {
            unsigned id=1020;
            if(mode.find("bool_invalid")!=std::string::npos)id=1026;
            if(mode.find("vector_invalid")!=std::string::npos)id=1080;
            if(mode.find("sound_invalid")!=std::string::npos)id=1030;
            if(mode.rfind("manual_",0)!=0) {
                const auto r=send(id,id==1080?EventKind::EntityRender:id==1030?EventKind::Sound:EventKind::Global);
                if(id==1026)assert(r.hasBoolean&&r.boolean);
                if(id==1080)assert(r.hasOffset&&r.offset.x==13&&r.offset.y==25);
                if(id==1030)assert(sound.id==8&&sound.loop&&sound.pan==-0.5f);
            }
            assert(Number("calls")==unsigned(id==1080?2:1));assert(LuaRuntime::TakeCallbackError());
            LuaRuntime::LuaErrorHistoryEntryView errors[8]{};const auto count=LuaRuntime::CopyLuaErrorHistory(errors,8);
            assert(count==1&&errors[0].owner!=0&&errors[0].callbackId==id);
        }else if(mode=="sound_abi") {
            send(1030,EventKind::Sound);assert(sound.delay==1);Check();
        }else if(mode=="grid_userdata") {
            const auto r=send(1444,EventKind::GridRender);assert(!r.hasOffset&&!r.hasBoolean&&Number("calls")==0);
            assert(LuaRuntime::TakeCallbackError());LuaRuntime::LuaErrorHistoryEntryView errors[8]{};
            assert(LuaRuntime::CopyLuaErrorHistory(errors,8)==1&&errors[0].owner!=0&&errors[0].callbackId==1444);
        }else if(mode=="sound_partial") {
            send(1030,EventKind::Sound);assert(sound.id==5&&Number("calls")==0);Check();
        }else if(mode=="grid_untyped"||mode=="update_untyped") {
            const auto r=send(mode=="grid_untyped"?1400:1160,mode=="grid_untyped"?EventKind::Grid:EventKind::Entity);
            assert(!r.hasBoolean&&!r.hasOffset);Check();
        }else
'''
REVIEW_DRIVER=RUNTIME_DRIVER.replace('    if(mode=="off"||mode=="none"){',CASES+'    if(mode=="off"||mode=="none"){',1)
REVIEW_DRIVER=REVIEW_DRIVER.replace('        if(mode=="catalog"){',CHECKS+'        if(mode=="catalog"){',1)

OFF_DRIVER=POLICY_DRIVER.replace('lua_pushnil(s);lua_pushcfunction(s,Yes);lua_call(s,6,5);lua_pop(s,5);',
 'lua_pushnil(s);lua_pushnil(s);lua_call(s,6,5);lua_pushvalue(s,-1);lua_setglobal(s,"nativeRunner");lua_pop(s,5);')
start=OFF_DRIVER.index('    Run(s,R"lua(')
end=OFF_DRIVER.index('    lua_close(s);',start)
OFF_DRIVER=OFF_DRIVER[:start]+r'''
    Run(s,R"lua(
local m={};local n=0
Isaac.AddPriorityCallback(m,1,0,function()n=n+1 end)
local oldtype=type;type=function()error('ordinary OFF dispatch called type()')end
Isaac.RunCallback(1);nativeRunner(1,nil);assert(n==2);type=oldtype
)lua");
'''+OFF_DRIVER[end:]

class RepentogonCallbackReviewTests(unittest.TestCase):
    def test_pre_update_and_listener_semantics(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-review-') as tmp:
            binary=test_support.build_lua_harness(source_root=SOURCE,workdir=Path(tmp),harness_source=REVIEW_DRIVER)
            for mode in ('legacy_alias','pre_true','pre_false','pre_nil','listener_error','manual_error','bool_invalid','manual_bool_invalid',
                         'vector_invalid','manual_vector_invalid','sound_invalid','manual_sound_invalid','grid_untyped','update_untyped','grid_userdata','sound_partial','sound_abi'):
                with self.subTest(mode=mode):
                    result=subprocess.run([str(binary),mode],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_off_ordinary_runner_does_not_call_type(self):
        callbacks.RepentogonCallbackTests._run_policy_driver(self,OFF_DRIVER)
