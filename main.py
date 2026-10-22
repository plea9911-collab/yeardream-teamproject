"""Standalone experimental WSGI backend using only Python standard library."""
import argparse
from http import HTTPStatus
import json
from pathlib import Path
from urllib.parse import unquote
from wsgiref.simple_server import make_server, WSGIRequestHandler

from session_core import PIN, VERSION, QuestionLoader, SessionEndpoints, SessionService
from sqlite_repository import SQLiteRepository


def create_app(question_root: Path, database: Path, *, registry=None, loader=None):
    # Test-only injection is explicit; production keeps the single pinned registry.
    endpoints = SessionEndpoints(SessionService(loader or QuestionLoader(question_root, registry or {VERSION: PIN}), SQLiteRepository(database)))

    def app(environ, start_response):
        method, path = environ['REQUEST_METHOD'], environ.get('PATH_INFO', '')
        code, payload = 404, {'error': {'code': 'route_not_found'}}
        answer_route = path.startswith('/sessions/') and path.endswith('/answers') and bool(path.split('/')[2]) and len(path.split('/')) == 4
        revise_route = path.startswith('/sessions/') and '/answers/' in path and bool(path.split('/')[2]) and bool(path.split('/')[-1]) and len(path.split('/')) == 5
        if path == '/sessions' or answer_route or revise_route:
            expected_method = 'PUT' if revise_route else 'POST'
            if method != expected_method:
                code, payload = 405, {'error': {'code': 'method_not_allowed'}}
            else:
                try:
                    length = int(environ.get('CONTENT_LENGTH') or '0')
                    if length <= 0 or length > 4096:
                        raise ValueError()
                    media_type = environ.get('CONTENT_TYPE', '').split(';')[0].strip().lower()
                    if media_type != 'application/json':
                        code, payload = 415, {'error': {'code': 'unsupported_media_type'}}
                    else:
                        raw = environ['wsgi.input'].read(length)
                        if len(raw) != length:
                            raise ValueError()
                        body = json.loads(raw)
                        if revise_route:
                            code, payload = endpoints.put_answer(unquote(path.split('/')[2]), unquote(path.split('/')[-1]), body)
                        elif answer_route:
                            code, payload = endpoints.post_answers(unquote(path.split('/')[2]), body)
                        else:
                            code, payload = endpoints.post_sessions(body)
                except (ValueError, UnicodeError):
                    code, payload = 422, {'error': {'code': 'invalid_request'}}
        elif path.startswith('/sessions/') and path[len('/sessions/'):] and '/' not in path[len('/sessions/'):]:
            if method != 'GET':
                code, payload = 405, {'error': {'code': 'method_not_allowed'}}
            else:
                code, payload = endpoints.get_session(unquote(path[len('/sessions/'):]))
        raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        start_response(f'{code} {HTTPStatus(code).phrase}', [('Content-Type', 'application/json; charset=utf-8'), ('Content-Length', str(len(raw))), ('Cache-Control', 'no-store')])
        return [raw]
    return app


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_config = Path(__file__).with_name('settings.json')
    if not default_config.exists():
        default_config = Path(__file__).with_name('settings.example.json')
    parser.add_argument('--config', type=Path, default=default_config)
    parser.add_argument('--init-db', action='store_true')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    config_dir = args.config.resolve().parent
    root = (config_dir / config['question_root']).resolve()
    database = (config_dir / config['database']).resolve()
    # Fail before serving if the selected question bundle is unusable.
    QuestionLoader(root, {VERSION: PIN}).load(PIN)
    if args.init_db:
        database.parent.mkdir(parents=True, exist_ok=True)
        SQLiteRepository(database).initialize_schema()
        print(json.dumps({'database_initialized': True}), flush=True)
        return
    with make_server('127.0.0.1', args.port, create_app(root, database), handler_class=QuietHandler) as server:
        print(json.dumps({'listening': '127.0.0.1', 'port': server.server_port, 'api_contract': 'experimental.sessions.1'}), flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
