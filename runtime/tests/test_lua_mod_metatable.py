"""PC Mod methods and owner identity survive a library replacing its metatable."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import build_lua_harness

SOURCE = Path(__file__).resolve().parents[1] / "source"
HARNESS = r'''
#include "lua_runtime.hpp"
#include "ports/save_file_port.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
class Store final: public isaac::runtime::ISaveFilePort {
    std::map<std::string,std::string> files;
public:
    isaac::runtime::Status Read(std::string_view n,char* out,std::size_t cap,std::size_t* size) noexcept override {
        const auto it=files.find(std::string(n));
        if(it==files.end())return isaac::runtime::Status{isaac::runtime::StatusCode::NotFound};
        *size=it->second.size();
        if(*size>cap)return isaac::runtime::Status{isaac::runtime::StatusCode::CapacityExceeded};
        std::memcpy(out,it->second.data(),*size);return isaac::runtime::Status::Ok();
    }
    isaac::runtime::Status Write(std::string_view n,std::string_view d) noexcept override {files[std::string(n)]=d;return isaac::runtime::Status::Ok();}
    isaac::runtime::Status Remove(std::string_view n) noexcept override {files.erase(std::string(n));return isaac::runtime::Status::Ok();}
    isaac::runtime::Status Exists(const char*n,bool* yes) noexcept override {*yes=files.count(n)!=0;return isaac::runtime::Status::Ok();}
    isaac::runtime::Status GetSaveSlot(unsigned* slot) noexcept override {*slot=1;return isaac::runtime::Status::Ok();}
};
int main() {
    Store store;isaac::runtime::SetSessionSaveFilePort(&store);
    const char* script=R"lua(
        local a=RegisterMod('CustomMetatable',1)
        local b=RegisterMod('NoMetatable',1)
        for _,name in ipairs({'AddCallback','AddPriorityCallback','RemoveCallback',
            'SaveData','LoadData','HasData','RemoveData'}) do
            assert(type(rawget(a,name))=='function',name..' is not a raw Mod field')
        end
        assert(rawget(a,'__handle')==nil)
        setmetatable(a,{__index=function(_,key)if key=='LazyClass'then return 42 end end})
        setmetatable(b,nil)
        collectgarbage('collect')
        assert(a.LazyClass==42)
        a:SaveData('first owner')
        b:SaveData('second owner')
        assert(a:HasData() and b:HasData())
        assert(a:LoadData()=='first owner' and b:LoadData()=='second owner')
        b:RemoveData()
        assert(not b:HasData() and a:LoadData()=='first owner')
        local called=0
        a:AddCallback('META_OWNER_CHECK',function(self)assert(self==a);called=called+1 end)
        b:AddPriorityCallback('META_OWNER_CHECK',-1,function(self)assert(self==b);called=called+1 end)
        Isaac.RunCallback('META_OWNER_CHECK')
        assert(called==2,'lost callbacks or owner identity')
        local entries=Isaac.GetCallbacks('META_OWNER_CHECK')
        assert(entries[1].Mod==b and entries[2].Mod==a)
        a:AddCallback(ModCallbacks.MC_POST_UPDATE,function()end)
        b:AddPriorityCallback(ModCallbacks.MC_POST_UPDATE,-1,function()end)
    )lua";
    const auto result=LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@mod-metatable.lua");
    char error[1024]{};(void)LuaRuntime::CopyLastLuaErrorText(error,sizeof(error));
    const auto count=LuaRuntime::RegisteredCallbackCount(1);
    std::printf("status=%u callbacks=%u error=%s\n",unsigned(result),count,error);
    return result==LuaRuntime::LuaInitResult::Success&&count==2?0:1;
}
'''
class ModMetatableTests(unittest.TestCase):
    def test_raw_methods_and_owners_survive_custom_or_removed_metatable(self):
        with tempfile.TemporaryDirectory(prefix="isaac-mod-metatable-") as temporary:
            binary=build_lua_harness(source_root=SOURCE,workdir=Path(temporary),
                                     harness_source=HARNESS)
            result=subprocess.run([str(binary)],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
