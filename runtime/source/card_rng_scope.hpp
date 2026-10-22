#pragma once
#include <cstdint>
namespace isaac::runtime {
// 仅游戏线程进入；单调token不依赖栈地址，旧userdata不会因地址重用复活。
struct CardRngScope { std::uintptr_t pointer{}; std::uint64_t token{}; CardRngScope* parent{}; };
struct CardRngScopes {
    CardRngScope* top{};
    std::uint64_t lastToken{};
    // 独立生命周期注册边界：调用者在受保护Lua调用返回后必定Leave。
    // GCC内联后只看见发布栈地址，无法关联后续Leave，误判为悬空指针。
    [[gnu::noinline]] bool Enter(CardRngScope& scope,std::uintptr_t pointer) noexcept {
        if(pointer==0 || lastToken==UINT64_MAX)return false;
        scope={pointer,++lastToken,top};top=&scope;return true;
    }
    void Leave(CardRngScope& scope) noexcept {
        if(top!=&scope)__builtin_trap();
        top=scope.parent;scope.pointer=0;
    }
    std::uintptr_t Resolve(std::uintptr_t pointer,std::uint64_t token) const noexcept {
        for(auto* scope=top;scope;scope=scope->parent)
            if(scope->pointer==pointer&&scope->token==token)return pointer;
        return 0;
    }
};
}
