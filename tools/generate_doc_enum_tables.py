#!/usr/bin/env python3
"""从**仓库自带的 PC 文档快照**生成"PC 全局枚举表"的 C++ 数据（补 `pc_lua_enum_data` 之外的那几张）。

## 为什么需要它（2026-09-19 批次 048）

`tools/generate_pc_lua_enum_tables.py` 只认 20 张表，而且它的输入是**用户 PC 游戏本体的
`enums.lua`**（不在仓库里）⇒ 那 20 张之外的表**没人能补**。真机上就撞上了：
GoodTrip 读 `RoomShape.ROOMSHAPE_LTL` 拿到 `nil`、`attempt to index a nil value (global 'RoomShape')`，
整条绘制回调被打断（小地图出不来）。

而 `tools/pc_enum_docs/`（模组开发文档枚举页的**逐字节副本**，进门禁、可由 git 复核）**就在仓库里**，
它的枚举页是规范的三列表格 `|DLC|Value|Enumerator|…|` / `|…|1 << 16|FLAG_ROT…|` ⇒
**名 → 值**可以机器解析、机器复核。本工具就读它。

## 与 `pc_lua_enum_data` 的关系（重要）

* **表名不许重叠**：那 20 张由 `pc_lua_enum_data` 提供（它们是 `enums.lua` 里被冻结的那批），
  这里只生成本工具 `TABLES` 里列的表；生成时会**断言两边不相交**，避免运行时互相覆盖。
* **值类型不同**：那张表的 `Value.value` 是 `std::int32_t`（所以 `1 << 32` 这类装不下、
  生成器会显式报错），本表用 **`std::int64_t`** —— `DamageFlag.DAMAGE_SPAWN_RUNE = 1 << 32`、
  `TearFlags` 那一类比比皆是，用 32 位会**静默回绕**成 0（假读数）。

## 用法

    python3 tools/generate_doc_enum_tables.py --write      # 生成/更新
    python3 tools/generate_doc_enum_tables.py --check      # 门禁用：与文档快照不一致就退出码 1

值的表达式只支持 `整数 / 十六进制 / 一元负号 / 左移 / 按位或 / 加 / 括号`；
遇到不认识的形状**直接失败**（静默跳过 = 让模组拿到 nil，那正是我们要避免的事）。
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: 契约快照（**进门禁的逐字节副本**，见该目录的 README）。
#:
#: ★ 为什么不是直接读 `analysis/isaacdocs-snapshot/`：那是本机的分析产物，**`analysis/` 被 gitignore**
#: ⇒ 干净检出（门禁里"只用 `git ls-files` 复制被跟踪文件"的那个用例）里根本没有这些页，
#: 生成器的输入就不存在。更根本的是：**契约源不在仓库里 = 这一类工作对任何其他人都不可做** ——
#: `pc_lua_enum_data`（那 20 张表）的输入是用户 PC 游戏本体、不在仓库里，所以"之外的表"
#: 长期没人能补（2026-09-19 真机撞 `RoomShape` 就是后果）。
DOC_DIR = ROOT / "tools" / "pc_enum_docs"

#: 本工具负责生成的表。**只放 `pc_lua_enum_data` 那 20 张之外的**。
#: 2026-09-19 首批：GoodTrip 真机上真正要用的那几张（先按"用了什么补什么"，
#: 同时把它们的整表都发出来 —— 只发一半会让模组读别的常量时又拿到 nil）。
TABLES = (
    "RoomShape",
    "DoorVariant",
    "Direction",
    "StageType",
    "DamageFlag",
    "RoomDescriptor",
    # 2026-09-20 批次 105：`CallbackPriority`。
    # ★ 这一张是**又一条"模组读不到"的实例**，而且是 GoodTrip 的**加载期**拦路虎：
    #   它的 `main.lua:84` 起有 **7 处** `_gt:AddPriorityCallback(…, CallbackPriority.EARLY, …)`
    #   **没有被 pcall 包住** ⇒ 这个全局是 nil 时整块 main.lua 在第 84 行中止，
    #   后面所有回调一个都注册不上（"小地图不出现"就是这么来的）。
    #   值：IMPORTANT=-200 / EARLY=-100 / DEFAULT=0 / LATE=100（**数值越小越早执行**）。
    "CallbackPriority",
    # 2026-09-29 批次 207：`ProjectileFlags` / `EntityFlag` —— MCM（Mod Config Menu）的两处**加载期
    # 与按键路径**消费者：
    #   * `ProjectileFlags.CANT_HIT_PLAYER`（`1 << 31`）：`modconfig.lua:220` 判"这发子弹会不会打到
    #     玩家"（`entity:ToProjectile().ProjectileFlags & ProjectileFlags.CANT_HIT_PLAYER`）；
    #   * `EntityFlag.FLAG_NO_QUERY` / 活表那几位：`Entity:HasEntityFlags(int)` 的实参来源。
    # 这两张表的**成员**由 `Entity:HasEntityFlags` / `EntityProjectile.ProjectileFlags` 两条 API 承接，
    # 所以"表 nil"会让模组拿到 nil 再按位与 ⇒ 整条回调报错被摘（与 RoomShape 那次同一形状）。
    # ★ 这两张表的值**超过 32 位**（`ProjectileFlags` 到 `1 << 48`）—— 正是本工具用 `int64` 的理由；
    #   文档里的 `.reporplus` 徽章本工具**不过滤**（与既有 7 张表同一口径：整表发出去，
    #   免得模组读别的常量时又拿到 nil）。
    "ProjectileFlags",
    "EntityFlag",
    # 2026-09-30 批次 212：`SoundEffect` —— **又一条"模组读不到就把整条回调掐死"的实例**，
    #   而且这次掐的是 MCM 的**声音**路径（`modconfig.lua:2950` 起
    #   `sfx:Play(SoundEffect.SOUND_BOSS2INTRO_ERRORBUZZ, …)`）：`SoundEffect` 是 nil 时
    #   这一行抛 `attempt to index a nil value (global 'SoundEffect')` ⇒ 那条回调当场中断
    #   （不只是"没声音"：它后面要做的事一件都做不成）。
    #   证据：真机读数 `dist/gdb-read-20260930-005757.txt` 的"最近 2 条 Lua 错误"第 2 条。
    "SoundEffect",
    # 2026-09-30 批次 217：`SeedEffect` —— **第三次同形状**（`RoomShape` → `SoundEffect` → 这一次），
    #   而且这次卡的是**中文版 MCM 的"开菜单"本行**：
    #   `modconfig.lua:3616` 在"显示菜单"那段里 `seeds:AddSeedEffect(SeedEffect.SEED_NO_HUD)`
    #   （`HideHudInMenu` 打开时必经），`SeedEffect` 是 nil ⇒
    #   `attempt to index a nil value (global 'SeedEffect')` ⇒ 那句之后的
    #   `ModConfigMenu.IsVisible = true` **永远执行不到** ⇒ 症状是"按右摇杆菜单打不开"
    #   （用户实测，且与输入链无关）。
    #   证据：真机读数 `dist/gdb-read-20260930-1411-cn-menu-broken.txt`（修 `RegisterMod` 之后仍报的那条）
    #   与修复后的 `dist/gdb-read-20260930-14xx-cn-seedeffect.txt`。
    #   值：`SEED_NO_HUD = 10`、`NUM_SEEDS = 80`（叶尾，**没有重复键**，不需要进 DUPLICATE_LAST_WINS）。
    "SeedEffect",
    # 2026-10-02 批次 269：`RenderMode` —— **第四次同形状**（RoomShape → SoundEffect → SeedEffect
    #   → 这一次），拦路虎在 BOIStageAPI15：
    #   `scripts/stageapi/grid/customdoors.lua:415` 无条件写
    #   `if shared.Room:GetRenderMode() == RenderMode.RENDER_NORMAL then …`，
    #   而 `RenderMode` 是 nil 时报 `attempt to index a nil value (global 'RenderMode')`
    #   ⇒ 那句之后的 `OverlaySprite:Render(...)` 永远执行不到（自定义门的高亮不出现），
    #   而且整条 `MC_POST_EFFECT_RENDER` 回调在那里中断。
    #   值：RENDER_NULL=0 / RENDER_NORMAL=1 / RENDER_SKIP=2 / RENDER_WATER_ABOVE=3 /
    #   RENDER_WATER_REFRACT=4 / RENDER_WATER_REFLECT=5（本页**没有重复键**）。
    #   ★ 与本批同时落地的 `Room:GetRenderMode()`（catalog 0x04010024）是**同一件事的两半**：
    #     少了这张表，那条 API 的返回值也仍然用不上。
    "RenderMode",
    # 2026-10-02 批次 292：`BackdropType` —— 与本批的 `Room:GetBackdropType()` 是**同一件事的两半**
    #   （与 269 那批的 `RenderMode` + `Room:GetRenderMode()` 逐字同形）：少了这张表，
    #   `Room:GetBackdropType()` 的返回值**也用不上**。
    #   消费者的证据：`MusicModCallback/scripts/mmc/repentance.lua:431` 起用
    #   `[BackdropType.BASEMENT] = Music.MUSIC_BASEMENT` 一类**整张以枚举值为键的映射表**
    #   （`BackdropType` 是 nil 时那些键全成 nil ⇒ 选曲静默错），同一文件的 `:467` 又正是
    #   `Game():GetRoom():GetBackdropType()` 的调用点；`BOIStageAPI15` 的
    #   `customFloorGen.lua:874` 拿它跟自定义楼层的 `Backdrop` 比。
    #   ★ 页里**没有 `BACKDROP_WATER`** —— 32 是 `MINES`（`Room::pre_render_pits` 里的
    #     `cmp w8,#0x20` 判的就是"矿层"，之后才看 `Flags` bit5 决定画不画水坑）。
    "BackdropType",
    # 2026-10-03 批次 297：`GameStateFlag` / `LevelStateFlag` —— 与本批落地的
    #   `Game:GetStateFlag(int Flag)` / `Level:GetStateFlag(int Flag)` 是**同一件事的两半**
    #   （第五次同形状：`RenderMode` → `BackdropType` → 这一次一对）。
    #   消费者证据：模组是**拿枚举常量当实参**的，缺表就是那一行直接抛错：
    #     * `ChallengeAPI/.../stage_transition.lua:34`
    #       `Game():SetStateFlag(GameStateFlag.STATE_BACKWARDS_PATH_INIT, true)`；
    #     * `ChallengeAPI` / `BOIStageAPI15` / `MusicModCallback` 多处
    #       `GetStateFlag(GameStateFlag.STATE_*)`（`STATE_BACKWARDS_PATH` / `STATE_MAUSOLEUM_HEART_KILLED`）；
    #     * `MinimapAPI` / `MusicModCallback` / `BOIStageAPI15` 多处
    #       `GetStateFlag(LevelStateFlag.STATE_MAP_EFFECT / STATE_COMPASS_EFFECT /
    #        STATE_MINESHAFT_ESCAPE / STATE_LEVEL_START_TRIGGERED)`。
    #   ★ 两张表**都要**：`GameStateFlag` 与 `LevelStateFlag` 是**两个不同的枚举**
    #     （前者在 `Game` 上、后者在 `Level` 上），模组哪一边都可能用。
    #   ★ `GameStateFlag.NUM_STATE_FLAGS` 在页里出现**两次**（`.rep` 档 49 / `.repplus` 档 53）
    #     ⇒ 已按规程登记进 `DUPLICATE_LAST_WINS`（取 53，与 `SoundEffect` / `BackdropType` 同口径）。
    #     `LevelStateFlag` **没有**重复键（`NUM_STATE_FLAGS` 只在末尾出现一次，值 24）。
    "GameStateFlag",
    "LevelStateFlag",
    # 2026-10-03 批次 301：`CacheFlag` —— 与本批落地的
    #   `EntityPlayer:AddCacheFlags(CacheFlag)`（34 处 / 4 个模组）是**同一件事的两半**
    #   （第六次同形状：`RenderMode` → `BackdropType` → `GameStateFlag`/`LevelStateFlag` → 这一次）。
    #   消费者证据：模组是**拿枚举常量当实参**的，缺表就是那一行直接抛错、整条回调被摘：
    #     * `Trinity/main.lua:754`
    #       `player:AddCacheFlags(CacheFlag.CACHE_DAMAGE | CacheFlag.CACHE_FIREDELAY)`；
    #     * `RepentancePlus/.../main.lua:758/1441` 的 `CacheFlag.CACHE_LUCK`、
    #       `:1139/1144` 的 `CACHE_DAMAGE` / `CACHE_FIREDELAY`、`:1534` 的 `CACHE_SHOTSPEED`；
    #     * `IsaacOnTwitchReloaded/scripts/{mechanics,callbacks,passiveItems,events,trinkets}.lua`
    #       与 `BOIStageAPI15/scripts/stageapi/stage/transitions.lua` 的
    #       `CACHE_ALL` / `CACHE_SPEED` / `CACHE_FLYING`；
    #     * `IsaacOnTwitchReloaded/main.lua:700` 甚至把值存在自己的表里
    #       （`IOTR.Items.Passive[key].cacheFlag`）⇒ 表是 nil 时**静默变成 nil 掩码**。
    #   ★ 那些值与本批的 Switch 侧取证**逐位对上**（打在同一个字 `Entity_Player+0x1958` 上）：
    #     `CACHE_DAMAGE=1<<0` / `CACHE_FIREDELAY=1<<1` / `CACHE_SHOTSPEED=1<<2` / `CACHE_RANGE=1<<3` /
    #     `CACHE_SPEED=1<<4` 正好是 `EvaluateItems` 里 `tbnz w8,#0/#1/#3/#4` + `tbz w8,#0x2` 的位号，
    #     `CACHE_LUCK=1<<10` 正是 `DonateLuck` 往里 OR 的 `0x400`，`CACHE_WEAPON=1<<8` 是 `tbz w8,#0x8`。
    #   ★ 本页**没有重复键** ⇒ 不需要进 `DUPLICATE_LAST_WINS`。
    "CacheFlag",
)

#: 与 `pc_lua_enum_data.cpp` 的表名列表比对用的对方文件。
FROZEN_TABLE_IMPLEMENTATION = ROOT / "runtime" / "source" / "program" / "pc_lua_enum_data.cpp"

#: **登记在案**的"同一个枚举名在文档里合法地出现两次、且值不同"的键（口径见解析处的注释）。
#: 这些页按"值升序 + DLC 档递增"排 ⇒ 取**最后一处** = 目标版本（Rep+ / 1.7.9b）的值。
#: 例：`SoundEffect.NUM_SOUND_EFFECTS`（`.rep` = 833、`.repplus` = **1091**）。
#: 没登记的重复键一律判错（保持"有歧义就红"）。
DUPLICATE_LAST_WINS = frozenset({
    "SoundEffect.NUM_SOUND_EFFECTS",
    # 批次 292（2026-10-02）：`BackdropType.NUM_BACKDROPS` —— 页里出现两次，
    # `.abrep` 徽章那一行是 **61**、`.repplus` 徽章那一行是 **63**（另有 `DEATHMATCH = 61`、
    # `LIL_PORTAL = 62` 只有 Rep+ 才有）⇒ 目标版本取 63（与 `SoundEffect` 同口径）。
    "BackdropType.NUM_BACKDROPS",
    # 批次 297（2026-10-03）：`GameStateFlag.NUM_STATE_FLAGS` —— 页里出现两次
    # （`.rep` 徽章那一行是 **49**、`.repplus` 徽章那一行是 **53**）⇒ 目标版本取 53。
    "GameStateFlag.NUM_STATE_FLAGS",
})

HEADER_PATH = ROOT / "runtime" / "source" / "program" / "doc_lua_enum_data.hpp"
IMPLEMENTATION_PATH = ROOT / "runtime" / "source" / "program" / "doc_lua_enum_data.cpp"

#: 表格行里"值"与"枚举名"所在的列（`|` 切分后：0 是行首那个空串）。
VALUE_COLUMN = 2
ENUMERATOR_COLUMN = 3

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COPYABLE_SUFFIX = "{: .copyable }"


class DocEnumError(RuntimeError):
    """文档里出现了本工具读不懂的东西 —— 一律响亮失败，不静默跳过。"""


def _evaluate_expression(expression: str, table: str, key: str) -> int:
    """只接受 `整数 / 十六进制 / 一元负号 / << / | / + / 括号` 的表达式。

    ★ 与 `generate_pc_lua_enum_tables.py` 的同名函数**刻意分开**：那个把值装进 `int32`，
    所以它会拒绝 `1 << 32`；本工具用 `int64`，必须**接受**它（`DamageFlag.DAMAGE_SPAWN_RUNE`）。
    """
    text = expression.strip()
    if not text:
        raise DocEnumError(f"{table}.{key}：值是空的")
    # 只允许白名单字符，避免把文档里的说明文字当成表达式算。
    if not re.fullmatch(r"[0-9a-fA-FxX()|<>\-+ \t]+", text):
        raise DocEnumError(f"{table}.{key}：值表达式 {expression!r} 里有不认识的字符")
    try:
        value = eval(text, {"__builtins__": {}}, {})  # noqa: S307 - 字符白名单已限定
    except SyntaxError as error:
        raise DocEnumError(f"{table}.{key}：值表达式 {expression!r} 解析失败（{error}）") from error
    if not isinstance(value, int):
        raise DocEnumError(f"{table}.{key}：值表达式 {expression!r} 不是整数")
    if not -(2 ** 63) <= value < 2 ** 63:
        raise DocEnumError(f"{table}.{key}：值 {value} 超出 int64")
    return value


def parse_table(table: str, source: pathlib.Path) -> list[tuple[str, int]]:
    """把一张枚举页解析成 `[(名字, 值), …]`（保持文档里的出现顺序）。

    页面里可能有**多张**表格（例如 `RoomDescriptor` 有 `DISPLAY_*` 与 `FLAG_*` 两张）——
    PC 把它们都挂在同一个全局表下，所以这里全部收进来。
    """
    if not source.is_file():
        raise DocEnumError(f"找不到文档快照页：{source}")
    entries: list[tuple[str, int]] = []
    seen: dict[str, int] = {}
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) <= ENUMERATOR_COLUMN:
            continue
        raw_value = cells[VALUE_COLUMN]
        raw_key = cells[ENUMERATOR_COLUMN].replace(_COPYABLE_SUFFIX, "").strip()
        if not _IDENTIFIER.fullmatch(raw_key):
            continue                      # 分隔行 / 说明行
        if raw_key == "Enumerator" or raw_value == "Value" or raw_value.startswith(":--"):
            continue                      # 表头（`|DLC|Value|Enumerator|…|`）与分隔行
        value = _evaluate_expression(raw_value, table, raw_key)
        if raw_key in seen:
            if seen[raw_key] != value:
                # ★ 2026-09-30 批次 212：文档里同一个枚举名**合法地**出现两次的情况 ——
                #   "计数常量"每个 DLC 档各一行（例：`SoundEffect.NUM_SOUND_EFFECTS`
                #   `.rep` 档 = 833、`.repplus` 档 = 1091）。这些页是按"值升序 + DLC 档递增"排的
                #   ⇒ **最后一行就是本任务目标版本（Rep+ / 1.7.9b）的值**。
                #   ★ 只有**登记在案**的键允许"取最后一处"；其余重复仍然判错 ——
                #     这不是"静默取一个"，而是"有歧义就红，除非明确登记了怎么解"。
                if f"{table}.{raw_key}" not in DUPLICATE_LAST_WINS:
                    raise DocEnumError(
                        f"{table}.{raw_key} 出现两次且值不同（{seen[raw_key]} / {value}）"
                        f"—— 要么修文档，要么把它登记进 DUPLICATE_LAST_WINS 并写明理由")
                seen[raw_key] = value
                for index, (key, _old) in enumerate(entries):
                    if key == raw_key:
                        entries[index] = (raw_key, value)
                        break
                continue
            continue                      # 同值重复：保留第一次
        seen[raw_key] = value
        entries.append((raw_key, value))
    if not entries:
        raise DocEnumError(f"{table}：从 {source} 里一条都没解析出来（格式变了？）")
    return entries


def frozen_table_names() -> set[str]:
    """`pc_lua_enum_data.cpp` 里已经发布了哪些表 —— 用来断言"两边不相交"。"""
    text = FROZEN_TABLE_IMPLEMENTATION.read_text(encoding="utf-8")
    return set(re.findall(r'\{"([A-Za-z_][A-Za-z0-9_]*)",\s*k', text))


def collect() -> list[tuple[str, list[tuple[str, int]]]]:
    frozen = frozen_table_names()
    overlap = sorted(set(TABLES) & frozen)
    if overlap:
        raise DocEnumError(
            "这些表已经在 pc_lua_enum_data 里发布了，本工具再发一次会互相覆盖："
            + "、".join(overlap)
        )
    return [(name, parse_table(name, DOC_DIR / f"{name}.md")) for name in TABLES]


def snapshot_digest() -> str:
    """文档快照的指纹：把本工具读的那几页按名字排序后连起来算 sha256。

    写进生成物头部 ⇒ 文档更新了、生成物没跟上，一眼能看出来（门禁也会红）。
    """
    digest = hashlib.sha256()
    for name in sorted(TABLES):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update((DOC_DIR / f"{name}.md").read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def render_header(digest: str) -> str:
    return "\n".join([
        "// Generated by tools/generate_doc_enum_tables.py; do not edit manually.",
        f"// docs snapshot SHA-256: {digest}",
        "//",
        # ★ 批次 292（2026-10-02）修正：这里原先写的是 `analysis/isaacdocs-snapshot/docs/enums/`
        #   —— 那正是本工具**刻意不读**的目录（`analysis/` 被 gitignore）。真值源是
        #   `DOC_DIR`（`tools/pc_enum_docs/`）里那批**逐字节 vendor 进仓库**的页，
        #   生成物头部的凭据 `docs snapshot SHA-256` 指的也是它们。
        "// 这些表来自 `tools/pc_enum_docs/`（逐字节 vendor 进仓库的 PC 文档枚举页），",
        "// 是 `pc_lua_enum_data` 那 20 张之外的**补充** —— 值用 `std::int64_t`，",
        "// 因为 `DamageFlag.DAMAGE_SPAWN_RUNE` 这类是 `1 << 32`，用 32 位会静默回绕成 0。",
        "#pragma once",
        "",
        "#include <cstddef>",
        "#include <cstdint>",
        "",
        "namespace DocLuaEnumData {",
        "struct Value { const char* key; std::int64_t value; };",
        "struct Table { const char* name; const Value* values; std::size_t count; };",
        "const Table* Tables(std::size_t* count);",
        "} // namespace DocLuaEnumData",
        "",
    ])


def render_implementation(digest: str,
                          tables: list[tuple[str, list[tuple[str, int]]]]) -> str:
    lines = [
        "// Generated by tools/generate_doc_enum_tables.py; do not edit manually.",
        f"// docs snapshot SHA-256: {digest}",
        '#include "doc_lua_enum_data.hpp"',
        "",
        "namespace DocLuaEnumData {",
    ]
    references = []
    for name, entries in tables:
        symbol = f"k{name}Values"
        lines.append(f"namespace {{ constexpr Value {symbol}[] = {{")
        for key, value in entries:
            lines.append(f'    {{"{key}", {value}}},')
        lines.append("}; }")
        references.append(
            f'    {{"{name}", {symbol}, sizeof({symbol}) / sizeof({symbol}[0])}},'
        )
    lines.append("")
    lines.append("namespace { constexpr Table kTables[] = {")
    lines.extend(references)
    lines.append("}; }")
    lines.append("")
    lines.append("inline const Table* Tables(std::size_t* count) {")
    lines.append("    if (count != nullptr) *count = sizeof(kTables) / sizeof(kTables[0]);")
    lines.append("    return kTables;")
    lines.append("}")
    lines.append("} // namespace DocLuaEnumData")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="生成/更新 C++ 文件")
    parser.add_argument("--check", action="store_true",
                        help="检查生成物是否与文档快照一致（门禁用）")
    args = parser.parse_args(argv)
    if not (args.write or args.check):
        parser.error("至少要给一个 --write 或 --check")

    try:
        tables = collect()
        digest = snapshot_digest()
    except DocEnumError as error:
        print(f"文档快照解析失败：{error}", file=sys.stderr)
        return 2

    header = render_header(digest)
    implementation = render_implementation(digest, tables)
    status = 0

    if args.write:
        HEADER_PATH.write_text(header, encoding="utf-8")
        IMPLEMENTATION_PATH.write_text(implementation, encoding="utf-8")
        print(f"已生成 {HEADER_PATH.relative_to(ROOT)}、{IMPLEMENTATION_PATH.relative_to(ROOT)}")

    if args.check:
        for path, expected in ((HEADER_PATH, header), (IMPLEMENTATION_PATH, implementation)):
            if not path.is_file():
                print(f"缺少生成物 {path.relative_to(ROOT)} —— 跑一次 --write", file=sys.stderr)
                status = 1
            elif path.read_text(encoding="utf-8") != expected:
                print(f"{path.relative_to(ROOT)} 与文档快照不一致 —— 跑一次 --write",
                      file=sys.stderr)
                status = 1
        if status == 0:
            total = sum(len(entries) for _name, entries in tables)
            print(f"文档枚举表与生成物一致（{len(tables)} 张表 / {total} 条常量）")
    return status


if __name__ == "__main__":
    sys.exit(main())
