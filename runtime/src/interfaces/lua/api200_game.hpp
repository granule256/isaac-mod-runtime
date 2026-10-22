#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int Api200GameAddEncounteredBoss(lua_State*);
int Api200GameButterBeanFart(lua_State*);
int Api200GameDonateAngel(lua_State*);
int Api200GameDonateGreed(lua_State*);
int Api200GameEnd(lua_State*);
int Api200GameFadein(lua_State*);
int Api200GameFadeout(lua_State*);
int Api200GameFinishChallenge(lua_State*);
int Api200GameGetGreedWavesNum(lua_State*);
int Api200GameGetNearestPlayer(lua_State*);
int Api200GameGetRandomPlayer(lua_State*);
int Api200GameHasEncounteredBoss(lua_State*);
int Api200GameMakeShockwave(lua_State*);
int Api200GameNextVictoryLap(lua_State*);
int Api200GameRerollEnemy(lua_State*);
int Api200GameRerollLevelCollectibles(lua_State*);
int Api200GameRerollLevelPickups(lua_State*);
int Api200GameStartStageTransition(lua_State*);
enum class Api200GameNative : unsigned { AddEncounteredBoss,ButterBeanFart,DonateAngel,DonateGreed,End,Fadein,Fadeout,FinishChallenge,GetGreedWavesNum,GetNearestPlayer,GetRandomPlayer,HasEncounteredBoss,MakeShockwave,NextVictoryLap,RerollEnemy,RerollLevelCollectibles,RerollLevelPickups,StartStageTransition,Count };
#if !defined(__SWITCH__)
struct Api200GameNativeTestBindings {std::uintptr_t methods[static_cast<unsigned>(Api200GameNative::Count)];};
void SetApi200GameNativeTestBindings(Api200GameNativeTestBindings) noexcept;
#endif
}
