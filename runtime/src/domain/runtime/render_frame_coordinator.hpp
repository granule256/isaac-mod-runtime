#pragma once

namespace isaac::runtime {

class RenderFrameScope;

// 渲染线程专用：帧状态存放在Manager钩子的栈上，不分配、不扫描，也不保留过期Manager。
class RenderFrameCoordinator {
public:
    void* Manager() const noexcept;

    template <typename DispatchFn>
    bool Dispatch(DispatchFn&& dispatch);

private:
    friend class RenderFrameScope;
    RenderFrameScope* frame_ = nullptr;
    bool dispatching_ = false;
};

class RenderFrameScope {
public:
    RenderFrameScope(RenderFrameCoordinator& coordinator, void* manager,
                     bool gameplay = true) noexcept
        : coordinator_(coordinator), previous_(coordinator.frame_), manager_(manager),
          gameplay_(gameplay) {
        coordinator_.frame_ = this;
    }
    ~RenderFrameScope() { coordinator_.frame_ = previous_; }
    RenderFrameScope(const RenderFrameScope&) = delete;
    RenderFrameScope& operator=(const RenderFrameScope&) = delete;

private:
    friend class RenderFrameCoordinator;
    RenderFrameCoordinator& coordinator_;
    RenderFrameScope* previous_;
    void* manager_;
    bool gameplay_;
    bool dispatched_ = false;
};

inline void* RenderFrameCoordinator::Manager() const noexcept {
    return frame_ ? frame_->manager_ : nullptr;
}

template <typename DispatchFn>
bool RenderFrameCoordinator::Dispatch(DispatchFn&& dispatch) {
    if (!frame_ || !frame_->gameplay_ || frame_->dispatched_ || dispatching_) return false;
    // 必须在进入Lua之前记录；回调里再次绘制HUD/Present不能重复派发。
    frame_->dispatched_ = true;
    struct DispatchScope {
        bool& active;
        explicit DispatchScope(bool& value) noexcept : active(value) { active = true; }
        ~DispatchScope() { active = false; }
    } scope(dispatching_);
    dispatch(frame_->manager_);
    return true;
}

// HUD::Render的真实ABI是void(this)，只调用一次原HUD，不重画原生前景。
template <typename DispatchFn>
void RenderAfterNativeHud(RenderFrameCoordinator& coordinator, void* hud,
                          void (*original)(void*), DispatchFn&& dispatch) {
    original(hud);
    coordinator.Dispatch(dispatch);
}

} // namespace isaac::runtime
