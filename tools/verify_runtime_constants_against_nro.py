#!/usr/bin/env python3
"""逐条核对 `runtime_constants.hpp` 里的守卫字节与真实游戏镜像。

存在的理由：`hook_manager.cpp` 的每个 `Verify*` 都用 `memcmp` 精确比较 16 字节守卫，**一个字节
抄错就让整个绑定静默失效**——没有日志、没有报错，只是"这个 API 永远装不上"。2026-09-13 就是
这样发现的：`kGameIsGreedModeExpectedBytes` 第 10 字节写成 `0xB8`（真值 `0x68`），使
`Game:IsGreedMode` 在真机上从未可用。所以每次构建/部署前跑一遍这个工具。

判据：
  * `kXOffset` + `kXExpectedBytes` / `kXExpectedEntry` / `kXExpectedOriginal`（以及 `kXFileOffset` /
    `kXCallFileOffset` 这些写法）配对；
  * 与 `Repentance.nro` 同偏移的字节逐字节比较；
  * **例外**：`tools/build_patches.py` 会写入的偏移（中继入口与代码洞）在原始镜像里本来就是
    未打补丁的样子，它们的期望值描述的是**打补丁后**的镜像，因此归为 `patched-image`，不计入不符。

★★★ 2026-09-29（批次 210）**这个工具曾经"看着在跑、其实漏了一整类常量"**，两个洞都补上了：

| 洞 | 后果 | 现在 |
| --- | --- | --- |
| `ARRAY_PATTERN` 只认 `ExpectedBytes` / `ExpectedEntry` 两个后缀 ⇒ `*Discriminator` 数组**连解析都进不去** | 判别式常量写错字节 ⇒ 守卫在真机上永远不比中 ⇒ 绑定静默不发布、那条 API 恒答假值。**2026-09-29 的真事故**：`Input.IsButtonTriggered`/`IsButtonPressed` 因为判别式写成了反汇编里的字面顺序（`F9 40 19 08`，真值 `08 19 40 F9`）而在真机上整条哑掉，MCM"按右摇杆开菜单"永远没反应 | 后缀表加 `Discriminator`（比在"入口偏移 + 判别式偏移"上，判别式偏移在 `DISCRIMINATOR_OFFSETS` 里显式登记）与 `ExpectedOriginal` |
| 基名剥离只按最长后缀剥一次 ⇒ 基名自己以 `File` 结尾的偏移（`kImageManagerLoadFileOffset`、`kSaveDataDeleteFileOffset`）被切成 `kImageManagerLoad` / `kSaveDataDelete`，与数组名 `k...LoadFileExpectedBytes` **配不上** ⇒ 那两条守卫**从来没跟镜像比过** | 静默漏检（和"常量写错"同一种后果，只是发生在"根本没比"这一侧） | 两种剥法都试（`FileOffset` 与只剥 `Offset`），配对集合变大、漏检消失 |

配套测试 `runtime/tests/test_runtime_constants_against_nro.py` 也补了判据：**`unpaired_arrays` 里
只允许出现"中继载荷/上下文"那一族**（名字含 `Relay` 或以 `ContextExpectedBytes` 结尾），
否则判红 —— 免得以后新加一个守卫常量、名字换了后缀，又静默地"没比过"。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import build_patches


DEFAULT_NRO = (
    "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    "/Program #0/1/.nro/Repentance.nro"
)
DEFAULT_CONSTANTS = "runtime/source/runtime_constants.hpp"
OFFSET_PATTERN = re.compile(r"inline constexpr (?:std::)?uintptr_t (k\w+?) = (0x[0-9A-Fa-f]+);")
#: 数组侧认的后缀（从两个扩到四个）。
#: `Discriminator`：只用 4 字节区分"形同一模一样的入口"（`KAGE::Input` 那四条），
#: 比的位置是"**入口偏移 + 判别式偏移**"，不是入口本身 ── 见 `DISCRIMINATOR_OFFSETS`。
#: `ExpectedOriginal`：打补丁前原始镜像里的字节（中继入口那一族）。
ARRAY_SUFFIXES = ("ExpectedBytes", "ExpectedEntry", "ExpectedOriginal", "Discriminator")
ARRAY_PATTERN = re.compile(
    r"inline constexpr std::array<u8, (\d+)> (k\w+?(?:" + "|".join(ARRAY_SUFFIXES) + r")) = \{(.*?)\};",
    re.S,
)
OFFSET_SUFFIXES = ("FileOffset", "CallFileOffset", "Offset")

#: 判别式数组 → 它那个"判别式偏移"常量的名字（**显式登记，不猜名字**）。
#: 为什么不按 `<基名>DiscriminatorOffset` 推：判别式偏移常量与入口常量不同族
#: （`kKageIsButtonPressedOffset` ↔ `kKageInputButtonDiscriminatorOffset`）。
#: 没登记就按入口偏移直接比 —— 那样几乎必然不符、会判红，而不会静默放过。
DISCRIMINATOR_OFFSETS = {
    "kKageIsButtonPressedDiscriminator": "kKageInputButtonDiscriminatorOffset",
}


def patched_offsets() -> set[int]:
    """Offsets `tools/build_patches.py` writes into the game image."""
    offsets = set()
    for name in dir(build_patches):
        if not name.endswith("RECORDS"):
            continue
        records = getattr(build_patches, name)
        if not isinstance(records, list):
            continue
        for record in records:
            if isinstance(record, tuple) and record and isinstance(record[0], int):
                offsets.add(record[0])
    return offsets


def parse_constants(text: str):
    offsets = {name: int(value, 16) for name, value in OFFSET_PATTERN.findall(text)}
    arrays = {}
    for size, name, body in ARRAY_PATTERN.findall(text):
        values = bytes(int(value, 16) for value in re.findall(r"0x([0-9A-Fa-f]{2})", body))
        arrays[name] = (int(size), values)
    return offsets, arrays


def pair_guards(offsets, arrays):
    """Pair `kXExpected*` arrays with the `kX*Offset` constant that locates them.

    Only **exact base** matches are used (`kFontLoadExpectedBytes` -> `kFontLoadOffset`,
    `kManagerRenderExpectedBytes` -> `kManagerRenderFileOffset`,
    `kGameIsGreedModeExpectedBytes` -> `kGameIsGreedModeOffset`). Relay guards spell their location
    differently (`kManagerRenderRelayExpectedBytes` describes the *patched* code cave at
    `kManagerRenderRelayCodeOffset`, and several arrays share one offset), so they are reported as
    `unresolved` here instead of being force-paired: those guards describe the post-patch image and
    are checked at boot by the Runtime's own `Verify*` functions, with `tools/build_patches.py`
    computing the very same bytes.

    ★ 2026-09-29（批次 210）两处修正：

    * **偏移侧的基名有两种剥法**（`kXxxFileOffset` 既可能是 `kXxx` 的 `FileOffset`、也可能是
      `kXxxFile` 的 `Offset`）。原来只按最长后缀剥一次 ⇒ 基名自己以 `File` 结尾的那两条
      （`kImageManagerLoadFileOffset` 0x4D1FE4、`kSaveDataDeleteFileOffset` 0x4CDD18）
      与数组 `k...LoadFileExpectedBytes` / `k...DeleteFileExpectedBytes` **配不上**，
      于是那两条 16 字节守卫**从来没跟镜像比过**。现在两种剥法都收进候选。
    * `Discriminator` 数组比在"**入口偏移 + 判别式偏移**"上（判别式偏移查
      `DISCRIMINATOR_OFFSETS`），不是比在入口那几个字节上。
    """
    by_base = {}
    for name, offset in offsets.items():
        for suffix in OFFSET_SUFFIXES:
            if name.endswith(suffix):
                entry = (name, suffix, offset)
                bucket = by_base.setdefault(name[: -len(suffix)], [])
                if entry not in bucket:
                    bucket.append(entry)
                break
    # 第二种剥法：只剥 `Offset`（基名保留它自己的 `File` / `CallFile` 尾巴）。
    for name, offset in offsets.items():
        if name.endswith("Offset"):
            entry = (name, "Offset", offset)
            bucket = by_base.setdefault(name[: -len("Offset")], [])
            if entry not in bucket:
                bucket.append(entry)
    pairs, unpaired = [], []
    for array_name, (size, values) in sorted(arrays.items()):
        base = array_name
        for suffix in ARRAY_SUFFIXES:
            if array_name.endswith(suffix):
                base = array_name[: -len(suffix)]
                break
        candidates = by_base.get(base, [])
        if not candidates:
            unpaired.append(array_name)
            continue
        # Prefer the plain `...Offset` spelling, then `...FileOffset`, then `...CallFileOffset`.
        candidates.sort(key=lambda item: OFFSET_SUFFIXES.index(item[1]))
        offset_name, suffix, offset = candidates[0]
        if array_name.endswith("Discriminator"):
            discriminator = DISCRIMINATOR_OFFSETS.get(array_name)
            if discriminator is None or discriminator not in offsets:
                # 没登记判别式偏移 ⇒ 按入口偏移比（几乎必然不符、判红），**不静默跳过**。
                unpaired.append(array_name)
                continue
            offset += offsets[discriminator]
            offset_name = f"{offset_name} + {discriminator}"
        pairs.append({
            "array": array_name,
            "offset_name": offset_name,
            "offset": offset,
            "declared_size": size,
            "expected": values,
        })
    return pairs, unpaired


def check(constants_text: str, nro: bytes, patched: set[int] | None = None) -> dict:
    patched = patched_offsets() if patched is None else patched
    offsets, arrays = parse_constants(constants_text)
    pairs, unpaired = pair_guards(offsets, arrays)
    # content表的共享序言没有唯一命名偏移；按每一行真实消费者地址核对，不能任选一行。
    content_table = re.search(r"kModContentFeedSpecs\s*=\s*\{\{(.*?)\}\};", constants_text, re.S)
    if content_table:
        for value, array_name in re.findall(
            r"\{\s*(0x[0-9A-Fa-f]+)\s*,\s*(k\w+)\.data\(\),\s*\2\.size\(\)",
            content_table.group(1)
        ):
            if array_name not in arrays:
                continue
            size, data = arrays[array_name]
            pairs.append({"array":array_name,"offset_name":f"kModContentFeedSpecs @ {value}",
                          "offset":int(value,16),"declared_size":size,"expected":data})
            if array_name in unpaired:
                unpaired.remove(array_name)
    results = []
    for pair in pairs:
        expected = pair["expected"]
        entry = {key: value for key, value in pair.items() if key != "expected"}
        entry["expected_hex"] = expected.hex().upper()
        if len(expected) != pair["declared_size"]:
            entry["status"] = "declared-size-mismatch"
        elif pair["offset"] in patched:
            entry["status"] = "patched-image"
        elif pair["offset"] + len(expected) > len(nro):
            entry["status"] = "out-of-range"
        else:
            actual = nro[pair["offset"]:pair["offset"] + len(expected)]
            entry["actual_hex"] = actual.hex().upper()
            entry["status"] = "match" if actual == expected else "mismatch"
        results.append(entry)
    failures = [entry for entry in results if entry["status"] not in ("match", "patched-image")]
    return {
        "checked": len(results),
        "matched": sum(1 for entry in results if entry["status"] == "match"),
        "patched_image": sum(1 for entry in results if entry["status"] == "patched-image"),
        "failures": failures,
        "unpaired_arrays": unpaired,
        "offsets_without_guard": sorted(
            name for name in offsets
            if not any(entry["offset_name"] == name for entry in results)
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--constants", type=Path, default=Path(DEFAULT_CONSTANTS))
    parser.add_argument("--nro", type=Path, default=Path(DEFAULT_NRO))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    nro = args.nro.read_bytes()
    report = check(args.constants.read_text(encoding="utf-8"), nro)
    report["nro"] = str(args.nro)
    report["nro_size"] = len(nro)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["failures"]:
        print(f"\n{len(report['failures'])} 条守卫与镜像不符", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
