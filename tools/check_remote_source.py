#!/usr/bin/env python3
"""Check the staged index or a Git revision; never modify files or push."""
import argparse
import os
from pathlib import Path, PurePosixPath
import re
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
PRIVATE_NOTICE_FILES = {
    'runtime/source/anm2_load_override_hook.cpp',
    'runtime/source/image_pcx_bridge_hook.cpp',
    'runtime/source/mod_resource_redirect.cpp',
    'runtime/source/mod_image_resources.cpp',
    'runtime/source/program/image_pcx_bridge_hook.cpp',
    'runtime/source/program/mod_resource_redirect.cpp',
    'runtime/source/program/mod_image_resources.cpp',
    'runtime/source/hook_manager.cpp',
    'runtime/source/mod_menu_native.cpp',
    'runtime/source/program/hook_manager.cpp',
    'runtime/source/program/mod_menu_native.cpp',
    'runtime/source/notice_integrity_native.cpp',
    'runtime/source/title_notice_native.cpp',
    'runtime/source/program/notice_integrity_native.cpp',
    'runtime/source/program/title_notice_native.cpp',
    'runtime/tests/test_notice_guard_module.py',
    'runtime/tests/test_notice_graphics_owned_relay.py',
    'runtime/tests/test_notice_control_flow.py',
    'runtime/tests/test_lua_font_resources.py',
    'tools/stage150_sprite_abi_audit.py',
    'runtime/tests/contract/test_save_file_channel.py',
    'runtime/tests/integration/test_hook_callback_pipeline.py',
    'runtime/tests/integration/test_mod_load_service.py',
    'runtime/tests/test_achievement_resume_flow.py',
    'runtime/tests/test_achievement_run_latch.py',
    'runtime/tests/test_batch411_path_separators.py',
    'runtime/tests/test_binding_declared_types.py',
    'runtime/tests/test_binding_guard_ordering.py',
    'runtime/tests/test_collision_relay_behavior.py',
    'runtime/tests/test_console_achievement_policy.py',
    'runtime/tests/test_console_controls.py',
    'runtime/tests/test_default_callback_readiness.py',
    'runtime/tests/test_default_manifest_loader.py',
    'runtime/tests/test_default_manifest_sync_reload.py',
    'runtime/tests/test_diagnostic_build_invariants.py',
    'runtime/tests/test_embedded_lua_runtime.py',
    'runtime/tests/test_embedded_mod_menu_removed.py',
    'runtime/tests/test_engine_array_owner.py',
    'runtime/tests/test_engine_call_access.py',
    'runtime/tests/test_entity_spawn_relay.py',
    'runtime/tests/test_entry_relay_adapter.py',
    'runtime/tests/test_game_ispaused_native_stage36.py',
    'runtime/tests/test_game_observer_stage26.py',
    'runtime/tests/test_game_owner_observer_stage35.py',
    'runtime/tests/test_got_slot_adapter.py',
    'runtime/tests/test_hook_port_coverage.py',
    'runtime/tests/test_hook_skip_switches.py',
    'runtime/tests/test_hud_achievement_status.py',
    'runtime/tests/test_hud_render_got_hook.py',
    'runtime/tests/test_image_bridge_buffer.py',
    'runtime/tests/test_image_pcx_cache_budget_floor.py',
    'runtime/tests/test_image_pcx_path_identity.py',
    'runtime/tests/test_input_entity_context.py',
    'runtime/tests/test_instruction_guard.py',
    'runtime/tests/test_lua_batch401_mod_player_names.py',
    'runtime/tests/test_lua_batch405_evaluate_cache_timing.py',
    'runtime/tests/test_lua_callback_dispatch_sites.py',
    'runtime/tests/test_lua_game_ispaused_stage37.py',
    'runtime/tests/test_lua_itempool_getcollectible.py',
    'runtime/tests/test_lua_neutral_keyboard_input.py',
    'runtime/tests/test_manager_loadconfigs_stage8.py',
    'runtime/tests/test_manager_render_hook.py',
    'runtime/tests/test_manifest_readiness.py',
    'runtime/tests/test_minimap_enabled_resources.py',
    'runtime/tests/test_minimap_touch_gate.py',
    'runtime/tests/test_mod_capacity_256.py',
    'runtime/tests/test_mod_content_active_scope.py',
    'runtime/tests/test_mod_image_full_path_identity.py',
    'runtime/tests/test_mod_menu_entry_row.py',
    'runtime/tests/test_mod_reload_graphics_reclaim.py',
    'runtime/tests/test_mod_resource_hash_collision.py',
    'runtime/tests/test_modmanager_reset_stage9.py',
    'runtime/tests/test_module_identity.py',
    'runtime/tests/test_native_resource_reload.py',
    'runtime/tests/test_no_static_guard_init.py',
    'runtime/tests/test_notice_integrity_namespace.py',
    'runtime/tests/test_npc_ai_got_hook.py',
    'runtime/tests/test_png_to_pcx_alloc_safety.py',
    'runtime/tests/test_pre_get_collectible_relay_runtime.py',
    'runtime/tests/test_present_relay_registers.py',
    'runtime/tests/test_render_layer_coordinator.py',
    'runtime/tests/test_render_scene_scope.py',
    'runtime/tests/test_run_taint_persistence.py',
    'runtime/tests/test_runtime_constants.py',
    'runtime/tests/test_runtime_constants_against_nro.py',
    'runtime/tests/test_runtime_state.py',
    'runtime/tests/test_shared_item_image_objects.py',
    'runtime/tests/test_stage102_change_room_diagnostic.py',
    'runtime/tests/test_stage104_room_key_stability_diagnostic.py',
    'runtime/tests/test_stage108_lifecycle_reentry_diagnostic.py',
    'runtime/tests/test_stage109_restart_postcall_diagnostic.py',
    'runtime/tests/test_stage110_managed_state_reset_diagnostic.py',
    'runtime/tests/test_stage112_descriptor_reentry_diagnostic.py',
    'runtime/tests/test_stage118_managed_file_write_diagnostic.py',
    'runtime/tests/test_stage127_save_load_diagnostic.py',
    'runtime/tests/test_stage128_save_data_manager_diagnostic.py',
    'runtime/tests/test_stage15_render_pause_diagnostic.py',
    'runtime/tests/test_stage16_music_pause_diagnostic.py',
    'runtime/tests/test_stage17_long_music_pause_diagnostic.py',
    'runtime/tests/test_stage45_music_id_diagnostic.py',
    'runtime/tests/test_stage48_music_replay_diagnostic.py',
    'runtime/tests/test_stage88_instant_restart_observation_diagnostic.py',
    'runtime/tests/test_stage89_restart_action_controller_diagnostic.py',
    'runtime/tests/test_startup_gate_probe.py',
    'runtime/tests/test_startup_mod_image_resources.py',
    'runtime/tests/test_test_run_observer.py',
    'runtime/tests/test_use_item_animation_events.py',
    'runtime/tests/test_use_item_result_consumer.py',
    'runtime/tests/unit/test_file_api_seam.py',
    'runtime/tests/unit/test_self_journal.py',
    'tests/test_mod_menu_resource_handle.py',
}
# Exact production UI inputs; this does not permit general media directories.
NOTICE_SUPPORT_INPUTS = {'tools/title_notice_support/' + name + '.png'
                         for name in ('wechat', 'alipay', 'kofi')}


def path_error(path):
    p = PurePosixPath(path)
    if p.is_absolute() or '..' in p.parts:
        return 'unsafe path'
    if path in ROOT_FILES:
        return None
    if path in NOTICE_SUPPORT_INPUTS:
        return None
    if path in PRIVATE_NOTICE_FILES or path.startswith('runtime/source/notice_guard/'):
        return 'private notice implementation; publish only its interface and binary dependency'
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


def private_address_values(root):
    """Use local private inputs, including the primary checkout from a worktree.

    These inputs are never copied into the audited index or committed tree.
    A standalone public clone has no private values to disclose.
    """
    common = Path(git(root, 'rev-parse', '--git-common-dir').decode().strip())
    if not common.is_absolute():
        common = Path(root) / common
    candidates = [Path(root), Path(root).parent / 'private', common.resolve().parent]
    explicit = os.environ.get('NOTICE_PRIVATE_SOURCE_ROOT')
    if explicit:
        candidates.insert(0, Path(explicit))
    values = set()
    for candidate in candidates:
        path = candidate / 'runtime/source/notice_guard/private_engine_addresses.hpp'
        if path.is_file():
            values.update(int(value, 16) for value in re.findall(
                r'\bconstexpr\s+(?:std::)?uintptr_t\s+\w+\s*=\s*(0x[0-9a-fA-F]+)', path.read_text()))
    return values


def private_content_errors(root, paths, tree):
    values = private_address_values(root)
    if not values:
        return []
    public = [path for path in paths if path_error(path) is None and
              (path in ROOT_FILES or PurePosixPath(path).suffix.lower() in SOURCE_SUFFIXES | {'.md'})]
    queries = ''.join(f'{tree}:{path}\n' if tree else f':{path}\n' for path in public)
    # One Git process reads exact staged/committed blobs, rather than thousands
    # of subprocesses or mutable working-copy files.
    raw = subprocess.check_output(['git', '-C', str(root), 'cat-file', '--batch'], input=queries.encode())
    cursor, errors = 0, []
    for path in public:
        end = raw.index(b'\n', cursor)
        header = raw[cursor:end].split()
        if len(header) != 3 or header[1] != b'blob':
            raise RuntimeError(f'cannot inspect source blob: {path}')
        size = int(header[2])
        body = raw[end + 1:end + 1 + size].decode('utf-8', errors='replace')
        cursor = end + 1 + size + 1
        literals = {int(token, 16) for token in re.findall(r'0[xX][0-9a-fA-F]+', body)}
        literals.update(int(token) for token in re.findall(
            r'(?<![\w.])([0-9]+)(?:[uUlL]+)?(?![\w.])', body))
        if literals & values:
            errors.append(f'{path}: private engine address literal exposed')
    return errors


def check(root, revision=None):
    # Resolve once so the checked tree cannot change halfway through the audit.
    tree = git(root, 'rev-parse', '--verify', f'{revision}^{{tree}}').decode().strip() if revision else None
    raw = git(root, 'ls-tree', '-rz', '--name-only', tree) if tree else git(root, 'ls-files', '-z')
    paths = [p.decode('utf-8') for p in raw.split(b'\0') if p]
    errors = [f'{path}: {reason}' for path in paths if (reason := path_error(path))]
    errors.extend(private_content_errors(root, paths, tree))
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
