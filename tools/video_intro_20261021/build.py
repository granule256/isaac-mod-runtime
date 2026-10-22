#!/usr/bin/env python3
"""生成项目介绍画面母版；仅取原片视频流，配音另行合成。"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
MOVIES = Path('/Users/kelinls/Movies')
FONT = '/System/Library/Fonts/STHeiti Medium.ttc'


def run(args):
    subprocess.run(args, check=True)


def stamp(t):
    ms = round(t * 1000)
    return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'


def wrap(text, font, width):
    lines = ['']
    for char in text:
        if font.getlength(lines[-1] + char) > width:
            lines.append(char)
        else:
            lines[-1] += char
    return lines


def prepare(config):
    out = Path(config['输出目录'])
    assets = out / '制作文件'
    assets.mkdir(parents=True, exist_ok=True)
    clips = sorted(MOVIES.glob('*.mov'))
    captions, shots = [], []
    cursor = 0.0
    for ci, chapter in enumerate(config['章节']):
        duration = float(chapter['时长'])
        sentences = re.findall(r'[^。！？]+[。！？]?', chapter['旁白'])
        weights = [len(s.strip()) for s in sentences]
        subt = cursor
        for si, (sentence, weight) in enumerate(zip(sentences, weights)):
            end = cursor + duration if si == len(sentences) - 1 else subt + duration * weight / sum(weights)
            # 所有分界对齐60fps，避免小片段累计时长误差。
            start_frame, end_frame = round(subt * 60), round(end * 60)
            captions.append({'start': start_frame / 60, 'end': end_frame / 60,
                             'text': sentence.strip(), 'chapter': ci + 1})
            subt = end
        local = cursor
        for index, source_start, shot_duration, speed in chapter['镜头']:
            src = clips[index - 1]
            info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(src)]))
            if source_start + shot_duration * speed > float(info['format']['duration']):
                raise ValueError(f'镜头超出原片: {src.name}')
            shots.append({'start': local, 'end': local + shot_duration, 'source': str(src),
                          'source_start': source_start, 'speed': speed, 'chapter': ci + 1})
            local += shot_duration
        if abs(local - cursor - duration) > 1e-6:
            raise ValueError('章节镜头总时长不一致')
        cursor += duration

    srt = ''.join(f"{i}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}\n\n"
                  for i, c in enumerate(captions, 1))
    (out / '项目介绍字幕.srt').write_text(srt)
    segments = []
    for cap in captions:
        chapter = config['章节'][cap['chapter'] - 1]
        overlay = Image.new('RGBA', (1920, 1080), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        d.rectangle((0, 0, 1919, 79), fill='#131820')
        d.rectangle((0, 980, 1919, 1079), fill='#131820')
        d.rectangle((0, 76, 1919, 79), fill='#283241')
        d.rounded_rectangle((44, 21, 53, 59), radius=4, fill='#6EE7CA')
        title_font = ImageFont.truetype(FONT, 30)
        small_font = ImageFont.truetype(FONT, 19)
        subtitle_font = ImageFont.truetype(FONT, 34)
        d.text((70, 19), '以撒 · Switch 模组运行时', font=title_font, fill='#F5F8FC')
        right = f"{cap['chapter']:02d} / 08    {chapter['标题']}"
        d.text((1875 - title_font.getlength(right), 22), right, font=title_font, fill='#A8C1C7')
        # 两侧的说明不覆盖游戏区域。
        d.text((15, 100), '实机录制', font=small_font, fill='#78919D')
        d.text((15, 133), '开发测试版', font=small_font, fill='#78919D')
        for i in range(8):
            y = 420 + i * 27
            d.rounded_rectangle((73, y, 87, y + 13), radius=4,
                                fill='#6EE7CA' if i == cap['chapter'] - 1 else '#2B3745')
        lines = wrap(cap['text'], subtitle_font, 1670)
        if len(lines) > 2:
            raise ValueError(f'字幕超出两行: {cap["text"]}')
        top = 1008 if len(lines) == 1 else 987
        for line_index, line in enumerate(lines):
            d.text(((1920 - subtitle_font.getlength(line)) / 2, top + line_index * 43),
                   line, font=subtitle_font, fill='#F5F8FC')
        png = assets / f"字幕-{len(segments):03d}.png"
        overlay.save(png)
        for shot in shots:
            start, end = max(cap['start'], shot['start']), min(cap['end'], shot['end'])
            if end - start < 1 / 120:
                continue
            source_start = shot['source_start'] + (start - shot['start']) * shot['speed']
            segments.append({**shot, 'start': start, 'end': end, 'source_start': source_start,
                             'overlay': str(png), 'frames': round((end - start) * 60)})
    if sum(s['frames'] for s in segments) != round(cursor * 60):
        raise ValueError('画面总帧数不等于时间线总帧数')
    (assets / '渲染清单.json').write_text(json.dumps(segments, ensure_ascii=False, indent=2))
    print(f'准备完成：{cursor:.1f}秒，{len(captions)}条逐句字幕，{len(segments)}个片段', flush=True)
    return out, assets, segments


def render(config):
    out, assets, segments = prepare(config)
    parts = []
    for i, seg in enumerate(segments):
        target = assets / f'片段-{i:03d}.mp4'
        parts.append(target)
        if target.exists():
            probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(target)]))
            if int(probe['streams'][0].get('nb_frames', -1)) == seg['frames']:
                continue
        vf = f"[0:v]setpts=(PTS-STARTPTS)/{seg['speed']},fps=60,scale=1600:900:flags=lanczos,pad=1920:1080:160:80:color=0x131820[v];[v][1:v]overlay=0:0:format=auto,format=yuv420p[out]"
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-threads', '2',
             '-ss', str(seg['source_start']), '-i', seg['source'], '-loop', '1', '-i', seg['overlay'],
             '-filter_complex_threads', '1', '-filter_complex', vf, '-map', '[out]', '-an',
             '-frames:v', str(seg['frames']), '-c:v', 'h264_videotoolbox', '-b:v', '9M',
             '-maxrate', '12M', '-bufsize', '18M', '-tag:v', 'avc1', '-movflags', '+faststart', str(target)])
        print(f'渲染 {i+1}/{len(segments)}，当前累计{seg["end"]:.2f}秒', flush=True)
    listing = assets / '拼接列表.txt'
    listing.write_text(''.join(f"file '{p.name}'\n" for p in parts))
    master = out / '项目介绍-120秒-画面母版-无音轨.mp4'
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0',
         '-i', str(listing), '-map', '0:v:0', '-c', 'copy', '-movflags', '+faststart', str(master)])
    print('画面母版已生成：' + str(master), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    cfg = json.loads((HERE / '时间线.json').read_text())
    prepare(cfg) if args.prepare else render(cfg)
