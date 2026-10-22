#pragma once
#include "ports/hook_port.hpp"

namespace isaac::runtime {
class InternalHookAdapter final : public IHookPort {
public:
    [[nodiscard]] Status Install(HookId id, const HookTarget& target) noexcept override;
    [[nodiscard]] bool IsInstalled(HookId id) const noexcept override;
    [[nodiscard]] std::uint32_t LastFailureCode() const noexcept { return lastFailure_; }
private:
    bool installed_{};
    bool pressureDestructorInstalled_{};
    bool pressureDeletingInstalled_{};
    bool clearAwardInstalled_{};
    bool entityDestructorInstalled_{};
    bool levelCurseFirstInstalled_{};
    bool levelCurseEvaluationInstalled_{};
    bool pickupSelectionInstalled_{};
    bool pickupSelectionSpecialInstalled_{};
    bool trinketFirstInstalled_{};
    bool trinketSelectedInstalled_{};
    bool consoleLengthInstalled_{};
    bool consoleCompareInstalled_{};
    std::uint32_t lastFailure_{};
};
} // namespace isaac::runtime
