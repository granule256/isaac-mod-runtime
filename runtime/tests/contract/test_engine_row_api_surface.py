"""契约：**引擎方法数据行**的 Lua 名字面 —— 每个数据行到底挂了哪条 API、用什么形状。

## 为什么要有它（2026-09-30 批次 239）

`test_engine_method_rows.py` 管的是**机制**（16 字节不变式、id 在目录里、形状与参数个数自洽），
但它全程按 **id / 常量名**核对，**从不提 Lua 名字**。后果有两条，都在 2026-09-30 暴露：

1. **完成定义门禁（`tools/api_definition_of_done.py`）的"边界判据"栏要求
   "判据文件里真的提到这条 API"** —— 数据行类 API 当时**一个可指的判据文件都没有**，
   于是 46 条（批次 238 的 28 条 + 239 的 18 条）全部缺台账条、门禁一直是红的，
   而 238 的门禁清单里**没有这一项**，所以没人发现。
2. 反过来说，**"这条数据行对应哪条 Lua API"此前没有任何地方被钉住**：id 的低 16 位对不上、
   或形状被改成另一种，机制测试全绿、而模组看到的语义已经变了。

所以本文件把那条对应关系**按名字**写下来（表就是判据），并核对三件事：
   ① 每个名字都在 catalog 里、owner 对得上；
   ② 每个名字**恰好**有一条数据行，且那条行的形状与本表写的一致；
   ③ 行的参数个数 == 形状声明的个数，且**允许的参数个数区间**就是
      `[个数 - 尾部可省数, 个数]`（这一格是边界判据：模组少传尾部参数时，
      共享处理器按"省略即 0"放行；多传则报错 —— 报错会摘掉整条回调，所以区间必须精确）。

★ 本表**故意逐条写死**（与 `EXPECTED_ROW_TOTAL` 同一性质）：加一条数据行必须在这里补一行，
  否则门禁红。这是"按名字钉住"的唯一可行做法 —— 从源码解析出来的名字集合，
  在完成定义门禁眼里等于"文件里没提到这条 API"。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # runtime/tests/contract/<本文件> ⇒ 仓库根
LUA_DIR = ROOT / "runtime" / "src" / "interfaces" / "lua"
HEADER = LUA_DIR / "engine_method_api.hpp"
CATALOG = LUA_DIR / "api_catalog.cpp"
DESCRIPTOR = LUA_DIR / "api_descriptor.hpp"

#: 承载数据行的家族 TU。
ROW_FILES = ("isaac_api.cpp", "game_api.cpp", "remaining_api.cpp", "music_api.cpp")

#: `Lua API 名 → 数据行用的形状`。**加数据行必须在这里补一行。**
DATA_ROW_SURFACE: dict[str, str] = {
    # Entity 族
    "Entity:IsActiveEnemy": "BoolOpt1",
    "Entity:IsBoss": "Bool0",
    "Entity:IsEnemy": "Bool0",
    "Entity:IsFlying": "Bool0",
    "Entity:Kill": "Void0",
    "Entity:Remove": "Void0",
    "Entity:Update": "Void0",
    # ★ 批次 330（2026-10-03）：`EntityFamiliar` 视图的两条（同一批建的视图元表）。
    #   都是**无参、返回 void** ⇒ 复用现成的 `EngineCallShape::Void0`（本批没有新形状）。
    #   接收者是本批新开的 `FieldReceipt::EntityFamiliar`（精确 vptr + 类型）。
    "EntityFamiliar:FollowParent": "Void0",
    "EntityFamiliar:AddToFollowers": "Void0",
    # EntityPlayer 族
    "EntityPlayer:AddBrokenHearts": "Void1",
    "EntityPlayer:AddCard": "Void1",
    "EntityPlayer:AddCoins": "Void1",
    "EntityPlayer:AddEternalHearts": "Void1",
    "EntityPlayer:AddHearts": "VoidIntBoolOpt1",
    "EntityPlayer:AddNullCostume": "VoidNullId1",
    "EntityPlayer:AddTrinket": "VoidIntBoolDefaultTrueOpt1",
    "EntityPlayer:AnimateHappy": "Void0",
    "EntityPlayer:AnimateSad": "Void0",
    "EntityPlayer:CanPickRedHearts": "Bool0",
    "EntityPlayer:EvaluateItems": "Void0",
    "EntityPlayer:GetBlackHearts": "Int0",
    "EntityPlayer:GetCard": "Int1",
    "EntityPlayer:GetExtraLives": "Int0",
    "EntityPlayer:GetGlyphOfBalanceDrop": "Ref2U32Pair",
    "EntityPlayer:GetPill": "Int1",
    "EntityPlayer:GetZodiacEffect": "Int0",
    "EntityPlayer:HasPlayerForm": "Bool1",
    "EntityPlayer:NeedsCharge": "Bool1",
    "EntityPlayer:Revive": "Void0",
    "EntityPlayer:SetActiveCharge": "Void2",
    "EntityPlayer:SetCard": "Void2",
    "EntityPlayer:SetShootingCooldown": "Void1",
    "EntityPlayer:TryRemoveNullCostume": "VoidNullId1",
    "EntityPlayer:TryRemoveTrinket": "Bool1",
    "EntityPlayer:UseCard": "Void2",
    # Game 族
    "Game:AddDevilRoomDeal": "Void0",
    "Game:ChangeRoom": "Void2",
    "Game:GetGreedBossWaveNum": "Int0",
    "Game:StartRoomTransition": "VoidIntIntIntHandleInt",
    "Game:Update": "Void0",
    # Level 族
    "Level:AddCurse": "VoidIntBool",
    "Level:GetPlanetariumChance": "Float0",
    "Level:GetRandomRoomIndex": "IntBoolInt",
    "Level:RemoveCurses": "Void1",
    "Level:SetNextStage": "Void0",
    "Level:SetStage": "Void2",
    "Level:Update": "Void0",
    "Level:UpdateVisibility": "Void0",
    # Room 族
    "Room:DestroyGrid": "BoolIntBoolBool",
    "Room:GetGridCollision": "Int1",
    "Room:GetRoomConfigStage": "Int0",
    "Room:HasCurseMist": "Bool0",
    "Room:IsAmbushActive": "Bool0",
    "Room:IsCurrentRoomLastBoss": "Bool0",
    "Room:PlayMusic": "Void0",
    "Room:RemoveDoor": "Void1",
    "Room:RemoveGridEntity": "VoidIntIntBool",
    "Room:SetGridPath": "BoolIntIntInt",
    "Room:SpawnClearAward": "Void0",
    "Room:TurnGold": "Void0",
    "Room:Update": "Void0",
    # MusicManager 族
    "MusicManager:DisableLayer": "VoidIntOpt1",
    "MusicManager:EnableLayer": "VoidIntBoolOpt2",
    "MusicManager:GetQueuedMusicID": "Int0",
    "MusicManager:IsLayerEnabled": "BoolIntOpt1",
    "MusicManager:PitchSlide": "VoidFloat1",
    "MusicManager:ResetPitch": "Void0",
    "MusicManager:VolumeSlide": "VoidFloatFloatOpt1",
    # ---- 批次 252（2026-10-01）：5 条新数据行（3 条用了本批新增的形状）----
    "MusicManager:Queue": "Void1",
    "MusicManager:Crossfade": "VoidIntFloatOpt1",
    "Game:ShowHallucination": "Void2",
    "Room:SpawnGridEntity": "BoolIntIntIntIntInt",
    "EntityPlayer:RemoveCollectible": "VoidIntBoolIntBoolOpt3",
    # ---- 批次 253：带 `Vector2 const&` 参数的两条（引用 ⇒ 指针，不需要扩跳板）----
    "Room:IsPositionInRoom": "BoolVector2RefFloat",
    "Game:CharmFart": "VoidVector2RefFloatHandle",
    # ---- 批次 254（2026-10-01）：语料 API 恢复（ItemPool 接收者 + 5 条数据行）----
    # `Game:MoveToRandomRoom`：`(bool, i32, EntityPlayer*)`（三种种类都已在表里）。
    "Game:MoveToRandomRoom": "VoidBoolIntHandle",
    # `ItemPool:RemoveCollectible`：引擎 3 格、PC 文档与语料都只 1 个 ⇒ 尾部 2 个可省。
    "ItemPool:RemoveCollectible": "BoolIntBoolBoolOpt2",
    # ---- `EntityPlayer` 三条零成本数据行（工作清单误记为 `needs_new_receiver`）----
    "EntityPlayer:AddKeys": "Void1",
    "EntityPlayer:AddGoldenKey": "Void0",
    "EntityPlayer:AddGoldenBomb": "Void0",
    # ---- 批次 285 / 286（2026-10-02）：三条引擎方法数据行 ----
    # ★ **那两批漏登记了这张表**，`test_the_surface_covers_every_data_row` 一直红着
    # （两条 `Morph` 从 285 起、`IsVulnerableEnemy` 从 286 起）——本批（287）补记。
    # 教训：加一条 `EngineMethodRow` 要**同时**改三处 —— `EXPECTED_ROW_TOTAL`（几条）、
    # 本表（叫什么名字、什么形状）、以及那一条的完成定义台账。285/286 只改了第一处。
    # （这两批的定向门禁清单里都没有本文件 ⇒ 同"第五道门禁"那个踩过两次的坑。）
    "EntityNPC:Morph": "BoolIntIntIntInt",
    "EntityPickup:Morph": "VoidIntIntIntBoolBoolBoolOpt3",
    "Entity:IsVulnerableEnemy": "Bool0",
    # ---- 批次 288（2026-10-02）：`EntityPlayer:GetMovementDirection`（`Int0`）。
    # ★ 本批另外两条（`GetHeadDirection` / `GetFireDirection`）是**字段读取型数据行**，
    #   不进本表 —— 本表只登记 `EngineMethodRow`。
    "EntityPlayer:GetMovementDirection": "Int0",
    # ---- 批次 303（2026-10-03）：**第一批"按 vtable 槽号调用"的引擎方法行** ----
    # `offset` 最高位置 1 = 虚调用、低 31 位 = 槽号（`engine_method_api.hpp` 的
    # `kEngineVtableRowFlag`）；`entryWord` 写 0（目标运行期才知道）。形状沿用既有的 `Bool0`。
    # ★ 本表的 `ROW_RE` 同批也扩了 —— 不认新形态的话，这两行会**绕过本门禁**
    #   （与 285/286 那次"加了行没登记本表"是同一类盲点）。
    "Entity:CanShutDoors": "Bool0",
    "EntityNPC:CanShutDoors": "Bool0",
    # ---- 批次 304（2026-10-03）：`GridEntity` 的两条虚函数（同机制）----
    "GridEntity:Destroy": "BoolOpt1",
    "GridEntity:PostInit": "Void0",
    # ---- 批次 321（2026-10-03）：`GridEntity:Update()`（槽 3，与上面两条同机制）----
    "GridEntity:Update": "Void0",
    # ---- 批次 324（2026-10-03）：★ 第一条**静态调用**（挂在全局 `EntityNPC` 表上）----
    "EntityNPC:ThrowSpider": "StaticVoidVector2RefHandleVector2RefBoolFloat",
    # ---- 批次 325（2026-10-03）：第二条静态行（挂在全局 `EntityLaser` 表上）----
    "EntityLaser:ShootAngle": "StaticIntVector2RefFloatIntVector2RefHandleBool",
    # ---- 批次 326（2026-10-03）：★ 第一次用 `FloatDefaultOne`（缺省是 1 的浮点）----
    "EntityPlayer:FireTechLaser": "Vector2RefIntVector2RefBoolBoolHandleFloatOpt3",
    # ---- 批次 335（2026-10-03）：交接第八份 §3「批 A」的三条 ----
    # 前两条共用**本批新开的**形状 33 `VoidIntBoolOpt1`（`void(this, i32, bool)`、尾部 1 个可省）：
    # 契约各写 1 个形参、引擎符号都是 2 格 ⇒ 按符号取、省略那一格保持 0。
    #   * `ChangePlayerType(PlayerType)`：那个 `bool` 对语料**惰性**（分支要求 `PlayerType ∈ {16,17}`，
    #     语料传 `PLAYER_EVE`(5)）；
    #   * `DischargeActiveItem(ActiveSlot = SLOT_PRIMARY)`：那个 `bool` **确实参与分支** ⇒
    #     取 0 是"契约只暴露 1 个形参 + vanilla 缺省一律是 0"这条口径（真机项已登记）。
    "EntityPlayer:ChangePlayerType": "VoidIntBoolOpt1",
    "EntityPlayer:DischargeActiveItem": "VoidIntBoolOpt2",
    # 第三条在 `game_api.cpp` 的 `kSeedsEngineRows` 里（接收者不同）：形状复用现成的 `Void1`，
    # 接收者是本批新开的 `FieldReceipt::Seeds`（= `Game + kGameSeedsObjectOffset`）。
    "Seeds:SetStartSeed": "VoidSeed1",
    # ---- 批次 341（2026-10-04）：两条引擎方法行（四条 API 里的后两条）----
    # `EntityPlayer:TryRemoveTrinketCostume(TrinketType)`：真身是同族 `TryRemoveCostume` 的
    # trinket 重载 @ `0x2A25B0`（`void(this, i32)`）⇒ 复用现成的 `Void1`。
    "EntityPlayer:TryRemoveTrinketCostume": "Void1",
    # `EntityFamiliar:FollowPosition(Vector Pos)`：真身 `follow_position(Vector2 const&) @ 0xAFCC0`
    # ⇒ **本批新开的**形状 34 `VoidVector2Ref`（`void(this, Vector2 const&)`、无缺省）。
    # ★★ 本条**推翻批次 331 的负结果**（"函数体从不读实参"）—— 见 `runtime_constants.hpp` 批次 341 段。
    "EntityFamiliar:FollowPosition": "VoidVector2Ref",
    # ---- 批次 344（2026-10-04）：一条引擎方法行 + 一个**全新 owner** ----
    # `PathFinder:HasPathToPos(Vector Pos, boolean IgnorePoop)`：真身
    # `NPCAI_Pathfinder::HasPathToPos(Vector2 const&, bool) const @ 0x42F6CC`
    # ⇒ **本批新开的**形状 35 `BoolVector2RefBool`（`bool(this, Vector2 const&, bool)`、
    # 两格都必填 ⇒ 无缺省）。接收者也是本批新开的 `FieldReceipt::PathFinder`。
    # ★ 同批的 `EntityPlayer:AnimateCollectible` 是**手写处理器**，**不进这张表**。
    "PathFinder:HasPathToPos": "BoolVector2RefBool",
    # ---- 批次 388（2026-10-07）：`TemporaryEffects`（`EntityPlayer:GetEffects()` 的返回值）----
    # 6 条**无可选参数**的方法落成数据行，全部复用**现成形状**（本批没有新形状），接收者是
    # 本批新开的 `FieldReceipt::TemporaryEffects`（校验句柄类型 + 玩家 vptr，再取 `player + 0x18D8`）。
    # 真身 = `Repentance.nro` 动态符号表里的 `TemporaryEffects::*`（见 `runtime_constants.hpp` 的
    # TemporaryEffects 段；那一族入口指纹很弱，只能证明"模块基址对"）。
    # ★ 同族的 6 条 `Add*`/`Remove*`（PC 缺省 true/1 ⇒ 数据行的"省略=0"表达不了）与 5 条占位
    #   都是**手写处理器**，**不进这张表**。
    "TemporaryEffects:HasCollectibleEffect": "Bool1",
    "TemporaryEffects:HasTrinketEffect": "Bool1",
    "TemporaryEffects:HasNullEffect": "Bool1",
    "TemporaryEffects:GetCollectibleEffectNum": "Int1",
    "TemporaryEffects:GetTrinketEffectNum": "Int1",
    "TemporaryEffects:GetNullEffectNum": "Int1",
}

#: 两种行形态都要认（2026-10-03 批次 303 起）：普通行 + **按 vtable 槽号调用的行**。
#: 分组：1=id、6=形状、7=参数个数（V表那一支"占"了中间的组，所以后两个组号往后挪了一位）。
ROW_RE = re.compile(
    r"\{\s*0x([0-9A-Fa-f]{8})\s*,\s*(?:MakeEngineVtableRowOffset\((k\w+Slot)\)"
    r"|(k\w+Offset)\s*,\s*(k\w+EntryWord))\s*,\s*(?:0\s*,\s*)?"
    r"FieldReceipt::(\w+)\s*,\s*EngineCallShape::(\w+)\s*,\s*(\d+)\s*,")
CATALOG_RE = re.compile(
    r"MakeId\(ApiDomain::(\w+),\s*\d+,\s*0x([0-9A-Fa-f]+)\)\s*,\s*ApiDomain::\w+,\s*"
    r'"(\w+)",\s*"(\w+)"')


def domain_values() -> dict[str, int]:
    """`ApiDomain` 枚举名 → 数值。真值源是 `api_descriptor.hpp`（不在这里抄一份）。"""
    header = DESCRIPTOR.read_text(encoding="utf-8")
    block = re.search(r"enum class ApiDomain[^{]*\{(.*?)\n\};", header, re.S)
    assert block is not None, "api_descriptor.hpp 里找不到 ApiDomain 枚举"
    return {name: int(value) for name, value in re.findall(r"(\w+)\s*=\s*(\d+)", block.group(1))}


def parse_catalog() -> dict[tuple[int, int], str]:
    """`（域值, 域内序号）` → `Owner:Name`。

    ★ 不能只用 4 位序号做键：**序号是域内编号**，`0x000F` 在 `Game` 域是 `Game:Update`、
    在 `Room` 域是 `Room:GetRoomConfigStage` —— 按序号单键会把它们互相覆盖，
    于是"这条数据行对应哪条 API"会随机指向另一个域的同号条目（本批第一版真踩了）。
    """
    domains = domain_values()
    out: dict[tuple[int, int], str] = {}
    for match in CATALOG_RE.finditer(CATALOG.read_text(encoding="utf-8")):
        domain = domains.get(match.group(1))
        if domain is None:
            continue
        out[(domain, int(match.group(2), 16))] = f"{match.group(3)}:{match.group(4)}"
    return out


def row_key(row: dict) -> tuple[int, int]:
    """数据行的 id → `（域值, 域内序号）`：id = `域<<24 | ownerGroup<<16 | 序号`。"""
    value = int(row["id"], 16)
    return (value >> 24) & 0xFF, value & 0xFFFF


def parse_rows() -> list[dict]:
    rows = []
    for name in ROW_FILES:
        text = (LUA_DIR / name).read_text(encoding="utf-8")
        for match in ROW_RE.finditer(text):
            rows.append({
                "file": name,
                "id": match.group(1).upper(),
                "shape": match.group(6),
                "argument_count": int(match.group(7)),
            })
    return rows


def parse_shapes() -> dict[str, tuple[int, int]]:
    """形状名 → （参数个数, 尾部可省个数）。

    ★ 逐行切分而不是一条大正则：形状行是**多行**的（参数数组换行），
    用 `.*?` + DOTALL 会把相邻两行粘到一起、把"尾部可省"读到下一行去
    （批次 239 第一版就是这么写的，被本文件自己的反例测试抓出来）。
    """
    header = HEADER.read_text(encoding="utf-8")
    block = re.search(r"enum class EngineCallShape[^{]*\{(.*?)\n\};", header, re.S)
    assert block is not None, "engine_method_api.hpp 里找不到 EngineCallShape 枚举"
    names = {int(index): name for name, index in re.findall(r"(\w+)\s*=\s*(\d+)", block.group(1))}

    table = (LUA_DIR / "isaac_api.cpp").read_text(encoding="utf-8")
    body = re.search(r"kEngineCallShapes\[\]\s*=\s*\{(.*?)\n\};", table, re.S)
    assert body is not None, "isaac_api.cpp 里找不到 kEngineCallShapes"

    parsed: list[tuple[int, int]] = []
    for chunk in re.split(r"\n\s*\{", body.group(1)):
        head = re.match(r"(\d+),\s*\{EngineArgKind::", chunk)
        if head is None:
            continue
        tail = re.search(r"IntArgumentGuard::\w+,\s*(\d+),", chunk)
        if tail is None:
            continue
        parsed.append((int(head.group(1)), int(tail.group(1))))

    assert len(parsed) == len(names), (
        f"形状描述符表解析出 {len(parsed)} 行、枚举有 {len(names)} 个值 —— 必须一一对应")
    return {names[index]: parsed[index] for index in sorted(names)}


class EngineRowApiSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = parse_catalog()
        cls.rows = parse_rows()
        cls.shapes = parse_shapes()

    def _row_for(self, api: str) -> dict | None:
        for row in self.rows:
            if self.catalog.get(row_key(row)) == api:
                return row
        return None

    def test_every_listed_api_exists_in_the_catalog(self):
        """表里的名字必须在目录里，且 owner 就是名字里的那个。"""
        published = set(self.catalog.values())
        for api in sorted(DATA_ROW_SURFACE):
            with self.subTest(api):
                self.assertIn(api, published,
                              f"{api} 不在 api_catalog.cpp 里 —— 数据行挂不上任何 API")

    def test_every_listed_api_has_exactly_one_data_row_with_the_declared_shape(self):
        """每个名字恰好一条数据行，且那条行的形状与表里写的一致。"""
        for api, shape in sorted(DATA_ROW_SURFACE.items()):
            with self.subTest(api):
                row = self._row_for(api)
                self.assertIsNotNone(row, f"{api} 没有对应的数据行")
                self.assertEqual(row["shape"], shape,
                                 f"{api} 的形状被改了：表里写 {shape}、源码里是 {row['shape']}")

    def test_row_shapes_are_registered(self):
        for api, shape in sorted(DATA_ROW_SURFACE.items()):
            with self.subTest(api):
                self.assertIn(shape, self.shapes, f"{shape} 不是描述符表里的形状")

    def test_declared_argument_count_matches_the_shape(self):
        for api in sorted(DATA_ROW_SURFACE):
            with self.subTest(api):
                row = self._row_for(api)
                expected, _ = self.shapes[row["shape"]]
                self.assertEqual(row["argument_count"], expected,
                                 f"{api}：行写 {row['argument_count']} 个参数、形状要求 {expected} 个")

    def test_the_optional_tail_is_the_only_accepted_range(self):
        """★ 边界判据：容许的参数个数区间 == `[个数 - 尾部可省数, 个数]`。

        少传尾部参数时共享处理器按"省略即 0"放行（`EngineMethodHandler` 里
        `minimumArguments = maximumArguments - static_cast<int>(shape.optionalArgumentCount)`）；
        多传则**报错** —— 而报错会摘掉整条模组回调，所以这个区间必须精确。
        这里核对两件事：① 形状表里的"尾部可省数"不大于参数总数（否则区间是空的）；
        ② 共享处理器真的按这一格算最小值（防"改了形状表、处理器没跟上"）。
        """
        handler = (LUA_DIR / "isaac_api.cpp").read_text(encoding="utf-8")
        self.assertIn(
            "const int minimumArguments = maximumArguments - "
            "static_cast<int>(shape.optionalArgumentCount);",
            handler,
            "共享处理器没有按 `optionalArgumentCount` 算最小参数个数 —— "
            "那么形状表里的'尾部可省'就是一纸空文")

        optional_shapes = [name for name, (_, optional) in self.shapes.items() if optional != 0]
        self.assertTrue(optional_shapes, "一个'尾部可省'的形状都没有，这条判据失去意义")
        for shape in sorted(optional_shapes):
            count, optional = self.shapes[shape]
            with self.subTest(shape):
                self.assertLessEqual(optional, count,
                                     f"{shape}：尾部可省数 {optional} 大于参数总数 {count}")

    def test_the_surface_covers_every_data_row(self):
        """反向：源码里**每条**数据行都必须在表里出现（漏登记 = 这条 API 无人钉住）。"""
        listed = set(DATA_ROW_SURFACE)
        on_disk = []
        for row in self.rows:
            api = self.catalog.get(row_key(row))
            if api is not None:
                on_disk.append(api)
        unlisted = sorted(set(on_disk) - listed)
        self.assertEqual(unlisted, [],
                         f"这些数据行没有登记进 DATA_ROW_SURFACE：{unlisted}")


if __name__ == "__main__":
    unittest.main()
