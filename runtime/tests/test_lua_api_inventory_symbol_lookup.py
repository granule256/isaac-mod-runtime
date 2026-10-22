"""门禁：API 清单的**符号查找**要能认出引擎的 snake_case 命名（`tools/build_lua_api_inventory.py`）。

## 为什么要有它

清单按**文档里的 Lua 方法名**去符号表里找同名函数。而引擎里**两套命名并存**：

* CamelCase —— `Entity_NPC::GetShootingInput(float)`、`Entity_NPC::GetMovementInput(float)`；
* snake_case —— `Entity_Player::get_shooting_input()`、`Entity_Familiar::follow_parent()`。

原先的索引 `by_class_method` 用**原始方法名**当键 ⇒ 文档里的 `GetShootingInput` 永远查不到
`get_shooting_input`。后果是实打实的：`EntityPlayer:GetShootingInput`（**14 处**、
当时全清单最大的一块）被判成 `no_symbol`、塞进"要先反汇编定性"那一桶，
而它其实**有名字可调**。批次 329 加了"归一化方法名兜底"（`match_kind = normalized_method`）。

## 这个夹具钉住四条

1. ★★ snake_case 能被认出来（`normalized_method`，置信度 **medium**，不冒充 high）；
2. **精确同名仍然优先**（引擎里同时有 `GetShootingInput` 与 `get_shooting_input` 时不许被兜底抢走）；
3. ★★ **不许跨类乱认**：`EntityPlayer` 的候选里没有 `Entity_NPC` ⇒ 只有
   `Entity_NPC::GetShootingInput` 时必须仍然查不到；
4. ★ **差一个字母不算**：`fire_projectile` 与引擎的 `fire_projectiles` 归一化后仍不同 ⇒ 不许被拉进来
   （这条是"兜底不能太贪"的负对照）。

夹具是**合成记录**（不读 NRO、不读文档），所以隔离副本里也跑得动。
"""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "build_lua_api_inventory.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("build_lua_api_inventory_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOL_MODULE = _load_tool()


def record(cls: str, method: str, arity: int = 0) -> dict:
    """一条最小的合成符号记录（字段与真实 `records` 里的同名同义）。"""
    return {
        "class": cls,
        "method": method,
        "namespace": "IsaacRepentance",
        "mangled": f"_Z_synthetic_{cls}_{method}",
        "offset": 0x1000,
        "guard16": "00" * 16,
        "signature": f"{cls}::{method}()",
        "arity": arity,
        "defined": True,
    }


def api(owner: str, name: str, arg_types=()) -> dict:
    return {
        "owner": owner,
        "name": name,
        "kinds": ["Function"],
        "signatures": [f"{name}()"],
        "availability": [],
        "doc_files": [],
        "arg_types": list(arg_types),
    }


class SymbolLookupTests(unittest.TestCase):
    def classify(self, entry: dict, records: list[dict]) -> dict:
        by_class_method, by_method, by_free, by_class_method_norm = (
            TOOL_MODULE.build_symbol_index(records))
        return TOOL_MODULE.classify(
            entry, by_class_method, by_class_method_norm, by_method, by_free,
            {}, {r["class"] for r in records})

    def test_snake_case_symbol_is_found_by_the_normalized_fallback(self):
        """★★ 文档写 `GetShootingInput`、引擎叫 `get_shooting_input` ⇒ 必须能认出来。"""
        result = self.classify(
            api("EntityPlayer", "GetShootingInput"),
            [record("Entity_Player", "get_shooting_input")],
        )
        self.assertEqual(result["category"], "missing_easy")
        self.assertEqual(result["reason_code"], "symbol_available")
        self.assertEqual(result["match_kind"], "normalized_method")
        #: ★ 兜底**不冒充** high：它只是"大小写/下划线不同"，与精确同名分开记。
        self.assertEqual(result["match_confidence"], "medium")
        self.assertEqual(result["switch"]["class"], "Entity_Player")
        self.assertEqual(result["switch"]["method"], "get_shooting_input")

    def test_the_exact_name_still_wins(self):
        """★ 引擎里同时有驼峰与下划线两份时，**精确同名优先**（兜底不许抢）。"""
        result = self.classify(
            api("EntityPlayer", "GetShootingInput"),
            [record("Entity_Player", "get_shooting_input"),
             record("Entity_Player", "GetShootingInput")],
        )
        self.assertEqual(result["switch"]["method"], "GetShootingInput")
        self.assertNotEqual(result["match_kind"], "normalized_method")

    def test_another_classes_method_is_never_borrowed(self):
        """★★ 只有 `Entity_NPC::GetShootingInput` 时，`EntityPlayer` 那条**必须查不到**。

        （这正是批次 328 之前清单报 `no_symbol` 的真实原因之一：引擎里确实有个**同名但不同类**
        的函数，而它不能当 `EntityPlayer:GetShootingInput` 的底座。）
        """
        result = self.classify(
            api("EntityPlayer", "GetShootingInput"),
            [record("Entity_NPC", "GetShootingInput", arity=1)],
        )
        self.assertNotEqual(result["category"], "missing_easy")
        self.assertNotEqual(result["reason_code"], "symbol_available")

    def test_a_one_letter_difference_is_not_matched(self):
        """★ 负对照：`fire_projectile` vs 引擎的 `fire_projectiles` ⇒ **不许**被兜底拉进来。"""
        result = self.classify(
            api("EntityFamiliar", "FireProjectile"),
            [record("Entity_Familiar", "fire_projectiles", arity=2)],
        )
        self.assertNotEqual(result["reason_code"], "symbol_available")

    def test_a_familiar_method_is_found_but_not_for_another_class(self):
        """★ 正负一对：`EntityFamiliar:FollowParent` 认得出，`EntityEffect:FollowParent` 认不出。"""
        records = [record("Entity_Familiar", "follow_parent")]
        found = self.classify(api("EntityFamiliar", "FollowParent"), records)
        self.assertEqual(found["reason_code"], "symbol_available")
        self.assertEqual(found["switch"]["class"], "Entity_Familiar")

        missing = self.classify(api("EntityEffect", "FollowParent"), records)
        self.assertNotEqual(missing["reason_code"], "symbol_available")


if __name__ == "__main__":
    unittest.main()
