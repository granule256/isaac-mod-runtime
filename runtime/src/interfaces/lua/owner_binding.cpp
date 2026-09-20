#include "interfaces/lua/owner_binding.hpp"

#include "interfaces/lua/runtime_perf.hpp"

#include <cstring>

extern "C" {
#include <lauxlib.h>
}


namespace {

//: 中央计时包装本体（批次 093）：取一次 tick → 调用被包的函数 → 记一笔 → 原样返回结果。
//:
//: `lua_call` 会把错误**原样向上抛**（`longjmp`）—— 这一层刻意不做捕获，也不做清理：
//: 一旦捕获，模组看到的错误位置与调用栈就变了，那是"为了测量改了行为"。
#if PERF_API_WRAPPER
int TimedHandlerWrapper(lua_State* state) {
    const std::uint32_t identifier =
        static_cast<std::uint32_t>(lua_tointeger(state, lua_upvalueindex(2)));
    const int argumentCount = lua_gettop(state);
    const std::uint64_t startedAt = isaac::runtime::RuntimePerfTick();
    lua_pushvalue(state, lua_upvalueindex(1));  // 被包的函数
    lua_insert(state, 1);                       // 放到最前面，当被调函数
    lua_call(state, argumentCount, LUA_MULTRET);
    const int resultCount = lua_gettop(state);
    IsaacRuntime_PerfNoteApiCall(isaac::runtime::RuntimePerfApiBucketKey(identifier), startedAt);
    return resultCount;
}
#endif  // PERF_API_WRAPPER

} // namespace

namespace isaac::runtime {

#if PERF_API_WRAPPER
void PushTimedHandler(lua_State* state, lua_CFunction handler, std::size_t upvalueCount,
                      std::uint32_t identifier) noexcept {
    lua_pushcclosure(state, handler, static_cast<int>(upvalueCount));  // 栈：inner
    lua_pushinteger(state, static_cast<lua_Integer>(identifier));      // 栈：inner, id
    // upvalue1 = 被包的函数（可能是带自己上值的闭包）、upvalue2 = 它的接口 id。
    lua_pushcclosure(state, &TimedHandlerWrapper, 2);
}
#endif  // PERF_API_WRAPPER

void PushHandler(lua_State* state, lua_CFunction handler, std::size_t upvalueCount,
                 std::uint32_t identifier) noexcept {
#if PERF_API_WRAPPER
    PushTimedHandler(state, handler, upvalueCount, identifier);
#else
    static_cast<void>(identifier);  // 不包装时用不到（逐接口读数需要 PERF_API_WRAPPER=1）
    lua_pushcclosure(state, handler, static_cast<int>(upvalueCount));
#endif
}

std::size_t AttachOwnerMethods(lua_State* state, const char* owner,
                               const LuaHandlerBinding* bindings,
                               std::size_t count,
                               const FieldApiRow* fieldRows,
                               std::size_t rowCount,
                               const EngineMethodRow* engineRows,
                               std::size_t engineRowCount) noexcept {
    if (state == nullptr || owner == nullptr) {
        return 0;
    }
    const ApiCatalog& catalog = ApiCatalog::Default();
    std::size_t attached = 0;
    for (std::size_t index = 0; index < catalog.Count(); ++index) {
        const LuaApiDescriptor* descriptor = catalog.At(index);
        if (descriptor == nullptr || std::strcmp(descriptor->owner, owner) != 0) {
            continue;
        }
        lua_CFunction handler = nullptr;
        for (std::size_t row = 0; row < count; ++row) {
            if (bindings[row].id == descriptor->id) {
                handler = bindings[row].handler;
                break;
            }
        }
        if (handler != nullptr) {
            // 批次 093：挂载点统一包一层计时（覆盖全部家族，不必逐个处理器插桩）。
            // 批次 095：**包装本身每次调用要多一次 `lua_call`**（约 0.1~0.2 µs × 每帧 646 次），
            // 所以生产构建默认**不包**（`PERF_API_WRAPPER` 默认 0）；要逐接口读数时
            // 用 `PERF_API_WRAPPER=1` 构建一份诊断包。
            PushHandler(state, handler, 0, descriptor->id);
            lua_setfield(state, -2, descriptor->name);
            ++attached;
            continue;
        }
        // 字段读取型：共享处理器 + 一行数据。行作为**闭包上值**带进去，
        // 于是同一个 `lua_CFunction` 能服务成百上千个 API，每个只占一行只读数据。
        bool attachedByRow = false;
        for (std::size_t row = 0; row < rowCount; ++row) {
            if (fieldRows[row].id != descriptor->id) {
                continue;
            }
            lua_pushlightuserdata(state, const_cast<FieldApiRow*>(&fieldRows[row]));
            PushHandler(state, &FieldApiHandler, 1, fieldRows[row].id);
            lua_setfield(state, -2, descriptor->name);
            ++attached;
            attachedByRow = true;
            break;
        }
        if (attachedByRow) {
            continue;
        }
        // 引擎方法类（批次 051）：同一套机制，共享处理器换成 `EngineMethodHandler`。
        for (std::size_t row = 0; row < engineRowCount; ++row) {
            if (engineRows[row].id != descriptor->id) {
                continue;
            }
            lua_pushlightuserdata(state, const_cast<EngineMethodRow*>(&engineRows[row]));
            PushHandler(state, &EngineMethodHandler, 1, engineRows[row].id);
            lua_setfield(state, -2, descriptor->name);
            ++attached;
            break;
        }
    }
    return attached;
}

} // namespace isaac::runtime
