#!/usr/bin/env python3
"""通过 OpenFilm 自带的本地 API 配置字幕、异步导出与读取结果。"""
import argparse
import json
import urllib.request
from pathlib import Path

PROJECT = Path('/Users/kelinls/Movies/项目介绍-OpenFilm-20261024')


def request(route, body=None, method=None):
    run = json.loads((Path.home() / '.openfilm/run.json').read_text())
    headers = {'x-studio-key': run['key'], 'content-type': 'application/json'}
    req = urllib.request.Request(run['origin'] + route,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main(command):
    projects = request('/api/projects')['projects']
    project = next(p for p in projects if Path(p['path']) == PROJECT)
    base = '/api/projects/' + project['id']
    evidence = PROJECT / '核验'
    evidence.mkdir(exist_ok=True)
    if command == 'style':
        result = request(base + '/subtitles', {'style': {
            'on': True, 'pos': {'x': .5, 'y': .95}, 'maxWidthPct': 88, 'align': 'center',
            'font': {'family': '"PingFang SC", "Hiragino Sans GB", sans-serif',
                     'sizePct': 3.9, 'weight': 550, 'italic': False,
                     'letterSpacingEm': .025, 'lineHeight': 1.25, 'upper': False},
            'fill': '#F2EEE7', 'stroke': None, 'shadow': None, 'box': None,
            'karaoke': None, 'language': None, 'bilingual': False,
        }}, 'PUT')
        captions = request(base + '/captions')
        assert len(captions['cues']) == 29
        assert captions['cues'][0]['startMs'] == 0
        last = captions['cues'][-1]
        assert last['startMs'] + last['durMs'] == 120000
        (evidence / '原生字幕核验.json').write_text(json.dumps(
            {'style': result['style'], **captions}, ensure_ascii=False, indent=2))
        print('已通过原生API设置字幕样式，29条字幕完整覆盖120秒')
    elif command in ('preview', 'stills'):
        jobs = [
            {'kind': 'stills', 'format': 'png', 'shortEdge': 1080,
             'at': [1.5, 15, 29, 49, 65, 82, 96, 112, 119],
             'burnSubtitles': True, 'name': '逐章审片'},
            {'kind': 'video', 'range': [0, 5], 'fps': 60, 'shortEdge': 720,
             'codec': 'h264', 'quality': 'high', 'burnSubtitles': True,
             'audio': True, 'sidecar': 'srt', 'name': '五秒导出审片'},
        ]
        if command == 'stills':
            jobs = jobs[:1]
            jobs[0]['name'] = '逐章审片-字幕位置修正'
        result = request(base + '/exports', {'folder': str(evidence), 'jobs': jobs})
        (evidence / '预览任务.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False))
    elif command == 'render':
        result = request(base + '/exports', {'folder': str(PROJECT), 'jobs': [
            {'kind': 'video', 'fps': 60, 'shortEdge': 1080, 'codec': 'h264', 'quality': 'high',
             'burnSubtitles': True, 'audio': True, 'sidecar': 'srt',
             'name': '以撒Switch模组运行时-项目介绍-中文字幕版'},
        ]})
        (evidence / '正式导出任务.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False))
    elif command == 'status':
        result = request(base + '/exports')
        (evidence / '导出状态.json').write_text(json.dumps(result['exports'], ensure_ascii=False, indent=2))
        print(json.dumps([{
            k: j.get(k) for k in ['id', 'kind', 'status', 'progress', 'phase', 'framesDone',
                                  'framesTotal', 'rate', 'etaMs', 'encoder', 'outputs', 'error']
        } for j in result['exports']], ensure_ascii=False, indent=2))
    elif command == 'captions':
        print(json.dumps(request(base + '/captions'), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['style', 'preview', 'stills', 'render', 'status', 'captions'])
    main(parser.parse_args().command)
