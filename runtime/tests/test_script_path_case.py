"""Case-sensitive game filesystem, PC Lua spelling, and exact-path priority."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
DRIVER = r'''
#include "game_file_reader.hpp"
#include "script_path_resolver.hpp"
#include "game_script_directory.hpp"
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
namespace {
int failures{}, scans{}, constructs{}, destroys{}, closes{};
std::vector<std::string> opens;
const char* wanted="rom:/isaac_mods/mods/Fiend/resources/LuaRooms/TheLab.lua";
const char* requested="rom:/isaac_mods/mods/Fiend/resources/luarooms/thelab.lua";
bool exactAvailable{},shortRead{},fallbackAvailable{true};
void Check(bool pass,const char* label) {
    if(!pass){std::printf("FAIL %s\n",label);++failures;}
}
void Construct(void*) {++constructs;}
void Destroy(void*) {++destroys;}
void Close(void*) {++closes;}
bool Open(void*,const char* path) {
    opens.emplace_back(path);
    return (fallbackAvailable && opens.back()==wanted) || (exactAvailable && opens.back()==requested);
}
int Length(const void*) {return 9;}
int Read(void*,void* out,int,int n) {std::memcpy(out,"return 37",n);return shortRead?n-1:n;}
int directoryReads{},directoryCloses{},directoryMode{};
bool directoryOpenFails{},directoryReadFails{},directoryBadCount{};
std::uint32_t DirectoryOpen(std::uint64_t* handle,const char*,int mode) {
    directoryMode=mode;directoryReads=0;*handle=123;return directoryOpenFails?1:0;
}
void DirectoryClose(std::uint64_t handle) {Check(handle==123,"directory handle ABI");++directoryCloses;}
std::uint32_t DirectoryRead(std::int64_t* count,GameFileReader::GameScriptDirectory::Entry* entries,
                           std::uint64_t handle,std::int64_t capacity) {
    Check(handle==123 && capacity>0,"directory read ABI");
    if(directoryReadFails)return 1;
    if(directoryBadCount){*count=capacity+1;return 0;}
    if(directoryReads++==0){std::strcpy(entries[0].name,"THELAB.LUA");*count=1;}
    else if(directoryReads==2){std::strcpy(entries[0].name,"TheLab.lua");*count=1;}
    else *count=0;
    return 0;
}
void TestGameDirectory() {
    GameFileReader::GameScriptDirectory directory{DirectoryOpen,DirectoryRead,DirectoryClose};
    char name[64]{};
    Check(directory.FindName("rom:/somewhere","TheLab.lua",false,name,sizeof(name)) &&
          !std::strcmp(name,"TheLab.lua"),"exact component preferred over earlier case variant");
    Check(directoryMode==2 && directoryCloses==1,"file enumeration filters files and closes handle");
    Check(directory.FindName("rom:/somewhere","thelab.lua",true,name,sizeof(name)) &&
          !std::strcmp(name,"THELAB.LUA"),"case-insensitive name returned unchanged");
    Check(directoryMode==1 && directoryCloses==2,"intermediate enumeration filters directories");
    directoryOpenFails=true;
    Check(!directory.FindName("rom:/absent","x",true,name,sizeof(name)) && directoryCloses==2,
          "missing parent returns safely without closing unopened handle");
    directoryOpenFails=false;directoryReadFails=true;
    Check(!directory.FindName("rom:/somewhere","x",false,name,sizeof(name)) && directoryCloses==3,
          "read failure closes directory and returns miss");
    directoryReadFails=false;directoryBadCount=true;
    Check(!directory.FindName("rom:/somewhere","x",false,name,sizeof(name)) && directoryCloses==4,
          "invalid engine count is bounded and closes directory");
    directoryBadCount=false;
    Check(!directory.FindName("rom:/somewhere","thelab.lua",false,name,4) && directoryCloses==5,
          "output capacity never truncates entry names");
}
bool Find(void*,const char* parent,const char* name,bool directory,char* out,std::size_t capacity) {
    ++scans;
    struct Entry {const char* parent;const char* name;bool directory;};
    const Entry entries[]={
        {"rom:/","isaac_mods",true},
        {"rom:/isaac_mods","mods",true},
        {"rom:/isaac_mods/mods","Fiend",true},
        {"rom:/isaac_mods/mods/Fiend","resources",true},
        {"rom:/isaac_mods/mods/Fiend/resources","LuaRooms",true},
        {"rom:/isaac_mods/mods/Fiend/resources/LuaRooms","TheLab.lua",false},
    };
    for(const auto& entry:entries) {
        if(std::strcmp(parent,entry.parent) || directory!=entry.directory ||
           !GameFileReader::ScriptPathResolver::EqualAsciiCase(name,entry.name))continue;
        if(std::strlen(entry.name)>=capacity)return false;
        std::strcpy(out,entry.name);return true;
    }
    return false;
}
}
int main() {
    TestGameDirectory();
    GameFileReader::Bindings bindings{Construct,Open,Length,Read,Close,Destroy};
    GameFileReader::ScriptPathResolver resolver{};
    resolver.findName=Find;
    bindings.scriptPathResolver=&resolver;
    unsigned char buffer[64]{};std::size_t length=0;
    const auto result=GameFileReader::ReadTextFile(bindings,requested,buffer,sizeof(buffer),&length);
    Check(result==GameFileReader::TextReadResult::Success,"case mismatch loads original author file");
    Check(length==9 && std::memcmp(buffer,"return 37",9)==0,"source bytes unchanged");
    Check(opens.size()==2 && opens.front()==requested && opens.back()==wanted,"exact path precedes actual spelling");
    Check(constructs==destroys && closes==1,"failed open and retry have balanced file lifetimes");
    const int scanned=scans;
    Check(GameFileReader::ReadTextFile(bindings,requested,buffer,sizeof(buffer),&length)==GameFileReader::TextReadResult::Success,
          "repeated include succeeds");
    Check(scans==scanned,"successful path cache avoids repeat directory enumeration");
    exactAvailable=true;opens.clear();
    Check(GameFileReader::ReadTextFile(bindings,requested,buffer,sizeof(buffer),&length)==GameFileReader::TextReadResult::Success,
          "new exact spelling takes priority over cached fallback");
    Check(opens.size()==1 && opens.front()==requested && scans==scanned,"exact success performs no fallback");
    Check(GameFileReader::ReadTextFile(bindings,requested,buffer,4,&length)==GameFileReader::TextReadResult::LengthOutOfRange && length==9,
          "existing length limit and observed length preserved");
    shortRead=true;
    Check(GameFileReader::ReadTextFile(bindings,requested,buffer,sizeof(buffer),&length)==GameFileReader::TextReadResult::ReadMismatch,
          "short read remains an error");
    shortRead=false;exactAvailable=false;fallbackAvailable=false;
    Check(GameFileReader::ReadTextFile(bindings,requested,buffer,sizeof(buffer),&length)==GameFileReader::TextReadResult::OpenFailed,
          "failed resolved open remains an error");
    Check(constructs==destroys,"all open and read failures balance file lifetimes");
    fallbackAvailable=true;
    auto exactOnly=bindings;exactOnly.scriptPathResolver=nullptr;
    Check(GameFileReader::ReadTextFile(exactOnly,requested,buffer,sizeof(buffer),&length)==GameFileReader::TextReadResult::OpenFailed,
          "unavailable resolver preserves exact-only behavior");
    Check(GameFileReader::ReadTextFile(bindings,"rom:/isaac_mods/mods/Fiend/resources/nope.lua",buffer,sizeof(buffer),&length)==GameFileReader::TextReadResult::OpenFailed,
          "missing module remains missing");
    char resolved[GameFileReader::ScriptPathResolver::kPathCapacity]{};
    const int beforeInvalid=scans;
    Check(!resolver.Resolve("rom:/isaac_mods/mods/../main.lua",resolved,sizeof(resolved)),"parent traversal is not introduced by fallback");
    Check(scans==beforeInvalid,"invalid paths rejected before directory IO");
    Check(!resolver.Resolve(requested,resolved,8),"small output never truncates a cached path");
    Check(!GameFileReader::ScriptPathResolver::EqualAsciiCase("x", "xx"),"different lengths do not match");
    Check(!GameFileReader::ScriptPathResolver::EqualAsciiCase("\xc0", "\xe0"),"non-ASCII bytes remain distinct");
    for(unsigned mask=1;mask<=GameFileReader::ScriptPathResolver::kCacheEntries+1;++mask) {
        std::string variant=requested;
        const auto base=variant.rfind('/')+1;
        for(unsigned bit=0;bit<5;++bit)if(mask&(1U<<bit))variant[base+bit]-='a'-'A';
        Check(resolver.Resolve(variant.c_str(),resolved,sizeof(resolved)),"cache continues resolving after its fixed capacity");
    }
    const int beforeEviction=scans;
    Check(resolver.Resolve(requested,resolved,sizeof(resolved)) && scans>beforeEviction,
          "bounded positive cache evicts old entries and re-resolves correctly");
    if(failures)return 1;
    std::puts("PASS case fallback, exact priority, positive cache, lifetime, bounds and misses");
}
'''


class ScriptPathCaseTests(unittest.TestCase):
    def test_real_reader_with_case_sensitive_file_bindings(self):
        with tempfile.TemporaryDirectory(prefix="isaac-script-path-") as directory:
            root = Path(directory)
            # Only platform memory-query declarations are replaced. The reader
            # and its actual public header are compiled without rewriting code.
            (root / "reader.cpp").write_text((ROOT / "runtime/source/game_file_reader.cpp").read_text())
            (root / "lib.hpp").write_text("#pragma once\n#include <atomic>\n")
            svc = root / "lib/nx/kernel/svc.h"
            svc.parent.mkdir(parents=True)
            svc.write_text("""#pragma once
#include <cstdint>
using u32=std::uint32_t;
struct MemoryInfo {std::uintptr_t addr{},size{};unsigned type{},perm{};};
constexpr unsigned MemState_Type=255,MemType_ModuleCodeStatic=1,Perm_Rx=5;
inline unsigned svcQueryMemory(MemoryInfo*,u32*,std::uintptr_t){return 1;}
#define R_FAILED(x) ((x)!=0)
""")
            main = root / "main.cpp"
            main.write_text(DRIVER)
            binary = root / "test"
            built = subprocess.run([
                "c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                "-I" + str(root), "-I" + str(ROOT / "runtime/source"),
                str(main), str(root / "reader.cpp"), "-o", str(binary),
            ], text=True, capture_output=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
