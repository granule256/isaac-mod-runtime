"""真实生产 Lua 绑定读取玩家当前 libc++ 名字，及 BF 原脚本条件回归。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
    from .test_lua_batch312_coop_ghost import HARNESS as PLAYER_HARNESS, SOURCE
except ImportError:
    from test_support import build_lua_harness
    from test_lua_batch312_coop_ghost import HARNESS as PLAYER_HARNESS, SOURCE

# 原脚本未改的名字条件和服装调用；服装调用在此用 spy 捕获，画面由真机验证。
BF_NAME_CONDITION = '''if player:GetName() == "Template" then
        player:AddNullCostume(characterCostume)
    end'''

HARNESS = PLAYER_HARNESS.split('int main(int argc, char** argv) {', 1)[0] + r'''
#include <string>
void WriteName(std::vector<unsigned char>& block, const std::string& name, bool forceLong=false) {
    // 独立写死已取证的实体偏移，不引用生产常量来避免同错同过。
    constexpr std::size_t offset=0x1740;
    std::memset(block.data()+offset,0,24);
    if (!forceLong && name.size()<=22) {
        WriteAt<std::uint8_t>(block,offset,static_cast<std::uint8_t>(name.size()*2));
        std::memcpy(block.data()+offset+1,name.data(),name.size());
    } else {
        WriteAt<std::uint64_t>(block,offset,1);
        WriteAt<std::uint64_t>(block,offset+8,name.size());
        WriteAt<std::uintptr_t>(block,offset+16,reinterpret_cast<std::uintptr_t>(name.data()));
    }
}
int main(int argc, char** argv) {
    if(argc!=2) return 90;
    const std::string scenario=argv[1];
    PublishFakeGame(0,0);
    // 原生玩家类型仍为 0（配置名 Isaac），当前实体名 Template：配置查表会读错。
    const std::string playerName=scenario=="long" ? "CurrentEntityNameLongerThanInlineStorage_123456789" : scenario=="empty" ? "" : "Template";
    const std::string parentName="DifferentCurrentName";
    WriteName(g_PlayerBytes,playerName,scenario=="long");
    WriteName(g_ParentBytes,parentName);
    if(scenario=="invalid") {
        WriteAt<std::uint64_t>(g_ParentBytes,0,g_EngineBase+kEntityTearVtableOffset);
        WriteAt<std::uint32_t>(g_ParentBytes,kEntityTypeOffset,2);
    }
    if(scenario=="corrupt") {
        WriteAt<std::uint64_t>(g_PlayerBytes,0x1740,1);
        WriteAt<std::uint64_t>(g_PlayerBytes,0x1748,8);
        WriteAt<std::uint64_t>(g_PlayerBytes,0x1750,0);
    }
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
    std::string script=R"LUA(
local p=Isaac.GetPlayer(0)
local q=p.Parent
print('NAME kind='..type(p:GetName()))
print('NAME value='..tostring(p:GetName()))
print('NAME parent='..tostring(p.GetName(q)))
print('NAME playerType='..p:GetPlayerType())
print('NAME args='..tostring(pcall(function() return p:GetName(1) end)))
print('NAME badrecv='..tostring(pcall(function() return p.GetName({}) end)))
print('NAME dot='..tostring(pcall(function() return p.GetName(p) end)))
local called=0
local characterCostume=77
local player=setmetatable({}, {__index=function(_,key)
  if key=='GetName' then return function() return p:GetName() end end
  if key=='AddNullCostume' then return function(_,id) assert(id==77); called=called+1 end end
end})
)LUA";
    script += R"LUA(__BF_CONDITION__
print('NAME costumeCalls='..called)
)LUA";
    const auto result=LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@bf-name.lua");
    static_cast<void>(result);
    return 0;
}
'''.replace('__BF_CONDITION__', BF_NAME_CONDITION)


class EntityPlayerNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-player-name-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.binary=build_lua_harness(source_root=SOURCE,workdir=Path(cls.tmp.name)/'harness',harness_source=HARNESS)

    def scenario(self,name):
        result=subprocess.run([str(self.binary),name],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        output=result.stdout+result.stderr
        print(output,end='')
        return output

    def test_short_current_name_is_not_type_zero_config_name(self):
        out=self.scenario('short')
        self.assertIn('NAME playerType=0',out)
        self.assertIn('NAME kind=string',out)
        self.assertIn('NAME value=Template',out)
        self.assertIn('NAME parent=DifferentCurrentName',out)

    def test_long_string(self):
        self.assertIn('NAME value=CurrentEntityNameLongerThanInlineStorage_123456789',self.scenario('long'))

    def test_empty_string(self):
        out=self.scenario('empty')
        self.assertIn('NAME kind=string',out)
        self.assertIn('NAME value=\n',out)

    def test_invalid_player_returns_nil(self):
        self.assertIn('NAME parent=nil',self.scenario('invalid'))

    def test_malformed_long_string_returns_nil(self):
        self.assertIn('NAME value=nil',self.scenario('corrupt'))

    def test_existing_argument_and_receiver_gates(self):
        out=self.scenario('short')
        self.assertIn('NAME args=false',out)
        self.assertIn('NAME badrecv=false',out)
        self.assertIn('NAME dot=true',out)

    def test_original_bf_name_condition_calls_hair_costume(self):
        self.assertIn('NAME costumeCalls=1',self.scenario('short'))
        self.assertIn('NAME costumeCalls=0',self.scenario('long'))


if __name__=='__main__':
    unittest.main()
