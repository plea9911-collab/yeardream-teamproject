> 최신 배포 준비·측정·플랫폼 결정은 [DEPLOYMENT_BENCHMARK.md](DEPLOYMENT_BENCHMARK.md)를 확인하세요. 아래 배포 계획 일부는 준비 전 기록입니다.

# 팀 실행·저장·배포 안내

2026-10-23 기준. 현재는 로컬 실행이며 공동 접속 주소는 없습니다. 팀 서버·계정이 아직 없어 실제 배포는 진행하지 않았습니다.

## 지금 팀원이 실행하기

Python 3.12와 Git 설치 후 새 폴더에서:

```sh
git clone --branch codex/frontend-video-yolo https://github.com/plea9911-collab/yeardream-teamproject.git
cd yeardream-teamproject
```

기존 작업 폴더가 있다면 먼저 `git status`로 자신의 수정 파일을 확인합니다. 수정이 남아 있으면 덮어쓰거나 reset하지 말고 자기 브랜치에 보관합니다. 깨끗한 폴더에서:

```sh
git fetch origin
git switch codex/frontend-video-yolo
git pull --ff-only
```

macOS/Linux:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-video.txt
python tools/prepare_video.py
python app_server.py
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-video.txt
.\.venv\Scripts\python.exe tools\prepare_video.py
.\.venv\Scripts\python.exe app_server.py
```

브라우저: http://127.0.0.1:8010 . 서버 종료: 터미널 Ctrl+C. 이 주소는 각자 자신의 컴퓨터를 가리키며 다른 사람과 기록을 공유하지 않습니다. 기존 `.venv`가 있으면 다시 만들 필요 없이 설치 단계부터 진행합니다. 현재 변경은 PR #1 브랜치에 있으므로 main만 받으면 화면이 없습니다. Windows는 실행 안내만 제공했으며 실기기 검증은 macOS입니다.

## 무엇이 어디에 저장되는가

| 내용 | 기본 위치 | 성격 |
|---|---|---|
| 대화·선택 답변·질문 스냅샷·수정 번호 | runtime/webapp/sessions.sqlite3 | SQLite DB, 서버 재시작 후 유지 |
| 입력 영상·원본 JPEG·표시 JPEG | runtime/webapp/videos/작업ID/ | 파일 저장소, DB 안에 영상 바이트를 넣지 않음 |
| 처리 상태·시점·박스·모델 점수 | 같은 폴더 job.json | 영상 작업 기록 |
| 마지막 세션/작업 ID | 브라우저 localStorage | 재접속용 표시 정보, 답변 원본이 아님 |
| YOLO 가중치 | models/yolo26n.pt | 설치 때 받는 모델, Git 제외 |

runtime과 DB·영상·모델은 Git에 올라가지 않습니다. GitHub push는 기록 백업이 아닙니다. 브라우저 저장소를 지우면 기존 기록은 서버에 남지만 현재 UI에는 과거 기록 목록이 없어서 자동 재연결하지 못합니다. 로그인과 사용자별 접근 권한도 아직 없습니다.

## 백업과 복원

DB만 백업(실행 중에도 SQLite backup API로 일관된 복사본 생성):

```sh
python tools/backup_webapp.py
```

기본 결과는 `runtime/backups/sessions-UTC시각.sqlite3`. 세션/답변 개수와 integrity=ok를 출력합니다. 기존 백업을 덮어쓰지 않습니다. **영상과 사진은 이 명령에 포함되지 않습니다.** 디스크 고장에 대비하려면 별도 보관 장소에 백업을 복사해야 합니다.

전체 기록 보관: 새 요청을 멈추고 진행 중 분석이 끝난 후 서버를 Ctrl+C로 종료합니다. `runtime/webapp` 폴더 전체(DB+videos)를 다른 날짜별 백업 폴더로 복사합니다. 사용한 Git 커밋과 질문 데이터 버전도 함께 기록합니다. 자동 삭제/주기 백업은 아직 없습니다.

복원 검증은 원래 폴더를 덮어쓰지 말고 백업을 별도의 `runtime/restore-check` 폴더로 복사한 뒤 다음처럼 실행합니다.

```sh
python app_server.py --runtime runtime/restore-check --port 8011
```

DB만 복원했다면 영상 결과는 복원되지 않습니다. 브라우저 원래 세션 ID를 모르면 기존 기록은 화면에서 자동으로 나오지 않습니다. 데이터 접근 검증은 동일 질문 데이터/코드 버전의 세션 API로 수행합니다. 다른 기기로 옮길 때에는 DB 내부 질문 파일 경로와 해당 기기의 데이터 경로 호환성도 확인해야 합니다.

## 배포 추천안 — 아직 구현·배포하지 않은 계획

소규모 팀 시연은 **Python 서버 한 대 + 영구 디스크 한 개**부터 시작합니다. 화면/API/YOLO를 같은 서버에 두고 SQLite와 영상을 영구 디스크에 저장하면 현재 코드 변경을 최소화할 수 있습니다. YOLO 분석은 현재처럼 한 번에 1건, 대기 포함 2건으로 제한합니다. 지금은 프로세스 안에 대기열이 있으므로 여러 서버/여러 프로세스로 늘리면 안 됩니다.

예상 구성: 팀원 → HTTPS/팀 접근 인증 → 운영용 Python 서버 → SQLite·영상 영구 디스크. 현재 app_server.py는 127.0.0.1만 허용하는 개발 서버입니다. 포트만 공개하거나 임시 터널을 여는 방식으로 배포하지 않습니다.

서버 확정 후 작업:
1. 서비스 계정/지역/요금 한도와 팀 전용 사용 범위를 결정합니다. 지금은 유료 리소스를 생성하지 않았습니다.
2. 운영용 WSGI 서버와 단일 분석 작업자를 구성합니다. 허용 호스트·HTTPS 원본 검증을 배포 주소에 맞춰 명시하고 현재 로컬 제한을 무조건 해제하지 않습니다.
3. 로그인 또는 팀 접근 제한을 적용합니다. 공개 사용을 받으려면 세션·영상 소유권 검사를 추가해야 합니다. ID만 아는 사람이 자료를 조회하는 현재 방식을 그대로 공개하지 않습니다.
4. `--runtime`을 영구 디스크로 지정합니다. 모델 파일은 설치/시작 과정에서 준비하며 실행 데이터와 분리합니다.
5. 200MB 업로드 제한, 프록시 시간 제한, 디스크 여유/보관 기간·삭제, 별도 백업을 구성합니다.
6. 재배포/서버 재시작 뒤 문답과 JPEG가 남는지, 백업으로 복원 가능한지, 동시 2건과 세 번째 요청 거절이 동작하는지 검사합니다.

서버 후보로 Render 유료 Web Service+Persistent Disk 등을 검토할 수 있으나, 아직 선택하지 않았습니다. 무료/일시 파일시스템에 DB를 두면 재배포·재시작 시 사라질 수 있습니다. CPU·메모리 용량은 샘플 실제 부하를 측정한 뒤 정하며 지금 비용이나 속도를 보장하지 않습니다. 사용량이 늘 때 PostgreSQL과 별도 파일 저장 서비스, 외부 작업 대기열로 분리합니다.

근거:
- [Python wsgiref 공식 문서: 운영 환경용 권장 아님](https://docs.python.org/3/library/wsgiref.html)
- [SQLite backup API](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup)
- [Render 영구 디스크와 기본 일시 파일시스템](https://render.com/docs/disks)

## 이번 최적화와 검증

영상 검사 중 같은 정수 진행률을 반복 저장하던 부분을 바꿔, 진행률이 바뀔 때만 job.json을 갱신합니다. 프레임 검사·탐지 기준·저장 결과는 유지합니다. 이 변경은 불필요한 디스크 쓰기를 줄이는 것이며 탐지 속도가 몇 배 빨라졌다는 성능 측정 결과는 아닙니다.

검증: 기존 문답26개+연결/백업9개 통과. 동일 진행률 중복 쓰기 방지, 백업에서 실제 세션 재조회, 백업 덮어쓰기 거절, 없는 DB를 실수로 생성하지 않음을 검사했습니다. 로컬 실제 DB도 세션2개/답변8개 백업하고 무결성 검사를 통과했습니다. 이 수치는 해당 시점의 테스트 기록입니다.
