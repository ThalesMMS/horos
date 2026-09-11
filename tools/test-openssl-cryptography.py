#!/usr/bin/env python3
"""Run pinned pyca/Wycheproof tests against the OpenSSL archives built by Horos.

Needs macOS, Python 3.11+, uv, Cargo and an existing Debug/Release Horos build.
All downloaded sources, environments and results stay in local-validation by
default. No Apple application, patient data or keychain is used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PINS = json.loads(Path(__file__).with_name('openssl-cryptography-test.json').read_text())


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def output(*args, **kwargs):
    return subprocess.check_output(list(map(str, args)), text=True, **kwargs).strip()


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def checkout(directory, pin):
    if not directory.exists():
        run('git', 'init', directory)
        run('git', '-C', directory, 'remote', 'add', 'origin', pin['url'])
        run('git', '-C', directory, 'fetch', '--depth', '1', 'origin', pin['revision'])
        run('git', '-C', directory, 'checkout', '--detach', 'FETCH_HEAD')
    if (Path(output('git', '-C', directory, 'rev-parse', '--show-toplevel')).resolve() != directory or
        output('git', '-C', directory, 'rev-parse', 'HEAD') != pin['revision'] or
        output('git', '-C', directory, 'status', '--porcelain', '--untracked-files=normal')):
        raise SystemExit(f'Expected a clean pinned checkout at {directory}; local files were preserved.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration', choices=['Debug', 'Release'], default='Debug')
    parser.add_argument('--work-root', type=Path, default=ROOT/'local-validation/openssl-cryptography')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('tests', nargs='*', default=['tests'], help='upstream test paths; defaults to the full suite')
    args = parser.parse_args()
    if sys.platform != 'darwin' or args.jobs < 1:
        parser.error('requires macOS and a positive job count')
    for tool in ('uv', 'cargo'):
        if not shutil.which(tool):
            raise SystemExit(f'Install {tool} before running this external test.')

    install = ROOT/'build/Build/Intermediates.noindex/Horos.build'/args.configuration/'OpenSSL.build/Install'
    artifacts = [install/'lib/libssl.a', install/'lib/libcrypto.a', install/'include/openssl/opensslv.h']
    for path in [*artifacts, install/'bin/openssl']:
        if not path.is_file():
            raise SystemExit(f'Build {args.configuration} first; missing {path}')
    fields = dict(line.split('=', 1) for line in (ROOT/'OpenSSL/upstream/VERSION.dat').read_text().splitlines() if '=' in line)
    expected = '.'.join(fields[k] for k in ('MAJOR', 'MINOR', 'PATCH'))
    library_version = output(install/'bin/openssl', 'version').split(' (Library:', 1)[0]
    if not library_version.startswith(f'OpenSSL {expected} '):
        raise SystemExit(f'Stale {args.configuration} installation: {library_version}, expected {expected}')
    hashes = {str(p.relative_to(install)): digest(p) for p in artifacts}
    identity = {'configuration': args.configuration, 'artifacts': hashes, 'pins': PINS}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    work = args.work_root.resolve()
    work.mkdir(parents=True, exist_ok=True)
    source, vectors = work/'cryptography', work/'wycheproof'
    checkout(source, PINS['cryptography'])
    checkout(vectors, PINS['wycheproof'])
    project = tomllib.loads((source/'pyproject.toml').read_text())
    packages = {p['name']: p['version'] for p in tomllib.loads((source/'Cargo.lock').read_text())['package']}
    if (project['project']['version'] != PINS['cryptography']['version'] or
        not project['tool']['maturin']['locked'] or packages['pyo3'] != '0.29.0' or 'ouroboros' in packages):
        raise SystemExit('The pinned pyca dependency contract changed; review its manifests before execution.')
    for test in args.tests:
        if not (source/test).resolve().is_relative_to(source/'tests') or not (source/test).exists():
            parser.error(f'Test path must exist inside the pinned upstream tests/: {test}')
    state = work/(args.configuration.lower()+'-'+key)
    state.mkdir(exist_ok=True)
    python = state/'venv/bin/python'
    if not python.exists():
        run('uv', 'venv', '--python', sys.executable, state/'venv')
    env = {**os.environ, 'OPENSSL_DIR': str(install), 'OPENSSL_LIB_DIR': str(install/'lib'),
           'OPENSSL_INCLUDE_DIR': str(install/'include'), 'OPENSSL_STATIC': '1', 'OPENSSL_NO_VENDOR': '1',
           'CARGO_TARGET_DIR': str(state/'cargo'), 'PYO3_PYTHON': str(python), 'PYTHONNOUSERSITE': '1'}
    env.pop('PYTHONPATH', None)
    print(f'Building pyca {PINS["cryptography"]["version"]} against {library_version} ({args.configuration})', flush=True)
    # The signed upstream release pins build tools with hashes and test
    # dependencies with constraints. Cargo.lock is enforced by maturin.
    run('uv', 'pip', 'install', '--python', python, '--require-hashes', '-r',
        source/'.github/requirements/build-requirements.txt', env=env)
    run('uv', 'pip', 'install', '--python', python, '--no-build-isolation', '--no-deps',
        '--no-cache', '--reinstall', source, env=env)
    run('uv', 'pip', 'install', '--python', python, '--no-build-isolation',
        '--constraint', source/'ci-constraints-requirements.txt', '--group',
        str(source/'pyproject.toml')+':test', source/'vectors', env=env)
    probe = '''import json,cryptography
from cryptography.hazmat.backends.openssl.backend import backend
from cryptography.hazmat.bindings import _rust
print(json.dumps(dict(cryptography=cryptography.__version__,openssl=backend.openssl_version_text(),binding=_rust.__file__)))'''
    linked = json.loads(output(python, '-c', probe, env=env, cwd=state))
    if linked['openssl'] != library_version or linked['cryptography'] != PINS['cryptography']['version']:
        raise SystemExit(f'Test package is linked to the wrong OpenSSL: {linked}')
    binding = Path(linked['binding']).resolve()
    if not binding.is_relative_to(state/'venv') or re.search(r'lib(?:ssl|crypto)\.', output('otool', '-L', binding)):
        raise SystemExit('Expected a static OpenSSL binding inside this test environment.')
    identity.update({'linked': linked, 'bindingSHA256': digest(binding), 'cargoLockSHA256': digest(source/'Cargo.lock'),
        'python': output(python, '--version'), 'cargo': output('cargo', '--version'), 'uv': output('uv', '--version'),
        'platform': platform.platform(), 'tests': args.tests, 'jobs': args.jobs})
    (state/'build-manifest.json').write_text(json.dumps(identity, indent=2)+'\n')
    print('Verified compiled binding:', json.dumps(linked), flush=True)
    # This is the upstream pytest suite, including its Wycheproof vectors;
    # the ordinary OpenSSL recipe skips a no-shared build and cannot do this.
    run(python, '-m', 'pytest', '-q', '-n', args.jobs, '--dist=worksteal', '--durations=10',
        '--wycheproof-root='+str(vectors), '--junitxml='+str(state/'results.xml'),
        *args.tests, env=env, cwd=source)
    print('PASS: external cryptography suite; manifest and JUnit:', state, flush=True)


if __name__ == '__main__':
    main()
