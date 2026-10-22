#pragma once
#include "relay/internal_hook.hpp"
namespace isaac::runtime {
struct ColdCallbackNativeBindings {using Random=std::uint32_t(*)(void*,std::uint32_t);Random random{};};
std::uint32_t LevelCurseFirstRandomInternalCallback(relay::InternalHookContext&,const void*) noexcept;
std::uint32_t LevelCurseEvaluateInternalCallback(relay::InternalHookContext&,const void*) noexcept;
std::uint32_t PickupSelectionInternalCallback(relay::InternalHookContext&,const void*) noexcept;
}
