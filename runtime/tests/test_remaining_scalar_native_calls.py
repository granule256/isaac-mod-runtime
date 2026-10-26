"""十九项公开实体方法真实解析及原生调用参数合约。

只在手写AsFunction最终目标处替换宿主函数；共享数据行保留生产跳板解析。
目标偏移冻结自NS原件，不读取生产字段表产生期望。这里不证明引擎内部游戏效果。
RemoveCollectible缺省来自固定PC resources/scripts/main.lua:844..850，非在线Rep+文档。
"""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from . import test_lua_entity_player as fixture
from . import test_support

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'runtime/source'
EVIDENCE = ROOT / 'dist/api-remaining-recovery-20261025'
# 固定NS动态符号偏移；PC owner见pc-fields-player-expanded.json，基类见Entity.md。
METHODS = (
    ('EntityPlayer:AddCoins', 0x280068, None),
    ('EntityPlayer:AddKeys', 0x2804e8, None),
    ('EntityPlayer:AddCard', 0x2b0b78, None),
    ('EntityPlayer:AddGoldenKey', 0x280588, None),
    ('EntityPlayer:AddGoldenBomb', 0x2fc3f0, None),
    ('EntityPlayer:RemoveCollectible', 0x299b50, None),
    ('EntityPlayer:AddBoneHearts', 0x27e380, 'EntityPlayerAddBoneHeartsFn'),
    ('EntityPlayer:AddGoldenHearts', 0x2fc924, 'EntityPlayerAddGoldenHeartsFn'),
    ('EntityPlayer:AddPrettyFly', 0x2f6db0, 'EntityPlayerAddPrettyFlyFn'),
    ('EntityPlayer:DonateLuck', 0x2f9978, 'EntityPlayerDonateLuckFn'),
    ('EntityPlayer:AddFriendlyDip', 0x2f62dc, 'EntityPlayerAddFriendlyDipFn'),
    ('EntityPlayer:AddBlueFlies', 0x27fc18, 'AddBlueFliesFn'),
    ('EntityPlayer:AddBlueSpider', 0x2fb40c, 'EntityPlayerAddBlueSpiderFn'),
    ('EntityPlayer:DropTrinket', 0x2a20d4, 'EntityPlayerDropTrinketFn'),
    ('Entity:AddCharmed', 0x5ebe8, 'EntityAddCharmedFn'),
    ('Entity:AddFear', 0x5f660, 'EntityAddFearFn'),
    ('Entity:AddFreeze', 0x5e358, 'EntityAddFreezeFn'),
    ('Entity:AddHealth', 0x5a248, 'EntityAddHealthFn'),
    ('Entity:AddPoison', 0x5e5f8, 'EntityAddPoisonFn'),
)

MOCKS = r'''
#include <cstdint>
extern "C" void ScalarTarget(std::uintptr_t);
extern "C" void ScalarVoid(std::uintptr_t);
extern "C" void ScalarInt(std::uintptr_t,std::int32_t);
extern "C" void ScalarFloat(std::uintptr_t,float);
extern "C" void ScalarRef(std::uintptr_t,const void*,std::int32_t,float);
extern "C" std::uintptr_t ScalarVector(std::uintptr_t,std::int32_t,float,float,std::uintptr_t);
extern "C" void ScalarDrop(std::uintptr_t,float,float,bool);
template<class F>struct ScalarMock;
template<>struct ScalarMock<void(*)(std::uintptr_t)>{static void Call(std::uintptr_t s){ScalarVoid(s);}};
template<>struct ScalarMock<void(*)(std::uintptr_t,std::int32_t)>{static void Call(std::uintptr_t s,std::int32_t v){ScalarInt(s,v);}};
template<>struct ScalarMock<void(*)(std::uintptr_t,float)>{static void Call(std::uintptr_t s,float v){ScalarFloat(s,v);}};
template<>struct ScalarMock<void(*)(std::uintptr_t,const void*,std::int32_t)>{static void Call(std::uintptr_t s,const void*r,std::int32_t v){ScalarRef(s,r,v,0);}};
template<>struct ScalarMock<void(*)(std::uintptr_t,const void*,std::int32_t,float)>{static void Call(std::uintptr_t s,const void*r,std::int32_t v,float f){ScalarRef(s,r,v,f);}};
template<class V>struct ScalarMock<std::uintptr_t(*)(std::uintptr_t,const V*)>{static std::uintptr_t Call(std::uintptr_t s,const V*v){return ScalarVector(s,0,v->x,v->y,0);}};
template<class V>struct ScalarMock<std::uintptr_t(*)(std::uintptr_t,std::int32_t,const V*)>{static std::uintptr_t Call(std::uintptr_t s,std::int32_t n,const V*v){return ScalarVector(s,n,v->x,v->y,0);}};
template<class V>struct ScalarMock<std::uintptr_t(*)(std::uintptr_t,std::int32_t,const V*,void*)>{static std::uintptr_t Call(std::uintptr_t s,std::int32_t n,const V*v,void*t){return ScalarVector(s,n,v->x,v->y,reinterpret_cast<std::uintptr_t>(t));}};
template<class V>struct ScalarMock<void(*)(std::uintptr_t,const V*,bool)>{static void Call(std::uintptr_t s,const V*v,bool b){ScalarDrop(s,v->x,v->y,b);}};
template<class F>F ScalarHost(std::uintptr_t target){ScalarTarget(target);return &ScalarMock<F>::Call;}
'''
MAIN = r'''
#include "interfaces/lua/entity_lifetime.hpp"
#include <cstdlib>
namespace LuaRuntime {void InstallScalarProbes();}
extern "C" {
#include <lauxlib.h>
extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;
extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];
}
static const unsigned offsets[]={FROZEN_OFFSETS};
static unsigned directCalls{},beforeDirect{},beforeShared{};
static std::uintptr_t target{},receiver{},targetEntity{};
static std::uint32_t ints[4]{};static float number{},vx{},vy{};static bool boolValue{},nullReturn{};
static std::vector<unsigned char> resultEntity;
static void ResetRecord(std::uintptr_t self){++directCalls;receiver=self;for(auto&v:ints)v=0;number=0;vx=vy=0;boolValue=false;targetEntity=0;}
extern "C" void ScalarTarget(std::uintptr_t t){target=t;}
extern "C" void ScalarVoid(std::uintptr_t s){ResetRecord(s);}
extern "C" void ScalarInt(std::uintptr_t s,std::int32_t n){ResetRecord(s);ints[0]=static_cast<std::uint32_t>(n);}
extern "C" void ScalarFloat(std::uintptr_t s,float n){ResetRecord(s);number=n;}
extern "C" void ScalarRef(std::uintptr_t s,const void*r,std::int32_t n,float f){
 ResetRecord(s);ints[0]=static_cast<std::uint32_t>(n);number=f;
 if(!r)std::abort();std::uint32_t type{},variant{};std::uintptr_t entity{};
 // EntityRef NS原生布局：Type0、Variant4、Entity28；生产EntityRefBufferAt保持完整缓冲。
 std::memcpy(&type,r,4);std::memcpy(&variant,static_cast<const char*>(r)+4,4);std::memcpy(&entity,static_cast<const char*>(r)+0x28,8);
 if(type!=1||variant!=0||entity!=AddressOf(g_PlayerBytes))std::abort();
}
extern "C" std::uintptr_t ScalarVector(std::uintptr_t s,std::int32_t n,float x,float y,std::uintptr_t t){ResetRecord(s);ints[0]=static_cast<std::uint32_t>(n);vx=x;vy=y;targetEntity=t;return nullReturn?0:AddressOf(resultEntity);}
extern "C" void ScalarDrop(std::uintptr_t s,float x,float y,bool b){ResetRecord(s);vx=x;vy=y;boolValue=b;}
static int BeginScalar(lua_State*){beforeDirect=directCalls;beforeShared=g_HostEngineCallTrampolineCalls;return 0;}
static int NoScalar(lua_State*L){if(beforeDirect!=directCalls||beforeShared!=g_HostEngineCallTrampolineCalls)return luaL_error(L,"invalid/stale/guard call reached native");return 0;}
static int NullScalar(lua_State*L){nullReturn=lua_toboolean(L,1)!=0;return 0;}
static int RetireScalar(lua_State*){isaac::runtime::RetireEntityLifetime(AddressOf(resultEntity));return 0;}
static int CheckScalar(lua_State*L){
 const int index=static_cast<int>(luaL_checkinteger(L,1));if(index<0||index>=19)return luaL_error(L,"bad test index");
 if(index<6){
  if(g_HostEngineCallTrampolineCalls!=beforeShared+1||directCalls!=beforeDirect)return luaL_error(L,"shared native count");
  if(g_HostEngineCallTrampolineLastTarget!=g_EngineBase+offsets[index]||g_HostEngineCallTrampolineLastIntegers[0]!=AddressOf(g_PlayerBytes))return luaL_error(L,"shared target/receiver");
  const unsigned count=index==5?4U:(index<3?1U:0U);
  for(unsigned i=0;i<count;++i)if(static_cast<std::uint32_t>(g_HostEngineCallTrampolineLastIntegers[i+1])!=static_cast<std::uint32_t>(luaL_checkinteger(L,static_cast<int>(i)+2)))return luaL_error(L,"integer/bool/default mismatch at register %d",i+1);
 }else{
  if(directCalls!=beforeDirect+1||g_HostEngineCallTrampolineCalls!=beforeShared)return luaL_error(L,"direct native count");
  if(target!=g_EngineBase+offsets[index]||receiver!=AddressOf(g_PlayerBytes))return luaL_error(L,"direct target/receiver");
  if(index==6||index==7||index==9||index==10||index==11||index==14||index==15||index==16||index==18){if(ints[0]!=static_cast<std::uint32_t>(luaL_checkinteger(L,2)))return luaL_error(L,"direct int32 mismatch");}
  if(index==17||index==18){if(number!=static_cast<float>(luaL_checknumber(L,index==17?2:3)))return luaL_error(L,"direct float mismatch");}
  if(index>=10&&index<=13){if(vx!=3.25F||vy!=-7.5F)return luaL_error(L,"Vector ABI mismatch");}
  if(index==11&&targetEntity!=AddressOf(g_PlayerBytes))return luaL_error(L,"target Entity pointer mismatch");
  if(index==13&&boolValue!=(luaL_checkinteger(L,2)!=0))return luaL_error(L,"DropTrinket truth value mismatch");
 }
 return BeginScalar(L);
}
int main(int argc,char**argv){
 if(argc!=3)return 90;const unsigned index=static_cast<unsigned>(std::strtoul(argv[1],nullptr,10));if(index>=19)return 91;const std::string scene=argv[2];
 static_cast<void>(&CorruptVtable);static_cast<void>(&PublishNullCostumes);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&ExpectNumber);static_cast<void>(kScriptTemplate);
 CreateBlocks();FillPlayer(true);PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));WriteWord(g_OwnerSlotBytes,0,AddressOf(g_GameBytes));PublishPlayers({AddressOf(g_PlayerBytes)});
 resultEntity=g_PlayerBytes;WriteWord(resultEntity,0,g_EngineBase+kEntityFamiliarVtableOffset);WriteAt<std::uint32_t>(resultEntity,kEntityTypeOffset,3);
 const unsigned char guards[][16]={FROZEN_GUARDS};for(unsigned i=0;i<19;++i)std::memcpy(g_ModuleBytes.data()+offsets[i],guards[i],16);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 const char* names[]={METHOD_NAMES};const char* valid[]={VALID_CALLS};const char* invalid[]={INVALID_CALLS};
 std::string body=scene=="valid"?valid[index]:scene=="invalid"?invalid[index]:"pcall(function() "+std::string(valid[index])+" end);NoScalar()";
 // guard/stale只运行一个合法参数调用，不能嵌入正向CheckScalar断言。
 if(scene=="guard"||scene=="stale"||scene=="wrong_vptr")body="pcall(function() p:"+std::string(names[index])+"("+std::string(FIRST_ARGUMENTS[index])+") end);NoScalar()";
 std::string script="local p=Isaac.GetPlayer();assert(p);local r=EntityRef(p);local v=Vector(3.25,-7.5);local m=RegisterMod('scalar native contract',1);m:AddCallback(1,function() BeginScalar();"+body+";_scalar_done={ok=1} end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@scalar-native.lua")!=LuaRuntime::LuaInitResult::Success){char e[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::puts(e);return 1;}
 LuaRuntime::InstallScalarProbes();
 if(scene=="guard")g_ModuleBytes[offsets[index]]^=1;
 if(scene=="stale")isaac::runtime::RetireEntityLifetime(AddressOf(g_PlayerBytes));
 if(scene=="wrong_vptr")WriteWord(g_PlayerBytes,0,0xdeadbeef);
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){char e[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::puts(e);return 2;}
 double done{};if(!LuaRuntime::ReadLuaTableNumber("_scalar_done","ok",&done)||done!=1)return 3;
 if(scene=="valid"&&directCalls+g_HostEngineCallTrampolineCalls==0)return 4;
 return 0;
}
'''


def _cases():
    """期望值来自固定PC签名/引导脚本，显式写出，不读取生产行。"""
    valid, invalid, first = [], [], []
    for index, (key, _, _) in enumerate(METHODS):
        name = key.split(':')[1]
        call = lambda args: f"p:{name}({args})"
        first.append('')
        if index in (0, 1, 2, 6, 7, 9):
            first[-1] = '-7'
            valid.append(';'.join(f"assert(select('#',{call(arg)})==0);CheckScalar({index},{want})"
                                  for arg, want in (('-7', -7), ('0x100000002', 2), ("'4294967294'", -2))))
            bad = ('', 'nil', 'false', '{}', '1.5')
        elif index in (3, 4, 8):
            valid.append(f"assert(select('#',{call('')})==0);CheckScalar({index})")
            bad = ('1',)
        elif index == 5:
            first[-1] = '77'
            # PC main.lua:850: activeSlot or 0; removeFromPlayerForm ~= false。
            valid.append(';'.join(f"assert(select('#',{call(args)})==0);CheckScalar(5,{expected})" for args, expected in (
                ('77', '77,0,0,1'),
                ('0x100000002,true,-1,false', '2,1,-1,0'),
                ('77,false,0,nil', '77,0,0,1'),
                ('77,0,0,0', '77,1,0,1'),
                ('77,nil,false,false', '77,0,0,0'),
            )))
            bad = ('', 'nil', '{}', '1.5', '77,false,{}')
        elif index in (10, 11, 12):
            first[-1] = '0x100000002,v' if index == 10 else '0x100000002,v,p' if index == 11 else 'v'
            # PC AddFriendlyDip wrapper84b206取registry key c066ef，与Familiar字段wrapper859cde相同。
            typed = "assert(getmetatable(e).__class==getmetatable(e:ToFamiliar()).__class,'AddFriendlyDip must return EntityFamiliar directly');" if index == 10 else ''
            count = '' if index == 12 else ',2'
            args = first[-1]
            valid.append(f"local e={call(args)};assert(type(e)=='userdata' and e.Type==3 and e:ToFamiliar()~=nil);{typed}CheckScalar({index}{count});"
                         f"NullScalar(true);assert({call(args)}==nil);CheckScalar({index}{count});NullScalar(false);"
                         "RetireScalar();assert(e.Type==nil)")
            bad = ('', '{}', '2,{}') if index == 10 else ('', '2,{},p', '2,v,{}', '1.5,v,p') if index == 11 else ('', '{}')
        elif index == 13:
            first[-1] = 'v,false'
            valid.append(';'.join(f"assert(select('#',{call('v,'+arg)})==0);CheckScalar(13,{want})"
                                  for arg, want in (('false', 0), ('nil', 0), ('0', 1), ('{}', 1), ("''", 1))))
            bad = ('', 'v', '{},false')
        elif index in (14, 15, 16, 18):
            suffix = ",'2.625'" if index == 18 else ''
            first[-1] = 'r,-7'+suffix
            valid.append(';'.join(f"assert(select('#',{call('r,'+arg+suffix)})==0);CheckScalar({index},{want}"+
                                  (',2.625)' if index == 18 else ')')
                                  for arg, want in (('-7', -7), ('0x100000002', 2), ("'4294967294'", -2))))
            bad = ('', 'r', '{} ,2'+suffix, 'r,1.5'+suffix, 'r,{}'+suffix)
            if index == 18:
                bad += ('r,2,{}', 'r,2,false')
        else:
            first[-1] = "'-2.625'"
            valid.append("assert(select('#',p:AddHealth('-2.625'))==0);CheckScalar(17,-2.625)")
            bad = ('', '{}', 'false', "'bad'")
        invalid.append(';'.join(f"assert(not pcall(function(){call(args)} end));NoScalar()" for args in bad) +
                       f";assert(not pcall(p.{name},{{}}" + (','+first[-1] if first[-1] else '') + "));NoScalar()")
    return valid, invalid, first


def _snapshot(paths):
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths if path.is_file()}


class RemainingScalarNativeCalls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='remaining-scalar-native-')
        cls.addClassCleanup(cls.tmp.cleanup)
        work = Path(cls.tmp.name)
        # 当前工作区缺少巨大原始游戏目录时使用项目主目录的同一固定原件，仅只读。
        original = Path('/Users/kelinls/code/github/isaac mod')
        nro_candidates = tuple(ROOT.glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro'))
        if not nro_candidates:
            nro_candidates = tuple(original.glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro'))
        if not nro_candidates:
            raise AssertionError('缺少独立NS原件Repentance.nro，不能伪造入口守卫')
        nro_path = nro_candidates[0]
        nro = nro_path.read_bytes()
        valid, invalid, first = _cases()
        quote = lambda s: json.dumps(s, ensure_ascii=True)
        cpp = MAIN.replace('FROZEN_OFFSETS', ','.join(hex(offset) for _, offset, _ in METHODS))
        cpp = cpp.replace('FROZEN_GUARDS', ','.join('{'+','.join(map(str, nro[offset:offset+16]))+'}' for _, offset, _ in METHODS))
        cpp = cpp.replace('METHOD_NAMES', ','.join(quote(key.split(':')[1]) for key, _, _ in METHODS))
        cpp = cpp.replace('INVALID_CALLS', ','.join(map(quote, invalid)))
        cpp = cpp.replace('VALID_CALLS', ','.join(map(quote, valid)))
        cpp = cpp.replace('int main(int argc,char**argv){', 'static const char* FIRST_ARGUMENTS[]={'+','.join(map(quote, first))+'};\nint main(int argc,char**argv){')
        cpp = cpp.replace('!LuaRuntime::ReadLuaTableNumber("_scalar_done","ok",&done)', 'LuaRuntime::ReadLuaTableNumber("_scalar_done","ok",&done)!=0')
        sources = list(test_support.layered_lua_runtime_sources(SOURCE))
        # 冻结编译输入和所有运行时头：运行结束逐项核同，防止并行生产改动污染结果。
        cls.production_paths = tuple(sorted(set(sources) | set((ROOT/'runtime/src').rglob('*.hpp')) | set(SOURCE.rglob('*.hpp'))))
        cls.before = _snapshot(cls.production_paths)
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE/'delegated-scalar-input-before.json').write_text(json.dumps(cls.before, indent=2)+'\n')
        cls.addClassCleanup(cls._check_stable_inputs)
        api = ROOT/'runtime/src/interfaces/lua/isaac_api.cpp'
        api_code = api.read_text()
        for _, _, alias in METHODS:
            if alias:
                old = f'engine_call::AsFunction<{alias}>'
                if api_code.count(old) != 1:
                    raise AssertionError(f'最终调用点数量发生变化: {alias}')
                api_code = api_code.replace(old, f'ScalarHost<{alias}>')
        instrumented = work/'instrumented_isaac_api.cpp'
        instrumented.write_text(MOCKS+api_code)
        runtime = SOURCE/'lua_runtime.cpp'
        instrumented_runtime = work/'instrumented_lua_runtime.cpp'
        instrumented_runtime.write_text(runtime.read_text()+r'''
int BeginScalar(lua_State*);int NoScalar(lua_State*);int CheckScalar(lua_State*);int NullScalar(lua_State*);int RetireScalar(lua_State*);
namespace LuaRuntime {void InstallScalarProbes(){
#define B(n) lua_pushcfunction(g_LuaState,::n);lua_setglobal(g_LuaState,#n)
B(BeginScalar);B(NoScalar);B(CheckScalar);B(NullScalar);B(RetireScalar);
#undef B
}}
''')
        # Probe函数须拥有外部链接，仅安装额外观测函数，不替换公开注册/解析。
        cpp = cpp.replace('static int BeginScalar', 'int BeginScalar').replace('static int NoScalar', 'int NoScalar').replace('static int CheckScalar', 'int CheckScalar').replace('static int NullScalar', 'int NullScalar').replace('static int RetireScalar', 'int RetireScalar')
        replacement = [instrumented if path == api else instrumented_runtime if path == runtime else path for path in sources]
        flags = tuple(flag for flag in test_support.HARNESS_COMPILE_FLAGS if not flag.startswith('-DEXL_DIAGNOSTIC_STAGE='))
        source = fixture.HARNESS[:fixture.HARNESS.index('int main(')] + cpp
        (EVIDENCE/'delegated-scalar-harness.cpp').write_text(source)
        with mock.patch.object(test_support, 'layered_lua_runtime_sources', return_value=replacement), mock.patch.object(test_support, 'HARNESS_COMPILE_FLAGS', flags):
            cls.binary = test_support.build_lua_harness(source_root=SOURCE, workdir=work, harness_source=source)

    @classmethod
    def _check_stable_inputs(cls):
        after = _snapshot(cls.production_paths)
        (EVIDENCE/'delegated-scalar-input-after.json').write_text(json.dumps(after, indent=2)+'\n')
        changed = sorted(key for key in set(cls.before) | set(after) if cls.before.get(key) != after.get(key))
        if changed:
            raise AssertionError('运行期间生产输入发生变化，结果不能归属同一版本: '+str(changed))

    def test_all_public_methods_native_contracts(self):
        for index, (key, _, _) in enumerate(METHODS):
            for scene in ('valid', 'invalid', 'guard', 'stale', 'wrong_vptr'):
                with self.subTest(key=key, scene=scene):
                    result = subprocess.run([str(self.binary), str(index), scene], capture_output=True, text=True)
                    print(f'{key} {scene}: exit={result.returncode} {result.stdout}{result.stderr}', flush=True)
                    self.assertEqual(result.returncode, 0, result.stdout+result.stderr)


    def test_remove_collectible_pc_bootstrap_defaults(self):
        result = subprocess.run([str(self.binary), '5', 'valid'], capture_output=True, text=True)
        print(f'EntityPlayer:RemoveCollectible valid: exit={result.returncode} {result.stdout}{result.stderr}', flush=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_add_friendly_dip_pc_direct_familiar_type(self):
        result = subprocess.run([str(self.binary), '10', 'valid'], capture_output=True, text=True)
        print(f'EntityPlayer:AddFriendlyDip valid: exit={result.returncode} {result.stdout}{result.stderr}', flush=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
