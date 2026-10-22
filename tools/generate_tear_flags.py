"""生成PC TearFlags完整128位常量；不允许截成int32或跳过未知表达式。"""
import argparse,hashlib,re
from pathlib import Path

def generate(source,output):
 raw=source.read_bytes();text=raw.decode('utf8');body=re.search(r'^TearFlags = \{(.*?)^\}',text,re.M|re.S)
 if not body:raise ValueError('缺TearFlags表')
 rows=[];seen=set()
 for line in body[1].splitlines():
  line=line.split('--',1)[0].strip()
  if not line:continue
  m=re.fullmatch(r'(TEAR_\w+)\s*=\s*(?:TEARFLAG\((\d+)\)|BitSet128\(0,0\)),?',line)
  if not m:
   count=re.fullmatch(r'(TEAR_EFFECT_COUNT)\s*=\s*(\d+),?',line)
   if count:
    rows.append((count[1],-2,int(count[2])));seen.add(count[1]);continue
   raise ValueError('未知TearFlags表达式：'+line)
  key=m[1];bit=int(m[2]) if m[2] else -1
  if key in seen or not -1<=bit<128:raise ValueError('重复或越界：'+key)
  seen.add(key);rows.append((key,bit,0))
 lines=['#pragma once','// 生成自PC enums.lua；SHA256 '+hashlib.sha256(raw).hexdigest(),'namespace isaac::runtime {','struct TearFlagConstant { const char* name; int bit; int scalar; };','inline constexpr TearFlagConstant kTearFlagConstants[] = {']
 lines += [f'    {{"{key}", {bit}, {scalar}}},' for key,bit,scalar in rows]
 lines += ['};','}']
 output.write_text('\n'.join(lines)+'\n');print(len(rows),'条完整128位标志')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();generate(a.source,a.output)
