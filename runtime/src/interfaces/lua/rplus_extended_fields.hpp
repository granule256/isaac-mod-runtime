#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
// 名字先筛选；未知名字不读取实体、不进行分类、不扫描布局。
int TryPushExtendedEntityField(lua_State*,std::uintptr_t entity,const char* name);
bool TryWriteExtendedEntityField(lua_State*,std::uintptr_t entity,const char* name);
int TryPushExtendedItemConfigField(lua_State*,std::uintptr_t item,const char* name);
bool TryWriteExtendedItemConfigField(lua_State*,std::uintptr_t item,const char* name);
int TryPushExtendedSpriteField(lua_State*,const char* name);
bool TryWriteExtendedSpriteField(lua_State*,const char* name);
// 调用者必须传入已经核对生命周期的实际RoomDescriptor实例，不能替换成当前房间。
int TryPushExtendedRoomDescriptorField(lua_State*,std::uintptr_t descriptor,const char* name);
bool TryWriteExtendedRoomDescriptorField(lua_State*,std::uintptr_t descriptor,const char* name);
#if !defined(__SWITCH__)
struct ExtendedFieldsNativeTestBindings {
 void (*setTarget)(void*,void*){};
 void (*setChild)(void*,void*){};
 void (*setTearHeight)(void*,float){};
 void (*setParent)(void*,void*){};
 void (*setSpawner)(void*,void*){};
};
void SetExtendedFieldsNativeTestBindings(ExtendedFieldsNativeTestBindings) noexcept;
#endif
}
