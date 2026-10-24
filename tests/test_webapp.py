"""WSGI integration tests use real session data + SQLite and a deterministic analyzer."""
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from app_server import create_web_app, VideoJobs, MAX_UPLOAD
from sqlite_repository import SQLiteRepository
from tools.team_check import service, V2


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / 'sessions.sqlite3'
        SQLiteRepository(self.db).initialize_schema()
        self.model = self.root / 'model.pt'
        self.model.write_bytes(b'test stub, never loaded')
        def analyzer(source, folder, model, progress):
            progress(50)
            (folder / 'detected.jpg').write_bytes(b'jpeg-test')
            (folder / 'original.jpg').write_bytes(b'jpeg-original')
            return {'status':'completed','progress':100,'detections':[]}
        self.jobs = VideoJobs(self.root / 'jobs', self.model, analyzer)
        self.app = create_web_app(self.db, self.jobs)
        self.service = service(self.db)
        self.state = self.service.start_session(V2)

    def tearDown(self):
        self.jobs.pool.shutdown(wait=True)
        self.temp.cleanup()

    def call(self, method, path, raw=b'', **headers):
        path, _, query = path.partition('?')
        env = dict(REQUEST_METHOD=method, PATH_INFO=path, QUERY_STRING=query,
                   CONTENT_LENGTH=str(len(raw)), CONTENT_TYPE='application/octet-stream',
                   HTTP_HOST='127.0.0.1:8010', **{'wsgi.input':io.BytesIO(raw)})
        env.update(headers)
        result = {}
        def start(status, h):
            result.update(code=int(status.split()[0]), headers=dict(h))
        body = b''.join(self.app(env,start))
        return result['code'], body, result['headers']

    def complete(self):
        while self.state['status'] != 'completed':
            q = self.state['current_question']
            option = next(o for o in q['options'] if o['collection_status']=='verified')
            self.state = self.service.submit_answer(self.state['session_id'],q['question_id'],[option['option_id']],self.state['revision'])

    def url(self, filename='sample.mp4', revision=None):
        return f"/video-jobs?session_id={self.state['session_id']}&revision={self.state['revision'] if revision is None else revision}&filename={filename}"

    def test_duplicate_progress_is_not_written_again(self):
        self.complete()
        def analyzer(source, folder, model, progress):
            for value in (0, 1, 1, 2, 2):
                progress(value)
            return {'status': 'no_detection', 'progress': 100, 'detections': []}
        self.jobs.analyzer = analyzer
        writes = []
        save = self.jobs.save
        def recording_save(data):
            writes.append((data['status'], data['progress']))
            save(data)
        self.jobs.save = recording_save
        code, body, _ = self.call('POST', self.url(), b'video')
        self.assertEqual(code, 202)
        self.jobs.pool.shutdown(wait=True)
        self.assertEqual(self.jobs.get(json.loads(body)['job_id'])['status'], 'no_detection')
        self.assertEqual([p for status, p in writes if status == 'processing'], [0, 1, 2])

    def test_corrupt_record_does_not_block_restart(self):
        bad_id = 'a' * 32
        folder = self.jobs.root / bad_id
        folder.mkdir()
        (folder / 'job.json').write_text('{broken', encoding='utf-8')
        restarted = VideoJobs(self.jobs.root, self.model)
        try:
            self.assertEqual((folder / 'job.json').read_text(), '{broken')
            self.assertEqual(self.call('GET', '/video-jobs/' + bad_id)[0], 503)
            self.assertEqual(self.call('GET', '/app-config')[0], 200)
        finally:
            restarted.pool.shutdown(wait=True)

    def test_frontend_and_existing_api(self):
        for path in ['/', '/app.js', '/style.css','/app-config']:
            self.assertEqual(self.call('GET',path)[0],200)
        self.assertEqual(self.call('GET','/sessions/'+self.state['session_id'])[0],200)
        self.assertEqual(self.call('GET','/../README.md')[0],404)
        self.assertEqual(self.call('POST','/',HTTP_ORIGIN='https://outside.example')[0],403)

    def test_upload_guards(self):
        self.assertEqual(self.call('POST',self.url(),b'video')[0],409)
        self.complete()
        self.assertEqual(self.call('POST',self.url('bad.txt'),b'video')[0],415)
        self.assertEqual(self.call('POST',self.url(),b'')[0],413)
        self.assertEqual(self.call('POST',self.url(),b'x',CONTENT_LENGTH=str(MAX_UPLOAD+1))[0],413)
        self.assertEqual(self.call('POST',self.url(revision=0),b'x')[0],409)
        self.assertEqual(self.call('POST',self.url(),b'x',CONTENT_LENGTH='12')[0],422)

    def test_result_and_revision_invalidation(self):
        self.complete()
        code, body, _ = self.call('POST',self.url(),b'video')
        self.assertEqual(code,202)
        job = json.loads(body)['job_id']
        for _ in range(100):
            data=self.jobs.get(job)
            if data['status']=='completed':break
            time.sleep(.01)
        self.assertEqual(data['status'],'completed')
        self.assertEqual(self.call('GET',f'/video-jobs/{job}/detected.jpg')[1],b'jpeg-test')
        # Changing an earlier real answer must invalidate the old video, including images.
        for answer in self.state['history']:
            alternative=next((o for o in answer['question_snapshot']['options'] if o['collection_status']=='verified' and o['option_id'] not in answer['selected_option_ids']),None)
            if alternative:
                self.service.revise_answer(self.state['session_id'],answer['question_id'],[alternative['option_id']],self.state['revision'])
                break
        else:self.fail('Expected a real alternative branch')
        self.assertEqual(self.call('GET',f'/video-jobs/{job}')[0],409)
        self.assertEqual(self.call('GET',f'/video-jobs/{job}/original.jpg')[0],409)

    def test_model_missing_and_busy_queue(self):
        self.complete()
        self.model.unlink()
        self.assertEqual(self.call('POST',self.url(),b'video')[0],503)
        self.model.write_bytes(b'stub')
        self.jobs.slots.acquire();self.jobs.slots.acquire()
        try:self.assertEqual(self.call('POST',self.url(),b'video')[0],429)
        finally:self.jobs.slots.release();self.jobs.slots.release()

    def test_host_and_content_type(self):
        self.assertEqual(self.call('GET','/',HTTP_HOST='outside.example')[0],403)
        self.complete()
        self.assertEqual(self.call('POST',self.url(),b'video',CONTENT_TYPE='text/plain')[0],415)

    def test_restart_marks_pending_failed(self):
        folder=self.jobs.root / ('a'*32);folder.mkdir()
        self.jobs.save({'job_id':'a'*32,'status':'processing'})
        other=VideoJobs(self.jobs.root,self.model)
        try:self.assertEqual(other.get('a'*32)['status'],'failed')
        finally:other.pool.shutdown()


if __name__=='__main__':unittest.main()
