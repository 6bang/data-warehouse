#!/usr/bin/env python3
"""Cross-platform local launcher. Never deploys or connects integrations itself."""
import argparse
import base64
import errno
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def init_env():
    destination = ROOT / '.env'
    if destination.exists():
        print('Existing .env preserved; no credentials were changed.')
        return
    values = {
        'DJANGO_SECRET_KEY': secrets.token_urlsafe(48),
        'INTEGRATION_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        'ADMIN_PASSWORD': secrets.token_urlsafe(24),
        'MYSQL_PASSWORD': secrets.token_urlsafe(24),
        'MYSQL_ROOT_PASSWORD': secrets.token_urlsafe(24),
    }
    lines = []
    for line in (ROOT / '.env.example').read_text(encoding='utf-8').splitlines():
        key = line.partition('=')[0]
        lines.append(f'{key}={values[key]}' if key in values else line)
    # Exclusive creation: never truncate a user's existing credentials.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        stream.write('\n'.join(lines) + '\n')
    print('Created private .env with unique credentials. Read ADMIN_PASSWORD locally; never commit or share it.')


def check_port(port):
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', port))
        except OSError as error:
            if error.errno == errno.EADDRINUSE:
                raise RuntimeError(f'Port {port} is occupied; stop the other app or choose another port.') from error
            raise RuntimeError(f'Cannot bind local port {port}; check local execution permissions.') from error


def run(command, cwd=ROOT, env=None):
    subprocess.run(command, cwd=cwd, env=env, check=True)


def stop(child):
    if child.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True)
    else:
        os.killpg(child.pid, signal.SIGTERM)
    try:
        child.wait(timeout=8)
    except subprocess.TimeoutExpired:
        if os.name != 'nt':
            os.killpg(child.pid, signal.SIGKILL)
        else:
            child.kill()
        child.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['demo', 'full', 'init'], nargs='?', default='demo')
    parser.add_argument('--frontend-port', type=int, default=5173)
    parser.add_argument('--backend-port', type=int, default=8000)
    parser.add_argument('--no-install', action='store_true', help='Use already installed dependencies only')
    args = parser.parse_args()
    if args.mode == 'init':
        init_env()
        return 0
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    node = shutil.which('node')
    if not npm or not node:
        raise RuntimeError('Install Node.js 22+ (including npm) first.')
    major = int(subprocess.check_output([node, '-p', 'process.versions.node.split(".")[0]'], text=True).strip())
    if major < 22:
        raise RuntimeError('Node.js 22+ required.')
    for port in [args.frontend_port] + ([args.backend_port] if args.mode == 'full' else []):
        if not 1024 <= port <= 65535:
            raise RuntimeError('Use a port between 1024 and 65535.')
        check_port(port)
    if args.mode == 'full' and args.backend_port == args.frontend_port:
        raise RuntimeError('Frontend and backend ports must differ.')
    if not args.no_install:
        run([npm, 'ci'], ROOT / 'frontend')
    elif not (ROOT / 'frontend/node_modules').is_dir():
        raise RuntimeError('Frontend dependencies missing. Run again without --no-install.')
    env = os.environ.copy()
    bypass = env.get('NO_PROXY', env.get('no_proxy', ''))
    env['NO_PROXY'] = ','.join(filter(None, [bypass, 'localhost', '127.0.0.1', '::1']))
    env['no_proxy'] = env['NO_PROXY']
    env['DEV_API_TARGET'] = f'http://127.0.0.1:{args.backend_port}'
    # Keep both servers on loopback. No implicit public bind or deployment.
    env['CORS_ALLOWED_ORIGINS'] = f'http://localhost:{args.frontend_port},http://127.0.0.1:{args.frontend_port}'
    commands = []
    if args.mode == 'full':
        if sys.version_info < (3, 11):
            raise RuntimeError('Use Python 3.11+ for the full backend.')
        init_env()
        python = ROOT / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
        if not python.exists():
            if args.no_install:
                raise RuntimeError('Backend virtual environment missing. Run without --no-install.')
            run([sys.executable, '-m', 'venv', str(ROOT / '.venv')])
        if not args.no_install:
            run([str(python), '-m', 'pip', 'install', '-r', 'requirements.txt'], ROOT / 'backend')
        run([str(python), 'manage.py', 'migrate', '--noinput'], ROOT / 'backend', env)
        run([str(python), 'manage.py', 'bootstrap_admin'], ROOT / 'backend', env)
        commands.append(([str(python), 'manage.py', 'runserver', f'127.0.0.1:{args.backend_port}', '--noreload'], ROOT / 'backend'))
    commands.append(([npm, 'run', 'dev', '--', '--host', '127.0.0.1', '--port', str(args.frontend_port), '--strictPort'], ROOT / 'frontend'))
    children = []
    try:
        for command, cwd in commands:
            children.append(subprocess.Popen(command, cwd=cwd, env=env, start_new_session=os.name != 'nt'))
        print(f'Local demo: http://127.0.0.1:{args.frontend_port}/demo', flush=True)
        if args.mode == 'full':
            print(f'Local login: http://127.0.0.1:{args.frontend_port}/login (credentials in private .env)', flush=True)
        print('Press Ctrl+C to stop. Integration access requires your own explicit configuration.', flush=True)
        while all(child.poll() is None for child in children):
            try:
                children[0].wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        return next((child.returncode for child in children if child.returncode is not None), 0)
    except KeyboardInterrupt:
        return 0
    finally:
        for child in reversed(children):
            stop(child)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f'Local startup failed: {error}', file=sys.stderr)
        sys.exit(1)
