"""固定PC颜色乘法修改左操作数，返回强持原颜色的借用引用。"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_lua_entity_player as fixture
from .test_support import build_lua_harness

MAIN = r'''
static std::vector<void*> multiplySprites;
static void MultiplySpriteCtor(void* self) {
    multiplySprites.push_back(self);
    std::memset(self,0,0x158);
}
static void MultiplySpriteDtor(void*) {}
int main() {
    static_cast<void>(&CorruptVtable);static_cast<void>(&PublishNullCostumes);
    static_cast<void>(&HarnessHasCollectible);static_cast<void>(&ExpectNumber);
    static_cast<void>(kScriptTemplate);
    CreateBlocks();FillPlayer(true);PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));
    WriteWord(g_OwnerSlotBytes,0,AddressOf(g_GameBytes));
    PublishPlayers({AddressOf(g_PlayerBytes)});LuaRuntime::SetEngineModuleBase(g_EngineBase);
    LuaRuntime::LuaSpriteBindings bindings{};
    bindings.ctor=MultiplySpriteCtor;bindings.destructor_=MultiplySpriteDtor;
    LuaRuntime::SetSpriteBindings(bindings);
    const char* script=R"lua(
local mod=RegisterMod('color-multiply',1)
mod:AddCallback(1,function()
 local function near(a,b) assert(math.abs(a-b)<.00001,tostring(a)..' ~= '..tostring(b)) end
 local a=Color(.5,.25,1,.75,.1,.2,.3);a:SetColorize(.2,.4,.6,.8)
 local b=Color(.25,.5,.5,.5,.4,.5,.6);b:SetColorize(.6,.8,1,1)
 local c=a*b
 near(c.R,.125);near(c.G,.125);near(c.B,.5);near(c.A,.375)
 near(c.RO,.5);near(c.GO,.7);near(c.BO,.9)
 near(a.R,c.R);near(b.R,.25)
 assert(not rawequal(a,c),'PC returns a borrowed userdata, not the owning userdata')
 a.R=.7;near(c.R,.7);c.G=.8;near(a.G,.8)
 local d=c:__mul(Color(1,1,1,1));near(d.R,.7);near(d.G,.8)
 a=nil;c=nil;collectgarbage('collect');near(d.R,.7)
 local lerp=Color.Lerp(d,d,.5);near(lerp.RO,.5)
 d.R=.125;d.G=.125
 local s=Sprite();s.Color=d;_multiplySprite=s
 local copied=Color(1,1,1,1)*b
 local copySprite=Sprite();copySprite.Color=copied;_multiplyCopySprite=copySprite
 local ignored=Color(1,1,1,1);ignored:SetColorize(.2,.4,.6,.8)
 local cancelling=Color(1,1,1,1);cancelling:SetColorize(-.5,.5,0,99)
 local ignoreSprite=Sprite();ignoreSprite.Color=ignored*cancelling;_multiplyIgnoreSprite=ignoreSprite
 local leftZero=Color(1,1,1,1);leftZero:SetColorize(-.5,.5,0,99)
 local replaceSprite=Sprite();replaceSprite.Color=leftZero*b;_multiplyReplaceSprite=replaceSprite
 local z=Color(1,1,1,1);local ref=z*Color(1,1,1,1)
 ref:SetColorize(.2,.4,.6,.8)
 ref=ref*ref
 near(ref.R,1);near(ref.RO,0)
 collectgarbage('collect');local before=collectgarbage('count')
 for i=1,2000 do ref=ref*Color(1,1,1,1) end
 collectgarbage('collect');assert(collectgarbage('count')-before<4,'borrowed wrappers retain a growing ownership chain')
 ref.R=.25;near(z.R,.25)
 _multiplyOk=1
end)
)lua";
    auto result=LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@color-multiply.lua");
    if(result!=LuaRuntime::LuaInitResult::Success)return 1;
    LuaRuntime::DispatchPostUpdate();
    if(LuaRuntime::TakeCallbackError()) {
        char error[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
        std::printf("%s\n",error);return 2;
    }
    if(!ExpectNumber("_multiplyOk",1))return 3;
    const float expected[4][11]={
        {.125f,.125f,.5f,.375f,.4f,.6f,.8f,.9f,.5f,.7f,.9f},
        {.25f,.5f,.5f,.5f,.6f,.8f,1,1,.4f,.5f,.6f},
        {1,1,1,1,.2f,.4f,.6f,.8f,0,0,0},
        {.25f,.5f,.5f,.5f,.6f,.8f,1,1,.4f,.5f,.6f},
    };
    if(multiplySprites.size()!=4)return 4;
    for(unsigned s=0;s<4;++s) {
        float actual[11];std::memcpy(actual,static_cast<char*>(multiplySprites[s])+0xe8,sizeof(actual));
        for(unsigned i=0;i<11;++i)if(std::abs(actual[i]-expected[s][i])>.00001f)return 10+i;
    }
    return 0;
}
'''


class ColorMultiplyTests(unittest.TestCase):
    def test_pc_left_mutation_borrowed_lifetime_and_native_consumer(self):
        with tempfile.TemporaryDirectory(prefix="color-multiply-") as work:
            source = fixture.HARNESS[:fixture.HARNESS.index("int main(")] + MAIN
            source = re.sub(r"namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}",
                            "", source, count=1)
            binary = build_lua_harness(source_root=fixture.SOURCE, workdir=Path(work),
                                       harness_source=source)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
