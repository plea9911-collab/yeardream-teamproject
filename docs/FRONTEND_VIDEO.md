# 화면 · 영상 업로드 · 차량 감지 (은미 담당)

기존 문답 서버와 질문 데이터를 변경하지 않고 `app_server.py`에서 화면과 영상 API를 추가했습니다. 로컬 개발·팀 시연용입니다. 인증 없는 개발 서버이므로 공용 인터넷에 노출하지 않습니다. 실행은 `127.0.0.1`만 허용합니다.

## 실행 (Python 3.12)

저장소 루트에서 실행합니다. 기존 문답 전용 `requirements.txt`는 그대로이며 영상 기능만 별도 설치합니다.

macOS / Linux:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-video.txt
python tools/prepare_video.py
python app_server.py
```

Windows PowerShell (스크립트 실행 정책을 바꿀 필요 없음):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-video.txt
.\.venv\Scripts\python.exe tools\prepare_video.py
.\.venv\Scripts\python.exe app_server.py
```

브라우저에서 http://127.0.0.1:8010 을 엽니다. 포트 변경은 `--port 8011`, 모델 경로 지정은 `--model 모델경로`입니다. 종료는 Ctrl+C. 2026-10-25 Windows에서도 CPU 전용 패키지·공식 모델 준비와 1초 합성 검은 영상의 no_detection을 확인했습니다. 실제 주행 영상의 차량 검출 성능·속도를 재평가한 것은 아닙니다.

`prepare_video.py`는 Ultralytics가 배포하는 공식 YOLO26n 모델을 내려받아 확인합니다. 최초 설치·모델 준비에는 인터넷이 필요하지만, 앱의 문답·영상 처리는 로컬에서 실행합니다. 모델·입력 영상·사진·DB·개인 설정은 Git에 올리지 않습니다. 모델과 패키지의 라이선스는 해당 배포자의 조건을 따릅니다.

## 화면 사용

1. 시작 → 차 대 차 → 상황·상세 상황·진행 방향 선택.
2. 답변은 기존 SQLite 기능으로 저장됩니다. ‘지금까지 선택한 답변’에서 수정할 수 있습니다.
3. 문답 완료 후 영상 선택 → 미리보기 → ‘차량 인식하고 사진 저장’.
4. 전송·분석 상태가 표시되고, 완료되면 원본/네모 표시 사진을 각각 저장합니다.
5. 새로고침하면 마지막 대화와 영상 작업을 복원합니다. 새 대화는 기존 기록을 삭제하지 않습니다.

현재 미수집인 차 대 사람/차 대 자전거 선택지는 비활성화합니다. v2를 이 추가 실행 파일에서 명시적으로 선택하며, 기존 `main.py`의 기본 v1 PIN과 기존 API는 바꾸지 않습니다. 차량 A/B와 내 차의 대응을 임의로 확정하지 않습니다.

## 정확한 영상 기능 범위

- MP4/MOV/AVI/MKV/WebM, 최대 200MB·120초·4K. 실제 디코딩 가능 여부도 검사합니다. H.264 MP4 권장.
- CPU YOLO26n, car/motorcycle/bus/truck, 모델 점수 0.5 이상.
- 약 0.5초 간격의 프레임 중 **처음 차량이 감지된 프레임**에서 종료합니다. 원본과 표시 사진, 시각·박스 좌표·분류·점수를 저장합니다.
- 차량을 못 찾으면 `no_detection`; 가짜 사진이나 결과를 만들지 않습니다.
- **사고 순간 탐지·충돌 판정·차량 이동 추적·과실 산정 기능이 아닙니다.** 사고 데이터셋으로 추가 학습하지 않았습니다.
- 대기 포함 최대 2건, 실제 분석 1건씩. 서버 재시작 중이던 작업은 실패 상태로 바꿔 재첨부를 안내합니다.
- 답변 revision이 달라지면 이전 영상 결과와 이미지 조회를 409로 거절합니다. 같은 선택의 수정(no-op)은 기존 결과 유지.

## 팀 연결 계약

기존 `/sessions` API는 그대로입니다. `POST /sessions`의 v2 버전은 `/app-config`에서 받습니다.

| 경로 | 동작 |
|---|---|
| GET `/app-config` | 질문 버전, 업로드 제한, 모델 준비 여부 |
| POST `/video-jobs?session_id=...&revision=...&filename=clip.mp4` | Content-Type: application/octet-stream, 원본 파일 바이트. 완료된 최신 세션만 수락. 202와 job_id 반환 |
| GET `/video-jobs/{job_id}` | uploading/queued/processing/completed/no_detection/failed 상태와 진행률 |
| GET `/video-jobs/{job_id}/detected.jpg` | 차량 네모 표시 사진 |
| GET `/video-jobs/{job_id}/original.jpg` | 같은 장면의 원본 사진 |
| GET `/video-jobs/{job_id}/result` | 완료 문답과 업로드 revision 확인 후 저장된 협회 A/B 비율·기본 해설·법규·판례 반환. 영상 처리가 종료된 뒤 사용 |

작업 결과에는 session_id/revision이 포함됩니다. 서버 내부 get_context의 검증된 chart_no로 data/accident_cases.json과 data/legal_references_by_chart.json을 조회합니다. 저장된 협회 A/B 비율·기본 해설과 PDF 원문·페이지·출처를 표시합니다. 31개 도표는 제공 PDF에 판례가 없어 빈 결과로 안내합니다. 답변 수정 시 결과도 409로 거절하며 영상 미검출·실패와 문답 기반 결과는 분리합니다. 실시간 검색·RAG·AI 생성은 수행하지 않습니다. 최신 범위는 [현재 작업 계획](CURRENT_PLAN.md)을 따릅니다.

## 저장과 재시작

기본 `runtime/webapp/sessions.sqlite3`, `runtime/webapp/videos/{job_id}/` 아래 입력 영상·job.json·사진을 보관합니다. 재실행 시 같은 DB를 사용합니다. 별도 시연 기록은 `--runtime runtime/다른이름`으로 분리합니다. 서버 종료 후 필요 없는 해당 runtime 폴더를 직접 정리할 수 있습니다. 자동 삭제·보존기간·사용자 인증은 구현 범위 밖입니다.

## 검증

```sh
python -B -X utf8 tools/team_check.py verify
python -m unittest discover -s tests -v
node --check web/app.js
python tests/video_smoke.py /경로/차량이보이는영상.mp4
```

2026-10-23 macOS CPU에서 수행:
- 기존 문답 검증 26개 통과. 질문 데이터/PIN·기존 핵심 코드 수정 없음.
- 추가 연결 테스트 6개 통과: 화면/기존 API, 업로드 제한·미완료/오래된 세션 거절, 사진 저장·답변 수정 시 무효화, 서버 재시작 처리 테스트.
- 수업 저장소 실제 `YOLO/sample.mp4`를 사용해 차량 5대 감지, 0.00초 원본/네모 표시 JPEG 저장 확인. 이는 이 샘플의 결과이며 일반 정확도 평가가 아닙니다.
- 실제 YOLO로 검은 영상의 no_detection, 손상 파일 거절 확인.
- 브라우저에서 문답 4단계→영상 선택/미리보기→업로드→처리→차량 사진 확인, 다운로드 파일 저장 확인. 새로고침 복원 및 390px 화면 가로 넘침 없음 확인.

수업 코드 참고: https://github.com/iciaGit/yeardream2026/tree/main/YOLO/basic
수업 샘플(저장소에 재배포하지 않음): https://github.com/iciaGit/yeardream2026/blob/main/YOLO/sample.mp4
YOLO 결과 사용법: https://docs.ultralytics.com/modes/predict/


## 화면 개선 및 재확인 (2026-10-23)

- 상단 3단계 진행 표시, 질문 한 화면씩 선택 → 다음 버튼으로 제출. 일부 어려운 선택지에 쉬운 풀이를 추가했으며 원래 질문/선택지와 분기 ID는 보존했습니다.
- 영상 첨부 전에 선택한 답변을 펼쳐 검토·수정합니다. 기존 수정/복원/영상 무효화 규칙을 유지합니다.
- 결과는 큰 사진과 장면 정보로 구성합니다. ‘차량 표시 / 원본’ 버튼은 같은 프레임의 이미지를 전환합니다.
- ‘사진 확대’는 별도 대화상자를 열고 화면에 맞춤부터 최대 4배까지 확대·축소합니다. 확대 화면에서도 원본 전환이 가능하며 스크롤로 사진을 이동합니다. Esc 또는 닫기로 돌아오면 확대 버튼에 키보드 초점이 복원됩니다.
- 모델 점수는 ‘인식 정보 자세히 보기’ 안에 둡니다. 사고 순간·과실비율로 표시하지 않습니다.

재검증: 기존 26개, 연결 테스트 6개, JS 구문 검사 통과. Chrome에서 4문답을 선택/다음으로 제출하고 실제 수업 영상을 다시 업로드해 5대와 두 JPEG를 확인했습니다. 원본 이미지 경로 전환, 확대 전후 폭 438.75→877.5px(2배), Esc 초점 복원, 사진 다운로드, 같은 답변 수정 시 결과 유지, 새로고침 복원을 확인했습니다. 390px 화면에서 문서 폭도 390px이며 모바일 확대·비교·닫기 동작을 확인했습니다. 모바일 실기기 테스트는 수행하지 않았습니다.

설계 참고: [KNIA 단계별 상황 선택](https://accident.knia.or.kr/myaccident1), [Progressive 사진 안내](https://www.progressive.com/claims/faq/guided-photo/), [FiftyOne 이미지 검토](https://docs.voxel51.com/user_guide/app.html). 공식 사이트의 이미지나 문구를 복제하지 않고 흐름과 사진 검토 방식을 참고했습니다.

## 팀 공유·저장·배포

브랜치 받기, DB/영상 저장 위치, 백업 명령, 배포 전 남은 작업은 [DEPLOYMENT_STORAGE.md](DEPLOYMENT_STORAGE.md)를 참고하세요. 현재 공동 서버에 배포한 상태는 아닙니다.
