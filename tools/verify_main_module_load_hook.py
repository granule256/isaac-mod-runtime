#!/usr/bin/env python3
"""从固定Main重定位/指令/NSO段边界独立核加载钩，Main地址空间不与NRO洞混算。"""
from pathlib import Path
import argparse,hashlib,json,re,struct
import nro_symbols
ROOT=Path(__file__).resolve().parents[1]
def verify(flat:Path,nso:Path,header:Path):
 b=flat.read_bytes();n=nso.read_bytes();h=header.read_text()
 assert n[:4]==b'NSO0'
 value=lambda key:int(re.search(r'\b'+key+r'\s*=\s*(0x[0-9a-fA-F]+)',h)[1],16)
 array=lambda key:bytes(int(x,16)for x in re.findall(r'0x([0-9a-fA-F]{2})',re.search(r'\b'+key+r'=\{([^}]+)\}',h)[1]))
 call,plt,cave,expected=[value(k)for k in ['kCallOffset','kPltOffset','kVeneerOffset','kExpectedBl']]
 assert b[call-16:call+16]==array('kCallGuard')
 assert b[plt:plt+16]==array('kPltGuard')
 word=struct.unpack_from('<I',b,call)[0];assert word==expected and word&0xfc000000==0x94000000
 imm=word&0x3ffffff;imm=imm-0x4000000 if imm&0x2000000 else imm;assert call+imm*4==plt
 a,l,_,br=struct.unpack_from('<4I',b,plt);assert a&0x9f00001f==0x90000010 and l&0xffc003ff==0xf9400211 and br==0xd61f0220
 imm=((a>>5)&0x7ffff)*4+((a>>29)&3);imm=imm-0x200000 if imm&0x100000 else imm;slot=(plt&~0xfff)+imm*0x1000+((l>>10)&0xfff)*8
 copy=bytearray(b);copy[0x10:0x14]=b'NRO0';_,relocs=nro_symbols.parse_dynamic_relocations(bytes(copy))
 rows=relocs['_ZN2nn2ro10LoadModuleEPNS0_6ModuleEPKvPvmi'];assert len(rows)==1 and rows[0].offset==slot and rows[0].relocation_type==1026
 real=struct.unpack_from('<I',n,0x18)[0];mapped=(real+0xfff)&~0xfff
 assert real<=cave and cave+16<=mapped and b[cave:cave+16]==bytes(16)
 return {'ok':True,'namespace':'Main','flat_sha256':hashlib.sha256(b).hexdigest(),'module_id':n[0x40:0x60].hex(),'call':hex(call),'plt':hex(plt),'untouched_got':hex(slot),'padding':[hex(cave),hex(cave+16)],'declared_text_end':hex(real),'mapped_text_end':hex(mapped)}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--main-flat',type=Path,default=ROOT/'dist/native-clear-profile-20261017/original-main-flat.bin');p.add_argument('--main-nso',type=Path,default=next(ROOT.glob('The Binding*/Program #0/0/main'),ROOT/'missing-main'));a=p.parse_args()
 print(json.dumps(verify(a.main_flat,a.main_nso,ROOT/'runtime/source/main_module_load_guards.hpp'),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
