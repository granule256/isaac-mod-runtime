"""指纹从原版NRO独立对照，避免夹具与声明同时写反却一起通过。"""
import re,struct,unittest
from pathlib import Path

class NativeEntryWords(unittest.TestCase):
    def test_literal_entry_words_match_original_instructions(self):
        root=Path(__file__).resolve().parents[2]
        source=(root/'runtime/source/runtime_constants.hpp').read_text()
        blob=next(root.glob('The Binding of Isaac_*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        values={n:int(v,16)for n,v in re.findall(r'constexpr\s+(?:std::)?(?:uintptr_t|uint32_t|u32)\s+(\w+)\s*=\s*(0x[0-9a-fA-F]+)',source)}
        checked=0;mismatches=[]
        for name,word in values.items():
            if not name.endswith('EntryWord')or not word:continue
            offset=values.get(name[:-len('EntryWord')]+'Offset')
            if offset is None or not 0<=offset<=len(blob)-4:continue
            checked+=1;actual=struct.unpack_from('<I',blob,offset)[0]
            if actual!=word:mismatches.append((name,hex(offset),hex(word),hex(actual)))
        self.assertGreater(checked,100,'必须实际覆盖原NRO的标量指纹')
        self.assertEqual(mismatches,[],'原始入口指纹与代码不符；不可用同一个声明常量给夹具铺代码')
