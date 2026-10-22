"""SQLite adapter selected by user; standalone artifact, not app registration."""
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

from session_core import AnswerSnapshot, QuestionRef, SessionError, SessionRecord


SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('in_progress','completed')),
        current_question_id TEXT,
        revision INTEGER NOT NULL CHECK(revision >= 0),
        question_schema_version TEXT NOT NULL,
        question_contract_version TEXT NOT NULL,
        question_file_path TEXT NOT NULL,
        question_file_sha256 TEXT NOT NULL CHECK(length(question_file_sha256)=64),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS answers (
        session_id TEXT NOT NULL REFERENCES sessions(session_id),
        answer_order INTEGER NOT NULL CHECK(answer_order >= 1),
        question_id TEXT NOT NULL,
        selected_option_ids_json TEXT NOT NULL,
        question_snapshot_json TEXT NOT NULL,
        selected_option_snapshots_json TEXT NOT NULL,
        answered_at TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK(revision >= 1),
        PRIMARY KEY(session_id, answer_order)
    )''',
)


class SQLiteRepository:
    def __init__(self, database: Path):
        self.database = Path(database).resolve()

    def _connect(self, *, read_only=False):
        # mode=rw prevents silently creating a replacement DB after deletion.
        uri = self.database.as_uri() + ('?mode=ro' if read_only else '?mode=rw')
        connection = sqlite3.connect(uri, uri=True, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def initialize_schema(self):
        """Explicit opt-in for a dedicated DB; no drops, resets or migrations."""
        connection = None
        try:
            connection = sqlite3.connect(self.database, timeout=5, isolation_level=None)
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('BEGIN IMMEDIATE')
            for statement in SCHEMA:
                connection.execute(statement)
            connection.commit()
        except sqlite3.Error:
            if connection:
                connection.rollback()
            raise SessionError('storage_unavailable') from None
        finally:
            if connection:
                connection.close()

    def create(self, record: SessionRecord) -> SessionRecord:
        if record.revision != 0 or record.history or record.status != 'in_progress':
            raise SessionError('invalid_initial_state')
        connection = None
        try:
            connection = self._connect()
            connection.execute('BEGIN IMMEDIATE')
            ref = record.question_ref
            connection.execute('''INSERT INTO sessions
                (session_id,status,current_question_id,revision,question_schema_version,
                 question_contract_version,question_file_path,question_file_sha256,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (record.session_id, record.status, record.current_question_id, record.revision,
                 ref.question_schema_version, ref.contract_version, ref.path, ref.sha256,
                 record.created_at, record.updated_at))
            stored = self._read(connection, record.session_id)
            if stored != record:
                raise SessionError('stored_state_invalid')
            connection.commit()
            return stored
        except SessionError:
            if connection:
                connection.rollback()
            raise
        except sqlite3.Error as exc:
            if connection:
                connection.rollback()
            if isinstance(exc, sqlite3.IntegrityError) and getattr(exc, 'sqlite_errorname', '') == 'SQLITE_CONSTRAINT_PRIMARYKEY':
                raise SessionError('session_id_conflict') from None
            raise SessionError('storage_unavailable') from None
        finally:
            if connection:
                connection.close()

    def transaction(self):
        return SQLiteTransaction(self)

    def get(self, session_id: str) -> SessionRecord | None:
        connection = None
        try:
            connection = self._connect(read_only=True)
            connection.execute('BEGIN')
            record = self._read(connection, session_id)
            connection.commit()
            return record
        except sqlite3.Error:
            raise SessionError('storage_unavailable') from None
        except (ValueError, TypeError, KeyError, IndexError):
            raise SessionError('stored_state_invalid') from None
        finally:
            if connection:
                connection.close()

    @staticmethod
    def _read(connection, session_id):
        row = connection.execute('SELECT * FROM sessions WHERE session_id=?', (session_id,)).fetchone()
        if row is None:
            return None
        answers = connection.execute('SELECT * FROM answers WHERE session_id=? ORDER BY answer_order', (session_id,)).fetchall()
        try:
            ref = QuestionRef(row['question_file_path'], row['question_file_sha256'], row['question_schema_version'], row['question_contract_version'])
            history = tuple(AnswerSnapshot(
                a['answer_order'], a['question_id'], tuple(json.loads(a['selected_option_ids_json'])),
                json.loads(a['question_snapshot_json']), tuple(json.loads(a['selected_option_snapshots_json'])),
                a['answered_at'], a['revision']) for a in answers)
            return SessionRecord(row['session_id'], ref, row['current_question_id'], row['created_at'], row['updated_at'], row['status'], row['revision'], history)
        except (ValueError, TypeError, KeyError, IndexError):
            raise SessionError('stored_state_invalid') from None


def record_dict(record: SessionRecord) -> dict:
    """For local persistence verification, not public HTTP output."""
    return asdict(record)


class SQLiteTransaction:
    """One connection, explicit commit; rollback on every other exit."""
    def __init__(self, repository):
        self.repository = repository
        self.connection = None
        self.committed = False
        self.original = None

    def __enter__(self):
        try:
            self.connection = self.repository._connect()
            self.connection.execute('BEGIN IMMEDIATE')
            return self
        except sqlite3.Error:
            if self.connection:
                self.connection.close()
            raise SessionError('storage_unavailable') from None

    def get_for_update(self, session_id):
        self.original = self.repository._read(self.connection, session_id)
        return self.original

    def save(self, record, expected_revision):
        old = self.original
        if (old is None or old.revision != expected_revision or record.session_id != old.session_id
            or record.question_ref != old.question_ref or record.created_at != old.created_at
            or record.revision != expected_revision+1 or record.history[:-1] != old.history
            or len(record.history) != len(old.history)+1):
            raise SessionError('stored_state_invalid')
        answer = record.history[-1]
        if answer.sequence != len(record.history) or answer.revision != record.revision:
            raise SessionError('stored_state_invalid')
        self.connection.execute('''INSERT INTO answers (session_id,answer_order,question_id,selected_option_ids_json,question_snapshot_json,selected_option_snapshots_json,answered_at,revision) VALUES (?,?,?,?,?,?,?,?)''',
            (record.session_id, answer.sequence, answer.question_id,
             json.dumps(answer.selected_option_ids), json.dumps(answer.question_snapshot, ensure_ascii=False),
             json.dumps(answer.selected_option_snapshots, ensure_ascii=False), answer.answered_at, answer.revision))
        changed = self.connection.execute(
            'UPDATE sessions SET status=?,current_question_id=?,revision=?,updated_at=? WHERE session_id=? AND revision=?',
            (record.status, record.current_question_id, record.revision, record.updated_at, record.session_id, expected_revision))
        if changed.rowcount != 1:
            raise SessionError('revision_conflict')
        if self.repository._read(self.connection, record.session_id) != record:
            raise SessionError('stored_state_invalid')

    def revise(self, record, expected_revision):
        """Replace one answer, truncate its suffix, then CAS the session in this transaction."""
        old = self.original
        if (old is None or old.revision != expected_revision or record.session_id != old.session_id
            or record.question_ref != old.question_ref or record.created_at != old.created_at
            or record.revision != expected_revision + 1 or len(record.history) > len(old.history)
            or not record.history):
            raise SessionError('stored_state_invalid')
        changed_at = next((n for n, (before, after) in enumerate(zip(old.history, record.history))
                           if before != after), None)
        if changed_at is None or record.history[:changed_at] != old.history[:changed_at]:
            raise SessionError('stored_state_invalid')
        answer = record.history[changed_at]
        if (answer.question_id != old.history[changed_at].question_id
            or answer.sequence != changed_at + 1 or answer.revision != record.revision
            or record.history[changed_at + 1:]):
            raise SessionError('stored_state_invalid')
        replaced = self.connection.execute('''UPDATE answers SET question_id=?,selected_option_ids_json=?,question_snapshot_json=?,
            selected_option_snapshots_json=?,answered_at=?,revision=? WHERE session_id=? AND answer_order=?''',
            (answer.question_id, json.dumps(answer.selected_option_ids), json.dumps(answer.question_snapshot, ensure_ascii=False),
             json.dumps(answer.selected_option_snapshots, ensure_ascii=False), answer.answered_at, answer.revision,
             record.session_id, answer.sequence))
        if replaced.rowcount != 1:
            raise SessionError('stored_state_invalid')
        self.connection.execute('DELETE FROM answers WHERE session_id=? AND answer_order>?',
                                (record.session_id, answer.sequence))
        changed = self.connection.execute(
            'UPDATE sessions SET status=?,current_question_id=?,revision=?,updated_at=? WHERE session_id=? AND revision=?',
            (record.status, record.current_question_id, record.revision, record.updated_at, record.session_id, expected_revision))
        if changed.rowcount != 1:
            raise SessionError('revision_conflict')
        if self.repository._read(self.connection, record.session_id) != record:
            raise SessionError('stored_state_invalid')

    def commit(self):
        self.connection.commit()
        self.committed = True

    def __exit__(self, kind, value, traceback):
        try:
            if not self.committed:
                self.connection.rollback()
        finally:
            self.connection.close()
        if isinstance(value, sqlite3.Error):
            raise SessionError('storage_unavailable') from None
        return False
