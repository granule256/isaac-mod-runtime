#pragma once

#include "domain/world/world_content_changes.hpp"

namespace isaac::runtime {

// Native completion records scalar state only; it never enters Lua or allocates.
WorldContentSnapshot CaptureWorldContentSnapshot() noexcept;
void RecordWorldContentMutation(WorldContentMutation kind) noexcept;
void BeginWorldContentRun() noexcept;
void BeginWorldContentFloor() noexcept;

// Both guarded direct API entries and GOT interception use this completion
// boundary. Every completed invocation, including nested invocations, records.
template<class Original, class... Args>
void CompleteWorldContentMutation(WorldContentMutation kind, Original original, Args... args) {
    original(args...);
    RecordWorldContentMutation(kind);
}

} // namespace isaac::runtime
