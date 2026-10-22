# 全局枚举表的**契约快照**（进门禁，勿手改）

这 16 个 `.md` 是 PC《以撒的结合：忏悔》模组文档里枚举页的**逐字节副本**，供
`tools/generate_doc_enum_tables.py` 解析 → 生成 `runtime/source/program/doc_lua_enum_data.{hpp,cpp}`。
（批次 292 加的是 `BackdropType.md` —— 与那批的 `Room:GetBackdropType()` 配对，
少了它模组拿返回值也比不了 `BackdropType.*`。批次 297 加的是 `GameStateFlag.md` /
`LevelStateFlag.md` —— 与那批的 `Game:GetStateFlag(int Flag)` / `Level:GetStateFlag(int Flag)`
配对：模组是**拿这些常量当实参**的，表是 nil 时那一行直接抛错。批次 301 加的是 `CacheFlag.md`
—— 与那批的 `EntityPlayer:AddCacheFlags(CacheFlag)` 配对：模组写
`player:AddCacheFlags(CacheFlag.CACHE_DAMAGE | CacheFlag.CACHE_FIREDELAY)`，
表是 nil 时 `CacheFlag.CACHE_DAMAGE` 本身就是 nil ⇒ 方法在也照样抛错。）

★ 目录里除了这 16 页，还有本 README 与 `.gitattributes`。清单以生成器的 `TABLES` 为准 ——
那里是唯一真值源，改表一定要同步 `runtime/tests/test_lua_doc_enum_tables.py` 的期望清单。

★ 例外：`ButtonAction.md` 是**引用页**，**不进 `TABLES`**。`ButtonAction` 这张枚举表是**手写**的
（在 `runtime/source/lua_runtime.cpp` 的 `kButtonActionConstants` 里，不由本工具生成），
把这一页放进来的目的是让它的**值/名字**有仓库内的契约可对照 —— 见
`runtime/tests/test_lua_button_action_rep_plus.py`（批次 218 就是靠它抓到 16/17/18 三个名字错位）。

## 为什么要把它们复制进仓库

原来那份完整快照在 `analysis/isaacdocs-snapshot/` 下，而 `analysis/` 是 **gitignore 的**（它是本机的
分析产物，不进门禁）。后果有两层，第二层才是真问题：

1. 干净检出（门禁里那个"只用 `git ls-files` 复制被跟踪文件"的用例）里没有这些页 ——
   生成器的输入**不存在**，`--check` 与"每张表都有文档页"的断言都过不去；
2. 更要紧的是：**契约源不在仓库里 = 这一类工作对任何其他人都不可做**。
   `pc_lua_enum_data`（那 20 张表）就是这种状态 —— 它的输入是用户 PC 游戏本体的 `enums.lua`，
   缺了就只能 `skip`，于是"那 20 张之外的表"长期没人能补，直到真机上撞了 `RoomShape` 才暴露
   （见 `docs/改动日志-20260919.md` 的 048）。

所以这里**刻意 vendor 一份**：来源与版本可追、字节可核对、改行尾要显式做（`.gitattributes` 标了 `-text`，
因为生成物的头部写着这些文件的 sha256，字节一变门禁就会红 —— 那正是我们要的）。

## 来源

* 上游：模组开发文档的枚举页（本站快照 `analysis/isaacdocs-snapshot/docs/enums/`）。
* 取用日期：2026-09-19（首批 6 页）、2026-09-20（`CallbackPriority`）、2026-09-29（`ProjectileFlags` / `EntityFlag`）、
  2026-09-30（`SoundEffect`、`SeedEffect`）、2026-09-30（`ButtonAction`，**引用页不是生成表**）、
  2026-10-02（`RenderMode`、`BackdropType`）、2026-10-03（`GameStateFlag`、`LevelStateFlag`、`CacheFlag`）。
* 取哪几页：只取本工具 `TABLES` 里列的那几张（**用到才取**；要用新表就再复制对应的一页，
  并在生成器 `TABLES` 与门禁的期望清单里同步登记）。

## 各页 sha256 前 16 位（复制时）

| 文件 | 大小 | sha256 前 16 位 |
| --- | ---: | --- |
| `RoomShape.md` | 1590 | `45c1ab371b7adf92` |
| `DoorVariant.md` | 778 | `3dc03ae7df35b0e4` |
| `Direction.md` | 418 | `bcd5c28fbd0ad326` |
| `StageType.md` | 724 | `a5ae5997d0606a19` |
| `DamageFlag.md` | 4607 | `e4c06715fd6d2416` |
| `RoomDescriptor.md` | 3487 | `7f7f2993e32d8376` |
| `CallbackPriority.md` | 380 | （2026-09-20 加，见 `test_lua_doc_enum_tables.py` 的字节钉） |
| `ProjectileFlags.md` | 5761 | `aea9f2c8eec32db2` |
| `EntityFlag.md` | 9093 | `4414720e6e65b72d` |
| `SoundEffect.md` | 197514 | `986aa69d35c0dbbf` |
| `SeedEffect.md` | 5863 | `d1b2c048512ca673` |
| `RenderMode.md` | 821 | `4306c4cbb588ca73` |
| `BackdropType.md` | 4828 | `c7e2772c7363482f` |
| `GameStateFlag.md` | 6321 | `46123e54b30c719e` |
| `LevelStateFlag.md` | 2304 | `234463ea6f188dd6` |
| `CacheFlag.md` | 1582 | `80915bf3965b08ca` |
| `ButtonAction.md` | 4204 | （引用页；见下） |

更新办法（例如上游文档修了某个值）：

```bash
cp analysis/isaacdocs-snapshot/docs/enums/<表>.md tools/pc_enum_docs/
python3 tools/generate_doc_enum_tables.py --write
python3 tools/run_tests.py            # 门禁会指出哪些被钉住的值/条数变了，人工确认后再改期望
```

⚠️ 只有**真的核对过上游变更**才允许重新复制 —— 这些值会直接决定模组在地图上画什么。
