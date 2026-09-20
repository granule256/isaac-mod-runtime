#pragma once

#include <cstddef>
#include <string_view>

// 模组开关菜单的脚本（2026-09-16，路线 B）。
//
// 为什么是**内嵌 Lua 脚本**而不是原生 C++ 界面：
//   * 画字走 `Font:DrawStringScaledUTF8`、读键走 `Input:IsActionTriggered` —— 这两族都已经
//     实现、而且 EID 在真机上就是用它们画的（`Font` 那段有完整的 ABI 证据与真机读数）；
//     原生界面等于把字体对象生命周期与绘制坐标再实现一遍；
//   * 脚本与运行时之间只有四个函数（`RuntimeMods.List/SetEnabled/Save/Reload`），
//     数据与时序留在 C++ 一侧（`hook_manager` 扫描时灌清单）。
//
// 它在**第一个模组的入口脚本之前**执行（见 `lua_runtime.cpp` 的 `InitializeScript`）：
// 这样它的 `RegisterMod` 与别的模组完全同路（自己的 owner、自己的回调），不需要新增派发机制。
//
// 纪律：
//   * 菜单自己任何一步出错都只影响菜单（`pcall` 包住绘制与读键），绝不影响模组加载；
//   * 不写任何**我们自己的**路径字面量：清单与状态都来自 `RuntimeMods`；唯一写出来的是
//     游戏自带的字体名（`font/droid.fnt` 支持中文，加载不到就退回 `font/terminus.fnt` 并改用英文）。
namespace isaac::runtime {

//: 菜单脚本的 chunk 名（出现在 Lua 报错里，一眼能认出"这是运行时的菜单"）。
inline constexpr char kModMenuChunkName[] = "@isaac-switch-mod-menu";
//: 菜单在回调登记表里的名字（`RegisterMod` 的第一个参数）。
inline constexpr char kModMenuName[] = "IsaacSwitchModMenu";

inline constexpr std::string_view kEmbeddedModMenuScript = R"LUA(
-- 模组开关菜单（Isaac Switch Runtime 自带；不是一个 PC 模组）
--
-- 开关方式：ACTION_MAP（Switch 上的“-”）呼出/收起；菜单里 上/下 选择、A 切换、B 关闭。
-- 关掉的模组要**重启游戏**才真正不加载（模组资源在启动时挂载），菜单会把这一条写在屏幕上。

local RuntimeMods = RuntimeMods
local MC = ModCallbacks

local mod = RegisterMod("IsaacSwitchModMenu", 1)

-- 里程碑位（与 `RuntimeMods.Report` 的约定一致；真机排障靠它）：
--   1 脚本已加载并登记成功、2 字体装上、3 字体失败、4 菜单打开、5 update 回调跑过、
--   6 切换过一次、7 落盘成功
local function Report(code)
  if RuntimeMods and RuntimeMods.Report then
    pcall(RuntimeMods.Report, code)
  end
end
Report(1)

local STATE = {
  open = false,
  selected = 1,
  items = {},
  message = "",
  messageFrames = 0,
  font = nil,
  cjk = false,
  fontFailed = false,
  dirty = false,
  held = {},
  scanFrames = 0,
  learnedController = nil,
}

--: 呼出/导航用到的动作号。优先读 `ButtonAction` 表，**取不到就用数字兜底** ——
--: 2026-09-16 真机读数：`-` = 动作号 13、手柄序号 **1**（不是 0）。枚举表一旦拿不到
--: （或字段名变了），数字兜底能保证菜单照旧能开，不至于变成一个"查不出来"的问题。
local function ActionCode(name, fallback)
  if ButtonAction ~= nil then
    local value = ButtonAction[name]
    if type(value) == "number" then
      return value
    end
  end
  return fallback
end

-- 呼出方式（2026-09-19 批次 080 改）：**组合键 = `-`（ACTION_MAP）+ `+`（ACTION_PAUSE）同时按住**。
--
-- 为什么不再用单键：`-` 是**游戏自己的地图键**，GoodTrip 的地图也挂在它上面 —— 单键呼出时
-- 一按 `-` 会同时弹出「游戏地图 + GoodTrip 叠加」和「我们的模组开关」，用户实测反馈过。
-- 而 `+` 是游戏的暂停键，单独占用同样会抢。
-- 组合键的三条互不干扰：单独 `-` = 地图；单独 `+` = 暂停；**两个一起** = 我们的菜单。
local KEY = {
  open = ActionCode("ACTION_MAP", 13),
  --: 组合键的第二个键：`ACTION_PAUSE`（Switch 上的 `+`）。
  open_modifier = ActionCode("ACTION_PAUSE", 12),
  up = ActionCode("ACTION_MENUUP", 22),
  up_alt = ActionCode("ACTION_UP", 2),
  down = ActionCode("ACTION_MENUDOWN", 23),
  down_alt = ActionCode("ACTION_DOWN", 3),
  confirm = ActionCode("ACTION_MENUCONFIRM", 14),
  confirm_alt = ActionCode("ACTION_ITEM", 9),
  back = ActionCode("ACTION_MENUBACK", 15),
  back_alt = ActionCode("ACTION_BOMB", 8),
}

local COLOR_SHADOW = Color(0, 0, 0, 0.85)
local COLOR_TEXT = Color(1, 1, 1, 1)
local COLOR_DIM = Color(0.62, 0.62, 0.62, 1)
local COLOR_ON = Color(0.45, 1, 0.45, 1)
local COLOR_OFF = Color(1, 0.45, 0.45, 1)
local COLOR_WARN = Color(1, 0.85, 0.35, 1)

local TEXT = {
  zh = {
    title = "模组开关（A 切换 / B 关闭）",
    none = "没有发现模组（检查 SD 卡上的 isaac_mods/mods）",
    dirty = "有改动，关闭菜单时保存",
    hint = "关掉的模组要重启游戏才不加载；呼出键：同时按住 - 和 +",
    saved = "开关已保存（重启游戏后生效）",
    failed = "保存失败：存档通道不可用",
    notoggle = "改不了这一项",
    restart = "  (重启后生效)",
    error = "菜单出错，已关闭",
    on = "已启用",
    off = "已停用",
  },
  en = {
    title = "MODS (A: toggle  B: close)",
    none = "No mods found (check isaac_mods/mods on the SD card)",
    dirty = "Changed - saving when the menu closes",
    hint = "Disabled mods stop loading after a restart; open: hold - and + together",
    saved = "Saved (takes effect after restart)",
    failed = "Save failed: save channel unavailable",
    notoggle = "Cannot change this one",
    restart = "  (restart to apply)",
    error = "Menu error - closed",
    on = "enabled",
    off = "disabled",
  },
}

local function T(key)
  local table_ = STATE.cjk and TEXT.zh or TEXT.en
  return table_[key] or TEXT.en[key] or key
end

local function Refresh()
  local list = {}
  if RuntimeMods and RuntimeMods.List then
    local ok, value = pcall(RuntimeMods.List)
    if ok and type(value) == "table" then
      list = value
    end
  end
  STATE.items = list
  if STATE.selected > #list then
    STATE.selected = math.max(1, #list)
  end
end

local function Say(text)
  STATE.message = text
  STATE.messageFrames = 180
end

--: 依次尝试的字体。
--:
--: ★ 2026-09-17 更正：**游戏自带字体都没有中文字形** —— `font/droid.fnt` 实测是纯 Latin-1
--: （`tools/fnt_glyph_report.py`：191 字形、码位上限 0xFF、中日韩 **0** 个），此前这里标着
--: `cjk = true` 是错的 ⇒ 中文文案会**静默空白**（菜单看起来"没内容"）。
--: 所以顺序改成"先找真正带中文字形的字体，找不到就用游戏字体 + 英文文案"（`T()` 按 `STATE.cjk`
--: 在中文/英文两套文案间切换，所以退到英文时菜单仍然可读）。
--: 顺带修掉一个大小写错误：游戏里是 `teammeatfont12.fnt`（全小写），原写法 `TeamMeatFont12.fnt`
--: 在大小写敏感的 romfs 上根本找不到。
local FONT_CANDIDATES = {
  --: ① 本模组自己的中文字体（占位：以后把字体拷进 q4-items 的 resources 就会先命中）
  { path = "rom:/isaac_mods/mods/q4-items/resources/font/q4_cn.fnt", cjk = true },
  --: ② EID 自带的中文字体（卡上有 EID 就能用；EID 自己也是这么加载它的）
  { path = "rom:/isaac_mods/mods/external item descriptions_836319872/resources/font/eid_cn_default.fnt",
    cjk = true },
  --: ③ 退路：游戏自带字体（只有 ASCII ⇒ 用英文文案，不会"什么都不显示"）
  { path = "font/teammeatfont12.fnt", cjk = false },
  { path = "font/droid.fnt", cjk = false },
  { path = "font/terminus.fnt", cjk = false },
}

local function EnsureFont()
  if STATE.font ~= nil or STATE.fontFailed then
    return STATE.font
  end
  local ok, font, cjk = pcall(function()
    for _, candidate in ipairs(FONT_CANDIDATES) do
      local created = Font()
      if created:Load(candidate.path) then
        return created, candidate.cjk
      end
    end
    return nil, false
  end)
  if not ok or font == nil then
    STATE.fontFailed = true
    Report(3)
    return nil
  end
  STATE.font = font
  STATE.cjk = cjk == true
  Report(2)
  return font
end

-- 描边靠"先画一遍黑的、再画白的"：不需要任何矩形绘制能力也能在任何背景上看清文字。
local function DrawText(font, text, x, y, scale, color)
  font:DrawStringScaledUTF8(text, x + 1, y + 1, scale, scale, COLOR_SHADOW, 0, false)
  font:DrawStringScaledUTF8(text, x, y, scale, scale, color, 0, false)
end

-- 按键读取统一走这里，**用"按住"而不是"刚按下"**。
--
-- 为什么不用 `Input.IsActionTriggered`（2026-09-16 真机结论）：那个"刚按下"标志在我们回调跑的
-- 时机里**已经抓不到** —— 实测 0~27 号动作 × controller 0/1 全问一遍、玩家按遍所有键，
-- "刚按下"位图全空，而同一批按键在"按住"位图上正常出现（`-` = 动作 13）。
-- 因此菜单**自己记上一帧的按住状态**做过沿判断，导航键再加一个重复延迟。
--: 按键查询要传的 controller 值。**真机结论（2026-09-16）**：
--: 引擎认的是**玩家自己的那个值**（EID 用 `EID.bagPlayer.ControllerIndex`，实测那次是 **33**），
--: 而猜的 0/1 一律答"没按下"。这里改成"**自学习 + 更全的候选**"：
--:   * 候选里最先放**上一次成功过的值**（学到就不再靠猜）；
--:   * 再放玩家自己的 `ControllerIndex`；
--:   * 再放游戏自己菜单代码里用的 `0xffffffff`（= 任意手柄，见 `Menu_*::Update` 的调用点）；
--:   * 最后放 0..3 与 32..35 兜底。
--: 任何一个候选答"是"就把那个值记下来，后面的帧优先问它。
local FALLBACK_CONTROLLERS = { 0, 1, 2, 3, 32, 33, 34, 35, 0xffffffff }

local function PlayerControllers()
  local controllers = {}
  if STATE.learnedController ~= nil then
    table.insert(controllers, STATE.learnedController)
  end
  if Isaac ~= nil and Isaac.GetPlayer ~= nil then
    local ok, player = pcall(function() return Isaac.GetPlayer(0) end)
    if ok and player ~= nil and player.ControllerIndex ~= nil then
      local index = player.ControllerIndex
      if type(index) == "number" then
        table.insert(controllers, index)
        Report(14)          -- 14 = 拿到了玩家自己的 controller 值
      end
    end
  end
  for _, fallback in ipairs(FALLBACK_CONTROLLERS) do
    table.insert(controllers, fallback)
  end
  return controllers
end

local function Held(code)
  if Input == nil or Input.IsActionPressed == nil then
    Report(12)          -- 12 = `Input.IsActionPressed` 根本不在（绑定/注册问题）
    return false
  end
  if ButtonAction == nil then
    Report(11)          -- 11 = 枚举表缺失，用的数字兜底
  end
  for _, controller in ipairs(PlayerControllers()) do
    local ok, down = pcall(function()
      return Input.IsActionPressed(code, controller)
    end)
    if ok and down == true then
      if STATE.learnedController ~= controller then
        STATE.learnedController = controller   -- 学到：以后优先问它
        Report(13)
      end
      return true
    end
  end
  return false
end

--: 过沿判断：`code` 从"没按住"变成"按住"的那一帧返回 true。
local function PressedOnce(code)
  local now = Held(code)
  local was = STATE.held[code] == true
  STATE.held[code] = now
  if now then
    Report(10 + (code % 16))   -- 记下"哪个动作号被看到按住"（位 10..25 里对应 code%16）
  end
  local fired = now and not was
  if fired then
    Report(8)                  -- 8 = 至少有一个动作号完成了"过沿"判定
  end
  return fired
end

local function AnyPressedOnce(codes)
  local fired = false
  for _, code in ipairs(codes) do
    if PressedOnce(code) then
      fired = true
    end
  end
  return fired
end

local function Draw()
  if not STATE.open then
    return
  end
  local font = EnsureFont()
  if font == nil then
    return
  end

  local scale = 0.55
  local x = 24.0
  local line = 22.0
  local y = 24.0
  DrawText(font, T("title"), x, y, scale, COLOR_TEXT)
  y = y + line

  if #STATE.items == 0 then
    DrawText(font, T("none"), x, y, scale, COLOR_DIM)
    y = y + line
  end

  for index, item in ipairs(STATE.items) do
    local marker = (index == STATE.selected) and "> " or "  "
    local box = item.Enabled and "[x] " or "[ ] "
    local color = item.Enabled and COLOR_ON or COLOR_OFF
    local suffix = ""
    if item.Enabled ~= item.Active then
      -- 开关与"这次真的加载了没有"不一致 ⇒ 要重启才生效
      suffix = T("restart")
      color = COLOR_WARN
    end
    DrawText(font, marker .. box .. item.Directory .. suffix, x, y, scale, color)
    y = y + line
  end

  y = y + line * 0.4
  if STATE.dirty then
    DrawText(font, T("dirty"), x, y, scale, COLOR_WARN)
    y = y + line
  end
  if STATE.messageFrames > 0 then
    DrawText(font, STATE.message, x, y, scale, COLOR_DIM)
    y = y + line
  end
  DrawText(font, T("hint"), x, y, scale, COLOR_DIM)
  y = y + line
  -- 排障用的一行：把"呼出键相关的几个动作号现在是不是按下的"直接画出来。
  -- 键位对不上时，玩家照着这一行按一遍就能告诉我们哪个号在动（不需要读调试桩）。
  local keys = {}
  for _, code in ipairs({ 13, 26, 12, 22, 23, 14, 15 }) do
    table.insert(keys, code .. (Held(code) and "=1" or "=0"))
  end
  DrawText(font, table.concat(keys, " "), x, y, scale, COLOR_DIM)
end

local function SaveIfDirty()
  if not STATE.dirty then
    return
  end
  local ok, saved = pcall(function()
    return RuntimeMods and RuntimeMods.Save and RuntimeMods.Save()
  end)
  if ok and saved then
    STATE.dirty = false
    Report(7)
    Say(T("saved"))
  else
    Say(T("failed"))
  end
end

local function Toggle()
  local item = STATE.items[STATE.selected]
  if item == nil then
    return
  end
  local wanted = not item.Enabled
  local ok, changed = pcall(function()
    return RuntimeMods and RuntimeMods.SetEnabled and
           RuntimeMods.SetEnabled(item.Directory, wanted)
  end)
  if ok and changed then
    item.Enabled = wanted
    STATE.dirty = true
    Report(6)
    Say(item.Directory .. ": " .. (wanted and T("on") or T("off")))
  else
    Say(T("notoggle"))
  end
end

-- 读键统一走这里：任何一次原生绑定不可用都只是"菜单不动"，不让回调报错
-- （回调一旦抛错，派发器会把这个回调摘掉 —— 菜单就再也不会响应了）。
-- 键位普查（只为排障）：每 10 帧把 0~27 号动作在**两个 controller 序号**上各问一遍，
-- 两种语义都问（"刚按下"与"按住"），结果由 C++ 侧的输入探针分位图记录 —— 真机上
-- "我按了某个键但菜单没反应"就能一次读数定位到"哪个动作号 + 哪个 controller + 哪种语义"。
local function ScanInputs()
  for controller = 0, 1 do
    for code = 0, 27 do
      if Input.IsActionTriggered ~= nil then
        pcall(Input.IsActionTriggered, code, controller)
      end
      if Input.IsActionPressed ~= nil then
        pcall(Input.IsActionPressed, code, controller)
      end
    end
  end
end

-- ===== 诊断伴生采样（批次 070，2026-09-19）===================================
--
-- 为什么要有它：问"第三方模组**内部**现在是什么状态"（例如 GoodTrip 的 `gt.floor.crd`
-- 是不是 nil、它的配置项取值多少）此前只能**改那个模组的脚本**再装一次卡 ——
-- 一次要用户"退游戏 → 开 FTP → 装 → 关 FTP → 开游戏"，十几分钟，而且一个问题一轮。
--
-- 现在改成：由**我们自己的**菜单模组（本来就第一个加载、不占模组位、不改任何第三方文件）
-- 定期把几个已知全局浅表扫一遍，写进**它自己的模组数据**；读数工具本来就会解模组数据
-- （`tools/read_device_state_via_gdb.py` 的模组数据解码），于是"模组内部状态"变成
-- **一条读数命令**，不用再为每个新问题装一次东西。
--
-- 边界（诚实说明，别指望它全免）：
--   * 只看**全局**（模组自己挂出来的入口，如 `gt`、`EID`）；模组内部的局部变量看不到；
--   * 深度 2 层、一次最多 40 行 —— 这段代码在每帧都跑的更新回调里，不能把大表整棵扫完；
--   * 全程 `pcall`：采样自己出任何问题都不许影响菜单与模组加载。
local DIAG = { countdown = 120, last = "" }

local function DiagScalar(value)
  local kind = type(value)
  if kind == "string" then
    return string.format("%q", string.sub(value, 1, 64))
  end
  if kind == "number" or kind == "boolean" or kind == "nil" then
    return tostring(value)
  end
  return "<" .. kind .. ">"
end

local function DiagTable(prefix, value, depth, out, budget)
  for key, item in pairs(value) do
    if budget[1] <= 0 then
      return
    end
    budget[1] = budget[1] - 1
    local name = prefix .. "." .. tostring(key)
    if type(item) == "table" then
      out[#out + 1] = name .. "=<table>"
      if depth > 1 then
        DiagTable(name, item, depth - 1, out, budget)
      end
    else
      out[#out + 1] = name .. "=" .. DiagScalar(item)
    end
  end
end

local function DiagCollect()
  local out = {}
  local budget = { 40 }
  local globals = _G
  for _, name in ipairs({ "gt", "EID" }) do
    local value = (globals ~= nil) and globals[name] or nil
    if value == nil then
      out[#out + 1] = name .. "=<missing>"
    elseif type(value) == "table" then
      out[#out + 1] = name .. "=<table>"
      DiagTable(name, value, 2, out, budget)
    else
      out[#out + 1] = name .. "=" .. DiagScalar(value)
    end
  end
  -- 引擎侧概要：与模组内部状态一起看，才能分清"模组的判断"与"引擎的事实"。
  local function probe(name, fn)
    local ok, value = pcall(fn)
    if ok then
      out[#out + 1] = name .. "=" .. DiagScalar(value)
    else
      out[#out + 1] = name .. "=<error>"
    end
  end
  probe("engine.frame", function() return Game():GetFrameCount() end)
  probe("engine.roomType", function() return Game():GetRoom():GetType() end)
  probe("engine.greedMode", function() return Game():IsGreedMode() end)
  return table.concat(out, "\n")
end

local function DiagSample()
  local ok, text = pcall(DiagCollect)
  if not ok or type(text) ~= "string" or text == "" or text == DIAG.last then
    return
  end
  DIAG.last = text
  pcall(function()
    if mod.SaveData ~= nil then
      mod:SaveData("DIAGSAMPLE\n" .. text)
    end
  end)
end

local function OnUpdate()
  Report(5)
  -- 采样先于菜单的早退分支：菜单开着还是关着都要采（真机上的问题多半在游玩过程中）。
  DIAG.countdown = DIAG.countdown - 1
  if DIAG.countdown <= 0 then
    DIAG.countdown = 300
    DiagSample()
  end
  if (STATE.scanFrames or 0) <= 0 then
    STATE.scanFrames = 10
    ScanInputs()
  else
    STATE.scanFrames = STATE.scanFrames - 1
  end
  -- 呼出：**组合键**（见 KEY 表的说明）。两个方向都认：先按 `+` 再按 `-`、或先按 `-` 再按 `+`，
  -- 只要在另一键**按住**期间出现另一键的过沿就算。这样不抢地图键、也不抢暂停键。
  local openChord = (Held(KEY.open_modifier) and PressedOnce(KEY.open))
      or (Held(KEY.open) and PressedOnce(KEY.open_modifier))
  if openChord then
    Report(9)                -- 9 = 呼出键的过沿判定成立（菜单即将打开）
    if STATE.open then
      STATE.open = false
      SaveIfDirty()
    else
      Refresh()
      STATE.selected = 1
      STATE.open = true
      Report(4)
      if #STATE.items == 0 then
        Say(T("none"))
      end
    end
    return
  end

  if not STATE.open then
    return
  end

  if AnyPressedOnce({ KEY.up, KEY.up_alt }) then
    STATE.selected = STATE.selected - 1
    if STATE.selected < 1 then
      STATE.selected = math.max(1, #STATE.items)
    end
  end
  if AnyPressedOnce({ KEY.down, KEY.down_alt }) then
    STATE.selected = STATE.selected + 1
    if STATE.selected > #STATE.items then
      STATE.selected = 1
    end
  end
  if AnyPressedOnce({ KEY.confirm, KEY.confirm_alt }) then
    Toggle()
  end
  if AnyPressedOnce({ KEY.back, KEY.back_alt }) then
    STATE.open = false
    SaveIfDirty()
  end
end

local function OnRender()
  STATE.messageFrames = math.max(0, STATE.messageFrames - 1)
  local ok = pcall(Draw)
  if not ok then
    STATE.open = false
    Say(T("error"))
  end
end

mod:AddCallback(MC.MC_POST_UPDATE, OnUpdate)
mod:AddCallback(MC.MC_POST_RENDER, OnRender)
)LUA";

//: 脚本字节数（由编译期常量算出来，避免"改了脚本忘了改长度"）。
inline constexpr std::size_t kEmbeddedModMenuScriptLength = kEmbeddedModMenuScript.size();

} // namespace isaac::runtime
