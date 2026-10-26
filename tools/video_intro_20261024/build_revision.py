#!/usr/bin/env python3
"""保留初版，按修订镜头表生成朴素的完整实机画面与原生字幕。"""
import hashlib
import html
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROJECT = Path('/Users/kelinls/Movies/项目介绍-OpenFilm-20261024')
CAPTURE = PROJECT / '取材记录-修订版'


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def preserve_write(path, body):
    """改变既有记录前另存逐字旧版，不删除草稿信息。"""
    encoded = body.encode()
    if path.exists() and path.read_bytes() != encoded:
        old = path.read_bytes()
        backup = PROJECT / '版本备份/修订草稿'
        backup.mkdir(parents=True, exist_ok=True)
        kept = backup / (path.name + '-' + hashlib.sha256(old).hexdigest()[:12])
        if not kept.exists():
            kept.write_bytes(old)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)


def card_page(lines, duration):
    parts = ''.join(f'<p>{html.escape(t)}</p>' for t in lines)
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=1920, height=1080">
<style>html,body{{margin:0;width:1920px;height:1080px;background:#111;color:#eee;overflow:hidden;font-family:-apple-system,"PingFang SC",sans-serif}}main{{position:absolute;left:160px;top:180px;width:1600px}}p{{font-size:45px;line-height:1.55;margin:24px 0;font-weight:400}}p:first-child{{font-size:70px;line-height:1.3;margin:0 0 58px;font-weight:600}}</style>
<main>{parts}</main><script>window.film={{width:1920,height:1080,duration:{duration},ready:document.fonts.ready,frame(t){{}}}};</script></html>\n'''


def note_page(current):
    note = '本次实机截图' if current else '历史实机截图'
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=1920, height=1080">
<style>html,body{{margin:0;width:1920px;height:1080px;background:transparent;overflow:hidden}}span{{position:absolute;left:50%;transform:translateX(-50%);top:12px;background:rgba(0,0,0,.65);color:#eee;padding:4px 8px;font:21px -apple-system,"PingFang SC",sans-serif}}</style><span>{note}</span>
<script>window.film={{width:1920,height:1080,ready:document.fonts.ready,frame(t){{}}}};</script></html>\n'''


def main():
    spec = json.loads((HERE / 'revision_storyboard.json').read_text())
    assert (PROJECT / '版本备份/20261024-两分钟初版/film.html').is_file()
    assets = PROJECT / 'assets/修订截图'
    pages = PROJECT / '修订页面'
    assets.mkdir(exist_ok=True)
    pages.mkdir(exist_ok=True)
    preserve_write(pages / '本次截图标记.html', note_page(True))
    preserve_write(pages / '历史截图标记.html', note_page(False))
    pictures = {}
    sources = []
    used = {shot[1]: shot[0] for scene in spec['scenes'] for shot in scene.get('shots', []) if shot[0] in ('image', 'footage')}
    for key, kind in used.items():
        raw = spec['assets'][key]
        current = raw.startswith('@capture/')
        original = CAPTURE / raw[len('@capture/'):] if current else ROOT / raw
        assert original.is_file(), str(original)
        copied = assets / (key + original.suffix.lower())
        if not copied.exists():
            shutil.copyfile(original, copied)
        assert digest(original) == digest(copied), '素材内容变更时使用新素材名'
        pictures[key] = {'asset': copied.relative_to(PROJECT).as_posix(), 'current': current}
        sources.append({'key': key, 'source': str(original), 'asset': str(copied.relative_to(PROJECT)),
                        'sha256': digest(original), 'type': '实机录像' if kind == 'footage' else '实机截图', 'current': current})
    films = ['<!doctype html>', '<html lang="zh-CN">', '<head><meta charset="utf-8">',
             '<meta name="viewport" content="width=1920, height=1080">',
             '<style>body{background:#111}video,img{object-fit:contain}</style></head><body>']
    note_track, picture_track = [], []
    captions, scenes = [], []
    cursor = 0
    source_videos = {}
    for index, scene in enumerate(spec['scenes'], 1):
        duration = sum(n for n, _ in scene['lines'])
        start = cursor
        for seconds, text in scene['lines']:
            assert seconds >= 3 and text.strip()
            captions.append({'start': cursor, 'end': cursor + seconds, 'text': text,
                             'scene': scene['id']})
            cursor += seconds
        media = []
        if 'card' in scene:
            assert 'shots' not in scene
            name = f'{index:02d}-{scene["id"]}.html'
            preserve_write(pages / name, card_page(scene['card'], duration))
            picture_track.append(f'<iframe id="{scene["id"]}" src="修订页面/{name}#t=0,{duration}" at="{start}" title="{html.escape(scene["title"],quote=True)}"></iframe>')
            media.append({'type': '文字说明页', 'path': '修订页面/' + name})
        else:
            local = start
            for si, shot in enumerate(scene['shots'], 1):
                clip_id = f'{scene["id"]}-{si}'
                if shot[0] in ('video', 'footage'):
                    _, number, first, seconds, speed = shot
                    rel = f'assets/原片-{number:02d}.mov' if shot[0] == 'video' else pictures[number]['asset']
                    asset = PROJECT / rel
                    assert asset.is_file()
                    if number not in source_videos:
                        info = json.loads(subprocess.check_output([
                            'ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(asset)]))
                        source_videos[number] = {'duration': float(info['format']['duration']), 'sha256': digest(asset)}
                    last = first + seconds * speed
                    assert first >= 0 and last <= source_videos[number]['duration']
                    sound = ' volume="0.65"' if scene['id'] == 'specialist' and shot[0] == 'footage' else ' muted'
                    rect = 'left:0px;top:0px;width:1920px;height:1080px'
                    picture_track.append(f'<video id="{clip_id}" src="{rel}#t={first},{last:g}" at="{local}" speed="{speed}"{sound} title="{html.escape(scene["title"],quote=True)}" style="{rect}"></video>')
                    assert speed == 1, '新版没有需要倍速标记的镜头'
                    media.append({'type': '录像', 'asset': rel,
                                  'source_start': first, 'duration': seconds, 'speed': speed})
                else:
                    _, key, seconds = shot
                    p = pictures[key]
                    picture_track.append(f'<img id="{clip_id}" src="{p["asset"]}#t=0,{seconds}" at="{local}" title="{html.escape(scene["title"],quote=True)}" style="left:0px;top:0px;width:1920px;height:1080px">')
                    note = '本次' if p['current'] else '历史'
                    note_track.append(f'<iframe id="note-{clip_id}" src="修订页面/{note}截图标记.html#t=0,{seconds}" at="{local}"></iframe>')
                    media.append({'type': '本次实机截图' if p['current'] else '历史实机截图', 'asset': p['asset'], 'duration': seconds})
                local += seconds
            assert local == cursor, (scene['id'], local, cursor)
        scenes.append({'id': scene['id'], 'title': scene['title'], 'start': start,
                       'end': cursor, 'duration': duration, 'media': media})
    music_asset = spec.get('music_asset', 'assets/原创背景音乐-完整版.wav')
    clock_asset = spec.get('caption_clock_asset', 'assets/字幕时钟.wav')
    # 舞蹈段保留原生游戏音轨，底乐在该段停下，避免两首音乐叠放。
    dance = next(s for s in scenes if s['id'] == 'specialist')
    music_clips = [f'<audio id="music-before" src="{music_asset}#t=0,{dance["start"]}" volume="1.8"></audio>',
                   f'<audio id="music-after" src="{music_asset}#t={dance["end"]},{cursor}" at="{dance["end"]}" volume="1.8"></audio>']
    # 原生字幕关联无声时钟媒体，独立于底乐的分段和游戏音轨。
    films += ['<section title="截图来源标记">', *note_track, '</section>',
              '<section title="完整实机画面与普通说明页">', *picture_track, '</section>',
              '<section title="原创轻背景音乐与中文字幕（无旁白）">',
              *music_clips, '</section>',
              '<section title="中文字幕时钟（静音媒体，无旁白）">',
              f'<audio id="caption-clock" src="{clock_asset}#t=0,{cursor}" volume="1"></audio>',
              '</section>', '</body>', '</html>']
    spec_loader = importlib.util.spec_from_file_location('intro_build', HERE / 'build_film.py')
    base = importlib.util.module_from_spec(spec_loader)
    spec_loader.loader.exec_module(base)
    base.music(PROJECT / music_asset, cursor)
    import wave
    clock = PROJECT / clock_asset
    if not clock.exists():
        with wave.open(str(clock), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
            w.writeframes(bytes(cursor * 8000 * 2))
    else:
        with wave.open(str(clock)) as w: assert w.getnframes() / w.getframerate() == cursor
    vtt = 'WEBVTT\n\nNOTE Each cue is one subtitle, as cut by hand in OpenFilm Studio.\n\n'
    vtt += ''.join(f'{base.stamp(c["start"])} --> {base.stamp(c["end"])}\n{c["text"]}\n\n' for c in captions)
    srt = ''.join(f'{i}\n{base.stamp(c["start"],True)} --> {base.stamp(c["end"],True)}\n{c["text"]}\n\n' for i, c in enumerate(captions, 1))
    preserve_write(clock.with_suffix('.vtt'), vtt)
    preserve_write(PROJECT / '完整版修订字幕.vtt', vtt)
    preserve_write(PROJECT / '完整版修订字幕.srt', srt)
    preserve_write(PROJECT / 'film.html', '\n'.join(films) + '\n')
    manifest = {'title': spec['title'], 'duration': cursor, 'fps': 60, 'width': 1920, 'height': 1080,
                'caption_clock_asset': clock_asset,
                'voice': spec['voice'], 'scenes': scenes, 'captions': captions, 'pictures': sources,
                'original_videos': source_videos, 'old_master_retained': True}
    preserve_write(PROJECT / '完整版修订时间线与素材清单.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    prose = '# 完整版修订文案\n\n'
    for scene in spec['scenes']:
        prose += f'## {scene["title"]}\n\n' + '\n\n'.join(t for _, t in scene['lines']) + '\n\n'
    preserve_write(PROJECT / '完整版修订文案.md', prose)
    print(json.dumps({'duration': cursor, 'frames': cursor * 60, 'scenes': len(scenes),
                      'captions': len(captions), 'pictures': len(sources),
                      'picture_clips': len(picture_track)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
