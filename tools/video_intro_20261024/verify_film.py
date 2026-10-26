#!/usr/bin/env python3
"""核验交付媒体；不会启动游戏、改原录像或运行项目门禁。"""
import hashlib
import json
import subprocess
from fractions import Fraction
from pathlib import Path

PROJECT = Path('/Users/kelinls/Movies/项目介绍-OpenFilm-20261024')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    evidence = PROJECT / '核验'
    jobs = json.loads((evidence / '导出状态.json').read_text())
    final = next(j for j in jobs if j['kind'] == 'video' and j['status'] == 'done'
                 and j['ask'].get('name') == '以撒Switch模组运行时-项目介绍-中文字幕版')
    movie = next(Path(p) for p in final['outputs'] if p.endswith('.mp4'))
    sidecar = next(Path(p) for p in final['outputs'] if p.endswith('.srt'))
    probe = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(movie)]))
    (evidence / '成片媒体信息.json').write_text(json.dumps(probe, ensure_ascii=False, indent=2))
    videos = [s for s in probe['streams'] if s['codec_type'] == 'video']
    audio = [s for s in probe['streams'] if s['codec_type'] == 'audio']
    assert len(videos) == 1 and len(audio) == 1
    video = videos[0]
    assert (video['width'], video['height']) == (1920, 1080)
    assert Fraction(video['avg_frame_rate']) == 60
    assert int(video['nb_frames']) == 7200
    assert abs(float(video['duration']) - 120) < .02
    assert abs(float(audio[0]['duration']) - 120) < .06
    assert 29 == sidecar.read_text().count('-->')
    captions = json.loads((evidence / '原生字幕核验.json').read_text())
    assert len(captions['cues']) == 29
    assert captions['style']['pos']['y'] == .95
    manifest = json.loads((PROJECT / '时间线与素材清单.json').read_text())
    source_checks = []
    for item in manifest['sources']:
        original, copied = Path(item['source']), PROJECT / 'assets' / item['asset']
        original_sha, copied_sha = sha(original), sha(copied)
        assert item['sha256'] == original_sha == copied_sha
        source_checks.append({'原片': str(original), 'sha256': original_sha, '副本一致': True})
    with (evidence / '完整解码错误日志.txt').open('w') as errors:
        decoded = subprocess.run([
            'ffmpeg', '-hide_banner', '-v', 'error', '-xerror', '-threads', '2',
            '-i', str(movie), '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'],
            stdout=subprocess.DEVNULL, stderr=errors)
    assert decoded.returncode == 0
    # 响度检测只读取最终单一音轨，原录像音轨通过film.html/原生look的声轨来源核对。
    with (evidence / '背景音乐响度.txt').open('w') as loudness:
        checked = subprocess.run([
            'ffmpeg', '-hide_banner', '-nostats', '-i', str(movie), '-vn',
            '-af', 'ebur128=peak=true', '-f', 'null', '-'],
            stdout=subprocess.DEVNULL, stderr=loudness)
    assert checked.returncode == 0
    result = {
        '日期': '2026-10-24', '视频': str(movie), '字幕': str(sidecar),
        '时长秒': float(video['duration']), '分辨率': [video['width'], video['height']],
        '帧率': 60, '总帧数': 7200, '字幕条数': 29,
        '声音': '单一原创器乐背景音乐，无旁白，原录像音轨均muted',
        '完整音视频解码退出码': decoded.returncode,
        '解码错误日志字节': (evidence / '完整解码错误日志.txt').stat().st_size,
        '视频SHA256': sha(movie), '原片与副本核验': source_checks,
        '限制': '没有哈基米配音；字幕按阅读节奏排布，不宣称语音同步；实机画面来自2026-10-20录像。',
    }
    (evidence / '最终核验.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
