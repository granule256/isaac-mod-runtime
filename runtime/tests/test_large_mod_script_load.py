"""Load an intact IsaacScript-sized entry through the real mod loading service."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

DRIVER = r'''
#include "application/mod/mod_load_service.hpp"
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
using namespace isaac::runtime;
namespace {
int failures{};
void Check(bool condition,const char* label) {
    if (!condition) { std::printf("FAIL %s\n",label); ++failures; }
}
struct Content final : IContentPort {
    std::string bytes;
    bool ioFailure{};
    Status Size(std::string_view,std::size_t* size) noexcept override {
        *size=bytes.size(); return Status::Ok();
    }
    Status Read(std::string_view,std::uint8_t* target,std::size_t capacity,
                std::size_t* observed) noexcept override {
        *observed=bytes.size();
        if (ioFailure) return Status{StatusCode::IoFailure};
        if (bytes.size()>capacity) return Status{StatusCode::CapacityExceeded};
        std::memcpy(target,bytes.data(),bytes.size());
        return Status::Ok();
    }
};
struct Lua final : ILuaEnginePort {
    const Content& content;
    const std::uint8_t* shared;
    unsigned calls{};
    std::size_t length{};
    Lua(const Content& c,const std::uint8_t* p):content(c),shared(p){}
    Status Initialize() noexcept override { return Status::Ok(); }
    bool IsReady() const noexcept override { return false; }
    Status RunChunk(const LuaChunk&) noexcept override { return Status::Ok(); }
    Status LoadManifestMod(const ManifestModLoad& load,std::uint32_t*) noexcept override {
        ++calls; length=load.entryLength;
        Check(load.entryBytes==reinterpret_cast<const char*>(shared),"one buffer reused");
        Check(load.entryLength==content.bytes.size(),"source not truncated");
        Check(std::memcmp(load.entryBytes,content.bytes.data(),load.entryLength)==0,
              "all author source bytes reach Lua unchanged");
        return Status::Ok();
    }
    Status CallGlobal(const char*,int,int*) noexcept override { return Status::Ok(); }
    void Shutdown() noexcept override {}
};
}
int main() {
    constexpr std::size_t kAuthorBundleBytes=2698817; // Unmodified WOL author TSTL bundle.
    std::vector<std::uint8_t> storage(kRomfsModScriptMaximumLength+2,0xa5);
    auto* buffer=storage.data()+1;
    Content content;
    Lua lua(content,buffer);
    ModLoadService service(content,lua);
    ResolvedManifestMod resolved{"rom:/isaac_mods/mods/watch/main.lua",
                                 "rom:/isaac_mods/mods/watch","@watch/main.lua",0,true};
    ModLoadRequest request{&resolved,buffer,kRomfsModScriptMaximumLength};
    ModLoadFailure failure;
    content.bytes="--"+std::string(kAuthorBundleBytes-3,'x')+"\n";
    const auto author=service.Load(request,&failure);
    Check(author.ok()&&author.value().entryBytes==kAuthorBundleBytes,
          "2698817-byte unmodified-author-sized Lua entry loads");
    Check(lua.calls==1,"large author entry executes once");
    content.bytes.assign(kRomfsModScriptMaximumLength,'x');
    const auto atLimit=service.Load(request,&failure);
    Check(atLimit.ok()&&atLimit.value().entryBytes==content.bytes.size(),"exact capacity accepted");
    const auto calls=lua.calls;
    content.bytes.push_back('x');
    const auto tooLarge=service.Load(request,&failure);
    Check(tooLarge.code()==StatusCode::CapacityExceeded&&failure.step==ModLoadStep::EntryRead,
          "over-limit file remains an entry-read failure");
    Check(failure.observedBytes==content.bytes.size()&&lua.calls==calls,
          "over-limit length reported without Lua execution");
    Check(storage.front()==0xa5&&storage.back()==0xa5,"buffer bounds preserved");
    content.bytes.clear();
    const auto empty=service.Load(request,&failure);
    Check(empty.code()==StatusCode::Corrupted&&lua.calls==calls,"empty source still rejected");
    content.ioFailure=true;
    content.bytes="-- io failure";
    const auto io=service.Load(request,&failure);
    Check(io.code()==StatusCode::IoFailure&&failure.step==ModLoadStep::EntryRead&&lua.calls==calls,
          "I/O failure retained without Lua execution");
    if (failures) return 1;
    std::printf("PASS author-sized entry, shared buffer, exact limit, overflow, empty, I/O\n");
    return 0;
}
'''


class LargeModScriptLoadTests(unittest.TestCase):
    def test_large_author_bundle_and_error_boundaries(self):
        compiler = shutil.which("c++")
        if compiler is None:
            self.skipTest("C++ compiler unavailable")
        with tempfile.TemporaryDirectory(prefix="large-mod-script-") as directory:
            source = Path(directory) / "main.cpp"
            binary = Path(directory) / "test"
            source.write_text(DRIVER)
            compiled = subprocess.run([
                compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                "-I" + str(ROOT / "runtime/src"), "-I" + str(ROOT / "runtime/source"),
                str(source), str(ROOT / "runtime/src/application/mod/mod_load_service.cpp"),
                "-o", str(binary),
            ], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
