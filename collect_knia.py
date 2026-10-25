
import json
from pathlib import Path

import requests

BASE_URL = "https://accident.knia.or.kr"
API_URL = f"{BASE_URL}/selectAccidentStep"


def fetch_accident_steps() -> list[dict]:
    response = requests.post(
        API_URL,
        data={"GROUPCODE": "2"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def main():
    items = fetch_accident_steps()

    # 1. 도표번호가 있는 항목만 추출
    charts = [
        {
            "chartNo": item["chartNo"],
            "name": item.get("acdNtty"),
            "itemId": item.get("acdNttyId"),
            "parentId": item.get("uppertyId"),
            "depth": item.get("dpth"),
        }
        for item in items
        if item.get("chartNo")
    ]

    # 2. 저장할 폴더 생성
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)

    # 3. 전체 사고 선택 항목 저장 (중간 단계 포함)
    steps_file = output_dir / "knia_accident_steps.json"
    steps_file.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 4. 도표번호가 있는 항목 저장
    output_file = output_dir / "knia_charts.json"
    output_file.write_text(
        json.dumps(charts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 5. 실행 결과 출력
    print(f"차대차 사고 항목: {len(items)}개")
    print(f"도표번호가 있는 항목: {len(charts)}개")
    print(f"전체 선택 항목 저장 위치: {steps_file}")
    print(f"도표 목록 저장 위치: {output_file}")


if __name__ == "__main__":
    main()
