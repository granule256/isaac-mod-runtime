"""Custom achievements use profile-scoped files and stable keys, not numeric IDs."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRIVER = r'''
#include "application/repentogon/achievement_state.hpp"
#include <cassert>
#include <cstring>
#include <string>
#include <unordered_map>
using namespace isaac::runtime;
struct Files:ISaveFilePort {
 unsigned slot=2,reads=0,writes=0; bool fail=false;
 std::unordered_map<std::string,std::string> data;
 Status GetSaveSlot(unsigned* out) noexcept override{*out=slot;return Status::Ok();}
 Status Read(std::string_view path,char* out,std::size_t cap,std::size_t* size) noexcept override {
  ++reads; auto it=data.find(std::string(path));if(it==data.end())return Status{StatusCode::NotFound};
  *size=it->second.size();if(*size>cap)return Status{StatusCode::CapacityExceeded};
  std::memcpy(out,it->second.data(),*size);return Status::Ok();
 }
 Status Write(std::string_view path,std::string_view bytes) noexcept override {
  ++writes;if(fail)return Status{StatusCode::IoFailure};
  data[std::string(path)]=std::string(bytes);return Status::Ok();
 }
 Status Remove(std::string_view) noexcept override{return Status{StatusCode::Unsupported};}
 Status Exists(const char*,bool*) noexcept override{return Status{StatusCode::Unsupported};}
};
int main(){
 Files files;AchievementState state;bool value=true;
 assert(state.Unlocked(&files,"First","ModA",&value).ok()&&!value);
 const auto reads=files.reads;
 for(int i=0;i<1000;++i)assert(state.Unlocked(&files,"First","ModA",&value).ok()&&!value);
 assert(files.reads==reads&&files.writes==0);
 bool changed=false;assert(state.Unlock(&files,"First","ModA",&changed).ok()&&changed);
 assert(state.Unlocked(&files,"First","ModA",&value).ok()&&value);
 assert(state.Unlock(&files,"First","ModA",&changed).ok()&&!changed&&files.writes==1);
 assert(state.Unlocked(&files,"First","ModB",&value).ok()&&!value);
 files.slot=3;assert(state.Unlocked(&files,"First","ModA",&value).ok()&&!value);
 files.slot=2;state.Reset();assert(state.Unlocked(&files,"First","ModA",&value).ok()&&value);
 files.fail=true;assert(!state.Unlock(&files,"Second","ModA",&changed).ok()&&!changed);
 assert(state.Unlocked(&files,"Second","ModA",&value).ok()&&!value);
 files.fail=false;
 // Profile roots are owned by the port; switching providers cannot reuse state.
 Files other;assert(state.Unlocked(&other,"First","ModA",&value).ok()&&!value);
 state.Reset();files.data.begin()->second.pop_back();
 assert(state.Unlocked(&files,"First","ModA",&value).code()==StatusCode::Corrupted);
 assert(!state.Unlock(&files,"Second","ModA",&changed).ok());
 files.slot=4;assert(!state.Unlocked(&files,"First","ModA",&value).ok());
 assert(!state.Unlocked(nullptr,"First","ModA",&value).ok());
}
'''


class AchievementStateTests(unittest.TestCase):
    def test_slot_profile_reload_failures_and_cached_queries(self):
        with tempfile.TemporaryDirectory(prefix='achievement-state-') as folder:
            folder = Path(folder)
            source = folder / 'driver.cpp'
            source.write_text(DRIVER)
            binary = folder / 'test'
            result = subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT / 'src'), str(source),
                str(ROOT / 'src/application/repentogon/achievement_state.cpp'),
                '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
