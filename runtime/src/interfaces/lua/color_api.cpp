#include "interfaces/lua/api100_bindings.hpp"
#include "interfaces/lua/color_api.hpp"

#include "interfaces/lua/owner_binding.hpp"

#include "lua_object_handles.hpp"

#include <cstring>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {

using LuaRuntime::ColorHandle;
using LuaRuntime::kColorMetatable;

constexpr char kColorOwner[] = "Color";
constexpr LuaHandlerBinding kColorMethods[] = {{0x0E011020, &ColorSetColorize},{0x0E011021, &ColorLerp}};

// The colour fields a Mod reads back. PC exposes the four components as floats in 0..1.
struct ColorField {
    const char* name;
    std::size_t offset;
};

// PC 的 `KColor` 字段是**长名**：`Red`/`Green`/`Blue`/`Alpha`。短名 `R/G/B/A` 属于另一个类
// （`Color`），两者很容易混。这一条是拿真实 Mod 的证据改过来的：EID 全程写
// `color.Red`/`color.Alpha`（`analysis/pc-mod-contract/…/external item descriptions_836319872/
// features/eid_api.lua:1440`、`main.lua:232`），而本实现原先只认短名 —— 结果 EID 那种写法会在
// 赋值处直接报错。短名保留为**别名**：PC 上能跑的 Mod 不会因此失效，多接受一组名字没有代价。
//
// 批次 3 追加 `RO`/`GO`/`BO`（PC `Color` 文档的变量名，
// `analysis/isaacdocs-snapshot/docs/Color.md:115`–`141`）：三个颜色**偏移**分量，与
// `Color(R,G,B,A,RO,GO,BO)` 构造函数的后三个参数对应。
constexpr ColorField kColorFields[] = {
    {"Red", offsetof(ColorHandle, red)},
    {"Green", offsetof(ColorHandle, green)},
    {"Blue", offsetof(ColorHandle, blue)},
    {"Alpha", offsetof(ColorHandle, alpha)},
    {"R", offsetof(ColorHandle, red)},
    {"G", offsetof(ColorHandle, green)},
    {"B", offsetof(ColorHandle, blue)},
    {"A", offsetof(ColorHandle, alpha)},
    {"RO", offsetof(ColorHandle, offsetRed)},
    {"GO", offsetof(ColorHandle, offsetGreen)},
    {"BO", offsetof(ColorHandle, offsetBlue)},
};

// 文档化的 `KColor` 常量（`analysis/isaacdocs-snapshot/docs/KColor.md` 的 Constants 一节）。
struct ColorConstant {
    const char* name;
    float red;
    float green;
    float blue;
    float alpha;
};

constexpr ColorConstant kColorConstants[] = {
    {"Black", 0.0f, 0.0f, 0.0f, 1.0f},
    {"Red", 1.0f, 0.0f, 0.0f, 1.0f},
    {"Green", 0.0f, 1.0f, 0.0f, 1.0f},
    {"Blue", 0.0f, 0.0f, 1.0f, 1.0f},
    {"Yellow", 1.0f, 1.0f, 0.0f, 1.0f},
    {"Cyan", 0.0f, 1.0f, 1.0f, 1.0f},
    {"Magenta", 1.0f, 0.0f, 1.0f, 1.0f},
    {"White", 1.0f, 1.0f, 1.0f, 1.0f},
    {"Transparent", 0.0f, 0.0f, 0.0f, 0.0f},
};

}  // namespace

int ColorIndex(lua_State* state) {
    auto* color = RequireColorArgument(state, 1);
    const char* field = luaL_checkstring(state, 2);
    for (const ColorField& candidate : kColorFields) {
        if (std::strcmp(candidate.name, field) == 0) {
            const auto* value = reinterpret_cast<const float*>(
                reinterpret_cast<const unsigned char*>(color) + candidate.offset);
            lua_pushnumber(state, static_cast<lua_Number>(*value));
            return 1;
        }
    }
    if (std::strcmp(field, "__mul") == 0) {
        lua_pushcfunction(state, ColorMultiply);
        return 1;
    }
    luaL_getmetatable(state,kColorMetatable);lua_getfield(state,-1,"__methods");
    if(lua_istable(state,-1)){lua_pushvalue(state,2);lua_rawget(state,-2);}else lua_pushnil(state);
    return 1;
}

int ColorNewIndex(lua_State* state) {
    auto* color = RequireColorArgument(state, 1);
    if (lua_type(state, 2) != LUA_TSTRING) {
        return luaL_error(state, "KColor fields are R, G, B and A");
    }
    const char* field = lua_tostring(state, 2);
    for (const ColorField& candidate : kColorFields) {
        if (std::strcmp(candidate.name, field) != 0) {
            continue;
        }
        if (!lua_isnumber(state, 3)) {
            return luaL_error(state, "KColor.%s must be a number", field);
        }
        auto* value = reinterpret_cast<float*>(
            reinterpret_cast<unsigned char*>(color) + candidate.offset);
        *value = static_cast<float>(lua_tonumber(state, 3));
        return 0;
    }
    return luaL_error(state, "KColor has no writable field named %s", field);
}

// 构造器。全局 `KColor` 与 `Color` 都是可调用的**类表**（同一个表，见
// `lua_runtime.cpp` 的 `RegisterColorApi`），所以本函数要应付两种栈形状：
// 经 `__call` 时是 (类表, R, G, B[, A[, RO, GO, BO]])，直接调用时是 (R, G, B[, …])。
//
// 接受 3..7 个数字：PC 的签名是
// `Color(R, G, B, A = 1, RO = 0, GO = 0, BO = 0)`
// （`analysis/isaacdocs-snapshot/docs/Color.md:27`），而 `KColor` 只有前四个
// （`KColor.md:16`）。EID 两种都在用：`KColor(0,0.67,0.93,1)`（`eid_api.lua:199`）与
// `Color(1,1,1,1,r/repDiv,g/repDiv,b/repDiv)`（`eid_api.lua:1369`、`main.lua:960`）。
int CreateColorHandle(lua_State* state) {
    const int arguments = lua_gettop(state);
    const int first = (arguments >= 4 && arguments <= 8 && lua_istable(state, 1)) ? 2 : 1;
    const int given = arguments - (first - 1);
    if (given < 3 || given > 7) {
        return luaL_error(
            state, "Color accepts red, green, blue and an optional alpha and three offsets");
    }
    for (int index = 0; index < given; ++index) {
        // PC main.lua 的构造包装对每个可选参数分别用 `value or default`。
        if (index >= 3 && !lua_toboolean(state, first + index)) {
            continue;
        }
        if (!lua_isnumber(state, first + index)) {
            return luaL_error(
                state, "Color accepts red, green, blue and an optional alpha and three offsets");
        }
    }
    auto* color = static_cast<ColorHandle*>(lua_newuserdata(state, sizeof(ColorHandle)));
    *color = {};
    color->red = static_cast<float>(lua_tonumber(state, first));
    color->green = static_cast<float>(lua_tonumber(state, first + 1));
    color->blue = static_cast<float>(lua_tonumber(state, first + 2));
    color->alpha = given >= 4 && lua_toboolean(state, first + 3)
                       ? static_cast<float>(lua_tonumber(state, first + 3)) : 1.0f;
    // 后三个（颜色偏移）只在句柄里保存：`font_api` 送给引擎的仍然是起头的 16 字节 RGBA。
    color->offsetRed = given >= 5 ? static_cast<float>(lua_tonumber(state, first + 4)) : 0.0f;
    color->offsetGreen = given >= 6 ? static_cast<float>(lua_tonumber(state, first + 5)) : 0.0f;
    color->offsetBlue = given >= 7 ? static_cast<float>(lua_tonumber(state, first + 6)) : 0.0f;
    luaL_getmetatable(state, kColorMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

std::size_t AttachColorMethods(lua_State* state) noexcept {
    // `KColor` is read through `__index`, so it owns no method table of its own yet; the
    // catalog-driven attach still runs so a future method lands here without touching Lua
    // registration code.
    return AttachApi100Methods(state,"Color") + AttachOwnerMethods(state,kColorOwner,kColorMethods,sizeof(kColorMethods)/sizeof(kColorMethods[0]));
}

// `KColor` 类表的 `__index`：文档化的 9 个常量。每次读取都产出**新**的颜色值 —— 共享同一个
// userdata 会让某个 Mod 的 `KColor.White.Alpha = 0` 改坏所有 Mod 看到的常量。
int KColorClassIndex(lua_State* state) {
    if (lua_type(state, 2) != LUA_TSTRING) {
        lua_pushnil(state);
        return 1;
    }
    const char* field = lua_tostring(state, 2);
    if(std::strcmp(field,"Lerp")==0){PushHandler(state,ColorLerp,0,0x0E011021);return 1;}
    for (const ColorConstant& candidate : kColorConstants) {
        if (std::strcmp(candidate.name, field) != 0) {
            continue;
        }
        auto* color = static_cast<ColorHandle*>(lua_newuserdata(state, sizeof(ColorHandle)));
        *color = {};
        color->red = candidate.red;
        color->green = candidate.green;
        color->blue = candidate.blue;
        color->alpha = candidate.alpha;
        // 常量没有颜色偏移（`KColor.White` 等就是纯 RGBA）——顺带把整块内存初始化干净。
        color->offsetRed = 0.0f;
        color->offsetGreen = 0.0f;
        color->offsetBlue = 0.0f;
        luaL_getmetatable(state, kColorMetatable);
        lua_setmetatable(state, -2);
        return 1;
    }
    lua_pushnil(state);
    return 1;
}

int ColorSetColorize(lua_State* state) {
    auto* color=RequireColorArgument(state,1);
    // PC65AEB0直接存入四个float，不夹值，不改变tint/offset。
    const float r=static_cast<float>(luaL_checknumber(state,2));
    const float g=static_cast<float>(luaL_checknumber(state,3));
    const float b=static_cast<float>(luaL_checknumber(state,4));
    const float amount=static_cast<float>(luaL_checknumber(state,5));
    color->colorizeRed=r;color->colorizeGreen=g;color->colorizeBlue=b;color->colorizeAmount=amount;return 0;
}
int ColorLerp(lua_State* state) {
    auto* a=RequireColorArgument(state,1);
    auto* b=RequireColorArgument(state,2);
    const float t=static_cast<float>(luaL_checknumber(state,3));
    auto* out=static_cast<ColorHandle*>(lua_newuserdata(state,sizeof(ColorHandle)));
    // PC65B210对全部11格做(1-t)*a+t*b，t允许外插，保持独立返回值。
    static_assert(sizeof(ColorHandle)==11*sizeof(float));
    float inputA[11],inputB[11],result[11];std::memcpy(inputA,a,sizeof(inputA));std::memcpy(inputB,b,sizeof(inputB));
    for(unsigned i=0;i<11;++i){const float first=(1.0f-t)*inputA[i];const float second=t*inputB[i];result[i]=first+second;}
    std::memcpy(out,result,sizeof(result));luaL_getmetatable(state,kColorMetatable);lua_setmetatable(state,-2);return 1;
}

int ColorMultiply(lua_State* state) {
    auto* left = RequireColorArgument(state, 1);
    // PC844990先复制右值；自乘或两个引用指向同一根值时也必须保留原输入。
    const ColorHandle right = *RequireColorArgument(state, 2);
    left->red *= right.red;
    left->green *= right.green;
    left->blue *= right.blue;
    left->alpha *= right.alpha;
    // PC65B0F0：右染色RGB和为零则保留左染色；左和为零则复制右染色，
    // 否则平均四格。染色强度本身不参与“是否存在染色”的判断。
    if ((right.colorizeRed + right.colorizeGreen) + right.colorizeBlue != 0.0f) {
        if ((left->colorizeRed + left->colorizeGreen) + left->colorizeBlue == 0.0f) {
            left->colorizeRed = right.colorizeRed;
            left->colorizeGreen = right.colorizeGreen;
            left->colorizeBlue = right.colorizeBlue;
            left->colorizeAmount = right.colorizeAmount;
        } else {
            left->colorizeRed = (left->colorizeRed + right.colorizeRed) * 0.5f;
            left->colorizeGreen = (left->colorizeGreen + right.colorizeGreen) * 0.5f;
            left->colorizeBlue = (left->colorizeBlue + right.colorizeBlue) * 0.5f;
            left->colorizeAmount = (left->colorizeAmount + right.colorizeAmount) * 0.5f;
        }
    }
    left->offsetRed += right.offsetRed;
    left->offsetGreen += right.offsetGreen;
    left->offsetBlue += right.offsetBlue;
    auto* reference = static_cast<ColorReferenceHandle*>(
        lua_newuserdata(state, sizeof(ColorReferenceHandle)));
    reference->value = left;
    luaL_getmetatable(state, kColorMetatable);
    lua_setmetatable(state, -2);
    // 直接持有根对象，避免 a=a*b 的每次调用保留上一层引用而形成长链。
    if (lua_rawlen(state, 1) == sizeof(ColorReferenceHandle)) lua_getuservalue(state, 1);
    else lua_pushvalue(state, 1);
    lua_setuservalue(state, -2);
    return 1;
}
} // namespace isaac::runtime
