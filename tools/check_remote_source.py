#!/usr/bin/env python3
"""Check the staged index or a Git revision; never modify files or push."""
import argparse
from pathlib import Path, PurePosixPath
import subprocess
import tempfile

ROOT_FILES = {'.gitignore', 'README.md', 'LICENSE'}
RUNTIME_FILES = {'.gitignore', 'Makefile', 'config.json', 'config.mk', 'exlaunch.sh'}
RUNTIME_DIRS = {'source', 'src', 'misc', 'tools', 'tests', 'game_patches', 'probes'}
FORBIDDEN_PREFIXES = (
    'runtime/tests/evidence/', 'runtime/tests/fixtures/minimap_native_longpress/',
    'tools/video_intro_', 'tools/test_fixtures/eid-highlight/',
    'runtime/tests/fixtures/mod_', 'runtime/tests/fixtures/stageapi_shared_init/',
    'runtime/tests/fixtures/minimapapi_frame_events/',
    'runtime/tests/fixtures/shared_item_images/',
)
SOURCE_SUFFIXES = {'.py', '.cpp', '.hpp', '.h', '.c', '.s', '.asm', '.sh', '.mk',
                   '.ld', '.specs', '.json', '.txt', '.js', '.java'}
INPUT_DOC_DIRS = ('tools/pc_contract_docs/', 'tools/pc_enum_docs/')
PROVENANCE_DOC = 'runtime/source/third_party/lua-5.3.3/SOURCE.md'


def path_error(path):
    p = PurePosixPath(path)
    if p.is_absolute() or '..' in p.parts:
        return 'unsafe path'
    if path in ROOT_FILES:
        return None
    if p.name.lower().startswith('readme'):
        return 'project documentation belongs in root README.md'
    if len(p.parts) < 2 or p.parts[0] not in {'runtime', 'tools', 'tests'}:
        return 'outside approved source roots'
    if p.parts[0] == 'runtime' and not (
        (len(p.parts) == 2 and p.name in RUNTIME_FILES) or p.parts[1] in RUNTIME_DIRS
    ):
        return 'outside active runtime source/build/test directories'
    if path.startswith(FORBIDDEN_PREFIXES):
        return 'local experiment, payload, media or evidence'
    for part in p.parts[:-1]:
        if (part in {'__pycache__', 'node_modules', 'build', 'deploy', 'dist', 'releases'}
                or part.startswith(('build-', 'deploy-'))
                or part.endswith(('-build', '-artifacts'))):
            return 'generated output directory'
    if p.suffix.lower() == '.md':
        if path == PROVENANCE_DOC or path.startswith(INPUT_DOC_DIRS):
            return None
        return 'nonessential documentation'
    if p.name in {'.gitignore', '.gitattributes', '.gitkeep', 'Makefile', 'LICENSE', 'COPYRIGHT'}:
        return None
    if p.suffix.lower() not in SOURCE_SUFFIXES:
        return 'not source, configuration, license or required text input'
    return None


def git(root, *args, **kwargs):
    return subprocess.check_output(['git', '-C', str(root), *args], **kwargs)


def check(root, revision=None):
    # Resolve once so the checked tree cannot change halfway through the audit.
    tree = git(root, 'rev-parse', '--verify', f'{revision}^{{tree}}').decode().strip() if revision else None
    raw = git(root, 'ls-tree', '-rz', '--name-only', tree) if tree else git(root, 'ls-files', '-z')
    paths = [p.decode('utf-8') for p in raw.split(b'\0') if p]
    errors = [f'{path}: {reason}' for path in paths if (reason := path_error(path))]
    errors.extend(f'{path}: required root file is missing' for path in sorted(ROOT_FILES - set(paths)))
    # Read ignore rules from the same index/tree, including nested rules. Checking
    # a commit must not accidentally use a different checkout's .gitignore.
    with tempfile.TemporaryDirectory(prefix='remote-source-ignore-') as directory:
        sandbox = Path(directory)
        git(sandbox, 'init', '-q')
        for path in paths:
            if PurePosixPath(path).name == '.gitignore':
                target = sandbox / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(git(root, 'show', f'{tree}:{path}' if tree else f':{path}'))
        result = subprocess.run(['git', '-C', directory, 'check-ignore', '--no-index', '-z', '--stdin'],
                                input=raw, capture_output=True)
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr.decode(errors='replace'))
        errors.extend(f'{p.decode()}: tracked despite ignore rule' for p in result.stdout.split(b'\0') if p)
    return paths, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--ref', help='Check this committed tree; default checks the staged index')
    args = parser.parse_args()
    try:
        paths, errors = check(args.root, args.ref)
    except (subprocess.CalledProcessError, RuntimeError, OSError, UnicodeError) as exc:
        print(f'Source audit failed: {exc}')
        return 2
    if errors:
        print('\n'.join(errors))
        print(f'REJECTED: {len(errors)} source policy violations')
        return 1
    print(f'PASS: {len(paths)} files; one root README; source policy satisfied')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
