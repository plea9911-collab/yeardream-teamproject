# 팀 공유 인수인계 (세션09)

저장소 루트에서 Python 3.12 표준 라이브러리 `sqlite3`, `wsgiref`로 실행한다. 외부 패키지 설치는 필요 없다. 개발용 로컬 WSGI 서버이며 실험 계약의 팀 채택과 공통 서버 통합은 미확정이다. 먼저 루트 README를 읽고 아래 새 DB 절차를 따른다.

## 지원 범위

| 자료 | 버전/계약 | 데이터 범위 |
|---|---|---|
| 기본 v1 | knia-rep-v1-9aaf88ec211ea3ab / experimental.questions.1 | 질문5, 선택23, 미수집18, 완료1 |
| 명시 v2 | knia-car-v2-dd12c7da4fc9b210 / experimental.questions.2 | 질문51, 선택160, 종료108, 범위밖 미수집2 |

v1 SHA256: `ccbd797a539f763e6d9ecb9294b9fe03c83acf7b95518e521313bcb5c2b9daff`

v2 SHA256: `48c4f7359adecf1f92f2f6ae16d1c2a64fa57856f59b0f2221ff6a40a89494c9`

두 질문 JSON은 수집 산출물의 바이트 동일 사본이다. `.gitattributes`의 `*.json -text`를 유지한다. v2는 `outputs/session07_collection/runs/live_final/datasets/knia-car-v2-dd12c7da4fc9b210/`에 있으며 source_mapping/uncollected도 함께 제공한다. 계약은 `docs/contracts/experimental.questions.2.json`, v1 계약은 `outputs/session03_representative/experimental_contract.json`이다. `docs/evidence/session07_input.snapshot.json`은 당시 포인터 사본으로 session08_started=false는 과거 상태다. knia-car-v1-* 중간 번들은 최종 입력으로 사용하지 않는다.

런타임 로더는 고정 SHA의 `questions.json`만 읽는다. 같은 폴더의 `source_mapping.json`과 `uncollected_branches.json`은 검토·감사용 사본이며 실행 필수 파일이 아니다. 계약 파일의 `session08_input.json` 표기는 당시 외부 감사 입력 포인터다. 현재 공유 실행에는 해당 파일이 필요 없으며, 명시 v2 registry는 `tools/team_check.py`의 `REGISTRY`를 사용한다.

기본 PIN은 v1이다. 저장 session의 question_ref(경로·SHA·버전·계약)는 immutable이다. 데이터 이름/경로를 바꾸거나 저장 세션을 새 버전으로 치환하지 않는다. 기본 main CLI는 v1 registry만 사용하므로 v2 DB를 기본 서버에 연결하지 않는다.

## 기본 v1 새 DB 실행

PowerShell에서 저장소 루트로 이동한 뒤 실행한다. `python --version`으로 3.12를 확인한다. 아래 설정은 개인 settings.json을 사용하지 않는다.

```powershell
$env:PYTHONUTF8='1'
$run = "runtime/handoff/v1-$([guid]::NewGuid().ToString('N').Substring(0,12))"
New-Item -ItemType Directory -Path $run -ErrorAction Stop | Out-Null
[IO.File]::WriteAllText((Join-Path (Get-Location) "$run/settings.json"), '{"contract_status":"experimental","question_root":"../../..","database":"sessions.sqlite3"}', (New-Object Text.UTF8Encoding $false))
python -B -X utf8 main.py --config "$run/settings.json" --init-db
python -B -X utf8 main.py --config "$run/settings.json" --port 8000
```

위 설정 생성 명령은 Windows PowerShell 5와 PowerShell 7 모두 BOM 없는 UTF-8로 저장한다. 설정 로더는 UTF-8 BOM을 처리하지 않으므로 BOM을 붙이는 저장 방식으로 바꾸지 않는다.

main.py의 상대경로는 **config 파일의 부모** 기준이다. 위 위치에서 `../../..`은 저장소 루트, DB는 새 설정과 같은 폴더다. 기본 실행은 로컬 settings.json이 있으면 우선하므로 기존 사용자 PC에서는 반드시 `--config`를 명시한다. 새 checkout에서만 `settings.example.json`을 참고해 자신만의 새 DB 설정을 만들 수 있다. 기존 DB에는 --init-db를 검증 목적으로 실행하지 않는다. 서버 종료는 Ctrl+C다.

## 명시 v2 실험 서버와 검증

```powershell
python -B -X utf8 tools/team_check.py serve --port 8008
python -B -X utf8 tools/team_check.py verify
```

serve는 매번 `runtime/handoff/<UUID>/sessions.sqlite3`를 새로 만들고 v1/v2 명시 registry를 사용한다. 출력된 DB 경로를 보관한다. 재시작은 `python -B -X utf8 tools/team_check.py serve --database '<출력 DB>' --port 8008`이다. 이 경우 파일을 초기화하지 않으며 runtime/handoff 안의 기존 파일만 허용한다. 운영 PIN/settings/schema는 변경하지 않는다.

verify는 매번 새 전용 폴더에 DB·상대경로 config·HTTP 요청/응답·verification.json을 저장한다. v1/v2 대표 서비스 완료, 기본 CLI v1/명시 v2 HTTP, 미수집, 수정·재완료·no-op/stale409, 공개 history, 프로세스 재시작과 내부 context 복원을 검사한다. 원본 raw 없이 동작하는지 검증하며 외부 수집 요청은 없다. 필요할 때만 `verify --all-paths`로 실제 서비스/SQLite v2 108종료 경로를 추가 재생할 수 있다. HTTP 전수가 아니며 세션09 기본 검증에서는 전수를 반복하지 않았다.

## HTTP 사용 예시

명시 v2 서버를 켠 다른 터미널에서 시작·조회·답변한다. 기본 v1 서버는 base를 8000, version을 v1 값으로 바꾼다.

```powershell
$base='http://127.0.0.1:8008'
$a=Invoke-RestMethod -Method Post -Uri "$base/sessions" -ContentType 'application/json' -Body '{"question_schema_version":"knia-car-v2-dd12c7da4fc9b210"}'
$sid=$a.session_id
$a=Invoke-RestMethod -Uri "$base/sessions/$sid"
$body=@{question_id=$a.current_question_id;selected_option_ids=@('o_2');expected_revision=$a.revision} | ConvertTo-Json
$a=Invoke-RestMethod -Method Post -Uri "$base/sessions/$sid/answers" -ContentType 'application/json' -Body $body
# 아래는 자동 검증용 대표 선택이다. 실제 사용자는 current_question.options의 ID를 고른다.
while ($a.status -eq 'in_progress') {
  $o=$a.current_question.options | Where-Object collection_status -eq 'verified' | Select-Object -First 1
  $body=@{question_id=$a.current_question_id;selected_option_ids=@($o.option_id);expected_revision=$a.revision} | ConvertTo-Json
  $a=Invoke-RestMethod -Method Post -Uri "$base/sessions/$sid/answers" -ContentType 'application/json' -Body $body
}
$a.status; $a.next_action; $a.message
# 동일 선택 수정 예시: changed=false, revision 유지
$last=$a.history[-1]
$body=@{selected_option_ids=@($last.selected_option_ids);expected_revision=$a.revision} | ConvertTo-Json
$edit=Invoke-RestMethod -Method Put -Uri "$base/sessions/$sid/answers/$($last.question_id)" -ContentType 'application/json' -Body $body
$a=Invoke-RestMethod -Uri "$base/sessions/$sid"
```

완료 endpoint는 없다. 마지막 명시 `complete` 분기를 답변할 때 `status=completed`, `next_action=upload_video`, 첨부 안내를 반환한다. 실제 업로드 기능은 없다. 실제 분기 수정은 history에 저장된 question_id를 PUT 경로에 쓰고 해당 문항의 **다른 verified 선택 ID**와 최신 revision을 보낸다. 후속 답변이 삭제되고 반환 상태에 따라 새 문항에 답하여 재완료한다. 루트 o_1/o_3는 미수집으로 422다. 검증 결과 verification.json의 http 배열에 실제 변경·재완료 요청/응답도 저장한다.

## 내부 get_context

HTTP context endpoint는 없다. 완료 세션에 대해서만 동일 DB와 registry로 내부 메서드를 사용한다. 다음 코드는 저장소 루트에서 실행한다.

```python
from pathlib import Path
from tools.team_check import service
database = Path('runtime/handoff/<출력 UUID>/sessions.sqlite3')
context = service(database).get_context('<완료 session_id>')
print(context)
```

또는 `python -B -X utf8 tools/team_check.py context --database '<출력 DB>' --session-id '<완료 ID>'`. 내부 context에는 provenance·상대 원본 경로가 포함되므로 공개 응답으로 그대로 노출하지 않는다. GET 공개 history에는 내부 source metadata/파일경로가 없다. context 소비자는 session_id/revision/question_schema_version을 함께 보관하고 사용 직전 최신 revision을 확인하여 낡은 결과를 폐기한다. GET/get_context는 읽기 전용이다.

## 오류와 저장 정책

save는 append 전용, 수정은 별도 transaction.revise이다. 실제 수정은 답변 교체·후속 삭제·상태 갱신·revision+1을 한 SQLite 트랜잭션에서 처리한다. answer_order는 남은 답변 순서이고 revision은 변경 버전이므로 서로 같다고 가정하지 않는다. 동일 선택 집합 수정은 changed=false이며 DB 쓰기가 없다. stale revision은 같은 선택이어도409다. 실패는 기존 상태를 보존하며 미수집/오류/규칙 누락을 완료로 만들지 않는다.

| HTTP | 의미 |
|---|---|
| 201 / 200 | 시작 / 조회·답변·수정 성공 |
| 422 | JSON·필드·타입·선택수·중복·알 수 없는 선택·미수집·등록되지 않은 버전 |
| 404 | 없는 세션/수정할 미답변/없는 route |
| 405 / 415 | 메서드 / Content-Type 오류 |
| 409 | revision_conflict, question_mismatch, session_completed |
| 503 | storage_unavailable (새 DB 초기화와 접근권한 확인) |
| 500 | 질문 파일·PIN·분기·저장 무결성 오류; 자동 대체 금지 |

차량 내 차/상대 차, A·B, 신호 대응은 미확인이다. source_dN_text는 선택한 원문이며 원천 비율을 사용자 차량에 임의 배정하지 않는다. 실제 데이터는 single/min1/max1만 지원한다.

## 재현 가능 범위와 별도 감사 자료

저장소만으로 새 DB 문답 API, 내부 context, 공유 smoke, 선택적 서비스108경로를 실행할 수 있다. 질문 JSON의 source_ref는 근거 **참조**이며 로더가 raw 파일을 열어 감사하지 않는다. 따라서 동작 검증 통과가 원천 재감사 완료를 뜻하지 않는다.

전체 수집·원본 행/문자구간·POST 교환·checkpoint/manifest 감사와 세션08의 과거 합성/장애 전체 suite 재현에는 별도 문서 아카이브가 필요하다. `docs/evidence/external_audit_manifest.json`에 파일별 상대경로·바이트 수·SHA·용도를 기록했다. 별도 아카이브 루트 아래 동일 상대경로로 제공하고 SHA를 대조한다. 정확한 보관 절대경로는 제공자의 세션09 `external_archive_location.json`에 있다. 별도 자료 전달 자체와 팀원 PC의 전체 감사 실행은 미확인이다. DB·캐시를 전달하지 않는다. 기존 수집기를 실행하면 checkpoint/과거 결과를 바꿀 수 있으므로 복사본과 새 출력 위치를 준비해야 하며 이 저장소는 외부 수집을 자동 실행하지 않는다.

세션08 과거 실적은 `docs/evidence/session08_historical.json`에 명시적으로 분리했다. 그 안의 개인 절대 DB 경로는 과거 실행 위치를 기록한 값이며 현재 실행 입력이나 전달할 DB가 아니다. 공유 검증의 통과 범위는 문답 실행이며, 별도 감사용 사본 전체의 존재·SHA 검증이나 원본 재감사를 포함하지 않는다. v2 108경로는 실제 서비스/SQLite 전수이고 HTTP는 대표 경로·수정·재완료다. 저장 myaccident1 차대차 후보 대조는 협회 전체 완전성을 의미하지 않는다. 복수 선택·일부 장애 검사는 합성 fixture이며 실제 데이터 지원 또는 디스크/전원 장애 검증이 아니다. 과거 cb19c110/미커밋 기록은 이후 6451f94 커밋 전 스냅샷이다.

팀이 결정할 것은 실험 계약 채택, 후속 담당자 인터페이스, 차량 역할/신호 매핑 근거, 전체 사이트 수집 범위와 공유/보관 방식이다. 운영 PIN 전환·배포·프론트·영상·과실검색·RAG·AI해설은 이번 범위에서 실행하지 않았다.
