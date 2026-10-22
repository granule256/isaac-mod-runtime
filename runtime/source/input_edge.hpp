#pragma once

#include <cstddef>
#include <cstdint>

namespace LuaRuntime {

// `Input.IsActionTriggered` / `Input.IsButtonTriggered` 的**上升沿**判定。
//
// ★★★ 批次 381（2026-10-06）**当前口径**：边沿 = **引擎帧上的一次事件**，只在它发生的那一帧有效。
//   每帧由 `SampleInputFrame()`（`input_api.cpp`）在"帧号自增之后、派发回调之前"主动采一次，
//   判定退化成**纯读** ⇒ 模组"什么时候问、问几个、跳过哪一个"**不再改变语义**。
//   * `Triggered(code, controller, frame)` = "这条记录是**本帧**采出来的边沿吗"；
//   * `Pressed(code, controller, frame)` = "这条记录**本帧**按住吗"（批次 381 的 A2：
//     让"按住"与"边沿"来自**同一次采样**，与 PC 的"同一次 Poll"同形）；
//   * **下一帧一律 false**，不管调用方上一帧问没问过 —— 这一条治的是"一次推动走两格"
//     与"十字键又驱动菜单"两张脸（机制见 `docs/会话交接-20261006-一-…md` 第 4.3 节）。
//
// 下面第一~四节是**沿革原文**（批次 107 / 221 / 380 的口径与依据），按"只加不删"纪律保留；
// 读的时候注意"第五节（批次 381）"已经推翻了第四节的最终形状。
//
// ## 一、为什么必须我们自己算（批次 221 把依据补成反汇编级）
//
// 引擎里有两条"刚按下"，**两条都不能用**（证据：`tools/nro_disasm.py` 直接反汇编本机镜像）：
//
//   1. `KAGE::Input::ManagerBase::IsActionTriggered @ 0x4F9A64` → 设备虚槽 `+0x50`
//      → `InputDeviceBase::IsActionTriggered @ 0x4F775C`：它**遍历该动作绑定的按钮**，
//         对每个按钮调 `IsButtonTriggered`（虚槽 `+0x38`）。**全程不看模拟量**。
//      ⇒ **摇杆推出来的方向动作**（`ACTION_SHOOT*` 那一族）在这条路上**永远为假**。
//        这正是批次 107 那次真机读数的形状：`IsActionPressed` 为真（动作 4/5/6/7/13、
//        controller = 33），`IsActionTriggered` 一次都没真 —— 因为那几个动作是**摇杆**驱动、
//        而不是按钮驱动。当年把这个形状解释成"引擎那份上升沿状态在模组的时机里是空的"，
//        现在看是**错的**：它根本就没查模拟量。
//
//   2. `InputDeviceBase::IsButtonTriggered @ 0x4F7558`：先判虚槽 `+0x30`（本帧该按钮按下），
//      满足了才去测**数据成员 `+0x38`**；而 `InputDeviceBase::Poll @ 0x4F70B0` 每帧开头
//      干的第一件事就是 `ldr x8,[x0,#0x30] ; str x8,[x0,#0x38]` ⇒ **`+0x38` = 上一帧的按钮位图**。
//      ⇒ 它的语义是「**连续两帧都按着**」——引擎自己的 `Menu_Title::Update` 与
//        `Console::check_key_autorepeat` 正是拿它做**连按**（`analysis/api-restore-input-keys`）。
//        **不是** PC 文档说的「这一帧刚按下」。
//
// ⇒ **Switch 引擎里没有 PC 语义的"刚按下"可以复用**（PC 与 NX 是同一份源码树的两个平台分支，
//   但 NX 分支这条查询的语义如此；而且 NX 本体**连模组回调系统都没有** —— 批次 151 已定案：
//   整份 11 MB 镜像里 `AddCallback` / `RunCallback` / `MC_*` **出现 0 次**，
//   ★ 2026-10-07（批次 390）**更正**：`MC_INPUT_ACTION` 现在**已接线**（挂 `KAGE::Input::ManagerBase::`
//   那三处查询入口 + 用返回值覆盖）—— 详见 `hook_catalog.hpp` 的 `ManagerIsAction*` 段。
// ⇒ **唯一的路**：拿引擎权威的**按住**状态（引擎对象里本帧/上帧两份位图）自己求**帧上差分**。
//   ★ 引擎对象里那份数据是现成的：`+0x30` = 本帧位图、`+0x38` = 上一帧位图（`Poll` 每帧维护）
//     ⇒ **PC 的边沿 = `本帧 & ~上帧`**，引擎自己就有（脚本对象取法见 `input_api.cpp` 的采样器）。
//
// ## 二、口径（对齐 PC 契约 `tools/pc_contract_docs/Input.md:75` / `:107`）
//
//   * 同一帧内**问多少次**，答案相同（PC："同一个 update cycle 内"那一半）；
//   * 一次按下**只报一次** true，**下一帧一律 false**，直到"松开 → 再按下"；
//   * 边沿 = **本帧按住、上一帧没按住**；
//   * 第一次采样（运行时的第 1 帧，没有上一帧）**不算边沿**。
//
// ## 三、★★ 批次 221（2026-09-30）：删掉"松手去抖窗口"
//
// 批次 110 在这里加过一个"松手去抖窗口"（读到"没按住"要连续超过 N 帧才算真松手），
// 批次 220 把 N 从 6 调到 20。**批次 221 整个删掉**，理由：
//
//   * 窗口是**猜一个时长**，而它**两侧都会咬人**，项目上已经往返过一次：
//       - 窗口太小 ⇒ 引擎的"按住"在按着的时候断一下，就被当成"新手按下"
//         ⇒ 用户看到的「**一次输入 = 好多次**」；
//       - 窗口太大 ⇒ **真实松手再按**（间隔短于窗口）被并成一次
//         ⇒ 用户看到的「**按着没反应**」。
//     2026-09-30 用户报的正是**两侧同时存在** ⇒ 说明"猜一个时长"这条路本身不成立，
//     继续调数字只是在两个症状之间来回挪。
//   * 改成**引擎帧边界上的差分**之后**不需要任何窗口**。
//   * ⇒ 如果仍然观察到"多报"，那是**闪断**，必须去**源头**修：
//     帧号来源混用（本批已改单一来源）与"每帧重复读引擎设备表"（本批已改成每帧读一次）。
//     在判定里用猜的数去盖，只会把病灶从"多报"挪成"吞报"。
//
// ## 四、★★ 批次 380（2026-10-06）：取消"必须严格相邻帧"（**它的理由后来被推翻，见第五节**）
//
// 批次 221 的判定写成 `frame == 上一次采样 + 1` 才算有历史。2026-10-06 的真机读数量到
// **游戏给"渲染回调"的次数比"更新回调"少**：同一个会话里 `MC_POST_UPDATE` **46026** 次、
// `MC_POST_RENDER` **43519** 次；跨两次读数算增量（真实游玩那段）：更新 6308 / 渲染 5966
// ⇒ 比例 **0.946** ⇒ **约 5.4% 的更新帧没有渲染帧**。
// 于是"在渲染回调里每帧都问"的模组（MCM 就是）会遇到：按下发生在**没有渲染帧的那次更新**上，
// 它下一次问到时 `frame` 已经跳了 2 ⇒ 批次 221 的判定**把这整次按下吞掉**。
//
// 批次 380 于是把判定改成 `pressed && !entry.held`（"上一次采样到没按住、这一次按住"）。
// **但那个改法的前提是错的**（第五节）：PC 上"某一帧没有渲染回调"同样会让只在渲染里问的模组
// 漏掉那次按下 —— **那是 PC 也有的行为**，不是我们必须补偿的偏差。批次 380 的第二个后果是：
// 边沿的定义落在"**自这个调用方上一次问过以来**"上 ⇒ 一个旋钮有两个相反的脸
// （拧紧 ⇒ 整次按下被吞；拧松 ⇒ 一次按下被算多次）。
//
// ## 五、★★★ 批次 381（2026-10-06）：边沿改成"帧上采样出来的一次事件"（**当前口径**）
//
// **病根**：批次 221 / 380 都在调"我们怎么判定"，但判定的输入是"**调用方什么时候来问**" ——
// 于是边沿的定义跟着调用方的询问节奏走。真机两张脸都源于此（`docs/会话交接-20261006-一-…md` §4.3）：
//   * 中文版 MCM 的 `actionsDown/Up/Left/Right` **同时含移动动作与菜单动作**，而
//     `inputhelper.lua` 的 `MultipleActionTriggered` **碰到第一个为真的就 `return`** ⇒ 排在后面的
//     动作号当帧不被问 ⇒ 我们下一帧把它认成"新按下"⇒ **光标再走一格**（"一次推动走两格"）；
//   * `modconfig.lua:2259` 的 `MultipleButtonTriggered(ignoreActionButtons)` 闸门同理 ⇒
//     被它跳过的动作边沿下一帧还被认成新按下 ⇒ **十字键又驱动了菜单**。
//
// **新形状**（本类的接口）：
//   * 每帧在**帧号自增之后、派发回调之前**（`ManagedFrameClock` 的帧边界钩子）采一次；
//   * 采样集合**有界**：按键号 0..17 全采、动作号 0..31 全采，× 设备表里真实存在的手柄
//     ＋ 一份"任意设备"聚合（`0xFFFFFFFF`）；
//   * 按键侧直接用引擎的 `本帧 & ~上帧`（`+0x30` / `+0x38`）⇒ **一次引擎调用都不用**，
//     天然与 PC 同形；动作侧每帧对每个动作号调一次引擎的 `IsActionPressed`，
//     `prev` 由我们自己存（**一帧一份，与调用方无关**）；
//     ★★ **批次 400（2026-10-07）更正了这一条**：真机读数证明**局内 `+0x30` 与 `+0x38`
//     在采样点恒等**（`本帧 & ~上帧` 恒为 0）⇒ 局内一次边沿都报不出来（菜单里却正常）
//     ⇒ **MCM 永远开不出来**。现在按键侧也走"`held` 由我们自己按帧存"的那条路
//     （第三个实参一律传 `nullptr`），细节见**第七节**；
//   * 判定 = 纯读：`Triggered = (记录的边沿帧号 == 当前帧号)` —— **不做任何帧号算术、
//     不做窗口、不做相邻帧要求**；同一帧内问多少次都一样，**下一帧一律 false**。
//
// ★ 与 PC 的差别（如实登记）：本类的边沿**只在"采样那一帧"有效**；某一帧的边沿若模组那一帧
//   一次都没问、下一帧再问，答 false —— **这正是 PC 的行为**（PC："过了那一次 update
//   就没了"）。⇒ 与 PC **同形**，不再是批次 380 那种"迟到也能拿到"。
// ★ 仍存在的差别只剩**平台缺件**（键盘设备不存在、没有模拟扳机、`MC_INPUT_ACTION` 没有
//   引擎派发点）与**采样有界**（采样集合之外的 (code, controller) 组合没有记录，按"没按"答）。
//   如实登记在 `runtime/src/interfaces/lua/api_deviation.cpp`。
//
// ## 六、为什么类里留这些**诊断字段**（读数工具按 `Entry` 布局直读）
//
// `tools/read_device_state_via_gdb.py` 按符号读 `g_ButtonEdge` / `g_ActionEdge` 的 `entries_`
// （每行 = 一个 controller 槽的 32 个 code；**行 1 = 设备 33、行 31 = 任意设备**）。
// ⇒ **`Entry` 的字段顺序与大小不许改**（改了读数工具的解码就错位）。
// 诊断量口径（批次 381 重定，旧文保留在 `api_deviation.cpp` 的台账里）：
//   * `MinEdgeGap` / `LastEdgeGap` = **相邻两次边沿之间隔了几帧**（不再是"距上次读到按住"）；
//   * `PeakReleaseRun` = **最长连续"没按住"的帧数**（不再是"闪断诊断"，现在是"按住稳定性"读数）。
//
// ## 七、★★★ 批次 400（2026-10-07）：按键侧**不再信引擎那对私有位图**（回归修复）
//
// **症状（用户实测）**：「我明确告诉你不能打开 mcm，就是存在 bug」。
//
// **定案证据**（判据 = `g_InputButtonEdgeCounts[32]`；**只有 `IsButtonTriggered` 真答了 `true`
// 才加一** ⇒ 它非零就等于"我们确实报过边沿"）：
//
// | 读数 | 环境 | 报过 true 的按键 |
// | --- | --- | --- |
// | 批次 380（10-06 00:53） | **局内**（该版用户实测 MCM 能开） | 十字下 3、B 6、左摇杆按下 7、**右摇杆按下 3** |
// | 批次 398 / pid 166（10-07 20:45） | **局内 8042 帧**（玩了一局：开枪、用道具、换房间） | **（一个都没有，全数组 0）** |
// | 批次 398 / pid 168（10-07 20:57） | 菜单 → 局内 | 左摇杆 5、右摇杆 14，**但全在进局之前**（最后边沿帧 803 / 当帧 18063） |
//
// ⇒ **`Triggered` 在局内永远 false，在菜单里却正常。** 而 MCM 的开菜单判定**只能在局内跑**
//   （渲染回调被"有房间 + 有玩家"的派发闸门挡在局外，`OpenConfigMenu` 还要 `room:IsClear()`）
//   ⇒ **MCM 永远开不出来**。
//
// **根因**：批次 381 把按键侧的边沿从"查询时问引擎"（380 那条**真机证明局内可用**的路）
//   换成"读设备对象 `+0x30`（本帧位图）/ `+0x38`（上帧位图）算 `本帧 & ~上帧`"，
//   而**那两格在局内的采样点上恒等**（`+0x30` 的"按住"是好的 —— pid 166 靠它答对过 A/减号/十字下
//   的"按住"；坏的是 `+0x38`，它在我们采样之前就已经被复制成与 `+0x30` 相同）。
//   ★ 而批次 381 恰好把"按右摇杆 ⇒ MCM 打开"这一条验收留成了**"待做"** ⇒ 没人发现。
//
// **修法（最小）**：按键侧**第三个实参一律传 `nullptr`** ⇒ 走本类自己的差分
//   `edge = pressed && 上一帧采样里的 held`。`held` 是**我们自己的、一帧一份**的，
//   与"调用方什么时候来问"无关 ⇒ **381 建立的"一帧一次事件"口径一点不变**
//   （"推一下走两格 / 十字键驱动菜单"两张脸不会回来），只是不再依赖那对私有位图。
//   ★ **不接受**的替代：把判定退回"按调用方询问节奏算差分"（221 / 380 那一档旋钮）。
//
// **代价与残留风险**：
//   * 引擎调用次数**不变**（按键侧仍然 0 次，只读 `+0x30` 一格）；
//   * 采样失败那一帧（`MarkSampleRowsEmpty`）会把 `held` 清零 ⇒ 下次成功采样可能**凭空多一个边沿**
//     （`STICK_RIGHT` 会 +2 而不是 +1）。真机上 `g_InputSampleFailures` 应当为 0；
//     若读数里它非零，先修采样失败，再判"多报"。
//
// **验收（本批的真机清单）**：① 进局、不暂停、按一下右摇杆 ⇒ **MCM 打开且只开一次**；
//   ② 读一次设备 ⇒ **局内**也出得来边沿（不再只在菜单里）；③/④/⑤ 菜单里推一下只走一格、
//   十字键不动、B/A 各一次（= 381 的三张脸不许回来）。
class InputFrameEdges {
public:
    //: code（按键号 / 动作号）与 controller（设备号）都只取低 5 位。
    //: 真机上设备号是 33 ⇒ 槽 1；"任意设备" `0xFFFFFFFF` ⇒ 槽 31。
    static constexpr std::uint32_t kSlots = 32u;
    static constexpr std::uint32_t kIndexMask = 31u;
    //: 帧号初值（"还没采过任何一帧"）。
    static constexpr std::uint32_t kNoFrame = 0xFFFFFFFFu;

    //: 采样**一个 controller 槽**的一行（32 个 code）。
    //:
    //: * `pressed[code]` = 本帧该码是否按住（调用方给，长度 = `kSlots`）；
    //: * `edge_or_null[code]` = **可选的**本帧边沿：只有"引擎自带一对可靠的本帧/上帧位图"的
    //:   调用方才会用它；传 `nullptr` 时由本类按 `pressed && !上一帧采样里的 held` 自己算
    //:   （**一帧一份、与调用方无关**）。
    //:   ★★ **批次 400：生产路径一律传 `nullptr`** —— 按键侧原先信的那对位图
    //:   （`+0x30` / `+0x38`）在**局内恒等** ⇒ 边沿恒 0 ⇒ 功能整体失效（第七节）。
    //:
    //: ★ 第一次采样（该格 `frame == kNoFrame`）：自己差分的那条路**不算边沿**；
    //:   直接喂 `edge_or_null` 的那条路**信任调用方**（引擎的"上帧位图"在第一帧就已经有效）。
    //:
    //: ★★★ 批次 406（2026-10-07）**同帧不幂等 —— 调用方每帧对每个槽只许写一次**：
    //:   本方法写下 `edge` 后**立刻把 `entry.held` 更新成 `cur`**，所以**同一帧对同一个槽再写
    //:   一次**（哪怕 `pressed` 一模一样）会把 `edge` 覆盖成 false —— 第一次那条边沿就没了。
    //:   而槽号 = `controller & kIndexMask`，**不同设备号可能落进同一个槽**（引擎手柄号 `1` 与
    //:   `33` 相差 32 ⇒ 同槽 1）。⇒ 调用方必须先把"所有设备"的结果**按槽聚合**，再**每槽只写一次**
    //:   （`input_api.cpp` 的 `SampleInputFrame` 就是这么做的）。
    void SampleRow(std::uint32_t controller, std::uint32_t frame, const bool* pressed,
                   const bool* edge_or_null) noexcept {
        if (pressed == nullptr) {
            return;
        }
        Entry* const row = entries_[controller & kIndexMask];
        for (std::uint32_t code = 0; code < kSlots; ++code) {
            Entry& entry = row[code];
            const bool cur = pressed[code];
            const bool has_history = entry.frame != kNoFrame;
            // 边沿 = 本帧按住 && 上一帧没按住（`prev` = 本类上一次采样里的 `held`）。
            // ★ 给了 `edge_or_null` 就信任调用方那一份（**批次 400 起生产路径不再给**，见第七节）。
            const bool edge = edge_or_null != nullptr ? (edge_or_null[code] && cur)
                                                      : (cur && has_history && !entry.held);
            if (edge && entry.lastEdgeFrame != kNoFrame) {
                // 诊断：相邻两次边沿隔了几帧（"真松手再按"会是几百帧）。
                const std::uint32_t gap = frame - entry.lastEdgeFrame;
                entry.lastEdgeGap = static_cast<std::uint16_t>(gap > 65535u ? 65535u : gap);
                if (entry.minEdgeGap == 0 || entry.lastEdgeGap < entry.minEdgeGap) {
                    entry.minEdgeGap = entry.lastEdgeGap;
                }
            }
            if (edge) {
                entry.lastEdgeFrame = frame;
            }
            if (cur) {
                entry.releaseRun = 0;
            } else if (entry.releaseRun < 255u) {
                // 诊断：当前连续"没按住"了多少帧 / 历史最大值。
                ++entry.releaseRun;
                if (entry.releaseRun > entry.peakReleaseRun) {
                    entry.peakReleaseRun = entry.releaseRun;
                }
            }
            entry.frame = frame;
            entry.edge = edge;
            entry.held = cur;
        }
    }

    //: 纯读：这一格是不是**本帧**有记录（A2 用它决定"读采样值"还是"回退现查"）。
    [[nodiscard]] bool HasFrame(std::uint32_t code, std::uint32_t controller,
                                std::uint32_t frame) const noexcept {
        return EntryAt(code, controller).frame == frame;
    }

    //: 纯读：这一格在本帧报边沿了吗（= 记录的边沿帧号 == 当前帧号）。
    [[nodiscard]] bool Triggered(std::uint32_t code, std::uint32_t controller,
                                 std::uint32_t frame) const noexcept {
        const Entry& entry = EntryAt(code, controller);
        return entry.frame == frame && entry.edge;
    }

    //: 纯读：这一格在本帧按住吗（批次 381 的 A2：与边沿同一次采样）。
    [[nodiscard]] bool Pressed(std::uint32_t code, std::uint32_t controller,
                               std::uint32_t frame) const noexcept {
        const Entry& entry = EntryAt(code, controller);
        return entry.frame == frame && entry.held;
    }

    //: 诊断：相邻两次边沿间隔的**最小值**（0 = 还没有两次样本）。
    [[nodiscard]] std::uint16_t MinEdgeGap(std::uint32_t code,
                                           std::uint32_t controller) const noexcept {
        return EntryAt(code, controller).minEdgeGap;
    }

    //: 诊断：**最近一次**边沿间隔（对照：几百帧就是"真松手再按"）。
    [[nodiscard]] std::uint16_t LastEdgeGap(std::uint32_t code,
                                            std::uint32_t controller) const noexcept {
        return EntryAt(code, controller).lastEdgeGap;
    }

    //: 诊断：**最长连续"没按住"帧数**（0 = 没断过）。
    [[nodiscard]] std::uint8_t PeakReleaseRun(std::uint32_t code,
                                              std::uint32_t controller) const noexcept {
        return EntryAt(code, controller).peakReleaseRun;
    }

    //: 新建 Lua 会话时清空（与其它会话级状态同一个口径）。
    void Reset() noexcept {
        for (std::size_t slot = 0; slot < kSlots; ++slot) {
            for (std::size_t index = 0; index < kSlots; ++index) {
                entries_[slot][index] = Entry{};
            }
        }
    }

private:
    //: ★ 字段顺序与大小**不许改**（读数工具按它解码，见文件头第六节）。
    struct Entry {
        //: 最后一次采样的帧号（`kNoFrame` = 还没采过）。
        std::uint32_t frame = kNoFrame;
        //: **本帧**是不是边沿。
        bool edge = false;
        //: **本帧**是不是按住（A2 的"按住"读它）。
        bool held = false;
        //: **上一次边沿**的帧号（诊断；批次 381 前这个名字存的是"上一次读到按住"的帧号）。
        std::uint32_t lastEdgeFrame = kNoFrame;
        //: 当前连续"没按住"的帧数 / 历史最大值（诊断）。
        std::uint8_t releaseRun = 0;
        std::uint8_t peakReleaseRun = 0;
        //: 相邻两次边沿间隔的最小值 / 最近值（诊断）。
        std::uint16_t minEdgeGap = 0;
        std::uint16_t lastEdgeGap = 0;
    };

    [[nodiscard]] const Entry& EntryAt(std::uint32_t code, std::uint32_t controller) const noexcept {
        return entries_[controller & kIndexMask][code & kIndexMask];
    }

    Entry entries_[kSlots][kSlots]{};
};

} // namespace LuaRuntime
