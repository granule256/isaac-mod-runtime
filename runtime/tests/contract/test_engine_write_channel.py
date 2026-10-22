"""引擎内存**写通道**的契约测试（2026-09-16 新增）。

## 为什么需要它

在 2026-09-16 之前，运行时对引擎对象是**只读**的：四个 API 族的可读性检查
（`IsEngineMemoryReadable`）加 `ReadEngine<T>`，没有任何写入口。这一批第一次开了写：

* `Sprite.Scale` / `Sprite.Color` / `Sprite.FlipX` 写进原生 `ANM2`
  （`sprite_api.cpp` 的 `ApplyCachedSpriteProperties`，绘制路径上每帧应用一次）；
* `EntityPlayer.ControlsCooldown` 写进 `Entity_Player+0x404`
  （`isaac_api.cpp` 的 `EntityNewIndex`，挂在 `EntityPlayer` 元表的 `__newindex` 上）。

写引擎内存与读是**两件危险等级完全不同**的事：读错地址最坏是"读到垃圾"，写错地址是
**静默破坏别人的内存**（症状是随机崩溃 / 存档损坏，而且事后无从归因）。所以这里把写通道的
三条纪律钉成门禁：

1. **唯一入口**：`runtime/src/interfaces/lua/` 下任何"往引擎地址写"都必须经过该 TU 里的
   `WriteEngine<T>`，不许出现裸指针赋值或裸 `memcpy` —— 这样"写之前先确认可写"就不可能被绕过；
2. **可读 ≠ 可写**：写路径必须查**写**缓存（`EngineGuardLookupWritable` /
   `EngineGuardRememberWritable`），且必须按 `Perm_W` 判定；拿读缓存给写路径放行会让
   `Sprite.Scale = 2` 去写只读页（真机 = `Data Abort`）；
3. **偏移有出处**：写点引用的必须是 `runtime_constants.hpp` 里的具名常量（且常量注释里要写出
   证据函数），不许在写点写裸字面量偏移。

2026-09-24（批次 103）：前两条的**落点搬了**，判据跟着搬（用户已批准改断言）——
原本"每个可写 TU 各有一份 `IsEngineMemoryWritable` 与一句裸 `memcpy`"，现在实现**收敛成层里
唯一一份**（`infrastructure/memory/engine_field_access.hpp` 的 `EngineMemoryWritable` /
`WriteField`），两个 TU 只剩一行委托。**契约意图一条没变**：写只有一个驱动点、写之前必须先
确认可写、且不许拿读缓存给写路径放行。

另外钉住"写入口不滥开"：`EntityPlayer` 只放行**取证过**的字段
（`ControlsCooldown` / `ControlsEnabled` / `Velocity` / `Position` / 六个战斗属性），别的字段名必须报错。
★ 2026-09-30（批次 212）改口径：原来只放行 `ControlsCooldown`，真机证明那样会把模组的
**整条回调**掐死（MCM 打开菜单时冻住玩家，第 1625 行 `player.Velocity = vecZero` 就抛错
⇒ 菜单永远画不出来）。放行的每个字段都有引擎自己的读点/写点当锚点。
★ 2026-10-07（批次 405）：再放开 `Damage`/`MoveSpeed`/`MaxFireDelay`/`ShotSpeed`/`Luck`/`TearRange`
（Trinity 在 `MC_EVALUATE_CACHE` 里写它们，见 `test_lua_batch405_evaluate_cache_timing.py`）。
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LUA_DIR = ROOT / "runtime" / "src" / "interfaces" / "lua"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
#: 2026-09-24（批次 102）：守卫头文件搬进了**引擎内存访问层**目录
#: （`src/infrastructure/memory/`）—— 它是"引擎内存"的基础设施，不再属于 Lua 界面层。
#: 这里**只改路径常量，断言一字未动**。
GUARD = ROOT / "runtime" / "src" / "infrastructure" / "memory" / "engine_memory_guard.hpp"
#: 引擎内存访问层：**唯一一份**写判定与写原语的所在处（2026-09-24 批次 103 收敛）。
LAYER = ROOT / "runtime" / "src" / "infrastructure" / "memory" / "engine_field_access.hpp"

SPRITE = LUA_DIR / "sprite_api.cpp"
ISAAC = LUA_DIR / "isaac_api.cpp"

#: 允许定义 `WriteEngine` / `IsEngineMemoryWritable` 的编译单元。批次 103 起这两个名字在 TU 里
#: **只剩一行委托**（实现收敛进 `LAYER`）——保留名字是为了 11 个调用点与既有门禁的稳定性，
#: 与既有的 `IsEngineMemoryReadable` 同例。
WRITE_CAPABLE_SOURCES = (SPRITE, ISAAC)


def function_body(text: str, signature: str) -> str:
    """从 `signature` 起按大括号配平截出函数体（够用即可：这些文件里没有花括号字面量干扰）。"""
    start = text.find(signature)
    if start < 0:
        raise AssertionError(f"源码里找不到：{signature}")
    brace = text.find("{", start)
    if brace < 0:
        raise AssertionError(f"{signature} 后面没有函数体")
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[brace:index + 1]
    raise AssertionError(f"{signature} 的函数体没有闭合")


def code_lines(text: str):
    """只留下**代码**行（丢掉 `//` 与 `*` 开头的注释行）。

    注释里出现 `*reinterpret_cast<float*>(address) = value` 这种**反面例子**是正常的
    （`sprite_api.cpp` 的 `WriteEngine` 上方就有一句"为什么不这么写"）——
    门禁判的是代码，不是文字。`--` 之前项目里有过"注释把契约门禁判红"的先例。
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue
        yield line


class EngineWriteChannelContractTests(unittest.TestCase):
    def setUp(self):
        self.sprite = SPRITE.read_text(encoding="utf-8")
        self.isaac = ISAAC.read_text(encoding="utf-8")
        self.guard = GUARD.read_text(encoding="utf-8")
        self.layer = LAYER.read_text(encoding="utf-8")
        self.constants = CONSTANTS.read_text(encoding="utf-8")

    # ------------------------------------------------------------------ 唯一入口
    def test_engine_writes_go_through_write_engine_only(self):
        """裸写引擎内存的写法一律不许出现 —— 写必须经 `WriteEngine<T>`，再落到层里那一句。

        2026-09-24（批次 103）：那句落值的 `memcpy` 现在在**层**的 `WriteField` 体内、**全仓
        唯一一处**；两个可写 TU 里一处裸写都不许有。契约意图不变：**写只能有一个驱动点**。
        """
        definitions = len(re.findall(r"bool\s+WriteEngine\s*\(", self.sprite + self.isaac))
        self.assertEqual(definitions, len(WRITE_CAPABLE_SOURCES),
                         "每个可写编译单元应当有且只有一份 `WriteEngine<T>` 定义")

        # ① 两个可写 TU：不许有裸写（实现已搬进层），且 `WriteEngine` 只转发。
        for name, text in (("sprite_api.cpp", self.sprite), ("isaac_api.cpp", self.isaac)):
            body = function_body(text, "bool WriteEngine(")
            with self.subTest(source=name):
                self.assertIn("engine_memory::WriteAt(", body,
                              "`WriteEngine` 没有转发到层里的写原语（又自己写了一遍？）")
                self.assertIn("&IsEngineMemoryWritable", body,
                              "`WriteEngine` 没有把本地那份可写判定注入写原语 ⇒ 写之前没确认可写")
                self.assertNotIn("memcpy", body,
                                 "`WriteEngine` 体内还有 `memcpy` —— 落值应当只剩层里那一处")

        # ② 层里那唯一一处落值，必须在 `WriteField` 体内，且地址先过层自己的检查与转换。
        write_field = function_body(self.layer, "bool WriteField(")
        self.assertEqual(len(re.findall(r"std::memcpy\s*\(", write_field)), 1,
                         "层里「往引擎落一个字段」的实现应当只有一处（`WriteField`）")
        self.assertIn("FieldAddress(", write_field,
                      "`WriteField` 没有先过地址检查（回绕 / 对齐 / 可写）就落值")
        self.assertIn("AsObject(", write_field,
                      "`WriteField` 没有走层自己的「整数地址 → 指针」转换（`AsObject`）")
        write_at = function_body(self.layer, "bool WriteAt(")
        self.assertIn("WriteField(", write_at,
                      "`WriteAt` 应当只是 `WriteField(address, 0, …)` 的转发")
        self.assertNotIn("memcpy", write_at)

        # 反向对照：整个 lua 目录里，不该再有裸写形态。
        for path in sorted(LUA_DIR.glob("*.cpp")):
            text = path.read_text(encoding="utf-8")
            others = [line.strip() for line in code_lines(text)
                      if re.search(r"memcpy\s*\(\s*reinterpret_cast<void\s*\*>", line)]
            self.assertEqual(others, [], f"{path.name} 里有裸写：{others}")

        # 直接对引擎指针做赋值（`*reinterpret_cast<float*>(address) = …`）同样不许出现 ——
        # 两个 TU 与层本身都判（层里那段"为什么不这么写"只出现在注释里，会被 `code_lines` 滤掉）。
        self.assertEqual([line.strip() for line in code_lines(self.layer)
                          if re.search(r"\*\s*reinterpret_cast<[^>]*\*>\s*\([^)]*\)\s*=", line)],
                         [], "层里出现了裸指针赋值")
        for name, text in (("sprite_api.cpp", self.sprite), ("isaac_api.cpp", self.isaac)):
            offenders = [line.strip() for line in code_lines(text)
                         if re.search(r"\*\s*reinterpret_cast<[^>]*\*>\s*\([^)]*\)\s*=", line)]
            self.assertEqual(offenders, [], f"{name} 里出现了裸指针赋值：{offenders}")

    # ------------------------------------------------------------------ 可读 ≠ 可写
    def test_write_path_uses_the_writable_cache_and_perm_w(self):
        """写判定**只有一份**（在层里），且按 `Perm_W`、查写缓存、**不碰**读缓存。

        2026-09-24（批次 103）：此前这条按"每个可写 TU 各有一份实现"判；两份实现收敛成层里
        唯一一份之后，断言改成"实现只在层里 + 两个 TU 只准委托"。意图不变：
        **可读不等于可写，写路径不许拿读缓存给只读页放行**。
        """
        body = function_body(self.layer, "bool EngineMemoryWritable(")
        self.assertIn("EngineGuardLookupWritable", body,
                      "写判定没有查写缓存（每次都进内核会拖慢绘制，且写法与读侧不一致）")
        self.assertIn("EngineGuardRememberWritable", body,
                      "写判定没有登记写区间（同一页会被反复问内核）")
        self.assertIn("Perm_W", body, "写判定必须按 `Perm_W`，不能只看可读")
        self.assertNotIn("EngineGuardLookupCached", body,
                         "写判定查了**读**缓存：可读不等于可写，模块映像的只读段会因此被放行")
        self.assertNotIn("Perm_R", body, "写判定不许用 `Perm_R`")

        # 两个可写 TU 只准委托：判定只许有一份，别在 TU 里又长出一份"简化版"。
        for path in WRITE_CAPABLE_SOURCES:
            text = path.read_text(encoding="utf-8")
            delegate = function_body(text, "bool IsEngineMemoryWritable(")
            with self.subTest(source=path.name):
                self.assertIn("engine_memory::EngineMemoryWritable(", delegate,
                              "可写判定必须委托层里那一份")
                for forbidden in ("Perm_W", "Perm_R", "EngineGuardLookupWritable",
                                  "EngineGuardRememberWritable", "EngineGuardLookupCached"):
                    self.assertNotIn(forbidden, delegate,
                                     f"`IsEngineMemoryWritable` 里出现了 {forbidden} —— "
                                     "判定只准有一份（在层里），TU 里应当是纯委托")

    def test_writable_cache_is_separate_and_cleared_with_the_scope(self):
        """写缓存必须与读缓存**分家**，并且随派发作用域一起清空（否则会命中过期区间）。"""
        self.assertIn("EngineGuardWritableRegionCache()", self.guard)
        self.assertNotEqual(self.guard.find("EngineGuardWritableRegionCache()"),
                            self.guard.find("EngineGuardRegionCache() {"),
                            "写缓存不能就是读缓存那一个实例")
        for scope in ("inline void EngineGuardSetCacheEnabled(", "inline void EngineGuardEnterDispatch()",
                      "inline void EngineGuardLeaveDispatch()"):
            body = function_body(self.guard, scope)
            with self.subTest(scope=scope):
                self.assertIn("EngineGuardWritableRegionCache().Clear()", body,
                              f"{scope} 没有清写缓存：换局/换相之后会命中过期区间")

    # ------------------------------------------------------------------ 偏移有出处
    def test_write_sites_reference_named_constants(self):
        """写点必须引用具名常量，常量注释里要写出证据（函数 + 指令形态）。"""
        for name in ("kSpriteScaleOffset", "kSpriteColorOffset", "kSpriteFlipXOffset"):
            with self.subTest(constant=name):
                self.assertIn(f"inline constexpr uintptr_t {name} =", self.constants,
                              f"{name} 没在 `runtime_constants.hpp` 里声明")
                self.assertIn(name, self.sprite, f"{name} 没有被写点引用（写了字面量偏移？）")
        self.assertIn("kEntityPlayerControlsCooldownOffset", self.isaac)
        self.assertIn("inline constexpr uintptr_t kEntityPlayerControlsCooldownOffset =",
                      self.constants)

        # 证据：两条互不相同的证人都要出现在常量注释里（见常量块上方的说明）。
        for witness in ("ANM2::Reset", "GetDestQuad"):
            with self.subTest(witness=witness):
                self.assertIn(witness, self.constants,
                              f"ANM2 字段偏移的证据里缺了 {witness} —— 偏移必须有第二证人")

    def test_sprite_write_covers_the_three_pc_properties(self):
        """三个属性的落点与宽度要与 PC 一致（Scale 两个 float、Color 四元组、FlipX 一个字节）。"""
        body = function_body(self.sprite, "bool ApplyCachedSpriteProperties(")
        self.assertIn("kSpriteScaleOffset", body)
        self.assertIn("kSpriteScaleOffset + sizeof(float)", body)
        # PC 的 Color 属性整值覆盖，不能只写 tint/offset 留下旧染色。
        self.assertIn("WriteEngine<EngineColorMod>", body)
        self.assertIn("EngineColorModFromHandle(color)", body)
        shared = (LUA_DIR / "engine_color_mod.hpp").read_text(encoding="utf-8")
        self.assertIn("offsetof(EngineColorMod, tint) == kColorModTintOffset", shared)
        self.assertIn("offsetof(EngineColorMod, shift) == kColorModShiftOffset", shared)
        self.assertIn("offsetof(EngineColorMod, colorize) == kColorModColorizeOffset", shared)
        self.assertIn("WriteEngine<std::uint8_t>(base + kSpriteFlipXOffset", body)
        # 只写"Mod 确实赋过值"的属性：没赋过值就不该动引擎原有的值。
        for flag in ("hasScale", "hasColor", "hasFlipX"):
            with self.subTest(flag=flag):
                self.assertIn(f"handle->{flag} != 0", body,
                              f"缺少 `{flag}` 门槛：Mod 没写过这个属性也会去改引擎对象")

    # ------------------------------------------------------------------ 写入口不滥开
    def test_player_newindex_only_allows_the_evidenced_fields(self):
        """`EntityPlayer` 的写入口**只放行取证过的字段**，别的字段名报错。

        ★ 2026-09-30（批次 212）改口径：原来只放行 `ControlsCooldown`。真机事故证明"只放
        `ControlsCooldown`"会把模组的**整条回调**掐死 —— MCM 打开菜单时冻住玩家
        （`modconfig.lua:1625 player.Velocity = vecZero`、`:1630 Position`、`:1632 ControlsEnabled`），
        第 1625 行就抛错 ⇒ 菜单永远画不出来（读数里那两条 `EntityPlayer fields are read-only …`）。
        ★ 2026-10-07（批次 405）再放开六个战斗属性（`Damage`/`MoveSpeed`/`MaxFireDelay`/`ShotSpeed`/
        `Luck`/`TearRange`）：Trinity 在 `MC_EVALUATE_CACHE` 里写它们（`main.lua:85/:116`），
        拒写同样会把整条回调摘掉。每个字段**都有引擎自己的读点/写点当锚点**
        （见 `runtime_constants.hpp` 的同名常量注释）。
        **陌生字段名仍然报错** —— 这条判据的意图（别让拼错的字段名被静默吞掉）没变。
        """
        body = function_body(self.isaac, "int EntityNewIndex(")
        for field, offset in (
                ("ControlsCooldown", "kEntityPlayerControlsCooldownOffset"),
                ("ControlsEnabled", "kEntityPlayerControlsEnabledOffset"),
                ("Velocity", "kEntityVelocityOffset"),
                ("Position", "kEntityPositionOffset"),
                # 批次 405：六个战斗属性（全部 float）。
                ("MaxFireDelay", "kEntityPlayerMaxFireDelayOffset"),
                ("ShotSpeed", "kEntityPlayerShotSpeedOffset"),
                ("Damage", "kEntityPlayerDamageOffset"),
                ("MoveSpeed", "kEntityPlayerMoveSpeedOffset"),
                ("Luck", "kEntityPlayerLuckOffset"),
                ("TearRange", "kEntityPlayerTearRangeOffset"),
        ):
            with self.subTest(field=field):
                self.assertIn(f'"{field}"', body, f"{field} 必须有自己的分支")
                self.assertIn(offset, body, f"{field} 必须用具名偏移常量（不许裸字面量）")
        # `ControlsEnabled` 是 **1 字节** bool（引擎自己的 `SetControlsEnabled` 用 `strb` 写），
        # 按 4 字节写会踩坏相邻字段（`+0x404` 的 ControlsCooldown 就在后面）。
        self.assertIn("WriteEngine<std::uint8_t>(entity + kEntityPlayerControlsEnabledOffset", body)
        # `Velocity` / `Position` 是 Vector2 = 两个 float：必须显式写 `+ sizeof(float)` 的第二分量。
        self.assertIn("entity + offset + sizeof(float)", body,
                      "Vector2 字段必须按两个 float 写（只写 X 会让 Y 保持旧值）")
        # 六个战斗属性是 **float**：必须按 float 写（按 int 写会把 4.25 这类值丢掉小数）。
        self.assertIn("WriteEngine<float>(entity + stat.offset", body,
                      "战斗属性必须按 float 写")
        self.assertIn('"EntityPlayer fields are read-only except "', body,
                      "未知字段名必须报错，不能静默吞掉（拼错的字段名会因此查不出来）")
        for field in ("Velocity", "Position", "ControlsEnabled", "ControlsCooldown",
                      "Damage", "MoveSpeed", "MaxFireDelay", "ShotSpeed", "Luck", "TearRange"):
            self.assertIn(field, body, f"报错文案里要列出放行的字段（{field} 缺了会让读者以为它不可写）")
        # PC基类非const字段可写，所有实体视图必须接到有守卫的共享入口。
        registration = self.isaac[self.isaac.find("void RegisterViewMetatables("):]
        base_block = registration[:registration.find("kEntityPlayerMetatable")]
        self.assertIn('lua_pushcfunction(state, EntityNewIndex)', base_block)
        self.assertIn('__newindex', base_block)
        self.assertIn('CheckEntityHandle(state, 1)', body)
        self.assertIn('ValidatedEntity(handle)', body)
        self.assertIn('IsEntityPlayer(entity)', body)
        self.assertIn('lua_setfield(state, -2, "__newindex")', registration)


if __name__ == "__main__":
    unittest.main()
