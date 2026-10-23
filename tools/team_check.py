"""Portable, offline handoff checks and explicit experimental dual-version server."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import urllib.error
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from session_core import PIN, VERSION, QuestionRef, QuestionLoader, SessionService
from sqlite_repository import SQLiteRepository
from main import create_app, QuietHandler
from wsgiref.simple_server import make_server

V2 = 'knia-car-v2-dd12c7da4fc9b210'
REF2 = QuestionRef('outputs/session07_collection/runs/live_final/datasets/' + V2 + '/questions.json',
    '48c4f7359adecf1f92f2f6ae16d1c2a64fa57856f59b0f2221ff6a40a89494c9', V2, 'experimental.questions.2')
REGISTRY = {VERSION: PIN, V2: REF2}

def service(db):
    return SessionService(QuestionLoader(ROOT, REGISTRY), SQLiteRepository(db))

def new_run():
    folder = ROOT / 'runtime' / 'handoff' / uuid4().hex[:12]
    folder.mkdir(parents=True, exist_ok=False)
    return folder

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['verify', 'serve', 'context'])
    p.add_argument('--database', type=Path)
    p.add_argument('--session-id')
    p.add_argument('--port', type=int, default=8008)
    p.add_argument('--all-paths', action='store_true', help='Optional service/SQLite 108 paths; not HTTP exhaustive')
    a = p.parse_args()
    if a.action in ('serve', 'context'):
        if a.database:
            db = a.database.resolve()
            if not db.is_relative_to(ROOT / 'runtime' / 'handoff') or not db.is_file():
                p.error('reopen only an existing runtime/handoff DB; never initialize existing DBs')
        elif a.action == 'context':
            p.error('context requires --database and --session-id')
        else:
            db = new_run() / 'sessions.sqlite3'
            SQLiteRepository(db).initialize_schema()
        if a.action == 'context':
            if not a.session_id:
                p.error('--session-id required')
            print(json.dumps(service(db).get_context(a.session_id), ensure_ascii=False))
            return
        for ref in REGISTRY.values():
            QuestionLoader(ROOT, REGISTRY).load(ref)
        with make_server('127.0.0.1', a.port, create_app(ROOT, db, registry=REGISTRY), handler_class=QuietHandler) as server:
            print(json.dumps({'database':str(db), 'port':server.server_port, 'experimental_registry':list(REGISTRY)}, ensure_ascii=False), flush=True)
            server.serve_forever()
        return
    folder = new_run()
    report = {'scope':'relocation smoke; real data and fresh SQLite; no external requests', 'checks':[], 'http':[]}
    def check(name, result):
        report['checks'].append({'name':name, 'passed':bool(result)})
        if not result:
            raise AssertionError(name)
    def paths(data, qid=None, prefix=()):
        qid = qid or data['start_question_id']
        q = next(q for q in data['questions'] if q['question_id'] == qid)
        for rule in q['routing']['rules']:
            seq = prefix + ((qid, rule['selected_option_ids']),)
            if rule['next']['type'] == 'complete':
                yield seq
            else:
                yield from paths(data, rule['next']['question_id'], seq)
    proc = None
    def launch(args):
        return subprocess.Popen([sys.executable,'-B','-X','utf8',*args],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8')
    def stop():
        nonlocal proc
        if proc:
            proc.terminate()
            proc.communicate(timeout=10)
            proc = None
    try:
        loader = QuestionLoader(ROOT, REGISTRY)
        bundles = {v:loader.load(r) for v,r in REGISTRY.items()}
        check('both exact pinned bundles load without raw captures', len(bundles)==2)
        db = folder / 'sessions.sqlite3'
        SQLiteRepository(db).initialize_schema()
        s = service(db)
        ids = []
        for v, data in bundles.items():
            selected_paths = list(paths(data)) if a.all_paths else [next(paths(data))]
            report.setdefault('service_paths',{})[v] = len(selected_paths)
            for seq in selected_paths:
                state = s.start_session(v)
                for qid, selected in seq:
                    state = s.submit_answer(state['session_id'],qid,selected,state['revision'])
                ctx = s.get_context(state['session_id'])
                check(v+' service completion/context', state['status']=='completed' and ctx['question_schema_version']==v)
            ids.append(state['session_id'])
        before = hashlib.sha256(db.read_bytes()).hexdigest()
        for sid in ids:
            s.get_session(sid); s.get_context(sid)
        check('GET/context readonly bytes',hashlib.sha256(db.read_bytes()).hexdigest()==before)
        # Exercise documented default CLI with relative config paths, independent of personal settings.
        config = folder / 'v1.json'
        config.write_text(json.dumps({'question_root':'../../..','database':'default.sqlite3'}),encoding='utf8')
        r = subprocess.run([sys.executable,'-B','-X','utf8','main.py','--config',str(config),'--init-db'],cwd=ROOT,capture_output=True,text=True,encoding='utf8')
        check('default CLI fresh DB initialization',r.returncode==0)
        proc = launch(['main.py','--config',str(config),'--port','0'])
        ready = json.loads(proc.stdout.readline())
        port = ready['port']
        def request(method, path, body=None):
            raw = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(f'http://127.0.0.1:{port}'+path, data=raw, method=method,headers={'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    code, out = resp.status,json.load(resp)
            except urllib.error.HTTPError as exc:
                code,out=exc.code,json.load(exc)
            report['http'].append({'method':method,'path':path,'request':body,'status':code,'response':out})
            return code,out
        code,state = request('POST','/sessions',{'question_schema_version':VERSION})
        check('default v1 HTTP start', code==201)
        check('default CLI refuses v2',request('POST','/sessions',{'question_schema_version':V2})[0]==422)
        stop()
        proc = launch(['tools/team_check.py','serve','--database',str(db),'--port','0'])
        port = json.loads(proc.stdout.readline())['port']
        check('dual registry restart GET',all(request('GET','/sessions/'+sid)[0]==200 for sid in ids))
        code,state=request('POST','/sessions',{'question_schema_version':V2})
        check('explicit v2 HTTP start',code==201)
        sid=state['session_id']; base='/sessions/'+sid
        check('uncollected refused',request('POST',base+'/answers',{'question_id':state['current_question_id'],'selected_option_ids':['o_1'],'expected_revision':0})[0]==422)
        seq=next(paths(bundles[V2]))
        for qid,selected in seq:
            code,state=request('POST',base+'/answers',{'question_id':qid,'selected_option_ids':selected,'expected_revision':state['revision']})
            check('v2 HTTP answer',code==200)
        check('explicit complete/upload prompt',state['status']=='completed' and state['next_action']=='upload_video')
        qid,selected=seq[-1]
        code,noop=request('PUT',base+'/answers/'+qid,{'selected_option_ids':selected,'expected_revision':state['revision']})
        check('same selection no-op',code==200 and noop['changed'] is False)
        check('stale same selection 409',request('PUT',base+'/answers/'+qid,{'selected_option_ids':selected,'expected_revision':state['revision']-1})[0]==409)
        # Change an earlier answer to another real collected branch and re-complete.
        for index,(qid,selected) in enumerate(seq):
            q=next(q for q in bundles[V2]['questions'] if q['question_id']==qid)
            alternative=next((r for r in q['routing']['rules'] if r['selected_option_ids']!=selected),None)
            if alternative:
                code,revised=request('PUT',base+'/answers/'+qid,{'selected_option_ids':alternative['selected_option_ids'],'expected_revision':state['revision']})
                check('real revision changed',code==200 and revised['changed'] is True)
                state=request('GET',base)[1]
                check('suffix removed and revision increments once',len(state['history'])==index+1 and state['revision']==len(seq)+1)
                while state['status']!='completed':
                    q=next(q for q in bundles[V2]['questions'] if q['question_id']==state['current_question_id'])
                    rule=q['routing']['rules'][0]
                    code,state=request('POST',base+'/answers',{'question_id':q['question_id'],'selected_option_ids':rule['selected_option_ids'],'expected_revision':state['revision']})
                    check('HTTP recompletion answer',code==200)
                break
        else:
            raise AssertionError('no real revision alternative')
        check('no context HTTP endpoint',request('GET',base+'/context')[0]==404)
        check('public history hides source metadata',all(k not in json.dumps(state['history']) for k in ['source_ref','source_row','normalized_facts','.response.body']))
        stop()
        proc=launch(['tools/team_check.py','serve','--database',str(db),'--port','0'])
        port=json.loads(proc.stdout.readline())['port']
        check('separate server restart restored revised state',request('GET',base)[1]==state)
        stop()
        r=subprocess.run([sys.executable,'-B','-X','utf8','tools/team_check.py','context','--database',str(db),'--session-id',sid],cwd=ROOT,capture_output=True,text=True,encoding='utf8')
        check('separate Python context restoration',r.returncode==0 and json.loads(r.stdout)==service(db).get_context(sid))
        report['status']='passed'
    except Exception as exc:
        report['status']='failed';report['error']=repr(exc)
    finally:
        stop()
        (folder/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'status':report['status'],'checks':len(report['checks']),'report':str(folder/'verification.json')},ensure_ascii=False))
    if report['status']!='passed':
        raise SystemExit(1)

if __name__=='__main__':
    main()
