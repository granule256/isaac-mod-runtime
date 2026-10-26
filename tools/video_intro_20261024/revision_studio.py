#!/usr/bin/env python3
"""修订版的原生字幕设置与异步导出；不覆盖初版成片。"""
import argparse
import hashlib
import json
from pathlib import Path
from studio_control import PROJECT, request
from build_revision import preserve_write

NAME = '以撒Switch模组项目-简短展示版'
EVIDENCE_DIR = PROJECT / '核验-简短展示版'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['style', 'preview', 'stills', 'text-preview', 'render', 'status'])
    args = parser.parse_args()
    manifest = json.loads((PROJECT / '完整版修订时间线与素材清单.json').read_text())
    project = next(p for p in request('/api/projects')['projects'] if Path(p['path']) == PROJECT)
    base = '/api/projects/' + project['id']
    out = EVIDENCE_DIR
    out.mkdir(exist_ok=True)
    if args.action == 'style':
        style = {
            'on': True, 'pos': {'x': .5, 'y': .935}, 'maxWidthPct': 88, 'align': 'center',
            'font': {'family': '"PingFang SC", "Hiragino Sans GB", sans-serif',
                     'sizePct': 3.7, 'weight': 500, 'italic': False,
                     'letterSpacingEm': 0, 'lineHeight': 1.35, 'upper': False},
            'fill': '#FFFFFF', 'stroke': {'widthEm': .035, 'color': '#000000'},
            'shadow': None,
            'box': {'color': '#000000', 'opacity': .65, 'radiusEm': .08, 'padXEm': .35, 'padYEm': .12},
            'karaoke': None, 'language': None, 'bilingual': False,
        }
        result = request(base + '/subtitles', {'style': style}, 'PUT')
        captions = request(base + '/captions')
        assert len(captions['cues']) == len(manifest['captions'])
        assert captions['cues'][0]['startMs'] == 0
        last = captions['cues'][-1]
        assert last['startMs'] + last['durMs'] == manifest['duration'] * 1000
        preserve_write(out / '原生字幕核验.json', json.dumps({'style': result['style'], **captions}, ensure_ascii=False, indent=2))
        (PROJECT / '完整版修订字幕样式.json').write_text(json.dumps(result['style'], ensure_ascii=False, indent=2))
        print('普通中文字幕已设置，字幕', len(captions['cues']), '条，总时长', manifest['duration'])
    elif args.action in ('preview', 'stills', 'text-preview'):
        at = [(s['start'] + s['end']) / 2 for s in manifest['scenes']]
        body = {'folder': str(out), 'jobs': [
            {'kind': 'stills', 'format': 'jpg', 'shortEdge': 1080, 'at': at,
             'burnSubtitles': True, 'name': '简短版逐段审片'},
            {'kind': 'video', 'range': [0, 8], 'fps': 60, 'shortEdge': 720,
             'codec': 'h264', 'quality': 'high', 'burnSubtitles': True,
             'audio': True, 'sidecar': 'srt', 'name': '简短版八秒审片'},
        ]}
        if args.action == 'text-preview':
            body['jobs'] = [{'kind': 'stills', 'format': 'jpg', 'shortEdge': 1080,
                             'at': [(c['start'] + c['end']) / 2 for c in sorted(manifest['captions'], key=lambda c:len(c['text']), reverse=True)[:4]],
                             'burnSubtitles': True, 'name': '简短版最长字幕排版检查'}]
        elif args.action == 'stills':
            body['jobs'] = body['jobs'][:1]
        result = request(base + '/exports', body)
        (out / '预览任务.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == 'render':
        assert not (PROJECT / (NAME + '.mp4')).exists(), '正式成片已有版本，勿重复导出'
        files = [PROJECT / 'film.html', *sorted((PROJECT / '修订页面').glob('*.html')),
                 (PROJECT / manifest.get('caption_clock_asset', 'assets/字幕时钟.wav')).with_suffix('.vtt'), PROJECT / '.film/subtitles.json']
        freeze = {str(p.relative_to(PROJECT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        (out / '正式导出工程SHA256.json').write_text(json.dumps(freeze, ensure_ascii=False, indent=2))
        result = request(base + '/exports', {'folder': str(PROJECT), 'jobs': [
            {'kind': 'video', 'fps': 60, 'shortEdge': 1080, 'codec': 'h264', 'quality': 'high',
             'burnSubtitles': True, 'audio': True, 'sidecar': 'srt', 'name': NAME},
        ]})
        (out / '正式导出任务.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False))
    else:
        jobs = request(base + '/exports')['exports']
        selected = [j for j in jobs if j.get('ask', {}).get('name', '').startswith(('简短版', NAME))]
        (out / '导出状态.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
        print(json.dumps([{k: j.get(k) for k in ['id', 'kind', 'status', 'progress', 'phase', 'framesDone',
                                                'framesTotal', 'rate', 'etaMs', 'outputs', 'error']}
                          for j in selected], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
