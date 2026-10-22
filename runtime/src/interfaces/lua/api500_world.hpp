#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int TryPushApi500GridField(lua_State*,std::uintptr_t,const char*);
int Api500GridNewIndex(lua_State*);
bool PushApi500GridDesc(lua_State*,std::uintptr_t);
void PushApi500RoomConfig(lua_State*,std::uintptr_t data,std::uintptr_t descriptor);
int Api500PushRoomSpawns(lua_State*,std::uintptr_t data);
int TryPushApi500DescriptorField(lua_State*,std::uintptr_t,const char*);
bool TryWriteApi500DescriptorField(lua_State*,std::uintptr_t,const char*);
int Api500ItemPoolIdentifyPill(lua_State*);
}
