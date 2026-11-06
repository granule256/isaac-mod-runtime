#pragma once

namespace isaac::runtime {
// Kill sets the native dead flag. A post-kill listener may revive the entity;
// running Kill after that listener would overwrite the revival. Repeated Kill
// calls on an already dead entity must not emit another death transition.
template<class ReadDead,class Kill,class Dispatch>
void CompleteEntityKill(const ReadDead& readDead,const Kill& kill,const Dispatch& dispatch) {
    const bool wasDead=readDead();
    kill();
    if(!wasDead)dispatch();
}
}
