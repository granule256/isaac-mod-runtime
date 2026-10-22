"""门禁：**引擎方法数据行**机制（`runtime/src/interfaces/lua/engine_method_api.hpp`）。

## 为什么有这条门禁（2026-09-19 批次 051）

一条"调引擎方法"的 API 原来要手写 ≈490 字节代码（入口守卫 224 + handler ~200），
而代码段当时只有 512 KiB、保留线 32 KiB ⇒ 2026-09-19 真的撞上了：**一口气补 8 条，构建直接失败**。
（当天晚些时候闸门按"失控增长闸门"的规则抬到 1 MiB / 2 MiB，见 `runtime/misc/link.ld` 的注释；
但"每条 API 花 490 字节代码"这个成本模型本身才是要治的东西。）

改成数据行之后，每个 API 只花 **16 字节只读数据、0 字节代码**（共享处理器一份）。
这条门禁守住这个**不变式** —— 否则不知不觉就会有人"顺手再写个处理器"，机制形同虚设：

1. 行里的 id 必须能在 `api_catalog.cpp` 里找到，**且 owner 对得上**；
2. 行的 `shape` 与 `argumentCount` 必须自洽（`VoidN` 就要 N 个整数参数）；
3. 行的两个常量（偏移 + 入口指纹）必须都在 `runtime_constants.hpp` 里，
   **且都登记进了 `tools/engine_symbol_signatures.json`**（否则 ABI 体检看不见它）；
4. **行里的 id 不许再出现在任何手写绑定表**（`{0x…, &Handler}` 那种）——
   那意味着这个 API 又占上了代码段，机制白做；
5. 行数写死（增删都要有人来解释）；
6. 行必须正好 16 字节（结构体里那条 `static_assert` 是成本前提）。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
LUA_DIR = ROOT / "runtime" / "src" / "interfaces" / "lua"
CATALOG = LUA_DIR / "api_catalog.cpp"
CONSTANTS = SOURCE / "runtime_constants.hpp"
SIGNATURES = ROOT / "tools" / "engine_symbol_signatures.json"
BINDING = LUA_DIR / "owner_binding.cpp"
ROWS_HEADER = LUA_DIR / "engine_method_api.hpp"

#: 承载数据行的家族 TU（加新的就在这张表里登记）。
#: ★ 批次 239 起 `music_api.cpp` 也在此列：`MusicManager` 的 7 条新 API 走数据行
#: （接收者是新的 `FieldReceipt::Music`，从 `Manager + kManagerMusicOffset` 解析）。
ROW_FILES = (LUA_DIR / "isaac_api.cpp", LUA_DIR / "game_api.cpp", LUA_DIR / "remaining_api.cpp",
             LUA_DIR / "music_api.cpp")

#: 行总数（**增删都要在这里解释**）。2026-09-19 批次 051 首批：5（EntityPlayer）+ 1（Game）
#: + 2（Level）+ 1（Room）= 9；批次 055 加 1 行：`Game:StartRoomTransition`（GoodTrip 传送的
#: 默认路径）⇒ 10；批次 063 再加 1 行：`Entity:IsFlying()`（GoodTrip 的诅咒房判定，
#: 缺它时刺房传送报 "attempt to call a nil value (method 'IsFlying')"）⇒ 11；
#: 批次 137（2026-09-26）再加 2 行：`EntityPlayer:AddNullCostume(int)` 与
#: `EntityPlayer:TryRemoveNullCostume(int)`（The Specialist for Good Items 的舞蹈段落要用，
#: 缺任意一条都会让整条回调被摘掉）⇒ 13。
#: ★ 批次 177（2026-09-28）再加 5 行：审查第 3 遍查出的 5 条"引擎里有同名成员函数、我们却恒返回假值"
#: 的桩（`EntityPlayer:GetPill(int)` / `GetCard(int)` / `GetZodiacEffect()` / `HasPlayerForm(Form)` /
#: `CanPickRedHearts()`）从**手写假桩**改成**数据行** ⇒ 13 + 5 = 18。
#: 为什么是这 5 条、另外 2 条为什么留到下一批：见
#: `docs/改动日志-20260928.md` §177 与 `dist/change-archive-20260928/177-five-stub-apis-to-engine-rows/README.md`。
#: ★ 批次 184（2026-09-28）再加 1 行：`EntityPlayer:GetGlyphOfBalanceDrop(variant, subtype)`
#: （`0x0E010042`）从手写"恒 0"桩改成数据行 —— 它是 §177 里"留到下一批"的两条之一。
#: 它需要一种**全新的形状**（`Ref2U32Pair`：`void(this, u32&, u32&)` + 返回一张两元表），
#: 这一批把形状补齐了 ⇒ 18 + 1 = 19。
#: ★ 批次 207（2026-09-29）再加 1 行：`Entity:IsActiveEnemy([bool includeDead])`（`0x0E010060`）
#: —— MCM 的 `RoomIsSafe()` 用它判"房间里有没有活敌人"。它需要**又一种新形状**
#: （`BoolOpt1`：`bool(this, bool 可选)`，"尾部参数可以省略"，省略时寄存器保持 0）
#: ⇒ 19 + 1 = **20**。
#: ★ 批次 238（2026-09-30）再加 **28** 行 —— **语料模组适配第一波**（用户指令：把
#: `analysis/mod-corpus/` 里那 17 个模组全部接上）。这一波挑的是"形状（`Void0/Void1/Void2`/
#: `Bool0/Bool1`/`Int0`）与接收者（`Entity`/`EntityPlayer`/`Room`/`Level`）都现成"的 28 条，
#: 所以**没有新形状、没有新接收者**，纯数据：
#: `Entity` 5 行（`IsBoss`/`IsEnemy`/`Kill`/`Remove`/`Update`）、`EntityPlayer` 13 行、
#: `Room` 6 行、`Level` 2 行、`Game` 2 行。
#: ★ 形状按**符号签名**取而不是按文档参数个数：`EntityPlayer:AddHearts(int)` 文档 1 个参数，
#: 符号是 `AddHearts(int, bool)` ⇒ ABI 两个整数 ⇒ `Void2`（默认参数在 ABI 上照样占寄存器）。
#: ⇒ 20 + 28 = **48**。
#: ★ 批次 239（2026-09-30）再加 **18** 行 —— **语料模组适配第二波 A 批**。用户指令：
#: 「先总结过往的错误经验，据此形成一套能批量且正确恢复 API 的流水线，来处理这次的 api 恢复任务」
#: （流水线本体 = `docs/批量恢复API的流水线.md`，待办清单 = `dist/api-restore-worklist.json`）。
#: 这一批取的正是清单里 `engine_row` 那 18 条：`Room` 6（`RemoveGridEntity`/`GetGridCollision`/
#: `SetGridPath`/`SpawnClearAward`/`DestroyGrid`/`TurnGold`）、`Level` 4（`SetStage`/`SetNextStage`/
#: `GetPlanetariumChance`/`GetRandomRoomIndex`）、`MusicManager` 7、`Game` 1（`GetGreedBossWaveNum`）。
#: ★ 本批**首次**同时动了两处机制本身（都是一次性的"能力"成本，不是"每条"的成本）：
#:   ① **9 种新形状**（`VoidIntIntBool`/`BoolIntIntInt`/`BoolIntBoolBool`/`Float0`/`IntBoolInt`/
#:      `VoidIntOpt1`/`BoolIntOpt1`/`VoidIntBoolOpt2`/`VoidFloatFloatOpt1`）—— 纯数据。
#:      其中 4 种专门为"**尾部参数可省**"而加：语料里 `Music:IsLayerEnabled()` / `EnableLayer()` /
#:      `DisableLayer()` **一个参数都不传**、`DestroyGrid(ind)` 只传 1 个、`SetGridPath(i, 0)` 只传 2 个，
#:      而复用 `Void1`/`Bool1` 会因为"参数个数严格相等"直接报错、摘掉整条模组回调。
#:   ② **一种新接收者** `FieldReceipt::Music`（`MusicManager()` 是占位句柄 ⇒ 接收者从
#:      `Manager + kManagerMusicOffset` 解析，不读 Lua 栈）—— 有了它，7 条音乐 API 才仍是数据行；
#:      否则每条都要回到 ≈490 字节的手写处理器。
#: ★ `music_api.cpp` 从本批起进入 `ROW_FILES`（它在批次 138 之前只承载手写处理器）。
#: ⇒ 48 + 18 = **66**。
#: ★ 批次 252（2026-10-01）再加 5 行（A 组 2 + B 组 3，含 3 种新形状）⇒ 66 + 5 = **71**。
#: ★ 批次 253（2026-10-01）再加 2 行（`Room:IsPositionInRoom` / `Game:CharmFart`，
#: 各带一种 `Vector2 const&` 参数的新形状）⇒ 71 + 2 = **73**。
#: ★ 批次 254（2026-10-01）再加 5 行 —— **语料 API 恢复**：`Game:MoveToRandomRoom`（1，
#: `kGameEngineRows`）、`ItemPool:RemoveCollectible`（1，`remaining_api.cpp` 本批**新建**的
#: `kItemPoolEngineRows`）、`EntityPlayer:AddKeys`/`AddGoldenKey`/`AddGoldenBomb`（3，
#: `kEntityPlayerEngineRows`）。★ 本批新增**一种接收者** `FieldReceipt::ItemPool`
#: （`ItemPoolHandle` 与 `Room`/`Music` 同形、不持引擎指针 ⇒ 接收者按
#: `ReadCurrentGameItemPool` 现查）与**两种形状**（`VoidBoolIntHandle`、`BoolIntBoolBoolOpt2`）。
#: ⇒ 73 + 5 = **78**。
#: ★ 批次 285（2026-10-02）再加 2 行 —— `EntityNPC:Morph`（1，`isaac_api.cpp` 本批**新建**的
#: `kEntityNPCEngineRows`）与 `EntityPickup:Morph`（1，新建的 `kEntityPickupEngineRows`）。
#: ★ 本批新增**两种形状**（都是一次性的"能力"成本）：`BoolIntIntIntInt`
#: （`bool(this, i32×4)` —— `EntityNPC:Morph`）与 `VoidIntIntIntBoolBoolBoolOpt3`
#: （`void(this, i32×3, bool×3)`、**尾部 3 个可省** —— `EntityPickup:Morph`；语料里 3 参与 6 参
#: 两种写法都有，少声明可省会让 3 参那条直接报错、摘掉整条模组回调）。
#: ★ 也没有新接收者：两条都走既有的 `FieldReceipt::Entity`（句柄校验口本批多认一张
#: `IsaacRuntime.EntityNPC` 元表）。
#: ⇒ 78 + 2 = **80**。
#: ★ 批次 286（2026-10-02）：80 → **81** —— `Entity:IsVulnerableEnemy()`（形状 `Bool0`）。
#: 那一次的计数改了、**这段说明漏了**，本批（288）补记。
#: ★ 批次 288（2026-10-02）：81 → **82** —— `EntityPlayer:GetMovementDirection()`（`Int0`，
#: 0 参返回整数）。形状是**既有的** `Int0` ⇒ 没有新增形状、也没有新接收者。
#: ★ 批次 303（2026-10-03）：82 → **84** —— `Entity:CanShutDoors()` 与 `EntityNPC:CanShutDoors()`
#: （**第一批"按 vtable 槽号调用"的行**：`offset` 最高位置 1、低 31 位 = 槽号；`entryWord` 写 0、
#: 处理器不核指纹）。形状沿用既有的 `Bool0` ⇒ 没有新增形状。
#: ★★ 同批还**扩了这个文件的 `ROW_RE`**：不认新形态的话，这两行会对**整张门禁隐形**
#: （`test_row_total_is_pinned` / `test_row_constants_are_declared_and_registered` 全都看不见它们）——
#: 这与"加了引擎方法行要改 `test_engine_row_api_surface.py` 的 `DATA_ROW_SURFACE`"是同一类盲点。
#: ★ 批次 304（2026-10-03）：84 → **86** —— `GridEntity:Destroy(boolean)` 与 `GridEntity:PostInit()`
#: （同机制；`Destroy` 用既有的 `BoolOpt1`（尾部布尔可省）、`PostInit` 用 `Void0` ⇒ 没有新形状）。
#: ★ 批次 321（2026-10-03）：86 → **87** —— `GridEntity:Update()`（同机制、槽 3；
#: 接收者与形状都沿用批 304 的 ⇒ 没有新形状、没有新接收者）。
#: ★ 批次 324（2026-10-03）：87 → **88** —— `EntityNPC.ThrowSpider`（静态调用；
#: 行形态不变，仍是 `{id, offset, entryWord, receipt, shape, N, 0xFF}`）。
#: ★ 批次 325（2026-10-03）：88 → **89** —— `EntityLaser.ShootAngle`（第二条静态行；
#: 形状 31，`optionalArgumentCount = 1`）。
#: ★ 批次 326（2026-10-03）：89 → **90** —— `EntityPlayer:FireTechLaser`（形状 32，尾部 3 个可省，
#: 最后一格 `FloatDefaultOne`）。
#: ★ 批次 330（2026-10-03）：90 → **92** —— `EntityFamiliar:FollowParent` / `AddToFollowers`
#: （两条**无参/返回 void** ⇒ 复用现成的 `EngineCallShape::Void0`，**本批不加形状**；
#: ★ 本批真正的产出是给 `EntityFamiliar` 建了自己的视图元表，否则这两条没有地方挂）。
#: ★ 331~334（2026-10-03）**没有改动这个计数**，理由逐条记下来（省得后人以为漏改）：
#:   * 331 = 纯文档批（交接 + 分诊），不动运行时；
#:   * 332 `EntityPlayer:GetMovementJoystick` = **手写处理器**（引擎返回 `Vector` HFA，
#:     跳板表达不了）⇒ 不进 `EngineMethodRow`；
#:   * 333 `Entity:MultiplyFriction` = **字段数据行**（`FieldKind::FloatMultiplyArg`，
#:     行在 `kFieldApis` 里）⇒ 同样不进本表；
#:   * 334 `EntityPlayer:CheckFamiliar` = **手写处理器**（后两个形参带非 0 缺省值）。
#: ⇒ 到 334 为止仍是 **92**。
#: ★ 批次 335（2026-10-03）：92 → **95** —— 交接第八份 §3「批 A」的三条数据行：
#: `EntityPlayer:ChangePlayerType` / `EntityPlayer:DischargeActiveItem`（共用**本批新开**的形状 33
#: `VoidIntBoolOpt1` = `void(this, i32, bool)`、尾部 1 个可省）与 `Seeds:SetStartSeed`（形状 `Void1`）。
#: ★ 本批**新增一个接收者** `FieldReceipt::Seeds`（= `Game + kGameSeedsObjectOffset`）——
#: 它同时也是"新开一档 receipt"的样本：`ResolveFieldReceipt` 里多一个 `case`，行的另外 6 格不变。
#: ★ 批次 341（2026-10-04）：95 → **97** —— 两条新数据行：
#:   `EntityPlayer:TryRemoveTrinketCostume`（形状 `Void1`）与
#:   `EntityFamiliar:FollowPosition`（**新形状** `VoidVector2Ref`）。
#: ★ 批次 344（2026-10-04）：97 → **98** —— 一条新数据行：
#:   `PathFinder:HasPathToPos`（**新形状** `BoolVector2RefBool`，纯数据、0 代码；
#:   接收者也是本批新开的 `FieldReceipt::PathFinder`）。
#:   ★ 同批的 `EntityPlayer:AnimateCollectible` 是**手写处理器**，**不进这张表**。
#: ★ 批次 388（2026-10-07）：98 → **104** —— `TemporaryEffects`（`EntityPlayer:GetEffects()` 的
#:   返回值）的 6 条**无可选参数**方法落成数据行（`Has*Effect` ×3 用 `Bool1`、`Get*EffectNum` ×3
#:   用 `Int1`；接收者是本批新开的 `FieldReceipt::TemporaryEffects`）。
#:   ★ 同族另有 6 条 `Add*`/`Remove*`（PC 缺省 `true`/`1`，非 0 ⇒ 数据行的"省略=0"表达不了）
#:     与 5 条占位，都是**手写处理器**，**不进这张表**。
EXPECTED_ROW_TOTAL = 104


def shape_arity_table() -> dict[str, int]:
    """`shape` → 该形状要求几个参数。

    **从签名描述符表派生，不再写死**（批次 055 起形状本身是数据）：枚举名与下标的对应关系
    读 `engine_method_api.hpp` 的 `EngineCallShape`，每个形状的参数个数读
    `isaac_api.cpp` 里 `kEngineCallShapes` 的行（每行第一个字段就是参数个数）。
    这样"加一种形状"只要改那两处，门禁自动跟上，不会再出现"门禁与实现说法不一致"。
    """
    header = ROWS_HEADER.read_text(encoding="utf-8")
    enum_block = re.search(
        r"enum class EngineCallShape[^{]*\{(.*?)\n\};", header, re.S)
    if enum_block is None:
        raise AssertionError("engine_method_api.hpp 里找不到 EngineCallShape 枚举")
    names = {}
    for name, index in re.findall(r"(\w+)\s*=\s*(\d+)", enum_block.group(1)):
        names[int(index)] = name

    table = (LUA_DIR / "isaac_api.cpp").read_text(encoding="utf-8")
    table_block = re.search(r"kEngineCallShapes\[\]\s*=\s*\{(.*?)\n\};", table, re.S)
    if table_block is None:
        raise AssertionError("isaac_api.cpp 里找不到 kEngineCallShapes 签名描述符表")
    counts = [int(value) for value in
              re.findall(r"^\s*\{(\d+),\s*\{EngineArgKind::", table_block.group(1), re.M)]

    if len(counts) != len(names):
        raise AssertionError(
            f"签名描述符表有 {len(counts)} 行、枚举有 {len(names)} 个值 —— 两者必须一一对应")
    return {names[index]: counts[index] for index in sorted(names)}

#: 两种行形态都要认（2026-10-03 批次 303 起）：
#:   * 普通行：`{0x…, kXxxOffset, kXxxEntryWord, FieldReceipt::…, EngineCallShape::…, N, …}`
#:     —— "模块基址 + 固定偏移 + 入口指纹"。
#:   * **按 vtable 槽号调用的行**：`{0x…, MakeEngineVtableRowOffset(kXxxSlot), 0, …}`
#:     —— 虚函数，目标运行期才算得出来，**没有入口指纹**（`entryWord` 写 0）。
#:     ★ 不认它的话，这些行对**整张门禁**隐形（"行数对不上""常量没定义"这类检查全都看不到它们）。
ROW_RE = re.compile(
    r"\{\s*0x([0-9A-Fa-f]{8})\s*,\s*(?:MakeEngineVtableRowOffset\((k\w+Slot)\)"
    r"|(k\w+Offset)\s*,\s*(k\w+EntryWord))\s*,\s*(?:0\s*,\s*)?"
    r"FieldReceipt::(\w+)\s*,\s*EngineCallShape::(\w+)\s*,\s*(\d+)\s*,")


def parse_rows() -> list[dict]:
    rows = []
    for path in ROW_FILES:
        text = path.read_text(encoding="utf-8")
        for match in ROW_RE.finditer(text):
            slot_constant, offset_constant, entry_constant = match.group(2), match.group(3), match.group(4)
            rows.append({
                "file": path.name,
                "id": "0x" + match.group(1).upper(),
                "offset_constant": slot_constant or offset_constant,
                "entry_constant": entry_constant,
                "receipt": match.group(5),
                "shape": match.group(6),
                "argument_count": int(match.group(7)),
                #: 这一行是"按 vtable 槽号调用"（虚函数）—— 它的常量是**槽号**、不进签名表。
                "is_vtable": slot_constant is not None,
            })
    return rows


class EngineMethodRowGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = parse_rows()
        cls.catalog_text = CATALOG.read_text(encoding="utf-8")
        cls.constants_text = CONSTANTS.read_text(encoding="utf-8")
        cls.signatures_text = SIGNATURES.read_text(encoding="utf-8")

    def test_row_ids_exist_in_the_catalog(self):
        """行里的 id 必须在目录里能找到 —— 否则这一行永远挂不上任何 API（静默失效）。

        目录行的写法：`{MakeId(ApiDomain::Isaac, 1, 0x0056), …}`，所以这里用
        `MakeId(<域>, 1, 0x…id)` 这个形状去核对（域按行所在的家族不同而不同，不在这里判域）。
        """
        for row in self.rows:
            with self.subTest(row["id"]):
                # 目录行里写的是 `MakeId(域, ownerGroup, 序号)` —— **序号只有低 16 位**，
                # 而数据行里的 id 是**拼好的完整 id**（`域<<24 | ownerGroup<<16 | 序号`，
                # 与绑定表 `{0x0E010056, …}` 同一口径）。所以这里拿低 4 位十六进制去核。
                sequence = row["id"][-4:]
                pattern = re.compile(r"MakeId\(ApiDomain::\w+, 1, 0x" + sequence + r"\)")
                self.assertRegex(self.catalog_text, pattern,
                                 f"{row['id']} 不在目录里 —— 行挂不上任何 API")

    def test_shape_and_argument_count_agree(self):
        """行里的 `argumentCount` 必须与签名描述符表说的**一模一样**。

        不一致时共享处理器会直接报错（不硬调），所以这条门禁是"构建前就拦下来"的那半。
        """
        arity = shape_arity_table()
        for row in self.rows:
            with self.subTest(f"{row['id']}/{row['shape']}"):
                self.assertIn(row["shape"], arity,
                              f"未知形状 {row['shape']}：要么在 EngineCallShape 里加一个下标、"
                              f"并在 kEngineCallShapes 里补一行描述符，要么改用已有形状")
                self.assertEqual(row["argument_count"], arity[row["shape"]],
                                 "形状与参数个数不一致（会按错误的 ABI 调进引擎）")

    def test_row_constants_are_declared_and_registered(self):
        """两个常量都必须**定义**；其中 `k…Offset` 还必须**登记进签名表**。

        签名表只收 `k…Offset`（它按偏移把常量对应到 NRO 里的符号），
        入口指纹常量 `k…EntryWord` 是同一份证据的另一半，不进那张表。
        """
        for row in self.rows:
            constants = [row["offset_constant"]]
            if row["entry_constant"] is not None:
                constants.append(row["entry_constant"])
            for constant in constants:
                with self.subTest(constant):
                    self.assertIn(f"{constant} = ", self.constants_text,
                                  f"{constant} 没在 runtime_constants.hpp 里定义")
            if row["is_vtable"]:
                # ★ 按 vtable 槽号调用的行**不进签名表**：签名表按"偏移 → NRO 符号"建索引，
                #   而这一行给的是**槽号**（同一行在 `Entity` 与 `Entity_NPC` 上是不同的实现）。
                #   ⇒ 它的"证据登记"落在 `runtime_constants.hpp` 的批次 303 段（怎么从 `_ZTV` 读槽号）。
                continue
            with self.subTest(row["offset_constant"]):
                self.assertIn(row["offset_constant"], self.signatures_text,
                              f"{row['offset_constant']} 没登记进 engine_symbol_signatures.json"
                              f"（先跑 tools/gen_engine_symbol_signatures.py）")

    def test_row_ids_never_use_a_hand_written_handler(self):
        """★ 机制的核心不变式：数据行的 id **不许**再挂手写处理器（那会重新占代码段）。"""
        binding_rows = re.findall(r"\{(0x[0-9A-Fa-f]{8}),\s*&\w+\}", self.catalog_text)
        for path in ROW_FILES:
            binding_rows.extend(
                re.findall(r"\{(0x[0-9A-Fa-f]{8}),\s*&\w+\}",
                           path.read_text(encoding="utf-8")))
        hand_written = {value.upper() for value in binding_rows}
        offenders = sorted(row["id"] for row in self.rows if row["id"] in hand_written)
        self.assertEqual(offenders, [],
                         f"这些 id 既在数据行里、又有手写处理器：{offenders} —— "
                         f"删掉手写那一份，否则每个 API 还是占 ≈490 字节代码")

    def test_row_total_is_pinned(self):
        self.assertEqual(len(self.rows), EXPECTED_ROW_TOTAL,
                         "数据行增减了 —— 改这里要写明本批加了什么、为什么")

    def test_the_row_struct_is_still_sixteen_bytes(self):
        header = ROWS_HEADER.read_text(encoding="utf-8")
        self.assertIn("static_assert(sizeof(EngineMethodRow) == 16", header,
                      "16 字节是这套机制的成本前提，改动它要重新做成本核算")
        for field in ("id", "offset", "entryWord", "receipt", "shape", "argumentCount",
                      "probeBit"):
            self.assertIn(field, header, f"行结构体里应有 {field}")

    def test_one_shared_handler_serves_every_row(self):
        """共享处理器必须只有**一份实现**，而且绑定循环真的在用它。"""
        implementations = []
        for path in LUA_DIR.glob("*.cpp"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"^int EngineMethodHandler\(lua_State\* state\)", text, re.M):
                implementations.append(path.name)
        self.assertEqual(implementations, ["isaac_api.cpp"],
                         f"共享处理器应当只有一份实现，实际：{implementations}")
        binding = BINDING.read_text(encoding="utf-8")
        self.assertIn("EngineMethodHandler", binding,
                      "绑定循环没有接上共享处理器 ⇒ 数据行根本挂不上去")


if __name__ == "__main__":
    unittest.main()
