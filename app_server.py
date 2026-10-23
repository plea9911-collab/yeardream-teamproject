"""Local frontend + video extension. Existing session API and pinned data stay intact."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
import json
import logging
from pathlib import Path
import re
import threading
from urllib.parse import parse_qs
from uuid import uuid4
from wsgiref.simple_server import make_server
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer

from main import create_app, QuietHandler
from sqlite_repository import SQLiteRepository
from tools.team_check import ROOT, REGISTRY, V2, service
from video_analysis import analyze_video, VideoError

MAX_UPLOAD = 200 * 1024 * 1024
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/style.css': ('style.css', 'text/css; charset=utf-8')}


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class LocalHandler(QuietHandler):
    timeout = 30


class VideoJobs:
    def __init__(self, root, model, analyzer=analyze_video):
        self.root, self.model, self.analyzer = Path(root), Path(model), analyzer
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(2)
        self.pool = ThreadPoolExecutor(max_workers=1)
        # Inference cannot survive process restart; leave a retriable state on disk.
        for file in self.root.glob('*/job.json'):
            data = json.loads(file.read_text())
            if data['status'] in ('queued', 'processing', 'uploading'):
                data.update(status='failed', message='서버가 재시작됐습니다. 영상을 다시 첨부해 주세요.')
                self.save(data)

    def save(self, data):
        with self.lock:
            path = self.root / data['job_id'] / 'job.json'
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            temp.replace(path)

    def get(self, job_id):
        if not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise FileNotFoundError()
        with self.lock:
            return json.loads((self.root / job_id / 'job.json').read_text(encoding='utf-8'))

    def run(self, data, source):
        try:
            data.update(status='processing', message='차량을 찾고 있습니다.')
            self.save(data)
            def progress(value):
                data['progress'] = value
                self.save(data)
            data.update(self.analyzer(source, source.parent, self.model, progress))
        except VideoError as exc:
            data.update(status='failed', message=str(exc))
        except Exception:
            logging.exception('Video job failed: %s', data['job_id'])
            data.update(status='failed', message='영상 분석에 실패했습니다. 모델·설치 환경과 영상 형식을 확인해 주세요.')
        finally:
            try:
                self.save(data)
            finally:
                self.slots.release()


def create_web_app(database, jobs):
    backend = create_app(ROOT, database, registry=REGISTRY)
    sessions = service(database)

    def app(env, start):
        path, method = env.get('PATH_INFO', ''), env['REQUEST_METHOD']
        def respond(code, data, mime='application/json; charset=utf-8', extra=()):
            raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            start(f'{code} {HTTPStatus(code).phrase}', [('Content-Type', mime),
                  ('Content-Length', str(len(raw))), ('Cache-Control', 'no-store'),
                  ('X-Content-Type-Options', 'nosniff'), *extra])
            return [raw]
        def error(code, message):
            return respond(code, {'error': {'message': message}})
        host = env.get('HTTP_HOST', '').split(':')[0]
        if host not in ('127.0.0.1', 'localhost'):
            return error(403, '로컬 주소에서만 사용할 수 있습니다.')
        # No cross-origin mutations for a local application without authentication.
        if method not in ('GET', 'HEAD'):
            origin = env.get('HTTP_ORIGIN')
            if origin and origin != 'http://' + env.get('HTTP_HOST', ''):
                return error(403, '다른 사이트에서의 요청은 허용되지 않습니다.')
        if path in STATIC:
            if method != 'GET':
                return error(405, 'GET 요청만 가능합니다.')
            name, mime = STATIC[path]
            return respond(200, (ROOT / 'web' / name).read_bytes(), mime,
                           [('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; media-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")])
        if path == '/app-config' and method == 'GET':
            return respond(200, {'question_schema_version': V2, 'max_upload_bytes': MAX_UPLOAD,
                                 'model_ready': jobs.model.is_file()})
        if path == '/video-jobs':
            if method != 'POST':
                return error(405, 'POST 요청만 가능합니다.')
            if env.get('CONTENT_TYPE', '').split(';')[0] != 'application/octet-stream':
                return error(415, '영상 파일을 바이너리 형식으로 전송해 주세요.')
            query = parse_qs(env.get('QUERY_STRING', ''))
            try:
                sid = query['session_id'][0]
                revision = int(query['revision'][0])
                suffix = Path(query['filename'][0]).suffix.lower()
                length = int(env.get('CONTENT_LENGTH', '0'))
            except (KeyError, ValueError):
                return error(422, '업로드 정보가 올바르지 않습니다.')
            if length <= 0 or length > MAX_UPLOAD:
                return error(413, '영상은 0바이트 초과, 200MB 이하여야 합니다.')
            if suffix not in ('.mp4', '.mov', '.avi', '.mkv', '.webm'):
                return error(415, 'MP4, MOV, AVI, MKV, WebM 영상을 선택해 주세요.')
            try:
                state = sessions.get_session(sid)
            except Exception:
                return error(404, '대화를 찾지 못했습니다.')
            if state['status'] != 'completed' or state['revision'] != revision:
                return error(409, '질문을 모두 마친 최신 대화에서 영상을 첨부해 주세요.')
            if not jobs.model.is_file():
                return error(503, 'YOLO 모델이 준비되지 않았습니다. 실행 안내를 확인해 주세요.')
            if not jobs.slots.acquire(blocking=False):
                return error(429, '처리 중인 영상이 많습니다. 잠시 후 다시 시도해 주세요.')
            job_id = uuid4().hex
            folder = jobs.root / job_id
            source = folder / ('input' + suffix)
            data = dict(job_id=job_id, session_id=sid, revision=revision,
                        status='uploading', progress=0, message='영상 수신 중')
            try:
                folder.mkdir()
                jobs.save(data)
                with source.open('wb') as file:
                    remaining = length
                    while remaining:
                        chunk = env['wsgi.input'].read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError('truncated upload')
                        file.write(chunk)
                        remaining -= len(chunk)
                data.update(status='queued', message='분석 순서를 기다리고 있습니다.')
                jobs.save(data)
                jobs.pool.submit(jobs.run, data.copy(), source)
            except Exception:
                source.unlink(missing_ok=True)
                data.update(status='failed', message='영상 전송이 중단됐습니다. 다시 시도해 주세요.')
                try:
                    if folder.exists():
                        jobs.save(data)
                finally:
                    jobs.slots.release()
                return error(422, data['message'])
            return respond(202, data)
        match = re.fullmatch(r'/video-jobs/([a-f0-9]{32})(?:/(original.jpg|detected.jpg))?', path)
        if match:
            if method != 'GET':
                return error(405, 'GET 요청만 가능합니다.')
            try:
                data = jobs.get(match[1])
                state = sessions.get_session(data['session_id'])
                if state['revision'] != data['revision'] or state['status'] != 'completed':
                    return error(409, '답변이 수정되어 이전 영상 결과를 사용할 수 없습니다.')
                if match[2]:
                    if data['status'] != 'completed':
                        return error(404, '아직 저장된 사진이 없습니다.')
                    return respond(200, (jobs.root / match[1] / match[2]).read_bytes(), 'image/jpeg')
                return respond(200, data)
            except FileNotFoundError:
                return error(404, '영상 작업을 찾지 못했습니다.')
        return backend(env, start)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8010)
    parser.add_argument('--runtime', type=Path, default=ROOT / 'runtime' / 'webapp')
    parser.add_argument('--model', type=Path, default=ROOT / 'models' / 'yolo26n.pt')
    args = parser.parse_args()
    args.runtime.mkdir(parents=True, exist_ok=True)
    database = args.runtime / 'sessions.sqlite3'
    if not database.exists():
        SQLiteRepository(database).initialize_schema()
    jobs = VideoJobs(args.runtime / 'videos', args.model)
    with make_server('127.0.0.1', args.port, create_web_app(database, jobs),
                     server_class=ThreadedServer, handler_class=LocalHandler) as server:
        print(f'Local: http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            jobs.pool.shutdown(wait=True)


if __name__ == '__main__':
    main()
