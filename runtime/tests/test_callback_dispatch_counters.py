"""门禁：回调派发计数这条读数通道的两头不许漂。

## 为什么要有它

2026-09-18 加的"回调派发计数"是**跨三处**写死的同一件事：

1. `callback_dispatcher.hpp` 的表长（`kCallbackDispatchCounterCount`，由 `kCallbackMaximumId`
   推出 ⇒ 74）；
2. `callback_dispatcher.cpp` 里三个**全局符号的名字**（设备读数工具按符号名取偏移，
   名字必须是 `isaac::runtime` 命名空间下的短名，不能落进匿名命名空间）；
3. `tools/read_device_state_via_gdb.py` 的偏移表、符号名映射、读多少个字、以及要读哪几个地址。

这三处任何一处单独改动，现象都是**读数骗人**（读到别人的变量或读到 0），而不是报错 ——
本项目已经因为"偏移表过期"误读过两次。所以这里把能自动核的都钉住：

* 表长：头文件的定义 == 读数工具的常量 == `kCallbackMaximumId + 1`；
* 符号名：读数工具里手写的 mangled 名 == 按头文件里的名字算出来的 mangled 名；
* 读数工具**真的请求了**这三个地址（防止"加了表忘了读"）；
* 累加点在派发器的**唯一入口**：`Dispatch` 与 `DispatchOwner` 各一处，一处都不能少
  （少了就等于某条派发路径不计入，而"计数全 0"会被读成"事件没送到"）；
* 读数工具里登记了名字的 id，必须在 `callback_descriptor.hpp` 里真有对应常量。

（与项目其它源码门禁同一形态：不做 C++ 解析，只做受控的文本提取。）
"""

import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DISPATCHER_HPP = ROOT / "runtime" / "src" / "application" / "callback" / "callback_dispatcher.hpp"
DISPATCHER_CPP = ROOT / "runtime" / "src" / "application" / "callback" / "callback_dispatcher.cpp"
DESCRIPTOR = ROOT / "runtime" / "src" / "domain" / "callback" / "callback_descriptor.hpp"
MOD_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "mod_api.cpp"
READER = ROOT / "tools" / "read_device_state_via_gdb.py"

#: 读数工具里那三个全局的**符号名映射键**。名字变了这里也要改 —— 门禁会核对 mangled 名。
COUNTER_SYMBOL_KEYS = (
    "g_CallbackDispatchCounts",
    "g_LastDispatchedCallbackId",
    "g_CallbackDispatchGeneration",
)


def load_reader():
    spec = importlib.util.spec_from_file_location("read_device_state_via_gdb", READER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def callback_ids() -> dict:
    """`callback_descriptor.hpp` 里的 `kCallbackXxx = N` → {N: 名字}。"""
    text = DESCRIPTOR.read_text(encoding="utf-8")
    return {int(value): name
            for name, value in re.findall(r"inline constexpr CallbackId (kCallback\w+) = (\d+);",
                                          text)
            if name != "kCallbackMaximumId"}


def has_dispatch_site_names() -> set:
    """`mod_api.cpp` 的 `HasDispatchSite()` 名单 → {常量名去掉 `kCallback` 前缀}。

    这是"到底有没有派发点"的**代码侧真值源**（设备侧那份诊断字就是按它报的），
    所以读数工具的名字表拿它核对，而不是另立一份。
    """
    text = MOD_API.read_text(encoding="utf-8")
    start = text.index("bool HasDispatchSite(")
    body = text[start:text.index("}", start)]
    return set(re.findall(r"id\s*==\s*kCallback([A-Za-z0-9_]+)", body))


class CallbackDispatchCounterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = DISPATCHER_HPP.read_text(encoding="utf-8")
        cls.source = DISPATCHER_CPP.read_text(encoding="utf-8")
        cls.reader = load_reader()

    def test_counter_table_length_matches_between_header_and_reader(self):
        text = DESCRIPTOR.read_text(encoding="utf-8")
        match = re.search(r"inline constexpr CallbackId kCallbackMaximumId = (\d+);", text)
        self.assertIsNotNone(match, "`kCallbackMaximumId` 不见了 —— 门禁的解析要跟着改")
        maximum = int(match.group(1))
        # 头文件里的写法：`static_cast<std::size_t>(kCallbackMaximumId) + 1`
        self.assertIn("static_cast<std::size_t>(kCallbackMaximumId) + 1", self.header)
        self.assertEqual(
            self.reader.CALLBACK_DISPATCH_COUNTER_COUNT, maximum + 1,
            f"读数工具的表长与 `kCallbackMaximumId + 1`（={maximum + 1}）不一致 "
            f"⇒ 会少读/多读一段内存",
        )

    def test_hardcoded_symbol_names_match_the_declared_names(self):
        """读数工具里手写的 mangled 名，必须与按声明名算出来的完全一致。

        为什么值得核：那三个名字是手抄的（`_ZN5isaac7runtime24g_...E`），抄错一位的后果不是
        报错，而是**安静地读到别的变量**（`_SymbolTable.__missing__` 只在名字完全找不到时才
        记账）。核一遍只要几微秒。
        """
        declared = set(re.findall(r"extern std::atomic<[^>]+> (g_\w+)", self.header))
        self.assertEqual(
            declared, set(COUNTER_SYMBOL_KEYS),
            f"头文件声明的全局与门禁登记的不一致：声明 {sorted(declared)}",
        )
        mapping = self.reader.SYM_ELF_NAMES
        for name in COUNTER_SYMBOL_KEYS:
            with self.subTest(symbol=name):
                self.assertIn(name, self.reader.SYMS, f"{name} 没进偏移表")
                self.assertIn(name, mapping, f"{name} 没进符号名映射")
                expected = f"_ZN5isaac7runtime{len(name)}{name}E"
                self.assertEqual(
                    mapping[name], expected,
                    f"{name} 的符号名抄错了：表里是 {mapping[name]}，按名字算应为 {expected}",
                )

    def test_reader_actually_requests_the_counters(self):
        """加了表却忘了请求 ⇒ 读数永远是 0，而 0 会被读成"事件没送到"。"""
        text = READER.read_text(encoding="utf-8")
        for token in ("'callback_dispatch_counts'", "'callback_dispatch_last'",
                      "'callback_dispatch_generation'",
                      "SYMS['g_CallbackDispatchCounts']",
                      "SYMS['g_LastDispatchedCallbackId']",
                      "SYMS['g_CallbackDispatchGeneration']"):
            with self.subTest(token=token):
                self.assertIn(token, text, f"读数工具没有读 {token}")

    def test_every_dispatch_entry_point_counts(self):
        """★ 累加点必须在派发器的**唯一入口**：两条路径各一处，少一处就等于那条路径不计入。

        `Dispatch` 与 `DispatchOwner` 是仅有的两个派发入口（`CallbackDispatcher` 只有这两个
        成员函数）。日后新增第三个入口时这条门禁会红 —— 提醒把它也接上，而不是让计数悄悄漏。
        """
        dispatch = self.source[self.source.index("DispatchReport CallbackDispatcher::Dispatch("):
                               self.source.index("DispatchReport CallbackDispatcher::DispatchOwner(")]
        owner = self.source[self.source.index("DispatchReport CallbackDispatcher::DispatchOwner("):
                            self.source.rindex("} // namespace isaac::runtime")]
        for name, body in (("Dispatch", dispatch), ("DispatchOwner", owner)):
            with self.subTest(entry=name):
                self.assertIn("RecordDispatch(id);", body,
                              f"{name} 没有记派发计数 ⇒ 走这条路的回调在设备上读出来恒为 0")

    def test_reader_callback_names_have_a_matching_constant(self):
        """读数工具里的名字表必须与"到底接没接线"这件事实一致。

        工具里那几个名字是给操作者看的（"这个数字是哪一种回调"）。写错 id 的后果是：
        读数把 `MC_POST_NEW_ROOM` 标在某条我们**没实现**的 id 上，于是现场判断被带到反方向
        —— 2026-09-15 的 `MC_INPUT_ACTION` 误报就是这一类的先例。

        判据用**已有的真值源**：`mod_api.cpp` 的 `HasDispatchSite` 名单 + 常量表。
        * `CALLBACK_NAMES`（已接线）里的每个 id：必须有常量，常量名逐字对得上，
          **并且**那个常量必须出现在 `HasDispatchSite` 名单里；
        * `CALLBACK_NOT_WIRED`（故意没接线）里的每个 id：它的常量**不许**出现在那份名单里。
        """
        ids = callback_ids()
        wired = has_dispatch_site_names()
        self.assertTrue(wired, "`HasDispatchSite` 名单没解析到 —— 门禁失去意义")
        for identifier, name in self.reader.CALLBACK_NAMES.items():
            with self.subTest(callback=name):
                self.assertIn(identifier, ids, f"{name} 的 id={identifier} 在常量表里不存在")
                expected = "kCallback" + name.removeprefix("MC_").title().replace("_", "")
                self.assertEqual(ids[identifier], expected,
                                 f"{name}(id={identifier}) 与常量 {ids[identifier]} 对不上，"
                                 f"按名字应为 {expected}")
                self.assertIn(expected.removeprefix("kCallback"), wired,
                              f"{name} 被标成『已接线』，但 `HasDispatchSite` 名单里没有它")
        for identifier, note in self.reader.CALLBACK_NOT_WIRED.items():
            with self.subTest(callback=note):
                # 两种形态都合法：**有常量但没派发点**（`MC_INPUT_ACTION`，常量在、`HasDispatchSite`
                # 不含它），或**连常量都没有**（`MC_PRE_GAME_EXIT`，压根没实现）。两者的共同要求
                # 是同一条：它不许出现在 `HasDispatchSite` 名单里。
                constant = ids.get(identifier)
                if constant is None:
                    continue
                self.assertNotIn(
                    constant.removeprefix("kCallback"), wired,
                    f"{note}（常量 {constant}）被标成『故意没接线』，但它已经在 `HasDispatchSite` "
                    f"名单里 —— 要么把它挪进 `CALLBACK_NAMES`，要么确认它不该被接线",
                )


if __name__ == "__main__":
    unittest.main()
