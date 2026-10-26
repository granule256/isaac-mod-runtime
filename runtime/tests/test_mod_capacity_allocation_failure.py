"""真实加载链的临时堆分配失败必须返回错误，不能崩溃或发布半份清单。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVER = r'''
#include "application/mod/manifest_service.hpp"
#include "application/mod/mod_discovery_service.hpp"
#include "application/mod/mod_toggle_service.hpp"
#include "infrastructure/mod/manifest_selector_adapter.hpp"
#include "mod_manifest.hpp"
#include <new>
#include <cstring>
#include <cstdio>
int failAt=0,allocations=0;
void* operator new(std::size_t n,const std::nothrow_t&) noexcept {
 if(++allocations==failAt)return nullptr;
 try{return ::operator new(n);}catch(...){return nullptr;}
}
void* operator new[](std::size_t n,const std::nothrow_t&) noexcept {
 if(++allocations==failAt)return nullptr;
 try{return ::operator new[](n);}catch(...){return nullptr;}
}
using namespace isaac::runtime;
const char text[]="{\"schema_version\":1,\"mods\":[{\"directory\":\"test\",\"enabled\":true}]}";
struct Content:IContentPort {
 Status Size(std::string_view,std::size_t*) noexcept override{return Status::Ok();}
 Status Read(std::string_view,std::uint8_t* p,std::size_t n,std::size_t* size) noexcept override{
  *size=sizeof(text)-1;if(n<*size)return Status{StatusCode::CapacityExceeded};
  std::memcpy(p,text,*size);return Status::Ok();
 }
};
struct Directories:IModDirectoryPort {
 Status ListSubdirectories(std::string_view,ModDirectoryEntry*,std::size_t,std::size_t* count) noexcept override{
  *count=0;return Status::Ok();
 }
};
struct Files:ISaveFilePort {
 int writes=0;
 Status Read(std::string_view,char*,std::size_t,std::size_t*) noexcept override{return Status{StatusCode::NotFound};}
 Status Write(std::string_view,std::string_view) noexcept override{++writes;return Status::Ok();}
 Status Remove(std::string_view) noexcept override{return Status::Ok();}
 Status Exists(const char*,bool* yes) noexcept override{*yes=false;return Status::Ok();}
};
int main(){
 Content content;ManifestParser parser{ManifestSelectorAdapter::SelectFunction(),ManifestSelectorAdapter::SelectAllFunction()};
 ManifestService service{content,parser};static ResolvedManifestModBatch batch;
 std::uint8_t buffer[sizeof(text)]{};ModLoadFailure failure{};
 for(int i=1;i<=3;++i){
  failAt=i;allocations=0;batch.count=7;
  if(service.ResolveAll(buffer,sizeof(buffer),&batch,&failure).code()!=StatusCode::IoFailure || batch.count!=7)return 10+i;
 }
 failAt=0;allocations=0;
 if(!service.ResolveAll(buffer,sizeof(buffer),&batch,&failure).ok() || batch.count!=1)return 20;
 static ::ModManifest::SelectedMods legacy;
 legacy.count=9;failAt=1;allocations=0;
 if(::ModManifest::SelectAllEnabled(text,sizeof(text)-1,&legacy)!=::ModManifest::ParseResult::OutOfMemory || legacy.count!=9)return 21;
 Directories dirs;ModDiscoveryService discovery{dirs};failAt=1;allocations=0;
 if(discovery.Discover(&batch).code()!=StatusCode::IoFailure || batch.count!=0)return 22;
 batch.count=1;failAt=1;allocations=0;
 if(discovery.AppendUnlisted(&batch).code()!=StatusCode::IoFailure || batch.count!=1)return 23;
 Files files;static ModToggleService toggles{files};
 failAt=1;allocations=0;
 if(toggles.Load().code()!=StatusCode::IoFailure)return 24;
 failAt=1;allocations=0;
 if(toggles.Save().code()!=StatusCode::IoFailure || files.writes)return 25;
 std::puts("three_nested_parse_allocations_and_discovery_toggle_oom_reported");return 0;
}
'''


class ModCapacityAllocationFailureTests(unittest.TestCase):
    def test_actual_loading_allocation_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'oom.cpp';source.write_text(DRIVER)
            binary=Path(tmp)/'oom'
            sources=[
                'runtime/source/mod_manifest.cpp',
                'runtime/src/infrastructure/mod/manifest_selector_adapter.cpp',
                'runtime/src/application/mod/manifest_parser.cpp',
                'runtime/src/application/mod/manifest_service.cpp',
                'runtime/src/application/mod/mod_discovery_service.cpp',
                'runtime/src/application/mod/mod_toggle_service.cpp',
                'runtime/src/domain/mod/mod_toggle_state.cpp',
            ]
            built=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',
                '-Iruntime/src','-Iruntime/source',str(source),*sources,'-o',str(binary)],
                cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(built.returncode,0,built.stdout+built.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            print(result.stdout.strip())


if __name__=='__main__':unittest.main()
