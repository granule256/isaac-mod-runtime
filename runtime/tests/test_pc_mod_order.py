"""原版显示名字节排序、批次路径所有权及过滤后的真实宿主回归。"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include "pc_mod_order.hpp"
#include "application/mod/mod_toggle_service.hpp"
#include <cstdio>
#include <cstring>
#include <algorithm>
using namespace isaac::runtime;
static ResolvedManifestModBatch batch;
static int reads;
static const char* labels[] = {"z", "!! MCM", "! A", "A B", "a", "A", "A0", "0", "！全角", "中文", "!", "A", " Custom Stage API", "!CuerLib"};
bool Reader(void*, const char* path, char* out, std::size_t cap, std::size_t* n) {
    ++reads;
    unsigned i = 99;
    if (std::sscanf(path, "isaac_mods/mods/d%u/metadata.xml", &i) != 1 || i >= 14) return false;
    *n = std::snprintf(out, cap, "<metadata><name>%s</name></metadata>", labels[i]);
    return true;
}
int main() {
    const char* expected[] = {"Custom Stage API", "!", "! A", "!! MCM", "!CuerLib", "0", "A", "A", "A B", "A0", "a", "d14", "z", "中文", "！全角"};
    for (unsigned round = 0; round < 33; ++round) {
        batch.count = 15;
        for (unsigned i = 0; i < batch.count; ++i) {
            unsigned id = (i + round) % 15;
            auto& p = batch.paths[i];
            std::snprintf(p.modRoot.data(), p.modRoot.size(), "rom:/isaac_mods/mods/d%u", id);
            std::snprintf(p.entryPath.data(), p.entryPath.size(), "entry%u", id);
            std::snprintf(p.chunkName.data(), p.chunkName.size(), "chunk%u", id);
            batch.mods[i] = {p.entryPath.data(), p.modRoot.data(), p.chunkName.data(), id + 100, id != 1};
        }
        ModPageEntrySource names[ResolvedManifestModBatch::kCapacity]{};
        char arena[8192]{}, path[kModPageMetadataPathCapacity]{}, xml[kModPageMetadataCapacity]{};
        reads = 0;
        if (!CollectAndSortPcModNames(batch, Reader, nullptr, names, arena, sizeof(arena), path, xml)) return 1;
        if (reads != 15) return 2;
        for (unsigned i = 0; i < batch.count; ++i) {
            if (std::strcmp(names[i].displayName, expected[i])) { std::printf("name %u: %s\n", i, names[i].displayName); return 3; }
            unsigned id = 99;
            auto& p = batch.paths[i]; auto& m = batch.mods[i];
            std::sscanf(m.modRoot, "rom:/isaac_mods/mods/d%u", &id);
            if (m.modRoot != p.modRoot.data() || m.manifestBytes != id + 100 || m.hasEntry != (id != 1)) return 4;
            if (m.hasEntry) {
                if (m.entryPath != p.entryPath.data() || m.chunkName != p.chunkName.data()) return 5;
                char entry[40]; std::snprintf(entry, sizeof(entry), "entry%u", id);
                if (std::strcmp(entry, m.entryPath)) return 6;
            } else if (*m.entryPath || *m.chunkName) return 7;
        }
        struct Files final : ISaveFilePort {
            Status Read(std::string_view, char*, std::size_t, std::size_t*) noexcept override { return Status{StatusCode::NotFound}; }
            Status Write(std::string_view, std::string_view) noexcept override { return Status::Ok(); }
            Status Remove(std::string_view) noexcept override { return Status::Ok(); }
            Status Exists(const char*, bool* out) noexcept override { *out = false; return Status::Ok(); }
        } files;
        ModToggleService toggles(files);
        if (!toggles.SetEnabled("d10", false).ok() || !toggles.SetEnabled("d0", false).ok()) return 8;
        if (toggles.ApplyToBatch(&batch) != 2 || batch.count != 13) return 12;
        if (std::strcmp(batch.mods[0].modRoot, "rom:/isaac_mods/mods/d12")) return 13;
        for (std::size_t i = 0; i < batch.count; ++i) {
            unsigned id = 99;
            std::sscanf(batch.mods[i].modRoot, "rom:/isaac_mods/mods/d%u", &id);
            if (id == 10 || id == 0 || id + 100 != batch.mods[i].manifestBytes || batch.mods[i].modRoot != batch.paths[i].modRoot.data()) return 14;
        }
    }
    if (ComparePcModNames(" A", "!") >= 0 || ComparePcModNames("A", "a") >= 0 || ComparePcModNames("! Z", "!! A") >= 0 || ComparePcModNames("A", "A0") >= 0 || ComparePcModNames("same", "same") != 0) return 9;
    // 失败不得留下部分重排；0项有效。
    ModPageEntrySource names[ResolvedManifestModBatch::kCapacity]{};
    char arena[1]{}, path[kModPageMetadataPathCapacity]{}, xml[kModPageMetadataCapacity]{};
    auto first = batch.mods[0].modRoot;
    if (CollectAndSortPcModNames(batch, Reader, nullptr, names, arena, sizeof(arena), path, xml) || batch.mods[0].modRoot != first) return 10;
    batch.count = 0;
    if (!CollectAndSortPcModNames(batch, Reader, nullptr, names, arena, sizeof(arena), path, xml)) return 11;
    // Published display names must outlive path compaction after filtering.
    batch.count=2;
    for(unsigned i=0;i<2;++i){
        std::snprintf(batch.paths[i].modRoot.data(),batch.paths[i].modRoot.size(),"rom:/isaac_mods/mods/d%u",i);
        batch.mods[i]={"",batch.paths[i].modRoot.data(),"",0,false};
    }
    auto whitespace=[](void*,const char* file,char* out,std::size_t cap,std::size_t* n){
        const char* label=std::strstr(file,"d0/")?"  ":"z";
        *n=std::snprintf(out,cap,"<name>%s</name>",label);return true;
    };
    char stable[256]{};
    if(!CollectAndSortPcModNames(batch,whitespace,nullptr,names,stable,sizeof(stable),path,xml))return 15;
    auto published=names[0].displayName;
    if(std::strcmp(published,"d0"))return 16;
    std::strcpy(batch.paths[0].modRoot.data(),"rom:/isaac_mods/mods/other");
    if(std::strcmp(published,"d0"))return 17;
    std::puts("PC_MOD_ORDER_PASSED");
}
'''
class PcModOrderTests(unittest.TestCase):
    def test_real_batch_order_and_pointer_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'main.cpp'
            src.write_text(HARNESS)
            binary = Path(tmp) / 'check'
            result = subprocess.run([shutil.which('c++'), '-std=c++23', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT/'runtime/source'), '-I', str(ROOT/'runtime/src'), str(src), str(ROOT/'runtime/src/application/mod/mod_toggle_service.cpp'), str(ROOT/'runtime/src/domain/mod/mod_toggle_state.cpp'), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PC_MOD_ORDER_PASSED', result.stdout)
if __name__ == '__main__':
    unittest.main()

# 同数量换序、显示名缓存与开关目录映射：链接真实菜单API和Lua，不复制实现。
API_HARNESS = r'''
#include "interfaces/lua/mod_menu_api.hpp"
#include "application/mod/mod_toggle_service.hpp"
#include <cstring>
using namespace isaac::runtime;
struct Files final : ISaveFilePort {
 Status Read(std::string_view,char*,std::size_t,std::size_t*)noexcept override{return Status{StatusCode::NotFound};}
 Status Write(std::string_view,std::string_view)noexcept override{return Status::Ok();}
 Status Remove(std::string_view)noexcept override{return Status::Ok();}
 Status Exists(const char*,bool* out)noexcept override{*out=false;return Status::Ok();}
};
int main() {
 Files files;ModToggleService toggles(files);ModMenuAttachToggles(&toggles);
 ResolvedManifestModBatch batch{};batch.count=2;
 batch.mods[0].modRoot="rom:/isaac_mods/mods/z-dir";
 batch.mods[1].modRoot="rom:/isaac_mods/mods/a-dir";
 const char* names[]={"!! first", "last"};
 auto generation=ModMenuDiscoveryGeneration();
 ModMenuPublishDiscovered(batch,names);
 if(ModMenuDiscoveryGeneration()==generation || std::strcmp(ModMenuDiscoveredDisplayName(0),"!! first"))return 1;
 if(!ModMenuSetEnabled(ModMenuDiscoveredDirectory(0),false) || toggles.IsEnabled("z-dir")==true || !toggles.IsEnabled("a-dir"))return 2;
 generation=ModMenuDiscoveryGeneration();
 batch.mods[0].modRoot="rom:/isaac_mods/mods/a-dir";
 batch.mods[1].modRoot="rom:/isaac_mods/mods/z-dir";
 const char* renamed[]={"! new", "old"};
 ModMenuPublishDiscovered(batch,renamed);
 if(ModMenuDiscoveredCount()!=2 || ModMenuDiscoveryGeneration()==generation || std::strcmp(ModMenuDiscoveredDisplayName(0),"! new"))return 3;
 if(!ModMenuDiscoveredEnabled(ModMenuDiscoveredDirectory(0)) || ModMenuDiscoveredEnabled(ModMenuDiscoveredDirectory(1)))return 4;
 ModMenuPublishDiscovered(batch);
 if(std::strcmp(ModMenuDiscoveredDisplayName(0),"a-dir") || ModMenuDiscoveredDisplayName(2)!=nullptr)return 5;
 return 0;
}
'''
class PcModMenuPublishedOrderTests(unittest.TestCase):
    def test_published_names_generation_and_toggle_directory(self):
        from .test_support import build_lua_harness
        with tempfile.TemporaryDirectory() as tmp:
            binary = build_lua_harness(source_root=ROOT/'runtime/source',workdir=Path(tmp),harness_source=API_HARNESS)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
