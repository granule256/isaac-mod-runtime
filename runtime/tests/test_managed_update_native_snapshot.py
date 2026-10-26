"""直接编译生产快照adapter，验证原生IsPaused ABI和同一Game的真实帧字段。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_support

ROOT=Path(__file__).resolve().parents[2]
SOURCE=r'''
#include "infrastructure/call/managed_update_snapshot.hpp"
#include <cassert>
#include <cstring>
#include <vector>
using namespace isaac::runtime;
static std::uintptr_t expectedGame{};
static bool paused{},readableGame=true,readableFrame=true;
static unsigned calls{},reads{},frameReads{};
static bool NativePaused(const void*game){assert(reinterpret_cast<std::uintptr_t>(game)==expectedGame);++calls;return paused;}
static bool Readable(std::uintptr_t address,std::size_t length){
 ++reads;
 if(address==expectedGame&&length==sizeof(std::uintptr_t))return readableGame;
 assert(address==expectedGame+0x24f99c&&length==4);++frameReads;return readableFrame;
}
int main(){
 std::vector<unsigned char> game(0x24f9ac);expectedGame=reinterpret_cast<std::uintptr_t>(game.data());
 const auto thunk=reinterpret_cast<std::uintptr_t>(&NativePaused);ManagedUpdateSnapshot out{};
 std::uint32_t frame=5744;std::memcpy(game.data()+0x24f99c,&frame,4);
 assert(ReadNativeManagedUpdateSnapshot(expectedGame,thunk,0x24f99c,&out,Readable));
 assert(out.game==expectedGame&&out.frame==5744&&calls==1&&reads==2&&frameReads==1);
 paused=true;reads=frameReads=0;
 assert(!ReadNativeManagedUpdateSnapshot(expectedGame,thunk,0x24f99c,&out,Readable));
 assert(out.game==0&&calls==2&&reads==1&&frameReads==0);
 paused=false;frame=0;std::memcpy(game.data()+0x24f99c,&frame,4);
 assert(ReadNativeManagedUpdateSnapshot(expectedGame,thunk,0x24f99c,&out,Readable)&&out.frame==0);
 readableFrame=false;assert(!ReadNativeManagedUpdateSnapshot(expectedGame,thunk,0x24f99c,&out,Readable)&&out.game==0);
 readableGame=false;const auto before=calls;assert(!ReadNativeManagedUpdateSnapshot(expectedGame,thunk,0x24f99c,&out,Readable)&&calls==before);
 assert(!ReadNativeManagedUpdateSnapshot(expectedGame,0,0x24f99c,&out,Readable));
 assert(!ReadNativeManagedUpdateSnapshot(0,thunk,0x24f99c,&out,Readable));
 assert(!ReadNativeManagedUpdateSnapshot(expectedGame,thunk,0x24f99c,nullptr,Readable));
}
'''


class ManagedUpdateNativeSnapshotTests(unittest.TestCase):
    def test_real_native_snapshot_adapter(self):
        with tempfile.TemporaryDirectory(prefix='managed-update-native-') as tmp:
            path=Path(tmp);(path/'main.cpp').write_text(SOURCE)
            result=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/src'),
                                   str(path/'main.cpp'),'-o',str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
