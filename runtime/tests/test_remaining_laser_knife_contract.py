"""Laser/Knife 剩余字段真实注册合约；宿主内存证据，不外推真机引擎。

固定数值由既有独立 NS 原件逐项抄录，不读取生产字段表生成期望。
SOURCE_LEDGER 仅供审查；执行时使用下面冻结的显式写入和断言。
未证明的四项明确排除，不能因返回 nil 计为通过。
"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness

# source.file 相对于 dist/apis400-20261016/，与该目录 field-proof-matrix.json
# 中 ns_accesses.file 的证据根一致；不是相对于本测试文件或 runtime/src/。
SOURCE_LEDGER = {'EntityLaser:ParentOffset': {'offset': '0x400',
                              'type': 'Vector',
                              'source': {'file': 'entity35/ns-Entity_Laser-Entity_Laser-f59b4.txt',
                                         'instruction': '000f59d4  91100260  add        x0, x19, '
                                                        '#0x400'}},
 'EntityLaser:StartAngleDegrees': {'offset': '0x408',
                                   'type': 'Float',
                                   'source': {'file': 'entity35/ns-Entity_Laser-Init-f7640.txt',
                                              'instruction': '000f76c4  f902067f  str        xzr, '
                                                             '[x19, #0x408]'}},
 'EntityLaser:AngleDegrees': {'offset': '0x40c',
                              'type': 'Float',
                              'source': {'file': 'entity35/ns-Entity_Laser-init_laser-f81fc.txt',
                                         'instruction': '000f822c  b9440e68  ldr        w8, [x19, '
                                                        '#0x40c]'}},
 'EntityLaser:LastAngleDegrees': {'offset': '0x410',
                                  'type': 'Float',
                                  'source': {'file': 'entity35/ns-Entity_Laser-Init-f7640.txt',
                                             'instruction': '000f76c8  b904127f  str        wzr, '
                                                            '[x19, #0x410]'}},
 'EntityLaser:Timeout': {'offset': '0x448',
                         'type': 'Int',
                         'source': {'file': 'entity35/ns-Entity_Laser-Init-f7640.txt',
                                    'instruction': '000f76e8  b9044a7f  str        wzr, [x19, '
                                                   '#0x448]'}},
 'EntityLaser:FirstUpdate': {'offset': '0x44c',
                             'type': 'Bool',
                             'source': {'file': 'entity35/ns-Entity_Laser-Init-f7640.txt',
                                        'instruction': '000f76a8  39113268  strb       w8, [x19, '
                                                       '#0x44c]'}},
 'EntityLaser:LaserLength': {'offset': '0x450',
                             'type': 'Float',
                             'source': {'file': 'entity35/ns-Entity_Laser-Init-f7640.txt',
                                        'instruction': '000f76fc  b904527f  str        wzr, [x19, '
                                                       '#0x450]'}},
 'EntityLaser:Radius': {'offset': '0x4e4',
                        'type': 'Float',
                        'source': {'file': 'entity35/ns-Entity_Laser-Init-f7640.txt',
                                   'instruction': '000f76f4  b904e668  str        w8, [x19, '
                                                  '#0x4e4]'}},
 'EntityLaser:IsActiveRotating': {'offset': '0x4e8',
                                  'type': 'Bool',
                                  'source': {'file': 'entity35/ns-Entity_Laser-Init-f7640.txt',
                                             'instruction': '000f7704  3913a27f  strb       wzr, '
                                                            '[x19, #0x4e8]'}},
 'EntityLaser:RotationDelay': {'offset': '0x4ec',
                               'type': 'UInt',
                               'source': {'file': 'entity35/ns-Entity_Laser-SetActiveRotation-f7540.txt',
                                          'instruction': '000f7548  b904ec01  str        w1, [x0, '
                                                         '#0x4ec]'}},
 'EntityLaser:RotationDegrees': {'offset': '0x4f0',
                                 'type': 'Float',
                                 'source': {'file': 'entity35/ns-Entity_Laser-SetActiveRotation-f7540.txt',
                                            'instruction': '000f754c  bd04f000  str        s0, '
                                                           '[x0, #0x4f0]'}},
 'EntityLaser:RotationSpd': {'offset': '0x4f4',
                             'type': 'Float',
                             'source': {'file': 'entity35/ns-Entity_Laser-SetActiveRotation-f7540.txt',
                                        'instruction': '000f7550  bd04f401  str        s1, [x0, '
                                                       '#0x4f4]'}},
 'EntityLaser:MaxDistance': {'offset': '0x4f8',
                             'type': 'Float',
                             'source': {'file': 'entity35/ns-Entity_Laser-Init-f7640.txt',
                                        'instruction': '000f7708  f9027e7f  str        xzr, [x19, '
                                                       '#0x4f8]'}},
 'EntityLaser:EndPoint': {'offset': '0x500',
                          'type': 'Vector',
                          'source': {'file': 'entity35/ns-Entity_Laser-Entity_Laser-f59b4.txt',
                                     'instruction': '000f5a00  91140260  add        x0, x19, '
                                                    '#0x500'}},
 'EntityLaser:DisableFollowParent': {'offset': '0x50c',
                                     'type': 'Bool',
                                     'source': {'file': 'entity35/ns-Entity_Laser-Init-f7640.txt',
                                                'instruction': '000f770c  3914327f  strb       '
                                                               'wzr, [x19, #0x50c]'}},
 'EntityLaser:BlackHpDropChance': {'offset': '0x524',
                                   'type': 'Float',
                                   'source': {'file': 'entity35/ns-Entity_Laser-Init-f7640.txt',
                                              'instruction': '000f7748  b905267f  str        wzr, '
                                                             '[x19, #0x524]'}},
 'EntityLaser:OneHit': {'offset': '0x561',
                        'type': 'Bool',
                        'source': {'file': 'entity35/ns-Entity_Laser-damage-ff994.txt',
                                   'instruction': '000ffa08  39558668  ldrb       w8, [x19, '
                                                  '#0x561]'}},
 'EntityLaser:GridHit': {'offset': '0x562',
                         'type': 'Bool',
                         'source': {'file': 'entity35/ns-Entity_Laser-update_circle_laser-f8c80.txt',
                                    'instruction': '000f9704  39158a7f  strb       wzr, [x19, '
                                                   '#0x562]'}},
 'EntityKnife:Scale': {'offset': '0x420',
                       'type': 'Float',
                       'source': {'file': 'entity35/ns-Entity_Knife-Init-eaa9c.txt',
                                  'instruction': '000eabe0  b9042268  str        w8, [x19, '
                                                 '#0x420]'}},
 'EntityKnife:RotationOffset': {'offset': '0x42c',
                                'type': 'Float',
                                'source': {'file': 'entity35/ns-Entity_Knife-Update-eb964.txt',
                                           'instruction': '000ecc60  bd442e61  ldr        s1, '
                                                          '[x19, #0x42c]'}},
 'EntityKnife:MaxDistance': {'offset': '0x44c',
                             'type': 'Float',
                             'source': {'file': 'entity35/ns-Entity_Knife-Init-eaa9c.txt',
                                        'instruction': '000eabe4  91113268  add        x8, x19, '
                                                       '#0x44c'}},
 'EntityKnife:Charge': {'offset': '0x450',
                        'type': 'Float',
                        'source': {'file': 'entity35/ns-Entity_Knife-Shoot-f4c58.txt',
                                   'instruction': '000f4d14  bd045260  str        s0, [x19, '
                                                  '#0x450]'}},
 'EntityKnife:PathOffset': {'offset': '0x4e8',
                            'type': 'Float',
                            'source': {'file': 'entity35/ns-Entity_Knife-Init-eaa9c.txt',
                                       'instruction': '000eac64  bd04ea60  str        s0, [x19, '
                                                      '#0x4e8]'}},
 'EntityKnife:PathFollowSpeed': {'offset': '0x4ec',
                                 'type': 'Float',
                                 'source': {'file': 'entity35/ns-Entity_Knife-Init-eaa9c.txt',
                                            'instruction': '000eac44  9113b268  add        x8, '
                                                           'x19, #0x4ec'}},
 'EntityLaser:BounceLaser': {'offset': '0x510',
                             'type': 'Entity',
                             'source': {'file': 'entity35/ns-Entity_Laser-Init-f7640.txt',
                                        'instruction': '000f7710  f9028a7f  str        xzr, [x19, '
                                                       '#0x510]'}}}
BASELINE_UNRESOLVED = {
    "EntityKnife:Rotation": "当前公开字段实现无入口，不能把 GetRotation 方法当属性；尚无独立 NS offset 证据",
    "EntityLaser:CurveStrength": "api_catalog.cpp 明确未证明候选，尚无独立 NS offset 证据",
    "EntityLaser:HomingLaser": "当前公开字段实现无入口，尚无独立 NS offset 证据",
    "EntityLaser:HomingType": "只有 SetHomingType 方法消费 +0x4fc，不证明同名属性存在",
}
# 首轮候选信息保留；两项由独立红/绿回归补齐，不计入本文件29字段。
COVERED_BY_SEPARATE_REGRESSION = {
    "EntityKnife:Rotation": "test_missing_laser_knife_properties.py：真实Knife类PC访问器与NS FromAngle消费",
    "EntityLaser:HomingType": "test_missing_laser_knife_properties.py：PC直接成员与NS SetHomingType/Update消费",
}
UNRESOLVED = {key: value for key, value in BASELINE_UNRESOLVED.items()
              if key not in COVERED_BY_SEPARATE_REGRESSION}
# 旗标原件：dist/callback-rplus-20261013（runtime/source/runtime_constants.hpp:9013）。
SOURCE_LEDGER.update({
    "EntityKnife:TearFlags": {"offset": "0x400", "type": "BitSet128", "source": "callback-rplus-20261013 PC getter/setter 与 NS 消费者"},
    "EntityLaser:TearFlags": {"offset": "0x418", "type": "BitSet128", "source": "callback-rplus-20261013 PC getter/setter 与 NS 消费者"},
    "EntityLaser:Angle": {"offset": "0x40c", "type": "Float/native setter", "source": "Entity_Laser::SetAngle 0xf5f38, api600_game.cpp kNatives[6] 完整16字节指纹"},
    "EntityLaser:SampleLaser": {"offset": "0x44d", "type": "Bool", "source": "Entity_Laser::Init 0xf76b4, api600_game.cpp kFields[1] 完整16字节指纹"},
})

MAIN = r'''
#include "interfaces/lua/api400_fields.guards.hpp"
#include "interfaces/lua/api600_game.hpp"
#include "interfaces/lua/bitset128_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "lua_object_handles.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
using Vec=LuaRuntime::VectorHandle;
static unsigned angleCalls=0;
static void Angle(void* self,float value){
 assert(self==g_Entities[kNoQuery].data());++angleCalls;
 // 实际入口消费者已由 NS SetAngle 0xf5f38 指纹限定；这里只核 ABI/receiver/value。
 assert(value==-37.25F);WriteAt<float>(g_Entities[kNoQuery],0x40c,value);
}
static void Run(lua_State* L,const char* s){if(luaL_dostring(L,s)){
 std::fprintf(stderr,"%s\nScript: %s\n",lua_tostring(L,-1),s);std::abort();}}
template<class T>static void Change(lua_State* L,EntitySlot slot,const char* s,unsigned offset,T value){
 auto expected=g_Entities;WriteAt<T>(expected[slot],offset,value);Run(L,s);assert(expected==g_Entities);
}
static void Unchanged(lua_State* L,const char* s){auto before=g_Entities;Run(L,s);assert(before==g_Entities);}
int main(){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);
 static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();
 FillEntity(kNoQuery,7,0,2,0,0,0,0,0,g_EngineBase+kEntityLaserVtableOffset,0);
 FillEntity(kSizeOnly,8,0,0,0,0,0,0,0,g_EngineBase+kEntityKnifeVtableOffset,0);
 PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);
 LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 namespace F=api400_fields;
 std::memcpy(g_ModuleBytes.data()+F::kLaserEntry,F::kLaserGuard.data(),16);
 std::memcpy(g_ModuleBytes.data()+F::kKnifeEntry,F::kKnifeGuard.data(),16);
 const unsigned char angleGuard[]={0x1,0x1,0x27,0x1e,0x0,0x8,0x4,0xbd,0x0,0x28,0x21,0x1e,0x0,0x34,0x1,0xbd};
 const unsigned char sampleGuard[]={0x68,0x36,0x11,0x91,0xe9,0x1f,0x80,0x52,0x74,0xa,0x5,0xb9,0x60,0x62,0x11,0x91};
 std::memcpy(g_ModuleBytes.data()+0xf5f38,angleGuard,16);
 std::memcpy(g_ModuleBytes.data()+0xf76b4,sampleGuard,16);
 Api600GameNativeTestBindings native{};native.methods[6]=engine_call::AddressOfFunction(&Angle);SetApi600GameNativeTestBindings(native);
 for(auto slot:{kNoQuery,kSizeOnly})for(unsigned i=0x400;i<0x580;++i)g_Entities[slot][i]=static_cast<unsigned char>(0xa1+(i%31));
 auto* L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
 luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);
 assert(RegisterIsaacApi(L));RegisterBitSet128Api(L);
 // 仅注册通用 Vector 基础设施，与既有原生缓冲夹具一致；不补挂任何待测字段/方法。
 RegisterVectorReferenceMetatable(L);luaL_newmetatable(L,LuaRuntime::kVectorMetatable);
 lua_pushcfunction(L,VectorIndex);lua_setfield(L,-2,"__index");
 lua_pushcfunction(L,VectorNewIndex);lua_setfield(L,-2,"__newindex");
 lua_newtable(L);static_cast<void>(AttachVectorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
 lua_pushcfunction(L,CreateVectorHandle);lua_setglobal(L,"Vector");
 PushEntityCallbackArgument(L,AddressOf(g_Entities[kNoQuery]));lua_setglobal(L,"laser");
 PushEntityCallbackArgument(L,AddressOf(g_Entities[kSizeOnly]));lua_setglobal(L,"knife");
 PushEntityCallbackArgument(L,AddressOf(g_Entities[kEnemyA]));lua_setglobal(L,"target");
 // EntityLaser:ParentOffset: entity35/ns-Entity_Laser-Entity_Laser-f59b4.txt / 000f59d4  91100260  add        x0, x19, #0x400
 WriteAt<Vec>(g_Entities[kNoQuery],0x400,Vec{13.25F,-17.5F});
 Unchanged(L,"assert(type(laser.ParentOffset)=='userdata');local c=laser.ParentOffset;assert(c.X==13.25 and c.Y==-17.5);c.X=99;assert(laser.ParentOffset.X==13.25);savedParentOffset=c");
 Change<Vec>(L,kNoQuery,"laser.ParentOffset=Vector(-3.5,7.25);assert(laser.ParentOffset.X==-3.5 and laser.ParentOffset.Y==7.25)",0x400,Vec{-3.5F,7.25F});
 Unchanged(L,"assert(not pcall(function()laser.ParentOffset={X=1,Y=2}end))");
 // EntityLaser:StartAngleDegrees: entity35/ns-Entity_Laser-Init-f7640.txt / 000f76c4  f902067f  str        xzr, [x19, #0x408]
 WriteAt<float>(g_Entities[kNoQuery],0x408,12.25);
 Unchanged(L,"assert(laser.StartAngleDegrees==12.25, 'EntityLaser:StartAngleDegrees native read')");
 Change<float>(L,kNoQuery,"laser.StartAngleDegrees=-37.25;assert(laser.StartAngleDegrees==-37.25)",0x408,-37.25);
 Unchanged(L,"assert(not pcall(function()laser.StartAngleDegrees={}end))");
 // EntityLaser:AngleDegrees: entity35/ns-Entity_Laser-init_laser-f81fc.txt / 000f822c  b9440e68  ldr        w8, [x19, #0x40c]
 WriteAt<float>(g_Entities[kNoQuery],0x40c,13.25);
 Unchanged(L,"assert(laser.AngleDegrees==13.25, 'EntityLaser:AngleDegrees native read')");
 Change<float>(L,kNoQuery,"laser.AngleDegrees=-37.25;assert(laser.AngleDegrees==-37.25)",0x40c,-37.25);
 Unchanged(L,"assert(not pcall(function()laser.AngleDegrees={}end))");
 // EntityLaser:LastAngleDegrees: entity35/ns-Entity_Laser-Init-f7640.txt / 000f76c8  b904127f  str        wzr, [x19, #0x410]
 WriteAt<float>(g_Entities[kNoQuery],0x410,14.25);
 Unchanged(L,"assert(laser.LastAngleDegrees==14.25, 'EntityLaser:LastAngleDegrees native read')");
 Change<float>(L,kNoQuery,"laser.LastAngleDegrees=-37.25;assert(laser.LastAngleDegrees==-37.25)",0x410,-37.25);
 Unchanged(L,"assert(not pcall(function()laser.LastAngleDegrees={}end))");
 // EntityLaser:Timeout: entity35/ns-Entity_Laser-Init-f7640.txt / 000f76e8  b9044a7f  str        wzr, [x19, #0x448]
 WriteAt<std::int32_t>(g_Entities[kNoQuery],0x448,105);
 Unchanged(L,"assert(laser.Timeout==105, 'EntityLaser:Timeout native read')");
 Change<std::int32_t>(L,kNoQuery,"laser.Timeout=-19;assert(laser.Timeout==-19)",0x448,-19);
 Unchanged(L,"assert(not pcall(function()laser.Timeout={}end));assert(not pcall(function()laser.Timeout=1.5 end))");
 // EntityLaser:FirstUpdate: entity35/ns-Entity_Laser-Init-f7640.txt / 000f76a8  39113268  strb       w8, [x19, #0x44c]
 WriteAt<std::uint8_t>(g_Entities[kNoQuery],0x44c,0x7d);
 Unchanged(L,"assert(laser.FirstUpdate==true,'EntityLaser:FirstUpdate')");
 Change<std::uint8_t>(L,kNoQuery,"laser.FirstUpdate=false;assert(laser.FirstUpdate==false)",0x44c,0);
 Change<std::uint8_t>(L,kNoQuery,"laser.FirstUpdate=0;assert(laser.FirstUpdate==true)",0x44c,1);
 // EntityLaser:LaserLength: entity35/ns-Entity_Laser-Init-f7640.txt / 000f76fc  b904527f  str        wzr, [x19, #0x450]
 WriteAt<float>(g_Entities[kNoQuery],0x450,17.25);
 Unchanged(L,"assert(laser.LaserLength==17.25, 'EntityLaser:LaserLength native read')");
 Change<float>(L,kNoQuery,"laser.LaserLength=-37.25;assert(laser.LaserLength==-37.25)",0x450,-37.25);
 Unchanged(L,"assert(not pcall(function()laser.LaserLength={}end))");
 // EntityLaser:Radius: entity35/ns-Entity_Laser-Init-f7640.txt / 000f76f4  b904e668  str        w8, [x19, #0x4e4]
 WriteAt<float>(g_Entities[kNoQuery],0x4e4,18.25);
 Unchanged(L,"assert(laser.Radius==18.25, 'EntityLaser:Radius native read')");
 Change<float>(L,kNoQuery,"laser.Radius=-37.25;assert(laser.Radius==-37.25)",0x4e4,-37.25);
 Unchanged(L,"assert(not pcall(function()laser.Radius={}end))");
 // EntityLaser:IsActiveRotating: entity35/ns-Entity_Laser-Init-f7640.txt / 000f7704  3913a27f  strb       wzr, [x19, #0x4e8]
 WriteAt<std::uint8_t>(g_Entities[kNoQuery],0x4e8,0x7d);
 Unchanged(L,"assert(laser.IsActiveRotating==true,'EntityLaser:IsActiveRotating')");
 Change<std::uint8_t>(L,kNoQuery,"laser.IsActiveRotating=false;assert(laser.IsActiveRotating==false)",0x4e8,0);
 Change<std::uint8_t>(L,kNoQuery,"laser.IsActiveRotating=0;assert(laser.IsActiveRotating==true)",0x4e8,1);
 // EntityLaser:RotationDelay: entity35/ns-Entity_Laser-SetActiveRotation-f7540.txt / 000f7548  b904ec01  str        w1, [x0, #0x4ec]
 WriteAt<std::uint32_t>(g_Entities[kNoQuery],0x4ec,110);
 Unchanged(L,"assert(laser.RotationDelay==110, 'EntityLaser:RotationDelay native read')");
 Change<std::uint32_t>(L,kNoQuery,"laser.RotationDelay=4026531875;assert(laser.RotationDelay==4026531875)",0x4ec,4026531875);
 Unchanged(L,"assert(not pcall(function()laser.RotationDelay={}end));assert(not pcall(function()laser.RotationDelay=1.5 end))");
 // EntityLaser:RotationDegrees: entity35/ns-Entity_Laser-SetActiveRotation-f7540.txt / 000f754c  bd04f000  str        s0, [x0, #0x4f0]
 WriteAt<float>(g_Entities[kNoQuery],0x4f0,21.25);
 Unchanged(L,"assert(laser.RotationDegrees==21.25, 'EntityLaser:RotationDegrees native read')");
 Change<float>(L,kNoQuery,"laser.RotationDegrees=-37.25;assert(laser.RotationDegrees==-37.25)",0x4f0,-37.25);
 Unchanged(L,"assert(not pcall(function()laser.RotationDegrees={}end))");
 // EntityLaser:RotationSpd: entity35/ns-Entity_Laser-SetActiveRotation-f7540.txt / 000f7550  bd04f401  str        s1, [x0, #0x4f4]
 WriteAt<float>(g_Entities[kNoQuery],0x4f4,22.25);
 Unchanged(L,"assert(laser.RotationSpd==22.25, 'EntityLaser:RotationSpd native read')");
 Change<float>(L,kNoQuery,"laser.RotationSpd=-37.25;assert(laser.RotationSpd==-37.25)",0x4f4,-37.25);
 Unchanged(L,"assert(not pcall(function()laser.RotationSpd={}end))");
 // EntityLaser:MaxDistance: entity35/ns-Entity_Laser-Init-f7640.txt / 000f7708  f9027e7f  str        xzr, [x19, #0x4f8]
 WriteAt<float>(g_Entities[kNoQuery],0x4f8,23.25);
 Unchanged(L,"assert(laser.MaxDistance==23.25, 'EntityLaser:MaxDistance native read')");
 Change<float>(L,kNoQuery,"laser.MaxDistance=-37.25;assert(laser.MaxDistance==-37.25)",0x4f8,-37.25);
 Unchanged(L,"assert(not pcall(function()laser.MaxDistance={}end))");
 // EntityLaser:EndPoint: entity35/ns-Entity_Laser-Entity_Laser-f59b4.txt / 000f5a00  91140260  add        x0, x19, #0x500
 WriteAt<Vec>(g_Entities[kNoQuery],0x500,Vec{13.25F,-17.5F});
 Unchanged(L,"assert(type(laser.EndPoint)=='userdata');local c=laser.EndPoint;assert(c.X==13.25 and c.Y==-17.5);c.X=99;assert(laser.EndPoint.X==13.25);savedEndPoint=c");
 Change<Vec>(L,kNoQuery,"laser.EndPoint=Vector(-3.5,7.25);assert(laser.EndPoint.X==-3.5 and laser.EndPoint.Y==7.25)",0x500,Vec{-3.5F,7.25F});
 Unchanged(L,"assert(not pcall(function()laser.EndPoint={X=1,Y=2}end))");
 // EntityLaser:DisableFollowParent: entity35/ns-Entity_Laser-Init-f7640.txt / 000f770c  3914327f  strb       wzr, [x19, #0x50c]
 WriteAt<std::uint8_t>(g_Entities[kNoQuery],0x50c,0x7d);
 Unchanged(L,"assert(laser.DisableFollowParent==true,'EntityLaser:DisableFollowParent')");
 Change<std::uint8_t>(L,kNoQuery,"laser.DisableFollowParent=false;assert(laser.DisableFollowParent==false)",0x50c,0);
 Change<std::uint8_t>(L,kNoQuery,"laser.DisableFollowParent=0;assert(laser.DisableFollowParent==true)",0x50c,1);
 // EntityLaser:BlackHpDropChance: entity35/ns-Entity_Laser-Init-f7640.txt / 000f7748  b905267f  str        wzr, [x19, #0x524]
 WriteAt<float>(g_Entities[kNoQuery],0x524,26.25);
 Unchanged(L,"assert(laser.BlackHpDropChance==26.25, 'EntityLaser:BlackHpDropChance native read')");
 Change<float>(L,kNoQuery,"laser.BlackHpDropChance=-37.25;assert(laser.BlackHpDropChance==-37.25)",0x524,-37.25);
 Unchanged(L,"assert(not pcall(function()laser.BlackHpDropChance={}end))");
 // EntityLaser:OneHit: entity35/ns-Entity_Laser-damage-ff994.txt / 000ffa08  39558668  ldrb       w8, [x19, #0x561]
 WriteAt<std::uint8_t>(g_Entities[kNoQuery],0x561,0x7d);
 Unchanged(L,"assert(laser.OneHit==true,'EntityLaser:OneHit')");
 Change<std::uint8_t>(L,kNoQuery,"laser.OneHit=false;assert(laser.OneHit==false)",0x561,0);
 Change<std::uint8_t>(L,kNoQuery,"laser.OneHit=0;assert(laser.OneHit==true)",0x561,1);
 // EntityLaser:GridHit: entity35/ns-Entity_Laser-update_circle_laser-f8c80.txt / 000f9704  39158a7f  strb       wzr, [x19, #0x562]
 WriteAt<std::uint8_t>(g_Entities[kNoQuery],0x562,0x7d);
 Unchanged(L,"assert(laser.GridHit==true,'EntityLaser:GridHit')");
 Change<std::uint8_t>(L,kNoQuery,"laser.GridHit=false;assert(laser.GridHit==false)",0x562,0);
 Change<std::uint8_t>(L,kNoQuery,"laser.GridHit=0;assert(laser.GridHit==true)",0x562,1);
 // EntityKnife:Scale: entity35/ns-Entity_Knife-Init-eaa9c.txt / 000eabe0  b9042268  str        w8, [x19, #0x420]
 WriteAt<float>(g_Entities[kSizeOnly],0x420,29.25);
 Unchanged(L,"assert(knife.Scale==29.25, 'EntityKnife:Scale native read')");
 Change<float>(L,kSizeOnly,"knife.Scale=-37.25;assert(knife.Scale==-37.25)",0x420,-37.25);
 Unchanged(L,"assert(not pcall(function()knife.Scale={}end))");
 // EntityKnife:RotationOffset: entity35/ns-Entity_Knife-Update-eb964.txt / 000ecc60  bd442e61  ldr        s1, [x19, #0x42c]
 WriteAt<float>(g_Entities[kSizeOnly],0x42c,30.25);
 Unchanged(L,"assert(knife.RotationOffset==30.25, 'EntityKnife:RotationOffset native read')");
 Change<float>(L,kSizeOnly,"knife.RotationOffset=-37.25;assert(knife.RotationOffset==-37.25)",0x42c,-37.25);
 Unchanged(L,"assert(not pcall(function()knife.RotationOffset={}end))");
 // EntityKnife:MaxDistance: entity35/ns-Entity_Knife-Init-eaa9c.txt / 000eabe4  91113268  add        x8, x19, #0x44c
 WriteAt<float>(g_Entities[kSizeOnly],0x44c,31.25);
 Unchanged(L,"assert(knife.MaxDistance==31.25, 'EntityKnife:MaxDistance native read')");
 Change<float>(L,kSizeOnly,"knife.MaxDistance=-37.25;assert(knife.MaxDistance==-37.25)",0x44c,-37.25);
 Unchanged(L,"assert(not pcall(function()knife.MaxDistance={}end))");
 // EntityKnife:Charge: entity35/ns-Entity_Knife-Shoot-f4c58.txt / 000f4d14  bd045260  str        s0, [x19, #0x450]
 WriteAt<float>(g_Entities[kSizeOnly],0x450,32.25);
 Unchanged(L,"assert(knife.Charge==32.25, 'EntityKnife:Charge native read')");
 Change<float>(L,kSizeOnly,"knife.Charge=-37.25;assert(knife.Charge==-37.25)",0x450,-37.25);
 Unchanged(L,"assert(not pcall(function()knife.Charge={}end))");
 // EntityKnife:PathOffset: entity35/ns-Entity_Knife-Init-eaa9c.txt / 000eac64  bd04ea60  str        s0, [x19, #0x4e8]
 WriteAt<float>(g_Entities[kSizeOnly],0x4e8,33.25);
 Unchanged(L,"assert(knife.PathOffset==33.25, 'EntityKnife:PathOffset native read')");
 Change<float>(L,kSizeOnly,"knife.PathOffset=-37.25;assert(knife.PathOffset==-37.25)",0x4e8,-37.25);
 Unchanged(L,"assert(not pcall(function()knife.PathOffset={}end))");
 // EntityKnife:PathFollowSpeed: entity35/ns-Entity_Knife-Init-eaa9c.txt / 000eac44  9113b268  add        x8, x19, #0x4ec
 WriteAt<float>(g_Entities[kSizeOnly],0x4ec,34.25);
 Unchanged(L,"assert(knife.PathFollowSpeed==34.25, 'EntityKnife:PathFollowSpeed native read')");
 Change<float>(L,kSizeOnly,"knife.PathFollowSpeed=-37.25;assert(knife.PathFollowSpeed==-37.25)",0x4ec,-37.25);
 Unchanged(L,"assert(not pcall(function()knife.PathFollowSpeed={}end))");
 // EntityLaser:BounceLaser: entity35/ns-Entity_Laser-Init-f7640.txt / 000f7710  f9028a7f  str        xzr, [x19, #0x510]
 WriteWord(g_Entities[kNoQuery],0x510,AddressOf(g_Entities[kEnemyA]));
 Unchanged(L,"assert(type(laser.BounceLaser)=='userdata');assert(GetPtrHash(laser.BounceLaser)==GetPtrHash(target));savedBounce=laser.BounceLaser");
 Change<std::uintptr_t>(L,kNoQuery,"laser.BounceLaser=nil;assert(laser.BounceLaser==nil)",0x510,0);
 Change<std::uintptr_t>(L,kNoQuery,"laser.BounceLaser=target",0x510,AddressOf(g_Entities[kEnemyA]));
 Unchanged(L,"assert(not pcall(function()laser.BounceLaser={}end))");

 // Angle 是原生 setter，而 AngleDegrees 是字段别名：getter 必须看到原生独立预置。
 WriteAt<float>(g_Entities[kNoQuery],0x40c,123.5F);
 Unchanged(L,"assert(laser.Angle==123.5 and laser.AngleDegrees==123.5)");
 Change<float>(L,kNoQuery,"laser.Angle=-37.25;assert(laser.AngleDegrees==-37.25)",0x40c,-37.25F);assert(angleCalls==1);
 Unchanged(L,"assert(not pcall(function()laser.Angle={}end))");assert(angleCalls==1);
 WriteAt<std::uint8_t>(g_Entities[kNoQuery],0x44d,0x71);
 Unchanged(L,"assert(laser.SampleLaser==true)");
 Change<std::uint8_t>(L,kNoQuery,"laser.SampleLaser=false;assert(laser.SampleLaser==false)",0x44d,0);
 Change<std::uint8_t>(L,kNoQuery,"laser.SampleLaser=0;assert(laser.SampleLaser==true)",0x44d,1);
 WriteAt<BitSet128Value>(g_Entities[kSizeOnly],0x400,BitSet128Value{0x8000000000000001ULL,0x4000000000000002ULL});
 Unchanged(L,"assert(type(knife.TearFlags)=='userdata');assert(knife.TearFlags==BitSet128(0x8000000000000001,0x4000000000000002));savedknifeFlags=knife.TearFlags");
 Change<BitSet128Value>(L,kSizeOnly,"knife.TearFlags=BitSet128(0x2000000000000003,0x8000000000000004);assert(knife.TearFlags==BitSet128(0x2000000000000003,0x8000000000000004))",0x400,BitSet128Value{0x2000000000000003ULL,0x8000000000000004ULL});
 Unchanged(L,"assert(savedknifeFlags==BitSet128(0x8000000000000001,0x4000000000000002));assert(not pcall(function()knife.TearFlags={low=1,high=2}end))");
 WriteAt<BitSet128Value>(g_Entities[kNoQuery],0x418,BitSet128Value{0x8000000000000001ULL,0x4000000000000002ULL});
 Unchanged(L,"assert(type(laser.TearFlags)=='userdata');assert(laser.TearFlags==BitSet128(0x8000000000000001,0x4000000000000002));savedlaserFlags=laser.TearFlags");
 Change<BitSet128Value>(L,kNoQuery,"laser.TearFlags=BitSet128(0x2000000000000003,0x8000000000000004);assert(laser.TearFlags==BitSet128(0x2000000000000003,0x8000000000000004))",0x418,BitSet128Value{0x2000000000000003ULL,0x8000000000000004ULL});
 Unchanged(L,"assert(savedlaserFlags==BitSet128(0x8000000000000001,0x4000000000000002));assert(not pcall(function()laser.TearFlags={low=1,high=2}end))");

 // 注册字段的每一个名字都必须遵守同一 owner 寿命边界，不能留下可写影子属性。
 // 这些名字是本合约冻结清单，不从生产表读取。
 Run(L,"laserNames={'Angle','AngleDegrees','BlackHpDropChance','BounceLaser','DisableFollowParent','EndPoint','FirstUpdate','GridHit','IsActiveRotating','LaserLength','LastAngleDegrees','MaxDistance','OneHit','ParentOffset','Radius','RotationDegrees','RotationDelay','RotationSpd','SampleLaser','StartAngleDegrees','TearFlags','Timeout'};knifeNames={'Charge','MaxDistance','PathFollowSpeed','PathOffset','RotationOffset','Scale','TearFlags'}");
 // 被引用对象退役后，不能继续给 BounceLaser 写入陈旧对象；旧引用也不能取字段。
 RetireEntityLifetime(AddressOf(g_Entities[kEnemyA]));
 Unchanged(L,"assert(savedBounce.Type==nil);assert(not pcall(function()laser.BounceLaser=target end))");
 RetireEntityLifetime(AddressOf(g_Entities[kNoQuery]));RetireEntityLifetime(AddressOf(g_Entities[kSizeOnly]));
 Unchanged(L,R"lua(
   for _,n in ipairs(laserNames) do assert(laser[n]==nil,n);laser[n]={} end
   for _,n in ipairs(knifeNames) do assert(knife[n]==nil,n);knife[n]={} end
   assert(laser.Angle==nil and laser.Timeout==nil and knife.Charge==nil)
   laser.Angle=11;laser.Timeout=99;knife.Charge=1;laser.TearFlags=BitSet128(1,2)
   assert(savedParentOffset.X==99 and savedEndPoint.X==99)
   assert(savedlaserFlags==BitSet128(0x8000000000000001,0x4000000000000002))
 )lua");assert(angleCalls==1);
 lua_close(L);return 0;
}
'''

class RemainingLaserKnifeContract(unittest.TestCase):
    def test_registered_fields_native_memory_neighbors_and_lifetime(self):
        prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
        prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '', prefix, count=1)
        with tempfile.TemporaryDirectory(prefix='remaining-laser-knife-') as d:
            binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=prefix+MAIN)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
