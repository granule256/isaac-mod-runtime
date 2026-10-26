#!/usr/bin/env python3
"""取本轮实机截图和状态；复用已核定工具，每次使用前校验当前PID/运行时。"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path('/Users/kelinls/Movies/项目介绍-OpenFilm-20261024/取材记录-修订版')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['screen', 'input', 'eval', 'state'])
    parser.add_argument('label')
    parser.add_argument('value', nargs='?')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('intro_live', ROOT / 'dist/rplus-menu-regression-20261024/hw.py')
    hw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hw)
    hw.OUT = OUT
    assert not (OUT / (args.label + '.json')).exists(), '保留原证据，使用新标签'
    with hw.Live() as live:
        if args.action == 'screen':
            # ASCII远端短名，避免把本地中文标签拼入设备端路径。
            remote = '/config/nxc/intro-' + hashlib.sha256(args.label.encode()).hexdigest()[:12] + '.jpg'
            capture = live.c.command('screen.capture path=' + remote + ' layer=lcd')
            data, stat = live.c.get(remote)
            path = OUT / (args.label + '.jpg')
            assert not path.exists()
            path.write_bytes(data)
            hw.save(args.label, {'capture': capture, 'stat': stat, 'sha256': hashlib.sha256(data).hexdigest()})
            print(path)
        elif args.action == 'input':
            assert args.value.startswith('input.') and 'detach' not in args.value
            result = live.c.command(args.value)
            hw.save(args.label, result)
            print(json.dumps(result, ensure_ascii=False))
        elif args.action == 'eval':
            print(json.dumps(live.evaluate(args.label, args.value), ensure_ascii=False))
        else:
            result = live.snap(args.label)
            print(json.dumps({k: result[k] for k in ['scene', 'frame', 'paused', 'errors', 'reload']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
