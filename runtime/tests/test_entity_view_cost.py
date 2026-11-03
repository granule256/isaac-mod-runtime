"""Query result views keep live type/vptr checks without classifying twice."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from .test_lua_api_method_lookup_cost import function

ROOT=Path(__file__).resolve().parents[2]

class EntityViewCostTests(unittest.TestCase):
 def test_real_query_view_keeps_cast_guards_with_one_identity_read(self):
  source=(ROOT/'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
  start=source.index('struct EntitySnapshot {')
  body=source[start:source.index('\nbool CaptureEntity',start)]
  start=source.index('constexpr std::uintptr_t kNonNpcEntityVtables[]')
  body+=source[start:source.index('};',start)+2]
  names=['bool IsTypedEntity(','bool CaptureEntityTypeSnapshot(',
         'bool IsNpcFamilyEntity(','CallbackEntityClass ClassifyCallbackEntity(',
         'const char* EntityViewMetatableForPointer(']
  if 'bool IsNpcFamilyVtable(' in source:names.insert(0,'bool IsNpcFamilyVtable(')
  body+='\n'.join(function(source,n) for n in names)
  prefix=r'''
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
constexpr unsigned kEntitySnapshotSpan=0x348,kEntityFlagsOffset=0x1b8,kEntityTypeOffset=0x38,kEntityVariantOffset=0x3c,kEntitySubTypeOffset=0x40;
constexpr unsigned kEntityBaseVtableOffset=16,kEntityBombVtableOffset=24,kEntityDummyVtableOffset=32,kEntityEffectVtableOffset=40,kEntityFamiliarVtableOffset=48,kEntityKnifeVtableOffset=56,kEntityLaserVtableOffset=64,kEntityPickupVtableOffset=72,kEntityPlayerVtableOffset=80,kEntityProjectileVtableOffset=88,kEntitySlotVtableOffset=96,kEntityTearVtableOffset=104,kEntityTextVtableOffset=112;
constexpr unsigned kEntityTypePlayer=1,kEntityTypePickup=5,kEntityTypeFamiliar=3,kEntityTypeTear=2,kEntityTypeProjectile=9,kEntityTypeLaser=7,kEntityTypeKnife=8,kEntityTypeEffect=1000,kEntityTypeBomb=4;
enum class CallbackEntityClass{None,Player,Pickup,Familiar,Tear,Projectile,Laser,Knife,Effect,Bomb,Npc};
constexpr const char*kEntityMetatable="base",*kEntityPlayerMetatable="player",*kEntityPickupMetatable="pickup",*kEntityLaserMetatable="laser",*kEntityProjectileMetatable="projectile",*kEntityKnifeMetatable="knife",*kEntityBombMetatable="bomb",*kEntityTearMetatable="tear",*kEntityNPCMetatable="npc";
std::array<unsigned char,0x348> entity{};bool readable=true;unsigned guards=0,reads=0;
std::uintptr_t EngineModuleBase(){return 0x1000;}
bool IsEnemyType(unsigned t){return t>=10&&t<1000;}
bool IsEntityVtableInRange(std::uintptr_t v){return v>=0x1010&&v<0x1080;}
bool IsEngineMemoryReadable(std::uintptr_t p,std::size_t){++guards;return readable&&p>=reinterpret_cast<std::uintptr_t>(entity.data())&&p<reinterpret_cast<std::uintptr_t>(entity.data()+entity.size());}
template<class T>bool ReadEngineUnchecked(std::uintptr_t p,T*out){++reads;std::memcpy(out,reinterpret_cast<void*>(p),sizeof(T));return true;}
template<class T>bool ReadEngine(std::uintptr_t p,T*out){return IsEngineMemoryReadable(p,sizeof(T))&&ReadEngineUnchecked(p,out);}
template<class T>void write(unsigned offset,T v){std::memcpy(entity.data()+offset,&v,sizeof(T));}
CallbackEntityClass ClassifyCallbackEntity(std::uintptr_t,std::int64_t* =nullptr) noexcept;
'''
  main=r'''
int main(){
 struct Case{unsigned type,offset;const char*view;};
 Case cases[]={{1,80,"player"},{5,72,"pickup"},{3,48,"base"},{9,88,"projectile"},{7,64,"laser"},{8,56,"knife"},{2,104,"tear"},{4,24,"bomb"},{180,120,"npc"},{1000,40,"base"},{6,96,"base"},{1,88,"base"},{9,120,"base"}};
 auto address=reinterpret_cast<std::uintptr_t>(entity.data());unsigned duplicate=0,unused=0;
 for(auto c:cases){
  write(0,std::uintptr_t(0x1000+c.offset));write(0x38,c.type);guards=reads=0;
  auto*name=EntityViewMetatableForPointer(address);
  if(std::strcmp(name,c.view)){std::fprintf(stderr,"type %u returned %s instead of %s",c.type,name,c.view);return 1;}
  if(guards>1)duplicate+=guards-1;if(reads>2)unused+=reads-2;
 }
 for(auto offset:kNonNpcEntityVtables){
  write(0,std::uintptr_t(0x1000+offset));write(0x38,unsigned(180));
  if(std::strcmp(EntityViewMetatableForPointer(address),"base"))return 2;
 }
 write(0,std::uintptr_t(0x1078));write(0x38,unsigned(180));
 if(std::strcmp(EntityViewMetatableForPointer(address),"npc"))return 3;
 write(0x38,unsigned(9));if(std::strcmp(EntityViewMetatableForPointer(address),"base"))return 4;
 write(0,std::uintptr_t(0x1058));if(std::strcmp(EntityViewMetatableForPointer(address),"projectile"))return 5;
 write(0,std::uintptr_t(9));if(std::strcmp(EntityViewMetatableForPointer(address),"base"))return 6;
 readable=false;if(std::strcmp(EntityViewMetatableForPointer(address),"base")||std::strcmp(EntityViewMetatableForPointer(0),"base"))return 7;
 if(duplicate||unused){std::fprintf(stderr,"query views repeated %u guards and read %u unused identity fields",duplicate,unused);return 8;}
}
'''
  with tempfile.TemporaryDirectory(prefix='entity-view-cost-')as tmp:
   work=Path(tmp);cpp=work/'check.cpp';cpp.write_text(prefix+body+main)
   result=subprocess.run(['c++','-std=c++17',str(cpp),'-o',str(work/'check')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   result=subprocess.run([str(work/'check')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
