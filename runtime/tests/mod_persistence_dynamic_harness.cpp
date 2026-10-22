#include "mod_persistence.hpp"
#include <chrono>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <map>
#include <string>
#include <vector>

using namespace isaac::runtime;
class Store final : public ISaveFilePort {
public:
    std::map<std::string, std::string> files;
    std::string last;
    int writes = 0;
    unsigned slot = 1;
    Status GetSaveSlot(unsigned* out) noexcept override { *out=slot; return Status::Ok(); }
    bool fail = false;
    bool failAfterComplete = false;
    int reads = 0;
    Status Read(std::string_view name, char* out, std::size_t capacity,
                std::size_t* size) noexcept override {
        ++reads; auto it = files.find(std::string(name));
        if(it == files.end()) return Status{StatusCode::NotFound};
        *size = it->second.size();
        if (*size > capacity) return Status{StatusCode::CapacityExceeded};
        std::memcpy(out, it->second.data(), *size);
        return Status::Ok();
    }
    Status Write(std::string_view name, std::string_view value) noexcept override {
        ++writes; last = std::string(name);
        files[last] = std::string(value.substr(0, fail ? value.size()/2 : value.size()));
        return fail || failAfterComplete ? Status{StatusCode::IoFailure} : Status::Ok();
    }
    Status Remove(std::string_view name) noexcept override {
        files.erase(std::string(name)); return Status::Ok();
    }
    Status Exists(const char*, bool* exists) noexcept override { *exists=false; return Status::Ok(); }
};
int failures=0;
void Check(bool value, const char* message) { if(!value) {++failures;if(failures<30)std::printf("FAIL %s\n",message);} }
void CheckValue(std::uint64_t ns, const std::string& want) {
    const char* data=nullptr; std::size_t size=0;
    Check(ModPersistence::LoadModData(ns,&data,&size)==ModPersistence::Result::Success &&
          size==want.size() && data && std::memcmp(data,want.data(),size)==0,"roundtrip_exact");
}
std::string Legacy(std::uint64_t ns, const std::string& value) {
    std::string file(32+24+value.size(),'\0');
    auto* p=reinterpret_cast<std::uint8_t*>(file.data());
    std::memcpy(p,"ISMODST2",8);
    ModPersistence::detail::WriteU16(p+8,2);ModPersistence::detail::WriteU16(p+10,32);
    ModPersistence::detail::WriteU64(p+12,9);ModPersistence::detail::WriteU32(p+20,1);
    ModPersistence::detail::WriteU32(p+24,24+value.size());
    ModPersistence::detail::WriteU64(p+32,ns);
    ModPersistence::detail::WriteU64(p+40,0x6D6F642D64617461ULL);
    p[48]=1;ModPersistence::detail::WriteU32(p+52,value.size());
    std::memcpy(p+56,value.data(),value.size());
    ModPersistence::detail::WriteU32(p+28,ModPersistence::detail::Checksum(p+32,file.size()-32));
    return file;
}
int main(int argc,char** argv) {
    if(argc!=2) return 2;
    std::ifstream input(argv[1],std::ios::binary);
    std::string large((std::istreambuf_iterator<char>(input)),{});
    Check(large.size()==25183,"real_specialist_structure_25183");
    Store store; SetSessionSaveFilePort(&store); ModPersistence::ResetCacheForTesting();
    Check(ModPersistence::SaveModData(1,large.data(),large.size())==ModPersistence::Result::Success,"25kb_save_succeeds");
    CheckValue(1,large);
    Check(ModPersistence::SaveModData(2,"second",6)==ModPersistence::Result::Success,"second_mod_save");
    CheckValue(1,large); CheckValue(2,"second");
    Check(store.files.size()==2,"two_mods_have_separate_files");
    const int before=store.writes;
    const int readsBefore=store.reads;
    const auto start=std::chrono::steady_clock::now();
    for(int i=0;i<10000;++i) Check(ModPersistence::SaveModData(1,large.data(),large.size())==ModPersistence::Result::Success,"identical_save");
    const auto micros=std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now()-start).count();
    Check(store.writes==before,"identical_data_never_writes");
    Check(store.reads==readsBefore,"identical_data_never_reads");
    ModPersistence::ResetCacheForTesting(); CheckValue(1,large); CheckValue(2,"second");
    Check(ModPersistence::SaveModData(1,"new",3)==ModPersistence::Result::Success,"second_generation");
    store.fail=true;
    Check(ModPersistence::SaveModData(1,"failed",6)==ModPersistence::Result::IoFailure,"torn_write_reports_failure");
    CheckValue(1,"new");
    ModPersistence::ResetCacheForTesting(); CheckValue(1,"new");
    store.fail=false; store.failAfterComplete=true;
    Check(ModPersistence::SaveModData(1,"uncertain",9)==ModPersistence::Result::IoFailure,"commit_failure_reported");
    CheckValue(1,"new");
    ModPersistence::ResetCacheForTesting(); CheckValue(1,"uncertain");
    // 提交结果不确定，但旧完整代次仍保留；不会声称失败一定回滚。
    store.failAfterComplete=false;
    store.files[store.last][12]^=1; // 代次被改但正文完整，头校验必须拒绝。
    ModPersistence::ResetCacheForTesting();CheckValue(1,"new");
    store.files[store.last][12]^=1;
    ModPersistence::ResetCacheForTesting();CheckValue(1,"uncertain");
    Check(ModPersistence::RemoveModData(1)==ModPersistence::Result::Success,"remove_tombstone");
    ModPersistence::ResetCacheForTesting();
    bool has=true;Check(ModPersistence::HasModData(1,&has)==ModPersistence::Result::Success&&!has,"removed_stays_removed_after_restart");
    CheckValue(2,"second");
    store.slot=2; ModPersistence::ResetCacheForTesting();
    has=true; Check(ModPersistence::HasModData(2,&has)==ModPersistence::Result::Success&&!has,"new_slot_has_no_other_slot_data");
    Check(ModPersistence::SaveModData(2,"slot2",5)==ModPersistence::Result::Success,"slot2_save");
    store.slot=1; CheckValue(2,"second");
    store.slot=2; CheckValue(2,"slot2");
    store.slot=0; Check(ModPersistence::SaveModData(2,"slot0",5)==ModPersistence::Result::Success,"startup_slot_zero");
    store.slot=3; Check(ModPersistence::SaveModData(2,"slot3",5)==ModPersistence::Result::Success,"third_slot");
    ModPersistence::ResetCacheForTesting();CheckValue(2,"slot3");
    store.slot=0;CheckValue(2,"slot0");store.slot=1;CheckValue(2,"second");
    Store legacy;legacy.files["isaac-mod-data.bin"]=Legacy(3,"old");
    const std::string original=legacy.files["isaac-mod-data.bin"];
    SetSessionSaveFilePort(&legacy);ModPersistence::ResetCacheForTesting();CheckValue(3,"old");
    legacy.fail=true;
    Check(ModPersistence::SaveModData(3,"failed",6)==ModPersistence::Result::IoFailure,"migration_failure_reported");
    ModPersistence::ResetCacheForTesting();CheckValue(3,"old");legacy.fail=false;
    Check(ModPersistence::SaveModData(3,large.data(),large.size())==ModPersistence::Result::Success,"migrate_large");
    Check(legacy.files["isaac-mod-data.bin"]==original,"legacy_container_preserved");
    ModPersistence::ResetCacheForTesting();CheckValue(3,large);
    Check(ModPersistence::RemoveModData(3)==ModPersistence::Result::Success,"migrated_remove");
    ModPersistence::ResetCacheForTesting();has=true;
    Check(ModPersistence::HasModData(3,&has)==ModPersistence::Result::Success&&!has,"legacy_does_not_resurrect_removed");
    std::printf("DEDUP_10000_US %lld WRITES %d FAILURES %d\n",static_cast<long long>(micros),before,failures);
    return failures?1:0;
}
