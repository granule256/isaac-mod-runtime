"""PC 的 SaveData 字符串不能被旧版16KiB共享容器上限限制。"""
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
#include <map>
#include <new>
int failAllocation=-1;
void* operator new[](std::size_t size,const std::nothrow_t&) noexcept {
 if(failAllocation==0)return nullptr;
 if(failAllocation>0)--failAllocation;
 return std::malloc(size);
}
void operator delete[](void* pointer) noexcept {std::free(pointer);}
void operator delete[](void* pointer,std::size_t) noexcept {std::free(pointer);}
struct Store : isaac::runtime::ISaveFilePort {
 std::map<std::string,std::string> files;
 bool fail=false;
 isaac::runtime::Status Read(std::string_view name,char* out,std::size_t cap,std::size_t* size) noexcept override {
  *size=0;
  const auto found=files.find(std::string(name));
  if(found==files.end())return isaac::runtime::Status{isaac::runtime::StatusCode::NotFound};
  *size=found->second.size();
  if(found->second.size()>cap)return isaac::runtime::Status{isaac::runtime::StatusCode::CapacityExceeded};
  std::memcpy(out,found->second.data(),found->second.size());*size=found->second.size();return isaac::runtime::Status::Ok();
 }
 isaac::runtime::Status Write(std::string_view name,std::string_view data) noexcept override {
  if(fail)return isaac::runtime::Status{isaac::runtime::StatusCode::IoFailure};
  files[std::string(name)].assign(data);return isaac::runtime::Status::Ok();
 }
 isaac::runtime::Status Remove(std::string_view name) noexcept override {files.erase(std::string(name));return isaac::runtime::Status::Ok();}
 isaac::runtime::Status Exists(const char* name,bool* exists) noexcept override {*exists=files.count(name)!=0;return isaac::runtime::Status::Ok();}
};
int main() {
 Store store;isaac::runtime::SetSessionSaveFilePort(&store);ModPersistence::ResetCacheForTesting();
 // 先存一个小模组，再验证一次20KiB数据与多个模组总量均越过旧上限。
 if(ModPersistence::SaveModData(1,"legacy",6)!=ModPersistence::Result::Success)return 1;
 ModPersistence::ResetCacheForTesting();
 const char* data=nullptr;std::size_t length=0;
 if(ModPersistence::LoadModData(1,&data,&length)!=ModPersistence::Result::Success || length!=6)return 2;
 std::string large(20000,'a');large[999]='\0';
 for(unsigned i=2;i<10;++i)if(ModPersistence::SaveModData(i,large.data(),large.size())!=ModPersistence::Result::Success)return 3;
 ModPersistence::ResetCacheForTesting();
 for(unsigned i=2;i<10;++i)if(ModPersistence::LoadModData(i,&data,&length)!=ModPersistence::Result::Success || length!=large.size() || std::memcmp(data,large.data(),length))return 4;
 const auto disk=store.files;
 for(const auto& [name,bytes]:disk) {
  ModPersistence::detail::Buffer file;
  file.length=bytes.size();
  file.bytes.reset(new (std::nothrow) std::uint8_t[file.length]);
  if(!file.bytes)return 10;
  std::memcpy(file.bytes.get(),bytes.data(),file.length);
  unsigned long long namespaceId=0;unsigned slot=0;
  const auto parsed=std::sscanf(name.c_str(),"isaac-mod-%llx-s%u-a.bin",&namespaceId,&slot);
  if(parsed!=2 || !ModPersistence::detail::ValidateFile(file,namespaceId,slot))return 10;
 }
 {
  failAllocation=0;
  const auto result=ModPersistence::SaveModData(2,"changed",7);
  failAllocation=-1;
  if(result!=ModPersistence::Result::IoFailure || store.files!=disk)return 11;
  if(ModPersistence::LoadModData(2,&data,&length)!=ModPersistence::Result::Success || length!=large.size())return 12;
 }
 store.fail=true;
 if(ModPersistence::SaveModData(2,"changed",7)!=ModPersistence::Result::IoFailure)return 5;
 if(store.files!=disk || ModPersistence::LoadModData(2,&data,&length)!=ModPersistence::Result::Success || length!=large.size())return 6;
 store.fail=false;
 if(ModPersistence::SaveModData(2,"small",5)!=ModPersistence::Result::Success || ModPersistence::RemoveModData(3)!=ModPersistence::Result::Success)return 7;
 ModPersistence::ResetCacheForTesting();
 if(ModPersistence::LoadModData(3,&data,&length)!=ModPersistence::Result::Missing || ModPersistence::LoadModData(2,&data,&length)!=ModPersistence::Result::Success || length!=5 || std::memcmp(data,"small",5))return 8;
 std::printf("capacity_roundtrip=%zu files failed_write_preserved\n",disk.size());return 0;
}
'''
class ModPersistenceCapacityTests(unittest.TestCase):
 def test_large_multimod_roundtrip_and_write_failure(self):
  with tempfile.TemporaryDirectory() as td:
   source=Path(td)/'probe.cpp';source.write_text(HARNESS);binary=Path(td)/'probe'
   result=subprocess.run(['c++','-std=c++20','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(source),'-o',str(binary)],text=True,capture_output=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   result=subprocess.run([str(binary)],text=True,capture_output=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr+f'exit={result.returncode}')
   print(result.stdout.strip())
if __name__=='__main__':unittest.main()
