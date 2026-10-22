#!/usr/bin/env python3
"""在已恢复房间音乐的Specialist脚本上补MMC公开选曲交接，保留行尾。"""
from pathlib import Path
import argparse


def patch(source: bytes) -> bytes:
    newline = b'\r\n' if b'\r\n' in source else b'\n'
    text = source.replace(b'\r\n', b'\n')
    marker = b'local wasPog = false;\n'
    entry = b'function Epic:DoCostume(apply)\n    result = false'
    if (text.count(marker) != 1 or text.count(entry) != 1 or
            text.count(b'MMC.Manager():Crossfade(MMC.GetMusicTrack());') != 1 or
            b'local activeDanceMusic' in text):
        raise ValueError('Specialist已验恢复版形状不匹配，拒绝修改')
    bridge = b'''
local activeDanceMusic
local registeredDanceMMC
local function EnsureDanceMusicCallback()
    if MMC and MMC.Initialised and registeredDanceMMC ~= MMC then
        local owner = MMC
        owner.AddMusicCallback(Epic, function(_, track)
            if activeDanceMusic and EpicSettings["EnableMusic"] and
                track == owner.GetMusicTrack() then
                return activeDanceMusic
            end
        end)
        registeredDanceMMC = owner
    end
end
if ModCallbacks.MC_PRE_MOD_UNLOAD then
    Epic:AddCallback(ModCallbacks.MC_PRE_MOD_UNLOAD, function()
        activeDanceMusic = nil
        if registeredDanceMMC then registeredDanceMMC.RemoveMusicCallback(Epic) end
        registeredDanceMMC = nil
    end)
end
'''
    text = text.replace(marker, marker + bridge, 1)
    text = text.replace(entry, b'''function Epic:DoCostume(apply)
    -- Clear before restoring, so MMC can select the room track again.
    if not apply or not EpicSettings["EnableMusic"] then activeDanceMusic = nil end
    EnsureDanceMusicCallback()
    result = false''', 1)
    for name in [b'customMusic', b'specialist', b'paincialist']:
        needle = b'if MusicManager():GetCurrentMusicID() ~= ' + name + b' then'
        if text.count(needle) != 1:
            raise ValueError('作者舞曲选择分支形状不匹配')
        position = text.index(needle)
        indentation = text[text.rfind(b'\n', 0, position) + 1:position]
        replacement = (b'activeDanceMusic = ' + name + b';\n' + indentation +
                       b'wasPog = true;\n' + indentation + needle)
        text = text.replace(needle, replacement, 1)
        old = (b'MusicManager():Play(' + name + b', 1);\n' + indentation +
               b'    wasPog = true;')
        if text.count(old) != 1:
            raise ValueError('作者播放标记形状不匹配')
        text = text.replace(old, b'MusicManager():Play(' + name + b', 1);', 1)
    return text.replace(b'\n', newline)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('必须另存候选，保留设备原件')
    args.output.write_bytes(patch(args.source.read_bytes()))
