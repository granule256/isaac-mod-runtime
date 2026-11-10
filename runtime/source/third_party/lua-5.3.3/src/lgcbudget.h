/* Optional host-controlled automatic GC pacing. See Copyright Notice in lua.h. */
#ifndef lgcbudget_h
#define lgcbudget_h

#include <stdint.h>
#include "lua.h"

typedef uint64_t (*lua_GCClock) (void *context);
typedef struct lua_GCBudgetInfo {
  uint64_t frame, budget, spent, frames, slices, steps, deferred;
  uint64_t pressure, cycles, maxslice, maxframe;
  uint64_t ticks, overruns;
  size_t highwater;
  size_t heap;
  ptrdiff_t debt;
  int state;
} lua_GCBudgetInfo;

/* Call on the VM owner thread. Identical configuration preserves the quota.
** NULL clock/zero budget disables pacing. No allocations or GC in these calls. */
LUA_API void lua_gc_setframebudget (lua_State *L, lua_GCClock clock,
    void *context, uint64_t budget, size_t highwater);
/* Explicit host opt-in, independent of time pacing. An explicit Lua setpause
** permanently takes precedence, including calls made before host setup. */
LUA_API void lua_gc_setautomaticpause (lua_State *L, int pause,
    int minimum, size_t maxthreshold);
LUA_API void lua_gc_beginframe (lua_State *L, uint64_t serial);
LUA_API void lua_gc_budgetinfo (lua_State *L, lua_GCBudgetInfo *info);
/* May run finalizers/raise errors: call only within a protected Lua call.
** Does nothing when pacing is disabled or the collector is stopped. */
LUA_API void lua_gc_advance (lua_State *L);

typedef struct lua_GCBudget {
  lua_GCClock clock;
  void *context;
  lua_GCBudgetInfo info;
  int hasframe;
  int explicitpause;
  int automaticpause;
  int minimumpause;
  size_t maxthreshold;
} lua_GCBudget;

#endif
