#pragma once
#include <cstddef>
#include <cstdint>
namespace isaac::runtime {
struct ProceduralTexelBackend {
 bool (*read)(std::uintptr_t,void*,std::size_t);
 void (*enable)(std::uintptr_t,bool);
};
struct ProceduralTexelResult {unsigned enabled{},failed{};};
// Called before native CreateProceduralItem draws/presents either of its two finite atlases.
// Native Present fills and synchronizes the CPU buffers before the item can be sampled.
[[nodiscard]] ProceduralTexelResult PrepareProceduralItemReadback(
 std::uintptr_t manager,const ProceduralTexelBackend& backend) noexcept;
[[nodiscard]] bool InstallProceduralTexelReadbackHook(std::uintptr_t moduleBase) noexcept;
}
