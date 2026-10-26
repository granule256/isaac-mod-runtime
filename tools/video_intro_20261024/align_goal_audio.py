#!/usr/bin/env python3
"""按已生成曼波的实际停顿对齐显示字幕，并收紧片尾空档。"""
import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path('/Users/kelinls/Movies/Bcut Drafts')
FOLDER = ROOT/'8F507393-8588-4CA5-9559-379B08D11D9C'
OUT = Path('/Users/kelinls/Movies/项目介绍-OpenFilm-20261024/配音字幕对齐-20261024')


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action',choices=['apply','preview'])
    args = parser.parse_args()
    plan = read(OUT/'对齐方案.json')
    if args.action == 'preview':
        return preview(plan)
    assert not any(s.endswith('/Contents/MacOS/BCUT') for s in subprocess.check_output(['ps','-axo','comm'],text=True).splitlines())
    assert not (OUT/'对齐结果.json').exists()
    movie = Path(plan['新底片'])
    assert movie.is_file()
    source = max(FOLDER.glob('*.bjson'),key=lambda p:p.stat().st_mtime)
    data = source.read_bytes()
    backup = OUT/'修改前完整备份'
    backup.mkdir()
    shutil.copytree(FOLDER, backup/FOLDER.name)
    shutil.copy2(ROOT/'draftInfo.json',backup/'draftInfo.json')
    config = json.loads(data)
    original = copy.deepcopy(config)
    t = config['timelineWidget']['timeline']
    display = next(tr for tr in t['captionTracks'] if len(tr['captions'])==20)
    cues = sorted([c for c in display['captions'] if 91000 <= c['inPoint'] < 111000], key=lambda c:c['inPoint'])
    assert len(cues)==4
    for cue,(start,end,text) in zip(cues,plan['显示字幕毫秒']):
        cue.update(inPoint=start,outPoint=end,captionText=text)
        cue['assetInfo'].update(content=text,displayName=text,duration=end-start)
    for tr in t['captionTracks']:
        for c in tr['captions']:
            if c['inPoint']==91000 and c.get('opacity')==0:
                c['outPoint']=102500
                c['assetInfo']['duration']=11500
            elif c['inPoint']>=111000:
                c['inPoint']-=8500
                c['outPoint']-=8500
    voices = []
    for tr in t['audioTracks']:
        for c in tr['audioClips']:
            if c['sourcePath']==plan['原底片']:
                c['sourcePath']=c['assetInfo']['srcPath']=str(movie)
                c['assetInfo']['duration']=c['outPoint']=c['trimOut']=106500
                c['assetInfo']['displayName']=movie.stem
                c['assetInfo']['itemName']=movie.name
                continue
            voices.append(c)
            if c['inPoint']>=111000:
                c['inPoint']-=8500
                c['outPoint']-=8500
    goal = next(c for c in voices if c['sourcePath']==plan['实际配音'])
    assert (goal['inPoint'],goal['outPoint'],goal['speed'])==(91000,102093,1)
    for tr in t['videoTracks']:
        for c in tr['clips']:
            assert c['sourcePath']==plan['原底片']
            for key in ['sourcePath','originalFilePath']:
                if c.get(key)==plan['原底片']:
                    c[key]=str(movie)
            c['assetInfo']['srcPath']=str(movie)
            c['assetInfo']['duration']=c['outPoint']=c['trimOut']=106500
            c['assetInfo']['displayName']=movie.stem
            c['assetInfo']['itemName']=movie.name
    for item in config['mainWindow']['browserPanelFiles']:
        if item['srcPath']==plan['原底片']:
            item['srcPath']=str(movie)
            item['duration']='106500'
    t['exportAreaInPoint']=t['exportAreaOutPoint']=-1
    before_voices=[c for tr in original['timelineWidget']['timeline']['audioTracks'] for c in tr['audioClips'] if c['sourcePath']!=plan['原底片']]
    for before,after in zip(before_voices,voices):
        expected=copy.deepcopy(before)
        if expected['inPoint']>=111000:
            expected['inPoint']-=8500
            expected['outPoint']-=8500
        assert expected==after, '禁止伸缩语音或改变前面配音'
    assert config['timelineWidget']['tts']==original['timelineWidget']['tts']
    cs=sorted(display['captions'],key=lambda c:c['inPoint'])
    assert len(cs)==20 and cs[-1]['inPoint']==102500 and cs[-1]['outPoint']==106500
    assert all(a['outPoint']==b['inPoint'] for a,b in zip(cs,cs[1:]))
    for cut,(a,b) in zip(plan['字幕断点相对秒'],plan['静音区间秒']):
        assert a<cut<b
    name=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H-%M-%S-')+f'{int(time.time()*1000)%1000:03d}'
    target=FOLDER/(name+'--{'+str(uuid.uuid4())+'}.bjson')
    write(target,config)
    index_path=ROOT/'draftInfo.json'
    index=read(index_path)
    entry=next(x for x in index['draftInfos'] if x['id']==FOLDER.name)
    entry.update(duration=106500000,modifyTime=int(time.time()*1000))
    temp=index_path.with_suffix('.json.codex-tmp')
    write(temp,index)
    temp.replace(index_path)
    assert source.read_bytes()==data
    shutil.copy2(target,OUT/'按实际配音对齐-工程快照.bjson')
    (OUT/'实际配音原件.wav').write_bytes(Path(plan['实际配音']).read_bytes())
    result={'工程':'以撒介绍-补充项目目标','草稿文件':str(target),'片长秒':106.5,
            '新增语音长度秒':11.093375,'字幕切点秒':[91,92.133,96.333,99.067,102.5],
            'CTA起点秒':102.5,'语音结束至CTA间隙秒':0.406625,'显示字幕数':20,
            '实际配音未变速未重合成':True,'三个断点均位于实测停顿':True,
            '前91秒的字幕配音未改':True,'原工程SHA256':hashlib.sha256(data).hexdigest(),
            '新工程SHA256':sha(target),'语音SHA256':sha(plan['实际配音']),
            '新底片SHA256':sha(movie)}
    write(OUT/'对齐结果.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


def preview(plan):
    result=read(OUT/'对齐结果.json')
    config=read(Path(result['草稿文件']))
    t=config['timelineWidget']['timeline']
    clips=[c for tr in t['audioTracks'] for c in tr['audioClips']]
    goal=next(c for c in clips if c['sourcePath']==plan['实际配音'])
    cta=next(c for c in clips if c['inPoint']==102500)
    bg=next(c for c in clips if c['sourcePath']==plan['新底片'])
    def db(c):
        return sum(f.get('gainValue',0) for f in c.get('fxs',[]) if f.get('fxName')=='Volume')
    # 预览仅验证声音与文字时点；正式画面使用必剪保存的原生样式。
    captions=plan['显示字幕毫秒']+[[102500,106500,'感兴趣的话可以先关注一下，顺手点个赞']]
    from PIL import Image, ImageDraw, ImageFont
    overlays=[]
    image_inputs=[]
    font='/Applications/BCUT.app/Contents/Resources/Font/Source Han Sans CN Medium.ttf'
    face=ImageFont.truetype(font,40)
    for i,(a,b,text) in enumerate(captions):
        # 本机FFmpeg不含drawtext；用已安装Pillow生成透明图，overlay是现有能力。
        f=OUT/f'预览字幕-{i+1}.png'
        image=Image.new('RGBA',(1920,1080),(0,0,0,0))
        ImageDraw.Draw(image).text((960,1032),text,font=face,anchor='mm',fill='white',stroke_width=2,stroke_fill='black')
        image.save(f)
        image_inputs+=['-i',str(f)]
        prev='0:v' if i==0 else f's{i-1}'
        overlays.append(f"[{prev}][{i+3}:v]overlay=eof_action=repeat:shortest=0:enable='gte(t,{(a-91000)/1000})*lt(t,{(b-91000)/1000})'[s{i}]")
    video=';'.join(overlays)+f';[s{len(captions)-1}]format=yuv420p[v]'
    audio=f'[0:a]volume={db(bg)}dB[a0];[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={db(goal)}dB[a1];[2:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={db(cta)}dB,adelay=11500|11500[a2];[a0][a1][a2]amix=inputs=3:duration=first:normalize=0[a]'
    movie=OUT/'项目目标与片尾-同步预览.mp4'
    assert not movie.exists()
    cmd=['ffmpeg','-hide_banner','-v','warning','-nostdin','-threads','2','-filter_complex_threads','1',
         '-ss','91','-t','15.5','-i',plan['新底片'],'-i',goal['sourcePath'],'-i',cta['sourcePath'],*image_inputs,
         '-filter_complex',video+';'+audio,'-map','[v]','-map','[a]','-t','15.5',
         '-c:v','h264_videotoolbox','-b:v','10000k','-c:a','aac','-b:a','192k','-movflags','+faststart',str(movie)]
    with (OUT/'同步预览日志.txt').open('w') as log:
        run=subprocess.run(cmd,stdout=log,stderr=log)
    assert run.returncode==0
    print(movie)


if __name__=='__main__':
    main()
