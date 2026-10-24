"""Single-process team demo server. Put behind an HTTPS reverse proxy."""
import base64
import binascii
import hmac
import os
from pathlib import Path
from urllib.parse import urlsplit

from app_server import VideoJobs, create_web_app, MAX_UPLOAD
from sqlite_repository import SQLiteRepository
from tools.team_check import ROOT


def team_gate(app, origin, password):
    expected = ('team:' + password).encode()
    def gated(env, start):
        def reply(code, message, extra=()):
            data = message.encode()
            start(code, [('Content-Type', 'text/plain; charset=utf-8'),
                        ('Content-Length', str(len(data))), ('Cache-Control', 'no-store'), *extra])
            return [data]
        # Health probes contain no application or model details.
        if env.get('PATH_INFO') == '/healthz' and env.get('REQUEST_METHOD') == 'GET':
            return reply('200 OK', 'ok')
        if env.get('HTTP_HOST') != urlsplit(origin).netloc:
            return reply('403 Forbidden', 'Host not allowed')
        if env.get('HTTP_ORIGIN') and env['HTTP_ORIGIN'] != origin:
            return reply('403 Forbidden', 'Origin not allowed')
        try:
            scheme, token = env.get('HTTP_AUTHORIZATION', '').split(' ', 1)
            supplied = base64.b64decode(token, validate=True) if scheme.lower() == 'basic' else b''
        except (ValueError, binascii.Error):
            supplied = b''
        if not hmac.compare_digest(supplied, expected):
            return reply('401 Unauthorized', 'Team sign-in required',
                         [('WWW-Authenticate', 'Basic realm="Team demo", charset="UTF-8"')])
        return app(env, start)
    return gated


def build_app():
    origin = os.environ.get('PUBLIC_ORIGIN', '').rstrip('/')
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('PUBLIC_ORIGIN must be a single HTTPS origin')
    password = os.environ.get('TEAM_PASSWORD', '')
    if len(password) < 24:
        raise ValueError('TEAM_PASSWORD must have at least 24 characters')
    if not os.environ.get('DATA_DIR'):
        raise ValueError('DATA_DIR must explicitly point to persistent storage')
    runtime = Path(os.environ['DATA_DIR'])
    if os.environ.get('RAILWAY_ENVIRONMENT_ID') and os.environ.get('RAILWAY_VOLUME_MOUNT_PATH') != str(runtime):
        raise ValueError('Railway volume must be mounted at DATA_DIR')
    if not runtime.is_absolute():
        raise ValueError('DATA_DIR must be an absolute persistent-volume path')
    model = Path(os.environ.get('MODEL_PATH', str(ROOT / 'models' / 'yolo26n.pt')))
    if not model.is_file():
        raise ValueError('Model missing; run tools/prepare_video.py during build')
    runtime.mkdir(parents=True, exist_ok=True)
    database = runtime / 'sessions.sqlite3'
    if not database.exists():
        SQLiteRepository(database).initialize_schema()
    jobs = VideoJobs(runtime / 'videos', model)
    return team_gate(create_web_app(database, jobs, public_origin=origin), origin, password), jobs


def main():
    from waitress import serve
    app, jobs = build_app()
    try:
        serve(app, host=os.environ.get('BIND_HOST', '0.0.0.0'),
              port=int(os.environ.get('PORT', '8080')), threads=4,
              url_scheme='https', max_request_body_size=MAX_UPLOAD,
              connection_limit=32, channel_timeout=120, expose_tracebacks=False)
    finally:
        jobs.pool.shutdown(wait=True)


if __name__ == '__main__':
    main()
