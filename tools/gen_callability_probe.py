#!/usr/bin/env python3
"""从**绑定表 + 接口目录**生成"可调用性探针"：在真机上逐条检查"模组到底调不调得到这个成员"。

## 为什么需要它（2026-09-18 的教训）

一夜之间修了三条"**成员在、模组却调不到**"的错，成因各不相同：

* 方法被登记进了**别的 owner 的绑定表**（`EntityPickup:CanReroll` 挂到了 `EntityPlayer` 元表上）；
* 查询结果发给模组的**实体视图太窄**（掉落物拿到基类 `Entity` 视图 ⇒ `EntityPickup` 的方法全是 nil）；
* 名字/绑定本身没问题，但**参数判据比 PC 严**（那条由另一条门禁管）。

这三类的共同点是：**"我们写了" ≠ "模组能调到"**。而此前的检查（接口目录、安全桩台账、偏移签名）
量的都是"实现面"——没有一条量"模组手里的那个对象上有没有它"。

## 它怎么生成

1. 从 `api_catalog.cpp` 取 `id → (owner, 成员名)`；
2. 从各 `*_handlers[]` 表取 `id → 处理器`（**登记在表里 = 会被挂到元表上**）；
3. 按 owner 汇总成员清单，并为每个 owner 给一个"**造一个该类型真实对象**"的 Lua 表达式；
4. 生成一支探针：对每个 `(owner, 成员)` 检查 `type(obj[成员]) == 'function'`，
   把**调不到的**列出来（屏幕上显示条数，并把清单**抛进运行时的错误通道**——那是设备侧唯一能读回的文本通道）。

⚠️ 只检查"有没有这个函数"，**不真的调用**：真调会有副作用（`AddCoins` 真的会给钱、`SetFrame` 会动动画）。

## 用法

    python3 tools/gen_callability_probe.py                 # 写到 dist/callability-probe-<日期>/main.lua
    python3 tools/gen_callability_probe.py --print         # 只打印，不落盘

生成结果里会明确列出**覆盖不到的 owner**（我们没有"造一个这种对象"的表达式）——那是诚实的覆盖率记账。
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LUA_API = ROOT / "runtime" / "src" / "interfaces" / "lua"
CATALOG = LUA_API / "api_catalog.cpp"

#: 每个 owner 怎么"造一个真实对象"。取不到的写成 None（会被记进"覆盖不到"清单）。
#: 表达式一律用**探针自己在局内能拿到的东西**（`Isaac.GetPlayer(0)` / `Game()` / 查询结果…）。
OWNER_EXPRESSIONS = {
    "Isaac": "Isaac",
    "Global": "_G",                      # 全局函数：直接在 `_G` 上找
    "os": "os",
    "debug": "debug",
    "Options": "Options",
    "RuntimeMods": "RuntimeMods",
    "Input": "Input",
    "Mod": "mod",                        # 探针自己的 Mod 对象
    "EntityPlayer": "Isaac.GetPlayer(0)",
    "Entity": "(Isaac.FindByType(20)[1] or Isaac.FindByType(5)[1] or Isaac.GetPlayer(0))",
    "EntityPickup": "Isaac.FindByType(5)[1]",
    "Sprite": "(Isaac.GetPlayer(0) ~= nil) and Isaac.GetPlayer(0):GetSprite() or nil",
    "Level": "Game() ~= nil and Game():GetLevel() or nil",
    "Room": "Game() ~= nil and Game():GetRoom() or nil",
    "Game": "Game()",
    "ItemPool": "Game() ~= nil and Game():GetItemPool() or nil",
    "ItemConfig": "Isaac.GetItemConfig()",
    "ItemConfig_Item": "(Isaac.GetItemConfig() ~= nil) and Isaac.GetItemConfig():GetCollectible(1) or nil",
    "RNG": "(Isaac.GetPlayer(0) ~= nil) and Isaac.GetPlayer(0):GetCollectibleRNG(1) or nil",
    "Seeds": "Game() ~= nil and Game():GetSeeds() or nil",
    "MusicManager": "MusicManager()",
    "Font": "Font()",
    "Vector": "Vector(1, 1)",
    "GridEntity": "(Game() ~= nil and Game():GetRoom() ~= nil) and Game():GetRoom():GetGridEntity(0) or nil",
}

ROW = re.compile(
    r'\{MakeId\(ApiDomain::(\w+), 1, (0x[0-9A-Fa-f]+)\),\s*ApiDomain::\w+,\s*"(\w+)",\s*"(\w+)"')
BINDING = re.compile(r'\{(0x[0-9A-Fa-f]+),\s*&(\w+)\}')

#: `ApiDomain` 的数值（`api_descriptor.hpp` 的枚举顺序）。绑定表的 key 高字节就是它
#: （目录里的 `MakeId(domain, 1, 小号)` 与之逐位对应），所以两侧靠"（域号, 小号）"对齐。
DOMAIN_VALUES = {
    "Global": 0, "Mod": 1, "Game": 2, "Level": 3, "Room": 4, "ItemPool": 5, "Music": 6,
    "Rng": 7, "Persistence": 8, "Input": 9, "Diagnostic": 10, "Font": 11, "Vector": 12,
    "Sprite": 13, "Isaac": 14, "Seed": 15, "ModMenu": 16,
}


def catalog_rows() -> dict[tuple[int, int], tuple[str, str]]:
    """（域号, 小号）→ (owner, 成员名)。"""
    text = CATALOG.read_text(encoding="utf-8")
    rows: dict[tuple[int, int], tuple[str, str]] = {}
    for domain, identifier, owner, member in ROW.findall(text):
        rows[(DOMAIN_VALUES[domain], int(identifier, 16))] = (owner, member)
    return rows


def binding_rows() -> tuple[dict[int, str], list[str]]:
    """所有 `*_handlers[]` 表里的 `id → 处理器`，外加"目录里没有这条 id"的异常清单。"""
    bindings: dict[int, str] = {}
    for path in sorted(LUA_API.glob("*.cpp")):
        text = path.read_text(encoding="utf-8")
        for table in re.finditer(r"constexpr LuaHandlerBinding (\w+)\[\] = \{(.*?)\n\};", text,
                                 re.S):
            for identifier, handler in BINDING.findall(table.group(2)):
                bindings[int(identifier, 16)] = handler
    return bindings, []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成'可调用性探针'")
    parser.add_argument("--print", dest="print_only", action="store_true")
    parser.add_argument("--date", default=datetime.date.today().strftime("%Y%m%d"))
    args = parser.parse_args(argv)

    rows = catalog_rows()
    bindings, _ = binding_rows()

    # owner → [成员名]，按绑定表来（表里的成员**必须**是函数）
    by_owner: dict[str, list[str]] = {}
    unknown_ids: list[str] = []
    for identifier, handler in sorted(bindings.items()):
        row = rows.get(((identifier >> 24) & 0xFF, identifier & 0xFFFF))
        if row is None:
            unknown_ids.append(f"0x{identifier:08X} ({handler})")
            continue
        owner, member = row
        by_owner.setdefault(owner, []).append(member)

    covered = {owner: members for owner, members in by_owner.items() if OWNER_EXPRESSIONS.get(owner)}
    uncovered = {owner: members for owner, members in by_owner.items()
                 if not OWNER_EXPRESSIONS.get(owner)}

    lines: list[str] = []
    lines.append("-- 本文件由 `tools/gen_callability_probe.py` 自动生成，**请勿手改**。")
    lines.append("--")
    lines.append("-- 它逐条检查：**模组手里的那个对象上，到底有没有目录里登记的这个成员**。")
    lines.append("-- 只检查存在性、不真的调用（真调会有副作用）。")
    lines.append("-- ⚠️ 清单取自**我们自己的绑定表**（`*_handlers[]`）⇒ 它查的是"
                 "「登记了、但对象上取不到」（2026-09-18 的 `EntityPickup:CanReroll` 就是这一类），"
                 "**不是**「目录里有、我们没实现」——后者是静态账本（目录 vs 绑定表）的活。")
    lines.append("--")
    lines.append("--")
    lines.append("-- ── 两阶段测量 ──")
    lines.append("--   A-early（第 30 帧）：**标题画面就能下结论**的一半 —— 全局对象/字体/绘制通道在不在；")
    lines.append("--   B-in-game（玩家与房间都在时）：量实体、房间、道具池那一族；A 的结果一并带在报告里。")
    lines.append("--   为什么分两段：在标题画面量实体族只会得到一堆 `nil`，那种报告没有信息量。")
    lines.append("--")
    lines.append("-- ── 四条回报通道（v2；v1 只用了屏幕+错误，真机上什么都没看到，"
                 "分不清是哪一步没跑）──")
    lines.append("--   ① 屏幕：**第 1 帧起每帧重画**一行 `alive`（v1 只画一帧，"
                 "16 毫秒就没了 —— 这是 v1 看不到东西的直接原因）；")
    lines.append("--   ② 自己的模组存档（`Mod:SaveData`）：脚本一加载就写 `LOADED` 标记，"
                 "测完写完整清单；")
    lines.append("--      设备侧可从内存读回（`g_ModDataCache` 的记录表，见 `tools/read_probe_report.py`），"
                 "**完全不依赖画面**；")
    lines.append("--   ③ Lua 错误通道：一次性 `error(摘要)` ⇒ 进'最后一次 Lua 错误'并置位'回调出错'；")
    lines.append("--   ④ 实测一次 `Isaac.RenderScaledText`（我们新写的默认字体绘制），"
                 "结果画在屏幕上（`RST ok` / `RST err:...`）。")
    lines.append("--")
    lines.append(f"-- 覆盖 owner {len(covered)} 个 / 成员 {sum(len(v) for v in covered.values())} 条；")
    if uncovered:
        lines.append("-- ⚠️ **覆盖不到**的 owner（我们没有'造一个这种对象'的表达式）：")
        for owner, members in sorted(uncovered.items()):
            lines.append(f"--     {owner}（{len(members)} 条）：{', '.join(sorted(members)[:6])}")
    lines.append("")
    lines.append("local mod = RegisterMod('CallabilityProbe', 1)")
    lines.append("")
    lines.append("local OWNERS = {")
    for owner in sorted(covered):
        members = ", ".join(f"'{member}'" for member in sorted(covered[owner]))
        lines.append(f"  {{ owner = '{owner}',")
        lines.append(f"    members = {{ {members} }} }},")
    lines.append("}")
    lines.append("")
    lines.append("-- 对象解析：**直接在本 chunk 里内联求值**。")
    lines.append("--")
    lines.append("-- 为什么不用 `load('return ' .. 表达式)()`（v2 的写法，真机上翻车）：那一版 20 个")
    lines.append("-- owner **全部** skipped —— 连 `mod`（模组自己的句柄）与 `Font()` 都拿不到，")
    lines.append("-- 而同一份脚本里直接 `Font()` 装字体是成功的 ⇒ 问题出在 `load` 编出来的 chunk")
    lines.append("-- 取不到我们的全局（另一个可能：`load` 本身不可用）。下面把 `type(load)` 一起报上来，")
    lines.append("-- 两种情况一次就能分辨。")
    lines.append("local function resolveObjects()")
    lines.append("  local objects = {}")
    lines.append("  local reasons = {}")
    lines.append("  local function take(owner, fn)")
    lines.append("    local ok, value = pcall(fn)")
    lines.append("    if not ok then")
    lines.append("      reasons[owner] = 'call-error: ' .. tostring(value)")
    lines.append("    elseif value == nil then")
    lines.append("      reasons[owner] = 'nil（对象当时不存在，例如还没进局）'")
    lines.append("    else")
    lines.append("      objects[owner] = value")
    lines.append("    end")
    lines.append("  end")
    for owner in sorted(covered):
        lines.append(f"  take('{owner}', function() return {OWNER_EXPRESSIONS[owner]} end)")
    lines.append("  return objects, reasons")
    lines.append("end")
    lines.append("")
    lines.append(r'''
-- ── 通道②：自己的模组存档（设备侧可读，不依赖画面）──────────────────────────
-- `Mod:SaveData(string)` 写进**本模组自己的命名空间**（不会动 EID 的数据）；写入失败不抛错，
-- 只把原因记下来，免得"存档失败"把整个探针带崩（那样就什么都查不到了）。
local saveError = nil
local function saveReport(text)
  local ok, err = pcall(function() mod:SaveData(text) end)
  if not ok then saveError = tostring(err) end
end

-- ── 通道①：屏幕。**自己装一份字体**（`Font()` + `Load()` 返回布尔），
-- 这条路径 EID 与 q4-items 已在真机上验证过画得出字，不依赖 `Isaac.RenderScaledText`。
local FONT_CANDIDATES = { 'font/droid.fnt', 'font/teammeatfont12.fnt', 'font/terminus.fnt' }
local font = nil
local fontPath = nil
for _, path in ipairs(FONT_CANDIDATES) do
  local okCtor, created = pcall(Font)
  if okCtor and created ~= nil then
    local okLoad, loaded = pcall(function() return created:Load(path) end)
    if okLoad and loaded == true then
      font = created
      fontPath = path
      break
    end
  end
end

local WHITE = Color(1, 1, 1, 1)
local SHADOW = Color(0, 0, 0, 0.85)

--: 优先用自己装的字体；装不上就退回 `Isaac.RenderScaledText`（两条都试过才算"画不出来"）。
local function draw(text, y)
  if font ~= nil then
    pcall(function()
      font:DrawStringScaledUTF8(text, 11, y + 1, 1.0, 1.0, SHADOW, 0, false)
      font:DrawStringScaledUTF8(text, 10, y, 1.0, 1.0, WHITE, 0, false)
    end)
    return
  end
  pcall(function() Isaac.RenderScaledText(text, 10, y, 1.0, 1.0, 1, 1, 1, 1) end)
end

--: 通道②第一笔：**脚本一加载就留痕**。哪怕回调一次都没派发，设备侧也能读到这一行 ⇒ 
--: "脚本没加载"与"脚本跑了但回调没派发"从此分得开（v1 分不开，白跑一轮）。
local LOAD_MARKER = 'CALLPROBE v2 LOADED font=' .. tostring(fontPath or 'none') ..
                   ' scaledText=' .. type(Isaac.RenderScaledText)
saveReport(LOAD_MARKER)

local state = { frames = 0, stage = 0, lines = {}, history = {}, tried = {} }

--: "进到局内了吗"：房间与玩家都在，才量得动实体/房间那一族 owner。
local function inGame()
  local ok, value = pcall(function()
    return Game() ~= nil and Game():GetRoom() ~= nil and Isaac.GetPlayer(0) ~= nil
  end)
  return ok and value == true
end

--: 房间里有没有拾取物（`EntityPickup` 那一族 owner 要靠它才量得动；商店/宝箱房通常有）。
local function hasPickup()
  local ok, value = pcall(function() return Isaac.FindByType(5)[1] end)
  return ok and value ~= nil
end

local function measure()
  local missing = {}
  local skipped = {}
  local objects, reasons = resolveObjects()
  for _, entry in ipairs(OWNERS) do
    local object = objects[entry.owner]
    if object == nil then
      table.insert(skipped, entry.owner .. '(' .. tostring(reasons[entry.owner] or '?') .. ')')
    else
      for _, member in ipairs(entry.members) do
        local hasIt, value = pcall(function() return object[member] end)
        if not hasIt or type(value) ~= 'function' then
          -- 取不到和"取到了但不是函数"是两件事，报告里分开写（PC 上成员也可能是数据字段）。
          table.insert(missing, entry.owner .. '.' .. member ..
                       (hasIt and '' or '(read-error)'))
        end
      end
    end
  end
  -- 全局对象本身在不在：与 owner 清单合起来看，才知道"是环境缺东西"还是"当时没进局"。
  local globals = 'load=' .. type(load) .. ' loadstring=' .. type(loadstring) ..
                  ' Isaac=' .. type(Isaac) .. ' Input=' .. type(Input) ..
                  ' Vector=' .. type(Vector) .. ' Font=' .. type(Font) .. ' Game=' .. type(Game)
  return missing, skipped, globals
end

--: 实测一次 `Isaac.RenderScaledText`（我们自己写的"默认字体"绘制）。
--:
--: ★ 用**纯 ASCII**串：游戏自带字体没有中文字形，上一版拿中文串测 ⇒ "看不到"根本不能作为反证
--: （v3 报告里 `RenderScaledText=ok` 就是这个坑）。现在：
--:   * 我们自己的字体在 y=200 画一行 `own-font line (ASCII)`（对照组，已知能显示）；
--:   * `Isaac.RenderScaledText` 在同一条竖线的 y=220 画 `RST line (ASCII) 2+2=4`。
--: 两条都在 ⇒ 这条 API 画得出来；只有上一条 ⇒ 它没画出来（要查明原因）。
--: 这两行**每帧都画**（`check()` 里无条件调用）。
--:
--: ★ 教训（同一天犯了两次）：第一版只画一次 ⇒ 屏幕上只闪一帧、人根本看不到，
--: 于是"看不到"被误读成"画不出来"。**诊断用的文字必须每帧重画**，而且不依赖测量时机
--: （下面从第 1 帧就开始画，不进任何"阶段"分支）。
local RST_LINE = 'RST y=300 x=400 (ASCII) if you see this, RenderScaledText works'
--: 坐标标定：**每一行都写上自己的 y**，让"哪一行在屏幕哪个位置"一次目视就能记下来
--: （2026-09-18 的未决问题：代码给 y=200/220，用户看到在偏下方；而 q4-items 用 y=500 能看见、
--: 注释说 654 看不见 —— 三个观察凑不出一个模型）。
local CALIBRATION_Y = { 10, 100, 200, 300, 400, 500, 600, 700 }
local lastRenderTextError = nil

local function drawRenderProbeLines()
  if font ~= nil then
    for _, y in ipairs(CALIBRATION_Y) do
      draw('Y=' .. tostring(y) .. ' x=10 (own font)', y)
    end
  end
  if type(Isaac.RenderScaledText) == 'function' then
    local ok, err = pcall(function()
      Isaac.RenderScaledText(RST_LINE, 400, 300, 1.0, 1.0, 1, 1, 1, 1)
    end)
    if not ok then
      lastRenderTextError = tostring(err)
    end
  end
end

--: 只做一次"结果"判定（错误消息要进报告）；画那一份由上面的每帧函数负责。
local function probeRenderScaledText()
  if type(Isaac.RenderScaledText) ~= 'function' then
    return 'not-a-function'
  end
  local ok, err = pcall(function()
    Isaac.RenderScaledText(RST_LINE, 10, 220, 1.0, 1.0, 1, 1, 1, 1)
  end)
  if not ok then
    lastRenderTextError = tostring(err)
    return 'err:' .. tostring(err)
  end
  return lastRenderTextError == nil and 'ok' or ('ok(但每帧绘制时报错: ' .. lastRenderTextError .. ')')
end

--: 量一轮并写进模组存档；返回摘要行（错误通道与屏幕都用它）。
local function runStage(tag)
  local missing, skipped, globals = measure()
  local summary = 'CALLPROBE-' .. tag .. ' miss=' .. tostring(#missing) ..
                  ' skipped=' .. tostring(#skipped)
  local renderTextResult = probeRenderScaledText()

  local text = summary .. '\nfont=' .. tostring(fontPath or 'none') ..
               '\nframes=' .. tostring(state.frames) .. ' inGame=' .. tostring(inGame()) ..
               '\n' .. globals ..
               '\nRenderScaledText=' .. renderTextResult .. '\n'
  for index, name in ipairs(missing) do
    if index > 200 then
      text = text .. '...(' .. tostring(#missing - 200) .. ' more)\n'
      break
    end
    text = text .. name .. '\n'
  end
  if #skipped > 0 then
    text = text .. 'SKIPPED\n'
    for index, name in ipairs(skipped) do
      if index > 24 then
        text = text .. '...\n'
        break
      end
      text = text .. '  ' .. name .. '\n'
    end
  end
  if saveError ~= nil then
    text = text .. 'SAVE-ERROR ' .. saveError .. '\n'
  end

  state.lines = { summary }
  for index, name in ipairs(missing) do
    if index > 10 then
      state.lines[#state.lines + 1] = '... 共 ' .. tostring(#missing) .. ' 条（完整清单见模组存档）'
      break
    end
    state.lines[#state.lines + 1] = name
  end
  if #skipped > 0 then
    state.lines[#state.lines + 1] = 'skipped ' .. tostring(#skipped) .. '（原因见模组存档）'
  end
  state.lines[#state.lines + 1] = 'RenderScaledText: ' .. renderTextResult
  -- 每一轮都留在同一份报告里（存档只有一份值）：后一轮的存档包含前面所有轮。
  table.insert(state.history, text)
  saveReport(table.concat(state.history, '\n=== 上一轮 ===\n'))
  return summary
end

local function check()
  state.frames = state.frames + 1
  if state.frames == 1 then
    -- 再写一次加载标记：脚本加载那一刻文件能力可能还没就绪（那时写失败只会被 pcall 吞掉），
    -- 而第 1 帧绘制回调里一定是就绪的 ⇒ 写两次，"两处都失败"才算真的写不进去。
    saveReport(LOAD_MARKER)
  end
  if state.stage == 0 and state.frames >= 30 then
    -- A 阶段：第 30 帧的现场（`frames`/`inGame` 都记在报告里 —— 标题画面那次
    -- "屏幕上一个字都没有"是不是因为那时还没派发，靠这两个读数就能分辨）。
    state.stage = 1
    error(runStage('A-early'))   -- ③ 一次性报错（错误文本就是摘要）
  end
  if state.stage == 1 and inGame() then
    -- B 阶段：进到局内才量得动实体/房间/道具池那一族。
    state.stage = 2
    error(runStage('B-in-game'))
  elseif state.stage == 1 and state.frames >= 3600 then
    -- 约 60 秒还没进局（用户在标题画面停着）：如实记下来，别让人以为"跑完了"。
    state.stage = 2
    saveReport('CALLPROBE-B TIMEOUT：60 秒内没进到局内，只有 A-early 的结果\n' ..
               table.concat(state.history, '\n=== 上一轮 ===\n'))
    state.lines[#state.lines + 1] = 'B TIMEOUT：60 秒内没进局'
  end
  if state.stage == 2 and not state.tried.pickup and hasPickup() then
    -- C 阶段：房间里**真的出现拾取物**时再量一次 —— `EntityPickup` 那一族只有这时才量得动
    -- （上一轮 `EntityPickup(nil…)` 就是"那间屋子地上什么都没有"，不是缺口）。
    state.tried.pickup = true
    state.stage = 3
    error(runStage('C-pickup'))
  end
  -- ① 每帧重画：v1 只在测量那一帧画一次 ⇒ 屏幕上几乎不可能看到。
  draw('CALLPROBE alive f=' .. tostring(state.frames) .. ' font=' .. tostring(fontPath or 'none'),
       30)
  -- ⑤ 候选两行（自己字体 vs `Isaac.RenderScaledText`）**每帧**都画，且与阶段无关。
  drawRenderProbeLines()
  for index, text in ipairs(state.lines) do
    draw(text, 52 + (index - 1) * 16)
  end
end

mod:AddCallback(ModCallbacks.MC_POST_RENDER, check)
''')

    text = "\n".join(lines) + "\n"
    if args.print_only:
        print(text)
        return 0

    target = ROOT / "dist" / f"callability-probe-{args.date}" / "main.lua"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(f"已写入 {target.relative_to(ROOT)}")
    print(f"覆盖 owner {len(covered)} 个、成员 {sum(len(v) for v in covered.values())} 条；"
          f"覆盖不到 {len(uncovered)} 个 owner（清单在文件头注释里）")
    if unknown_ids:
        print(f"⚠️ 绑定表里有 {len(unknown_ids)} 条 id 在目录里找不到（登记与目录不一致）：")
        for item in unknown_ids[:10]:
            print(f"    {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
