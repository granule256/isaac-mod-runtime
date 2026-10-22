"""统一 API Catalog 的契约测试。

Catalog 必须是 Lua API 的唯一清单：每个真实注册的 API 都能在清单里找到，
清单里也不能出现运行时不存在的“幽灵 API”。同时校验 id 方案、重复项与查询行为。
"""

import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "runtime"
SRC = RUNTIME / "src"
LUA_RUNTIME = RUNTIME / "source" / "lua_runtime.cpp"
CATALOG_SOURCE = SRC / "interfaces" / "lua" / "api_catalog.cpp"
FAMILY_API_SOURCES = (
    SRC / "interfaces" / "lua" / "bitset128_api.cpp",
    SRC / "interfaces" / "lua" / "mod_api.cpp",
    SRC / "interfaces" / "lua" / "rplus_method_bindings.cpp",
    SRC / "interfaces" / "lua" / "api100_bindings.cpp",
    SRC / "interfaces" / "lua" / "api200_bindings.cpp",
    SRC / "interfaces" / "lua" / "api300_bindings.cpp",
    SRC / "interfaces" / "lua" / "api400_bindings.cpp",
    SRC / "interfaces" / "lua" / "api500_config.cpp",
    SRC / "interfaces" / "lua" / "api600_bindings.cpp",
    SRC / "interfaces" / "lua" / "api700_bindings.cpp",
    SRC / "interfaces" / "lua" / "game_api.cpp",
    SRC / "interfaces" / "lua" / "isaac_api.cpp",
    SRC / "interfaces" / "lua" / "remaining_api.cpp",
    SRC / "interfaces" / "lua" / "music_api.cpp",
    SRC / "interfaces" / "lua" / "rng_api.cpp",
    SRC / "interfaces" / "lua" / "input_api.cpp",
    SRC / "interfaces" / "lua" / "font_api.cpp",
    SRC / "interfaces" / "lua" / "color_api.cpp",
    SRC / "interfaces" / "lua" / "vector_api.cpp",
    SRC / "interfaces" / "lua" / "sprite_api.cpp",
    # 2026-09-16：运行时的模组开关控制面（`RuntimeMods`，新域 `ModMenu`）。
    SRC / "interfaces" / "lua" / "mod_menu_api.cpp",
)

DRIVER = textwrap.dedent(
    r"""
    #include "domain/runtime/status.hpp"
    #include "interfaces/lua/api_catalog.hpp"

    #include <cstdio>
    #include <cstring>

    using namespace isaac::runtime;

    namespace {

    int failures = 0;

    void Check(bool condition, const char* what) {
        if (!condition) {
            std::printf("FAILED_CHECK %s\n", what);
            ++failures;
        }
    }

    constexpr LuaApiDescriptor InvalidEntry(std::uint32_t id, ApiDomain domain, const char* owner,
                                            const char* name) {
        return LuaApiDescriptor{id, domain, owner, name, ApiVersion{1, 0}, 0,
                                ThreadAffinity::Any, ApiMaturity::Experimental};
    }

    void TestDefaultCatalog() {
        const ApiCatalog& catalog = ApiCatalog::Default();
        Check(catalog.Validate().ok(), "default_catalog_valid");
        Check(catalog.Count() >= 30, "catalog_covers_current_surface");

        const LuaApiDescriptor* paused = catalog.Find(0x02010001);
        Check(paused != nullptr && std::strcmp(paused->owner, "Game") == 0 &&
                  std::strcmp(paused->name, "IsPaused") == 0,
              "find_by_id_game_ispaused");
        Check(paused != nullptr && paused->maturity == ApiMaturity::HardwareVerified,
              "ispaused_is_hardware_verified");
        Check(paused != nullptr && paused->domain == ApiDomain::Game, "ispaused_domain");

        const LuaApiDescriptor* pause = catalog.Find("MusicManager", "Pause");
        Check(pause != nullptr && pause->id == 0x06010002, "find_pause_by_owner_name");
        Check(pause != nullptr && pause->affinity == ThreadAffinity::MainRender,
              "pause_runs_on_render_thread");

        const LuaApiDescriptor* save = catalog.Find("Mod", "SaveData");
        Check(save != nullptr && save->id == 0x08010001, "save_data_id");
        Check(save != nullptr && save->maturity == ApiMaturity::Experimental,
              "persistence_stays_experimental");

        const LuaApiDescriptor* registerMod = catalog.Find("Global", "RegisterMod");
        Check(registerMod != nullptr && registerMod->id == 0x00010001, "register_mod_id");

        Check(catalog.Find(static_cast<std::uint32_t>(0xDEADBEEF)) == nullptr, "unknown_id_missing");
        Check(catalog.Find("Game", "NotAnApi") == nullptr, "unknown_name_missing");
        Check(catalog.Find(nullptr, "IsPaused") == nullptr, "null_owner_rejected");
        Check(catalog.Find("Game", nullptr) == nullptr, "null_name_rejected");
        Check(catalog.At(catalog.Count()) == nullptr, "at_out_of_range");
    }

    void TestValidationRejectsBadTables() {
        const LuaApiDescriptor duplicateId[] = {
            InvalidEntry(0x02010001, ApiDomain::Game, "Game", "IsPaused"),
            InvalidEntry(0x02010001, ApiDomain::Game, "Game", "IsOther"),
        };
        Check(ApiCatalog{duplicateId, 2}.Validate().code() == StatusCode::Rejected,
              "duplicate_id_rejected");

        const LuaApiDescriptor duplicateName[] = {
            InvalidEntry(0x02010001, ApiDomain::Game, "Game", "IsPaused"),
            InvalidEntry(0x02010002, ApiDomain::Game, "Game", "IsPaused"),
        };
        Check(ApiCatalog{duplicateName, 2}.Validate().code() == StatusCode::Rejected,
              "duplicate_owner_name_rejected");

        const LuaApiDescriptor emptyName[] = {
            InvalidEntry(0x02010001, ApiDomain::Game, "Game", ""),
        };
        Check(ApiCatalog{emptyName, 1}.Validate().code() == StatusCode::InvalidArgument,
              "empty_name_rejected");

        const LuaApiDescriptor zeroId[] = {
            InvalidEntry(0, ApiDomain::Game, "Game", "IsPaused"),
        };
        Check(ApiCatalog{zeroId, 1}.Validate().code() == StatusCode::InvalidArgument,
              "zero_id_rejected");

        // Domain byte must match the declared domain: an id from another domain
        // silently mislabels the API in generated docs.
        const LuaApiDescriptor wrongDomain[] = {
            InvalidEntry(0x06010001, ApiDomain::Game, "Game", "IsPaused"),
        };
        Check(ApiCatalog{wrongDomain, 1}.Validate().code() == StatusCode::InvalidArgument,
              "domain_byte_mismatch_rejected");

        Check(ApiCatalog{nullptr, 0}.Validate().code() == StatusCode::InvalidArgument,
              "empty_catalog_rejected");
    }

    } // namespace

    int main() {
        TestDefaultCatalog();
        TestValidationRejectsBadTables();
        if (failures != 0) {
            std::printf("CATALOG_CHECKS_FAILED %d\n", failures);
            return 1;
        }
        std::printf("CATALOG_CHECKS_PASSED\n");
        return 0;
    }
    """
)


def host_compiler() -> str | None:
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return found
    return None


def non_layered_regions(source: str) -> list[str]:
    """Return every `#if !defined(EXL_LAYERED_RUNTIME)` block of a source file.

    The legacy translation unit keeps a verbatim copy of each migrated handler
    inside such a block, so the tests need the block *bodies*. A plain regex
    cannot do this: blocks like the Music family contain nested
    `#if defined(EXL_DIAGNOSTIC_STAGE)` directives, and a non-greedy match would
    stop at the inner `#endif` and silently report the body as missing.
    """
    regions: list[str] = []
    depth = 0
    start: int | None = None
    for index, line in enumerate(source.splitlines()):
        stripped = line.strip()
        if stripped == "#if !defined(EXL_LAYERED_RUNTIME)":
            if depth == 0:
                start = index + 1
            depth += 1
            continue
        if stripped.startswith("#if"):
            depth += 1
            continue
        if stripped.startswith("#endif"):
            depth = max(0, depth - 1)
            if depth == 0 and start is not None:
                regions.append("\n".join(source.splitlines()[start:index]))
                start = None
    return regions


def registered_function_names() -> set[str]:
    """Extract every Lua function field the runtime registers."""
    lines = LUA_RUNTIME.read_text(encoding="utf-8").splitlines()
    names: set[str] = set()
    for index, line in enumerate(lines):
        match = re.search(r'lua_setfield\(state, -2, "([^"]+)"\)', line)
        if match is None:
            continue
        name = match.group(1)
        if name.startswith("__"):
            continue  # metatable plumbing, not a callable API
        previous = lines[index - 1] if index > 0 else ""
        if "lua_pushcfunction" in previous:
            names.add(name)

    registered_ids = set()
    for source_path in FAMILY_API_SOURCES:
        body = source_path.read_text(encoding="utf-8")
        # 两种绑定形态都要认：
        #   * 手写处理器：`{0x…, &Handler}`
        #   * **字段读取型数据行**（`field_api.hpp`）：`{0x…, k...Offset, 0, FieldKind::…, …}`
        # 后者是 2026-09-15 成本压缩引入的共享处理器机制：每个 API 只占一行数据。
        # 不认它的话，这些 API 会被判成"目录里有、运行时没注册"的幽灵条目。
        registered_ids.update(
            re.findall(r"\{\s*(0x[0-9A-Fa-f]{8}),\s*&", body)
        )
        registered_ids.update(
            re.findall(r"\{\s*(0x[0-9A-Fa-f]{8}),\s*k\w+Offset\s*,", body)
        )
        # ★ 批次 303（2026-10-03）：**按 vtable 槽号调用的引擎方法行**
        #   （`{0x…, MakeEngineVtableRowOffset(k...Slot), …}`）—— 第 2 栏两个形态都不是，
        #   不认它的话这些 API 会被判成"目录里有、运行时没注册"的幽灵条目。
        registered_ids.update(
            re.findall(r"\{\s*(0x[0-9A-Fa-f]{8}),\s*MakeEngineVtableRowOffset\(k\w+Slot\)", body)
        )
    domain_bytes = {
        "Global": 0, "Mod": 1, "Game": 2, "Level": 3, "Room": 4,
        "ItemPool": 5, "Music": 6, "Rng": 7, "Persistence": 8, "Input": 9,
        "Diagnostic": 10, "Font": 11, "Vector": 12, "Sprite": 13, "Vector": 12,
        "Isaac": 14,
        # `Seeds`（`Game:GetSeeds()` 的返回值），2026-09-12 第五轮加入。这份映射与下面
        # `test_family_binding_ids_match_the_catalog` 里的那份必须同时加，否则新家族会被
        # 静默跳过 —— 两个字典各写一份本身就是个坑，注释在此留痕。
        "Seed": 15,
        # `RuntimeMods`（运行时自带的模组开关菜单控制面），2026-09-16 加入。
        "ModMenu": 16,
        # `HUD`（`Game:GetHUD()` 的返回值），批次 207（2026-09-29）加入。真值源是
        # `runtime/src/interfaces/lua/api_descriptor.hpp` 的 `ApiDomain`；此处与下面
        # `test_family_binding_ids_match_the_catalog` 里那份**必须同时加**，否则
        # `0x11…` 两条绑定行会在 `by_owner` 里查不到 → 该用例判红。
        "Hud": 17,
    }
    catalog = CATALOG_SOURCE.read_text(encoding="utf-8")
    for domain, group, sequence, name in re.findall(
        r'MakeId\(ApiDomain::(\w+),\s*(\d+),\s*(0x[0-9A-Fa-f]+)\),\s*'
        r'ApiDomain::\w+,\s*"[^"]+",\s*"([^"]+)"',
        catalog,
    ):
        if domain not in domain_bytes:
            continue
        identifier = (
            (domain_bytes[domain] << 24) | (int(group) << 16) | int(sequence, 16)
        )
        if f"0x{identifier:08x}" in {value.lower() for value in registered_ids}:
            names.add(name)
    return names


def registered_global_names() -> set[str]:
    """Every global name the runtime (or a family TU) publishes.

    家族 TU 也会挂全局：`Isaac`/`Options` 由 `isaac_api.cpp` 自己建表并 `lua_setglobal`，
    批次 4 的 `GetPtrHash` 同理。Catalog 的幽灵条目门禁必须看得见它们，否则一条真实现
    会被判成"登记了但没注册"。
    """
    names = set(
        re.findall(r'lua_setglobal\(state, "([^"]+)"\)', LUA_RUNTIME.read_text(encoding="utf-8"))
    )
    for source_path in FAMILY_API_SOURCES:
        names.update(
            re.findall(r'lua_setglobal\(state, "([^"]+)"\)',
                       source_path.read_text(encoding="utf-8"))
        )
    return names


def catalog_pairs() -> set[tuple[str, str]]:
    """(owner, name) pairs from the catalog table."""
    source = CATALOG_SOURCE.read_text(encoding="utf-8")
    # Entries start with `{MakeId(...)`; the first two quoted strings inside an
    # entry are the owner label and the API name.
    return set(
        re.findall(
            r'MakeId\([^}]*?"([A-Za-z_][A-Za-z0-9_]*)",\s*"([A-Za-z_][A-Za-z0-9_]*)"',
            source,
            flags=re.DOTALL,
        )
    )


def catalog_api_names() -> set[str]:
    return {name for _owner, name in catalog_pairs()}


def catalog_owner_labels() -> set[str]:
    return {owner for owner, _name in catalog_pairs()}


class ApiCatalogContractTests(unittest.TestCase):
    def test_mod_methods_are_registered_from_their_owner_translation_unit(self):
        """`Mod` 家族的绑定表、注册与实现体都在自己的 TU 里。

        `Mod:AddCallback` 是最后一个搬出旧 TU 的实现体（回调注册表通过
        `lua_runtime_state.hpp` 的访问器取得），因此 `lua_runtime.cpp` 里不得再出现
        任何 Mod handler、过渡 thunk 或过渡头。
        """
        source = LUA_RUNTIME.read_text(encoding="utf-8")
        mod_api = (SRC / "interfaces" / "lua" / "mod_api.cpp").read_text(encoding="utf-8")
        self.assertIn("isaac::runtime::AttachModMethods(state)", source)
        self.assertIn("std::size_t AttachModMethods(lua_State* state) noexcept", mod_api)
        self.assertIn("AttachOwnerMethods(state, kModOwner", mod_api)
        for api_id in ("0x01010001", "0x08010001", "0x08010002", "0x08010003", "0x08010004"):
            with self.subTest(api_id=api_id):
                self.assertIn(api_id, mod_api, f"{api_id} 缺少 Mod 绑定行")
        # 五个 handler 的实现体都在家族 TU，绑定表直接取本 TU 的函数地址。
        for handler in ("ModAddCallback", "ModSaveData", "ModLoadData", "ModHasData",
                        "ModRemoveData"):
            with self.subTest(handler=handler):
                self.assertIn(f"int {handler}(lua_State* state) {{", mod_api)
                self.assertIn(f"&{handler}", mod_api)
                self.assertNotIn(f"int {handler}(lua_State* state) {{", source)
        # 过渡头与过渡 thunk 都已删除。
        self.assertFalse((SRC / "interfaces" / "lua" / "legacy_handler_bindings.hpp").exists())
        self.assertNotIn("LuaModAddCallback", mod_api)
        self.assertNotIn("LuaModAddCallback", source)
        # 回调注册表仍由旧 TU 拥有，家族 TU 只通过访问器取用。
        #
        # 2026-09-16（多模组加载）：owner 句柄从"全局常量 `RuntimeOwnerHandle()`"改成
        # "从 Mod userdata 解包"（`UnpackModOwner`），因为每个 Mod 现在各有自己的 owner。
        # 这条断言的**意图不变**：家族 TU 不许自己去摸旧 TU 的状态，只能通过
        # `lua_runtime_state.hpp` 声明出来的访问器取。所以这里换成新的那个名字。
        state = (ROOT / "runtime" / "source" / "lua_runtime_state.hpp").read_text(encoding="utf-8")
        for accessor in ("ManagedCallbackRegistry", "UnpackModOwner", "IsStage13CallbackMode"):
            with self.subTest(accessor=accessor):
                self.assertIn(accessor, state)
                self.assertIn(accessor, mod_api)
        self.assertIn("CallbackRegistry& ManagedCallbackRegistry()", source)
        self.assertIn("ModHandle UnpackModOwner(", state)

    def test_game_methods_are_registered_from_their_owner_translation_unit(self):
        source = LUA_RUNTIME.read_text(encoding="utf-8")
        game_api = (SRC / "interfaces" / "lua" / "game_api.cpp").read_text(encoding="utf-8")
        shared = (SRC / "interfaces" / "lua" / "owner_binding.cpp").read_text(encoding="utf-8")
        self.assertIn("isaac::runtime::AttachGameMethods(state)", source)
        self.assertIn("std::size_t AttachGameMethods(lua_State* state) noexcept", game_api)
        self.assertIn("AttachOwnerMethods(state, kGameOwner", game_api)
        for api_id in ("0x02010001", "0x02010002", "0x02010003", "0x02010004", "0x02010005"):
            with self.subTest(api_id=api_id):
                self.assertIn(api_id, game_api, f"{api_id} 缺少 Game 绑定行")
        # 注册循环只有一份实现，家族 TU 只放绑定表。
        self.assertIn("std::size_t AttachOwnerMethods(", shared)
        self.assertIn("catalog.At(index)", shared)
        for family in ("mod_api.cpp", "game_api.cpp"):
            body = (SRC / "interfaces" / "lua" / family).read_text(encoding="utf-8")
            self.assertNotIn("lua_setfield", body, f"{family} 不应重复注册循环")

    def test_family_handler_bodies_live_in_their_family_units(self):
        """实现体归属：每个 handler 只允许存在于自己的家族 TU。

        第十片删除了旧 TU 的非分层副本，所以这里同时断言"旧 TU 里没有任何副本"，
        以及每个 handler 都能在自己的家族 TU 里找到唯一一份实现体。
        """
        legacy = LUA_RUNTIME.read_text(encoding="utf-8")
        self.assertEqual(non_layered_regions(legacy), [],
                         "旧 TU 仍保留非分层副本，探针与生产包会走两套实现")
        owners = {
            "mod_api.cpp": ("ModAddCallback", "ModSaveData", "ModLoadData", "ModHasData",
                            "ModRemoveData"),
            "game_api.cpp": ("GameIsPaused", "GameIsGreedMode", "GameGetLevel",
                             "GameGetItemPool", "GameGetRoom"),
            "remaining_api.cpp": ("LevelGetStage", "LevelIsAscent", "RoomGetType",
                                  "ItemPoolGetCollectible"),
            "music_api.cpp": ("MusicGetCurrentMusicId", "MusicPause", "MusicResume"),
            "rng_api.cpp": ("RngSetSeed", "RngNext"),
            "input_api.cpp": ("InputIsButtonTriggered", "InputIsButtonPressed",
                              "InputGetButtonValue", "InputIsActionTriggered",
                              "InputIsActionPressed", "InputGetActionValue"),
            "font_api.cpp": ("FontLoad", "FontUnload", "FontIsLoaded", "FontGetStringWidth",
                             "FontGetStringWidthUTF8", "FontGetLineHeight",
                             "FontGetBaselineHeight", "FontGetCharacterWidth",
                             "FontSetMissingCharacter"),
            "vector_api.cpp": ("VectorLength", "VectorLengthSquared", "VectorDistance",
                               "VectorDistanceSquared", "VectorDot", "VectorCross",
                               "VectorGetAngleDegrees", "VectorNormalize", "VectorNormalized",
                               "VectorResize", "VectorResized", "VectorRotated", "VectorClamp",
                               "VectorClamped", "VectorLerp", "VectorFromAngle"),
            "sprite_api.cpp": ("SpritePlay", "SpriteSetAnimation", "SpriteSetFrame",
                               "SpriteLoad", "SpriteLoadGraphics", "SpriteReplaceSpritesheet",
                               "SpriteGetFrame", "SpriteSetLayerFrame",
                               "SpriteGetLayerFrame", "SpriteUpdate", "SpriteIsPlaying",
                               "SpriteIsFinished", "SpritePlayRandom", "SpriteRender",
                               "SpriteRenderLayer", "SpriteIsLoaded"),
            # `Isaac` 门面：19 个成员都在自己的家族 TU 里（`Options` 的两个字段是值，
            # 不是 handler，所以不在这张表里）。
            # ★ 批次 268 把两条也列进来（`IsaacCountEntities` / `IsaacRunCallbackWithParam`）：
            #   表本身是**部分**清单（其余批次的手写处理器没在这里逐条列），这里只保证
            #   "新加的这两条实现体唯一、且不在旧 TU 里"。
            "isaac_api.cpp": ("IsaacGetFrameCount", "IsaacGetTime", "IsaacDebugString",
                              "IsaacIsInGame", "IsaacRunCallback", "IsaacGetPlayer",
                              "IsaacGetItemConfig", "IsaacFindByType", "IsaacFindInRadius",
                              "IsaacCountEnemies", "IsaacCountBosses", "IsaacWorldToScreen",
                              "IsaacWorldToRenderPosition", "IsaacGetPersistentGameData",
                              "IsaacGetTrinketIdByName", "IsaacGetCallbacks", "IsaacLoadModData",
                              "IsaacSaveModData", "IsaacRenderScaledText", "IsaacCountEntities",
                              "IsaacRunCallbackWithParam"),
        }
        for unit, handlers in owners.items():
            body = (SRC / "interfaces" / "lua" / unit).read_text(encoding="utf-8")
            for handler in handlers:
                with self.subTest(unit=unit, handler=handler):
                    self.assertEqual(body.count(f"int {handler}(lua_State* state) {{"), 1)
                    self.assertNotIn(f"int {handler}(lua_State* state) {{", legacy,
                                     f"{handler} 的实现体同时存在于旧 TU")
        # 旧 TU 也不再保留任何内联注册语句。
        for handler in ("GameIsPaused", "RoomGetType", "ItemPoolGetCollectible", "LevelGetStage",
                        "MusicGetCurrentMusicId", "RngSetSeed", "InputIsButtonTriggered",
                        "AddCallback"):
            with self.subTest(handler=handler):
                self.assertNotIn(f"lua_pushcfunction(state, {handler})", legacy)

    def test_every_owner_registers_from_a_family_unit(self):
        """所有 owner 都从家族 TU 注册，旧 TU 不再自带内联 switch/注册循环。"""
        source = LUA_RUNTIME.read_text(encoding="utf-8")
        expected = {
            "Mod": ("mod_api.cpp", "AttachModMethods"),
            "Game": ("game_api.cpp", "AttachGameMethods"),
            "Level": ("remaining_api.cpp", "AttachLevelMethods"),
            "Room": ("remaining_api.cpp", "AttachRoomMethods"),
            "ItemPool": ("remaining_api.cpp", "AttachItemPoolMethods"),
            "MusicManager": ("music_api.cpp", "AttachMusicMethods"),
            "RNG": ("rng_api.cpp", "AttachRngMethods"),
            "Input": ("input_api.cpp", "AttachInputMethods"),
            "Font": ("font_api.cpp", "AttachFontMethods"),
            # `Vector` 的整套注册（元表 + 运算符 + 可调用的类表）在自己的 TU 里，
            # 所以 `lua_runtime.cpp` 通过 `RegisterVectorApi` 间接调用家族注册函数。
            "Vector": ("vector_api.cpp", "AttachVectorMethods"),
            "Sprite": ("sprite_api.cpp", "AttachSpriteMethods"),
            # `Isaac` 的全局表也由家族 TU 自己建立（`RegisterIsaacApi` 里调
            # `AttachIsaacMethods`），旧 TU 只调用家族入口。
            "Isaac": ("isaac_api.cpp", "AttachIsaacMethods"),
        }
        # 家族自己建表的 owner：旧 TU 里出现的是家族入口名，`Attach*Methods` 只在本 TU。
        family_entry_points = {
            "Isaac": ("isaac::runtime::RegisterIsaacApi(state)", "AttachIsaacMethods(state)"),
        }
        for owner, (unit, function) in expected.items():
            with self.subTest(owner=owner):
                body = (SRC / "interfaces" / "lua" / unit).read_text(encoding="utf-8")
                if owner in family_entry_points:
                    entry_point, attach_call = family_entry_points[owner]
                    self.assertIn(entry_point, source)
                    self.assertIn(attach_call, body)
                else:
                    self.assertIn(f"isaac::runtime::{function}(state)", source)
                self.assertIn(f"std::size_t {function}(lua_State* state) noexcept", body)
                # owner 既可以直接写字面量，也可以通过常量传入。
                self.assertIn("AttachOwnerMethods(state,", body)
                self.assertIn(f'"{owner}"', body)
        self.assertNotIn("AttachCatalogOwnerMethods", source)
        self.assertNotIn("ResolveLuaApiHandler", source)

    def test_family_binding_ids_match_the_catalog(self):
        """家族表里的字面 id 必须与 Catalog 计算出的 id 一致。

        id 对不上时方法只是“静默不注册”，行为测试不一定发现，所以在这里逐条比对。
        """
        domain_bytes = {
            "Global": 0, "Mod": 1, "Game": 2, "Level": 3, "Room": 4,
            "ItemPool": 5, "Music": 6, "Rng": 7, "Persistence": 8, "Input": 9,
            "Diagnostic": 10, "Font": 11, "Vector": 12, "Sprite": 13, "Isaac": 14,
            # `Seeds` 家族（`Game:GetSeeds()` 的返回值），2026-09-12 第五轮加入。
            "Seed": 15,
            # `RuntimeMods`（运行时自带的模组开关菜单控制面），2026-09-16 加入。
            # 两份映射（本处与 `registered_function_names` 里那份）必须同时加。
            "ModMenu": 16,
            # `HUD`（`Game:GetHUD()` 的返回值），批次 207（2026-09-29）加入。
            # 两条绑定行（`IsVisible` / `SetVisible`）落在 `game_api.cpp`。
            "Hud": 17,
        }
        catalog = CATALOG_SOURCE.read_text(encoding="utf-8")
        entry = re.compile(
            r'MakeId\(ApiDomain::(\w+),\s*(\d+),\s*(0x[0-9A-Fa-f]+)\),\s*'
            r'ApiDomain::\w+,\s*"([^"]+)",\s*"([^"]+)"'
        )
        by_owner: dict[str, set[int]] = {}
        for domain, group, sequence, owner, _name in entry.findall(catalog):
            if domain not in domain_bytes:
                continue
            identifier = (domain_bytes[domain] << 24) | (int(group) << 16) | int(sequence, 16)
            by_owner.setdefault(owner, set()).add(identifier)

        # 家族表既可以直接引用本 TU 的 handler，也可以通过过渡 thunk 引用旧 TU。
        # 手写处理器行，外加**字段读取型数据行**（`{0x…, k...Offset, …}`，共享处理器机制）。
        # ★ 批次 303（2026-10-03）：再加上**按 vtable 槽号调用的引擎方法行**
        #   （`{0x…, MakeEngineVtableRowOffset(k...Slot), …}`）—— 它们的第 2 栏既不是
        #   `&handler` 也不是 `k…Offset`，旧正则**看不见**它们，于是"家族绑定行数"会少算。
        #   这正是这条断言的用处：行数对不上时逼人来看一眼（本批就是这么发现的）。
        row = re.compile(
            r"\{\s*(0x[0-9A-Fa-f]{8}),\s*(?:&(?:LuaRuntime::)?(\w+)|k\w+Offset\s*,"
            r"|MakeEngineVtableRowOffset\(k\w+Slot\))"
        )
        unit_owners = {
            "api500_config.cpp": {"ItemConfigCard"},
            "api600_bindings.cpp": {'Global', 'EntityPtr', 'Game', 'EntityPlayer', 'RoomConfigSpawns', 'Room', 'ItemConfig', 'GridEntityDoor', 'CardConfigList', 'RoomConfigEntries', 'ItemConfig_Item', 'PillConfigList', 'Sprite', 'GridEntityRock'},
            "api400_bindings.cpp": {"Entity","EntityPlayer","EntityNPC","EntityPickup","EntityEffect","EntityKnife","EntityLaser","EntityProjectile","EntityTear","Seeds"},
            "api300_bindings.cpp": {"EntityPlayer","Game","Room","Level","PathFinder","Seeds","EntityEffect","ItemConfig","EntityNPC","EntityKnife","EntityLaser","EntityTear","EntityBomb"},
            "api200_bindings.cpp": {"Entity","EntityFamiliar","EntityKnife","EntityTear","EntityPlayer","Game","GridEntityDoor","GridEntityPit","GridEntityPoop","GridEntityPressurePlate","HUD","ItemConfig","Level","PathFinder","Room","Seeds","Sprite"},
            "api100_bindings.cpp": {"EntityPlayer","Entity","EntityFamiliar","EntityPickup","GridEntity","GridEntityDoor","GridEntityRock","Level","Room","ItemPool","Color","Sprite","MusicManager"},
            "rplus_method_bindings.cpp": {"Entity","EntityPlayer","EntityBomb","EntityKnife","EntityLaser","EntityTear","EntityProjectile","Game","Room","GridEntity","GridEntityDoor","PathFinder"},
            "mod_api.cpp": {"Mod"},
            # `Game` 之外还有 `Seeds`（`Game:GetSeeds()` 的返回值，2026-09-12 第五轮加入）：
            # 它的两个方法就落在同一个 TU 里，因为句柄与元表都跟着 `Game` 家族走。
            "game_api.cpp": {"Game", "Seeds", "HUD"},
            # 批次 12（2026-09-16）：`GridEntity` 族（`Room:GetGridEntity()` 的返回值）的绑定表
            # 也住在 `remaining_api.cpp` —— 与 `Room` 同族、同一个 TU。
            #: 批次 284 加 `GridEntityDoor`（门有自己的方法表与目录行 ⇒ 它是独立 owner；
            #: 它与 `GridEntity` 在 PC 里本就是两页；批次 273 曾误以为它收不了，见 `api_catalog.cpp` 的更正）。
            #: 批次 347（2026-10-04）加 `RoomConfigSpawn`（`RoomDescriptor.Data.Spawns:Get(i)`
            #: 的返回值）与 `RoomConfigEntry`（`spawn:PickEntry(r)` 的返回值）—— 两个都住在
            #: `remaining_api.cpp`（与 `Room`/`RoomDescriptor` 同 TU）。
            "remaining_api.cpp": {"Level", "Room", "ItemPool", "GridEntity", "GridEntityDoor",
                                  "RoomConfigSpawn", "RoomConfigEntry"},
            # 批次 045：`SFXManager()` 与 `MusicManager` 同属"声音"域（0x06）⇒ 同一文件两个 owner 是允许的。
            "music_api.cpp": {"MusicManager", "SFXManager"},
            "rng_api.cpp": {"RNG"},
            "input_api.cpp": {"Input"},
            "font_api.cpp": {"Font"},
            "color_api.cpp": {"KColor", "Color"},
            "vector_api.cpp": {"Vector"},
            "sprite_api.cpp": {"Sprite"},
            # `Isaac` 门面（19 行）以及批次 2 的实体只读视图：`Entity`/`EntityPlayer` 的
            # 方法表也在同一个家族 TU 里（元表内的 owner 就是元表名）。批次 2b 加上
            # `ItemConfig`（6 行）与 `ItemConfig_Item`（1 行）；条目的字段
            # （`ID`/`Type`/`Name`/`Description`）走 `__index`，与 `Vector` 的 `X`/`Y` 同例，
            # 不占绑定行。
            #: 批次 281 加 `EntityTear`（`Entity:ToTear()` 的视图 —— 它有自己的元表与方法表，
            #: 所以它也是一个**独立的 owner**）。
            #: 批次 285 加 `EntityNPC`（`Entity:ToNPC()` 的视图 —— 同上，它自己的方法表里放 `Morph`）。
            #: 批次 330（2026-10-03）加 `EntityFamiliar`（`Entity:ToFamiliar()` 的视图 ——
            #: 本批才给它建自己的元表，方法表里放 `FollowParent`/`AddToFollowers`）。
            #: 批次 344（2026-10-04）加 `PathFinder`（`EntityNPC.Pathfinder` 属性的返回值 ——
            #: 它有自己的元表与方法表（`HasPathToPos`），所以是一个**独立 owner**；
            #: ★ 与上面几个"下转视图"不同：它不是某个实体的视图，而是 `Entity_NPC` 里
            #: **内嵌**的 `NPCAI_Pathfinder` 子对象）。
            "bitset128_api.cpp": {"BitSet128"},
            "isaac_api.cpp": {"Isaac", "Entity", "EntityPlayer", "EntityPickup", "EntityTear",
                              "EntityLaser", "EntityNPC", "EntityFamiliar", "PathFinder",
                              #: 批次 388（2026-10-07）：`EntityPlayer:GetEffects()` 的返回值 ——
                              #: PC 里 `TemporaryEffects` 是自己的一个对象类（17 个方法），因此也是
                              #: 一个**独立 owner**。它**没有**新开 domain（照 `PathFinder` 的先例：
                              #: 返回对象不新开域），域仍是 `Isaac`。
                              "TemporaryEffects", "ItemConfig", "ItemConfig_Item", "PersistentGameData"},
            # 2026-09-16：运行时自带的模组开关菜单控制面（`RuntimeMods`，域 `ModMenu`）。
            "mod_menu_api.cpp": {"RuntimeMods"},
        }
        checked = 0
        for unit in ("mod_api.cpp", "game_api.cpp", "remaining_api.cpp",
                     "music_api.cpp", "rng_api.cpp", "input_api.cpp", "font_api.cpp",
                     "color_api.cpp", "vector_api.cpp", "sprite_api.cpp", "isaac_api.cpp",
                     "mod_menu_api.cpp", "bitset128_api.cpp", "rplus_method_bindings.cpp", "api100_bindings.cpp", "api200_bindings.cpp", "api300_bindings.cpp", "api400_bindings.cpp", "api500_config.cpp", "api600_bindings.cpp"):
            body = (SRC / "interfaces" / "lua" / unit).read_text(encoding="utf-8")
            for identifier, _handler in row.findall(body):
                value = int(identifier, 16)
                with self.subTest(unit=unit, api_id=identifier):
                    owners = {owner for owner, ids in by_owner.items() if value in ids}
                    self.assertTrue(
                        owners & unit_owners[unit],
                        f"{identifier} 不属于 {unit} 的 owner（实际 {sorted(owners)}）",
                    )
                checked += 1
        # 35 + `Font` 的 3 个绘制变体 + `Vector` 的 16 行方法
        # （`Vector` 的 X/Y 是字段、运算符在元表里，都不占绑定行）。
        # 54 + `Sprite` 的 16 行（第一步 13 行、第二步 3 行；`SetFrame` 的两个重载合成一行）。
        # 70 + `Isaac` 的 19 行（`Options` 的两个字段是值、没有绑定行，见
        # `test_options_fields_are_registered_as_values`）。
        # 89 + 批次 2 的实体视图 4 行：`Entity.ToPlayer`（1 行）与 `EntityPlayer` 的
        # `HasCollectible`/`GetPlayerType`/`GetData`（3 行）；`EntityPlayer` 的字段
        # （`Position`/`Type`/... ）走 `__index`，与 `Vector` 的 `X`/`Y` 同例，不占绑定行。
        # 93 + 批次 2b 的 ItemConfig 视图 7 行：`ItemConfig` 的
        # `GetCollectible`/`GetTrinket`/`GetCard`/`GetPillEffect`/`IsCollectible`/`HasTags`
        # （6 行）与 `ItemConfig_Item.HasTags`（1 行）；条目的字段
        # （`ID`/`Type`/`Name`/`Description`）同样走 `__index`，不占绑定行。
        # 100 + 批次 3 的 7 行：`Game` 的 `GetNumPlayers`/`GetFrameCount`（2 行，EID 的
        # `OnRender` 早期就要用）、`EntityPlayer` 的
        # `GetOtherTwin`/`GetEffectiveMaxHearts`/`GetSoulHearts`/`GetBrokenHearts`（4 行）与
        # `ItemConfig_Item.IsCollectible`（1 行，EID 在描述构建里无参调用它）；
        # `EntityPlayer.ControllerIndex` 与全局 `Color(...)` / `debug.getinfo` 不占绑定行
        # （前者是 `__index` 里的字段名，后两者在旧 TU 里注册，见 `test_api_catalog` 的
        # "每个注册名都必须在 Catalog 里"那条）。
        # 107 + 批次 4 的 7 行：`Entity` 的 `ToPickup`/`GetData`（2 行）、`EntityPlayer` 的
        # `GetActiveItem`/`GetTrinket`/`GetBabySkin`（3 行，EID 的玩家取值路径）、
        # `EntityPickup.IsShopItem`（1 行；★ 2026-09-29 批次 201 起是**真实现**，不再是安全 stub ——
        # 判据 `Price != 0`，见该条目录注释与 `isaac_api.cpp`）与 `Level.GetCurses`（1 行）。
        # 全局 `GetPtrHash` 在家族 TU 里 `lua_setglobal` 注册、没有绑定行（与 `Color(...)` 同例）。
        # 114 + 批次 5 的 2 行：`Entity.GetSprite`（`Entity` 主 sprite 的只读视图，EID 的
        # `EID:IsAltChoice()` 在宝藏房里必需）与 `Sprite.GetAnimation`（读 `ANM2+0x38` 的当前
        # 动画名）。两者都是真实现，各有绑定行。
        # 116 + 第五轮的 4 行：`Game.GetSeeds`/`Game.GetVictoryLap`（2 行）与
        # `Seeds.IsCustomRun`/`Seeds.GetStartSeed`（2 行）—— EID 的
        # `features/eid_api.lua:2046` 直接 `game:GetSeeds():IsCustomRun()`，
        # 缺一个就让整条 update 回调报错（真机报告 `01789210180`）。
        # 120 + 批次 6（2026-09-12）的 30 行 `EntityPlayer` 成员：EID 逐帧调用
        # （`eid_api.lua:2606` 的 `player:GetPill(0)` 等），缺一个就断整条 update 回调。
        # 150 + `Sprite.GetTexel`（1 行，2026-09-12：EID 的 `IsAltChoice` 逐像素比对要用，
        # 缺它就是"调 nil"、整条渲染链被摘除）。
                # 151 + 批次 7 的 6 行 `Room` 网格成员（2026-09-12）。
        # 158 + 2026-09-14 的 1 行 `EntityPlayer.AddCollectible`（真实现：底座
        # `Entity_Player::AddCollectible` @ `0x292A74`，调用点做入口 4 字节指纹核对，
        # 返回值用 `HasCollectible` 复核实际结果）。
        # 159 + 批次 8（2026-09-15）的 4 行 `Level` 成员：`GetCurrentRoomIndex`/`GetCurrentRoom`
        # （字段读与"与 Game:GetRoom 同一个对象"）、`GetAbsoluteStage`/`IsNextStageAvailable`
        # （各有 Switch 符号 @ `0x3E7F3C` / `0x3DBDBC`，入口 16 字节守卫校验后调用）。
        # 缺口来自 `tools/eid_api_gap_report.py`：EID 的潘多拉魔盒条目
        # （`features/eid_modifiers.lua:197/200`）在描述构建里无条件调用 `GetAbsoluteStage()`，
        # 缺它就是 "attempt to call a nil value"、整条描述回调在那一行中断。
        # 163 + 地基二期（2026-09-15）的 3 行 `Level` 房间描述符成员：
        # `GetCurrentRoomDesc`/`GetRoomByIdx`/`GetRooms`。它们背后是一整条新的读取链
        # （内联描述符数组 + 八个已真机验证的字段偏移），不是单个字段读。
        # 166 + 批次 7（2026-09-15）的 2 行：`EntityPlayer.GetCollectibleCount` 与
        # `ItemConfig_Item.IsTrinket` —— EID 用到而运行时里完全没有的两条。它们走的是**数据行**
        # 形态（`{id, k...Offset, …}`，共享处理器 `FieldApiHandler`），所以上面的计数正则
        # 同时认"手写绑定行"与"数据行"两种形态（见 `registered_ids` 处的注释）。
        # 地基三期（成本压缩）把 5 条既有成员也迁成了数据行，**总数不变**，只是换了登记形态。
        # 168 + 批次 8（2026-09-15）的 1 行 `Room.GetRenderScrollOffset`：
        # EID 用到而运行时里没有的一条；偏移 `+0x1938` 有引擎自身代码的硬证据
        # （见 `tools/layout_tables/room.json` 与布局表复核门禁）。
        # 169 + 批次 9（2026-09-15）的 1 行 `Entity.ToFamiliar`：EID 用它把跟班从候选实体里挑出来。
        # 判据同 `ToPickup`（Type 与 vptr 都要对），vtable 偏移由符号表推出并与既有两个常量互相验证。
        # 170 + 批次 10（2026-09-15）的 1 行 `Room.WorldToScreenPosition`：EID 用它把实体位置
        # 画到屏幕上；换算方式直接取自引擎自己的实现（引擎函数 + 房间滚动 + Game 调整量）。
        # 171 + 批次 11（2026-09-16）的 3 行 `Level` 成员：`GetStageType`/`IsAltStage`（数据行，
        # 读 `Level+0x04`）与 `IsPreAscent`（两个字段的组合判据，手写）。字段证据见
        # `runtime_constants.hpp` 的 `kLevelStageTypeOffset`：`Level::SetStage` 把两个参数
        # 连着写进 `+0x00`/`+0x04`。
        # 174 + 批次 12（2026-09-16）的 2 行 `GridEntity` 成员（`GetVariant`/`GetType`）：
        # EID 的网格描述需要它们；前置是"网格实体视图"这一族本身 —— 同批把
        # `Room:GetGridEntity()` 从"恒返回 nil"（登记在案的偏离）改成真返回。
        # 176 + 批次 13（2026-09-16）的 3 行：`GridEntity.GetRNG`（`0x0E010054`）、
        # `ItemPool.IsPillIdentified`（`0x05010003`）与 `RNG.GetSeed`（`0x07010003`）。
        # 它们就是 EID 缺口表里最后剩下的两条高置信缺口（`spikes:GetRNG():GetSeed()` 需要
        # `GetRNG` 与 `GetSeed` 各一行；`pool:IsPillIdentified(color)` 一行）。
        # 180 + 批次 14（2026-09-16）的一行：`Room.GetFrameCount`（`0x0401000A`）——
        # EID 的背包合成渲染路径无条件调它，之前完全没有，导致拿着背包合成时每帧抛错
        # （真机 `g_LastLuaErrorText` 坐实）。**这是台账 designed 的记账方式：每加一批 +1。**
        # 181 + 4 行（2026-09-16，模组开关菜单的控制面 `RuntimeMods.List/SetEnabled/Save/Reload`）：
        # 这四条**不是 PC API**，是运行时自带菜单脚本自己用的控制面（新域 `ModMenu`）。
        # 记进目录的理由与别人一样：Lua 侧可见的东西必须有单一出处，否则"谁能调什么"就查不清了。
        # 185 + 1 行（2026-09-16）：`RuntimeMods.Report` —— 菜单脚本用它上报"走到哪一步"，
        # 让真机上"按了没反应"能一次读数定位（脚本加载/字体/打开/回调/落盘）。
        # 186 + 1 行（2026-09-18）：`EntityPlayer.AddCoins(int)`（`0x0056`）—— PC 有、我们此前没有，
        # 而"给钱"在本运行时**没有别的通道**（字段写只认 `ControlsCooldown`、没有 `Isaac.Spawn`、
        # `GetNumCoins` 那时还是恒 0 的桩）。同批把 `GetNumCoins` 从桩改成真实现（读
        # `Entity_Player+0x16E0`），**那条是已有行、不占新行**。用途见
        # `docs/改动日志-20260918.md` 的"金币无限测试模组"。
        # 187 + 1 行（2026-09-18 下午）：`Mod.RemoveCallback(int, function)`（`0x0002`）——
        # 回调表由运行时自己维护，所以这条没有任何引擎底座可接（清单里归 `missing_hard`，
        # 理由就是"Switch 侧没有 mod 清单与 Lua 运行时，必须由 Runtime 自己维护回调表"）。
        # EID 在真机上真的会调它（4 处），缺它时那几处报 nil 调用。语义要点：按**函数身份**
        # 摘掉该 id 上的这一条，同 id 其余登记必须留下（EID 一家就登记 5 个 `MC_POST_NEW_ROOM`）。
        # 188 + 1 行（2026-09-18 下午）：`Room.IsMirrorWorld()`（`0x000B`）—— 判据是"当前房间的
        # 维度 == 1"（读 `Level+0x21560`；维度枚举含义出自 PC 文档快照 `RoomDescriptor.md`：
        # 1 = 次级维度 = Downpour/Dross 的镜子维度）。EID 在 `main.lua:839` 无条件调它。
        # 193 + 4 行（2026-09-19 批次 041，为 GoodTrip 补）：`Isaac.GetRoomEntities`（真实现）、
        # `Isaac.ExecuteCommand`（平台降级：Switch 无控制台）、`Input.GetMousePosition` /
        # `Input.IsMouseBtnPressed`（平台降级：Switch 无鼠标）。判据写在各自实现处与
        # `tools/api_catalog.cpp` 那四行的注释里。
        # 197 + 3 行（2026-09-19 批次 045，为 GoodTrip 补）：`Mod:AddPriorityCallback`、
        # `SFXManager:Play`、`SFXManager:IsPlaying`。`Global.CallbackPriority` 是**值型条目**
        # （枚举表，没有 C 函数）⇒ 不进绑定行，与 `Options` 的字段同例。
        # 200 + 1 行（批次 046）：`Room:GetDoor`（GoodTrip 运行期要它；先对齐形状、恒 nil）。
        # 201 + 2 行（批次 050）：只接"开地图 + 传送必需"的两个引擎方法 ——
        #   `EntityPlayer:SetShootingCooldown`（缺它"开地图后按方向键"在画图之前报错）、
        #   `Game:ChangeRoom`。
        # 203 + 6 行（批次 051）：050 因**代码段预算**被砍掉的六个全部接回来了 ——
        #   `AnimateHappy`/`AnimateSad`/`GetBlackHearts`/`Room:PlayMusic`/`Level:AddCurse`/
        #   `Level:RemoveCurses`。它们**不占代码**：走的是本批新做的"引擎方法数据行"机制
        #   （共享处理器 + 每 API 16 字节只读数据，见 `interfaces/lua/engine_method_api.hpp`）。
        # 209 + 1 行（批次 055）：`Game:StartRoomTransition` —— GoodTrip 传送的**默认路径**
        #   （`trip.lua:207`）。它 5 个参数、含玩家实体指针，是"通用跳板 + 签名描述符"
        #   （`engine_call_trampoline.*`）的第一个真实消费者：**仍不占代码**，只多一行数据行
        #   与一行签名描述符。
        # 210 + 1 行（批次 063）：`Entity:IsFlying()` —— GoodTrip 的诅咒房判定
        #   （`trip.lua:90`）要用它；同样**不占代码**：一条数据行 + 一行签名描述符
        #   （`EngineCallShape::Bool0`，返回种类里的 Bool 在批次 055 就位）。
        # 211 + 1 行（批次 065）：`Entity:TakeDamage`（**手写**：float + `EntityRef` 句柄 +
        #   按接收者选入口）。同一批还加了全局 `EntityRef(entity)` —— 那是**全局**构造器，
        #   不进家族绑定表（与 `Vector`/`Color`/`Sprite` 同例），所以这里只 +1。
        #   两件都是 GoodTrip 诅咒房过路费（`trip.lua:70`）的必需项。
        # 批次 106 加了一条（`Level:GetStartingRoomIndex`）⇒ 212 → 213。
        # 批次 137（2026-09-26）加了三条（The Specialist for Good Items 的"跳舞 + 放歌"）：
        #   `MusicManager:UpdateVolume`（`0x06010006`，手写 handler：接收者是回调 Manager 派生的
        #   Music 对象，数据行那套解不出）、`EntityPlayer:AddNullCostume`（`0x0E01005B`）与
        #   `EntityPlayer:TryRemoveNullCostume`（`0x0E01005C`）—— 后两条是引擎方法数据行，
        #   **不占代码** ⇒ 213 → 216。
        # 批次 138（2026-09-26）再加一条：`MusicManager:Play`（`0x06010007`，手写 handler：
        #   同族 `UpdateVolume` 的理由 —— 接收者是回调 Manager 派生的 Music 对象）⇒ 216 → 217。
        # 批次 139（2026-09-26）再加一条：`Isaac:GetCostumeIdByPath`（`0x0E01005D`，手写 handler：
        #   遍历 null 道具向量比 `+0x88`）⇒ 217 → 218。
        # 批次 140（2026-09-26）再加一条：`Game:GetPlayer`（`0x0201000C`，手写 handler —— 走
        #   与 `Isaac.GetPlayer` 同一条链、但越界口径按 Game.md 正文夹到最后一个）⇒ 218 → 219。
        # 批次 148（2026-09-26）再加一条：`Isaac:GetMusicIdByName`（`0x0E01005E`，手写 handler ——
        #   遍历 `Music + 0x3D8` 的曲目表比条目起点的名字串，返回下标）⇒ 219 → 220。
        # 批次 195（2026-09-29）再加两条：`RNG:RandomInt`（`0x07010004`）与
        #   `RNG:RandomFloat`（`0x07010005`）—— 两条都是**手写 handler**（接收者是 `RNG` userdata，
        #   数据行那套解不出 userdata 接收者），底座是引擎的 `RNG::Random(uint)` @ `0x44E3E8` /
        #   `RNG::Random()` @ `0x44E4C0`（Hook 安装时按 16 字节入口指纹核对后发布，见
        #   `runtime_constants.hpp` 与 `hook_manager.cpp` 的 `TryInstallRngBindings`）。
        #   为什么必须补：本批把四条 `Get*RNG` 从恒 nil 改成真句柄之后，链上最后一环就是这两条 ——
        #   语料里的 Trinity 写的是 `GetCollectibleRNG(BIRTHRIGHT):RandomFloat()`
        #   （`analysis/mod-corpus/Trinity/main.lua:173`），缺它就是 `attempt to call a nil value`
        #   ⇒ 220 → 222。
        # 批次 195（2026-09-29）再加一条：`Isaac:ScreenToWorld`（`0x0E01005F`，手写 handler ——
        #   引擎里**没有**反向入口，PC 自己也就是地把四步算式做完；WIDTH/HEIGHT/POINTSCALE
        #   运行期从引擎 GOT 槽读，见 `runtime_constants.hpp` 与 `remaining_api.cpp` 的
        #   `TransformScreenToWorldPosition`）⇒ 222 → 223。
        # 批次 207（2026-09-29）再加 11 行（MCM 前置 API；每一行的 id 都由 `api_catalog.cpp`
        # 的对应条目背书）：
        #   * `isaac_api.cpp` 7 行 —— `Entity:IsActiveEnemy`（`0x0E010060`，引擎方法数据行，
        #     形状 `BoolOpt1`）、`Entity:HasEntityFlags`（`0x0E010061`，字段行，
        #     逐位判 `Entity+0x1B8`）、`Entity:ToProjectile`（`0x0E010062`，手写 handler：
        #     接收者是 `Entity` userdata，数据行那套解不出）、
        #     `Isaac:GetScreenWidth`/`GetScreenHeight`/`GetEntityTypeByName`/`GetEntityVariantByName`
        #     （`0x0E010063`..`0x0E010066`，四条手写 handler）；
        #   * `game_api.cpp` 3 行 —— `Game:GetHUD`（`0x0201000D`）与 `HUD:IsVisible`/`SetVisible`
        #     （`0x11010001`/`0x11010002`，接收者是 `HUD` userdata ⇒ 手写 handler）；
        #   * `remaining_api.cpp` 1 行 —— `Room:IsClear`（`0x0401000E`，两级解引用）。
        #   ⇒ 223 + 11 = **234**。
        # 批次 214（2026-09-30）再加 6 行（两个 MCM 变体各缺的那几条，id 由 `api_catalog.cpp` 背书）：
        #   * `sprite_api.cpp` 3 行 —— `Sprite:Reset`（`0x0D010013`，`ANM2::Reset @0x4A4724`）、
        #     `Sprite:GetLayerCount`（`0x0D010014`，读 `ANM2+0xB0`）、
        #     `Sprite:GetDefaultAnimationName`（`0x0D010015`，读动画表第一条的名字）；
        #     中文版 MCM（工坊 2494192799）的 `scripts/filepathhelper.lua` 要这三条，**不在 pcall 里**；
        #   * `game_api.cpp` 3 行 —— `Seeds:HasSeedEffect`（`0x0F010004`，走 `std::set<eSeedEffect>` 树查找）、
        #     `Seeds:AddSeedEffect`（`0x0F010005`）/`Seeds:RemoveSeedEffect`（`0x0F010006`）——
        #     后两条是"不抛错的空实现 + 探针"（引擎唯一入口吃名字字符串，拿不到枚举→名字；见偏离台账）。
        #   ⇒ 234 + 6 = **240**。
        # 批次 238（2026-09-30）再加 28 行 —— **语料模组适配第一波**（用户指令：把
        # `analysis/mod-corpus/` 里那 17 个模组全部接上）。逐模组缺口报告去重后共 152 条
        # "运行时里找不到"的 API，这一波做的是"形状与接收者都现成"的 28 条，
        # 全部落成**引擎方法数据行**（`Entity` 5 / `EntityPlayer` 13 / `Room` 6 / `Level` 2 / `Game` 2）：
        # `Entity:IsBoss`/`IsEnemy`/`Kill`/`Remove`/`Update`；
        # `EntityPlayer:AddBrokenHearts`/`AddCard`/`AddEternalHearts`/`AddHearts`/`AddTrinket`/
        # `EvaluateItems`/`GetExtraLives`/`NeedsCharge`/`Revive`/`SetActiveCharge`/`SetCard`/
        # `TryRemoveTrinket`/`UseCard`；
        # `Room:GetRoomConfigStage`/`HasCurseMist`/`IsAmbushActive`/`IsCurrentRoomLastBoss`/
        # `RemoveDoor`/`Update`；`Level:Update`/`UpdateVisibility`；`Game:AddDevilRoomDeal`/`Update`。
        # 底座与逐条证据（mangled + 偏移 + 入口指纹）见 `runtime_constants.hpp` 的批次 238 段。
        # ⇒ 240 + 28 = **268**。
        # 批次 239（2026-09-30）再加 18 行 —— **语料模组适配第二波 A 批**（流水线：
        # `docs/批量恢复API的流水线.md`，待办清单 `dist/api-restore-worklist.json` 里
        # `engine_row` 那 18 条）。全部落成**引擎方法数据行**：
        # `Room` 6（`RemoveGridEntity`/`GetGridCollision`/`SetGridPath`/`SpawnClearAward`/
        # `DestroyGrid`/`TurnGold`）、`Level` 4（`SetStage`/`SetNextStage`/`GetPlanetariumChance`/
        # `GetRandomRoomIndex`）、`MusicManager` 7（`DisableLayer`/`IsLayerEnabled`/`EnableLayer`/
        # `VolumeSlide`/`GetQueuedMusicID`/`PitchSlide`/`ResetPitch`）、`Game` 1（`GetGreedBossWaveNum`）。
        # 底色与逐条证据（mangled + 偏移 + 入口指纹 + PC 契约页:行号）见 `runtime_constants.hpp` 的批次 239 段。
        # ⇒ 268 + 18 = **286**。
        # 批次 240（2026-09-30）再加 5 行 —— **语料模组适配第二波 C 批的名字表一族**
        # （`Isaac.GetItemIdByName` / `GetCardIdByName` / `GetPillEffectByName` /
        # `GetPlayerTypeByName` / `GetChallengeIdByName`）。表源 `tools/isaac_name_source/*.txt`
        # → `tools/generate_isaac_name_tables.py` → `runtime/source/program/isaac_name_tables.*`。
        # ⇒ 286 + 5 = **291**。
        # 批次 241（2026-09-30）：再加 1 行 —— `ItemConfig_Item:IsRune()`（`0x0E01007E`，
        # 为 EID 的三处无保护调用 `GetCard(id):IsRune()` 补；缺它时每帧一个 Lua 错误）
        # ⇒ 291 + 1 = **292**。
        # 批次 242（2026-09-30）再加 5 行 —— **C 批剩项：下转族**
        # （`Entity:ToNPC` / `ToTear` / `ToLaser` / `ToEffect` / `ToKnife`）。
        # 判据 = `vptr` 精确等于 `base + <类>VtableOffset`；常量 = vtable 符号 + 0x10。
        # ⇒ 292 + 5 = **297**。
        # 批次 249（2026-10-01）再加 3 行 —— **Room 三个返回 Vector 的方法**（手写）。
        # ⇒ 297 + 3 = **300**。
        # 批次 252（2026-10-01）再加 5 行 —— **A 组 2 + B 组 3**（`MusicManager:Queue` /
        # `Crossfade`、`Game:ShowHallucination`、`Room:SpawnGridEntity`、
        # `EntityPlayer:RemoveCollectible`，全部数据行）⇒ 300 + 5 = **305**。
        # 批次 253（2026-10-01）再加 2 行 —— `Room:IsPositionInRoom` / `Game:CharmFart`
        # （带 `Vector2 const&` 参数、走数据行）⇒ 305 + 2 = **307**。
        # 批次 254（2026-10-01）再加 5 行 —— **语料 API 恢复**：`Game:MoveToRandomRoom`、
        # `ItemPool:RemoveCollectible`、`EntityPlayer:AddKeys`/`AddGoldenKey`/`AddGoldenBomb`，
        # 全部是引擎方法数据行（含本批新增的 `FieldReceipt::ItemPool` 与两种形状）。
        # ⇒ 307 + 5 = **312**。
        # 批次 259（2026-10-01）再加 4 行 —— **Room 四条位置类方法**（`FindFreePickupSpawnPosition` /
        # `GetClampedPosition` / `FindFreeTilePosition` / `GetDoorSlotPosition`，全部手写：
        # 返回 `Vector2`、跳板只支持标量返回）⇒ 312 + 4 = **316**。
        # 批次 261（2026-10-01）再加 3 行 —— **`glue_compose` 桶的三条**（`Isaac:GetChallenge` /
        # `Isaac:ConsoleOutput` / `Isaac:HasModData`，都是 `Isaac` 全局表上的手写处理器）
        # ⇒ 316 + 3 = **319**。
        # 批次 262（2026-10-01）再加 2 行 —— `Isaac:GetFreeNearPosition` / `Isaac:GridSpawn`
        # （由 Room 原语拼出来的两条，定义在 `remaining_api.cpp`）⇒ 319 + 2 = **321**。
        # 批次 265（2026-10-02）再加 1 行 —— `Isaac:GetSoundIdByName`（遍历引擎音效表反查编号）
        # ⇒ 321 + 1 = **322**。
        # 批次 267（2026-10-02）再加 1 行 —— `Game:SpawnParticles`（手写：`ColorMod const&` 要从
        # Lua 的 `Color` 构造，形状机制表达不了）⇒ 322 + 1 = **323**。
        # 批次 268（2026-10-02）再加 2 行 —— `glue_compose` 桶最后两条：`Isaac:CountEntities`
        # （手写：直接转调引擎 `EntityList::CountSpawned`，4 个实参 + 接收者放不进任何形状）
        # 与 `Isaac:RunCallbackWithParam`（手写：`Isaac.RunCallback` 那一族的带过滤值变体）
        # ⇒ 323 + 2 = **325**。
        # 批次 269（2026-10-02）再加 4 行 —— `blocked_decision` 桶清空：
        # `Isaac:RenderText` / `Isaac:GetTextWidth`（复用批次 026 那条默认字体绘制路径）
        # 与 `Room:GetRenderMode` / `Room:GetRenderSurfaceTopLeft`（两条 `Placeholder`）
        # ⇒ 325 + 4 = **329**。
        # 批次 270（2026-10-02）再加 1 行 —— `Level:QueryRoomTypeIndex`（手写；
        # `needs_new_shape` 桶最后一条）⇒ 329 + 1 = **330**。
        # 批次 271（2026-10-02）再加 3 行 —— `needs_new_receiver` 桶头部三条
        # （`Entity:SetColor` / `Entity:AddCharmed` / `EntityPlayer:UseActiveItem`）
        # ⇒ 330 + 3 = **333**。
        # 批次 272（2026-10-02）再加 1 行 —— `GridEntity:Init`（`needs_new_receiver`
        # 桶里做完 271 三条之后剩下调用点最多的一条，15 处）⇒ 333 + 1 = **334**。
        # 批次 273（2026-10-02）再加 8 行 —— `needs_new_receiver` 桶里参数最简单的一批
        # （AddFreeze/AddPoison + 玩家族六条）⇒ 334 + 8 = **342**。
        # 批次 274（2026-10-02）再加 12 行 —— 清桶批（Entity 3 + EntityPlayer 8 + Seeds 1）
        # ⇒ 342 + 12 = **354**。
        # 批次 275（2026-10-02）再加 2 行 —— `Entity:AddEntityFlags` / `ClearEntityFlags`
        # ⇒ 354 + 2 = **356**。
        # 批次 276（2026-10-02）再加 8 行 —— `GridEntity:GetGridIndex` + 7 条子类转换
        # ⇒ 356 + 8 = **364**。
        # 批次 277（2026-10-02）再加 1 行 —— `Entity:GetEntityFlags` ⇒ 364 + 1 = **365**。
        # 批次 278（2026-10-02）再加 5 行（EntityPlayer 族）⇒ 365 + 5 = **370**。
        # 批次 279（2026-10-02）再加 3 行（Sprite overlay 三条）⇒ 370 + 3 = **373**。
        # 批次 280（2026-10-02）再加 2 行（Sprite:GetDefaultAnimation / Stop）⇒ 373 + 2 = **375**。
        # 批次 281（2026-10-02）再加 1 行（`EntityTear:ChangeVariant`，视图化第一条）
        # ⇒ 375 + 1 = **376**。
        # 批次 282（2026-10-02）再加 1 行（`EntityLaser:SetActiveRotation`）⇒ 376 + 1 = **377**。
        # 批次 283（2026-10-02）再加 4 行（`Sprite` 的四条「按名字查询」）⇒ 377 + 4 = **381**。
        # 批次 284（2026-10-02）再加 5 行（`EntityPlayer` 两条 0 参布尔查询 + `GridEntityDoor`
        # 三条 —— 后者是新 owner，它自己一张表）⇒ 381 + 5 = **386**。
        # 批次 285（2026-10-02）再加 2 行（`EntityNPC:Morph` + `EntityPickup:Morph`；前者是新
        # owner `EntityNPC` —— `Entity:ToNPC()` 从本批起压 `EntityNPC` 视图）⇒ 386 + 2 = **388**。
        # 批次 286（2026-10-02）再加 1 行（`Entity:IsVulnerableEnemy`）⇒ 388 + 1 = **389**。
        # ★ 那一次的计数改了、**这段说明漏了**，本批（287）补记。
        # 批次 287（2026-10-02）再加 3 行（`EntityPlayer` 的"心数 / 金色钥匙"：
        # `GetBoneHearts` / `GetEternalHearts` / `HasGoldenKey`，三条都是**字段读取型数据行**）
        # ⇒ 389 + 3 = **392**。
        # 批次 288（2026-10-02）再加 3 行（`EntityPlayer` 的方向三条：`GetHeadDirection` /
        # `GetFireDirection` 走**字段读取型数据行**，`GetMovementDirection` 走**引擎方法数据行**）
        # ⇒ 392 + 3 = **395**。
        # 批次 289（2026-10-02）再加 2 行（`Room` 的两条边界访问器 `GetTopLeftPos` /
        # `GetBottomRightPos`，都走**字段读取型数据行** —— 引擎里没有同名访问器）
        # ⇒ 395 + 2 = **397**。
        # 批次 290（2026-10-02）再加 1 行（`Room:GetRoomShape`，同样走**字段读取型数据行**，
        # 只是接收者是「当前房间 → 描述符 → 房间配置对象」两跳链的末端）⇒ 397 + 1 = **398**。
        # 批次 291（2026-10-02）再加 4 行（`Room` 的四个只读状态量：`GetBossID` / `IsFirstVisit` /
        # `IsAmbushDone` / `HasWaterPits`，全部走**字段读取型数据行**）。
        # ★ 本批新增**一个接收者** `FieldReceipt::RoomDescriptor`（当前房间 → `Room+0x8` 一跳的末端；
        #   `IsAmbushDone`/`HasWaterPits` 的字段住在描述符的 `Flags` 位掩码上）与
        #   **一个新种类** `FieldKind::BoolBit`（读 `u32`、单独测 `offset2` 指定的那一位）。
        # ⇒ 398 + 4 = **402**。
        # 批次 292（2026-10-02）再加 2 行（`Room:GetBackdropType` 走**字段读取型数据行**读
        # `Room+0x21B0`；`Room:SetClear(boolean)` 走本批新收的 `FieldKind::BoolBitWrite`
        # —— 往描述符 `Flags` 的 bit0 写实参，是本机制第一条**有副作用**的行）。
        # ★ 同一批还把 `BackdropType` 枚举表生成进运行时（`DocLuaEnumData`），
        #   那是与 `Room:GetBackdropType()` 配对的另一半（枚举表**不占绑定行**）。
        # ⇒ 402 + 2 = **404**。
        # 批次 293（2026-10-03）再加 3 行 —— `Entity` 的三个相邻状态字节
        # （`IsVisible` 0x1C1 / `Exists` 0x1C2 / `IsDead` 0x1C3，合 32 处）。
        # 三条都走**字段读取型数据行**、接收者是既有的 `FieldReceipt::Entity`
        # ⇒ 本批**零新机制**（没有新 kind、没有新接收者）。
        # ⇒ 404 + 3 = **407**。
        # 批次 294（2026-10-03）再加 3 行 —— `Level:GetPreviousRoomIndex()` /
        # `Level:GetLastBossRoomListIndex()`（两条字段行）+ `GridEntityDoor:IsRoomType(RoomType)`
        # （**手写处理器**，登记在 `kGridEntityDoorHandlers[]`）。
        # ⇒ 407 + 3 = **410**。
        # 批次 295（2026-10-03）再加 2 行 —— `Room:GetDecorationSeed()` /
        # `Room:GetSpawnSeed()`（两条字段行读描述符上的两个种子）。
        # ⇒ 410 + 2 = **412**。
        # 批次 296（2026-10-03）再加 3 行 —— `EntityNPC:GetChampionColorIdx()` /
        # `EntityNPC:GetBossColorIdx()`（两条字段行，读 `Entity_NPC` 的 `+0xD10`/`+0xD24`）
        # + `EntityPlayer:GetActiveCharge(ActiveSlot = SLOT_PRIMARY)`（**手写处理器**，
        # 登记在 `kEntityPlayerHandlers[]`）。
        # ⇒ 412 + 3 = **415**。
        # 批次 297（2026-10-03）再加 2 行 —— `Game:GetStateFlag(int Flag)` /
        # `Level:GetStateFlag(int Flag)`（两条字段行，走新机制 `FieldKind::BoolBitArrayOfArg`；
        # `Game` 那一条是本族**第一张**字段行表 `kGameFieldApis`，住在 `game_api.cpp`）。
        # ⇒ 415 + 2 = **417**。
        # 批次 298（2026-10-03）再加 1 行 —— `GridEntity:GetSprite()`（**手写处理器**，
        # 登记在 `kGridEntityHandlers[]`：它要交回 `Sprite` 句柄，数据行产出不了句柄）。
        # ⇒ 417 + 1 = **418**。
        # 批次 299（2026-10-03）再加 1 行 —— `EntityPlayer:HasFullHearts()`（**手写处理器**，
        # 登记在 `isaac_api.cpp` 的 EntityPlayer 绑定表里；「有效上限」那段抽成了共享函数）。
        # ⇒ 418 + 1 = **419**。
        # 批次 300（2026-10-03）再加 2 行 —— `Game:SetStateFlag` / `Level:SetStateFlag`
        # （两条字段行，走新种类 `FieldKind::BoolBitArrayOfWriteArg`）。
        # ⇒ 419 + 2 = **421**。
        # 批次 301（2026-10-03）再加 1 行 —— `EntityPlayer:AddCacheFlags(CacheFlag)`
        # （**一条字段行**，走新种类 `FieldKind::U32OrWithArg`：读改写 `Entity_Player + 0x1958`
        # 的 `_cacheFlags`；**0 字节代码**）。
        # ⇒ 421 + 1 = **422**。
        # 批次 302（2026-10-03）再加 2 行 —— `Room:SetFloorColor` / `Room:SetWallColor`
        # （两条字段行，走新种类 `FieldKind::ColorModWrite`：把 `Color` 句柄转成 44 字节
        # `ColorMod` 整块写进 `Room+0x7968` / `+0x7994`；**0 字节代码**）。
        # ⇒ 422 + 2 = **424**。
        # 批次 303（2026-10-03）再加 2 行 —— `Entity:CanShutDoors` / `EntityNPC:CanShutDoors`
        # （两条**引擎方法行**，走新约定"按 vtable 槽号调用"：`offset` 最高位置 1、低 31 位 = 槽号。
        # 槽号从 Switch 的 `_ZTV` 读出；**0 字节代码**，但共享处理器多了一支"算目标地址"）。
        # ⇒ 424 + 2 = **426**。
        # 批次 304（2026-10-03）再加 2 行 —— `GridEntity:Destroy(boolean)` / `GridEntity:PostInit()`
        # （两条**引擎方法行**，同样走"按 vtable 槽号调用"：`GridEntity` 的槽位是
        # `vptr + 槽号*8`，槽号来自 `_ZTVGridEntity`；**0 字节代码**）。
        # ⇒ 426 + 2 = **428**。
        # 批次 305（2026-10-03）再加 3 行 —— `MusicManager:Disable` / `Enable` / `IsEnabled`
        # （三条**字段数据行**，落在 `Music + 0x3F0` 那一个字节上；前两条走新种类
        # `FieldKind::BoolWriteConst`（写常量、不收实参）、第三条走既有的 `Bool`；**0 字节代码**）。
        # ⇒ 428 + 3 = 431；批次 306 加 `Seeds:GetStageSeed` / `GetNextSeed` ⇒ 433；
        #   批次 307 ⇒ 434；批次 308 ⇒ 435；批次 309 加 `Sprite:GetFilename` ⇒ 436；
        #   批次 310（2026-10-03）加 `Room:GetAliveBossesCount` ⇒ 437；
        #   批次 311（2026-10-03）加 `Room:GetAliveEnemiesCount` ⇒ 438；
        #   批次 312（2026-10-03）加 `EntityPlayer:IsCoopGhost`（只读字段数据行，读
        #   `Entity_Player + 0x284C` 一个字节 ⇒ `FieldKind::Bool`；**0 字节代码**）⇒ **439**。
        #   批次 313（2026-10-03）加 `Level:HasBossChallenge` / `Level:GetCanSeeEverything`
        #   （两条只读字段数据行，读 `Level + 0x08` / `+0x11` 各一个字节 ⇒ `FieldKind::Bool`；
        #   **0 字节代码**）⇒ 441。
        #   批次 314（2026-10-03）加 `EntityNPC:IsChampion`（只读字段数据行，读
        #   `Entity_NPC + 0xD0F` 一个字节 ⇒ `FieldKind::Bool`；**0 字节代码**）⇒ 442。
        #   批次 315（2026-10-03）加 `Entity:Die`（**写侧**字段数据行：往 `Entity + 0x1C3`
        #   写常量 1 ⇒ `FieldKind::BoolWriteConst`，与 305 的 `Music:Enable/Disable` 同形；
        #   **0 字节代码**）⇒ **443**。
        #   批次 316（2026-10-03）加 `Entity:GetDropRNG`（只读字段数据行读 `Entity + 0x3D8`
        #   那 16 字节 `RNG`、压 `kRngMetatable` 句柄 ⇒ 本批新开的 `FieldKind::RngSnapshot`；
        #   新机制只在共享处理器里加一次，这一行本身仍是 16 字节数据）⇒ **444**。
        #   批次 321（2026-10-03）加 `GridEntity:Update`（按 vtable 槽号虚调用，槽 3；
        #   接收者/形状都沿用批 304 的 ⇒ **零新机制**）⇒ **445**。
        #   批次 324（2026-10-03）加 `EntityNPC.ThrowSpider`（静态调用，挂在**全局类表**上）⇒ **446**。
        #   批次 325 加 `EntityLaser.ShootAngle`（同机制，第二条静态行）⇒ **447**。
        #   批次 326 加 `EntityPlayer:FireTechLaser`（实例方法 + FloatDefaultOne）⇒ **448**。
        #   批次 327（2026-10-03）加 `Room:IsDoorSlotAllowed`（只读字段数据行：按 Lua 实参给的
        #   门位测 `RoomConfig::Room.Doors`（`Data+0x40`）的第 n 位 ⇒ 沿用 `FieldKind::BoolBitArrayOfArg`
        #   与既有的 `FieldReceipt::RoomConfigData`；**0 字节代码**）⇒ **449**。
        #   批次 328（2026-10-03）加 `EntityPlayer:GetShootingInput` / `GetShootingJoystick`
        #   （两条**手写处理器**：引擎返回 `Vector`（两个 float 的 HFA，走 `s0`/`s1`）⇒ 跳板表达不了，
        #   照 `Room:GetCenterPos` 的先例手写；两条在 PC 上共用同一个绑定 VA `0x741B00`）⇒ **451**。
        #   批次 330（2026-10-03）加 `EntityFamiliar:FollowParent` / `AddToFollowers`
        #   （两条**引擎方法行**，无参/返回 void ⇒ 复用现成 `EngineCallShape::Void0`；
        #   ★ 本批真正的产出是给 `EntityFamiliar` 建了自己的视图元表，否则方法没有地方挂）⇒ **453**。
        #   批次 332（2026-10-03）加 `EntityPlayer:GetMovementJoystick`（**手写处理器**：引擎返回
        #   `Vector`（HFA）⇒ 跳板表达不了；★ 引擎里那个函数叫 `get_movement_input`，**名字不一样**，
        #   靠逐条对照函数体定案）⇒ **454**。
        #   批次 333（2026-10-03）加 `Entity:MultiplyFriction`（字段数据行，走**新开**的
        #   `FieldKind::FloatMultiplyArg` —— 第一条"浮点读改写"；读改写的是一格 float =
        #   `Entity + 0x340` 的本帧工作摩擦）⇒ **455**。
        #   批次 334（2026-10-03）加 `EntityPlayer:CheckFamiliar`（**手写处理器**：5 个形参、
        #   后两个是**非 0 缺省值**（`nil`/`-1`）⇒ 数据行那条路缺两种表达能力 ⇒ 手写；
        #   第 3 参的 `RNG&` 复用 `Level:QueryRoomTypeIndex` 那套"句柄裸存储当引擎对象"）⇒ **456**。
        #   批次 335（2026-10-03）加 3 行 —— 交接第八份 §3「批 A」：
        #   `EntityPlayer:ChangePlayerType` / `EntityPlayer:DischargeActiveItem`（两条**引擎方法行**，
        #   共用本批新开的形状 `VoidIntBoolOpt1`：`void(this, i32, bool)`、尾部 1 个可省；
        #   契约各写 1 个形参、引擎符号都是 2 格 ⇒ 按符号取）与 `Seeds:SetStartSeed`（**引擎方法行**，
        #   形状 `Void1`；★ 这三条共同点 = 接收者那一格：本批新开了 `FieldReceipt::Seeds`
        #   （`Game + kGameSeedsObjectOffset`），前两条走既有的 `FieldReceipt::EntityPlayer`）
        #   ⇒ 456 + 3 = **459**。
        #   批次 336（2026-10-03 深夜）加 2 行 —— 交接第八份 批 B/批 C 的"纯取证批"：
        #   `Room:GetTintedRockIdx`（**字段数据行**：`Room+0xE90` 一个 i32，`FieldKind::I32`
        #   + 既有的 `FieldReceipt::Room`；PC 绑定 `0x427750` 是 `mov eax,[ecx+0x764]; ret`）
        #   与 `Entity:CollidesWithGrid`（**字段数据行**：`Entity+0x1EC` 一个字节，
        #   `FieldKind::Bool` + 既有的 `FieldReceipt::Entity`；PC 绑定 `0x641420` 是
        #   `mov al,[ecx+0x188]; ret`）⇒ **0 字节代码**，本批没开任何新机制。
        #   ⇒ 459 + 2 = **461**。
        #   批次 337（2026-10-04 凌晨）加 1 行 —— 交接第八份 §3 批 C 里那条处数最大的
        #   `EntityPlayer:FireTear(...)`（**手写处理器**，**4 处**）：契约 7 个形参、引擎只有 5 个
        #   （三个布尔被打包成一个 `u32`，且 `Velocity` 是**按值**的 HFA），而其中**两个缺省值是 `true`**
        #   ⇒ 数据行那条路缺两种表达能力 ⇒ 手写（与 328/332/334 同一笔账）⇒ 461 + 1 = **462**。
        #   批次 339（2026-10-04）加 1 行 —— `EntityFamiliar:FireProjectile(Vector Dir)`
        #   （**手写处理器**）：引擎真身 `Entity_Familiar::fire_projectiles(Vector2 const&, bool)`
        #   @ `0xB06FC` 逐字存在，契约只 1 个形参、引擎多一个隐藏 bool ⇒ 转发
        #   ⇒ 462 + 1 = **463**。
        #   批次 340（2026-10-04）加 2 行 —— `Game:Spawn(...)` 与 `Isaac.Spawn(...)`
        #   （**两条手写**：引擎 `Game::SpawnEx` 的第 8 个形参**走栈**、通用跳板填不了；
        #   且 `Isaac.Spawn` 的形参序与引擎不同、还要现取非 0 随机种子）
        #   ⇒ 463 + 2 = **465**。
        #   批次 341（2026-10-04）加 4 行 —— 上一批那四份并行取证报告落地的四条：
        #   `Entity:IsInvincible()`（**字段数据行**：`Entity+0x384` 一个字节，`FieldKind::Bool`
        #     + 既有的 `FieldReceipt::Entity`）；`EntityLaser:SetMaxDistance(float)`
        #     （**字段数据行**：写 `Entity_Laser+0x4F8`，**本批新开** `FieldKind::FloatFromArg`）；
        #   `EntityPlayer:TryRemoveTrinketCostume(TrinketType)`（**引擎方法行**，形状 `Void1`
        #     —— 真身是同族 `TryRemoveCostume(eTrinketType) @ 0x2A25B0`）；
        #   `EntityFamiliar:FollowPosition(Vector Pos)`（**引擎方法行**，**本批新开**形状
        #     `VoidVector2Ref` —— 真身 `follow_position(Vector2 const&) @ 0xAFCC0`）
        #   ⇒ 465 + 4 = **469**。★ 本批**新增一档字段行的 owner** `EntityLaser`
        #   （`test_field_api_rows` 的 `OWNERS_BY_RECEIPT["Entity"]` 同步加了它）。
        #   批次 342（2026-10-04）加 3 行（两条字段行 + 一个与属性共用的 getter）
        #   ⇒ 469 + 3 = **472**；批次 343（2026-10-04）加 3 行（字段行 + 两张列表）
        #   ⇒ 472 + 3 = **475**（这两批的逐条说明见各自的改动日志节）。
        #   批次 344（2026-10-04）加 2 行 —— `EntityPlayer:AnimateCollectible(...)`
        #   （**手写处理器**：字符串实参 + 两个**非空字符串缺省** ⇒ 数据行那条路缺两种表达能力；
        #    真身是**改名**后的 `Entity_Player::AnimatePickup(eCollectibleType, char const*, char const*)
        #    @ 0x2DD150`；★★ 缺省必须传**字面串**，引擎的 `ANM2::Play` 对 null 无检查 ⇒ 传 null 会崩）
        #   与 `PathFinder:HasPathToPos(Vector, boolean)`（**引擎方法数据行**，**本批新开**形状
        #    `BoolVector2RefBool`（纯数据、0 代码）+ `FieldReceipt::PathFinder`（严格校验句柄类型）；
        #    真身 `NPCAI_Pathfinder::HasPathToPos(Vector2 const&, bool) const @ 0x42F6CC`）
        #   ⇒ 475 + 2 = **477**。★ 本批**新增一档 owner** `PathFinder`
        #   （上面 `isaac_api.cpp` 的 owner 集合同步加了它）。
        #   批次 345（2026-10-04）加 1 行 —— `Isaac.Explode(Vector pos, Entity source, float damage)`
        #   （**手写处理器**：引擎真身 `Game::BombExplosionEffects @ 0x355C68` 有 **9 个形参**
        #    ⇒ **第 9 格 `bool` 走栈**、通用跳板填不了；且第 4 格是 16 字节**按值**的 `bitset128_t`）
        #   ⇒ 477 + 1 = **478**。
        #   批次 346（2026-10-04）加 1 行 —— `Entity:AddVelocity(Vector[, boolean IgnoreTimeScale])`
        #   （**手写纯算法**：Switch 侧**没有可调真身**（符号 0 命中 / NRO 原始字节 0 命中）
        #    ⇒ 按 PC 绑定 `0x422B60` 的算式直接读写三格；★★ **推翻旧负结果**「两侧摩擦模型不同」）
        #   ⇒ 478 + 1 = **479**。
        #   批次 347（2026-10-04）加 1 行 —— `RoomConfigSpawn:PickEntry(float r)`（**手写处理器**：
        #   数据行要同时新开 `EngineReturnKind` + `EngineCallShape` + `FieldReceipt` 三处枚举，
        #   而 `RoomConfigSpawn` 只有这一个方法 ⇒ 手写少动三处账；连同 `Data.Spawns` 换真容器、
        #   `RoomConfigSpawn`/`RoomConfigEntry` 两个视图、以及一条 `Partial/design` 偏离）
        #   ⇒ 479 + 1 = **480**。★ 本批**新增两档 owner**（上面 owner 集合同步加了）。
        #   ★ 批次 388（2026-10-07）加 **17** 行 —— `TemporaryEffects`（`EntityPlayer:GetEffects()`
        #   的返回值）的 17 个方法，owner = `"TemporaryEffects"`（上面 owner 集合同步加了）：
        #   6 条走 `kTemporaryEffectsEngineRows`（引擎方法数据行）、11 条走 `kTemporaryEffectsHandlers`
        #   （6 条 Add*/Remove* 手写 + 5 条占位）；域仍是 `Isaac`。⇒ 480 + 17 = **497**。
        # 2026-10-09：7个SFX占位已变为真实引擎方法数据行，497+7=504；
        # 每行id仍由上面的逐条catalog核验覆盖。
        # 2026-10-13追加真实健康/武器/颜色/HUD绑定56项：539→595。
        # 2026-10-14：100个真实方法绑定；595→695。
        # 2026-10-16：新增Card:IsCard与ItemPool:IdentifyPill两条实际绑定。
        self.assertEqual(checked, 983, "家族绑定行数应与已登记 API 数一致")

    def test_options_fields_are_registered_as_values(self):
        """`Options` 的两个字段是**值**而不是方法：Catalog 里有条目、绑定表里没有绑定行。

        它们没有 `lua_CFunction`，所以 `test_family_binding_ids_match_the_catalog` 覆盖不到；
        这里直接断言 `RegisterOptionsTable` 真的让两个字段可读，否则 Catalog 里就多出
        两条幽灵 API。

        **两个字段的取数方式刻意不同**（按 2026-09-14 的实现改写，原断言是"两个名字都必须以
        `lua_setfield(state, -2, "<名字>")` 出现"，那是 `Language` 还被当静态值缓存时的写法）：

        * `HUDOffset` 是**静态值**：建表时一次性 `lua_setfield` 写进去；
        * `Language` 是**动态字段**：引擎中途换语言后必须能读到新值，所以不能在建表时缓存，
          改由元表 `__index`（`OptionsIndex`）每次现读
          （`ReadCurrentLanguageCode` → `Manager::GetLanguageCode()`，读不到时兜底 `"en"`）。

        因此这里按两条路径分别断言，并**反过来断言 `Language` 不得被静态缓存** —— 那正是
        这条动态设计要防的失效模式。
        """
        source = LUA_RUNTIME.read_text(encoding="utf-8")
        family = (SRC / "interfaces" / "lua" / "isaac_api.cpp").read_text(encoding="utf-8")
        self.assertIn("isaac::runtime::RegisterOptionsTable(state)", source)
        self.assertIn("std::size_t RegisterOptionsTable(lua_State* state) noexcept", family)
        labels = catalog_owner_labels()
        self.assertIn("Options", labels)
        for name in ("HUDOffset", "Language", "FoundHUD"):
            with self.subTest(field=name):
                self.assertIn(name, catalog_api_names())

        # ① 静态值：建表时直接写入。
        self.assertNotIn('lua_setfield(state, -2, "HUDOffset")', family)
        self.assertIn('std::strcmp(key, "HUDOffset") == 0', family)
        self.assertIn('lua_pushcfunction(state, OptionsNewIndex)', family)
        # ② 动态字段：元表 `__index` 指向 `OptionsIndex`，且它确实服务 `Language`。
        self.assertIn("lua_pushcfunction(state, OptionsIndex)", family)
        self.assertIn('lua_setfield(state, -2, "__index")', family)
        self.assertIn('std::strcmp(key, "Language") == 0', family)
        self.assertNotIn('lua_setfield(state, -2, "Language")', family)

    def test_every_registered_lua_name_is_in_the_catalog(self):
        known = catalog_api_names() | catalog_owner_labels()
        # CppContainer是PC类元数据命名空间，实际方法属于返回对象，非新增调用API。
        # 路径与__class在真实Lua的test_lua_item_config_list_views中核对。
        known |= {"CppContainer"}
        missing = sorted((registered_function_names() | registered_global_names()) - known)
        self.assertEqual(missing, [], f"以下 API 已在 lua_runtime.cpp 注册但不在 Catalog：{missing}")

    def test_catalog_has_no_phantom_apis(self):
        registered = registered_function_names() | registered_global_names()
        # `Options` 的两个字段是值型条目：没有 `lua_CFunction`，绑定表里也不该有绑定行。
        # 它们的注册由 `test_options_fields_are_registered_as_values` 覆盖。
        # 新增已发布动态值字段；无幽灵条目的判据保持不变，真实读写由test_lua_options_foundhud覆盖。
        value_only = {"HUDOffset", "Language", "AnnouncerVoiceMode", "FoundHUD"}
        phantom = sorted(catalog_api_names() - registered - value_only)
        self.assertEqual(phantom, [], f"Catalog 中存在运行时不注册的 API：{phantom}")

    def test_catalog_behaviour_on_host(self):
        compiler = host_compiler()
        if compiler is None:
            self.skipTest("需要宿主 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="runtime-api-catalog-") as temporary:
            directory = Path(temporary)
            source = directory / "catalog.cpp"
            binary = directory / "catalog"
            source.write_text(DRIVER, encoding="utf-8")
            compile_result = subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(SRC),
                    str(source),
                    str(SRC / "interfaces" / "lua" / "api_catalog.cpp"),
                    "-o",
                    str(binary),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run_result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run_result.returncode, 0, run_result.stdout + run_result.stderr)
            self.assertIn("CATALOG_CHECKS_PASSED", run_result.stdout)


if __name__ == "__main__":
    unittest.main()

# 2026-10-09更正：HUDOffset同样为动态字段，旧说明保留，测试拒绝静态缓存。

# 2026-10-09：新增PGD:Unlocked真实绑定，504→505，owner沿用Isaac域。
