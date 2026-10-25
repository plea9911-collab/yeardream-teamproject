# 팀 실행 시작점

현재 범위는 [최신 작업 계획](docs/CURRENT_PLAN.md)과 [제출 MVP](docs/MVP.md)를 먼저 읽습니다. 2026-10-25 사용자 결정으로 법규·판례는 JSON 정확조회, 비율·해설은 협회 저장 자료, 영상은 첫 차량 감지 장면을 사용합니다. RAG·실시간 검색·AI 생성·사고 전용 모델 학습은 이번 제출에서 제외합니다.

## 화면과 영상 기능 실행

질문 선택 → 영상 첨부 → YOLO 차량 감지 → 사진 및 사고유형별 기본 비율·해설·법규·판례를 확인합니다. 차량이 검출되지 않아도 저장 자료는 별도로 제공합니다.
**[화면·영상 실행 안내](docs/FRONTEND_VIDEO.md)**를 따라 Python 3.12 환경과 모델을 준비한 뒤 `python app_server.py`를 실행하고 http://127.0.0.1:8010 을 엽니다.
차량 감지 사진으로 사고 순간이나 과실을 판단하지 않습니다. 비율은 자료의 차량 A/B에 대한 협회 기본 비율이며 내 차·상대 차로 지정하지 않습니다. 기존 문답 핵심 코드와 PIN은 유지합니다. 새 결과 조회에는 외부 검색·모델·추가 패키지가 필요하지 않습니다. 기존 영상 실행 환경은 화면·영상 안내를 따릅니다.

---

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
