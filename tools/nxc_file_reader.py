"""按设备 stat 大小读取文件；禁止依赖 fs.read 的越界/EOF 行为。"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

NXC_DIR = Path('/Users/kelinls/code/github/KELI-NX')
CHUNK = 2000


def call(command):
    result = subprocess.run([sys.executable, 'pc/nxc.py', '--json', command],
        capture_output=True, text=True, cwd=NXC_DIR,
        env={**os.environ, 'NXC_DEVICE_IP': '192.168.124.11'})
    if result.returncode:
        raise ValueError((result.stdout + result.stderr).strip()[:400])
    # 正文可能回显命令；返回码判定失败，payload 是唯一数据来源。
    output = result.stdout.strip()
    start = output.find('[')
    if start < 0:
        raise ValueError('响应中没有 JSON')
    rows = json.loads(output[start:])
    if len(rows) != 1:
        raise ValueError('响应条数不符')
    row = rows[0]
    if not isinstance(row, dict) or 'error' in row or not row.get('header', '').startswith('OK '):
        raise ValueError(f'设备协议返回失败：{row}')
    return row.get('payload', [])


def path_argument(remote):
    if '\x00' in remote or '\n' in remote or '\r' in remote:
        raise ValueError('路径包含空字符或换行')
    # 协议以空白分词，没有引号语法；百分号是解码前缀，文件名中的字面 % 必须编码。
    return ''.join(f'%{ord(ch):02X}' if ch == '%' or ch == ' ' or ord(ch) < 0x20
                   or ord(ch) == 0x7f else ch for ch in remote)


def file_size(remote):
    payload = call(f'fs.stat path={path_argument(remote)}')
    for row in payload:
        if isinstance(row, dict) and 'size' in row:
            size = int(row['size'])
            if size >= 0:
                return size
    raise ValueError('fs.stat 没有有效文件大小')


def blocks(remote, size):
    offset = 0
    while offset < size:
        requested = min(CHUNK, size - offset)
        payload = call(f'fs.read path={path_argument(remote)} offset={offset} len={requested}')
        encoded = next((row for row in payload if isinstance(row, str)), None)
        if encoded is None:
            raise ValueError(f'@{offset} 没有 base64 数据行')
        block = base64.b64decode(encoded, validate=True)
        if not block or len(block) > requested:
            raise ValueError(f'@{offset} 返回 {len(block)} 字节，请求 {requested} 字节')
        for row in payload:
            if isinstance(row, dict) and 'bytes' in row and int(row['bytes']) != len(block):
                raise ValueError(f'@{offset} 返回长度与 bytes 字段不符')
        yield block
        offset += len(block)
