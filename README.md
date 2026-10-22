# Experimental session backend (sessions 04–06)

Python 3.12 standard library WSGI + SQLite. Team contract not established.
Python 3.12 standard library only; no package installation required.

Initialize the dedicated DB explicitly:
`python -B main.py --init-db`

Run locally:
`python -B main.py --port 8000`

POST /sessions with application/json:
`{"question_schema_version":"knia-rep-v1-9aaf88ec211ea3ab"}`

GET /sessions/{session_id}

See the session04_session_start README in the document workspace for full
repository, transaction, error and verification handoff. This is a local
development server; team FastAPI integration remains a future decision.

## Session 05 experimental extension

POST /sessions/{id}/answers (application/json), exact body fields:
`{"question_id":"q_knia_d0_root","selected_option_ids":["o_2"],"expected_revision":0}`
ID comes from the path; client labels/conditions are rejected. Success: 200.
Existing start/get envelope remains experimental.sessions.1; new submission
contract is experimental.answers.1 (draft, not team adopted). Stored snapshot history is server-owned with pinned provenance; public history
projects question/option text and IDs without internal source metadata. Context is internal only:
`SessionService(loader, repository).get_context(session_id)` using
experimental.accident_context.1. No context HTTP route is registered.

BEGIN IMMEDIATE, current-state/revision validation, snapshot INSERT, conditional
session UPDATE with rowcount=1, readback, explicit commit use one connection.
Every other transaction exit rolls back. Factory: repository.transaction().
save(record, expected_revision) is append-only and adds exactly one answer.
Session06 implements editing through the separate revise method; revision is
independent of history length. Do not reuse save for edits.

## Session 06 experimental revision extension

`PUT /sessions/{id}/answers/{question_id}` accepts the exact JSON body
`{"selected_option_ids":[...],"expected_revision":N}`. It is an experimental
draft beside (not a change to) the existing session and answer envelopes.
The path question must already be stored. A stale revision is always 409, even
for equal selections. Equal selected sets return 200 with `changed:false` and
make no write. A changed selection replaces the server-built snapshot, deletes
all later answers, recalculates the next question or explicit completion, and
increments session revision once in one SQLite transaction. Cancellation is
the client making no PUT; there is no cancellation endpoint.

`answer_order` is the contiguous position in retained history. `revision` is a
monotonic session mutation version and need not equal history length. Answer
snapshot revisions are strictly increasing retained mutation revisions. Session
05 records remain valid because their answer revisions and history lengths are
equal. `SQLiteTransaction.save` remains append-only; `revise` owns replacement
and suffix deletion. Consumers of context/search results must bind
`session_id`, `revision`, and `question_schema_version`, then recheck the
latest revision immediately before use and discard a mismatched result.

Errors: 422 malformed request/type/count/duplicate/unknown option/uncollected;
404 missing session; 409 revision_conflict, question_mismatch, session_completed;
503 storage_unavailable; 500 routing/data/pin integrity errors. No implicit
completion or idempotency. All rejected submissions preserve prior state.
Completion returns upload_video and the Korean attachment prompt; video upload
itself is outside this backend's implemented scope.

Verification (from the document workspace, Python 3.12 standard library):
`python -B outputs/session05_answers/verify.py`
It creates a new dedicated verification DB each run and never resets runtime DB.
See outputs/session05_answers/README.md in that workspace for detailed handoff.

## Portable checkout setup

The default uses local settings.json when present, otherwise settings.example.json.
Relative paths resolve from the config file directory. Copy settings.example.json
to settings.json only if local overrides are needed; personal settings are ignored.

On a fresh checkout only, initialize your own empty runtime database:
`python -B main.py --init-db`
Then run `python -B main.py --port 8000`. Existing runtime databases are never
committed, reset, or replaced.

The exact pinned representative JSON and experimental question contract are
included under outputs/session03_representative. This covers five single-choice
questions, 23 options, 18 uncollected branches and one verified completion, not
the full dataset. Original provenance paths refer to separately retained capture
artifacts in the document workspace; those raw captures are not included here.

Session06 verification in that workspace passed: prior regression 116, revision
service/SQLite 82, actual HTTP 45, synthetic multiple/exception 60 checks.
Valid alternative branch changes are synthetic tests because each production
question currently has only one collected valid choice. No disk-fault or power-loss
testing is claimed.
