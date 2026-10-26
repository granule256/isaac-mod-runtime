"""新旧ELF的owner名字表严格按符号大小读取，不越界造名字。"""
import importlib.util
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))

def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/f'{name}.py')
    loaded=importlib.util.module_from_spec(spec);sys.modules[name]=loaded
    spec.loader.exec_module(loaded);return loaded

class OwnerDiagnosticCapacityTests(unittest.TestCase):
    def test_live_reader_uses_exact_old_and_new_symbol_sizes(self):
        perf=module('rt_perf_now')
        class Device:
            base=0x10000
            def __init__(self,size):
                self.syms={} if size is None else {'g_ModOwnerNames':(0x100,size)}
                self.calls=[]
            def read(self,addr,size):self.calls.append((addr,size));return b'x'*size
        for size in (2048,258*64,None,65):
            dev=Device(size);data=perf.read_owner_names(dev)
            valid=size in (2048,258*64)
            self.assertEqual(len(data),size if valid else 0)
            self.assertEqual(dev.calls,[(0x10100,size)] if valid else [])

    def test_gdb_old_and_new_decode_only_complete_slots(self):
        reader=module('read_device_state_via_gdb')
        for slots in (32,258):
            raw=bytearray(slots*64)
            raw[(slots-1)*64:(slots-1)*64+4]=b'last'
            words=[int.from_bytes(raw[i:i+8],'little') for i in range(0,len(raw),8)]
            values={'mod_owner_names':words}
            self.assertEqual(reader.owner_name_table(values),[(slots-1,'last')])
            self.assertEqual(reader.owner_display_name(values,slots-1),'last')
            self.assertEqual(reader.owner_display_name(values,slots),'')

    def test_gdb_request_uses_elf_size_and_skips_unknown(self):
        reader=module('read_device_state_via_gdb')
        reader.SYMS['g_ModOwnerNames']=0x100
        for size in (2048,258*64,0,65):
            reader.MOD_OWNER_NAMES_BYTES=size
            requests,_=reader.build_requests(0x10000,0x20000,0)
            names=[r for r in requests if r[0]=='mod_owner_names']
            self.assertEqual(names,[('mod_owner_names',0x10100,size//8)]
                             if size in (2048,258*64) else [])
            self.assertFalse(any(r[0]=='g_ModOwnerNames' for r in requests))
