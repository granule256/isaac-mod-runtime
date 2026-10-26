#!/usr/bin/env python3
"""保留用户字幕样式与曼波配音，在点赞前插入项目目标。"""
import copy
import hashlib
import json
import secrets
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

PROJECT = Path('/Users/kelinls/Movies/项目介绍-OpenFilm-20261024')
OUT = PROJECT / '补充项目目标-20261024'
DRAFTS = Path('/Users/kelinls/Movies/Bcut Drafts')
SOURCE_ID = '37CC7FDE-2299-460E-9C7B-D2488063EC31'
NAME = '以撒介绍-补充项目目标'
MOVIE = Path('/Users/kelinls/Movies/以撒pc模组兼容层介绍-补充目标-无字幕.mp4')


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stamp(ms):
    return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'


def main():
    assert MOVIE.is_file() and not (OUT / '补充导入结果.json').exists()
    ps = subprocess.check_output(['ps', '-axo', 'comm'], text=True)
    assert not any(x.endswith('/Contents/MacOS/BCUT') for x in ps.splitlines()), '请正常保存并退出必剪'
    source_folder = DRAFTS / SOURCE_ID
    source = max(source_folder.glob('*.bjson'), key=lambda p: p.stat().st_mtime)
    source_bytes = source.read_bytes()
    index_file = DRAFTS / 'draftInfo.json'
    index_bytes = index_file.read_bytes()
    backup = OUT / '修改前完整备份'
    backup.mkdir()
    shutil.copytree(source_folder, backup / SOURCE_ID)
    (backup / 'draftInfo.json').write_bytes(index_bytes)
    (OUT / '最终保存的原工程.bjson').write_bytes(source_bytes)
    config = json.loads(source_bytes)
    old_timeline = copy.deepcopy(config['timelineWidget']['timeline'])
    old_caps = sorted([c for t in old_timeline['captionTracks'] for c in t['captions']], key=lambda c:c['inPoint'])
    assert len(old_caps) == 16 and old_caps[-1]['inPoint'] == 91000
    assert '关注' in old_caps[-1]['captionText'] and '点赞' not in old_caps[-1]['captionText']
    assert '点个赞' in old_caps[-1]['captionText']
    old_movie = old_timeline['videoTracks'][0]['clips'][0]['sourcePath']
    old_voice = [c for t in old_timeline['audioTracks'] for c in t['audioClips'] if c['assetInfo'].get('audioType') == 6]
    assert len(old_voice) == 16
    draft_id = str(uuid.uuid4()).upper()
    folder = DRAFTS / draft_id
    folder.mkdir()
    voice_map = {}
    for clip in old_voice:
        original = Path(clip['sourcePath'])
        target = folder / original.name
        shutil.copy2(original, target)
        assert sha(original) == sha(target)
        voice_map[str(original)] = str(target)

    def new_id():
        return str(secrets.randbits(62) + 1)

    id_map = {}
    def gather(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ('idString', 'uid'):
                    id_map.setdefault(str(v), new_id())
                gather(v)
        elif isinstance(x, list):
            for v in x:
                gather(v)
    gather(config)

    def rewrite(x):
        if isinstance(x, dict):
            return {id_map.get(k, k):rewrite(v) for k, v in x.items()}
        if isinstance(x, list):
            return [rewrite(v) for v in x]
        if isinstance(x, str):
            if x in id_map:
                return id_map[x]
            if x in voice_map:
                return voice_map[x]
            if x == old_movie:
                return str(MOVIE)
            if x == Path(old_movie).name:
                return MOVIE.name
            if x == Path(old_movie).stem:
                return MOVIE.stem
        return x
    config = rewrite(config)
    timeline = config['timelineWidget']['timeline']
    track = timeline['captionTracks'][0]
    template = copy.deepcopy(next(c for c in track['captions'] if c['inPoint'] == 91000))
    for caption in track['captions']:
        if caption['inPoint'] >= 91000:
            caption['inPoint'] += 20000
            caption['outPoint'] += 20000
    spec = read_json(OUT / '补充方案.json')
    added_uids = []
    for start, end, text in spec['新增字幕']:
        c = copy.deepcopy(template)
        c.update(idString=new_id(), uid=new_id(), inPoint=start, outPoint=end, captionText=text)
        c['assetInfo'].update(content=text, displayName=text, duration=end-start)
        track['captions'].append(c)
        added_uids.append(c['uid'])
    track['captions'].sort(key=lambda c:c['inPoint'])
    for tr in timeline['videoTracks']:
        for clip in tr['clips']:
            assert clip['inPoint'] == 0 and clip['outPoint'] == 95000
            clip['outPoint'] = clip['trimOut'] = clip['assetInfo']['duration'] = 115000
    for tr in timeline['audioTracks']:
        for clip in tr['audioClips']:
            if clip['assetInfo'].get('audioType') == 6:
                if clip['inPoint'] >= 91000:
                    clip['inPoint'] += 20000
                    clip['outPoint'] += 20000
            else:
                assert clip['sourcePath'] == str(MOVIE)
                clip['outPoint'] = clip['trimOut'] = clip['assetInfo']['duration'] = 115000
    for item in config['mainWindow']['browserPanelFiles']:
        if item['srcPath'] == str(MOVIE):
            item['duration'] = '115000'
    for k in ['exportAreaInPoint', 'exportAreaOutPoint']:
        timeline[k] = -1
    name = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H-%M-%S-') + f'{int(time.time()*1000)%1000:03d}'
    file = folder / (name + '--{' + str(uuid.uuid4()) + '}.bjson')
    write_json(file, config)
    subprocess.run(['ffmpeg','-v','error','-ss','93','-i',str(MOVIE),'-frames:v','1',
                    '-vf','scale=480:270','-y',str(folder/'cover.jpg')],check=True)
    index = json.loads(index_bytes)
    entry = copy.deepcopy(next(e for e in index['draftInfos'] if e['id'] == SOURCE_ID))
    entry.update(id=draft_id, name=NAME, duration=115000000, modifyTime=int(time.time()*1000),
                 cloud_draft_id='', cloud_draft_version='', storyLineId='', video_slice_id='')
    index['draftInfos'].insert(0,entry)
    temp = index_file.with_suffix('.json.codex-tmp')
    write_json(temp,index)
    temp.replace(index_file)
    captions = track['captions']
    assert len(captions) == 20 and captions[-1]['inPoint'] == 111000 and captions[-1]['outPoint'] == 115000
    assert all(a['outPoint'] == b['inPoint'] for a,b in zip(captions,captions[1:]))
    assert [c['captionText'] for c in captions[:15]] == [c['captionText'] for c in old_caps[:15]]
    style_keys = ['scaleX','scaleY','transX','transY','drawOutline','outlineWidth','outlineColor']
    assert all(all(c[k] == template[k] for k in style_keys) for c in captions[15:])
    assert len(config['timelineWidget']['tts']) == 16
    assert not set(added_uids).intersection(config['timelineWidget']['tts'].values())
    assert source.read_bytes() == source_bytes
    assert read_json(index_file)['draftInfos'][1:] == json.loads(index_bytes)['draftInfos']
    srt = ''.join(f'{i}\n{stamp(c["inPoint"])} --> {stamp(c["outPoint"])}\n{c["captionText"]}\n\n' for i,c in enumerate(captions,1))
    (OUT/'以撒pc模组兼容层介绍-补充目标.srt').write_text(srt)
    shutil.copy2(file,OUT/'补充目标版-可编辑工程.bjson')
    result = {'工程名称':NAME,'草稿ID':draft_id,'草稿文件':str(file),'底片':str(MOVIE),
              '总时长秒':115,'工程帧率':timeline['config']['videoFps']['num'],
              '字幕条数':20,'新增字幕UID':added_uids,'新增范围秒':[91,111],
              '关注点赞范围秒':[111,115],'原曼波配音16条保留':True,'新增配音':'由用户生成',
              '原文案与用户样式保留':True,'原项目未改':True,
              '原工程SHA256':hashlib.sha256(source_bytes).hexdigest(),
              '新工程SHA256':sha(file),'底片SHA256':sha(MOVIE),
              '配音文件逐项SHA一致':{str(Path(k).name):sha(Path(v)) for k,v in voice_map.items()}}
    write_json(OUT/'补充导入结果.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
