#pragma once
namespace LuaRuntime {
[[nodiscard]] bool IsRawEngineInputQuery() noexcept;
class RawEngineInputQueryScope {
  public:
    RawEngineInputQueryScope() noexcept;
    ~RawEngineInputQueryScope() noexcept;
    RawEngineInputQueryScope(const RawEngineInputQueryScope&) = delete;
    RawEngineInputQueryScope& operator=(const RawEngineInputQueryScope&) = delete;
};
}
