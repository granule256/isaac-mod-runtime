#!/usr/bin/env python3
"""将已确认的实机时间线制作成独立、可编辑的 OpenFilm 工程。"""
import argparse
import hashlib
import html
import json
import math
import shutil
import subprocess
import wave
from array import array
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
MOVIES = Path('/Users/kelinls/Movies')
DEFAULT_PROJECT = MOVIES / '项目介绍-OpenFilm-20261024'


def stamp(seconds, comma=False):
    ms = round(seconds * 1000)
    sep = ',' if comma else '.'
    return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d}{sep}{ms%1000:03d}'


def music(path, duration=120, rate=24000):
    """原创低音量器乐底乐；没有语音、采样或原录像音轨。"""
    if path.exists():
        with wave.open(str(path)) as old:
            if old.getnframes() == duration * rate and old.getframerate() == rate:
                return
        raise ValueError('已有背景音乐与本次参数不符，请另建版本而非覆盖')
    # Am / F / C / G 分解和弦，非现成歌曲旋律；5ms起音避免点击。
    chords = [(57, 60, 64, 69), (53, 57, 60, 65), (48, 52, 55, 60), (55, 59, 62, 67)]
    pattern = (0, 2, 1, 3, 1, 2, 0, 2)
    pulse = .5
    samples = array('h')
    for beat in range(int(duration / pulse)):
        chord = chords[(beat // 8) % len(chords)]
        frequency = 440 * 2 ** ((chord[pattern[beat % 8]] - 69) / 12)
        bass = 440 * 2 ** ((chord[0] - 24 - 69) / 12)
        for n in range(round(rate * pulse)):
            local = n / rate
            t = beat * pulse + local
            fade = min(1, t / 1.8, max(0, (duration - t) / 3))
            attack = min(1, local / .005)
            pluck = attack * math.exp(-local * 6.5)
            bell = (math.sin(2 * math.pi * frequency * local)
                    + .17 * math.sin(4 * math.pi * frequency * local))
            low = math.sin(2 * math.pi * bass * t) * (.5 - .5 * math.cos(2 * math.pi * local / pulse))
            value = fade * (.075 * pluck * bell + .035 * low)
            samples.append(round(max(-1, min(1, value)) * 32767))
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(samples.tobytes())


def sha256(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def build(project):
    config = json.loads((REPO / 'tools/video_intro_20261021/时间线.json').read_text())
    captions = json.loads((HERE / 'captions.json').read_text())
    assets = project / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    clips = sorted(MOVIES.glob('*.mov'))
    if len(clips) != 9:
        raise ValueError('素材序号依据原九段录像，数量变化时必须重新核对映射')
    used = sorted({shot[0] for c in config['章节'] for shot in c['镜头']})
    records = []
    for i in used:
        source = clips[i - 1]
        target = assets / f'原片-{i:02d}.mov'
        source_sha = sha256(source)
        if not target.exists():
            # 独立实文件，避免工程服务器拒绝指向目录外的符号链接。
            shutil.copyfile(source, target)
        if sha256(target) != source_sha:
            raise ValueError(f'素材复制核验失败：{source}')
        info = json.loads(subprocess.check_output([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(source)]))
        records.append({'index': i, 'source': str(source), 'asset': target.name,
                        'sha256': source_sha, 'duration': float(info['format']['duration'])})
    limits = {r['index']: r['duration'] for r in records}
    total = sum(c['时长'] for c in config['章节'])
    previous = 0
    for start, end, text in captions:
        if start != previous or end <= start or end > total or not text.strip():
            raise ValueError(f'字幕时间不连续：{start}/{end}')
        if len(text) > 35:
            raise ValueError(f'字幕过长：{text}')
        previous = end
    if previous != total or total != 120:
        raise ValueError('字幕必须完整覆盖120秒')
    film = ['<!doctype html>', '<html lang="zh-CN">', '<head>', '<meta charset="utf-8">',
            '<meta name="viewport" content="width=1920, height=1080">',
            '<style>body{background:#111917}video{object-fit:contain}</style>', '</head>', '<body>',
            '<section title="章节包装">']
    cursor = 0
    for i, c in enumerate(config['章节']):
        page = project / f'章节-{i+1:02d}.html'
        page.write_text((HERE / 'chapter.html').read_text().replace(
            "const index = Number(new URLSearchParams(location.search).get('chapter'));", f'const index = {i};'))
        film.append(f'<iframe id="chapter-{i+1}" src="{page.name}#t=0,{c["时长"]}" at="{cursor}" title="{html.escape(c["标题"], quote=True)}"></iframe>')
        cursor += c['时长']
    film += ['</section>', '<section title="实机画面（原声已移除）">']
    cursor = 0
    shots = []
    for ci, c in enumerate(config['章节']):
        local = 0
        for source_index, source_start, duration, speed in c['镜头']:
            source_end = source_start + duration * speed
            if source_end > limits[source_index]:
                raise ValueError('镜头超出原片范围')
            at = cursor + local
            shot_id = f'shot-{len(shots)+1:02d}'
            film.append(f'<video id="{shot_id}" src="assets/原片-{source_index:02d}.mov#t={source_start},{source_end:g}" at="{at:g}" speed="{speed}" muted style="left:160px;top:80px;width:1600px;height:900px" title="第{ci+1}章实机片段"></video>')
            shots.append({'id': shot_id, 'at': at, 'duration': duration, 'source': source_index,
                          'in': source_start, 'out': source_end, 'speed': speed, 'chapter': ci+1})
            local += duration
        if local != c['时长']:
            raise ValueError('章节镜头总时长不匹配')
        cursor += local
    film += ['</section>', '<section title="原创背景音乐与中文字幕（无旁白）">',
             '<audio id="music-captions" src="assets/原创背景音乐.wav#t=0,120" volume="1.8"></audio>',
             '</section>', '</body>', '</html>']
    (project / 'film.html').write_text('\n'.join(film) + '\n')
    music(assets / '原创背景音乐.wav')
    vtt = 'WEBVTT\n\nNOTE Each cue is one subtitle, as cut by hand in OpenFilm Studio.\n\n'
    vtt += ''.join(f'{stamp(a)} --> {stamp(b)}\n{text}\n\n' for a, b, text in captions)
    (assets / '原创背景音乐.vtt').write_text(vtt)
    (project / '项目介绍字幕.vtt').write_text(vtt)
    (project / '项目介绍字幕.srt').write_text(''.join(
        f'{i}\n{stamp(a, True)} --> {stamp(b, True)}\n{text}\n\n'
        for i, (a, b, text) in enumerate(captions, 1)))
    (project / '解说与字幕文案.txt').write_text('\n'.join(t for _, _, t in captions) + '\n')
    (project / '时间线与素材清单.json').write_text(json.dumps({
        'duration': total, 'width': 1920, 'height': 1080, 'fps': 60,
        'voice': '无旁白；用户授权无法取得哈基米时交付字幕版',
        'audio': '原创低音量器乐背景音乐；所有原录像音轨均muted',
        'sources': records, 'shots': shots, 'captions': captions,
        'speedNotes': '第六章前9秒为2倍速，后9秒为1.5倍速，包装明确标注',
    }, ensure_ascii=False, indent=2) + '\n')
    (project / '.gitignore').write_text('.film/\nassets/*.mov\nassets/*.wav\n*.mp4\n核验/\n')
    (project / '制作说明.md').write_text(
        '# 以撒 Switch 模组运行时：实机介绍\n\n'
        '120秒，1920×1080，60fps；真实Switch录像，中文字幕，原创背景音乐，无旁白。'
        '本次未取得哈基米音色，按用户授权交付字幕版。原录像的声音不进入成片。\n\n'
        'film.html 是可编辑时间线；章节页面为透明包装；assets 保存实文件素材。'
        '字幕通过同名WebVTT交给OpenFilm原生字幕轨道，背景音乐没有人声，字幕是介绍文字。'
        'SRT可单独导入其他软件。导出需启用烧录字幕。\n\n'
        '控制台输入前9秒2倍速、后9秒1.5倍速，画面有标注；其余实机片段正常速度。'
        '没有使用报错录像来证明功能正常。开发测试版，并非所有模组兼容。\n\n'
        '素材来源：用户Movies内2026-10-20录像；原件未改写。'
        '音乐为本轮脚本生成的简短分解和弦，无第三方录音采样。\n')
    print(json.dumps({'project': str(project), 'seconds': total, 'shots': len(shots),
                      'chapters': len(config['章节']), 'captions': len(captions),
                      'sourceIndexes': used}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, default=DEFAULT_PROJECT)
    build(parser.parse_args().project)
