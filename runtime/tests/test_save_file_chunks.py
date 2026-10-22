"""验证生产Read/Write函数的对齐分块、短读和提交顺序，原生入口用内存文件替身。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
CPP=ROOT/'runtime/src/infrastructure/persistence/engine_save_file_adapter.cpp'

def method(text,signature):
 start=text.index(signature);begin=text.index('{',start);depth=1;end=begin+1
 while depth:
  if text[end]=='{':depth+=1
  if text[end]=='}':depth-=1
  end+=1
 return text[start:end]

PRELUDE=r'''
#include "infrastructure/persistence/engine_save_file_adapter.hpp"
#include <string>
#include <cstring>
#include <cstdint>
#include <cstdio>
namespace isaac::runtime {
std::string disk;
int writes=0, reads=0, commits=0, closes=0;
bool shortRead=false, zeroRead=false, failWrite=false;
std::uint32_t Open(std::uint64_t* h,const char*,int){*h=1;return 0;}
std::uint32_t Create(const char*,std::int64_t){return 0;}
std::uint32_t Write(std::uint64_t,std::int64_t offset,const void* data,std::size_t size,const std::uint32_t*) {
 ++writes;if(failWrite && writes==2)return 1;
 if(reinterpret_cast<std::uintptr_t>(data)%4096 || size>16384)return 1;
 if(disk.size()<static_cast<std::size_t>(offset)+size)disk.resize(offset+size);
 std::memcpy(disk.data()+offset,data,size);return 0;
}
std::uint32_t Read(std::uint64_t* count,std::uint64_t,std::int64_t offset,void* data,std::size_t size){
 ++reads;if(reinterpret_cast<std::uintptr_t>(data)%4096 || size>16384)return 1;
 if(zeroRead){*count=0;return 0;}
 const auto remaining=disk.size()-offset;*count=remaining<size?remaining:size;
 if(shortRead && *count>123)*count=123;
 std::memcpy(data,disk.data()+offset,*count);return 0;
}
std::uint32_t Resize(std::uint64_t,std::int64_t size){disk.resize(size);return 0;}
std::uint32_t Flush(std::uint64_t){return 0;}
std::uint32_t Size(std::int64_t* size,std::uint64_t){*size=disk.size();return 0;}
std::uint32_t Close(std::uint64_t){++closes;return 0;}
std::uint32_t Commit(const char*){++commits;return 0;}
constexpr std::size_t kPathCapacity=320;
constexpr int kVfsOpenModeRead=1,kVfsOpenModeWrite=2;
constexpr std::uint32_t kResultPathAlreadyExists=0x402;
Status StatusFromResult(std::uint32_t result,bool){return result?Status{StatusCode::IoFailure}:Status::Ok();}
'''
MAIN=r'''
} // namespace
using namespace isaac::runtime;
int main() {
 EngineSaveFileAdapter port;std::string source(70001,'a');source[20000]='\0';
 if(port.Write("data",source).code()!=StatusCode::Unsupported)return 1;
 port.AllowFromGameThread();
 if(!port.Write("data",source).ok() || disk!=source || writes!=5 || commits!=1)return 2;
 std::string target(source.size(),'x');std::size_t size=0;
 if(!port.Read("data",target.data(),target.size(),&size).ok() || target!=source || size!=source.size() || reads!=5)return 3;
 shortRead=true;target.assign(target.size(),'x');
 if(!port.Read("data",target.data(),target.size(),&size).ok() || target!=source)return 4;
 zeroRead=true;
 if(port.Read("data",target.data(),target.size(),&size).code()!=StatusCode::IoFailure || size!=0)return 5;
 zeroRead=false;shortRead=false;
 if(port.Read("data",target.data(),10,&size).code()!=StatusCode::CapacityExceeded)return 6;
 writes=0;failWrite=true;
 if(port.Write("data",source).code()!=StatusCode::IoFailure || commits!=1 || writes!=2)return 7;
 failWrite=false;
 if(!port.Write("data","small").ok() || disk!="small" || commits!=2)return 8;
 if(!port.Write("data","").ok() || !disk.empty() || commits!=3)return 9;
 std::printf("aligned_chunks_short_read_error_and_commit_ok closes=%d\n",closes);return 0;
}
'''
class SaveFileChunksTests(unittest.TestCase):
 def test_actual_adapter_read_write_methods(self):
  text=CPP.read_text();calls=method(text,'struct EngineSaveFileAdapter::Calls')+';'
  # 仅入口解析注入内存替身；执行的读/写/路径函数逐字来自生产源码。
  resolve='''const EngineSaveFileAdapter::Calls* EngineSaveFileAdapter::Resolve() noexcept {
   if(!allowed_)return nullptr;
   std::strcpy(mountPoint_.data(),"sdmc:/");std::strcpy(mountName_.data(),"sdmc");mountValid_=true;
   static Calls calls{};calls.openFile=Open;calls.createFile=Create;calls.writeFile=isaac::runtime::Write;calls.readFile=isaac::runtime::Read;
   calls.setFileSize=Resize;calls.flushFile=Flush;calls.getFileSize=Size;calls.closeFile=Close;calls.commitSaveData=Commit;return &calls;
  }'''
  methods='\n'.join(method(text,signature) for signature in ['bool EngineSaveFileAdapter::BuildRelativePath','Status EngineSaveFileAdapter::Read','Status EngineSaveFileAdapter::Write'])
  stubs='''Status EngineSaveFileAdapter::Remove(std::string_view) noexcept {return Status{StatusCode::Unsupported};}
Status EngineSaveFileAdapter::Exists(const char*,bool*) noexcept {return Status{StatusCode::Unsupported};}
alignas(0x1000) char EngineSaveFileAdapter::buffer_[EngineSaveFileAdapter::kMaximumFileBytes];'''
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'probe.cpp';p.write_text(PRELUDE+calls+resolve+methods+stubs+MAIN);b=Path(td)/'probe'
   result=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/src'),str(p),'-o',str(b)],text=True,capture_output=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   result=subprocess.run([str(b)],text=True,capture_output=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr+f'exit={result.returncode}');print(result.stdout.strip())
if __name__=='__main__':unittest.main()
