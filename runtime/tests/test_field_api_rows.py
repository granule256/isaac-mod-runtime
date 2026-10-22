"""字段读取型 API「数据行」机制的门禁（**不需要设备**）。

这套机制的意义是**成本**：一个"读引擎字段并返回"的方法手写要 236–312 字节代码
（反汇编实测），写成数据行则是 **0 字节代码 + 16 字节只读数据**，代价是共享处理器
`FieldApiHandler` 的一次性 ~1 KB。所以它必须被钉住三件事：

1. **行本身合法**：`id` 在 catalog 里存在且 owner 对得上；`id` 不重复；不与手写绑定表撞 id
   （撞了就会出现"同一方法挂两次、以手写为准"这种难查的现象）；
2. **偏移有出处**：行里引用的必须是 `runtime_constants.hpp` 里的**具名常量**，
   不能在实现里现编一个偏移 —— 这条与地基二期"只有有证据的偏移才能进 API"一致；
3. **行真的被挂上**：`AttachOwnerMethods` 必须收到那张行表，否则方法会静默消失。
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REMAINING_API = (ROOT / "runtime" / "src" / "interfaces" / "lua"
                 / "remaining_api.cpp")
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
GAME_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "game_api.cpp"
MUSIC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "music_api.cpp"
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
BINDING = ROOT / "runtime" / "src" / "interfaces" / "lua" / "owner_binding.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def catalog_entries() -> dict[int, tuple[str, str]]:
    """`catalog id -> (owner, name)`（id 按 `MakeId(domain, group, low)` 的打包规则算）。

    `MakeId` 的位布局在 `api_catalog.cpp` 顶部：`domain << 24 | group << 16 | low`。
    """
    #: ★ 批次 305（2026-10-03）：补上 `Music`（= `ApiDomain::Music` = `0x06`）——
    #: `MusicManager` 的三条字段行（`Disable`/`Enable`/`IsEnabled`）住在 `music_api.cpp`，
    #: 域字节是 `0x06`；**字典里没有它时，那些行的 id 会"查不到"、被误判成"不在 catalog 里"**。
    #: （取值真值源是 `api_descriptor.hpp` 的 `enum class ApiDomain`，别在这里另立一份。）
    domain_bits = {
        "Global": 0x01, "Isaac": 0x0E, "Game": 0x02, "Level": 0x03, "Room": 0x04,
        "Music": 0x06,
    }
    entries: dict[int, tuple[str, str]] = {}
    pattern = re.compile(
        r"\{MakeId\(ApiDomain::(\w+),\s*(\d+),\s*0x([0-9A-Fa-f]+)\),\s*ApiDomain::\w+,\s*"
        r"\"(\w+)\",\s*\"(\w+)\"")
    for match in pattern.finditer(read(CATALOG)):
        domain, group, low, owner, name = match.groups()
        top = domain_bits.get(domain, 0)
        identifier = (top << 24) | (int(group) << 16) | int(low, 16)
        entries[identifier] = (owner, name)
    return entries


def constant_values() -> dict[str, int]:
    values: dict[str, int] = {}
    pattern = re.compile(r"inline constexpr uintptr_t (k\w+Offset)\s*=\s*(0x[0-9A-Fa-f]+)")
    for match in pattern.finditer(read(CONSTANTS)):
        values[match.group(1)] = int(match.group(2), 16)
    return values


#: 行表所在的位置与它们各自允许的 owner（**家族的行表住在自己的 TU 里**，契约门禁也这么要求）。
ROW_TABLES = (
    # ★ 批次 296（2026-10-03）：`Entity` 这一档多一个 owner `EntityNPC` ——
    #   `EntityNPC` 视图是批次 285 建的（`Entity:ToNPC()` 压 `kEntityNPCMetatable`），
    #   而本批是**第一次**把字段行挂到它上面（`GetChampionColorIdx` / `GetBossColorIdx`）。
    #   两条的接收者仍是 `FieldReceipt::Entity`（`CheckEntityHandle` 早认这张元表）。
    (ISAAC_API, "kFieldApis",
     {"Entity": {"Entity", "EntityPlayer", "EntityPickup", "EntityNPC", "EntityLaser"},
      "EntityPlayer": {"EntityPlayer"},
      "ItemConfigItem": {"ItemConfig_Item"}}),
    (REMAINING_API, "kLevelFieldApis", {"Level": {"Level"}}),
    # 批次 297（2026-10-03）：`Game` 族的**第一张**字段行表（此前 `Game` 一条都没有）——
    # `Game:GetStateFlag(int Flag)`。它用 `FieldReceipt::Level`（枚举注释里本来就写着
    # "`Game`/`Level`（引擎里 Level 内嵌在 Game 起始处，解析链同一条）"⇒ 两者同一地址），
    # 所以这里允许的 owner 是 `Level` 那一档的 `Game`。
    (GAME_API, "kGameFieldApis", {"Level": {"Game"}}),
    # 批次 289（2026-10-02）：`Room` 的位置类表（`GetTopLeftPos` / `GetBottomRightPos`）。
    (REMAINING_API, "kRoomFieldApis", {"Room": {"Room"}}),
    # ★ 批次 305（2026-10-03）：`MusicManager` 的字段行表（第三条数据行表**形态**）——
    # `Disable`/`Enable`/`IsEnabled` 三条落在 `Music`（`Manager` 内嵌子对象）的同一个字节上。
    # 接收者是既有的 `FieldReceipt::Music`（批次 239 立的）。
    (MUSIC_API, "kMusicFieldApis", {"Music": {"MusicManager"}}),
    # ★ 批次 308（2026-10-03）：`GridEntity` 的字段行表（`SetType`）——
    # 接收者是既有的 `FieldReceipt::GridEntity`（批 304 开的，栈上那个句柄）。
    # 它与 `kGridEntityHandlers` / `kGridEntityEngineRows` 同住在 `remaining_api.cpp`。
    (REMAINING_API, "kGridEntityFieldApis", {"GridEntity": {"GridEntity"}}),
)


def field_rows() -> list[dict]:
    """所有字段读取型行表的每一行（解析字段而不是执行 C++）。"""
    rows: list[dict] = []
    for path, table_name, _owners in ROW_TABLES:
        rows.extend(_rows_of(path, table_name))
    return rows


def _rows_of(path, table_name: str) -> list[dict]:
    text = read(path)
    table = re.search(r"constexpr FieldApiRow " + table_name + r"\[\] = \{(.*?)\n\};", text, re.S)
    if table is None:
        return []
    rows: list[dict] = []
    offset2 = r"(?:static_cast<std::uint32_t>\(\s*)?(k\w+Offset|0x[0-9A-Fa-f]+|\d+)\s*\)?"
    pattern = (r"\{\s*(0x[0-9A-Fa-f]+)\s*,\s*(k\w+Offset)\s*,\s*"
               + offset2 + r"\s*,\s*FieldKind::(\w+)\s*,\s*FieldMissing::(\w+)\s*,"
               r"\s*FieldReceipt::(\w+)\s*,\s*(0x[0-9A-Fa-f]+|\d+)\s*\}")
    for match in re.finditer(pattern, table.group(1)):
        rows.append({
            "_table": table_name,
            "id": int(match.group(1), 16),
            "offset_name": match.group(2),
            "offset2": match.group(3),
            "kind": match.group(4),
            "missing": match.group(5),
            "receipt": match.group(6),
            "probe": match.group(7),
        })
    return rows


class FieldApiRowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = field_rows()
        cls.catalog = catalog_entries()
        cls.constants = constant_values()

    def test_the_table_is_not_empty_and_parses(self):
        """行表必须真的解析出内容 —— 解析器失效会让下面几条"全绿但什么都没查"。"""
        self.assertGreaterEqual(len(self.rows), 4, f"只解析到 {len(self.rows)} 行")

    #: 接收者族 → 允许的 catalog owner（按"行所在的那张表"取，见 `ROW_TABLES`）。
    #: 批次 289 加 `Room`：`receipt` 是**算出来的**（解析"当前房间"），不从栈上取接收者，
    #: 所以它只服务 `owner == "Room"` 的目录行。
    OWNERS_BY_RECEIPT = {
        # ★ 批次 296：`EntityNPC` 是本档的**第四个**允许 owner（见 `ROW_TABLES` 的注释）——
        #   `Entity`/`EntityPlayer`/`EntityPickup` 之外，`EntityNPC` 视图上的字段行
        #   （`GetChampionColorIdx` / `GetBossColorIdx`）同样是"从栈上取实体句柄"。
        "Entity": {"Entity", "EntityPlayer", "EntityPickup", "EntityNPC", "EntityLaser"},
        "EntityPlayer": {"EntityPlayer"},
        "ItemConfigItem": {"ItemConfig_Item"},
        # 批次 297：`Level` 这一档多一个 owner `Game` —— `FieldReceipt::Level` 解析出来的就是
        # `Game*`（Level 内嵌在 Game 起始处），所以 `Game:GetStateFlag` 与 `Level:GetStateFlag`
        # 用的是同一条解析链、同一份判据。
        "Level": {"Level", "Game"},
        "Room": {"Room"},
        # 批次 290：`RoomConfigData` 的接收者是**算出来的**（当前房间 → 描述符 → 房间配置对象），
        # 同样不从栈上取 ⇒ 也只服务 `owner == "Room"` 的目录行。
        "RoomConfigData": {"Room"},
        # 批次 291：`RoomDescriptor` 的接收者也是**算出来的**（当前房间 → `Room+0x8`，一跳），
        # 服务"字段住在描述符上"的 `Room:` 方法（`IsAmbushDone` / `HasWaterPits`）。
        "RoomDescriptor": {"Room"},
        # ★ 批次 305：`Music` 的接收者也是**算出来的**（`Manager + kManagerMusicOffset`，批 239），
        # 只服务 `owner == "MusicManager"` 的目录行。
        "Music": {"MusicManager"},
        # ★ 批次 308：`GridEntity` 的接收者**从栈上取**（`Room:GetGridEntity(i)` 交回的句柄，
        # 与 `GetType`/`GetVariant` 那一族手写处理器同一份存活判据）⇒ 只服务 `owner == "GridEntity"`。
        "GridEntity": {"GridEntity"},
    }

    def test_every_row_id_exists_in_the_catalog_with_the_right_owner(self):
        self.assertTrue(self.catalog, "没有解析到 catalog 条目")
        for row in self.rows:
            with self.subTest(row=hex(row["id"])):
                self.assertIn(row["id"], self.catalog,
                              f"{hex(row['id'])} 不在 catalog 里 ⇒ 这一行永远不会被挂上")
                owner, _name = self.catalog[row["id"]]
                allowed = self.OWNERS_BY_RECEIPT[row["receipt"]]
                self.assertIn(owner, allowed,
                              f"行说接收者是 {row['receipt']}，catalog 里的 owner 却是 {owner}")

    def test_ids_are_unique_within_the_table(self):
        ids = [row["id"] for row in self.rows]
        self.assertEqual(len(ids), len(set(ids)), "行表里有重复 id")

    def test_row_ids_do_not_collide_with_hand_written_bindings(self):
        """同一个 id 既在行表又在手写绑定表里 ⇒ 手写优先、行被静默忽略。

        这种"改了行却没生效"的现象很难查，所以直接禁掉：迁移一个方法就把手写那行删掉。
        """
        hand_written = set(int(value, 16) for value in re.findall(
            r"\{\s*(0x0E01[0-9A-Fa-f]{4})\s*,\s*&(?:EntityPlayer|ItemConfigItem)\w+\s*\}",
            read(ISAAC_API)))
        overlap = sorted(set(row["id"] for row in self.rows) & hand_written)
        self.assertEqual(overlap, [], f"这些 id 同时挂在两处：{[hex(v) for v in overlap]}")

    def test_offsets_are_named_constants_not_magic_numbers(self):
        """偏移必须引用 `runtime_constants.hpp` 里的具名常量（有出处），不许写字面量。"""
        for row in self.rows:
            with self.subTest(row=hex(row["id"])):
                self.assertIn(row["offset_name"], self.constants,
                              f"{row['offset_name']} 不在 runtime_constants.hpp 里")

    #: 每个接收者上"偏移的合理上界"——用于抓"十进制/十六进制抄混"这类明显越界。
    #: ★ 2026-10-03（批次 294）：原来只有一个 0x4000 的常量（那是 `Entity_Player` 的量级），
    #:   而 `Level`/`Game`/`Room` 是**巨型对象**（`Level+0x2155C`、`Room+0x1FC0` …，
    #:   远超 0x4000）⇒ 按接收者分档，否则新加的 `Level` 行会被误判成抄错。
    #:   `Entity`/`EntityPlayer`/`ItemConfigItem` 仍在 0x4000 以内（这些类的实例是小对象）。
    OFFSET_LIMITS = {
        # ★ 批次 305：`Music`（`Manager` 的内嵌子对象）—— 本批只用到 `+0x3F0`，
        # 但同族已知字段到 `+0x490` 量级 ⇒ 取 0x1000 作"明显越界"的上界。
        "Music": 0x1000,
        "Entity": 0x4000,
        "EntityPlayer": 0x4000,
        # ★ 批次 341（2026-10-04）：`EntityLaser`（`Entity` 的子类，成员到 `+0x508` 量级）
        # —— 与 `Entity` 家族同一档；本批只用到 `+0x4F8`。
        "EntityLaser": 0x4000,
        # ★ 批次 308：`GridEntity` 是小对象（已知成员：类型 `+0x08`、变体 `+0x10`、
        # 内嵌 ANM2 `+0x48`）⇒ 与 `Entity` 家族同一档。
        "GridEntity": 0x4000,
        "ItemConfigItem": 0x4000,
        "Room": 0x30000,
        "RoomDescriptor": 0x400,
        "RoomConfigData": 0x400,
        "Level": 0x30000,
    }

    #: 批次 297（2026-10-03）：**同一接收者、不同 owner 时对象大小可以差很多** ⇒ 按
    #: `(接收者, owner)` 再加一档覆盖。目前唯一一条：`FieldReceipt::Level` 同时服务
    #: `Level`（对象到 `0x21568` 量级 ⇒ `0x30000` 够用）与 `Game`（`Game + 0x26FA50` 就是
    #: 状态标志数组 —— `Game` 是**巨型对象**，`0x30000` 会误报）⇒ `Game` 单开一档。
    #: ★ 这不是放宽判据：它是把"一个上界"拆成"两个更贴切的上界"，`Level` 那一档**没动**。
    OWNER_OFFSET_LIMITS = {
        ("Level", "Game"): 0x300000,
    }

    def test_offsets_stay_inside_the_owner_object(self):
        """偏移要落在**该接收者对象**的合理范围内（明显越界的偏移一定是抄错了）。"""
        for row in self.rows:
            with self.subTest(row=hex(row["id"])):
                value = self.constants[row["offset_name"]]
                owner = self.catalog.get(row["id"], ("?", "?"))[0]
                limit = self.OWNER_OFFSET_LIMITS.get((row["receipt"], owner))
                if limit is None:
                    limit = self.OFFSET_LIMITS.get(row["receipt"])
                self.assertIsNotNone(
                    limit, f"接收者 {row['receipt']} 没有登记偏移上界 —— 新接收者要在这里加一档")
                self.assertLess(value, limit,
                                f"{row['offset_name']} = {hex(value)} 越界（{row['receipt']} 的上界 "
                                f"是 {hex(limit)}）")

    def test_rows_are_registered_through_attach_owner_methods(self):
        """行表必须真的传给 `AttachOwnerMethods`，否则整张表是死数据。"""
        text = read(ISAAC_API)
        self.assertRegex(text, r"AttachOwnerMethods\(state, kEntityPlayerOwner,[^;]*FieldApiRows",
                         "EntityPlayer 族的行表没有传给 AttachOwnerMethods ⇒ 那些方法根本不会被挂上")
        self.assertRegex(text, r"AttachOwnerMethods\(state, kItemConfigItemOwner,[^;]*FieldApiRows",
                         "ItemConfig_Item 族的行表没有挂上")
        remaining = read(REMAINING_API)
        self.assertRegex(remaining, r"AttachOwnerMethods\(state, \"Level\",[^;]*kLevelFieldApis",
                         "Level 族的行表没有挂上")
        # 批次 289：`Room` 族的字段行表接在"本来传 `nullptr, 0`"的那个实参位置上 ——
        # 忘了传就是"两条 API 挂不上、且只有真机上才发现"。
        self.assertRegex(remaining, r"AttachOwnerMethods\(state, \"Room\",[^;]*kRoomFieldApis",
                         "Room 族的字段行表没有挂上")

    def test_binding_mechanism_supports_rows_with_a_closure_upvalue(self):
        """绑定机制要按"闭包 + 行作为上值"注册，而不是把行指针忘了传。"""
        text = read(BINDING)
        self.assertIn("lua_pushlightuserdata", text)
        self.assertIn("lua_pushcclosure", text)
        self.assertIn("FieldApiHandler", text)

    def test_row_size_stays_sixteen_bytes(self):
        """行必须是 16 字节 —— 编译期已由 `static_assert` 钉住，这里再确认它还在。"""
        self.assertIn("static_assert(sizeof(FieldApiRow) == 16", read(HEADER))


if __name__ == "__main__":
    unittest.main()
