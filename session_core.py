"""Pinned experimental session service; append-only answers and internal context."""
from __future__ import annotations

from contextlib import AbstractContextManager
from copy import deepcopy
from dataclasses import dataclass, field, replace, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Protocol
from uuid import uuid4

VERSION = 'knia-rep-v1-9aaf88ec211ea3ab'
CONTRACT = 'experimental.questions.1'
QUESTION_PATH = 'outputs/session03_representative/runs/live_final/datasets/' + VERSION + '/questions.json'
QUESTION_SHA = 'ccbd797a539f763e6d9ecb9294b9fe03c83acf7b95518e521313bcb5c2b9daff'


class SessionError(Exception):
    """Safe public code only; never include driver errors or credentials."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class QuestionRef:
    path: str
    sha256: str
    question_schema_version: str
    contract_version: str


PIN = QuestionRef(QUESTION_PATH, QUESTION_SHA, VERSION, CONTRACT)


class ExperimentalQuestionAdapter:
    """Only experimental.questions.1; add a separate adapter after team adoption."""
    @staticmethod
    def validate(data: dict) -> None:
        try:
            questions = data['questions']
            ids = [q['question_id'] for q in questions]
            if not ids or any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)) or data['start_question_id'] not in ids:
                raise ValueError()
            frontier = {(b['question_id'], b['option_id']) for b in data['uncollected_branches']}
            if len(frontier) != len(data['uncollected_branches']):
                raise ValueError()
            expected = set()
            for q in questions:
                if not isinstance(q['text'], str) or not q['text'] or q['selection_mode'] != 'single' or q['min_selections'] != 1 or q['max_selections'] != 1:
                    raise ValueError()
                options = q['options']
                oids = [o['option_id'] for o in options]
                if not oids or len(oids) != len(set(oids)) or any(not isinstance(o['label'], str) or not o['label'] for o in options):
                    raise ValueError()
                routed = set()
                for rule in q['routing']['rules']:
                    selected = rule['selected_option_ids']
                    if len(selected) != 1 or selected[0] not in oids or selected[0] in routed:
                        raise ValueError()
                    routed.add(selected[0])
                    dest = rule['next']
                    if dest['type'] == 'question':
                        if dest['question_id'] not in ids:
                            raise ValueError()
                    elif dest != {'type': 'complete'}:
                        raise ValueError()
                for option in options:
                    if option['option_id'] not in routed:
                        if option['collection_status'] != 'uncollected':
                            raise ValueError()
                        expected.add((q['question_id'], option['option_id']))
            if expected != frontier:
                raise ValueError()
        except (KeyError, TypeError, ValueError, IndexError):
            raise SessionError('invalid_question_data') from None

    @staticmethod
    def public_question(question: dict) -> dict:
        # Provenance and internal relative file locations stay in the pinned dataset.
        return {**{k: deepcopy(question[k]) for k in ('question_id', 'text', 'selection_mode', 'min_selections', 'max_selections', 'vehicle_role')},
                'options': [{k: deepcopy(o[k]) for k in ('option_id', 'label', 'collection_status')} for o in question['options']]}


class MultiTerminalQuestionAdapter(ExperimentalQuestionAdapter):
    """experimental.questions.2: single-choice tree with per-choice terminal evidence."""
    @staticmethod
    def validate(data: dict) -> None:
        ExperimentalQuestionAdapter.validate(data)
        try:
            for question in data['questions']:
                routed = {r['selected_option_ids'][0] for r in question['routing']['rules']}
                if any(o['collection_status'] != 'verified' for o in question['options'] if o['option_id'] in routed):
                    raise ValueError()
            questions = {q['question_id']: q for q in data['questions']}
            expected = {(q['question_id'], r['selected_option_ids'][0])
                        for q in questions.values() for r in q['routing']['rules']
                        if r['next'] == {'type': 'complete'}}
            actual = set()
            for terminal in data['terminals']:
                key = (terminal['question_id'], terminal['option_id'])
                if key in actual or key not in expected:
                    raise ValueError()
                actual.add(key)
                option = next(o for o in questions[key[0]]['options'] if o['option_id'] == key[1])
                ref = terminal['source_ref']
                if (terminal['type'] != 'complete' or not terminal['evidence']
                    or not isinstance(terminal['chart_no'], str) or not terminal['chart_no']
                    or terminal['chart_no'] != option['source_row']['chartno']
                    or ref != option['source_ref']['result'] or ref['status'] != 200
                    or ref['method'] != 'POST' or not isinstance(ref['path'], str)
                    or len(ref['sha256']) != 64):
                    raise ValueError()
            if actual != expected:
                raise ValueError()
            active, visited = set(), set()
            def walk(qid):
                if qid in active:
                    raise ValueError()
                if qid in visited:
                    return
                active.add(qid)
                for rule in questions[qid]['routing']['rules']:
                    if rule['next']['type'] == 'question':
                        walk(rule['next']['question_id'])
                active.remove(qid)
                visited.add(qid)
            walk(data['start_question_id'])
            if visited != set(questions):
                raise ValueError()
        except (KeyError, TypeError, ValueError, IndexError, StopIteration, RecursionError):
            raise SessionError('invalid_question_data') from None


class QuestionLoader:
    """Explicit registry, exact bytes per load, no filesystem search/fallback."""
    def __init__(self, root: Path, registry: dict[str, QuestionRef]):
        self.root = root.resolve()
        self.registry = dict(registry)

    def reference(self, version: str) -> QuestionRef:
        if not version or version not in self.registry:
            raise SessionError('question_version_not_found')
        return self.registry[version]

    def load(self, ref: QuestionRef) -> dict:
        if ref != self.reference(ref.question_schema_version):
            raise SessionError('question_reference_mismatch')
        if ref.contract_version not in (CONTRACT, 'experimental.questions.2'):
            raise SessionError('unsupported_question_contract')
        path = (self.root / ref.path).resolve()
        if not path.is_relative_to(self.root):
            raise SessionError('invalid_question_path')
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            raise SessionError('question_file_missing') from None
        except OSError:
            raise SessionError('question_file_unreadable') from None
        if hashlib.sha256(raw).hexdigest() != ref.sha256:
            raise SessionError('question_hash_mismatch')
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            raise SessionError('invalid_question_data') from None
        if not isinstance(data, dict):
            raise SessionError('invalid_question_data')
        if data.get('contract_version') != ref.contract_version or data.get('contract_status') != 'experimental':
            raise SessionError('unsupported_question_contract')
        if data.get('schema_version') != ref.question_schema_version or data.get('data_version') != ref.question_schema_version:
            raise SessionError('question_version_mismatch')
        adapter = MultiTerminalQuestionAdapter if ref.contract_version == 'experimental.questions.2' else ExperimentalQuestionAdapter
        adapter.validate(data)
        return data


@dataclass(frozen=True)
class AnswerSnapshot:
    """Server-owned snapshot of one committed answer."""
    sequence: int
    question_id: str
    selected_option_ids: tuple[str, ...]
    question_snapshot: dict
    selected_option_snapshots: tuple[dict, ...]
    answered_at: str
    revision: int


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    question_ref: QuestionRef
    current_question_id: str | None
    created_at: str
    updated_at: str
    status: str = 'in_progress'
    revision: int = 0
    history: tuple[AnswerSnapshot, ...] = field(default_factory=tuple)


class Repository(Protocol):
    def transaction(self) -> AbstractContextManager[Transaction]: ...

    def get(self, session_id: str) -> SessionRecord | None:
        """Consistent aggregate snapshot; read only; storage failure => storage_unavailable."""
        ...

    def create(self, record: SessionRecord) -> SessionRecord:
        """Atomic insert; return stored aggregate after durable commit; no upsert."""
        ...


class Transaction(Protocol):
    """Session06 separates append-only saves from explicit history truncation edits."""
    def get_for_update(self, session_id: str) -> SessionRecord | None: ...
    def save(self, record: SessionRecord, expected_revision: int) -> None: ...
    def revise(self, record: SessionRecord, expected_revision: int) -> None: ...
    def commit(self) -> None: ...


class TransactionFactory(Protocol):
    def transaction(self) -> AbstractContextManager[Transaction]:
        """Rollback on error or context exit without successful explicit commit."""
        ...


class SessionService:
    def __init__(self, loader: QuestionLoader, repository: Repository):
        self.loader, self.repository = loader, repository

    @staticmethod
    def _response(record: SessionRecord, dataset: dict) -> dict:
        question = next((q for q in dataset['questions'] if q['question_id'] == record.current_question_id), None)
        if record.status == 'in_progress' and question is None:
            raise SessionError('stored_question_not_found')
        return deepcopy({
            'api_contract_version': 'experimental.sessions.1',
            'contract_status': 'experimental',
            'session_id': record.session_id, 'status': record.status,
            'revision': record.revision, 'history': [{
                'sequence': a.sequence, 'question_id': a.question_id,
                'selected_option_ids': list(a.selected_option_ids),
                'question_snapshot': ExperimentalQuestionAdapter.public_question(a.question_snapshot),
                'selected_option_snapshots': [{k: deepcopy(o[k]) for k in ('option_id', 'label', 'collection_status')}
                                              for o in a.selected_option_snapshots],
                'answered_at': a.answered_at, 'revision': a.revision,
            } for a in record.history],
            'current_question_id': record.current_question_id,
            'current_question': ExperimentalQuestionAdapter.public_question(question) if question else None,
            'question_schema_version': record.question_ref.question_schema_version,
            'question_contract_version': record.question_ref.contract_version,
            'question_file': {'sha256': record.question_ref.sha256},
            'next_action': 'upload_video' if record.status == 'completed' else 'answer_question',
            **({'message': '모든 질문이 끝났어요. 사고 영상을 첨부해주세요.'} if record.status == 'completed' else {}),
            'created_at': record.created_at, 'updated_at': record.updated_at,
        })

    def start_session(self, question_schema_version: str) -> dict:
        ref = self.loader.reference(question_schema_version)
        data = self.loader.load(ref)
        now = datetime.now(timezone.utc).isoformat()
        record = SessionRecord(str(uuid4()), ref, data['start_question_id'], now, now)
        committed = self.repository.create(record)
        return self._response(committed, data)

    def get_session(self, session_id: str) -> dict:
        self._session_id(session_id)
        record = self.repository.get(session_id)
        if record is None:
            raise SessionError('session_not_found')
        data = self.loader.load(record.question_ref)
        self._validate_record(record, data)
        return self._response(record, data)


    @staticmethod
    def _session_id(value):
        if not isinstance(value, str) or not value.strip():
            raise SessionError('invalid_session_id')

    @staticmethod
    def _selection(question, selected, dataset):
        if not isinstance(selected, list) or any(not isinstance(i, str) or not i for i in selected):
            raise SessionError('invalid_selection_type')
        if len(selected) != len(set(selected)):
            raise SessionError('duplicate_selection')
        if not question['min_selections'] <= len(selected) <= question['max_selections']:
            raise SessionError('invalid_selection_count')
        if question['selection_mode'] == 'single' and len(selected) != 1:
            raise SessionError('invalid_selection_count')
        options = [o for o in question['options'] if o['option_id'] in selected]
        if len(options) != len(selected):
            raise SessionError('unknown_option')
        if any(o['collection_status'] == 'uncollected' for o in options):
            raise SessionError('uncollected_branch')
        matches = [r['next'] for r in question['routing']['rules']
                   if set(r['selected_option_ids']) == set(selected)]
        if len(matches) != 1:
            raise SessionError('routing_error')
        dest = matches[0]
        if dest.get('type') == 'question':
            if dest.get('question_id') not in {q['question_id'] for q in dataset['questions']}:
                raise SessionError('routing_error')
        elif dest != {'type': 'complete'}:
            raise SessionError('routing_error')
        return options, dest

    @classmethod
    def _validate_record(cls, record, data):
        # Replay against the pinned server definition; detect tampering and partial writes.
        current, status = data['start_question_id'], 'in_progress'
        if (type(record.revision) is not int or record.revision < len(record.history)
            or (not record.history and record.revision != 0)
            or (record.history and record.history[-1].revision != record.revision)):
            raise SessionError('stored_state_invalid')
        try:
            for n, answer in enumerate(record.history, 1):
                question = next(q for q in data['questions'] if q['question_id'] == current)
                options, dest = cls._selection(question, list(answer.selected_option_ids), data)
                if (status != 'in_progress' or answer.sequence != n
                    or type(answer.revision) is not int or answer.revision < n
                    or answer.revision > record.revision
                    or (n > 1 and answer.revision <= record.history[n-2].revision)
                    or answer.question_id != current or answer.question_snapshot != question
                    or answer.selected_option_snapshots != tuple(options)
                    or answer.selected_option_ids != tuple(o['option_id'] for o in options)):
                    raise SessionError('stored_state_invalid')
                status = 'completed' if dest['type'] == 'complete' else 'in_progress'
                current = None if status == 'completed' else dest['question_id']
            if record.status != status or record.current_question_id != current:
                raise SessionError('stored_state_invalid')
        except (SessionError, StopIteration, KeyError, TypeError, ValueError):
            raise SessionError('stored_state_invalid') from None

    def submit_answer(self, session_id, question_id, selected_option_ids, expected_revision):
        self._session_id(session_id)
        if not isinstance(question_id, str) or not question_id.strip():
            raise SessionError('invalid_question_id')
        if type(expected_revision) is not int or expected_revision < 0:
            raise SessionError('invalid_revision')
        with self.repository.transaction() as tx:
            record = tx.get_for_update(session_id)
            if record is None:
                raise SessionError('session_not_found')
            if record.revision != expected_revision:
                raise SessionError('revision_conflict')
            data = self.loader.load(record.question_ref)
            self._validate_record(record, data)
            if record.status == 'completed':
                raise SessionError('session_completed')
            if question_id != record.current_question_id:
                raise SessionError('question_mismatch')
            question = next(q for q in data['questions'] if q['question_id'] == question_id)
            options, dest = self._selection(question, selected_option_ids, data)
            now = datetime.now(timezone.utc).isoformat()
            revision = record.revision + 1
            answer = AnswerSnapshot(len(record.history)+1, question_id,
                tuple(o['option_id'] for o in options), deepcopy(question),
                tuple(deepcopy(options)), now, revision)
            updated = replace(record, history=record.history+(answer,), revision=revision,
                updated_at=now, status='completed' if dest['type'] == 'complete' else 'in_progress',
                current_question_id=None if dest['type'] == 'complete' else dest['question_id'])
            # Build response before saving so serialization/preparation failures roll back too.
            response = self._response(updated, data)
            tx.save(updated, expected_revision)
            tx.commit()
        return response

    def revise_answer(self, session_id, question_id, selected_option_ids, expected_revision):
        """Experimental edit: replace one saved answer and discard every later answer."""
        self._session_id(session_id)
        if not isinstance(question_id, str) or not question_id.strip():
            raise SessionError('invalid_question_id')
        if type(expected_revision) is not int or expected_revision < 0:
            raise SessionError('invalid_revision')
        with self.repository.transaction() as tx:
            record = tx.get_for_update(session_id)
            if record is None:
                raise SessionError('session_not_found')
            if record.revision != expected_revision:
                raise SessionError('revision_conflict')
            data = self.loader.load(record.question_ref)
            self._validate_record(record, data)
            target_index = next((n for n, answer in enumerate(record.history)
                                 if answer.question_id == question_id), None)
            if target_index is None:
                raise SessionError('answer_not_found')
            current = record.history[target_index]
            question = next(q for q in data['questions'] if q['question_id'] == question_id)
            options, dest = self._selection(question, selected_option_ids, data)
            option_ids = tuple(o['option_id'] for o in options)
            # A stale request has already failed above. Equal selected sets are a read-only no-op.
            if set(current.selected_option_ids) == set(option_ids):
                return self._response(record, data) | {'changed': False}
            now = datetime.now(timezone.utc).isoformat()
            revision = record.revision + 1
            replacement = AnswerSnapshot(current.sequence, question_id, option_ids,
                deepcopy(question), tuple(deepcopy(options)), now, revision)
            history = record.history[:target_index] + (replacement,)
            updated = replace(record, history=history, revision=revision, updated_at=now,
                status='completed' if dest['type'] == 'complete' else 'in_progress',
                current_question_id=None if dest['type'] == 'complete' else dest['question_id'])
            self._validate_record(updated, data)
            response = self._response(updated, data) | {'changed': True}
            tx.revise(updated, expected_revision)
            tx.commit()
        return response

    def get_context(self, session_id):
        self._session_id(session_id)
        record = self.repository.get(session_id)
        if record is None:
            raise SessionError('session_not_found')
        data = self.loader.load(record.question_ref)
        self._validate_record(record, data)
        if record.status != 'completed':
            raise SessionError('session_incomplete')
        conditions, refs, labels = {}, [], []
        for answer in record.history:
            for option in answer.selected_option_snapshots:
                for key, value in option.get('normalized_facts', {}).get('conditions', {}).items():
                    if key in conditions and conditions[key] != value:
                        raise SessionError('stored_state_invalid')
                    conditions[key] = deepcopy(value)
                labels.append(option['label'])
                refs.append({'sequence': answer.sequence, 'question_id': answer.question_id,
                    'option_id': option['option_id'], 'source_ref': deepcopy(option.get('source_ref'))})
        terminal = data.get('terminal', {})
        last = record.history[-1]
        if record.question_ref.contract_version == 'experimental.questions.2':
            matches = [t for t in data['terminals'] if t['question_id'] == last.question_id
                       and last.selected_option_ids == (t['option_id'],)]
            if len(matches) != 1:
                raise SessionError('invalid_question_data')
            terminal = matches[0]
        verified = (terminal.get('type') == 'complete' and terminal.get('question_id') == last.question_id
                    and last.selected_option_ids == (terminal.get('option_id'),)
                    and bool(terminal.get('evidence')) and bool(terminal.get('source_ref')))
        return {'context_contract_version': 'experimental.accident_context.1', 'contract_status': 'experimental',
            'session_id': session_id, 'revision': record.revision,
            'question_schema_version': record.question_ref.question_schema_version,
            'question_contract_version': record.question_ref.contract_version,
            'question_file': asdict(record.question_ref), 'answer_refs': refs,
            'conditions': conditions, 'my_vehicle': None, 'other_vehicle': None,
            'source_mapping': deepcopy(data.get('source_mapping')),
            'search_summary': '선택한 사고 상황: ' + ' / '.join(labels),
            'chart_no': terminal.get('chart_no') if verified else None,
            'chart_evidence': {'evidence': terminal['evidence'], 'source_ref': deepcopy(terminal['source_ref'])} if verified else None}


class SessionEndpoints:
    """Framework-neutral handlers registered by main.create_app."""
    def __init__(self, service: SessionService):
        self.service = service

    def post_sessions(self, body: dict) -> tuple[int, dict]:
        if not isinstance(body, dict) or set(body) != {'question_schema_version'} or not isinstance(body['question_schema_version'], str):
            return 422, {'error': {'code': 'invalid_request'}}
        return self._call(201, lambda: self.service.start_session(body['question_schema_version']))

    def get_session(self, session_id: str) -> tuple[int, dict]:
        return self._call(200, lambda: self.service.get_session(session_id))

    def post_answers(self, session_id, body):
        if not isinstance(body, dict) or set(body) != {'question_id', 'selected_option_ids', 'expected_revision'}:
            return 422, {'error': {'code': 'invalid_request'}}
        return self._call(200, lambda: self.service.submit_answer(session_id, **body))

    def put_answer(self, session_id, question_id, body):
        if not isinstance(body, dict) or set(body) != {'selected_option_ids', 'expected_revision'}:
            return 422, {'error': {'code': 'invalid_request'}}
        return self._call(200, lambda: self.service.revise_answer(session_id, question_id, **body))

    @staticmethod
    def _call(status, action):
        try:
            return status, action()
        except SessionError as exc:
            http = {'session_not_found': 404, 'question_version_not_found': 422,
                    'storage_unavailable': 503, 'session_id_conflict': 409,
                    'revision_conflict': 409, 'session_completed': 409, 'question_mismatch': 409,
                    'answer_not_found': 404,
                    'uncollected_branch': 422, 'invalid_session_id': 422, 'invalid_question_id': 422,
                    'invalid_revision': 422, 'invalid_selection_type': 422,
                    'duplicate_selection': 422, 'invalid_selection_count': 422, 'unknown_option': 422}.get(exc.code, 500)
            return http, {'error': {'code': exc.code}}
