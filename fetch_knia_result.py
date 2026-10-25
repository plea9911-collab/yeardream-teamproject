
import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://accident.knia.or.kr"
API_URL = f"{BASE_URL}/selectMyAccidentPredictive"
DETAIL_URL = f"{BASE_URL}/myaccident-content"

DATA_DIR = Path("data")
CHARTS_FILE = DATA_DIR / "knia_charts.json"
OUTPUT_FILE = DATA_DIR / "accident_cases.json"
ERROR_FILE = DATA_DIR / "collection_errors.json"

# 처음에는 3개만 시험 수집해.
# 검증이 끝나면 None으로 바꾸면 전체 도표를 수집해.
MAX_CHARTS = None

# 요청을 너무 빠르게 반복하지 않도록 대기
REQUEST_DELAY = 0.4

SECTION_ALIASES = {
    "사고 상황": ["사고 상황"],
    "적용(비적용)": ["적용(비적용)", "적용 비적용"],
    "기본 과실 해설": ["기본 과실 해설"],
    "수정요소 해설": ["수정요소 해설"],
    "관련법규": ["관련법규", "관련 법규"],
    "판례/조정 사례": [
        "판례/조정 사례",
        "판례 / 조정 사례",
        "판례/조정사례",
        "판례·조정 사례",
        "판례 및 조정 사례",
    ],
}

SECTION_NAMES = list(SECTION_ALIASES.keys())

# 페이지 공통 영역 또는 다음 영역의 시작을 나타내는 문구
END_MARKERS = [
    "과실비율 알아보기",
    "관련 사이트",
    "유의사항",
    "개인정보처리방침",
    "손해보험협회",
    "교통사고 대응요령",
    "사고 직후 이렇게 하세요",
    "과실비율이 궁금하신가요",
    "혼자 고민하지 마세요",
    "현저한 과실",
    "중대한 과실",
]


def normalize_label(text: str) -> str:
    """제목 비교 시 공백과 구두점 차이를 줄인다."""
    return re.sub(r"[\s·ㆍ/()（）:：]", "", text).strip()


def clean_text(text: str) -> str:
    """연속된 공백과 빈 줄을 정리한다."""
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
    ]
    return "\n".join(line for line in lines if line)


def fetch_fault_ratio(chart_no: str) -> list[dict]:
    """공식 API에서 해당 도표의 과실비율을 가져온다."""
    response = requests.post(
        API_URL,
        data={
            "chartNo": chart_no,
            "numChk": "true",
        },
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": BASE_URL,
        },
    )
    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError("과실비율 API 응답이 리스트 형식이 아닙니다.")

    return data


def fetch_detail_page(chart_no: str) -> str:
    """공식 상세 페이지 HTML을 가져온다."""
    response = requests.get(
        DETAIL_URL,
        params={
            "chartNo": chart_no,
            "chartType": "1",
        },
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0",
        },
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding

    return response.text


def extract_detail_sections(html: str) -> dict[str, str]:
    """상세 페이지에서 제목별 내용을 추출한다."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in soup.get_text("\n").splitlines()
        if line.strip()
    ]

    normalized_lines = [
        normalize_label(line)
        for line in lines
    ]

    # 각 항목 제목이 실제로 등장하는 위치를 찾는다.
    section_positions = {}

    for section_name, aliases in SECTION_ALIASES.items():
        normalized_aliases = {
            normalize_label(alias)
            for alias in aliases
        }

        for index, line in enumerate(normalized_lines):
            if line in normalized_aliases:
                section_positions[section_name] = index
                break

    ordered_positions = sorted(
        (position, name)
        for name, position in section_positions.items()
    )

    sections = {name: "" for name in SECTION_NAMES}

    for position_index, (start, section_name) in enumerate(
        ordered_positions
    ):
        if position_index + 1 < len(ordered_positions):
            end = ordered_positions[position_index + 1][0]
        else:
            end = len(lines)

        # 다음 항목 제목을 찾지 못한 경우에도
        # 페이지 하단 공통 영역이 섞이지 않도록 종료 지점을 찾는다.
        for index in range(start + 1, end):
            normalized_line = normalized_lines[index]

            if any(
                normalize_label(marker) in normalized_line
                for marker in END_MARKERS
            ):
                end = index
                break

        content = clean_text("\n".join(lines[start + 1:end]))
        sections[section_name] = content

    return sections


def fetch_accident_case(chart_no: str, chart_name: str = "") -> dict:
    """도표 하나의 과실비율과 상세 설명을 구성한다."""
    results = fetch_fault_ratio(chart_no)

    if not results:
        raise ValueError(
            f"{chart_no}: 과실비율 API 결과가 비어 있습니다."
        )

    result = next(
        (
            item for item in results
            if item.get("chartNo") == chart_no
        ),
        results[0],
    )

    html = fetch_detail_page(chart_no)
    sections = extract_detail_sections(html)

    detail_url = (
        f"{DETAIL_URL}?"
        f"{urlencode({'chartNo': chart_no, 'chartType': '1'})}"
    )

    related_laws = (
        [{"content": sections["관련법규"]}]
        if sections["관련법규"]
        else []
    )

    precedents = (
        [{"content": sections["판례/조정 사례"]}]
        if sections["판례/조정 사례"]
        else []
    )

    return {
        "chart_no": chart_no,
        "url": detail_url,
        "accident_type": (
            result.get("acdNtty")
            or chart_name
            or ""
        ),
        "fault_ratio": {
            "A": result.get("fltRtA"),
            "B": result.get("fltRtB"),
        },
        "accident_situation": sections["사고 상황"],
        "application_criteria": sections["적용(비적용)"],
        "basic_fault_explanation": sections["기본 과실 해설"],
        "adjustment_explanation": sections["수정요소 해설"],
        "related_laws": related_laws,
        "precedents_and_mediation": precedents,
        "collection_status": {
            "accident_situation": bool(sections["사고 상황"]),
            "application_criteria": bool(
                sections["적용(비적용)"]
            ),
            "basic_fault_explanation": bool(
                sections["기본 과실 해설"]
            ),
            "adjustment_explanation": bool(
                sections["수정요소 해설"]
            ),
            "related_laws": bool(related_laws),
            "precedents_and_mediation": bool(precedents),
        },
    }


def load_json(path: Path, default):
    """JSON 파일을 읽는다. 파일이 없으면 기본값을 반환한다."""
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data) -> None:
    """JSON 파일을 UTF-8로 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def save_case(record: dict) -> None:
    """도표 번호가 같으면 갱신하고, 없으면 추가한다."""
    records = load_json(OUTPUT_FILE, [])

    records = [
        item for item in records
        if item.get("chart_no") != record["chart_no"]
    ]

    records.append(record)
    save_json(OUTPUT_FILE, records)


def main():
    if not CHARTS_FILE.exists():
        print(f"도표 목록 파일을 찾을 수 없습니다: {CHARTS_FILE}")
        return

    charts = load_json(CHARTS_FILE, [])

    if not isinstance(charts, list):
        print("knia_charts.json은 JSON 리스트 형식이어야 합니다.")
        return

    # knia_charts.json의 실제 키는 chartNo와 name이다.
    valid_charts = []

    for chart in charts:
        chart_no = chart.get("chartNo") or chart.get("chart_no")

        if chart_no:
            valid_charts.append({
                "chart_no": chart_no,
                "name": chart.get("name", ""),
            })

    # 같은 도표 번호가 여러 번 있으면 한 번만 처리한다.
    unique_charts = {}
    for chart in valid_charts:
        unique_charts[chart["chart_no"]] = chart

    chart_list = list(unique_charts.values())

    if MAX_CHARTS is not None:
        chart_list = chart_list[:MAX_CHARTS]

    errors = load_json(ERROR_FILE, [])
    total = len(chart_list)
    succeeded = 0
    failed = 0

    print(f"수집 대상 도표: {total}개")
    print(f"저장 파일: {OUTPUT_FILE}")
    print("-" * 50)

    for index, chart in enumerate(chart_list, start=1):
        chart_no = chart["chart_no"]
        chart_name = chart["name"]

        print(f"[{index}/{total}] {chart_no} 수집 중...")

        try:
            record = fetch_accident_case(
                chart_no,
                chart_name,
            )

            save_case(record)
            succeeded += 1

            status = record["collection_status"]
            print(
                f"  과실비율: "
                f"A={record['fault_ratio']['A']}%, "
                f"B={record['fault_ratio']['B']}%"
            )
            print(
                f"  관련법규: "
                f"{'수집됨' if status['related_laws'] else '확인 필요'}"
            )
            print(
                f"  판례/조정 사례: "
                f"{'수집됨' if status['precedents_and_mediation'] else '확인 필요'}"
            )

            # 비어 있는 핵심 항목은 별도로 기록한다.
            missing = [
                field for field, collected in status.items()
                if not collected
            ]

            if missing:
                print(f"  확인할 항목: {', '.join(missing)}")

        except (
            requests.RequestException,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            failed += 1

            error_record = {
                "chart_no": chart_no,
                "error": str(error),
            }

            errors = [
                item for item in errors
                if item.get("chart_no") != chart_no
            ]
            errors.append(error_record)
            save_json(ERROR_FILE, errors)

            print(f"  수집 실패: {error}")

        time.sleep(REQUEST_DELAY)

    print("\n" + "=" * 50)
    print("수집 작업 완료")
    print(f"성공: {succeeded}개")
    print(f"실패: {failed}개")
    print(f"결과 파일: {OUTPUT_FILE}")
    print(f"오류 목록: {ERROR_FILE}")


if __name__ == "__main__":
    main()
