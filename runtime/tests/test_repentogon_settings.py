"""The extension switch is transactional and remains fixed for a game process."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DRIVER = r'''
#include "application/repentogon/repentogon_settings.hpp"
#include "interfaces/repentogon/repentogon_menu.hpp"
#include <cassert>
#include <cstring>
#include <string>
using namespace isaac::runtime;
struct Files final : ISaveFilePort {
    std::string bytes;
    Status read{StatusCode::NotFound}, write{};
    int reads{}, writes{};
    Status Read(std::string_view name,char* out,std::size_t cap,std::size_t* size) noexcept override {
        assert(name==kRepentogonSettingsFile); ++reads; *size=bytes.size();
        if(!read.ok()) return read;
        if(bytes.size()>cap) return Status{StatusCode::CapacityExceeded};
        std::memcpy(out,bytes.data(),bytes.size()); return Status::Ok();
    }
    Status Write(std::string_view name,std::string_view value) noexcept override {
        assert(name==kRepentogonSettingsFile);++writes;
        if(write.ok())bytes=value;return write;
    }
    Status Remove(std::string_view) noexcept override {return Status{StatusCode::Unsupported};}
    Status Exists(const char*,bool*) noexcept override {return Status{StatusCode::Unsupported};}
};
int main() {
    Files files;
    RepentogonSettings settings;
    assert(settings.LoadOnce(&files).ok());
    assert(!settings.Requested()&&!settings.StartupEnabled()&&!settings.NeedsRestart());
    assert(std::strcmp(RepentogonMenuLabel(settings,false),"REPENTOGON: OFF")==0);
    assert(files.writes==0);
    assert(settings.SetEnabled(&files,true).ok());
    assert(settings.Requested()&&!settings.StartupEnabled()&&settings.NeedsRestart());
    assert(std::strcmp(RepentogonMenuLabel(settings,false),"REPENTOGON: ON [RESTART]")==0);
    assert(files.bytes=="isaac-repentogon 1\nenabled 1\n");
    files.read=Status::Ok();
    assert(settings.LoadOnce(&files).ok()&&files.reads==1);
    assert(!settings.StartupEnabled());
    RepentogonSettings restarted;
    assert(restarted.LoadOnce(&files).ok()&&restarted.StartupEnabled());
    assert(std::strcmp(RepentogonMenuLabel(restarted,false),"REPENTOGON: ON [EMPTY]")==0);
    assert(std::strcmp(RepentogonMenuLabel(restarted,true),"REPENTOGON: ON")==0);
    files.write=Status{StatusCode::IoFailure};
    assert(!restarted.SetEnabled(&files,false).ok());
    assert(restarted.Requested()&&!restarted.NeedsRestart());
    files.write=Status::Ok();
    assert(restarted.SetEnabled(&files,false).ok());
    assert(!restarted.Requested()&&restarted.StartupEnabled()&&restarted.NeedsRestart());
    assert(restarted.SetEnabled(&files,true).ok()&&!restarted.NeedsRestart());
    for(const char* bad : {"", "enabled 1\n", "isaac-repentogon 2\nenabled 1\n",
                          "isaac-repentogon 1\nenabled 2\n", "isaac-repentogon 1\nenabled 1\njunk"}) {
        files.bytes=bad;
        RepentogonSettings corrupt;
        assert(!corrupt.LoadOnce(&files).ok());
        assert(!corrupt.Requested()&&!corrupt.StartupEnabled());
    }
    RepentogonSettings unavailable;
    assert(!unavailable.LoadOnce(nullptr).ok());
    assert(!unavailable.SetEnabled(nullptr,true).ok()&&!unavailable.Requested());
}
'''


class RepentogonSettingsTests(unittest.TestCase):
    def test_persistent_restart_scoped_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'settings.cpp'
            source.write_text(DRIVER)
            result = subprocess.run([
                shutil.which('c++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT / 'runtime/src'), str(source),
                str(ROOT / 'runtime/src/application/repentogon/repentogon_settings.cpp'),
                '-o', str(Path(tmp) / 'settings'),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(Path(tmp) / 'settings')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
