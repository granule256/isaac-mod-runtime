#!/usr/bin/env python3
"""修正ChallengeAPI d5c7bff主入口遗留的旧目录引用；不改其已迁移的startingpills实现。"""
from pathlib import Path
import argparse,hashlib
ORIGINAL_SHA256='9a27a043fe9953a541ec36bcc081c98e9b0848dbc54b12047586bbbfd5fb61af'
OLD=b"include('scripts.challengeapi.goals.hooks.tags.init')"
NEW=b"-- startingpills is already loaded by scripts.challengeapi.goals.hooks.init."
def repair(source:bytes, hooks:bytes)->bytes:
 if hashlib.sha256(source).hexdigest()!=ORIGINAL_SHA256:
  raise ValueError('ChallengeAPI主入口版本与已审查的d5c7bff不一致')
 if source.count(OLD)!=1 or hooks.count(b"include('scripts.challengeapi.goals.hooks.startingpills')")!=1:
  raise ValueError('真实startingpills入口或旧引用数量不符')
 return source.replace(OLD,NEW)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
 hooks=a.source.parent/'scripts/challengeapi/goals/hooks/init.lua'
 result=repair(a.source.read_bytes(),hooks.read_bytes());a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(result)
 print(hashlib.sha256(result).hexdigest())
if __name__=='__main__':main()
