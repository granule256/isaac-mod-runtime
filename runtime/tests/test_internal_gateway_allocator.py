"""直接包含生产纯头，验证固定中继空间分配与过期计划拒绝。"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = r'''
#include "relay/internal_gateway_allocator.hpp"
#include <cassert>
#include <type_traits>
using namespace isaac::runtime::relay;
static_assert(!std::is_copy_constructible_v<InternalGatewayAllocator>);
static_assert(!std::is_copy_assignable_v<InternalGatewayAllocator>);
static_assert(!std::is_move_constructible_v<InternalGatewayAllocator>);
static_assert(!std::is_move_assignable_v<InternalGatewayAllocator>);
int main() {
    InternalGatewayAllocator packed;
    for (std::size_t i=0;i<32;++i) {
        const auto a=packed.Plan(false);
        const auto repeated=packed.Plan(false);
        assert(a.valid && a.index==i && a.offset==i*32 && a.end==(i+1)*32);
        assert(repeated.valid && repeated.index==a.index && repeated.offset==a.offset && repeated.end==a.end);
        assert(packed.count()==i && packed.used()==i*32);
        assert(packed.Commit(a));
    }
    assert(packed.count()==32 && packed.used()==1024);
    assert(!packed.Plan(false).valid && !packed.Plan(true).valid);
    assert(!packed.Commit(packed.Plan(false)) && packed.count()==32 && packed.used()==1024);

    InternalGatewayAllocator mixed;
    const auto first=mixed.Plan(false);
    assert(mixed.Commit(first));
    const auto stale=mixed.Plan(false);
    const auto page=mixed.Plan(true);
    assert(page.valid && page.index==1 && page.offset==0x1000 && page.end==0x1020);
    assert(mixed.count()==1 && mixed.used()==32);
    assert(mixed.Commit(page));
    assert(!mixed.Commit(stale));
    const auto next=mixed.Plan(false);
    assert(next.offset==0x1020 && next.end==0x1040 && mixed.Commit(next));
    assert(!mixed.Commit(first));
    assert(mixed.count()==3 && mixed.used()==0x1040);

    InternalGatewayAllocator pages;
    for (std::size_t i=0;i<16;++i) {
        const auto a=pages.Plan(true);
        assert(a.valid && a.index==i && a.offset==i*0x1000 && a.end==i*0x1000+32);
        assert(pages.Commit(a));
    }
    assert(pages.count()==16 && pages.used()==0xf020);
    // 最后一页的32字节网关完整落在arena内，下一页起点已越界。
    assert(pages.used()-32==0xf000 && pages.used()<=0x10000);
    const auto exhausted=pages.Plan(true);
    assert(!exhausted.valid && !pages.Commit(exhausted));
    assert(pages.count()==16 && pages.used()==0xf020);
    // 页空间已不足，但元数据和最后一页内的紧密分配仍可用。
    const auto tail=pages.Plan(false);
    assert(tail.valid && tail.offset==0xf020 && tail.end==0xf040);
    assert(pages.Commit(tail));

    InternalGatewayAllocator invalid;
    const auto good=invalid.Plan(false);
    auto bad=good;bad.valid=false;assert(!invalid.Commit(bad));
    bad=good;bad.index=1;assert(!invalid.Commit(bad));
    bad=good;bad.offset=32;bad.end=64;assert(!invalid.Commit(bad));
    bad=good;bad.end=33;assert(!invalid.Commit(bad));
    bad=good;bad.offset=0xffe0;bad.end=0x10000;assert(!invalid.Commit(bad));
    bad=good;bad.offset=0x10000;bad.end=0x10020;assert(!invalid.Commit(bad));
    bad=good;bad.offset=static_cast<std::size_t>(-32);bad.end=0;assert(!invalid.Commit(bad));
    assert(invalid.count()==0 && invalid.used()==0);
    assert(invalid.Commit(good));
    assert(!invalid.Commit(good) && invalid.count()==1 && invalid.used()==32);
}
'''


class InternalGatewayAllocatorTests(unittest.TestCase):
    def test_allocation_contract(self):
        with tempfile.TemporaryDirectory(prefix="internal-gateway-") as tmp:
            source = Path(tmp) / "main.cpp"
            binary = Path(tmp) / "allocator-test"
            source.write_text(SOURCE)
            subprocess.run([os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT / "source"), str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
