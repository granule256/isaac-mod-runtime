#pragma once
namespace isaac::runtime {
struct ModRoomLoadBindings {
    using Load = bool (*)(void*, int, int);
    using Append = void (*)(void*, int, int);
    Load load{};
    Append append{};
};
// 本体失败保持失败；成功后才合并模组，调用者随后才能查询完整房间集合。
inline bool LoadStageRoomsWithMods(const ModRoomLoadBindings& native, void* config,
                                  int stage, int mode) noexcept {
    const bool loaded = native.load(config, stage, mode);
    if (loaded && native.append) native.append(config, stage, mode);
    return loaded;
}
}
