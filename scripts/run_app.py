"""Supervise the existing local services. No evaluation runs on startup."""
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    children, logs = [], []
    lock = None
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, stop)
    try:
        # A listening socket is an automatically released cross-platform single-instance lock.
        lock = socket.socket()
        try:
            lock.bind(('127.0.0.1', 47931))
        except OSError:
            raise RuntimeError('A startup supervisor is already running (lock port 47931). Use its terminal to stop it.')
        for module in ('httpx', 'fastapi', 'uvicorn'):
            if importlib.util.find_spec(module) is None:
                raise RuntimeError('Python dependencies missing. Run uv sync first.')
        from classifier import core
        import httpx
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        if not npm or not shutil.which('node'):
            raise RuntimeError('Install Node.js and npm, then run npm --prefix web ci.')
        if not (ROOT / 'web/node_modules/vite/bin/vite.js').exists():
            raise RuntimeError('Frontend dependencies missing. Run npm --prefix web ci.')
        settings = core.inference_config()
        try:
            core.load_policy()
        except FileNotFoundError:
            raise RuntimeError('Policy file missing. Copy .env.example to .env or set POLICY_FILE to an existing policy file.') from None
        if os.getenv('MOCK') == '1':
            raise RuntimeError('Unset MOCK or set MOCK=0 for the application startup command.')
        for port in (8000, 5173):
            with socket.socket() as probe:
                try:
                    probe.bind(('127.0.0.1', port))
                except OSError:
                    raise RuntimeError(f'Port {port} is already occupied. Stop the existing service before running make run.')
        directory = ROOT / '.run/logs'
        directory.mkdir(parents=True, exist_ok=True)
        def start(command, name, env=None):
            stream = (directory / f'{name}.log').open('a', encoding='utf-8')
            logs.append(stream)
            options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, **options)
            children.append(child)
            return child
        with httpx.Client(trust_env=False, timeout=2) as client:
            def wait(url, child=None, timeout=45):
                until = time.monotonic() + timeout
                while time.monotonic() < until:
                    if child is not None and child.poll() is not None:
                        raise RuntimeError(f'Service exited before readiness. Inspect {directory}.')
                    try:
                        response = client.get(url)
                        if response.status_code == 200:
                            return response
                    except httpx.HTTPError:
                        pass
                    time.sleep(.2)
                raise RuntimeError(f'Health check timed out: {url}. Inspect {directory}.')
            if settings['provider'] == 'ollama':
                base = settings['url'].removesuffix('/api/chat')
                try:
                    available = client.get(base + '/api/tags')
                    available.raise_for_status()
                except httpx.HTTPError:
                    parsed = urlsplit(base)
                    if parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
                        raise RuntimeError('Configured remote Ollama is unavailable. Start it on its host or check OLLAMA_BASE_URL.')
                    executable = shutil.which('ollama')
                    if not executable:
                        raise RuntimeError('Install Ollama, then run ollama pull ' + settings['model'])
                    env = dict(os.environ, OLLAMA_HOST=parsed.netloc)
                    ollama = start([executable, 'serve'], 'ollama', env)
                    available = wait(base + '/api/tags', ollama)
                models = available.json().get('models', [])
                if not any(settings['model'] in (m.get('name'), m.get('model')) for m in models):
                    raise RuntimeError(f"Model {settings['model']} missing. Run: ollama pull {settings['model']}")
            elif not os.getenv(settings['key_env'], '').strip():
                raise RuntimeError(f"Set {settings['key_env']} in .env for {settings['provider']}.")
            backend = start([sys.executable, '-m', 'uvicorn', 'server:app', '--host', '127.0.0.1', '--port', '8000'], 'backend')
            wait('http://127.0.0.1:8000/api/runtime', backend)
            # Launch Vite directly from the installed npm dependency; no shell wrapper to orphan children.
            frontend = start([shutil.which('node'), str(ROOT / 'web/node_modules/vite/bin/vite.js'), str(ROOT / 'web'),
                              '--host', '127.0.0.1', '--port', '5173', '--strictPort'], 'frontend')
            wait('http://127.0.0.1:5173', frontend)
            wait('http://127.0.0.1:5173/api/runtime', frontend)
            print(f'Ready: http://127.0.0.1:5173\nAPI: http://127.0.0.1:8000/docs\nLogs: {directory}\nCtrl+C to stop.', flush=True)
            while True:
                if any(child.poll() is not None for child in children):
                    raise RuntimeError(f'A service exited. Inspect {directory}.')
                time.sleep(.3)
    except KeyboardInterrupt:
        print('Stopping services...', flush=True)
        return 0
    except (RuntimeError, OSError, ValueError) as exc:
        print(f'Startup failed: {exc}', file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, signal.SIG_IGN)
        for child in reversed(children):
            if child.poll() is None:
                try:
                    if os.name == 'nt':
                        child.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for child in reversed(children):
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for stream in logs:
            stream.close()
        if lock:
            lock.close()


if __name__ == '__main__':
    sys.exit(main())
