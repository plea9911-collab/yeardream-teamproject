# 문답 백엔드 — 팀 실행 시작점

Python 3.12 표준 라이브러리 sqlite3/wsgiref 기반 실험 백엔드입니다. 설치할 외부 패키지는 없습니다.

먼저 [팀 인수인계 및 실행 절차](docs/TEAM_HANDOFF.md)를 읽으세요. 새 DB·개인경로 없는 설정·기본 v1 실행·명시 v2 서버·HTTP 예시·내부 get_context·오류/revision 정책·원본 감사 한계를 안내합니다.

저장소 루트에서 공유 검증:

```powershell
python --version
$env:PYTHONUTF8='1'
python -B -X utf8 tools/team_check.py verify
```

매 실행 runtime/handoff/<UUID>에 새 DB와 verification.json을 생성합니다. 기존 DB와 개인 settings.json은 사용하지 않습니다. v1 기본 PIN을 유지하며 v2는 명시 registry의 실험 실행입니다. 팀 계약 채택과 차량 역할 대응, 협회 사이트 전체 완전성은 미확정입니다.

기본 v1은 main.py에 새 상대경로 config를 명시하여 실행합니다. 명시 v2 실험 서버는 `python -B -X utf8 tools/team_check.py serve --port 8008`입니다. 자세한 준비와 재시작 방법은 인수인계 문서를 따르세요.

질문 JSON은 v1/v2 SHA를 고정하고 바이트를 보존했습니다. runtime DB·캐시·개인 설정은 공유하지 않습니다. API 동작과 선택적 서비스108경로 검증은 저장소로 가능하지만 raw 원본 전체 감사에는 별도 아카이브가 필요합니다. 파일별 참조는 [외부 감사 manifest](docs/evidence/external_audit_manifest.json), 과거 검증 범위는 [세션08 역사 기록](docs/evidence/session08_historical.json)을 참조하세요. 과거 결과는 이번 실행 결과와 구분합니다.
