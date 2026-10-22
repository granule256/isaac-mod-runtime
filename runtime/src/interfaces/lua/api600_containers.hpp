#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
void RegisterApi600RoomConfigContainers(lua_State*);
void PushApi600SpawnList(lua_State*,std::uintptr_t roomData);
int TryPushApi600SpawnField(lua_State*,int index,const char*key);
void CheckApi600RoomConfigView(lua_State*,int index);
void InheritApi600RoomConfigViewOwner(lua_State*,int sourceIndex,int targetIndex);
int Api600RoomConfigReadOnly(lua_State*);
int Api600RoomConfigEntriesGet(lua_State*);
int Api600RoomConfigEntriesLen(lua_State*);
int Api600RoomConfigSpawnsLen(lua_State*);
}
