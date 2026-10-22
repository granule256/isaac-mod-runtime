#include "mod_persistence.hpp"
#include <chrono>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
using namespace isaac::runtime;
struct Store : ISaveFilePort {
    std::map<std::string,std::string> files;
    std::size_t bytes=0;
    int writes=0;
    Status Read(std::string_view n,char* out,std::size_t cap,std::size_t* size) noexcept override {
        auto it=files.find(std::string(n));if(it==files.end())return Status{StatusCode::NotFound};
        *size=it->second.size();if(*size>cap)return Status{StatusCode::CapacityExceeded};
        std::memcpy(out,it->second.data(),*size);return Status::Ok();
    }
    Status Write(std::string_view n,std::string_view value) noexcept override {
        ++writes;bytes+=value.size();files[std::string(n)]=std::string(value);return Status::Ok();
    }
    Status Remove(std::string_view) noexcept override {return Status::Ok();}
    Status Exists(const char*,bool*) noexcept override {return Status::Ok();}
};
int main() {
    Store store;SetSessionSaveFilePort(&store);ModPersistence::ResetCacheForTesting();
    std::string data(4096,'a');
    if(ModPersistence::SaveModData(1,data.data(),data.size())!=ModPersistence::Result::Success ||
       ModPersistence::SaveModData(2,data.data(),data.size())!=ModPersistence::Result::Success)return 1;
    int writes=store.writes;
    auto start=std::chrono::steady_clock::now();
    for(int i=0;i<100000;++i)if(ModPersistence::SaveModData(1,data.data(),data.size())!=ModPersistence::Result::Success)return 2;
    auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
    if(store.writes!=writes)return 3;
    const auto before=store.bytes;
    if(ModPersistence::SaveModData(1,"new",3)!=ModPersistence::Result::Success)return 4;
    std::printf("DEDUP_100000_NS=%lld UPDATE_ONE_BYTES=%zu DEDUP_WRITES=0\n",static_cast<long long>(ns),store.bytes-before);
}
