#!/usr/bin/env python3
"""Classify complete Git changes without network access or implicit writes."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


def path_class(path):
    if not path or path.startswith('/') or '..' in PurePosixPath(path).parts:
        return 'G'
    if path in {'Containerfile', 'Justfile', 'image-template.env', 'build-version.json',
                'installer/build-metadata.py', 'scripts/build-version.py',
                'scripts/build-created.py'} or path.startswith(('build_files/', 'system_files/')):
        return 'A'
    if path in {'.github/workflows/build.yml', 'scripts/classify-container-changes.py',
                'scripts/check-version-tag.py', 'cosign.pub'}:
        return 'B'
    if path == '.github/workflows/build-disk.yml' or path.startswith(('installer/', 'disk_config/')):
        return 'C'
    if path in {'tests/test_build_provenance.py', 'tests/test_container_workflow_policy.py'}:
        return 'D'
    if path in {'README.md', 'AGENTS.md'} or path.startswith(('docs/', '.agents/')):
        return 'E'
    if path.startswith('prototype/hybrid-focus/') or re.fullmatch(r'tests/test_hybrid_focus_[^/]+\.py', path):
        return 'F'
    return 'G'


def parse_diff(raw):
    if not raw or not raw.endswith(b'\0'):
        raise ValueError('Empty or incomplete NUL-separated diff')
    fields = raw[:-1].decode('utf-8', errors='strict').split('\0')
    records = []
    index = 0
    while index < len(fields):
        status = fields[index]
        if not re.fullmatch(r'[AMD]|R(?:100|[0-9]{1,2})', status):
            raise ValueError('Unsupported Git change status')
        count = 2 if status.startswith('R') else 1
        paths = fields[index + 1:index + 1 + count]
        if len(paths) != count or not all(paths):
            raise ValueError('Incomplete Git change record')
        records.append((status, paths))
        index += count + 1
    return records


def git(repo, *args):
    run = subprocess.run(['git', '-C', str(repo), *args], capture_output=True)
    if run.returncode:
        raise ValueError('Required Git operation failed: ' + args[0])
    return run.stdout


def read_lock(repo, revision):
    data = json.loads(git(repo, 'show', f'{revision}:image-lock.json'))
    required = {'schema_version', 'platform', 'resolved_at', 'container_base',
                'installer_base', 'install_payload'}
    if not isinstance(data, dict) or set(data) != required:
        raise ValueError('Unknown or missing lock keys')
    if type(data['schema_version']) is not int or data['schema_version'] != 2:
        raise ValueError('Unsupported lock schema')
    if data['platform'] != 'linux/amd64' or not isinstance(data['resolved_at'], str):
        raise ValueError('Unsupported lock platform or timestamp')
    for key in ('container_base', 'installer_base', 'install_payload'):
        entry = data[key]
        if not isinstance(entry, dict) or set(entry) != {'source', 'image', 'version'}:
            raise ValueError('Unknown or missing lock entry keys')
        if not all(isinstance(value, str) and value for value in entry.values()):
            raise ValueError('Invalid lock entry value')
        if not re.fullmatch(r'ghcr\.io/[a-z0-9_./-]+@sha256:[0-9a-f]{64}', entry['image']):
            raise ValueError('Lock image is not digest-pinned')
    return data


def classify(repo, event, base, head, ref):
    result = dict(event=event, base_sha=base, head_sha=head, ref=ref,
                  classes=[], paths={}, reasons=[], unknown=[], blocking=False,
                  run_tests=False, build_container=False, release_candidate=False,
                  run_iso=False, summary='')
    try:
        if event not in {'push', 'pull_request', 'workflow_dispatch'}:
            raise ValueError('Unsupported event')
        for revision in (base, head):
            if not re.fullmatch(r'[0-9a-f]{40}', revision or ''):
                raise ValueError('Full base/head commit SHA required')
            git(repo, 'cat-file', '-e', revision + '^{commit}')
        # PR callers must supply the actual merge base. Push callers supply event before/after.
        git(repo, 'merge-base', '--is-ancestor', base, head)
        records = parse_diff(git(repo, 'diff', '--no-ext-diff', '--name-status',
                                 '-z', '--find-renames', base, head, '--'))
        for status, paths in records:
            for path in paths:
                if path == 'image-lock.json':
                    if status != 'M':
                        raise ValueError('Lock addition/deletion/rename requires explicit review')
                    before, after = read_lock(repo, base), read_lock(repo, head)
                    classes = set()
                    if before['container_base'] != after['container_base']:
                        classes.add('A')
                    if any(before[key] != after[key] for key in ('installer_base', 'install_payload')):
                        classes.add('C')
                    # Formatting and resolution-time changes still exercise provenance tests.
                    if not classes:
                        classes.add('D')
                else:
                    classes = {path_class(path)}
                for category in sorted(classes):
                    result['paths'].setdefault(category, []).append(path)
                    result['reasons'].append(f'{category}: {status} {path}')
        result['paths'] = {key: sorted(set(value)) for key, value in sorted(result['paths'].items())}
        result['classes'] = list(result['paths'])
        result['unknown'] = result['paths'].get('G', [])
        if result['unknown']:
            raise ValueError('Unknown paths require explicit classification')
        result['run_tests'] = True
        result['build_container'] = bool({'A', 'B'} & set(result['classes'])) or event == 'workflow_dispatch'
        result['release_candidate'] = event == 'push' and ref == 'refs/heads/main' and 'A' in result['classes']
        result['summary'] = 'Release candidate' if result['release_candidate'] else (
            'Validation build only' if result['build_container'] else 'Tests only; container intentionally skipped')
    except (ValueError, OSError, UnicodeError) as error:
        result.update(blocking=True, run_tests=False, build_container=False,
                      release_candidate=False, summary='Blocked: ' + str(error))
        result['reasons'].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--event', required=True)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    result = classify(args.repo, args.event, args.base, args.head, args.ref)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    if args.github_output:
        with args.github_output.open('a') as stream:
            for key in ('blocking', 'run_tests', 'build_container', 'release_candidate', 'run_iso'):
                stream.write(f'{key}={str(result[key]).lower()}\n')
    return 1 if result['blocking'] else 0


if __name__ == '__main__':
    sys.exit(main())
