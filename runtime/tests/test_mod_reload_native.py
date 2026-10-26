"""真实NRO入口守卫和静态ModEntry资源生命周期，避免释放自建菜单条目。"""
import importlib.util
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HARNESS=r'''
#include "mod_reload_native.hpp"
#include <cassert>
#include <array>
#include <cstring>
#include <vector>
using namespace isaac::runtime;
struct Memory {
 std::array<std::uintptr_t,2048> words{};std::vector<std::uintptr_t> freed;
 bool Read(std::uintptr_t address,std::uintptr_t* out){if(address%8||address/8>=words.size())return false;*out=words[address/8];return true;}
};
int main(){
 Memory m;const std::uintptr_t entry=0x200,head=entry+0xf0,node=0x800,record=0xa00;
 m.words[(entry+0xf8)/8]=node;m.words[(entry+0x100)/8]=1;
 m.words[(node+8)/8]=head;m.words[(node+0x10)/8]=record;
 auto read=[&](auto a,auto* out){return m.Read(a,out);};
 auto freeImage=[&](auto a){m.freed.push_back(a);};
 assert(VisitModEntryImages(entry,read,freeImage,false)&&m.freed.empty());
 assert(VisitModEntryImages(entry,read,freeImage,true));
 assert(m.freed==std::vector<std::uintptr_t>{record+0x278});
 m.words[(node+8)/8]=node;assert(!VisitModEntryImages(entry,read,freeImage,false));
 m.words[(node+8)/8]=head;m.words[(entry+0x100)/8]=2;
 assert(!VisitModEntryImages(entry,read,freeImage,false));
 m.words[(entry+0xf8)/8]=head;m.words[(entry+0x100)/8]=0;
 assert(VisitModEntryImages(entry,read,freeImage,true));
 // Native UnloadMods must see an empty vector, while the renderer's static table is restored.
 std::array<std::uintptr_t,3> vector{0x1110,0x1130,0x1140};const auto saved=vector;
 bool nativeCalled=false;
 auto get=[&](auto* out){*out=vector;return true;};
 auto put=[&](const auto& value){vector=value;return true;};
 assert(WithEmptyModVector(get,put,[&]{nativeCalled=true;assert((vector==std::array<std::uintptr_t,3>{}));}));
 assert(nativeCalled&&vector==saved);
 nativeCalled=false;
 assert(!WithEmptyModVector([](auto*){return false;},put,[&]{nativeCalled=true;}));
 assert(!nativeCalled&&vector==saved);
}
'''

class ModReloadNativeTests(unittest.TestCase):
 def test_static_entries_and_menu_vector_ownership(self):
  header=ROOT/'runtime/source/mod_reload_native.hpp'
  self.assertTrue(header.exists(),'缺少静态模组资源安全释放实现')
  with tempfile.TemporaryDirectory(prefix='isaac-mod-reload-native-') as folder:
   source=Path(folder)/'main.cpp';source.write_text(HARNESS);binary=Path(folder)/'check'
   result=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(header.parent),str(source),'-o',str(binary)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   result=subprocess.run([str(binary)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)

 def test_native_entry_guards_match_original_nro(self):
  header=ROOT/'runtime/source/mod_reload_native.hpp'
  self.assertTrue(header.exists(),'缺少本轮原生入口守卫')
  spec=importlib.util.spec_from_file_location('reload_nro_disasm',ROOT/'tools/nro_disasm.py')
  import sys
  sys.path.insert(0,str(ROOT/'tools'))
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  nro=Path(module.DEFAULT_NRO).read_bytes()
  rows=re.findall(r'\{(0x[0-9a-fA-F]+),\s*\{([^}]+)\}\}',header.read_text())
  self.assertGreaterEqual(len(rows),6)
  # Switch原始Reset/Update均为strb +0x168；不能照PC布局写到ANM2内部。
  import struct
  self.assertEqual(struct.unpack_from('<I',nro,0x41020c)[0],0x3905a27f)
  self.assertEqual(struct.unpack_from('<I',nro,0x41062c)[0],0x3905a268)
  self.assertIn('kModsEditedOffset = 0x168;', (ROOT/'runtime/source/mod_page_nav.hpp').read_text())
  for offset,guard in rows:
   expected=bytes(int(value.strip(),16) for value in guard.split(',') if value.strip())
   self.assertEqual(len(expected),16)
   start=int(offset,16)
   self.assertEqual(nro[start:start+16],expected,f'错误原生入口 {offset}')
