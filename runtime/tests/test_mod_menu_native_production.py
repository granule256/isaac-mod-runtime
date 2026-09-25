"""门禁：「模组那一行 + 模组页」搬进生产之后，几条判据一条都不许放松。

## 这一批（2026-09-23，批次 078）

077 把这套功能**整块**从探针（`runtime/source/probe/native_mods_menu_probe.cpp`）搬进了生产代码
（规格：`docs/设计-模组页搬生产-20260923.md`），真机验收**通过**，但带出两条新结论，
于是 078 做了两件事：**撤掉换字体那段接线**（真机：那一页按字节画字，换字体救不了中文）、
**语言码改成每帧都问**（真机：换语言当场生效，而那张纸是分语言的）。
探针**原样保留**做现场探索用，所以这里钉的每一条都是"生产版必须自己成立"的判据，而不是"抄没抄对"：

1. **判"引擎那份动画里有没有我们那一层"只能读图层数**（`ANM2+0xB0`）：
   `ANM2::GetLayer(int)` 越界时**不返回空指针**（它打一条日志后照样算出界地址）
   ⇒ 用"`GetLayer(12)` 是不是空"来判就是读越界内存；
2. **有那一层时绝不再画**：回调里必须先判、再 `return`，兜底绘制只能出现在它之后
   （画了就是两层叠在一起）；
3. **兜底必须存在**，而且"**空的东西绝不拿去画**"：拿不到字体/布局/页面原点时
   `DrawRowLabel` 返回 false 并什么都不画（上一批真机崩溃就是"拿空精灵表去画"）；
4. **写回引擎的必须是"行号"**（`EngineRowForSlot`）并再夹一次上界（恒 0..4）：
   用 `EngineIndexClampedForSlot` 当映射会把视觉上的"统计数据"（我们的第 4 格）写成引擎行 4
   = 选项 ⇒ **真机现象是"统计和选项按了都是设置"**（2026-09-23 用户实测）；
5. **状态面符号必须外部链接**：`nm` 里能看到**裸名** `g_ModMenuState`
   （放进匿名命名空间就查不到 —— 2026-09-19 的 D6 事故）；
6. **状态面下标三处一致**：`.cpp` / `.hpp` / `tools/read_device_state_via_gdb.py`；
7. **生产路径里不许有主动报错**（沿用 `test_instruction_guard` 的口径）；
8. **`HookId` 与 `kHookCatalog` 一一对应**，新加的三条要进读数工具的 `HOOK_NAMES`；
9. **探针与生产互斥**：两个 TU 装的是**同一批入口**（入口中继靠改写入口 16 字节工作，
   装第二次必然 `EntryMismatch`）⇒ 探针构建里跳过生产安装；
10. **不搬假数据**：生产代码里不许出现 `PROBE-MOD-A` 之类的固定测试名。

另有两条是这一批自己带来的硬约束（违反哪一条都算没做完），一并钉住：
11. **不搬那两条"贴图路线"**（内存版 / 磁盘版 `LoadImage`）：075 之后那一行由引擎自己画，
    那两条已是死路（真机崩过）⇒ 生产版只留"画字"兜底；
12. **引擎自己的字体对象一个字节都不许动**（`g_Manager + 0x117120`）：077 曾把扩展字体装进去
    换中文，真机证明那一页用的是**按字节**的画字重载 ⇒ 换字体救不了中文（还多 32MB 字图集）
    ⇒ 078 整个撤掉；那个对象仍被**读**（兜底画字取行高），但只读不写。
13. **语言码每帧都问**（078）：用户在选项页换语言是当场生效的 ⇒ 变了就重新 `Init` 一次模组页
    （**贴图**会跟着换）。语言变了就**照引擎自己的换语言协议**把那三步做完
    （`Menu_Mods::PreLanguageSwitch` → `AnmCache::FreeUnreferencedImages/Entries` →
    `Menu_Mods::PostLanguageSwitch`）—— 只重跑 `Init` 是不够的（动画缓存按路径哈希认）。
    ★ 079 曾因"把 EID 搞坏"被撤回，但那个归因后来被证明是误判（真因是挂载点没恢复，
    批次 082 修的），2026-09-23 经用户批准重新启用（批次 083）
    （引擎把我们这侧 shim 借用的贴图/动画当成"没人引用"放掉了）⇒ 已撤回，见 `.cpp` 里那段注释。
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
CPP = SOURCE / "mod_menu_native.cpp"
HPP = SOURCE / "mod_menu_native.hpp"
HOOK_MANAGER = SOURCE / "hook_manager.cpp"
CATALOG = ROOT / "runtime" / "src" / "domain" / "runtime" / "hook_catalog.hpp"
ADAPTER = ROOT / "runtime" / "src" / "infrastructure" / "relay" / "entry_relay_hook_adapter.cpp"
READER = ROOT / "tools" / "read_device_state_via_gdb.py"
ELF = ROOT / "runtime" / ".gdbsym-artifacts" / "runtime.elf"

#: 本功能相关的挂点，**按追加顺序**钉住。2026-09-23 批次 092 追加了第四条（成就闸门）。
NEW_HOOKS = ("MenuGameRender", "MenuTitleRender", "MenuManagerSetState")
#: 批次 092 追加、098 改设计的**只属于生产**的挂点：成就闸门。
#: 092~097 挂在 `PersistentGameData::TryUnlock`（拦解锁调用）；098 按用户裁定"照 PC 语义"
#: 挪到 `PersistentGameData::SetReadOnly`（唯一写只读位的地方，参数改成「原参数 OR 该禁」）。
#: ★ 它**不属于** `NEW_HOOKS` —— 那一组是"探针也装、所以探针构建里必须跳过"的；
#:   本条的入口探针**不碰**，两边不会在同一入口装第二次，所以不需要那条跳过判据。
PRODUCTION_ONLY_HOOKS = ("PersistentGameDataSetReadOnly",)
#: 本功能相关的全部挂点（**按追加顺序**）—— 目录顺序、`HOOK_NAMES`、回调声明三条判据共用。
ALL_NEW_HOOKS = NEW_HOOKS + PRODUCTION_ONLY_HOOKS
#: 状态面字段数（`State` 的字段个数 = 读数工具那一段的下标个数）。
#: 22 = 077 的 20 格 + 078 加的两格（换语言次数 / 重载页面次数）；
#: **27** = 上面那 22 格 + 2026-09-23 定位"换语言后 EID 坏掉"时加的 4 格 + "开模组禁成就"那 1 格
#: （挂载点重建中继跑过几次 / 其中失败几次 / 会话挂载服务发布了没 / 最后一次 `Font:Load` 的结果）
#: + "开模组禁成就"那一格 + 2026-09-23 批次 085 加的 4 格（`metadata.xml` 三种解析结果 + 开着的真实模组个数）。
#: ★ 加字段只能往后加；改了这里就要同时改读数工具的读数宽度（`26 个 u32 = 13 个字`）。
#: 状态面的字段数（u32 个数）。★ 加格子**只能往后追加**，并同步改这里、明文清单与读数工具。
#: 2026-09-24（批次 097）：35 → **40**（[35]..[39] = 成就闸门的"被调到/拦下/真解锁/最后成就号/原函数缺失"）。
#: 2026-09-24（批次 107）：40 → **41**（[40] = `enabledRealMods`：**处于启用状态**的真实模组个数 ——
#: 判据改成 PC 口径之后必须能与 [30]「实际加载」分开看，否则"开关开了但还没重启"这种情况读不出来）。
#: 2026-09-24（批次 116）：41 → **45**（[41]..[44] = "发现清单自证"四格：清单条数 / 启用位图 /
#: 本局加载位图 / 发现跑过没。理由：待修记录里 `[40] = 0` 与"开关服务读不出来时默认全都开着"
#: 是矛盾的，而两个**汇总数**分不出"清单空 / 全禁用 / 发现没跑到"这三种，它们的处置完全不同）。
#: 2026-09-25（批次 117）：45 → **51**（[45]..[50] = "局内单向闩锁"六格：闩锁值 / 置位次数 /
#: 清零次数 / 上次清零来源 / `GameExit` 被调到几次 / 闩锁可用否。判据改成"一局之内单向"之后，
#: 必须能从读数里分清"闩锁有没有置位""清零点有没有跑到""它是不是被停用了"这三件事）。
#: 2026-09-25（批次 118）：51 → **54**（[51]..[53] = "在一局里吗" + 边沿写位的调用次数与结果。
#: 117 的第一次真机读数暴露两件事：闩锁在**主菜单**上就置了位（裁定①要求"进局前关掉 ⇒ 不锁"）、
#: 而"边沿写位到底生效没有"当时没有任何格子能回答）。
#: 2026-09-25（批次 119）：54 → **56**（[54]..[55] = 出局时留存的污染 / 把留存接回来过几次。
#: 用户裁定"**继续同一份存档算同一局**"⇒ 出局时闩锁要转成"留存"、继续时接回来并补写一次锁；
#: 没有这两格就分不清"继续有没有把污染接回来"与"根本没留存"）。
#: 2026-09-25（批次 120）：56 → **58**（[56]..[57] = 存档分区里那个"污染过"标记我们认为它是几 /
#: 读写失败几次。用户裁定"**比 PC 严**"⇒ 跨重启也要保持，所以标记要落盘；没有这两格就分不清
#: "文件读到了什么"与"存档分区那条路坏没坏"）。
STATE_FIELDS = 58

sys.path.insert(0, str(ROOT))


def function_body(text: str, signature: str) -> str:
    """取一个函数的函数体（从签名起、到下一个顶格的 `}` 为止）。"""
    assert signature in text, f"没找到 {signature}"
    return text.split(signature, 1)[1].split("\n}\n", 1)[0]


class ModMenuNativeProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = CPP.read_text(encoding="utf-8")
        cls.hpp = HPP.read_text(encoding="utf-8")

    # ---- 1) 判据必须是图层数，不是 `GetLayer` 的空指针 ------------------------

    def test_layer_presence_is_read_from_the_layer_count(self):
        self.assertIn("kAnm2LayerCountOffset", self.cpp, "必须有一个「图层数在 ANM2 里哪个偏移」的常量")
        body = function_body(self.cpp, "bool HasNativeLayer")
        self.assertIn("kAnm2LayerCountOffset", body, "判定函数必须读图层数")
        self.assertNotIn("getLayer(", body,
                         "不许用 `GetLayer(12)` 判有没有那一层：它越界时返回的是出界地址")
        self.assertIn("kMenuGameLayerCountWithModRow", body, "阈值要有名字、不许写魔数")

    def test_the_getlayer_trap_is_written_down_next_to_the_constant(self):
        """把「`GetLayer` 越界不返回空」这件事写在常量旁边 —— 不然下一个人还会那样写。"""
        anchor = self.cpp.index("kAnm2LayerCountOffset = ")
        window = self.cpp[max(0, anchor - 1200):anchor + 400]
        self.assertIn("GetLayer", window, "常量旁边要提到 `GetLayer` 这个坑")
        self.assertIn("空指针", window, "要说清「越界时不返回空指针」这件事")

    # ---- 2) 有那一层时不再自己画 --------------------------------------------

    def test_the_relay_skips_its_own_drawing_when_the_engine_draws_it(self):
        body = function_body(self.cpp, 'extern "C" void EntryRelayMenuGameRenderCallback')
        self.assertIn("HasNativeLayer", body, "回调里必须问一次「引擎那份动画有没有这一层」")
        self.assertIn("if (nativeLayer)", body, "有那一层时必须走单独的分支")
        native_branch = body.split("if (nativeLayer)", 1)[1].split("}", 1)[0]
        self.assertIn("return", native_branch, "有那一层时这一帧不再画我们自己的东西")
        self.assertLess(body.index("HasNativeLayer"), body.index("DrawRowLabel"),
                        "必须先判、后画（顺序反了就等于画两遍）")
        self.assertLess(body.index("if (nativeLayer)"), body.index("DrawRowLabel"),
                        "我们的绘制必须排在那个分支**之后**")

    # ---- 3) 兜底必须存在，而且"空的东西绝不拿去画" ---------------------------

    def test_the_fallback_drawing_path_is_still_there(self):
        self.assertIn("bool DrawRowLabel", self.cpp, "兜底绘制必须存在（没有那一层时不能整行消失）")
        body = function_body(self.cpp, "bool DrawRowLabel")
        # 三样东西拿不到就**什么都不画**：画字入口、字体对象所在的 `g_Manager`、那一套布局。
        self.assertIn("g_Menu.drawText == nullptr", body, "拿不到画字入口 ⇒ 不画")
        self.assertIn("g_Menu.manager == 0", body, "拿不到 `g_Manager` ⇒ 不画（字体对象在它里面）")
        self.assertIn("g_Menu.layout == nullptr", body, "拿不到布局 ⇒ 不画")
        self.assertIn("return false", body, "兜底必须把「到底画没画」如实交回调用方")
        # 画字调用必须排在那些前置判据之后（顺序反了就是"拿空的东西去画"）。
        self.assertLess(body.index("g_Menu.drawText == nullptr"), body.index("g_Menu.drawText("),
                        "判据必须在真正的画字调用之前")
        self.assertLess(body.index("return false"), body.index("g_Menu.drawText("),
                        "至少要有一条早退排在画字之前")
        relay = function_body(self.cpp, 'extern "C" void EntryRelayMenuGameRenderCallback')
        self.assertIn("DrawRowLabel(", relay, "回调的兜底必须调它")

    # ---- 4) 写回引擎的是"行号"，并且夹在 0..4 --------------------------------

    def test_engine_index_is_the_row_number_and_clamped(self):
        body = function_body(self.cpp, "void ModRowUpdate")
        self.assertIn("EngineRowForSlot(g_Slot)", body,
                      "写回引擎的必须是**行号**（`EngineRowForSlot`）")
        self.assertIn("kMenuGameEngineEntryCount", body, "必须再夹一次上界（恒 0..4）")
        # ★ 判据是"**没被调用**"，不是"字面名字没出现"：那条注释必须留下 ——
        #   它写的就是这个 bug 的后果（"统计和选项按了都是设置"），删掉注释等于删掉为什么。
        self.assertNotIn("EngineIndexClampedForSlot(", self.cpp,
                         "不许拿 `EngineIndexClampedForSlot` 当映射：它会把视觉上的"
                         "「统计数据」（我们的第 4 格）写成引擎行 4 = 选项 ⇒ "
                         "真机现象是「统计和选项按了都是设置」")

    # ---- 5) 状态面符号是外部链接（`nm` 能看到裸名） ---------------------------

    def test_input_edges_are_only_cleared_when_leaving_the_page(self):
        """★★ 边沿状态**只在"真的离开模组页"那一刻**清零，不许在别的 `!active` 帧清。

        真机现象（用户 2026-09-23 报）：**每次进模组页，第一个模组的开关都会自己翻一次。**

        机制（同一帧的先后顺序，读 `ModMenuNativeUpdate` 就看得出来）：
          ① `ModRowUpdate` 里我们那一格的确认 ⇒ `EnterModsPage()`，它把四个边沿
             **按"当前还按着的情况"锁上**（进页面用的就是 A 键、此刻还按着）
             —— 目的正是"下一帧不许把它当成新按下"；
          ② **同一帧**接着跑 `ModsPageUpdate`：`g_Menu.menuState` 是这一帧**开头**读的，
             那时还没切到 16 ⇒ `active == false` ⇒ 早退分支**把刚锁上的清零**；
          ③ 下一帧状态已是 16、A 还按着、上一帧记的是 0 ⇒ `Edge()` 判成"刚按下"
             ⇒ 顺手把第一条的开关翻掉。

        ⇒ 判据：清零那四行必须**在"刚离开"那个分支里**（`pageWasActive != 0 && !active`），
        而不是在 `if (!active) { ... }` 早退分支里。
        """
        text = CPP.read_text(encoding="utf-8")
        start = text.index("void ModsPageUpdate(")
        body = text[start:start + 3000]

        leave = body.index("g_Menu.pageWasActive != 0 && !active")
        early_return = body.index("if (!active) {", leave)
        clears = [m.start() for m in re.finditer(r"g_PageLast(Up|Down|Confirm|Back) = 0;", body)]
        self.assertEqual(len(clears), 4,
                         f"应当恰好有 4 处清零（上下确认返回各一次），实际 {len(clears)} 处")
        for position in clears:
            self.assertGreater(position, leave,
                               "清零必须在'刚离开'那个分支里")
            self.assertLess(position, early_return,
                            "清零**不许**放进 `if (!active)` 早退分支 —— 那一帧正好是"
                            "'刚切进页面、状态还没生效'的那一帧，清了就会在下一帧误判一次确认，"
                            "真机现象就是'每次进模组页第一个模组的开关自己翻一次'")

    def test_the_achievement_gate_follows_pc_semantics(self):
        """★★ 成就闸门（批次 098）：**照 PC 语义** —— 闸门挂在 `SetReadOnly` 上，判据看"实际加载"。

        ## 用户裁定（2026-09-24）
        "你现在的解锁设计就很垃圾，因为加载时仍能解锁就直接用个 if 堵上是吗？
        你看看 PC 上到底是如何做的，然后按 PC 上的来。"
        语义要求：**没打完妈腿前用模组 ⇒ 不给成就；没用模组 ⇒ 能解锁。**

        ## 取证（逐条反汇编，工具 `tools/nro_disasm.py`）
        * PC 的规则 = 带符号的 `AfterbirthPlus.nro` 里 `ModManager::AchievementsLocked()`（`0x250CB8`）：
          遍历模组列表 → 任一启用 ⇒ `PersistentGameData::Unlocked(4)` 取反
          ⇒ 「有模组开着 且 成就 #4（打过妈妈）未解锁」= 锁。**开局问一次**的查询式模型。
        * Switch 移植版把这条链删干净了（`check_game_data_modified` 是死代码、
          `Manager::AchievementUnlocksDisallowed` 是空实现）；`Game::Start`（`0x34E518`）里
          残留的禁成就判据只有"特殊种子"与"挑战局"两条，最后调 `PersistentGameData::SetReadOnly`。
        * ★★ `Manager+0x36D4D` **不参与**那个判断：`Game::Start` 只是把它抄进 `Game+0x2F0030`
          （紧挨难度字段）⇒ 084~089 写它完全无效。
        * `SetReadOnly`（`0x439460`）是**唯一**写只读位（`PGD+0x1`）的地方，24 个调用点全在开局路径上。

        ## 我们的做法
        挂 `SetReadOnly` 入口中继，参数改成「引擎原参数 OR `AchievementsShouldBeBlockedFor(self)`」，
        禁与不禁都交回引擎；`TryUnlock` 不再拦。

        ## 判据
        1. `.cpp` 里**不许**再写任何引擎状态字节（那两个总闸都不写）—— 只看、只记；
        2. 判据必须用 `ModMenuActiveCount()`（**实际加载**），不许用开关状态，也不许有 fail-closed；
        3. 状态面要有 `[26]`/`[30]` 两格；
        4. 那两格的值必须是「实际加载 ≠ 0 **且** 成就 #4 未解锁」算出来的；
        5. `hook_manager.cpp` 里闸门必须挂在 `PersistentGameDataSetReadOnly` 上，最终参数是
           「引擎原参数 OR 判定」，且**拿不到回退入口时什么都不写**；
        6. **不许**调 `Manager::AchievementUnlocksDisallowed` / `Game::AchievementUnlocksDisallowed`。
        """
        text = CPP.read_text(encoding="utf-8")
        self.assertIn("constexpr std::uintptr_t kManagerAchievementsDisallowedOffset = 0x36D4D;",
                      text, "`0x36D4D` 那个常量要留着（它是'我们查过它、它不参与判据'的记录）")
        # ★ 2026-09-23 根因修复后，这段逻辑**单独抽成了 `UpdateAchievementDisallow`**，
        #   并在 `ModMenuNativeUpdate` 的**最开头**调用 —— 因为原来放的位置在
        #   "`g_MenuManager` 读不到就 return"那道**早退之后**，而**在一局游戏里菜单管理器不存在**
        #   ⇒ 那一整段一整局都不执行 ⇒ 读数永远停在进局前的旧值。
        #   ⇒ 判据跟着搬到新载体，并**新增**一条结构性判据：调用必须在早退之前。
        body = function_body(text, "void UpdateAchievementDisallow")
        update = function_body(text, "void ModMenuNativeUpdate")
        self.assertIn("UpdateAchievementDisallow(*module);", update,
                      "每帧更新里要调它（每帧刷读数）")
        call_at = update.index("UpdateAchievementDisallow(*module);")
        # 那道早退的**代码**（不是注释）：`ReadSingleton(*module, kMenuManagerSlotOffset…` 那一句。
        early = update.index("ReadSingleton(*module, kMenuManagerSlotOffset")
        self.assertLess(call_at, early,
                        "★ 这个调用必须在「`g_MenuManager` 读不到就 return」那道早退**之前** —— "
                        "在一局游戏里菜单管理器不存在，放到早退之后就一整局都不执行（2026-09-23 根因）")
        # ★★★ 098 起：**一个引擎状态字节都不写**（那两个总闸仍**被读**，用于读数看现场真值）。
        #    落地改由 `SetReadOnly` 入口中继完成（见本方法判据 5），所以这里钉"禁止写"。
        code_only = re.sub(r"//[^\n]*", "", body)
        self.assertNotIn("kManagerAchievementsDisallowedOffset", code_only,
                         "不许再写 `Manager+0x36D4D` —— 098 已证明它**不参与** `SetReadOnly` 的判据")
        self.assertNotIn("kPersistentReadOnlyOffset,", code_only,
                         "不许写只读位 —— 它是引擎按本局判据设的，我们只在入口中继里抬参数")
        self.assertIn("achievementsDisallowed", body, "判定结果要记进状态面（读数里看得出该不该禁）")
        hpp = HPP.read_text(encoding="utf-8")
        self.assertIn("achievementsDisallowed", hpp, "状态面 .hpp 要有 [26] 这一格")
        # ★★ 口径（★ 批次 107 起是**用户 2026-09-24 裁定"按 PC 口径"**）：
        #    数的是**处于"启用状态"**的真实模组 —— 与 PC 的 `ModManager::AchievementsLocked()`
        #    同口径（它走模组列表里**每一项的启用位**，界面上一开就变、**不需要重启**）。
        #    ★ 107 之前用的是 `ModMenuActiveCount()`（"本局**开机时真的加载了**几个"），
        #    那个数在"开关打开但还没重启就进局"时是 0 ⇒ **漏判**（真机实测后用户裁定改口径）。
        judge = function_body(text, "bool AchievementsShouldBeBlockedFor")
        self.assertIn("if (isaac::runtime::ModMenuEnabledCount() == 0)", judge,
                      "判据必须是「**处于启用状态**的真实模组数」= `ModMenuEnabledCount()`")
        self.assertNotIn("if (isaac::runtime::ModMenuActiveCount() == 0)", judge,
                         "★ 不许再拿「本局实际加载了几个」当判据：那个数在开机那一刻就定死了，"
                         "开关打开但没重启时它是 0 ⇒ 会漏判（批次 107 的由来）")
        self.assertNotIn("ModMenuDiscoveryDone(", judge,
                         "不许再有 fail-closed（'发现没完成就按有模组算'）—— 那正是"
                         "'关着模组也不给成就'的形状，用户 2026-09-24 已裁定撤掉")
        # ★ 两个数**都要记进读数**：它们回答的是不同的问题（"现在开着几个" / "本局加载了几个"），
        #   混成一个正是上次定位时读不出现场的原因。
        self.assertIn("ModMenuEnabledCount()", body, "启用数要算出来（判据就是它）")
        self.assertIn("ModMenuActiveCount()", body, "实际加载数也要算（诊断用）")
        for field in ("enabledRealMods", "activeRealMods"):
            self.assertIn(field, body, f"{field} 要记进状态面")
            self.assertIn(field, hpp, f"状态面 .hpp 要有 {field} 那一格")
        # 判据的第二半（一比一照 PC）：成就 #4 = 打过妈妈，**直接读持久位**。
        # 为什么不调 `PersistentGameData::Unlocked()`：后者在持久位为 0 时还会去看**本局**状态
        # （`0x43968C` 那段），2026-09-23 真机实测它把"没打过妈妈"判成了"已解锁"。
        self.assertIn("kAchievementWomb", body, "要问的是成就 #4（打过妈妈）那一个")
        self.assertIn("kPersistentAchievementArrayOffset", body, "要直接读持久位数组")
        self.assertNotIn("achievementUnlocked(", re.sub(r"//[^\n]*", "", text),
                         "不许调 `Unlocked()` 当判据（它掺了本局状态）；直接读那个字节")
        self.assertIn("achievementSample", body, "抽样要记进读数（自证位置没读错）")
        self.assertIn("kManagerPersistentGameDataOffset", body,
                      "`PersistentGameData` 嵌在 `Manager+0x18`（实证），别用别的偏移")
        self.assertIn("enabled != 0 && !wombUnlocked", body,
                      "「这一局该不该禁」的**查询结果**必须与判据同一个口径（107 起是 `enabled`）——"
                      "既不许恒 1，也不许只按模组个数算（那会把「打完妈妈就不锁」这条丢掉）；"
                      "更不许与判据用不同的数（那样读数会说谎）")
        self.assertIn("wombAchievementUnlocked", hpp,
                      "状态面 .hpp 要有 [31] 那一格（读数里看得出为什么锁着）")
        # 那两个"看着像但语义不对"的引擎接口不许被**调用**。
        # ★ 判据只看**代码**（去掉行注释）：注释里必须能写出它们的名字来解释"为什么不用"
        #   —— 否则下一个人看到 `AchievementUnlocksDisallowed` 这个符号名一定会想调它。
        text_code = re.sub(r"//[^\n]*", "", text)
        self.assertNotIn("AchievementUnlocksDisallowed(", text_code,
                         "别调 `AchievementUnlocksDisallowed(...)`：`Manager::` 那个是空实现，"
                         "`Game::` 那个问的是**特殊种子**（与模组无关）")
        # ★★ 闸门本身（098 的落地点）：挂在 `SetReadOnly` 上、最终参数是「原参数 OR 判定」、
        #    缺回退入口时**什么都不写**（退回 Switch 原生行为，宁可不禁也不误禁）。
        hook = HOOK_MANAGER.read_text(encoding="utf-8")
        self.assertNotIn("HookId::PersistentGameDataTryUnlock", hook,
                         "旧的 `TryUnlock` 闸门必须已经撤掉（098 的设计变更）")
        self.assertIn("HookId::PersistentGameDataSetReadOnly", hook,
                      "闸门要挂在 `SetReadOnly` 上（唯一写只读位的地方）")
        self.assertIn("EntryRelayPersistentGameDataSetReadOnlyCallback", hook,
                      "要有对应的入口中继回调")
        self.assertIn("engineWantsLock || pcShouldLock", hook,
                      "最终参数必须是「引擎原参数 OR 判定」—— 不许覆盖引擎自己的判据（特殊种子/挑战局）")
        self.assertIn("setReadOnlyOriginalMissing", hook,
                      "缺回退入口那一格要记进读数")

    def test_state_surface_field_order_is_pinned(self):
        """★ 状态面的**字段顺序**就是读数工具的下标契约 —— 加格子只能**往后追加**。

        2026-09-23 我自己踩过一次（这次事故的根因）：加新格子时用"插在锚点之前"的改法，
        把后面所有下标都往后挪了一位 —— 于是读数里**每一行都读到了别的格子**
        （"成就 #4 已解锁 = 是"其实读的是"禁成就那一格"，"数组抽样"其实读的是"最后一次字体加载"），
        **连着几轮的真机解读全部作废**，还据此改错了一版判据。
        ⇒ 顺序钉在这里：改顺序必须**同时**改这一条与读数工具，改不动就说明你在挪别人的格子。
        """
        # ★★ 这份清单是**明文编号契约**，不是「文件里现在是什么就钉什么」。
        #    2026-09-23 的教训：先写成"从 .hpp 里现读一份来钉"，结果我自己把新字段
        #    插错位置时门禁**跟着一起错**、照样全绿 ⇒ 白加。现在明文列出，改顺序必须同时改这里。
        expected = [
            "armed", "relayInstalled", "failure", "rowOwner", "rowDrawFrames",
            "rowFallbackFrames", "languageCode", "slot", "engineIndex", "confirmOnOurs",
            "pageEnterCalls", "pageBackCalls", "pageDrivenFrames", "entryCount", "selectedEntry",
            "toggleSaveState", "fontObjectWrites", "setStateSwallowed", "pageOriginX", "pageOriginY",
            "languageSwitches", "pageReloads", "mountRelayFired", "mountRelayFailures",
            "mountServicePublished", "lastFontLoadWord", "achievementsDisallowed",
            "metadataRootRelativeHits", "metadataPrefixedHits", "metadataMisses",
            "activeRealMods", "wombAchievementUnlocked", "achievementSample",
            "persistentReadOnly", "drivenFrames",
            # 批次 097（2026-09-24）加的五格、098 改成统计新闸门（`SetReadOnly`）：
            # 被调到几次 / 引擎本来要锁几次 / 我们按 PC 抬成锁几次 / 最后写下的值 / 缺回退入口。
            "setReadOnlyCalls", "setReadOnlyEngineLocked", "setReadOnlyForcedByPc",
            "setReadOnlyLastValue", "setReadOnlyOriginalMissing",
            # 批次 107（2026-09-24）加的一格：**处于启用状态**的真实模组个数（判据用的就是它）。
            "enabledRealMods",
            # 批次 116（2026-09-24）加的四格：发现清单自证（条数 / 启用位图 / 本局加载位图 / 发现跑过没）。
            "discoveredRealMods", "discoveredEnabledMask", "discoveredActiveMask", "discoveryDone",
            # 批次 117（2026-09-25）加的六格：局内单向闩锁
            # （闩锁值 / 置位次数 / 清零次数 / 上次清零来源 / `GameExit` 被调到几次 / 闩锁可用否）。
            "runLatch", "runLatchSets", "runLatchResets", "runLatchResetSource", "gameExitCalls",
            "runLatchArmed",
            # 批次 118（2026-09-25）加的三格：在一局里吗 / 边沿写位试过几次 / 边沿写位的结果。
            "runInProgress", "runLatchEdgeWrites", "runLatchEdgeWriteResult",
            # 批次 119（2026-09-25）加的两格：出局时留存的污染 / 把留存接回来过几次。
            "runLatchCarriedOver", "runLatchResumes",
            # 批次 120（2026-09-25）加的两格：存档分区里那个标记（我们认为它是几 / 读写失败几次）。
            "taintFileState", "taintFileFailures",
        ]
        fields = re.findall(r"std::uint32_t\s+(\w+);", self.hpp[self.hpp.index("struct State"):])
        self.assertEqual(fields, expected,
                         "状态面字段顺序变了 —— 那是读数工具的下标契约，**只能往后追加**；"
                         "挪动已有格子会让读数里每一行都读错格（2026-09-23 的事故）")

    def test_the_womb_achievement_is_blocked_like_any_other(self):
        """★★ 成就 #4（**打过妈妈**）**不给豁免** —— 模组开着时它也一样不给。

        用户 2026-09-24 裁定（把行为回退到批次 092）：判据就是
        「`有模组开着` 且 `成就 #4 还没解锁`」，而 #4 正是"打过妈妈"那一个。
        093 曾给它开豁免、理由是"不然会锁死"—— 那个理由是错的：**关掉模组之后本函数
        一律返回 false**（见函数里那条 `if (!modsInUse) return false;`），#4 随时拿得到，
        不存在锁死；而"模组开着时连妈腿也不给"正是 PC 的行为
        （2026-09-24 用户原话：使用模组打完妈腿是不应该给成就的）。

        三条判据，缺一不可（**这条门禁是从 093 那条翻转过来的**，理由见上）：
          ① 判定函数回到 092 的签名：**不接收成就号**；
          ② 函数体里除了"没有模组在用时那一处 `return false`"之外**不许再有别的 `return false`**
             —— 多出来的那一处就是给某个成就开的后门；
          ③ 中继仍然拦在入口上，但**不许**把成就号传进判定函数。
        """
        text = CPP.read_text(encoding="utf-8")
        body = function_body(text, "bool AchievementsShouldBeBlockedFor")
        self.assertNotIn("std::uint32_t achievement", body,
                         "判定函数回到 092 的签名：不看是哪一个成就")
        self.assertNotIn("achievement ==", body,
                         "不许再按成就号放行（093 的豁免已由用户 2026-09-24 裁定撤销）")
        self.assertEqual(
            body.count("return false"), 1,
            "函数里只应有一处 `return false`（= 没有模组在用时的一律放行）；"
            "多出来的那一处就是给某个成就开的豁免")
        hook = HOOK_MANAGER.read_text(encoding="utf-8")
        self.assertIn("AchievementsShouldBeBlockedFor(self)", hook,
                      "中继必须把持久数据指针传进判定函数")
        self.assertNotIn("AchievementsShouldBeBlockedFor(self, achievement)", hook,
                         "中继不许再把成就号传进判定函数（那是 093 的形态）")

    def test_state_surface_symbol_is_externally_linked(self):
        """判据是「声明与定义都给 **C 语言链接**」，不是"某一行长什么样"。

        为什么不钉死拼法：`.cpp` 里那句必须是**块形式** `extern "C" { … }`（gcc + `-Werror` 下
        `extern "C" State x = {…};` 会报 `'x' initialized and declared 'extern'`），
        而 `.hpp` 里是普通声明形式 —— 两种拼法都要认，但"有没有 C 语言链接"这条一个字不放松。
        """
        # ① `.hpp` 的声明带 `extern "C"`（行内形式或块形式）。
        hpp_lines = self.hpp.splitlines()
        declaration = [i for i, line in enumerate(hpp_lines) if "g_ModMenuState;" in line]
        self.assertEqual(len(declaration), 1, "`.hpp` 里应当恰好有一条 `g_ModMenuState` 声明")
        index = declaration[0]
        window = "\n".join(hpp_lines[max(0, index - 6):index + 1])
        self.assertIn('extern "C"', window,
                      "`.hpp` 里那条声明必须在 `extern \"C\"` 之下（否则符号会被改编名）")
        # ② `.cpp` 里它是**定义**（带初始化器）—— `extern "C"` 只管链接，定义必须真存在。
        self.assertRegex(self.cpp, r'State\s+g_ModMenuState\s*=\s*\{',
                         "`.cpp` 里必须有带初始化器的定义（不是又一条 extern 声明）")
        # ③ 定义必须在**匿名命名空间之外**：放进去 `nm` 就查不到（2026-09-19 的 D6 事故）。
        #    ⚠️ 匿名命名空间里可以（也应当）写一条 `using` 声明来用它 —— 那只影响名字查找，
        #    不影响链接。所以这里钉的是"**不许再声明/定义**"，不是"名字不许出现"。
        anonymous = self.cpp.index("namespace {")
        definition = self.cpp.index("State g_ModMenuState = {")
        self.assertLess(definition, anonymous, "状态面定义不许放进匿名命名空间")
        self.assertNotIn("State g_ModMenuState", self.cpp[anonymous:],
                         "匿名命名空间里不许再声明/定义状态面（那会让它变成内部链接）；"
                         "要在这里用它只能写 `using` 声明")

    def test_state_surface_symbol_resolves_in_the_built_elf(self):
        """有构建产物时顺带核对一次：**裸名**必须能在当前生产 ELF 里解析到。

        这一条是"读数工具能不能取到状态面"的守门人（读数工具主表里那一项就是裸名）。
        """
        if not ELF.is_file():
            self.skipTest(f"没有本地构建产物 {ELF.relative_to(ROOT)}")
        import importlib.util
        spec = importlib.util.spec_from_file_location("elf_syms_for_mod_menu", ROOT / "tools" / "elf_syms.py")
        elf_syms = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(elf_syms)
        symbols = elf_syms.load_symbols(ELF.read_bytes())
        self.assertTrue("g_ModMenuState" in symbols,
                        "生产 ELF 里没有裸名 `g_ModMenuState` ⇒ 读数工具会读不到"
                        "（是不是放进匿名命名空间了？）")
        mangled = [name for name in symbols if "ModMenuState" in name and name != "g_ModMenuState"]
        self.assertEqual(mangled, [], f"状态面符号不该有改编名：{mangled}")

    # ---- 6) 状态面下标三处一致 ----------------------------------------------

    def test_state_surface_layout_matches_the_reader(self):
        fields = re.findall(r"^\s*std::uint32_t (\w+);", self.hpp, re.M)
        self.assertEqual(len(fields), STATE_FIELDS,
                         f"`State` 的字段数变了（{len(fields)}）：读数工具的下标是按这个数定的")
        # `.cpp` 里的初始化列表个数必须与字段数一致（少一个 = 后面整段错位）。
        init = re.search(r'State g_ModMenuState = \{(.*?)\};', self.cpp, re.S).group(1)
        init = re.sub(r"//[^\n]*", "", init)  # 去掉行注释（里面也有数字）
        self.assertEqual(len(re.findall(r"\b\d+\b", init)), STATE_FIELDS,
                         "`.cpp` 的初始化值个数必须与 `.hpp` 的字段个数一致")
        reader = READER.read_text(encoding="utf-8")
        self.assertIn("'mod_menu_state': 'g_ModMenuState'", reader,
                      "读数工具必须按**裸名**取状态面（见 `.hpp` 的 `extern \"C\"`）")
        # 读数请求的**字数**从字段数算出来，不写死（写死的话每加一个字段都要改这里，
        # 而漏改的表现是"读数少读一段"，很隐蔽）。1 个字 = 8 字节。
        words = (STATE_FIELDS * 4 + 7) // 8
        self.assertIn(f"('mod_menu_state', base + SYMS['mod_menu_state'], {words})", reader,
                      f"读数请求必须读满 {STATE_FIELDS} 个 u32 = {words} 个 8 字节字")
        self.assertIn(f"unpack_from('<{STATE_FIELDS}I'", reader,
                      "读数端解出来的字段数必须与结构体一致")

    # ---- 7) 生产路径里不许有主动报错 ----------------------------------------

    def test_no_active_break_in_the_production_path(self):
        for path, text in ((CPP, self.cpp), (HPP, self.hpp)):
            self.assertNotIn("svcBreak", text, f"{path.name} 里不许出现主动报错指令")

    # ---- 8) HookId 与 kHookCatalog 一一对应，且三条进了读数工具的 HOOK_NAMES --

    def test_new_hooks_are_appended_to_the_catalog_in_order(self):
        catalog = CATALOG.read_text(encoding="utf-8")
        order = re.search(r"enum class HookId[^{]*\{(.*?)\};", catalog, re.S).group(1)
        ids = re.findall(r"(\w+)\s*(?:=\s*\d+)?\s*,", order)
        self.assertEqual(ids[-len(ALL_NEW_HOOKS) - 1:-1], list(ALL_NEW_HOOKS),
                         "新 `HookId` 必须**追加在末尾**（插在中间会让所有老编号挪位）")
        self.assertEqual(ids[-1], "Count")
        rows = re.findall(
            r"\{\s*HookId::(\w+)\s*,\s*\"([^\"]*)\"\s*,\s*HookBackend::(\w+)\s*,\s*(true|false)\s*\}",
            catalog)
        self.assertEqual([row[0] for row in rows], ids[:-1],
                         "`kHookCatalog` 必须每个挂点一行、顺序与 `HookId` 完全一致")
        for name in ALL_NEW_HOOKS:
            self.assertIn((name, name, "EntryRelay", "false"), rows,
                          f"{name} 那一行必须是「名字一致 / 入口中继 / 可选」")
        reader = READER.read_text(encoding="utf-8")
        # 注意：`.*?` 会停在注释里的 `` `[i]` `` 那个方括号上 ⇒ 用"行尾的 `]`"当结束符。
        names = re.search(r"^HOOK_NAMES = \[(.*?)\]\n", reader, re.S | re.M).group(1)
        tail = re.findall(r"'(\w+)'", names)[-len(ALL_NEW_HOOKS):]
        self.assertEqual(tail, list(ALL_NEW_HOOKS),
                         "读数工具的 `HOOK_NAMES` 必须按同一顺序追加这几条"
                         "（它按 HookId 顺序读 `g_hookCallbacks`）")

    def test_the_adapter_wires_all_callbacks(self):
        """每个新挂点都要有回调声明 —— **返回类型不限**（按目标函数的 ABI 定，
        例如 `TryUnlock` 返回 `bool`（w0），回调就按 `std::uint32_t` 声明）。"""
        adapter = ADAPTER.read_text(encoding="utf-8")
        for name in ALL_NEW_HOOKS:
            self.assertRegex(adapter, rf'extern "C" [\w:<> ]+EntryRelay{name}Callback',
                             f"{name} 缺回调声明（在 entry_relay_hook_adapter.cpp）")
            self.assertIn(f"case HookId::{name}:", adapter, f"{name} 缺 `BindingOf` 分支")
            self.assertIn(f"&EntryRelay{name}Callback", adapter, f"{name} 缺登记")

    # ---- 9) 探针与生产互斥 ---------------------------------------------------

    def test_probe_and_production_never_install_the_same_entry(self):
        hook = HOOK_MANAGER.read_text(encoding="utf-8")
        predicate = function_body(hook, "bool SkipOptionalHooksPredicate")
        probe_branch = predicate.split(
            "#if defined(EXL_PROBE_BREAK) && EXL_PROBE_BREAK_NATIVE_MODS_MENU", 1)
        self.assertEqual(len(probe_branch), 2,
                         "跳过判据里必须有「探针构建 ⇒ 跳过生产这三个挂点」那一段")
        for name in NEW_HOOKS:
            self.assertIn(f"HookId::{name}", probe_branch[1].split("#endif", 1)[0],
                          f"探针构建里没跳过 {name}（同一入口装第二次必然 EntryMismatch）")
        # 每帧点与安装点都必须落在"探针那一段的 `#else`"里。
        update_site = hook.split("isaac::runtime::probe::NativeModsMenuProbeUpdate();", 1)[1]
        self.assertIn("ModMenuNativeUpdate();", update_site.split("#endif", 1)[0],
                      "每帧点必须写在探针那条 `#if` 的 `#else` 分支里（互斥）")
        install_site = hook.split(
            "isaac::runtime::probe::NativeModsMenuProbeInstallRelay(module);", 1)[1]
        self.assertIn("ModMenuNativeInstall(module);", install_site.split("#endif", 1)[0],
                      "安装点必须写在探针那条 `#if` 的 `#else` 分支里（互斥）")

    def test_diagnostic_stage_builds_are_untouched(self):
        """诊断阶段构建的行为一个字都不许变（那些构建是别的调查在用的）。

        ★ 守卫在 `ModMenuNativeUpdate()` 的**函数体开头**，不在 `hook_manager.cpp` 的调用点：
          `test_stage118_managed_file_write_diagnostic` 拿 `#if !defined(EXL_DIAGNOSTIC_STAGE)`
          当**切片结束符**去取 `ManagerUpdateHook::Callback` 那一段（它要确认那里有"跑原函数"
          那一句），在调用点再插一条同样的条件会让它切早 ⇒ 那条既有门禁会红（批次 077 实测）。
          函数体里早退与"调用点不调"完全等价：一次引擎读都不发生。
        """
        body = function_body(self.cpp, "void ModMenuNativeUpdate() noexcept")
        self.assertIn("#if defined(EXL_DIAGNOSTIC_STAGE)", body,
                      "诊断阶段构建必须在这里直接返回（什么都不做）")
        self.assertLess(body.index("#if defined(EXL_DIAGNOSTIC_STAGE)"),
                        body.index("FindTargetModule"),
                        "守卫必须排在**任何**引擎访问之前（早退要早）")
        early = body[body.index("#if defined(EXL_DIAGNOSTIC_STAGE)"):body.index("#endif")]
        self.assertIn("return;", early, "那一支里必须是直接返回")
        # 调用点那一段不许再出现同样的条件（否则 stage118 那条既有门禁会红）。
        hook = HOOK_MANAGER.read_text(encoding="utf-8")
        site = hook.split("isaac::runtime::probe::NativeModsMenuProbeUpdate();", 1)[1]
        site = site.split("#endif", 1)[0]
        self.assertIn("ModMenuNativeUpdate();", site, "每帧点必须写在探针那条 `#if` 的 `#else` 里")
        self.assertNotIn("#if !defined(EXL_DIAGNOSTIC_STAGE)", site,
                         "调用点不许再加诊断阶段守卫（会切坏 stage118 那条门禁的解析）")
        self.assertIn("ModMenuNativeInstall(module);", hook, "安装点必须存在")

    # ---- 10) 不搬假数据 ------------------------------------------------------

    def test_no_fake_mod_names_in_production(self):
        for fake in ("PROBE-MOD-A", "PROBE-MOD-B", "PROBE-MOD-C"):
            self.assertNotIn(fake, self.cpp, f"生产代码里不许出现固定测试名 {fake}")
            self.assertNotIn(fake, self.hpp, f"生产头文件里不许出现固定测试名 {fake}")
        self.assertIn("不搬假数据", self.cpp, "这条纪律要写在代码里（下一个人会想加回去）")

    # ---- 11) 不搬那两条"贴图路线" --------------------------------------------

    def test_the_two_dead_sprite_routes_are_not_carried_over(self):
        for token in ("LoadImage", "SmartPointerShim", "kImageManagerLoadMemoryOffset",
                      "kImageManagerLoadFileOffset", "smart_pointer_shim"):
            self.assertNotIn(token, self.cpp,
                             f"生产版不许搬贴图路线（{token}）：075 之后那一行由引擎自己画，"
                             "那两条已是死路（真机崩过）")

    # ---- 12) 引擎自己的字体对象：本批起**一个字节都不许动** ------------------

    def test_the_engine_font_object_is_never_written(self):
        """077 曾把扩展字体装进引擎字体对象换中文；真机推翻 ⇒ 078 整个撤掉。

        真机结论（`docs/会话交接-2026-09-23-模组页搬生产完成.md` 第四节 4.1）：
        `Menu_Mods::Render` 用的是**按字节**的 `Font::DrawStringScaled(char const*, …)`
        —— 它把字符串里每个字节当一个字形编号，中文（UTF-8 三字节、每字节 ≥ 0x80）只会画出
        三个不相干的字形 ⇒ **换字体救不了中文**。代价却是多 32MB 字图集、观感还会变。

        ⇒ 本条从"要装进引擎字体对象"**加强**成"一个字节都不许改那个对象"：
        换字体的入口（`Font::Load` / `IsLoaded`）与那段接线的名字**一个都不许再出现**。
        """
        for token in ("TeamMeatFontExtended12", "FontLoadFn", "FontIsLoadedFn", "fontLoad",
                      "fontIsLoaded", "EnsurePageFont", "cjkFontState"):
            self.assertNotIn(token, self.cpp,
                             f"换字体那段接线（{token}）已按真机结论撤掉，不许再出现")
            self.assertNotIn(token, self.hpp, f"换字体那段接线（{token}）已按真机结论撤掉")
        self.assertNotIn('"font/CJK/LanaPixel.fnt"', self.cpp,
                         "不许用 `font/CJK/LanaPixel.fnt`：它的图集背景不透明黑，"
                         "真机被画成黑方块（比没有中文更糟）")
        # 那个字体对象**仍然要被读**（兜底画字时取行高）——但只能读，不许写。
        # 判据 = 这个偏移**只许出现在两处**：常量自己的定义、以及 `DrawRowLabel` 里取字体对象那一次。
        # （任何多出来的用处都意味着有人又拿它去写那个对象了。）
        self.assertIn("constexpr std::uintptr_t kManagerFontOffset = 0x117120;", self.cpp,
                      "`g_Manager + 0x117120` 要有一个具名常量")
        draw_body = function_body(self.cpp, "bool DrawRowLabel")
        self.assertIn("kManagerFontOffset", draw_body,
                      "兜底画字要用它取行高（`Font::GetLineHeight`）—— 唯一的合法用处")
        self.assertEqual(self.cpp.count("kManagerFontOffset"), 2,
                         "这个偏移只许出现两次（常量定义 + 兜底画字那一次）；"
                         "多出来的用处多半又是「往那个对象里写东西」")
        # 状态面那一格是本条纪律的载体：它数"我们改写过几次"，恒 0。
        self.assertIn("fontObjectWrites", self.hpp, "状态面里要有这一格（恒 0）的说明")
        self.assertIn("恒 0", self.hpp, "要写明它恒 0，不然下一个人会以为它忘了赋值")

    # ---- 12b) 语言码**每帧都问**，变了就重载页面（2026-09-23 批次 078）--------

    def test_language_is_polled_every_frame_and_changes_trigger_a_reload(self):
        """用户在选项页里换语言是**当场生效**的（077 的"一次定死"前提被实测推翻）。

        而模组页那张纸是**分语言**的（`rp_patch/resources.zh/` 写「模组」、`resources.de/` 写
        `MODS`）⇒ 语言变了必须让页面按新语言重载一次动画。
        """
        resolve = function_body(self.cpp, "void ResolveLanguage")
        # ① 每帧都问：不许再靠 `languageState != 0` 早退（那正是"一次定死"的写法）。
        self.assertNotIn("if (g_Menu.languageState != 0)", resolve,
                         "不许再用 `languageState` 当「问过一次就不再问」的开关")
        self.assertIn("getLanguageCode", resolve, "每帧问一次语言码（一次读，代价可忽略）")
        self.assertIn("languageSeen", resolve, "要区分「第一次读到」与「语言变了」")
        self.assertIn("ModRowLayoutForLanguage", resolve, "语言变了必须重挑那一列的挪位表")
        # ② 变了就挂"重载页面"的标志（真正动手在 ReloadPageForLanguage 里）。
        self.assertIn("pageReloadPending", resolve, "语言变了要挂起重载标志")
        self.assertIn("languageSwitches", resolve, "变了几次要记进状态面（读数里一眼看得出）")
        # ③ 重载：**照引擎自己的换语言协议**做那三步（2026-09-23 批次 083 重新启用 079 的做法）。
        #
        # ★★ 为什么 079 当年被撤回、现在又拿回来 —— 这段历史必须留在这里，免得第三次踩：
        #    079 上卡后真机"EID 的信息显示坏了"，当时的结论是"引擎那两个全局回收把我们这侧
        #    **引擎引用计数看不见的持有人**放掉了"，于是 080 撤回、并加了"不许再调"的禁止性判据。
        #    **但那个结论是误判**：同一天定位到另一个真 bug —— `SetSessionContentMountService`
        #    **从来没被调用过** ⇒ 换语言（`Manager::SetLanguage` 尾调 `RebuildContentMountPoints`）
        #    之后 **Mod 的挂载点一个都没恢复** ⇒ EID 下次开局重新加载字体时 `.fnt` 打不开
        #    ⇒ 字体永久"未加载"（批次 082 已修）。那个 bug 与回收无关、**每次换语言都会犯**
        #    （080 撤回之后 EID 照样坏 —— 当时的记录自己也写了这一点）。
        #    ⇒ 修掉挂载点 bug 之后，经用户批准重试 079 的做法（2026-09-23 批次 083）。
        #    **判据**：如果真机 EID 又坏，先看状态面 [24]（挂载服务发布了没）与读数里的
        #    Lua 错误历史，**别再直接归因给回收**。
        reload_body = function_body(self.cpp, "void ReloadPageForLanguage")
        # ★ 批次 105（用户 2026-09-24 批准把这条**放宽到语义**）：原来这两个 token 钉的是
        #   `freeUnreferencedImages(reinterpret_cast<void*>(anmCache))` —— 连"必须用裸转换"这个
        #   **拼法**也一起钉了。而 105 把本 TU 的引擎读/写全收进了访问层（改成 `AsObject(anmCache)`），
        #   拼法必然变，**意图一个字不变**：三步都在、顺序与引擎一致、参数是那个 GOT 槽读出来的指针。
        #   ⇒ 判据改成「调用名」+「同一段里有 `anmCache`」两条合起来。
        #   ★ 不许再放宽成"只找调用名"：那样"参数被换成别的指针"就查不出来了。
        steps = ("modsPreLanguageSwitch(g_ModsObject)",
                 "freeUnreferencedImages(",
                 "freeUnreferencedEntries(",
                 "modsPostLanguageSwitch(g_ModsObject)")
        for token in steps:
            self.assertIn(token, reload_body, f"换语言协议缺了这一步：{token}")
        for call in ("freeUnreferencedImages(", "freeUnreferencedEntries("):
            argument = reload_body.split(call, 1)[1].split(";", 1)[0]
            self.assertIn("anmCache", argument,
                          f"`{call}…)` 的参数必须是从 GOT 槽读出来的 `anmCache` ——"
                          "引擎那两个回收函数放掉的是它管的那些资源，换成别的指针就是放错东西")
        order = [reload_body.index(token) for token in steps]
        self.assertEqual(order, sorted(order),
                         "那三步的顺序必须与引擎一致：Pre 放开 → 回收 → Post 重新加载")
        self.assertIn("ReadSlot(module, kAnmCacheSlotOffset", reload_body,
                      "`&g_AnmCache` 必须从 GOT 槽读出来（引擎自己的取法），不许瞎传指针")
        self.assertIn("ModPageIsActive(g_Menu.menuState)", reload_body,
                      "换动画必须在**页面没显示**时做（正画着的时候换它的动画没有意义）")
        # 四个入口都要逐字节守卫过：任一不过 ⇒ 一次都不调用（绝不盲目跳地址）。
        verify = function_body(self.cpp, "void VerifyEntries")
        for guard in ("kMenuModsPreLanguageSwitchOffset", "kMenuModsPostLanguageSwitchOffset",
                      "kAnmCacheFreeUnreferencedImagesOffset",
                      "kAnmCacheFreeUnreferencedEntriesOffset"):
            self.assertIn(guard, verify, f"{guard} 的入口必须逐字节核对过才允许调用")
        self.assertNotIn("g_Menu.modsCtor(", reload_body,
                         "★ 重载**不许**重跑 `ctor`：它会在活对象上重建内嵌 ANM2，"
                         "把旧动画在缓存里的引用直接丢掉（漏）")
        self.assertIn("ModPageIsActive", reload_body,
                      "页面正显示时不换它的动画（等它关了再换，标志还挂着）")
        self.assertIn("pageReloads", reload_body, "重载次数要进状态面")
        self.assertIn("positionSet = 0", reload_body,
                      "位置那套状态机要跟着重来（`Init` 会写回页面位置）")
        # ④ 时机：在**每帧更新**里调，不在渲染回调里（那一下会 `ANM2::Load`）。
        update = function_body(self.cpp, "void ModMenuNativeUpdate() noexcept")
        self.assertIn("ReloadPageForLanguage(*module);", update, "每帧更新里要调它（要传 module：那三步要用它读 GOT 槽）")
        title_relay = function_body(self.cpp, 'extern "C" void EntryRelayMenuTitleRenderCallback')
        self.assertNotIn("ReloadPageForLanguage", title_relay,
                         "渲染回调里不许重载页面（`ANM2::Load` 不能在渲染批次中间做）")

    # ---- 13) 只改内存，唯一例外是离开页面时那一次落盘 ------------------------

    def test_only_memory_is_written_and_toggles_are_saved_once_on_exit(self):
        self.assertEqual(self.cpp.count("ModMenuSaveToggles()"), 1,
                         "落盘只允许一次（离开模组页时那一次）")
        page = function_body(self.cpp, "void ModsPageUpdate")
        self.assertIn("ModMenuSaveToggles()", page, "那一次落盘就在模组页的每帧驱动里")
        self.assertIn("ModPageShouldPersist", page, "「只有真改过才写」由纯判定说了算")
        leave = page.split("g_Menu.pageWasActive != 0 && !active", 1)[1].split("if (!active)", 1)[0]
        self.assertIn("ModMenuSaveToggles()", leave,
                      "落盘必须发生在「刚刚离开页面」那一刻（不是每帧）")


if __name__ == "__main__":
    unittest.main()
