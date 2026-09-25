"""门禁：**"加载一次就永久有效"的引擎句柄，必须有作废路径**；而且首选路线必须是**磁盘路径**加载。

## 这条门禁由来的事故（2026-09-23，批次 068 → 069 → 070 → 071）

用户实测："有部分对局进去了再退出，**只有「模组」那一行的字会消失**，纸和其他行都在"，重启即好。

根因（070 之后定案）：选择界面那一行的标签是运行时**从内存**交给引擎贴图管理器的
（`ImageManager::LoadImage` 的内存重载），还登记在**我们自己编的缓存键**下。我们是全工程
**唯一**这么做的地方；引擎自己的行、以及所有模组（EID 等）都是**按磁盘路径**加载
（`ANM2::Load`，`Sprite:Load` 走的就是这条），它们从不会消失 —— 关卡加载会把
"没有磁盘文件背书的贴图"从图片缓存里清掉。

四条走过的路（都在真机上验过，别回头）：
  * 068：用"`Game*` 有没有值"当作废信号 ⇒ 真机**一次都没触发**（回到菜单时那个指针不变 0）；
  * 069：改用运行时自己的**关卡/房间事件派发计数** ⇒ 判据生效了（`[97] = 1`），但仍然画不出来；
  * 070：每次重载**换缓存键**（同名会命中失效条目）⇒ 重载"成功"、状态良好、画了 3856 帧，
    屏幕上一个字都没有 ⇒ 手里那个图片对象是**死的**；
  * **071**：改成**引擎自己的按路径加载**（`ANM2::Load(path, true)`）+ `ANM2::Render` ——
    **真机上崩了**（`Data Abort @ 0x0`，`AnimationLayer::GetSourceQuad` 里的空精灵表：
    引擎按 `.anm2` 里的 `<Spritesheet Path="x.png">` 找 `.png`，我们只放了 `.pcx`）；
  * **072（本版）**：改用引擎**按文件名版**的贴图加载
    `ImageManager::LoadImage(char const* path, ...)`（与内存版同一个管理器、同一个返回值形状），
    绘制仍用已验证的 `Manager::RenderQuad`，并且**拿到空指针就不画**；
    图在构建期落成真实文件（`tools/emit_mod_row_art.py`）。内存那条路线降为**兜底**。

## 判据（哪一条都不许放松）

1. 内存那条兜底路线**仍然**要保留"已加载就早退"的保护（它是防每帧重载的保护），
   **同时**必须有把句柄清空、并换缓存键的路径 —— 早退不能变成"永不再加载"；
2. 作废必须挂在**关卡/房间事件计数**上（不是"猜游戏状态"），而且 `Game*` 那格只作为留证；
3. **绘制优先级**必须是"ANM2 路线 → 内存贴图 → 用字画"这个次序，任何一条断了自动落到下一条；
4. 关卡切换的**同一个触发点**必须让 ANM2 路线**从磁盘重读一次**（同一个路径再 `Load`），
   并去重（只在事件计数变化时发生）—— ★ 这条是"它与内存路线的本质区别"，必须钉住；
5. ANM2 那条路的路径串**只能**走 `isaac::runtime::BuildNativeString`（`ANM2::Load` 收的是
   libc++ 的 `std::string`），且 Load 之后必须读 `ANM2+0x149` 确认图形真的载入了 ——
   "Load 过了"不等于"图画得出来"；
6. 新增的每一个判据都要能在读数里看见（诊断字里要有对应格子）。
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "runtime" / "source" / "probe" / "native_mods_menu_probe.cpp"
HPP = ROOT / "runtime" / "source" / "probe" / "native_mods_menu_probe.hpp"


def function_body(text: str, signature: str) -> str:
    """取一个函数的函数体（从签名起、到下一个顶格的 `}` 为止）。"""
    assert signature in text, f"没找到 {signature}"
    return text.split(signature, 1)[1].split("\n}\n", 1)[0]


class ProbeImageCacheInvalidationTests(unittest.TestCase):
    # ---- ① 内存兜底路线：早退 + 作废 + 换缓存键 -------------------------------

    def test_prepare_image_keeps_its_early_return(self):
        body = function_body(PROBE.read_text(encoding="utf-8"), "bool ModRowPrepareImage")
        self.assertIn("image.pointer != nullptr", body,
                      "准备贴图函数必须保留「已加载就早退」的保护（否则每帧都会重新加载）")

    def test_somewhere_clears_the_cached_handle(self):
        text = PROBE.read_text(encoding="utf-8")
        self.assertRegex(text, r"image\.pointer\s*=\s*nullptr",
                         "必须存在把贴图句柄作废的路径 —— 否则「已加载就早退」= 永不再加载")
        self.assertRegex(text, r"imageState\s*=\s*0",
                         "作废时也要把失败/已加载状态清掉，否则重试逻辑不放行")
        self.assertIn("g_ModRowImageName[at] = '\\0'", text,
                      "重载时要换缓存键（同名会命中失效条目，070 已证）")

    def test_invalidation_is_driven_by_the_level_event_counters(self):
        """作废必须挂在**事件计数**上，不是"猜游戏状态"。

        2026-09-23 实测教训：第一版用"`Game*` 有没有值"当判据，**真机一次都没触发**
        （读数 `[97] = 0`，可用户确实进过局）—— 回到菜单时那个指针并不变 0。
        改成运行时自己的回调派发计数（`MC_POST_NEW_LEVEL` / `MC_POST_NEW_ROOM`）之后才成立。
        """
        text = PROBE.read_text(encoding="utf-8")
        self.assertIn("g_CallbackDispatchCounts", text,
                      "作废要挂在运行时的回调派发计数上（关卡/房间事件）")
        self.assertIn("kCallbackPostNewLevel", text)
        self.assertIn("ModRowInvalidateImageOnGameTransition", text)
        self.assertIn("gamePresent", text, "`Game*` 仍然留一格做证据，但**不再**是判据")

    # ---- ② 新路线：引擎按**文件名**从磁盘加载贴图（072 起是首选） ----------------

    def test_file_route_is_the_preferred_draw_path(self):
        """绘制优先级：磁盘那张贴图 → 内存贴图 → 用字画（顺序不许颠倒，且**空图不画**）。"""
        body = function_body(PROBE.read_text(encoding="utf-8"),
                             'extern "C" void ModRowMenuGameRenderRelayCallback')
        self.assertIn("ModRowDrawSprite", body, "渲染回调里必须走贴图那条路")
        self.assertIn("ModRowDrawLabel", body, "贴图拿不到时必须落到用字兜底")
        self.assertLess(body.index("ModRowDrawSprite"), body.index("ModRowDrawLabel"),
                        "先试贴图、拿不到再画字（顺序不许颠倒）")
        self.assertRegex(body, r"if\s*\(\s*!\s*ModRowDrawSprite\(",
                         "用字兜底只能挂在「贴图没画成」这个条件上（071 的崩溃就是画了空图）")

        draw = function_body(PROBE.read_text(encoding="utf-8"), "bool ModRowDrawSprite")
        self.assertLess(draw.index("fileImage.pointer != nullptr"),
                        draw.index("image.pointer != nullptr"),
                        "磁盘那张图必须排在内存那张之前 —— 内存那张没有文件背书，会被关卡加载清掉")
        self.assertLess(draw.index("fileImage.pointer != nullptr"), draw.index("renderQuad("),
                        "★ 先判空、再拿去画（071 真机就是「画了空的东西」才崩的）")
        self.assertLess(draw.index("image.pointer != nullptr"), draw.index("renderQuad("),
                        "内存那条路同样要先判空再画")
        self.assertIn("return false", draw, "两张图都没有时必须返回 false，交给调用方兜底")

    def test_never_touches_the_anm2_render_route(self):
        """**绝不再走 ANM2 那条渲染路**：071 真机上它 `Data Abort @ 0x0`（空精灵表）。"""
        text = PROBE.read_text(encoding="utf-8")
        for marker in ("kSpriteRenderOffset", "kSpriteLoadOffset", "kSpriteCtorOffset",
                       "kSpritePlayOffset", "kSpriteObjectSize"):
            self.assertNotIn(marker, text, f"{marker} 不该再出现在探针里（072 已换路线）")
        self.assertNotIn("spriteRender(", text, "不许再调 `ANM2::Render`")

    def test_file_route_uses_the_file_variant_of_load_image(self):
        """必须用**按文件名版**的 `ImageManager::LoadImage`，入口要逐字节守卫。"""
        text = PROBE.read_text(encoding="utf-8")
        self.assertIn("kImageManagerLoadFileOffset", text, "按文件名版的入口偏移")
        self.assertIn("kImageManagerLoadFileExpectedBytes", text, "入口必须逐字节守卫")
        self.assertIn("fileGuardState = 1", text, "守卫过了要留证（读数 [108]）")
        self.assertEqual(text.count("kImageManagerLoadMemoryOffset"), 1,
                         "内存版入口只允许在 `ModRowPrepareImage` 里取一次")

    def test_file_route_prefers_installed_relay_original_and_guards_only_without_it(self):
        """自身入口中继改写前 16 字节后仍要调用文件版加载；无中继才允许原入口守卫。"""
        body = function_body(PROBE.read_text(encoding="utf-8"), "bool ModRowPrepareFileImage")
        relay = "Original<ModRowContext::LoadImageFileFn>"
        guard = "Guarded(module, kImageManagerLoadFileOffset"
        self.assertIn(relay, body, "已安装中继必须取回放原序言的入口")
        self.assertIn(guard, body, "未安装中继时仍须校验原版入口")
        self.assertLess(body.index(relay), body.index(guard), "应先取中继原函数、再按需守卫")
        self.assertRegex(body, r"if\s*\(\s*loadImageFile\s*!=\s*nullptr\s*\)",
                         "原函数存在时必须直接使用，不能再比对已被改写的入口")
        self.assertIn("g_ModRow.loadImageFile = loadImageFile", body)

    def test_file_route_is_prepared_once_not_every_frame(self):
        body = function_body(PROBE.read_text(encoding="utf-8"), "bool ModRowPrepareFileImage")
        self.assertIn("fileState == kFileRouteReady", body, "装好之后必须早退（不每帧重载）")
        self.assertIn("fileState != 0", body, "失败过也不每帧重试")
        self.assertIn("fileState != kFileRouteLanguagePending", body,
                      "但「语言还没定」不算失败：语言定下来之后必须继续往下走")

    def test_level_transition_reloads_the_image_from_disk(self):
        """同一触发点上：内存句柄作废 **且** 磁盘那张图重读一次。"""
        text = PROBE.read_text(encoding="utf-8")
        body = function_body(text, "void ModRowInvalidateImageOnGameTransition")
        self.assertIn("ModRowReloadFileImageFromDisk", body,
                      "★ 关卡切换后必须让新路线也**从磁盘**重读一次（同一个触发点）")
        reload_body = function_body(text, "void ModRowReloadFileImageFromDisk")
        self.assertIn("g_ModRow.filePath", reload_body,
                      "重读必须按**当初命中的那条路径**再加载一次")
        self.assertIn("loadImageFile(", reload_body, "重读必须真的再调一次按文件名版的加载")
        self.assertIn("fileImage = isaac::runtime::relay::SmartPointerShim{}", reload_body,
                      "重读拿不到时必须**清空**那张图：留着就是画一张引擎已经收回去的图")
        self.assertEqual(text.count("ModRowReloadFileImageFromDisk();"), 1,
                         "从磁盘重读只允许有一个调用点（关卡/房间事件计数变化那里）")

    def test_candidate_paths_are_built_without_truncation(self):
        """候选路径必须「拼不完整就算失败」，绝不能截断出一条看着像的路径。"""
        body = function_body(PROBE.read_text(encoding="utf-8"), "bool ModRowBuildFileImagePaths")
        self.assertIn("ModRowAppendText", body, "拼路径要走上限受检的追加函数")
        self.assertIn("kModRowFileSuffix", body)
        self.assertNotIn("snprintf", body)
        self.assertNotIn("strncpy", body)

    def test_new_judgements_are_visible_in_the_diagnostics(self):
        """这一批的每条判据都要在读数里看得见，而且三处（.cpp / .hpp / 读数工具）一致。"""
        text = PROBE.read_text(encoding="utf-8")
        hpp = HPP.read_text(encoding="utf-8")
        reader = (ROOT / "tools" / "read_device_state_via_gdb.py").read_text(encoding="utf-8")
        for cell in ("modRowFileState", "modRowFileCandidate", "modRowFileHits",
                     "modRowFileLoadCalls", "modRowFileDraws", "modRowFileReloads",
                     "modRowFilePathLength", "modRowFileFlag", "modRowFileGuardState"):
            self.assertIn(cell, text, f"探针状态里应当有 {cell}")
            self.assertIn(cell, hpp, f".hpp 的说明里也要有 {cell}（三处必须一致）")
        self.assertIn("按文件名加载贴图", reader,
                      "读数工具要解释新路线（否则现场读数没人看得懂）")
        self.assertIn("f109[102]", reader, "命中掩码要在读数里打出来")


if __name__ == "__main__":
    unittest.main()
