"""字体测宽缓存：真实Lua绑定及固定缓存边界。"""
import subprocess
import tempfile
import unittest
try:
    from .test_lua_font_resources import HARNESS, SOURCE
    from .test_support import build_lua_harness
except ImportError:
    from test_lua_font_resources import HARNESS, SOURCE
    from test_support import build_lua_harness

EXTRA = r'''
#include "interfaces/lua/font_api.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"
#include "interfaces/lua/font_width_cache.hpp"
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
static int Check(lua_State* L) {
 int expected=luaL_checkinteger(L,1);
 if(g_widthCalls!=expected) return luaL_error(L,"width calls: expected %d got %d",expected,g_widthCalls);
 return 0;
}
static int Rebind(lua_State* L) {
 LuaRuntime::LuaFontBindings b{};
 if(lua_toboolean(L,1)) { b.getStringWidth=&FakeGetStringWidthUTF8; b.getStringWidthUTF8=&FakeGetStringWidth; }
 else { b.getStringWidth=&FakeGetStringWidth; b.getStringWidthUTF8=&FakeGetStringWidthUTF8; }
 b.ctor=&FakeCtor;b.destructor_=&FakeDestructor;b.load=&FakeLoad;b.unload=&FakeUnload;
 b.isLoaded=&FakeIsLoaded;b.setMissingCharacter=&FakeSetMissingCharacter;
 LuaRuntime::SetFontBindings(b);return 0;
}
int main() {
 PublishFakeBindings();
 auto* L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,"string",luaopen_string,1);lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kFontMetatable);
 lua_pushvalue(L,-1);lua_setfield(L,-2,"__index");
 lua_pushcfunction(L,isaac::runtime::DestroyFontHandle);lua_setfield(L,-2,"__gc");
 (void)isaac::runtime::AttachFontMethods(L);lua_pop(L,1);
 lua_pushcfunction(L,isaac::runtime::CreateFontHandle);lua_setglobal(L,"Font");
 lua_pushcfunction(L,Check);lua_setglobal(L,"check");
 lua_pushcfunction(L,Rebind);lua_setglobal(L,"rebind");
 const char* s=R"lua(
 local f=Font();assert(f:Load('font/a.fnt'))
 assert(f:GetStringWidth('abc')==30);assert(f:GetStringWidth('abc')==30);check(1)
 assert(f:GetStringWidthUTF8('abc')==13);assert(f:GetStringWidthUTF8('abc')==13);check(2)
 local g=Font();assert(g:Load('font/a.fnt'));assert(g:GetStringWidth('abc')==30);check(3)
 f:SetMissingCharacter(1);assert(f:GetStringWidth('abc')==30);check(4)
 assert(f:Load('font/b.fnt'));assert(f:GetStringWidth('abc')==30);check(5)
 assert(not f:Load('font/b.fnt','bad'));assert(not pcall(f.GetStringWidth,f,'abc'));check(5)
 assert(f:Load('font/b.fnt'));assert(f:GetStringWidth('abc')==30);check(6)
 f:Unload();assert(not pcall(f.GetStringWidth,f,'abc'));assert(f:Load('font/a.fnt'))
 assert(f:GetStringWidth('abc')==30);check(7)
 rebind(true);assert(f:GetStringWidth('abc')==13);check(8)
 rebind(false);assert(f:GetStringWidth('abc')==30);check(9)
 assert(f:GetStringWidth('')==0);assert(f:GetStringWidth('')==0);check(10)
 assert(f:GetStringWidth('a\0b')==10);assert(f:GetStringWidth('a\0b')==10);check(11)
 assert(f:GetStringWidth(123)==30);assert(f:GetStringWidth(123)==30);check(12)
 local long=string.rep('a',129);assert(f:GetStringWidth(long)==1290);assert(f:GetStringWidth(long)==1290);check(14)
 getmetatable(f).__gc(f);assert(not pcall(f.GetStringWidth,f,'abc'));check(14)
 for i=1,100 do assert(g:GetStringWidth('value'..i)==#('value'..i)*10) end
 assert(g:GetStringWidth('abc')==30)
 )lua";
 if(luaL_dostring(L,s)!=LUA_OK){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}
 // 原生借用Font使用同一元表，但不能缓存（外部可改字体）。
 alignas(16) unsigned char storage[kFontObjectSize]{};
 FakeCtor(storage);FakeLoad(storage,"x",nullptr);
 std::uintptr_t game=reinterpret_cast<std::uintptr_t>(storage);
 std::uintptr_t slot=reinterpret_cast<std::uintptr_t>(&game);
 LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(&slot)-kGameOwnerGlobalSlotOffset);
 (void)isaac::runtime::PushBorrowedGameFont(L,game,0);lua_setglobal(L,"borrowed");
 g_widthCalls=0;
 if(luaL_dostring(L,"assert(borrowed:GetStringWidth('abc')==30);assert(borrowed:GetStringWidth('abc')==30);check(2)")!=LUA_OK)return 4;
 // 相同函数地址重新发布绑定也必须失效。
 g_widthCalls=0;
 if(luaL_dostring(L,"saved=Font();saved:Load('x');assert(saved:GetStringWidth('same')==40);check(1)")!=LUA_OK)return 5;
 g_widthBias=7;PublishFakeBindings();
 if(luaL_dostring(L,"assert(saved:GetStringWidth('same')==47);check(2);local s=string.rep('x',128);assert(saved:GetStringWidthUTF8(s)==513);assert(saved:GetStringWidthUTF8(s)==513);check(3)")!=LUA_OK)return 15;
 g_widthBias=0;
 LuaRuntime::SetFontBindings({});
 if(luaL_dostring(L,"assert(not pcall(saved.GetStringWidth,saved,'same'));check(3)")!=LUA_OK)return 14;
 PublishFakeBindings();
 using Cache=isaac::runtime::FontWidthCache;
 Cache cache{};Cache::Key key{L,L,storage,1,1,false};
 char text[4]={'a','b','c','\0'};int width=0;
 cache.Insert(key,text,3,30);if(!cache.Find(key,text,3,&width)||width!=30)return 6;
 text[0]='z';if(cache.Find(key,text,3,&width))return 7;
 for(int i=0;i<5;++i){text[0]=static_cast<char>('a'+i);cache.Insert(key,text,3,i);}
 text[0]='a';if(cache.Find(key,text,3,&width))return 8;
 text[0]='e';if(!cache.Find(key,text,3,&width)||width!=4)return 9;
 auto other=key;other.state=storage;if(cache.Find(other,text,3,&width))return 10;
 other=key;other.owner=storage;if(cache.Find(other,text,3,&width))return 11;
 other=key;other.generation=2;if(cache.Find(other,text,3,&width))return 12;
 cache.Invalidate(L,L);if(cache.Find(key,text,3,&width))return 13;
 std::printf("cache_bytes=%zu entry_bytes=%zu\n",sizeof(Cache),sizeof(Cache::Entry));
 lua_close(L);return 0;
}
'''

class FontWidthCacheTests(unittest.TestCase):
    def test_real_lua_width_cache(self):
        source = HARNESS.split('const char* kUnavailableScript')[0] + '\n} // namespace\n'
        source = source.replace('int g_ctorCalls = 0;', 'int g_widthCalls = 0;\nint g_widthBias = 0;\nint g_ctorCalls = 0;')
        source = source.replace('std::strlen(text)) * 10;', 'std::strlen(text)) * 10 + g_widthBias;')
        source = source.replace('int FakeGetStringWidth(const void* font, const char* text) {', 'int FakeGetStringWidth(const void* font, const char* text) {\n ++g_widthCalls;')
        source = source.replace('int FakeGetStringWidthUTF8(const void* font, const char* text) {', 'int FakeGetStringWidthUTF8(const void* font, const char* text) {\n ++g_widthCalls;')
        for token in ('RESOURCES','GC','CALLBACK','DRAW'):
            source=source.replace('@'+token+'_SCRIPT@','')
        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path
            binary=build_lua_harness(source_root=SOURCE,workdir=Path(tmp),harness_source=source+EXTRA)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
