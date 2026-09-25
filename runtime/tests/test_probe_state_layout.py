"""门禁：探针的诊断字面**三处必须一致** —— C++ 结构体、初值列表、读数工具的读取宽度。

## 为什么要有它（这条是"已知的坑"，只是以前没人踩）

探针的诊断字是一个**按固定顺序排的 u32 数组**，读数工具**按偏移**解它（没有名字、没有版本号）。
于是有三个地方必须同时改对，而它们分散在两个文件、三种写法里：

1. `native_mods_menu_probe.cpp` 的 `struct NativeModsMenuProbeState`（真正的布局）；
2. 同一个文件里那句**聚合初始化**（值个数必须等于字段个数 —— 少了会**静默补 0**，
   多了编译就红，所以危险的是"少"）；
3. `tools/read_device_state_via_gdb.py` 里读这个符号的**字（8 字节）个数**
   —— 少读 ⇒ 最后几格在读数里根本不存在，而打印那一段是用 `len(raw) >= N*4` 判的，
   于是**整段诊断会静静地不显示**，看起来像"探针没跑 / 这一批没数据"。

第 2、3 条都栽过或差点栽（2026-09-22 批次 058 加 15 格时，初值列表少补了两个 0）。
⇒ 把它变成机器判据：三处一起数，谁不同步就红。

另外还核对 `.hpp` 里那份"给人看的视图结构"（`NativeModsMenuProbeView`）：
它虽然不是布局的真身，但它是**读数的说明书**，字段顺序与名字必须与 .cpp 那份**逐格对齐**
（2026-09-22 的 058 就是把 [67]..[81] 同时写进两处，容易漏一处）。
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CPP = ROOT / "runtime" / "source" / "probe" / "native_mods_menu_probe.cpp"
HPP = ROOT / "runtime" / "source" / "probe" / "native_mods_menu_probe.hpp"
READER = ROOT / "tools" / "read_device_state_via_gdb.py"
STATE_NAME = "NativeModsMenuProbeState"


def fields_of(text: str, struct_name: str) -> list[str]:
    match = re.search(rf"struct {struct_name} \{{(.*?)\n\}};", text, re.S)
    assert match is not None, f"{struct_name} 没找到"
    return re.findall(r"^\s*std::uint32_t\s+(\w+);", match.group(1), re.M)


def initializer_values(text: str) -> list[str]:
    match = re.search(rf"g_{STATE_NAME}\{{(.*?)\}};", text, re.S)
    assert match is not None, "诊断字的聚合初始化没找到"
    return [value for value in re.split(r"[,\s]+", match.group(1)) if value]


class ProbeStateLayoutTests(unittest.TestCase):
    def test_initializer_lists_every_field(self):
        text = CPP.read_text(encoding="utf-8")
        fields = fields_of(text, STATE_NAME)
        values = initializer_values(text)
        self.assertTrue(fields, "字段一个都没解析到（正则过期了？）")
        self.assertEqual(
            len(values), len(fields),
            f"聚合初始化给了 {len(values)} 个值、结构体有 {len(fields)} 个字段"
            "（少了会静默补 0，读数里表现为「最后几格莫名是 0」）",
        )

    def test_reader_reads_the_whole_state(self):
        text = READER.read_text(encoding="utf-8")
        fields = fields_of(CPP.read_text(encoding="utf-8"), STATE_NAME)
        match = re.search(
            r"\('native_mods_probe', base \+ SYMS\['native_mods_probe'\], (\d+)\)", text)
        self.assertIsNotNone(match, "读数工具里那条读数没找到")
        words = int(match.group(1))
        bytes_read = words * 8  # 这台机器上按 8 字节字读
        self.assertGreaterEqual(
            bytes_read, len(fields) * 4,
            f"读数只读了 {bytes_read} 字节，而诊断字有 {len(fields) * 4} 字节"
            " ⇒ 最后几格读不到、打印那一段会静静地不显示",
        )
        self.assertLess(bytes_read - len(fields) * 4, 8,
                        "读数宽度比诊断字多出一整个字以上（多半是忘了同步）")

    def test_view_documentation_matches_the_real_layout(self):
        real = fields_of(CPP.read_text(encoding="utf-8"), STATE_NAME)
        view = fields_of(HPP.read_text(encoding="utf-8"), "NativeModsMenuProbeView")
        self.assertEqual(
            view, real,
            "`.hpp` 里那份「给人看的视图」与 `.cpp` 的真实布局逐格对不上了"
            "（它是读数的说明书，必须同名同序）",
        )

    def test_cells_are_documented_with_their_index(self):
        """每一格都要在注释里写明自己的下标（`// [NN]`）—— 读数对不上时全靠它定位。"""
        lines = HPP.read_text(encoding="utf-8").splitlines()
        missing = []
        index = 0
        for line in lines:
            match = re.match(r"\s*std::uint32_t\s+(\w+);", line)
            if match is None:
                continue
            if f"[{index}]" not in line:
                missing.append((index, match.group(1)))
            index += 1
        self.assertEqual(missing, [], f"这几格没写下标：{missing}")


if __name__ == "__main__":
    unittest.main()
