"""真实 EID 绘制片段：逐次检查原生 44B，偏移来自 PC/NS SetOffset 指令而非实现常量。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness

ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include "lua_runtime.hpp"
#include "interfaces/lua/engine_color_mod.hpp"
#include "interfaces/lua/color_api.hpp"
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <string>
using namespace isaac::runtime;
int calls = 0;
float offsets[3] = {1,1,1};
bool layerMode = true;
void Ctor(void* self) {
    std::memset(self, 0, 0x158);
    // 旧染色留下的非零值：Color(...) 整值赋回应清除它。
    float stale[4] = {.2f,.3f,.4f,.5f};
    std::memcpy(static_cast<char*>(self)+0xe8+0x10, stale, 16);
}
void Dtor(void*) {}
void Capture(void* self, const void* pos) {
    float raw[11];
    std::memcpy(raw, static_cast<char*>(self)+0xe8, sizeof(raw));
    float expected[11] = {1,1,1,1,0,0,0,0,0,0,0};
    if(calls < 4) for(int i=0;i<3;++i) expected[8+i]=offsets[i];
    if(std::memcmp(raw,expected,sizeof(raw))) {
        for(int i=0;i<11;++i) if(raw[i]!=expected[i])
            std::fprintf(stderr,"COLOR_OFFSET_FAIL draw=%d byte=+%02x got=%g expected=%g\n",calls,i*4,raw[i],expected[i]);
        std::exit(10);
    }
    const float expectedPos[5][2]={{10,21},{10,19},{11,20},{9,20},{10,20}};
    if(std::memcmp(pos, expectedPos[calls], 8)) std::exit(11);
    ++calls;
}
void Render(void* self,const void* p,const void*,const void*) {
    if(layerMode) std::exit(12); Capture(self,p);
}
void RenderLayer(void* self,int layer,const void* p,const void*,const void*) {
    if(!layerMode || layer!=1) std::exit(13); Capture(self,p);
}
int main(int argc,char** argv) {
    if(argc!=4 && argc!=5) return 90;
    bool border=argc==5;
    const int frame=std::atoi(argv[1]);
    const bool multi=std::atoi(argv[2]);
    layerMode=std::atoi(argv[3]);
    int c=border?255:255-static_cast<int>(255*((frame%40)/40.0));
    if(multi) { offsets[0]=int(c*.5)/255.f; offsets[1]=int(c*.75)/255.f; offsets[2]=c/255.f; }
    else for(float& v:offsets) v=c/255.f;
    if(std::strcmp(argv[1], "shared")==0) {
    // 共用映射写方向，独立字面布局：不能用结构字段自己证自己。
    lua_State* L=luaL_newstate();
    luaL_newmetatable(L,LuaRuntime::kColorMetatable); lua_pop(L,1);
    for(double v:{.25,.5,.75,1.,-.1,.2,.3}) lua_pushnumber(L,v);
    CreateColorHandle(L);
    EngineColorMod native{};
    if(!FillEngineColorMod(L,-1,&native)) return 20;
    const float expected[11]={.25,.5,.75,1,0,0,0,0,-.1f,.2f,.3f};
    if(std::memcmp(&native,expected,44)) { std::fprintf(stderr,"SHARED_OFFSET_WRITE_FAIL\n");return 21; }
    // 读方向：染色格和值偏移故意不同；读错格会失败。
    float source[11]={.1f,.2f,.3f,.4f,.9f,.8f,.7f,.6f,-.5f,.25f,.75f};
    std::memcpy(&native,source,44);
    PushLuaColorFromEngineColorMod(L,native);
    auto* handle=static_cast<LuaRuntime::ColorHandle*>(lua_touserdata(L,-1));
    if(handle->offsetRed!=-.5f || handle->offsetGreen!=.25f || handle->offsetBlue!=.75f) return 22;
    lua_close(L);
    std::puts("SHARED_COLOR_OK"); return 0;
    }
    LuaRuntime::LuaSpriteBindings bind{};
    bind.ctor=Ctor;bind.destructor_=Dtor;bind.render=Render;bind.renderLayer=RenderLayer;
    LuaRuntime::SetSpriteBindings(bind);
    std::string script="EID={Config={Indicator='highlight'},isRepentance=true,isMultiplayer=";
    script+=multi?"true}":"false}";
    if(border) script+=" EID.Config.Indicator='border' ";
    script+=R"lua(
nullVector=Vector(0,0)
Isaac.WorldToScreen=function(p) return p end
function EID:IsGridEntity(e) return false end
function EID:PlayersHaveCollectible(id) return false end
function EID:getEntityData(e,k) return nil end
@INDICATOR@
@ENTITY@
local sprite=Sprite()
local e={Type=5,Variant=@VARIANT@,FrameCount=@FRAME@,Position=Vector(10,20)}
function e:GetSprite() return sprite end
function e:ToPickup() return {IsShopItem=function() return false end} end
EID:renderIndicator(e,@PLAYER@)
print('EID_COLOR_OK')
RegisterMod('eid-offset-test',1):AddCallback(ModCallbacks.MC_POST_UPDATE,function() end)
)lua";
    auto result=LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@eid-real-highlight.lua");
    if(result!=LuaRuntime::LuaInitResult::Success || calls!=5) {
        LuaRuntime::LuaErrorHistoryEntryView errors[8]{};
        auto n=LuaRuntime::CopyLuaErrorHistory(errors,8);
        std::fprintf(stderr,"init=%d calls=%d errors=%zu\n",int(result),calls,n);
        for(size_t i=0;i<n;++i) std::fprintf(stderr,"%s\n",errors[i].text);
        return 30;
    }
    return 0;
}
'''

class EIDHighlightColorOffsetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='eid-highlight-offset-')
        fixtures=ROOT/'tools/test_fixtures/eid-highlight'
        src=HARNESS.replace('@INDICATOR@',(fixtures/'render-indicator.lua').read_text()).replace('@ENTITY@',(fixtures/'render-entity.lua').read_text())
        src=src.replace('@VARIANT@',')lua"+std::to_string(layerMode?100:10)+R"lua(').replace('@FRAME@',')lua"+std::to_string(frame)+R"lua(').replace('@PLAYER@',')lua"+std::to_string(multi?2:1)+R"lua(')
        cls.binary=build_lua_harness(source_root=ROOT/'runtime/source',workdir=Path(cls.temp.name),harness_source=src)
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    def test_actual_eid_edges_and_center_native_bytes(self):
        for frame,multi,layer in [(0,0,1),(20,0,1),(39,0,1),(20,1,1),(0,0,0)]:
            with self.subTest(frame=frame,multi=multi,layer=layer):
                result=subprocess.run([str(self.binary),str(frame),str(multi),str(layer)],text=True,capture_output=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('EID_COLOR_OK',result.stdout)

    def test_shared_mapping_both_directions(self):
        result=subprocess.run([str(self.binary),'shared','0','0'],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('SHARED_COLOR_OK',result.stdout)

    def test_actual_eid_border_ignores_blink_frame(self):
        result=subprocess.run([str(self.binary),'39','0','1','border'],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('EID_COLOR_OK',result.stdout)
