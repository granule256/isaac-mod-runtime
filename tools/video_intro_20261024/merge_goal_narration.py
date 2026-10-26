#!/usr/bin/env python3
"""让新增目标使用单段朗读，保留短字幕和用户当前工程。"""
import copy
import hashlib
import json
import secrets
import shutil
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path('/Users/kelinls/Movies/Bcut Drafts')
PROJECT_ID = '8F507393-8588-4CA5-9559-379B08D11D9C'
OUT = Path('/Users/kelinls/Movies/项目介绍-OpenFilm-20261024/结尾整段朗读-20261024')


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    ps = subprocess.check_output(['ps', '-axo', 'comm'], text=True)
    assert not any(s.endswith('/Contents/MacOS/BCUT') for s in ps.splitlines()), '请保存并退出必剪'
    assert not (OUT/'整段朗读结果.json').exists(), '本次修改已经执行'
    folder = ROOT/PROJECT_ID
    source = max(folder.glob('*.bjson'), key=lambda p:p.stat().st_mtime)
    source_bytes = source.read_bytes()
    backup = OUT/'修改前完整备份'
    backup.mkdir()
    shutil.copytree(folder, backup/PROJECT_ID)
    shutil.copy2(ROOT/'draftInfo.json', backup/'draftInfo.json')
    config = json.loads(source_bytes)
    original = copy.deepcopy(config)
    widget = config['timelineWidget']
    timeline = widget['timeline']
    assert len(timeline['captionTracks']) == 1
    captions = timeline['captionTracks'][0]['captions']
    selected = sorted([c for c in captions if 91000 <= c['inPoint'] < 111000], key=lambda c:c['inPoint'])
    assert len(selected) == 4 and selected[0]['inPoint'] == 91000 and selected[-1]['outPoint'] == 111000
    # 只纠正新增末句的明显笔误，原话在完整备份中保留。
    for c in selected:
        if '主要是其的性能优化' in c['captionText']:
            text = c['captionText'].replace('主要是其的性能优化', '主要是性能优化')
            c['captionText'] = text
            c['assetInfo']['content'] = c['assetInfo']['displayName'] = text
    first = selected[0]['captionText'].rstrip('。') + selected[1]['captionText']
    # 保留正常衔接词，避免逐字幕句首再起一次语气。
    progress = selected[2]['captionText'].rstrip('。') + '，' + selected[3]['captionText']
    text = first.rstrip('。') + '。' + progress.rstrip('。') + '。'
    assert '\n' not in text
    new_id = lambda:str(secrets.randbits(62)+1)
    speech = copy.deepcopy(selected[0])
    speech.update(idString=new_id(), uid=new_id(), inPoint=91000, outPoint=111000,
                  captionText=text, opacity=0)
    speech['assetInfo'].update(content=text, displayName='项目目标：整段朗读一次', duration=20000)
    track = copy.deepcopy(timeline['captionTracks'][0])
    track.update(captions=[speech], idString=new_id(), uid=new_id(),
                 index=max(t['index'] for t in timeline['captionTracks'])+1, enable=True, lock=False)
    timeline['captionTracks'].insert(0, track)
    for name in ['trackList','trackListWidget']:
        rows = widget[name]['trackWidgetList']
        for row in rows:
            row['index'] += 1
        rows.insert(0, {'index':1,'trackHeightLevel':0,'trackWidgetWaveHeightLevel':0,'uid':track['uid']})
    assert timeline['audioTracks'] == original['timelineWidget']['timeline']['audioTracks']
    assert timeline['videoTracks'] == original['timelineWidget']['timeline']['videoTracks']
    assert widget.get('tts', {}) == original['timelineWidget'].get('tts', {})
    assert speech['uid'] not in widget.get('tts', {}).values()
    name = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H-%M-%S-')+f'{int(time.time()*1000)%1000:03d}'
    target = folder/(name+'--{'+str(uuid.uuid4())+'}.bjson')
    write(target, config)
    index_path = ROOT/'draftInfo.json'
    index = json.loads(index_path.read_text())
    next(x for x in index['draftInfos'] if x['id'] == PROJECT_ID)['modifyTime'] = int(time.time()*1000)
    temp = index_path.with_suffix('.json.codex-tmp')
    write(temp, index)
    temp.replace(index_path)
    reread = json.loads(target.read_text())
    assert reread['timelineWidget']['timeline']['captionTracks'][0]['captions'][0]['captionText'] == text
    assert len(reread['timelineWidget']['timeline']['captionTracks'][1]['captions']) == 20
    assert source.read_bytes() == source_bytes
    shutil.copy2(target, OUT/'项目目标整段朗读-工程快照.bjson')
    (OUT/'项目目标整段朗读.txt').write_text(text+'\n')
    result = {'工程':'以撒介绍-补充项目目标','草稿文件':str(target),'范围秒':[91,111],
              '朗读文本':text,'朗读条目数':1,'画面短字幕数':20,
              '朗读文本透明度':0,'朗读轨道UID':track['uid'],'朗读字幕UID':speech['uid'],
              '现有音轨与视频未改':True,'现有TTS关联未改':True,'原始版本字节未改':True,
              '原稿SHA256':hashlib.sha256(source_bytes).hexdigest(),
              '新稿SHA256':hashlib.sha256(target.read_bytes()).hexdigest()}
    write(OUT/'整段朗读结果.json', result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
