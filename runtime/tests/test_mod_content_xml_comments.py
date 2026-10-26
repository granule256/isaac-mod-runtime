"""真实名字解析器处理XML注释的回归；不修改作者原件、不启动全量门禁。"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include "program/mod_content_names.hpp"
#include <fstream>
#include <iterator>
#include <string>
#include <cstdio>
int main(int argc, char** argv) {
    if (argc < 3) return 2;
    std::ifstream input(argv[1], std::ios::binary);
    if (!input) return 3;
    const std::string xml((std::istreambuf_iterator<char>(input)), {});
    using namespace isaac::runtime;
    const bool pocket = std::string(argv[2]) == "pocket";
    const auto file = pocket ? ModContentFileKind::PocketItems : ModContentFileKind::Items;
    const auto family = pocket ? ModContentNameFamily::Card : ModContentNameFamily::Trinket;
    const auto stored = IngestModContentXml(file, "comments-test", xml.data(), xml.size());
    const auto& stats = ModContentNameStatistics();
    std::printf("{\"stored\":%u,\"consumed\":%u,\"malformed\":%u,\"ids\":[",
                stored, stats.consumedIds, stats.malformedFiles);
    for (int i = 3; i < argc; ++i) {
        const std::string name(argv[i]);
        std::printf("%s%d", i == 3 ? "" : ",", LookupModContentName(family, name.data(), name.size()));
    }
    std::puts("]}");
}
'''


class ModContentXmlCommentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-xml-comments-")
        cls.directory = Path(cls.temporary.name)
        source = cls.directory / "harness.cpp"
        source.write_text(HARNESS)
        cls.binary = cls.directory / "harness"
        subprocess.run([
            "c++", "-std=c++17", "-I" + str(ROOT / "runtime/source"),
            str(ROOT / "runtime/source/program/mod_content_names.cpp"), str(source),
            "-o", str(cls.binary),
        ], check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def parse(self, text, queries=(), family="items"):
        path = self.directory / "input.xml"
        path.write_bytes(text if isinstance(text, bytes) else text.encode())
        result = subprocess.run([str(self.binary), str(path), family, *queries],
                                check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def assert_valid(self, result, count, ids):
        self.assertEqual(result, {"stored": count, "consumed": count,
                                  "malformed": 0, "ids": ids})

    def test_comment_before_root_can_contain_unpaired_quotes(self):
        result = self.parse('<!-- Guppy\'s "notes -->'
                            '<items><trinket name="First"/></items>', ["First"])
        self.assert_valid(result, 1, [190])

    def test_inner_comment_does_not_add_fake_items_or_shift_ids(self):
        result = self.parse('<items><trinket name="First"/>'
                            '<!-- > <trinket name="Phantom"/> Guppy\'s note -->'
                            '<trinket name="Second"/></items>',
                            ["First", "Second", "Phantom"])
        self.assert_valid(result, 2, [190, 191, -1])

    def test_trailing_comment_does_not_reject_the_complete_items_file(self):
        result = self.parse('<items><trinket name="Brittle Penny"/></items>'
                            '<!-- Guppy\'s note -->', ["Brittle Penny"])
        self.assert_valid(result, 1, [190])

    def test_card_comment_uses_the_same_xml_rules(self):
        result = self.parse('<pocketitems><card name="First"/>'
                            '<!-- > <card name="Phantom"/> " -->'
                            '<rune name="Second"/></pocketitems>',
                            ["First", "Second", "Phantom"], "pocket")
        self.assert_valid(result, 2, [98, 99, -1])

    def test_real_auri_items_original_keeps_both_trinket_names(self):
        original = (ROOT / "dist/character-hair-pause-20261026/auri-user-original/"
                           "2283703372/content/items.xml").read_bytes()
        self.assert_valid(self.parse(original, ["Brittle Penny", "Hansen Penny"]),
                          108, [211, 212])

    def test_unterminated_comment_is_still_rejected(self):
        result = self.parse('<items><trinket name="First"/></items>'
                            '<!-- broken <trinket name="Phantom"/>', ["First", "Phantom"])
        self.assertEqual(result, {"stored": 0, "consumed": 0,
                                  "malformed": 1, "ids": [-1, -1]})

    def test_truncated_real_tag_is_still_rejected(self):
        result = self.parse('<items><trinket name="First"', ["First"])
        self.assertEqual(result, {"stored": 0, "consumed": 0,
                                  "malformed": 1, "ids": [-1]})


if __name__ == "__main__":
    unittest.main()
