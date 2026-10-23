"""Local HTTP deployment benchmark + restart/restore proof; never uploads off-device."""
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from uuid import uuid4

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.team_check import V2
from tools.backup_webapp import backup_database


def main():
    video = Path(sys.argv[1]).resolve()
    run = ROOT / 'runtime' / 'benchmarks' / uuid4().hex[:10]
    run.mkdir(parents=True)
    data = run / 'data'
    password = secrets.token_urlsafe(32)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = 'https://bench.example'
    headers = {'Host': 'bench.example', 'Authorization': 'Basic ' + base64.b64encode(('team:' + password).encode()).decode()}
    env = dict(os.environ, PUBLIC_ORIGIN=origin, TEAM_PASSWORD=password, DATA_DIR=str(data),
               PORT=str(port), BIND_HOST='127.0.0.1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
    process = None
    metrics = []
    stop = threading.Event()
    def request(path, body=None, content_type='application/json'):
        req = urllib.request.Request(f'http://127.0.0.1:{port}' + path, data=body,
                                     headers=dict(headers, **{'Content-Type': content_type}))
        with urllib.request.urlopen(req, timeout=210) as response:
            return response.read()
    def start(directory):
        nonlocal process
        env['DATA_DIR'] = str(directory)
        process = subprocess.Popen([sys.executable, 'deploy_server.py'], cwd=ROOT, env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(200):
            if process.poll() is not None:
                raise RuntimeError('Deployment server failed to start')
            try:
                if request('/healthz') == b'ok': return
            except OSError: time.sleep(.05)
        raise RuntimeError('Start timeout')
    def shutdown():
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=20)
    def sample_memory():
        while not stop.wait(.02):
            try:
                p = psutil.Process(process.pid)
                metrics.append((time.monotonic(), p.memory_info().rss))
            except (psutil.NoSuchProcess, ProcessLookupError): pass
    report = {'platform': platform.platform(), 'machine': platform.machine(),
              'python': platform.python_version(), 'source_bytes': video.stat().st_size,
              'scope': 'local Waitress server RSS sampled every 20ms; CPU; HTTP upload-to-result; no cloud or TLS latency',
              'runs': []}
    try:
        start(data)
        threading.Thread(target=sample_memory, daemon=True).start()
        report['startup_rss_mib'] = psutil.Process(process.pid).memory_info().rss / 2**20
        state = json.loads(request('/sessions', json.dumps({'question_schema_version': V2}).encode()))
        while state['status'] != 'completed':
            q = state['current_question']
            option = next(o for o in q['options'] if o['collection_status'] == 'verified')
            state = json.loads(request('/sessions/' + state['session_id'] + '/answers', json.dumps({
                'question_id': q['question_id'], 'selected_option_ids': [option['option_id']],
                'expected_revision': state['revision']}).encode()))
        # A synthetic worst-path input, not an accuracy test or representative scene.
        import cv2
        import numpy as np
        cap = cv2.VideoCapture(str(video))
        report['source_video'] = {key: cap.get(prop) for key, prop in [('fps', cv2.CAP_PROP_FPS), ('frames', cv2.CAP_PROP_FRAME_COUNT), ('width', cv2.CAP_PROP_FRAME_WIDTH), ('height', cv2.CAP_PROP_FRAME_HEIGHT)]}
        cap.release()
        blank = run / 'blank120.mp4'
        writer = cv2.VideoWriter(str(blank), cv2.VideoWriter_fourcc(*'mp4v'), 10, (1280, 720))
        for _ in range(1200): writer.write(np.zeros((720, 1280, 3), np.uint8))
        writer.release()
        blank4k = run / 'blank4k1s.mp4'
        writer = cv2.VideoWriter(str(blank4k), cv2.VideoWriter_fourcc(*'mp4v'), 10, (3840, 2160))
        for _ in range(10): writer.write(np.zeros((2160, 3840, 3), np.uint8))
        writer.release()
        first_job = None
        for label, source in [('real_cold', video), ('real_repeat_1', video), ('real_repeat_2', video), ('blank_120s_720p', blank), ('blank_1s_4k', blank4k)]:
            cpu_before = psutil.Process(process.pid).cpu_times()
            t = time.monotonic()
            payload = source.read_bytes()
            job = json.loads(request(f'/video-jobs?session_id={state["session_id"]}&revision={state["revision"]}&filename={source.name}', payload, 'application/octet-stream'))
            deadline = time.monotonic() + 210
            while job['status'] in ('uploading', 'queued', 'processing'):
                if time.monotonic() > deadline: raise RuntimeError('Job timed out')
                time.sleep(.1)
                job = json.loads(request('/video-jobs/' + job['job_id']))
            elapsed = time.monotonic() - t
            cpu_after = psutil.Process(process.pid).cpu_times()
            report['runs'].append({'case': label, 'seconds': round(elapsed, 3), 'cpu_seconds': round(cpu_after.user+cpu_after.system-cpu_before.user-cpu_before.system, 3),
                'peak_rss_mib': round(max((m for ts,m in metrics if ts >= t), default=0) / 2**20, 2),
                'end_rss_mib': round(psutil.Process(process.pid).memory_info().rss / 2**20, 2),
                'status': job['status'], 'vehicles': len(job.get('detections', []))})
            expected = 'no_detection' if label.startswith('blank') else 'completed'
            assert job['status'] == expected, job
            if first_job is None: first_job = job
        time.sleep(2)
        report['post_work_idle_rss_mib'] = round(psutil.Process(process.pid).memory_info().rss / 2**20, 2)
        image_path = '/video-jobs/' + first_job['job_id'] + '/original.jpg'
        image_hash = hashlib.sha256(request(image_path)).hexdigest()
        def hashes(folder):
            return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in folder.rglob('*') if p.is_file()}
        expected_files = hashes(data / 'videos')
        shutdown()
        backup = run / 'backup'
        shutil.copytree(data, backup)
        report['sqlite_backup_counts'] = backup_database(data / 'sessions.sqlite3', run / 'db-only.sqlite3')
        start(data)
        assert json.loads(request('/sessions/' + state['session_id'])) == state
        assert hashlib.sha256(request(image_path)).hexdigest() == image_hash
        assert hashes(data / 'videos') == expected_files
        report['restart_preserved'] = True
        shutdown()
        # Restore to a different empty location; original storage is never overwritten.
        restored = run / 'restored'
        shutil.copytree(backup, restored)
        start(restored)
        assert json.loads(request('/sessions/' + state['session_id'])) == state
        assert hashlib.sha256(request(image_path)).hexdigest() == image_hash
        assert hashes(restored / 'videos') == expected_files
        report['restore_preserved'] = True
        report['verified_video_files'] = len(expected_files)
        report['storage_bytes'] = sum(p.stat().st_size for p in data.rglob('*') if p.is_file())
    finally:
        stop.set()
        shutdown()
    path = run / 'report.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'report': str(path), **report}, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
