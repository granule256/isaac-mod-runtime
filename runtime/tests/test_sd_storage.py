"""Exercise the production SD backend with an in-memory nn::fs filesystem."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DRIVER = r'''
#include "infrastructure/persistence/sd_save_file_adapter.hpp"
#include "mod_persistence.hpp"
#include <cassert>
#include <cstring>
#include <map>
#include <string>
using namespace isaac::runtime;
std::map<std::string,std::string> disk;
std::map<std::uint64_t,std::string> handles;
std::uint64_t nextHandle=1;
int oldReads=0, writes=0, calls=0;
bool failWrite=false, failRead=false, shortRead=false, failRename=false;
std::uint32_t Create(const char* p,std::int64_t n,int) {
 ++calls;if(disk.count(p))return 0x402;disk[p].resize(n);return 0;
}
std::uint32_t Open(std::uint64_t* h,const char* p,int) {
 ++calls;if(!disk.count(p))return 0x202;*h=nextHandle++;handles[*h]=p;return 0;
}
void Close(std::uint64_t h){handles.erase(h);}
std::uint32_t Size(std::int64_t* n,std::uint64_t h){*n=disk[handles[h]].size();return 0;}
std::uint32_t Read(std::uint64_t* n,std::uint64_t h,std::int64_t o,void* b,std::size_t cap){
 if(failRead)return 0xdead;
 const auto& s=disk[handles[h]];*n=std::min<std::size_t>(cap,s.size()-o);
 if(shortRead)*n=std::min<std::size_t>(*n,127);
 std::memcpy(b,s.data()+o,*n);return 0;
}
std::uint32_t Write(std::uint64_t h,std::int64_t o,const void* b,std::size_t n,const std::uint32_t*){
 ++writes;if(failWrite)return 0xdead;disk[handles[h]].replace(o,n,static_cast<const char*>(b),n);return 0;
}
std::uint32_t Flush(std::uint64_t){return 0;}
std::uint32_t Delete(const char* p){++calls;return disk.erase(p)?0:0x202;}
std::uint32_t Rename(const char* a,const char* b){
 ++calls;if(failRename && std::strstr(a,".tmp"))return 0xdead;
 if(!disk.count(a))return 0x202;if(disk.count(b))return 0x402;
 disk[b]=std::move(disk[a]);disk.erase(a);return 0;
}
struct Legacy final : ISaveFilePort {
 std::map<std::string,std::string> files;unsigned slot=2;
 Status Read(std::string_view p,char* b,std::size_t cap,std::size_t* n) noexcept override{
  ++oldReads;auto it=files.find(std::string(p));*n=0;
  if(it==files.end())return Status{StatusCode::NotFound};*n=it->second.size();
  if(cap<*n)return Status{StatusCode::CapacityExceeded};std::memcpy(b,it->second.data(),*n);return Status::Ok();
 }
 Status GetSize(std::string_view p,std::size_t* n) noexcept override{
  auto it=files.find(std::string(p));if(it==files.end())return Status{StatusCode::NotFound};*n=it->second.size();return Status::Ok();
 }
 Status GetSaveSlot(unsigned* s) noexcept override{*s=slot;return Status::Ok();}
 Status Write(std::string_view,std::string_view) noexcept override{assert(false);return {};}
 Status Remove(std::string_view) noexcept override{assert(false);return {};}
 Status Exists(const char*,bool* e) noexcept override{*e=false;return {};}
};
bool OnOwnerThread(void*){return true;}
bool OnOtherThread(void*){return false;}
int main(){
 SdFileApi api{};api.create=Create;api.open=Open;api.close=Close;api.size=Size;
 api.read=Read;api.write=Write;api.flush=Flush;api.remove=Delete;api.rename=Rename;
 Legacy legacy;SdSaveFileAdapter port{legacy};char out[32]{};std::size_t n=999;
 assert(port.Read("mcm",out,sizeof(out),&n).code()==StatusCode::Unsupported && calls==0);
 assert(port.Configure(api,"isaacsd:/profiles/user-a/",OnOwnerThread,nullptr).ok());
 assert(port.Write("../escape","x").code()==StatusCode::InvalidArgument);
 assert(port.Write(std::string_view("bad\0name",8),"x").code()==StatusCode::InvalidArgument);
 std::string data(70001,'x');data[20000]='\0';
 assert(port.Write("mcm",data).ok() && writes==5);
 assert(disk["isaacsd:/profiles/user-a/mcm"]==data);
 std::string actual(data.size(),' ');shortRead=true;
 assert(port.Read("mcm",actual.data(),actual.size(),&n).ok() && actual==data);
 assert(port.Read("mcm",out,sizeof(out),&n).code()==StatusCode::CapacityExceeded && n==data.size());
 shortRead=false;
 assert(port.Write("mcm","small").ok());
 assert(disk["isaacsd:/profiles/user-a/mcm"]=="small");
 failWrite=true;assert(!port.Write("mcm","broken").ok());failWrite=false;
 assert(disk["isaacsd:/profiles/user-a/mcm"]=="small");
 failRename=true;assert(!port.Write("mcm","broken").ok());failRename=false;
 assert(port.Read("mcm",out,sizeof(out),&n).ok() && std::string(out,n)=="small");
 assert(port.Write("empty","").ok());n=999;
 assert(port.Read("empty",out,sizeof(out),&n).ok() && n==0);
 legacy.files["old"]="previous config";
 assert(port.Read("old",out,sizeof(out),&n).ok() && std::string(out,n)=="previous config");
 assert(disk["isaacsd:/profiles/user-a/old"]=="previous config" && legacy.files.count("old"));
 failRead=true;const int reads=oldReads;
 assert(!port.Read("old",out,sizeof(out),&n).ok() && oldReads==reads);failRead=false;
 legacy.files["failed-migration"]="keep";failWrite=true;
 assert(!port.Read("failed-migration",out,sizeof(out),&n).ok());failWrite=false;
 assert(port.Remove("old").ok());
 SdSaveFileAdapter restarted{legacy};
 assert(restarted.Configure(api,"isaacsd:/profiles/user-a/",OnOwnerThread,nullptr).ok());
 assert(restarted.Read("old",out,sizeof(out),&n).code()==StatusCode::NotFound);
 assert(restarted.Write("old","new").ok());
 assert(restarted.Read("old",out,sizeof(out),&n).ok() && std::string(out,n)=="new");
 SdSaveFileAdapter otherUser{legacy};assert(otherUser.Configure(api,"isaacsd:/profiles/user-b/",OnOwnerThread,nullptr).ok());
 assert(otherUser.Write("mcm","other").ok() && disk["isaacsd:/profiles/user-a/mcm"]=="small");
 unsigned slot{};assert(port.GetSaveSlot(&slot).ok() && slot==2);
 // The actual Mod:SaveData backend retains binary data, banks and slot isolation.
 isaac::runtime::SetSessionSaveFilePort(&port);ModPersistence::ResetCacheForTesting();
 assert(ModPersistence::SaveModData(123,data.data(),data.size())==ModPersistence::Result::Success);
 const char* saved=nullptr;std::size_t length{};
 assert(ModPersistence::LoadModData(123,&saved,&length)==ModPersistence::Result::Success);
 assert(length==data.size() && std::memcmp(saved,data.data(),length)==0);
 legacy.slot=1;
 assert(ModPersistence::LoadModData(123,&saved,&length)==ModPersistence::Result::Missing);
 assert(ModPersistence::SaveModData(123,"slot1",5)==ModPersistence::Result::Success);
 legacy.slot=2;ModPersistence::ResetCacheForTesting();
 assert(ModPersistence::LoadModData(123,&saved,&length)==ModPersistence::Result::Success && length==data.size());
 assert(port.Configure(api,"isaacsd:/profiles/user-a/",OnOtherThread,nullptr).ok());
 const int previousCalls=calls;assert(!port.Write("mcm","wrong thread").ok() && calls==previousCalls);
 assert(handles.empty());
}
'''


class SdStorageTests(unittest.TestCase):
    def test_sd_files_migration_recovery_and_thread_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "driver.cpp"
            source.write_text(DRIVER)
            binary = Path(tmp) / "driver"
            result = subprocess.run([
                "c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "runtime/src"), "-I", str(ROOT / "runtime/source"), str(source),
                str(ROOT / "runtime/src/infrastructure/persistence/sd_save_file_adapter.cpp"),
                "-o", str(binary),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
