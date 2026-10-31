#pragma once
struct lua_State;
struct TargetModule;
namespace isaac::runtime::notice {
// Resolves and publishes native graphics methods at the existing startup points.
void InstallGraphicsBindings(const TargetModule& module);
// Called inside the existing protected Lua preparation. Raises a Lua error if
// the production package is not verified; installs actual required metatables.
int InstallRuntimeTypes(lua_State* state);
}
