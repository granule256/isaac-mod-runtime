#include "interfaces/lua/repentogon_room_mutations.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "program/xml_data_store.hpp"
#include "runtime_constants.hpp"
#include <array>
#include <cstdlib>
#include <cstring>
#include <string>
#include <utility>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
constexpr std::uint8_t kRemoveGuard[]={0x3f,0xfc,0x06,0x71,0x08,0x01,0x00,0x54,0x09,0x4c,0x21,0x8b,0x28,0x0d,0x43,0xf8};
#if defined(__SWITCH__)
constexpr std::uint8_t kBackdropGuard[]={0xff,0x03,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf5,0x13,0x00,0xf9};
api100_native::Cache g_Remove{},g_Backdrop{};
std::uintptr_t g_BackdropFallbackVerifiedBase{};
#else
api100_native::Cache g_Remove{};
#endif
#if !defined(__SWITCH__)
RepentogonRoomMutationNativeTestBindings g_Host{};
#endif
std::uintptr_t Room(lua_State* L) {
    if(!LuaRuntime::IsOnGameThread())luaL_error(L,"Room mutation requires the game thread");
    luaL_checkudata(L,1,LuaRuntime::kRoomMetatable);
    const auto room=ResolveEngineReceiver(L,FieldReceipt::Room,1);
    if(!room)luaL_error(L,"Room reference is no longer available");
    return room;
}

// Switch BackdropConfig starts at Backdrop+0x1D8 with stride 0x148.
// Backdrop::pre_render_walls opens the strings/int block at this layout.
constexpr std::uintptr_t kBackdropConfigBase = 0x1d8;
constexpr std::uintptr_t kBackdropConfigStride = 0x148;
constexpr std::size_t kBackdropConfigStringBytes = 24;
constexpr std::array<std::uintptr_t,11> kBackdropConfigStringOffsets = {
    0x08,0x20,0x38,0x50,0x80,0x98,0xb0,0xc8,0xe0,0xf8,0x110};
constexpr std::uintptr_t kBackdropWallsOffset = 0x68;
constexpr std::uintptr_t kBackdropWallVariantsOffset = 0x6c;
constexpr std::uintptr_t kBackdropFloorsOffset = 0x70;
constexpr std::uintptr_t kBackdropFloorVariantsOffset = 0x74;

struct BackdropXmlConfig {
    std::uint32_t reference{};
    int walls{};
    int wallVariants{};
    int floors{};
    int floorVariants{};
    bool writeGfx{true};
    std::array<std::string,11> strings;
};

enum class BackdropXmlDecision { Native, Apply, Invalid };

RepentogonBackdropInitNative g_BackdropInitFallback{};
std::uint32_t g_BackdropTypeOverride{};

const char* Attribute(const xml_data::XmlRecord& record,const char* name) {
    const auto* value=record.FindAttribute(name);
    return value ? value->value.c_str() : "";
}

int Integer(const char* text) noexcept {
    if(!text||!*text)return 0;
    char* end{};
    const long value=std::strtol(text,&end,0);
    return end!=text?static_cast<int>(value):0;
}

bool EndsWith(const std::string& value,const char* suffix) noexcept {
    const auto size=std::strlen(suffix);
    return value.size()>=size&&std::memcmp(value.data()+value.size()-size,suffix,size)==0;
}

std::string Joined(const char* root,const char* leaf) {
    return std::string(root?root:"")+(leaf?leaf:"");
}

bool IsAnm2Backdrop(std::uint32_t id) noexcept {
    return id==18||id==26||id==35||id==52||id==53||id==54;
}

#if defined(__SWITCH__)
using BackdropFileExists=bool(*)(const char*);
std::uintptr_t g_BackdropFileExistsBase{};
BackdropFileExists g_BackdropFileExists{};

BackdropFileExists ResolveBackdropFileExists() noexcept {
    const auto base=LuaRuntime::EngineModuleBase();
    if(base&&g_BackdropFileExistsBase==base&&g_BackdropFileExists)
        return g_BackdropFileExists;
    if(!base)return nullptr;
    if(!engine_call::VerifyEntryBytes(
           base+kFilesysFileExistsOffset,
           kFilesysFileExistsExpectedBytes.data(),
           kFilesysFileExistsExpectedBytes.size(),
           &engine_memory::EngineMemoryReadable))
        return nullptr;
    g_BackdropFileExistsBase=base;
    g_BackdropFileExists=
        engine_call::AsFunction<BackdropFileExists>(base+kFilesysFileExistsOffset);
    return g_BackdropFileExists;
}
#endif

bool BackdropPathExists(const std::string& path) noexcept {
#if !defined(__SWITCH__)
    return g_Host.backdropPathExists&&g_Host.backdropPathExists(path.c_str());
#else
    const auto exists=ResolveBackdropFileExists();
    return exists&&exists(path.c_str());
#endif
}

BackdropXmlDecision BuildBackdropXmlConfig(std::uint32_t requested,BackdropXmlConfig* output) {
    if(!output)return BackdropXmlDecision::Invalid;
    const auto* record=xml_data::FindEntryById(xml_data::XmlNodeType::Backdrop,
                                               static_cast<int>(requested));
    if(!record)return BackdropXmlDecision::Native;
    const char* source=Attribute(*record,"sourceid");
    if(requested<=60&&std::strcmp(source,"BaseGame")==0)return BackdropXmlDecision::Native;

    const int explicitReference=Integer(Attribute(*record,"reftype"));
    if(explicitReference>60)return BackdropXmlDecision::Invalid;
    std::uint32_t reference=static_cast<std::uint32_t>(explicitReference);
    if(requested>60&&reference<1) {
        reference=std::strcmp(Attribute(*record,"reversewatergfx"),"true")==0?3U:1U;
    } else if(requested<=60) {
        reference=requested;
    }
    if(reference>=63)return BackdropXmlDecision::Invalid;

    BackdropXmlConfig config{};
    config.reference=reference;
    config.walls=Integer(Attribute(*record,"walls"));
    config.wallVariants=Integer(Attribute(*record,"wallvariants"));
    config.floors=Integer(Attribute(*record,"floors"));
    config.floorVariants=Integer(Attribute(*record,"floorvariants"));
    const char* gfxRoot=Attribute(*record,"gfxroot");
    const char* gridRoot=Attribute(*record,"gridgfxroot");
    const char* gfx=Attribute(*record,"gfx");
    config.strings[0]=Joined(gfxRoot,gfx);
    if(IsAnm2Backdrop(reference)) {
        if(!EndsWith(config.strings[0],".anm2")) {
            config.writeGfx=false;
        } else if(!BackdropPathExists(config.strings[0])) {
            return BackdropXmlDecision::Invalid;
        }
    }
    auto imagePath=[&](const char* name,std::string* path) {
        const char* leaf=Attribute(*record,name);
        *path=EndsWith(leaf,".png")?Joined(gfxRoot,leaf):"";
    };
    imagePath("lfloorgfx",&config.strings[1]);
    imagePath("nfloorgfx",&config.strings[2]);
    imagePath("watergfx",&config.strings[3]);
    const char* props=Attribute(*record,"props");
    config.strings[4]=EndsWith(props,".anm2")?Joined(gridRoot,props):"";
    auto gridPath=[&](const char* name,const char* fallback,std::string* path) {
        const char* leaf=Attribute(*record,name);
        *path=EndsWith(leaf,".png")?Joined(gridRoot,leaf):fallback;
    };
    gridPath("rocks","gfx/grid/rocks_basement.png",&config.strings[5]);
    gridPath("pit","gfx/grid/grid_pit.png",&config.strings[6]);
    gridPath("waterpit","gfx/grid/grid_pit_water.png",&config.strings[7]);
    gridPath("bridge","gfx/grid/grid_bridge.png",&config.strings[8]);
    gridPath("door","gfx/grid/door_01_normaldoor.png",&config.strings[9]);
    gridPath("holeinwall","gfx/grid/door_08_holeinwall.png",&config.strings[10]);
    *output=std::move(config);
    return BackdropXmlDecision::Apply;
}

#if defined(__SWITCH__)
using BackdropStringAssign=void*(*)(void*,const char*);
std::uintptr_t g_BackdropStringAssignBase{};
BackdropStringAssign g_BackdropStringAssign{};

BackdropStringAssign ResolveBackdropStringAssign() noexcept {
    if(const auto assign=LuaRuntime::LibcxxStringAssignThunk())return assign;
    const auto base=LuaRuntime::EngineModuleBase();
    if(base&&g_BackdropStringAssignBase==base&&g_BackdropStringAssign)
        return g_BackdropStringAssign;
    if(!base)return nullptr;
    const auto assign=engine_call::ResolveFunction<BackdropStringAssign>(
        base,0x700000,kLibcxxStringAssignOffset,kLibcxxStringAssignExpectedBytes,
        &engine_memory::EngineMemoryReadable);
    g_BackdropStringAssignBase=assign?base:0;
    g_BackdropStringAssign=assign;
    return assign;
}
#endif

bool WriteBackdropString(std::uintptr_t address,const std::string& value) noexcept {
    if(!engine_memory::EngineMemoryWritable(address,kBackdropConfigStringBytes))
        return false;
#if !defined(__SWITCH__)
    if(!g_Host.assignBackdropString)return false;
    g_Host.assignBackdropString(engine_memory::AsObject(address),value.c_str());
    return true;
#else
    const auto assign=ResolveBackdropStringAssign();
    if(!assign)return false;
    assign(engine_memory::AsObject(address),value.c_str());
    return true;
#endif
}

bool WriteBackdropXmlConfig(void* backdrop,const BackdropXmlConfig& config) noexcept {
    const auto base=engine_memory::AddressOf(backdrop);
    if(!base||base>UINTPTR_MAX-kBackdropConfigBase)return false;
    const auto configBase=base+kBackdropConfigBase+
        static_cast<std::uintptr_t>(config.reference)*kBackdropConfigStride;
    for(std::size_t index=0;index<config.strings.size();++index) {
        if(index==0&&!config.writeGfx)continue;
        if(configBase>UINTPTR_MAX-kBackdropConfigStringOffsets[index]||
           !WriteBackdropString(configBase+kBackdropConfigStringOffsets[index],
                                config.strings[index]))return false;
    }
    return engine_memory::WriteField(configBase,kBackdropWallsOffset,config.walls,
                                     engine_memory::EngineMemoryWritable)&&
        engine_memory::WriteField(configBase,kBackdropWallVariantsOffset,config.wallVariants,
                                  engine_memory::EngineMemoryWritable)&&
        engine_memory::WriteField(configBase,kBackdropFloorsOffset,config.floors,
                                  engine_memory::EngineMemoryWritable)&&
        engine_memory::WriteField(configBase,kBackdropFloorVariantsOffset,
                                  config.floorVariants,engine_memory::EngineMemoryWritable);
}
}
bool ApplyRepentogonBackdropInit(void* backdrop,std::uint32_t id,bool loadGraphics,
                                 RepentogonBackdropInitNative native) noexcept {
    if(!native)return false;
    BackdropXmlConfig config{};
    switch(BuildBackdropXmlConfig(id,&config)) {
        case BackdropXmlDecision::Native:
            native(backdrop,id,loadGraphics);
            g_BackdropTypeOverride=id;
            return true;
        case BackdropXmlDecision::Invalid:
            return false;
        case BackdropXmlDecision::Apply:
            if(!WriteBackdropXmlConfig(backdrop,config))return false;
            native(backdrop,config.reference,loadGraphics);
            g_BackdropTypeOverride=id;
            return true;
    }
    return false;
}
void SetRepentogonBackdropInitFallback(RepentogonBackdropInitNative fallback) noexcept {
    g_BackdropInitFallback=fallback;
}
RepentogonBackdropInitNative RepentogonBackdropInitFallback() noexcept {
    return g_BackdropInitFallback;
}
int RepentogonRoomGetBackdropType(lua_State* L) {
    if(lua_gettop(L)!=1)
        return luaL_error(L,"Room:GetBackdropType accepts no arguments");
    luaL_checkudata(L,1,LuaRuntime::kRoomMetatable);
    const auto room=ResolveEngineReceiver(L,FieldReceipt::Room,1);
    if(!room) {
        lua_pushinteger(L,0);
        return 1;
    }
    if(g_BackdropTypeOverride!=0) {
        lua_pushinteger(L,g_BackdropTypeOverride);
        return 1;
    }
    std::uint32_t backdrop{};
    if(!engine_memory::ReadField(room,kRoomBackdropTypeOffset,&backdrop,
                                 engine_memory::EngineMemoryReadable))
        backdrop=0;
    lua_pushinteger(L,backdrop);
    return 1;
}
int RepentogonRoomRemoveGridEntityImmediate(lua_State* L) {
    const auto room=Room(L);
    const auto index=static_cast<std::int32_t>(luaL_checkinteger(L,2));
    const auto trail=static_cast<std::int32_t>(luaL_checkinteger(L,3));
    const bool keep=lua_toboolean(L,4)!=0;
    std::uintptr_t host{};
#if !defined(__SWITCH__)
    if(!g_Host.removeGrid)return luaL_error(L,"Room grid removal host binding is unavailable");
    host=engine_call::AddressOfFunction(g_Host.removeGrid);
#endif
    using Fn=void(*)(void*,std::int32_t,std::int32_t,bool);
    engine_call::AsFunction<Fn>(api100_native::Resolve(L,{0x4883c0,kRemoveGuard},g_Remove,host))(
        engine_memory::AsObject(room),index,trail,keep);
    return 0;
}
int RepentogonRoomSetBackdropType(lua_State* L) {
    const auto room=Room(L);
    const auto id=luaL_checkinteger(L,2);
    if(id<0)return luaL_error(L,"Invalid backdrop id %I",id);
    const auto decoration=luaL_checkinteger(L,3);
    constexpr std::uintptr_t offset=0x1fe0;
    if(room>UINTPTR_MAX-offset)return luaL_error(L,"Room backdrop address is invalid");
    using Fn=RepentogonBackdropInitNative;
    Fn native=RepentogonBackdropInitFallback();
#if !defined(__SWITCH__)
    if(!native) {
        if(!g_Host.initBackdrop)return luaL_error(L,"Room backdrop host binding is unavailable");
        native=g_Host.initBackdrop;
    }
#else
    std::uintptr_t host{};
    if(native) {
        const auto base=LuaRuntime::EngineModuleBase();
        if(base==0||base>UINTPTR_MAX-0x26e80-16)
            return luaL_error(L,"Room backdrop entry is invalid");
        if(g_BackdropFallbackVerifiedBase!=base) {
            if(!engine_call::VerifyEntryBytes(base+0x26e80,kBackdropGuard,sizeof(kBackdropGuard),
                    &engine_memory::EngineMemoryReadable))
                return luaL_error(L,"Room backdrop entry guard mismatch");
            g_BackdropFallbackVerifiedBase=base;
        }
    } else {
        native=engine_call::AsFunction<Fn>(
            api100_native::Resolve(L,{0x26e80,kBackdropGuard},g_Backdrop,host));
    }
#endif
    if(!ApplyRepentogonBackdropInit(engine_memory::AsObject(room+offset),
            static_cast<std::uint32_t>(id),decoration!=0,native))
        return luaL_error(L,"Invalid custom backdrop configuration for id %I",id);
    return 0;
}
int RepentogonRoomSetRail(lua_State* L) {
    const auto room=Room(L);
    if(lua_gettop(L)!=3)return luaL_error(L,"Room:SetRail expects a grid index and rail type");
    const auto index=luaL_checkinteger(L,2);
    const auto rail=luaL_checkinteger(L,3);
    std::int32_t width{},height{};
    if(!engine_memory::ReadField(room,kRoomGridWidthOffset,&width,
                                 engine_memory::EngineMemoryReadable)||
       !engine_memory::ReadField(room,kRoomGridHeightOffset,&height,
                                 engine_memory::EngineMemoryReadable)||
       width<=0||height<=0||
       static_cast<std::uint64_t>(width)*static_cast<std::uint64_t>(height)>0x10000)
        return luaL_error(L,"Room grid dimensions are unavailable");
    if(index<0||index>=static_cast<lua_Integer>(width)*height)
        return luaL_error(L,"Invalid grid index %I",index);
    // Room::Init constructs the embedded RailManager at Room+0x7c78. Its
    // variant array starts at +8 and RailManager::Init clears 0x1c0 bytes.
    // Pinned libzhl Room::IsValidRailType includes carts, mineshaft and
    // door rails plus the 255 clear sentinel, not every low-nibble variant.
    const bool validRail=(rail>=0&&rail<=10)||rail==16||rail==17||
        rail==32||rail==33||(rail>=80&&rail<=85)||(rail>=96&&rail<=101)||
        rail==112||rail==113||rail==144||rail==145||rail==160||rail==161||rail==255;
    if(!validRail)return luaL_error(L,"Invalid rail type %I",rail);
    if(index>=0x1c0)return luaL_error(L,"Rail index exceeds the room rail array");
    constexpr std::uintptr_t kRailVariantsOffset=0x7c80;
    if(!engine_memory::WriteField(room,
            kRailVariantsOffset+static_cast<std::uintptr_t>(index),
            static_cast<std::uint8_t>(rail),engine_memory::EngineMemoryWritable))
        return luaL_error(L,"Room rail array is not writable");
    return 0;
}
#if !defined(__SWITCH__)
void SetRepentogonRoomMutationNativeTestBindings(RepentogonRoomMutationNativeTestBindings value) noexcept {g_Host=value;}
#endif
}
