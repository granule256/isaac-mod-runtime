#!/usr/bin/env python3
"""核验最终确认版的成片、字幕、素材与导出期间的工程指纹。"""
import hashlib
import json
import subprocess
from fractions import Fraction
from pathlib import Path
from revision_studio import NAME, EVIDENCE_DIR

PROJECT = Path('/Users/kelinls/Movies/项目介绍-OpenFilm-20261024')
OUT = EVIDENCE_DIR


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    manifest = json.loads((PROJECT / '完整版修订时间线与素材清单.json').read_text())
    frames = round(manifest['duration'] * manifest['fps'])
    movie = PROJECT / (NAME + '.mp4')
    srt = PROJECT / (NAME + '.srt')
    jobs = json.loads((OUT / '导出状态.json').read_text())
    job = next(j for j in jobs if j['ask'].get('name') == NAME)
    assert job['status'] == 'done' and job['framesDone'] == job['framesTotal'] == frames
    probe = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(movie)]))
    (OUT / '成片媒体信息.json').write_text(json.dumps(probe, ensure_ascii=False, indent=2))
    video = [s for s in probe['streams'] if s['codec_type'] == 'video']
    sound = [s for s in probe['streams'] if s['codec_type'] == 'audio']
    assert len(video) == len(sound) == 1
    v = video[0]
    assert (v['width'], v['height']) == (1920, 1080)
    assert Fraction(v['avg_frame_rate']) == 60 and int(v['nb_frames']) == frames
    assert abs(float(v['duration']) - manifest['duration']) < .03
    assert abs(float(sound[0]['duration']) - manifest['duration']) < .08
    assert srt.read_text().count('-->') == len(manifest['captions'])
    subs = json.loads((OUT / '原生字幕核验.json').read_text())
    assert len(subs['cues']) == len(manifest['captions'])
    last = subs['cues'][-1]
    assert last['startMs'] + last['durMs'] == manifest['duration'] * 1000
    assert all(m['type'] != '文字说明页' for s in manifest['scenes'] for m in s['media'])
    text = ''.join(c['text'] for c in manifest['captions'])
    for unwanted in ['先介绍项目，再看', '接下来按实际用途', '补齐环节', '持续完善']:
        assert unwanted not in text
    assert '项目后面也会开源' in text and '顺手点个赞' in text
    for scene in manifest['scenes']:
        if scene['id'] in ('eid', 'goodtrip', 'console', 'specialist'):
            assert scene['duration'] == 8
            assert sum(scene['start'] <= c['start'] < scene['end'] for c in manifest['captions']) == 1
    before = json.loads((OUT / '正式导出工程SHA256.json').read_text())
    assert all(sha(PROJECT / rel) == digest for rel, digest in before.items())
    checked = []
    for item in manifest['pictures']:
        assert sha(Path(item['source'])) == sha(PROJECT / item['asset']) == item['sha256']
        checked.append({'素材': item['asset'], 'sha256': item['sha256'], '原件副本一致': True})
    old_master = PROJECT / '以撒Switch模组运行时-项目介绍-中文字幕版.mp4'
    assert sha(old_master) == '4d69c5ccd0e9036216cccde3e27c61d652bb83a54df6846d4312324f2a35002c'
    detailed_master = PROJECT / '以撒Switch模组项目-介绍视频-最终修订版.mp4'
    assert sha(detailed_master) == 'cc73755b876ac21d786a8caa4f501da476af80287b639d8816717b1c41c83d10'
    with (OUT / '完整解码错误日志.txt').open('w') as errors:
        run = subprocess.run([
            'ffmpeg', '-hide_banner', '-v', 'error', '-xerror', '-threads', '2',
            '-i', str(movie), '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'],
            stdout=subprocess.DEVNULL, stderr=errors)
    assert run.returncode == 0
    with (OUT / '音轨响度检查.txt').open('w') as loudness:
        audio = subprocess.run([
            'ffmpeg', '-hide_banner', '-nostats', '-i', str(movie), '-vn',
            '-af', 'ebur128=peak=true', '-f', 'null', '-'], stdout=subprocess.DEVNULL, stderr=loudness)
    assert audio.returncode == 0
    result = {
        '日期': '2026-10-24', '成片': str(movie), '字幕': str(srt),
        '时长秒': manifest['duration'], '帧率': 60, '帧数': frames, '分辨率': [1920, 1080],
        '字幕条数': len(manifest['captions']), '文件字节数': movie.stat().st_size,
        'sha256': sha(movie), '完整音视频解码退出码': run.returncode,
        '解码错误日志字节': (OUT / '完整解码错误日志.txt').stat().st_size,
        '初版成片未变': True, '详细版成片未变': True,
        '四项各八秒且一句字幕': True, '工程导出前后指纹一致': True, '素材检查': checked,
        '声音': '无配音；轻背景音乐，跳舞录像段保留原生游戏声音，用户原录像声音全部排除',
        '取材': 'GoodTrip与跳舞使用本轮Switch原生30秒录像，角色等辅以注明来源的实机截图',
    }
    (OUT / '最终核验.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
