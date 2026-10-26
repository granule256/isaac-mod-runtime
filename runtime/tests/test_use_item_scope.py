"""独立编译纯 C++ 头，验证调用边界与嵌套作用域行为。"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = r'''
#include "domain/callback/use_item_scope.hpp"
#include <cassert>
#include <type_traits>
using namespace isaac::runtime;
static_assert(!std::is_copy_constructible_v<UseItemCallScope>);
static_assert(!std::is_copy_assignable_v<UseItemCallScope>);
static_assert(!std::is_move_constructible_v<UseItemCallScope>);
static_assert(!std::is_move_assignable_v<UseItemCallScope>);
int main() {
    UseItemCallFrame* head = nullptr;
    assert(!TryClaimUseItemBoundary(head, 1));
    {
        UseItemCallScope outer(head, 1, 59, 0xffffffffu, -1, -1);
        auto* parent = head;
        assert(head == &outer.frame() && parent->previous == nullptr);
        assert(parent->item == 59 && parent->postItem == 34);
        assert(parent->flags == 0xffffffffu && parent->slot == -1 && parent->custom == -1);
        assert(!parent->dispatched);
        {
            UseItemCallScope middle(head, 2, 7, 0, 0, 0);
            auto* child = head;
            assert(child->previous == parent && child->postItem == 7);
            assert(!TryClaimUseItemBoundary(head, 1));
            assert(!parent->dispatched && !child->dispatched);
            {
                UseItemCallScope inner(head, 1, 8, 0, 0, 0);
                assert(head->previous == child);
                assert(!TryClaimUseItemBoundary(head, 2));
                assert(!child->dispatched && !parent->dispatched && !head->dispatched);
                assert(TryClaimUseItemBoundary(head, 1));
                assert(!TryClaimUseItemBoundary(head, 1));
                assert(!child->dispatched && !parent->dispatched);
            }
            assert(head == child);
            assert(TryClaimUseItemBoundary(head, 2));
        }
        assert(head == parent);
        assert(TryClaimUseItemBoundary(head, 1));
        // 先认领，再模拟同步回调中的同玩家递归。
        {
            UseItemCallScope recursive(head, 1, 9, 0, 0, 0);
            auto* second = head;
            assert(TryClaimUseItemBoundary(head, 1));
            {
                UseItemCallScope third(head, 1, 10, 0, 0, 0);
                assert(TryClaimUseItemBoundary(head, 1));
                assert(second->dispatched && parent->dispatched);
            }
            assert(head == second && !TryClaimUseItemBoundary(head, 1));
        }
        assert(head == parent && !TryClaimUseItemBoundary(head, 1));
        {
            UseItemCallScope zero(head, 1, 0, 0, 0, 0);
            assert(!TryClaimUseItemBoundary(head, 1) && !head->dispatched);
        }
        {
            UseItemCallScope signedValue(head, 1, static_cast<std::int32_t>(0xffffffffu), 0, 0, 0);
            assert(head->item == -1 && head->postItem == -1);
            assert(TryClaimUseItemBoundary(head, 1));
        }
        assert(head == parent);
    }
    assert(head == nullptr);
}
'''


class UseItemScopeTests(unittest.TestCase):
    def test_portable_scope_behavior(self):
        with tempfile.TemporaryDirectory(prefix="use-item-scope-") as tmp:
            source = Path(tmp) / "main.cpp"
            binary = Path(tmp) / "scope-test"
            source.write_text(SOURCE)
            subprocess.run([os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT / "src"), str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
