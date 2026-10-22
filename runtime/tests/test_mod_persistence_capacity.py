"""PC 的 SaveData 字符串不能挤在所有模组共享的16KiB固定容器里。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HARNESS=r'''
#include "mod_persistence.hpp"
#include <string>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <new>
#include "domain/persistence/persistence_codec.hpp"
int failAllocation=-1;
void* operator new[](std::size_t size,const std::nothrow_t&) noexcept {
 if(failAllocation==0)return nullptr;
 if(failAllocation>0)--failAllocation;
 return std::malloc(size);
}
void operator delete[](void* pointer) noexcept {std::free(pointer);}
void operator delete[](void* pointer,std::size_t) noexcept {std::free(pointer);}
struct Store : isaac::runtime::ISaveFilePort {
 std::string bytes;
 bool fail=false;
 isaac::runtime::Status Read(std::string_view,char* out,std::size_t cap,std::size_t* size) noexcept override {
  *size=0;
  if(bytes.empty())return isaac::runtime::Status{isaac::runtime::StatusCode::NotFound};
  if(bytes.size()>cap)return isaac::runtime::Status{isaac::runtime::StatusCode::CapacityExceeded};
  std::memcpy(out,bytes.data(),bytes.size());*size=bytes.size();return isaac::runtime::Status::Ok();
 }
 isaac::runtime::Status Write(std::string_view,std::string_view data) noexcept override {
  if(fail)return isaac::runtime::Status{isaac::runtime::StatusCode::IoFailure};
  bytes.assign(data);return isaac::runtime::Status::Ok();
 }
 isaac::runtime::Status Remove(std::string_view) noexcept override {bytes.clear();return isaac::runtime::Status::Ok();}
 isaac::runtime::Status Exists(const char*,bool* exists) noexcept override {*exists=!bytes.empty();return isaac::runtime::Status::Ok();}
};
int main() {
 Store store;isaac::runtime::SetSessionSaveFilePort(&store);ModPersistence::ResetCacheForTesting();
 // 先存旧格式小容器，升级仍读得回来；随后一次20KiB数据与多个模组总量均越过旧上限。
 if(ModPersistence::SaveModData(1,"legacy",6)!=ModPersistence::Result::Success)return 1;
 ModPersistence::ResetCacheForTesting();
 const char* data=nullptr;std::size_t length=0;
 if(ModPersistence::LoadModData(1,&data,&length)!=ModPersistence::Result::Success || length!=6)return 2;
 std::string large(20000,'a');large[999]='\0';
 for(unsigned i=2;i<10;++i)if(ModPersistence::SaveModData(i,large.data(),large.size())!=ModPersistence::Result::Success)return 3;
 ModPersistence::ResetCacheForTesting();
 for(unsigned i=2;i<10;++i)if(ModPersistence::LoadModData(i,&data,&length)!=ModPersistence::Result::Success || length!=large.size() || std::memcmp(data,large.data(),length))return 4;
 const auto disk=store.bytes;
 if(!isaac::runtime::PersistenceCodec::ValidateFile(reinterpret_cast<const std::uint8_t*>(disk.data()),disk.size()).ok())return 10;
 for(int failure=0;failure<3;++failure){
  failAllocation=failure;
  const auto result=ModPersistence::SaveModData(2,"changed",7);
  failAllocation=-1;
  if(result!=ModPersistence::Result::IoFailure || store.bytes!=disk)return 11;
  if(ModPersistence::LoadModData(2,&data,&length)!=ModPersistence::Result::Success || length!=large.size())return 12;
 }
 store.fail=true;
 if(ModPersistence::SaveModData(2,"changed",7)!=ModPersistence::Result::IoFailure)return 5;
 if(store.bytes!=disk || ModPersistence::LoadModData(2,&data,&length)!=ModPersistence::Result::Success || length!=large.size())return 6;
 store.fail=false;
 if(ModPersistence::SaveModData(2,"small",5)!=ModPersistence::Result::Success || ModPersistence::RemoveModData(3)!=ModPersistence::Result::Success)return 7;
 ModPersistence::ResetCacheForTesting();
 if(ModPersistence::LoadModData(3,&data,&length)!=ModPersistence::Result::Missing || ModPersistence::LoadModData(2,&data,&length)!=ModPersistence::Result::Success || length!=5 || std::memcmp(data,"small",5))return 8;
 std::printf("capacity_roundtrip=%zu old_format_and_failed_write_preserved\n",disk.size());return 0;
}
'''
class ModPersistenceCapacityTests(unittest.TestCase):
 def test_large_multimod_roundtrip_old_format_and_write_failure(self):
  with tempfile.TemporaryDirectory() as td:
   source=Path(td)/'probe.cpp';source.write_text(HARNESS);binary=Path(td)/'probe'
   result=subprocess.run(['c++','-std=c++20','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(source),str(ROOT/'runtime/src/domain/persistence/persistence_codec.cpp'),'-o',str(binary)],text=True,capture_output=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   result=subprocess.run([str(binary)],text=True,capture_output=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr+f'exit={result.returncode}')
   print(result.stdout.strip())
if __name__=='__main__':unittest.main()
