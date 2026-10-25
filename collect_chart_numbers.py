
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://accident.knia.or.kr"
OUTPUT_FILE = Path("data/chart_numbers.json")


def main():
    response = requests.get(
        BASE_URL,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    charts = {}

    for link in soup.find_all("a", href=True):
        url = urljoin(BASE_URL, link["href"])
        parsed = urlparse(url)

        if parsed.netloc != "accident.knia.or.kr":
            continue

        if parsed.path != "/myaccident-content":
            continue

        params = parse_qs(parsed.query)
        chart_no = params.get("chartNo", [""])[0]

        if not chart_no:
            continue

        # 일반 도표 상세 페이지 형식만 수집
        chart_type = params.get("chartType", ["1"])[0]
        if chart_type != "1":
            continue

        charts[chart_no] = {
            "chart_no": chart_no,
            "url": url,
            "title": link.get_text(" ", strip=True),
        }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(
            list(charts.values()),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"수집한 도표 번호: {len(charts)}개")
    print(f"저장 위치: {OUTPUT_FILE}")

    for chart in charts.values():
        print(f"- {chart['chart_no']}: {chart['url']}")

    if not charts:
        print(
            "홈페이지 HTML에서 도표 링크를 찾지 못했습니다. "
            "도표 검색 기능의 실제 데이터 요청을 추가로 확인해야 합니다."
        )


if __name__ == "__main__":
    main()
