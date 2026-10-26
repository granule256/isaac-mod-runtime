#!/usr/bin/env python3
"""参考BcutStr的新格式，在必剪退出后另建底片与可编辑字幕草稿。"""
import copy
import hashlib
import json
import re
import secrets
import shutil
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT = Path('/Users/kelinls/Movies/项目介绍-OpenFilm-20261024')
DRAFTS = Path('/Users/kelinls/Movies/Bcut Drafts')
HANDOFF = PROJECT / '必剪交接'
SOURCE_ID = '67423DE7-869F-4905-8636-A4E287CDE6A0'
NAME = '以撒介绍-无字幕底片与可编辑字幕'
MOVIE = PROJECT / '以撒Switch模组项目-简短展示版-无字幕.mp4'
SRT = PROJECT / '以撒Switch模组项目-简短展示版.srt'


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def parse_srt(path):
    def ms(s):
        h, m, sec, frac = map(int, re.split('[:,]', s))
        return ((h * 60 + m) * 60 + sec) * 1000 + frac
    cues = []
    for part in re.split(r'\n\s*\n', path.read_text().strip()):
        lines = part.splitlines()
        a, b = lines[1].split(' --> ')
        cues.append({'start': ms(a), 'end': ms(b), 'text': '\n'.join(lines[2:])})
    return cues


def main():
    assert MOVIE.is_file() and SRT.is_file()
    # 必剪自动保存会覆盖内存中的旧索引，必须先正常退出。
    ps = subprocess.check_output(['ps', '-axo', 'comm'], text=True)
    assert not any(line.endswith('/Contents/MacOS/BCUT') for line in ps.splitlines()), '请先保存并退出必剪'
    HANDOFF.mkdir(exist_ok=True)
    result_path = HANDOFF / '导入结果.json'
    assert not result_path.exists(), '本轮草稿已创建；不要重复导入'
    cues = parse_srt(SRT)
    assert len(cues) == 16 and cues[0]['start'] == 0 and cues[-1]['end'] == 95000
    assert all(a['end'] == b['start'] for a, b in zip(cues, cues[1:]))
    source = max((DRAFTS / SOURCE_ID).glob('*.bjson'), key=lambda p: p.stat().st_mtime)
    original = source.read_bytes()
    index_file = DRAFTS / 'draftInfo.json'
    original_index = index_file.read_bytes()
    backup = HANDOFF / '导入前完整备份'
    backup.mkdir()
    shutil.copytree(DRAFTS / SOURCE_ID, backup / SOURCE_ID)
    (backup / 'draftInfo.json').write_bytes(original_index)
    config = json.loads(original)
    assert config['draftCreatedVersion'] == '3.11.24'
    timeline = config['timelineWidget']['timeline']
    assert len(timeline['captionTracks']) == 1
    base_caption = copy.deepcopy(timeline['captionTracks'][0]['captions'][0])
    old_movie = timeline['videoTracks'][0]['clips'][0]['sourcePath']
    assert Path(old_movie).name == '以撒Switch模组项目-简短展示版.mp4'
    id_map = {}

    def new_id():
        return str(secrets.randbits(62) + 1)

    def clone(value):
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if k in ('uid', 'idString'):
                    out[k] = id_map.setdefault(str(v), new_id())
                else:
                    out[k] = clone(v)
            return out
        if isinstance(value, list):
            return [clone(v) for v in value]
        if isinstance(value, str):
            if value == old_movie:
                return str(MOVIE)
            if value == Path(old_movie).name:
                return MOVIE.name
            if value == Path(old_movie).stem:
                return MOVIE.stem
            marker = 'BCUT.app/Contents/Resources/'
            if marker in value:
                return '/Applications/BCUT.app/Contents/Resources/' + value.split(marker, 1)[1]
        return value

    config = clone(config)
    timeline = config['timelineWidget']['timeline']
    base_caption = clone(base_caption)
    captions = []
    for cue in cues:
        c = copy.deepcopy(base_caption)
        # 本机原生保存证实位置是归一化坐标；不能把像素偏移直接写入。
        c.update(captionText=cue['text'], inPoint=cue['start'], outPoint=cue['end'],
                 idString=new_id(), uid=new_id(), scaleX=0.56, scaleY=0.56,
                 transX=0, transY=-0.9259259104728699)
        c['assetInfo'].update(content=cue['text'], displayName=cue['text'], duration=cue['end'] - cue['start'])
        captions.append(c)
    timeline['captionTracks'][0]['captions'] = captions
    timeline['config']['videoFps'] = {'den': 1, 'num': 60}
    config['timelineWidget']['tts'] = {}
    draft_id = str(uuid.uuid4()).upper()
    folder = DRAFTS / draft_id
    folder.mkdir()
    stamp = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H-%M-%S-') + f'{int(time.time()*1000)%1000:03d}'
    file = folder / (stamp + '--{' + str(uuid.uuid4()) + '}.bjson')
    write_json(file, config)
    # 封面来自无字幕底片，不能用旧带字封面冒充。
    subprocess.run(['ffmpeg', '-v', 'error', '-ss', '2', '-i', str(MOVIE), '-frames:v', '1',
                    '-vf', 'scale=480:270', '-y', str(folder / 'cover.jpg')], check=True)
    index = json.loads(original_index)
    entry = copy.deepcopy(next(x for x in index['draftInfos'] if x['id'] == SOURCE_ID))
    entry.update(id=draft_id, name=NAME, duration=95000000, modifyTime=int(time.time() * 1000),
                 cloud_draft_id='', cloud_draft_version='', storyLineId='', video_slice_id='')
    assert not any(x['name'] == NAME for x in index['draftInfos'])
    index['draftInfos'].insert(0, entry)
    temp = index_file.with_suffix('.json.codex-tmp')
    write_json(temp, index)
    temp.replace(index_file)
    reread = read_json(file)['timelineWidget']['timeline']
    assert [c['captionText'] for c in reread['captionTracks'][0]['captions']] == [c['text'] for c in cues]
    assert [(c['inPoint'], c['outPoint']) for c in reread['captionTracks'][0]['captions']] == [(c['start'], c['end']) for c in cues]
    assert all(c['sourcePath'] == str(MOVIE) for t in reread['videoTracks'] for c in t['clips'])
    assert all(c['sourcePath'] == str(MOVIE) for t in reread['audioTracks'] for c in t['audioClips'])
    assert len({c['uid'] for c in captions}) == len({c['idString'] for c in captions}) == 16
    assert source.read_bytes() == original, '原草稿不应被更改'
    assert read_json(index_file)['draftInfos'][1:] == json.loads(original_index)['draftInfos']
    shutil.copy2(file, HANDOFF / '以撒介绍-可编辑字幕.bjson')
    shutil.copy2(SRT, HANDOFF / SRT.name)
    result = {'项目名称': NAME, '草稿ID': draft_id, '草稿文件': str(file), '底片': str(MOVIE),
              '字幕': str(SRT), '字幕条数': 16, '总时长毫秒': 95000, '帧率': 60,
              '原草稿未变': True, '原索引条目保留': True, '字幕内容时间逐条一致': True,
              '原草稿SHA256': hashlib.sha256(original).hexdigest(),
              '新草稿SHA256': hashlib.sha256(file.read_bytes()).hexdigest(),
              '参考来源': 'https://github.com/Yao-lin101/BcutStr/tree/67c29037092d4034b18eb4a8b9b2e65deb4e4945',
              '说明': '复用本机真实模板；给字幕和轨道分配唯一ID，替换无字幕底片，保留分离背景音轨。'}
    write_json(result_path, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
