"""WSGI integration tests use real session data + SQLite and a deterministic analyzer."""
import io
import json
from pathlib import Path
import tempfile
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
        self.jobs.pool.shutdown(wait=True)
        data = self.jobs.get(job)
        self.assertEqual(data['status'],'completed')
        self.assertEqual(self.call('GET',f'/video-jobs/{job}/detected.jpg')[1],b'jpeg-test')
        code, raw, _ = self.call('GET', f'/video-jobs/{job}/result')
        self.assertEqual(code, 200)
        result = json.loads(raw)
        self.assertEqual(result['session_id'], self.state['session_id'])
        self.assertEqual(result['revision'], self.state['revision'])
        self.assertEqual(result['chart_no'], '차1-1')
        self.assertTrue(result['laws'])
        self.assertTrue(result['precedents'])
        self.assertEqual(result['laws'][0]['pdf_pages'], [1])
        self.assertEqual(result['fault']['basis'], 'stored_knia')
        self.assertEqual(result['fault']['ratio'], {'A': 0, 'B': 100})
        self.assertTrue(result['fault']['explanation'])
        self.assertIn('chartNo=', result['fault']['source_url'])
        self.assertNotIn('question_file', result)
        self.assertNotIn('answer_refs', result)
        # Changing an earlier real answer must invalidate the old video, including images.
        for answer in self.state['history']:
            alternative=next((o for o in answer['question_snapshot']['options'] if o['collection_status']=='verified' and o['option_id'] not in answer['selected_option_ids']),None)
            if alternative:
                self.service.revise_answer(self.state['session_id'],answer['question_id'],[alternative['option_id']],self.state['revision'])
                break
        else:self.fail('Expected a real alternative branch')
        self.assertEqual(self.call('GET',f'/video-jobs/{job}')[0],409)
        self.assertEqual(self.call('GET',f'/video-jobs/{job}/original.jpg')[0],409)
        self.assertEqual(self.call('GET',f'/video-jobs/{job}/result')[0],409)

    def test_reference_result_requires_finished_uploaded_video(self):
        self.complete()
        job_id = 'b' * 32
        self.assertEqual(self.call('GET', f'/video-jobs/{job_id}/result')[0], 404)
        (self.jobs.root / job_id).mkdir()
        data = dict(job_id=job_id, session_id=self.state['session_id'],
                    revision=self.state['revision'], status='processing')
        self.jobs.save(data)
        self.assertEqual(self.call('GET', f'/video-jobs/{job_id}/result')[0], 409)
        for status in ('no_detection', 'failed'):
            data['status'] = status
            self.jobs.save(data)
            code, body, _ = self.call('GET', f'/video-jobs/{job_id}/result')
            self.assertEqual(code, 200)
            self.assertTrue(json.loads(body)['laws'])

    def test_pdf_absence_is_distinct_from_a_missing_chart(self):
        from result_service import build_result
        context = dict(session_id=self.state['session_id'], revision=1,
                       search_summary='테스트', chart_no='차1-3')
        result = build_result(context)
        self.assertTrue(result['laws'])
        self.assertEqual(result['precedents'], [])
        self.assertEqual(result['precedent_status'], 'not_in_provided_pdf')
        context['chart_no'] = 'unknown'
        missing = build_result(context)
        self.assertEqual(missing['laws'], [])
        self.assertEqual(missing['precedents'], [])
        self.assertIsNone(missing['fault']['ratio'])

    def test_result_sources_fail_independently(self):
        from unittest.mock import patch
        import result_service
        original = result_service.read_data
        context = dict(session_id=self.state['session_id'], revision=1, chart_no='차1-1')
        for missing in ('accident_cases.json', 'legal_references_by_chart.json'):
            def read(filename):
                if filename == missing:
                    raise FileNotFoundError(filename)
                return original(filename)
            with patch.object(result_service, 'read_data', side_effect=read):
                result = result_service.build_result(context)
            if missing == 'accident_cases.json':
                self.assertEqual(result['fault']['status'], 'unavailable')
                self.assertTrue(result['laws'])
            else:
                self.assertEqual(result['law_status'], 'unavailable')
                self.assertEqual(result['fault']['ratio'], {'A': 0, 'B': 100})

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
