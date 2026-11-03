"""Classify production entity snapshots without reading unused spatial fields."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from .test_lua_api_method_lookup_cost import function

ROOT = Path(__file__).resolve().parents[2]


class EntityClassificationCostTests(unittest.TestCase):
    def test_class_and_callback_filter_follow_live_identity_only(self):
        source = (ROOT / 'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
        start = source.index('struct EntitySnapshot {')
        snapshot = source[start:source.index('\nbool CaptureEntity', start)]
        body = snapshot + '\n' + '\n'.join(function(source, name) for name in (
            'bool CaptureEntityTypeSnapshot(',
            'CallbackEntityClass ClassifyCallbackEntity(',
        ))
        prefix = r'''
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
constexpr unsigned kEntitySnapshotSpan=0x348,kEntityFlagsOffset=0x1b8,kEntityTypeOffset=0x38,
 kEntityVariantOffset=0x3c,kEntitySubTypeOffset=0x40,kEntityIndexOffset=0x30,
 kEntityPositionOffset=0x140,kEntitySizeOffset=0x340;
constexpr unsigned kEntityTypePlayer=1,kEntityTypePickup=5,kEntityTypeFamiliar=3,
 kEntityTypeTear=2,kEntityTypeProjectile=9,kEntityTypeLaser=7,kEntityTypeKnife=8,
 kEntityTypeEffect=1000,kEntityTypeBomb=4;
constexpr unsigned kEntityPlayerVtableOffset=16,kEntityPickupVtableOffset=24,kEntityFamiliarVtableOffset=32;
enum class CallbackEntityClass{None,Player,Pickup,Familiar,Tear,Projectile,Laser,Knife,Effect,Bomb,Npc};
std::array<unsigned char,kEntitySnapshotSpan> entity{};
bool readable=true;unsigned spatialReads{};
std::uintptr_t EngineModuleBase(){return 0x1000;}
bool IsEngineMemoryReadable(std::uintptr_t p,unsigned n){return readable&&p==reinterpret_cast<std::uintptr_t>(entity.data())&&n==entity.size();}
bool IsEntityVtableInRange(std::uintptr_t p){return p>=0x1000&&p<0x1100;}
bool IsEnemyType(unsigned type){return type>=10&&type<1000;}
template<class T>bool ReadEngineUnchecked(std::uintptr_t p,T* out){
 auto offset=p-reinterpret_cast<std::uintptr_t>(entity.data());
 if(offset==kEntityIndexOffset||offset==kEntityPositionOffset||offset==kEntityPositionOffset+4||offset==kEntitySizeOffset)++spatialReads;
 std::memcpy(out,reinterpret_cast<void*>(p),sizeof(T));return true;
}
template<class T>void write(unsigned offset,T value){std::memcpy(entity.data()+offset,&value,sizeof(T));}
'''
        main = r'''
int main(){
 struct Case{unsigned type,offset;CallbackEntityClass kind;};
 const Case cases[]={{1,16,CallbackEntityClass::Player},{5,24,CallbackEntityClass::Pickup},
 {3,32,CallbackEntityClass::Familiar},{2,40,CallbackEntityClass::Tear},
 {9,40,CallbackEntityClass::Projectile},{7,40,CallbackEntityClass::Laser},
 {8,40,CallbackEntityClass::Knife},{1000,40,CallbackEntityClass::Effect},
 {4,40,CallbackEntityClass::Bomb},{160,40,CallbackEntityClass::Npc},{6,40,CallbackEntityClass::None}};
 auto address=reinterpret_cast<std::uintptr_t>(entity.data());
 for(auto c:cases){
  write(0,std::uintptr_t(0x1000+c.offset));write(kEntityTypeOffset,c.type);
  write(kEntityVariantOffset,unsigned(77));write(kEntitySubTypeOffset,unsigned(9));
  std::int64_t filter=-1;
  if(ClassifyCallbackEntity(address,&filter)!=c.kind)return 1;
  const auto expected=c.kind==CallbackEntityClass::Npc?160:c.kind==CallbackEntityClass::Knife?9:77;
  if(filter!=expected)return 2;
 }
 write(kEntityTypeOffset,unsigned(1));write(0,std::uintptr_t(0x1028));
 if(ClassifyCallbackEntity(address,nullptr)!=CallbackEntityClass::None)return 3;
 write(kEntityTypeOffset,unsigned(160));
 if(ClassifyCallbackEntity(address,nullptr)!=CallbackEntityClass::Npc)return 4;
 write(0,std::uintptr_t(9));if(ClassifyCallbackEntity(address,nullptr)!=CallbackEntityClass::None)return 5;
 readable=false;if(ClassifyCallbackEntity(address,nullptr)!=CallbackEntityClass::None)return 6;
 if(ClassifyCallbackEntity(0,nullptr)!=CallbackEntityClass::None)return 7;
 if(spatialReads){std::fprintf(stderr,"classification read %u unused spatial fields",spatialReads);return 8;}
}
'''
        with tempfile.TemporaryDirectory(prefix='entity-classify-cost-') as tmp:
            work = Path(tmp)
            cpp = work / 'check.cpp'
            cpp.write_text(prefix + body + main)
            result = subprocess.run(['c++', '-std=c++17', str(cpp), '-o', str(work / 'check')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(work / 'check')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
