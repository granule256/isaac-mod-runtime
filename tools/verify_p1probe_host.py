#!/usr/bin/env python3
"""在宿主机上把 `dist/probe-p1probe-20261004/main.lua` 跑一遍（LuaJIT via lupa）。

为什么要它：探针是**要放到真机上跑的东西**，而真机一轮迭代（用户进游戏、找到房间、
看到屏幕、回传）很贵。宿主机这一遍能廉价地拦掉"探针自己抛错 / 输出为空 / 分支写反"
这三类问题 —— 尤其是"探针自己抛错"，那会让它既没读数、又把运行时搞成加载失败。

做法：给 `main.lua` 一副**替身环境**（`RegisterMod` / `ModCallbacks` / `Game()` / `Isaac`
/ `Color` / `Font`），喂几种场景，把 `Isaac.RenderScaledText` 的每一行抓下来核对。

用法：
    /Users/kelinls/.workbuddy/binaries/python/envs/default/bin/python tools/verify_p1probe_host.py
退出码 0 = 全部通过；1 = 有断言失败（打印失败项）。
"""

from __future__ import annotations

import pathlib
import sys

import lupa

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBE = ROOT / "dist" / "probe-p1probe-20261004" / "main.lua"

#: 替身环境。`P1LINES` 收屏幕输出，`P1CALLBACKS` 收注册的回调（键 = 回调号）。
PREAMBLE = r"""
P1LINES = {}
P1CALLBACKS = {}
P1FONT_FAILS = false

local mod_mt = {}
mod_mt.__index = mod_mt
function mod_mt.AddCallback(self, id, fn)
  P1CALLBACKS[id] = fn
end
function mod_mt.SaveData(self, data)
  P1SAVED.text = data
  P1SAVED.count = P1SAVED.count + 1
end
function mod_mt.LoadData(self) return P1SAVED.text end
function mod_mt.HasData(self) return P1SAVED.count > 0 end
function RegisterMod(name, id)
  return setmetatable({ name = name, id = id }, mod_mt)
end

ModCallbacks = { MC_POST_UPDATE = 1, MC_POST_RENDER = 2 }

Isaac = {}
function Isaac.RenderScaledText(text, x, y, sx, sy, r, g, b, a)
  P1LINES[#P1LINES + 1] = { text = text, x = x, y = y, r = r, g = g, b = b }
end

-- 替身：假的"别人登记的绘制回调"。默认给一个 GoodTrip 的（它**会报错**）+ 一个正常的，
-- 用来验证探针能不能"自己 pcall 别人的回调并抓住报错原文"。
P1OTHER_CALLBACKS = nil        -- nil = 用默认的两个
function Isaac.GetCallbacks(id)
  if id ~= 2 then return {} end
  if P1OTHER_CALLBACKS ~= nil then return P1OTHER_CALLBACKS end
  return {
    { Mod = { Name = "GoodTrip [Fixed]" }, Function = function(self)
        local bad = nil
        return bad.Type                       -- 故意炸：attempt to index a nil value
      end },
    { Mod = { Name = "q4-items" }, Function = function(self) return 1 end },
    { Mod = { Name = "p1probe" }, Function = function(self) return 1 end },
  }
end

function Color(r, g, b, a) return { r, g, b, a } end

-- 替身：Mod:SaveData（探针把打包文本交给它 —— 真机上这落进运行时的模组数据容器）
P1SAVED = { text = "", count = 0 }


-- ★ 替身：地图键（`-` / ButtonAction.ACTION_MAP = 13）与玩家
ButtonAction = { ACTION_MAP = 13 }
P1MAP_HELD = false
Input = {}
function Input.IsActionPressed(action, index)
  if action ~= 13 then return false end
  return P1MAP_HELD
end
function Isaac.GetPlayer(index)
  return { ControllerIndex = 0 }
end


function Font()
  if P1FONT_FAILS then error("no font") end
  return {
    Load = function(self, path) return path == "font/terminus.fnt" end,
    DrawStringScaledUTF8 = function(self, text, x, y, sx, sy, c, w, center)
      P1LINES[#P1LINES + 1] = { text = "FONT>" .. text, x = x, y = y }
    end,
  }
end

-- ★ 替身：`Sprite()` —— 批次 362 的 anm2 加载探针要用（真机上它调的是引擎自己的
-- `ANM2::Load` / `SetFrame` / `SetLastFrame` / `GetFrame`，这里只复刻可观察行为）。
-- 表里的数字 = **那条动画在那一份文件里的帧数**（本机数过 XML）：
--   `gfx/ui/minimap1.anm2` / `minimap2.anm2` 的 `RoomUnvisited`：本体 13 帧、模组 1 帧
--   （替身按"本体赢了"喂 13 ⇒ `SetLastFrame()` 之后 `GetFrame()` = 12）
--   `sprite/gt/gt_ui.anm2` 的 `select`：模组独有、14 帧（⇒ 13）
--   没列出来的路径（探针故意用的那条不存在的）= 1 帧（⇒ 0）
P1SPRITE_FRAMES = {
  ["gfx/ui/minimap1.anm2"] = 13,
  ["gfx/ui/minimap2.anm2"] = 13,
  ["sprite/gt/gt_ui.anm2"] = 14,
}
P1SPRITE_FAILS = false
function Sprite()
  if P1SPRITE_FAILS then error("no sprite") end
  local object = { path = nil, frames = 1, frame = 0 }
  function object:Load(path, graphics)
    self.path = path
    self.frames = P1SPRITE_FRAMES[path] or 1
  end
  function object:SetFrame(name, index) self.frame = index or 0 end
  function object:SetLastFrame() self.frame = (self.frames or 1) - 1 end
  function object:GetFrame() return self.frame end
  function object:IsPlaying(name) return P1SPRITE_FRAMES[self.path] ~= nil end
  return object
end

-- 场景由 Python 侧灌进来：P1SCENE 的字段决定 Game() 返回什么
gt = { widget = { mmp_pin = 0 },
  get_config = function() return { OverlayKeyController = 10, ShowSpecialIcons = true,
      KeyboardMapEnable = true, OverlayKey = nil, MinimapScale = 10,
      DimMapInCombat = true, CursorOnGameMap = false, SwapAnalogSticks = false } end }

P1SCENE = {
  stage = 1, stage_type = 0, curses = 0, ascent = false,
  room_type = 1, visited = 3, grid = 7,
  spawn_size = 3,
  spawns = { },            -- 每个元素 { entry_count = n, entry = {Type=..., Variant=...} 或 nil }
}
function Game()
  local scene = P1SCENE
  return {
    GetLevel = function(self)
      return {
        GetStage = function() return scene.stage end,
        GetStageType = function() return scene.stage_type end,
        GetCurses = function() return scene.curses end,
        IsAscent = function() return scene.ascent end,
        GetCurrentRoomDesc = function()
          return {
            VisitedCount = scene.visited,
            GridIndex = scene.grid,
            Data = {
              Type = scene.room_type,
              Spawns = {
                Size = scene.spawn_size,
                Get = function(self, index)
                  local item = scene.spawns[index + 1]
                  if item == nil then return nil end
                  return {
                    EntryCount = item.entry_count,
                    PickEntry = function(self, r)
                      return item.entry
                    end,
                  }
                end,
              },
            },
          }
        end,
      }
    end,
  }
end
"""


def make_lua():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(PREAMBLE)
    lua.execute(PROBE.read_text(encoding="utf-8"))
    return lua


FAILURES: list[str] = []
CHECKS = 0


def check(condition: bool, label: str) -> None:
    global CHECKS
    CHECKS += 1
    if not condition:
        FAILURES.append(label)


def scene(lua, **fields):
    """把 Python 的 dict 灌进 Lua 侧的 `P1SCENE`。"""
    lua.execute("P1LINES = {}")
    for key, value in fields.items():
        if key == "spawns":
            lua.execute(
                "P1SCENE.spawns = {} "
                "for i = 1, %d do "
                "  P1SCENE.spawns[i] = { entry_count = %d, entry = %s } "
                "end"
                % (
                    len(value),
                    value[0]["entry_count"] if value else 0,
                    "nil",
                )
            )
            # 逐条补充（上面的循环只为了建表，真正的值在这里逐条覆盖）
            for index, item in enumerate(value, start=1):
                entry = item.get("entry")
                if entry is None:
                    entry_lua = "nil"
                else:
                    entry_lua = "{ Type = %d, Variant = %d, SubType = %d }" % (
                        entry.get("Type", 0),
                        entry.get("Variant", 0),
                        entry.get("SubType", 0),
                    )
                lua.execute(
                    "P1SCENE.spawns[%d] = { entry_count = %d, entry = %s }"
                    % (index, item["entry_count"], entry_lua)
                )
        else:
            lua.globals().P1SCENE[key] = value


def frame(lua):
    """跑一帧：先 MC_POST_UPDATE，再 MC_POST_RENDER。"""
    lua.execute("P1CALLBACKS[1]()")
    lua.execute("P1CALLBACKS[2]()")


#: 探针的 anm2 探针起跑帧（与 `main.lua` 的 `ANM2_PROBE_START_FRAME` 必须一致）。
ANM2_START_FRAME = 300


def frames(lua, count: int) -> None:
    """连跑 `count` 帧（直接调 Lua 函数，不重复 execute 源码 —— 几百帧时快得多）。"""
    update = lua.globals().P1CALLBACKS[1]
    render = lua.globals().P1CALLBACKS[2]
    for _ in range(count):
        update()
        render()


def lines(lua) -> list[str]:
    return [row["text"] for row in lua.globals().P1LINES.values()]


def joined(lua) -> str:
    return "\n".join(lines(lua))


def check_ascii(lua, label: str) -> None:
    """★ 屏幕那一路**只许 ASCII**：主通道的字体是引擎自带的 terminus8，写中文会画成空白/乱码。
    （2026-10-04 批次 362 实测踩过：`ANM … 12=本体 0=模组` 里那四个汉字画不出来。
    只在受控场景里查 —— 别人模组的报错原文可能真的是中文，那种不算错。）
    """
    bad = [row for row in lines(lua) if any(ord(ch) > 127 for ch in row)]
    check(not bad, "%s: 屏幕那一路出现了非 ASCII 字符（会画不出来）：%s" % (label, bad))


def main() -> int:
    lua = make_lua()
    check(lua.globals().P1CALLBACKS[1] is not None, "MC_POST_UPDATE 没注册")
    check(lua.globals().P1CALLBACKS[2] is not None, "MC_POST_RENDER 没注册")

    ok_entry = {"Type": 33, "Variant": 4, "SubType": 0}
    other_entry = {"Type": 21, "Variant": 0, "SubType": 0}
    entry_970 = {"Type": 970, "Variant": 2, "SubType": 0}

    # --- 场景 A：一切正常（三格都有条目，且都不命中 970）--------------------
    scene(
        lua,
        stage=1, stage_type=0, curses=0, ascent=False,
        room_type=1, visited=3, grid=7, spawn_size=3,
        spawns=[
            {"entry_count": 1, "entry": other_entry},
            {"entry_count": 1, "entry": ok_entry},
            {"entry_count": 1, "entry": other_entry},
        ],
    )
    frame(lua)
    text = joined(lua)
    check("LOOP ok=true" in text, "A: 应当 ok=true，实得\n" + text)
    check("ERRN=0" in text, "A: 应当 ERRN=0，实得\n" + text)
    check("SZ3" in text, "A: 应当 SZ3，实得\n" + text)
    check("0/EC1/T21" in text, "A: 第 0 格应当 EC1/T21，实得\n" + text)
    check("1/EC1/T33" in text, "A: 第 1 格应当 EC1/T33，实得\n" + text)
    check("FONT>" in text, "A: 字体那条备用通道应当画出来，实得\n" + text)
    check_ascii(lua, "A")
    check(len(lines(lua)) >= 8, "A: 行数太少（%d），实得\n%s" % (len(lines(lua)), text))

    # --- 场景 B：★ 关键分支 —— 第 1 格 EntryCount=0 且 PickEntry 给 nil --------
    scene(
        lua,
        stage=2, stage_type=4, curses=0, ascent=False,
        room_type=1, visited=5, grid=9, spawn_size=3,
        spawns=[
            {"entry_count": 1, "entry": other_entry},
            {"entry_count": 0, "entry": None},
            {"entry_count": 1, "entry": other_entry},
        ],
    )
    frame(lua)
    text = joined(lua)
    check("EFF1" in text, "B: stage=2 应当算出 EFF1，实得\n" + text)
    check("LOOP ok=false" in text, "B: 应当 ok=false，实得\n" + text)
    check("attempt to index" in text, "B: 报错原文应当带上（GoodTrip 那句），实得\n" + text)
    check("ERRN=1" in text, "B: 应当 ERRN=1，实得\n" + text)
    check("E1@" in text, "B: 应当留下「当时在哪」那一行，实得\n" + text)
    check("SZnil" not in text, "B: SZ 不应当是 nil，实得\n" + text)
    check("1/EC0/nil" in text, "B: 第 1 格应当 EC0 且 PickEntry 给 nil，实得\n" + text)

    # --- 场景 C：报错之后继续跑，且第一次的原文**不被后来的正常帧冲掉** -------
    scene(
        lua,
        stage=1, stage_type=0, curses=0, ascent=False,
        room_type=1, visited=1, grid=1, spawn_size=1,
        spawns=[{"entry_count": 1, "entry": other_entry}],
    )
    frame(lua)
    text = joined(lua)
    check("attempt to index" in text, "C: 第一次报错的原文应当仍在屏幕上，实得\n" + text)
    check("ERRN=" in text, "C: ERRN 那一行应当仍在，实得\n" + text)
    check("LOOP ok=true" in text, "C: 这一帧本身应当是 ok=true，实得\n" + text)

    # --- 场景 D：Size=0（347 之前的老行为）⇒ 不应当报错、也不应当记错误 -------
    lua.execute("P1LINES = {}")
    frame(lua)
    # 先把累计清零是做不到的（S 是局部 upvalue）；换个进程重来一遍更干净。
    lua2 = make_lua()
    scene(
        lua2,
        stage=6, stage_type=0, curses=0, ascent=False,
        room_type=1, visited=1, grid=1, spawn_size=0,
        spawns=[],
    )
    frame(lua2)
    text2 = joined(lua2)
    check("SZ0" in text2, "D: 应当 SZ0，实得\n" + text2)
    check("LOOP ok=true" in text2, "D: Size=0 时循环一次都不跑 ⇒ ok=true，实得\n" + text2)
    check("ERRN=0" in text2, "D: Size=0 不应当记错误，实得\n" + text2)
    check("EFF3" in text2, "D: stage=6 应当算出 EFF3，实得\n" + text2)

    # --- 场景 E：迷宫诅咒（stage=1 + CURSE_OF_LABYRINTH=2 + stageType=4）⇒ EFF1 -
    lua3 = make_lua()
    scene(
        lua3,
        stage=1, stage_type=4, curses=2, ascent=False,
        room_type=1, visited=1, grid=1, spawn_size=0,
        spawns=[],
    )
    frame(lua3)
    text3 = joined(lua3)
    check("EFF1" in text3, "E: 迷宫诅咒下的 stage=1 应当算出 EFF1，实得\n" + text3)

    # --- 场景 F：字体通道失败（Font() 抛错）⇒ 不抛出去、降级成一行文字 -------
    lua4 = make_lua()
    lua4.execute("P1FONT_FAILS = true")
    scene(
        lua4,
        stage=1, stage_type=0, curses=0, ascent=False,
        room_type=1, visited=1, grid=1, spawn_size=0,
        spawns=[],
    )
    frame(lua4)
    text4 = joined(lua4)
    check("font: FAIL" in text4, "F: 字体拿不到时应当画一行 font: FAIL，实得\n" + text4)
    check("P1 v1" in text4, "F: 主通道不应当受字体失败影响，实得\n" + text4)

    # --- 场景 G：★ 护栏 —— Size 读成垃圾值 ⇒ 只报告、不循环、不污染 ERRN --------
    lua5 = make_lua()
    scene(
        lua5,
        stage=1, stage_type=0, curses=0, ascent=False,
        room_type=1, visited=1, grid=1, spawn_size=99999,
        spawns=[{"entry_count": 1, "entry": other_entry}],
    )
    frame(lua5)
    text5 = joined(lua5)
    check("SZ99999" in text5, "G: 应当如实报出读到的 Size，实得\n" + text5)
    check("out of sane range" in text5, "G: 应当报出护栏那句话，实得\n" + text5)
    check("calls=0" in text5, "G: 护栏命中时 calls 应当是 0（没循环），实得\n" + text5)
    check("ERRN=0" in text5, "G: 护栏不算 GoodTrip 那种报错，ERRN 应当仍是 0，实得\n" + text5)
    check("\nE1 " not in ("\n" + text5), "G: 不应当把护栏写进 E1，实得\n" + text5)

    # --- 场景 H：★★ 抓住"别的模组在绘制回调里报的错" ------------------------
    lua6 = make_lua()
    scene(
        lua6,
        stage=1, stage_type=0, curses=0, ascent=False,
        room_type=1, visited=1, grid=41, spawn_size=0,
        spawns=[],
    )
    frame(lua6)
    text6 = joined(lua6)
    check("CB3[" in text6, "H: 应当列出 3 条绘制回调，实得\n" + text6)
    check("GoodTrip" in text6, "H: 名单里应当出现 GoodTrip，实得\n" + text6)
    check("CE1 " in text6, "H: 应当抓到 1 条报错，实得\n" + text6)
    check("attempt to index" in text6, "H: 报错原文应当带上，实得\n" + text6)
    check("runs=2" in text6, "H: 应当额外跑 2 条（3 条里跳过探针自己），实得\n" + text6)

    # --- 场景 I：同一房间不重复跑；换房间再跑一次（runs 累加）---------------
    frame(lua6)
    text7 = joined(lua6)
    check("runs=2" in text7, "I: 同一房间第二次不应当再跑，实得\n" + text7)
    scene(
        lua6,
        stage=1, stage_type=0, curses=0, ascent=False,
        room_type=1, visited=1, grid=42, spawn_size=0,
        spawns=[],
    )
    frame(lua6)
    text8 = joined(lua6)
    check("runs=4" in text8, "I: 换房间后应当再跑一次（runs=4），实得\n" + text8)
    check("CE2 " in text8, "I: 报错会累加，实得\n" + text8)

    # --- 场景 J：★★ 打包文本经 `mod:SaveData` 交出去（调试桩从内存读的那一段）-----
    lua7 = make_lua()
    lua7.execute("P1MAP_HELD = true")          # 模拟"按住地图键"
    scene(
        lua7,
        stage=2, stage_type=4, curses=0, ascent=False,
        room_type=1, visited=6, grid=41, spawn_size=2,
        spawns=[{"entry_count": 1, "entry": other_entry},
                {"entry_count": 1, "entry": entry_970}],
    )
    frame(lua7)
    saved = lua7.globals().P1SAVED.text
    check(bool(saved), "J: 应当通过 Mod:SaveData 交出一段文本，实得空串")
    check("P1PROBE v1" in saved, "J: 打包文本应当有版本头，实得\n" + saved)
    check("OverlayKeyController=10" in saved, "J: 应当带上 GoodTrip 的键位配置，实得\n" + saved)
    check("keyobs" in saved and "btnAtMap" in saved, "J: 应当带上按键观测，实得\n" + saved)
    check("R st=2.4" in saved, "J: 应当带上房间记录，实得\n" + saved)
    check("want=1" in saved, "J: stage2+普通房+访问过+表非空 ⇒ want 应当是 1，实得\n" + saved)
    check("SZ2" not in saved, "J: 打包文本里不该出现屏幕行前缀，实得\n" + saved)

    # --- 场景 K：★★ 批次 362 的 anm2 加载探针 -------------------------------
    lua8 = make_lua()
    scene(
        lua8,
        stage=1, stage_type=0, curses=0, ascent=False,
        room_type=1, visited=1, grid=1, spawn_size=0,
        spawns=[],
    )
    frames(lua8, 1)
    text9 = joined(lua8)
    check("ANM n=0" in text9, "K: 还没到起跑帧时不应当有读数，实得\n" + text9)
    frames(lua8, ANM2_START_FRAME)     # 推进到第 301 帧（起跑帧是 300）
    text9 = joined(lua8)
    check("ANM n=1" in text9, "K: 过了起跑帧应当正好跑过一次，实得\n" + text9)
    check("sh1=12" in text9, "K: 共享路径应当读成本体那份（13 帧 ⇒ 12），实得\n" + text9)
    check("sh2=12" in text9, "K: 第二个共享样本同样应当答 12，实得\n" + text9)
    check("gt=13" in text9, "K: 模组独有的 gt_ui（select，14 帧）应当答 13，实得\n" + text9)
    check("miss=0" in text9, "K: 故意不存在的路径应当答 0，实得\n" + text9)
    check_ascii(lua8, "K")
    saved9 = lua8.globals().P1SAVED.text
    check("anm2 n=1" in saved9, "K: 打包文本里应当带上 anm2 那一行，实得\n" + saved9)
    check("shared=12" in saved9 and "modonly=13" in saved9,
          "K: 打包文本那一行应当带四个按键名的读数，实得\n" + saved9)
    #: 再推进一个周期（600 帧）⇒ 应当跑第二次，且读数不变（idempotent）
    frames(lua8, 600)
    text10 = joined(lua8)
    check("ANM n=2" in text10, "K: 一个周期之后应当跑第二次，实得\n" + text10)
    check("sh1=12" in text10, "K: 第二次的读数应当与第一次一致，实得\n" + text10)

    if FAILURES:
        print("host check FAILED (%d / %d)" % (len(FAILURES), CHECKS))
        for item in FAILURES:
            print(" - " + item)
        return 1
    print("host check OK：11 个场景、%d 条断言全部通过" % CHECKS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
