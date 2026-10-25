
import json
from pathlib import Path

import requests

from fetch_knia_result import (
    fetch_fault_ratio,
    fetch_detail_page,
    extract_detail_sections,
)


DATA_FILE = Path("data/knia_accident_steps.json")


def load_accident_steps() -> list[dict]:
    """저장된 사고 유형 데이터를 불러온다."""
    with DATA_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_children(items: list[dict], parent_id) -> list[dict]:
    """특정 항목의 바로 아래 선택지들을 반환한다."""
    return [
        item
        for item in items
        if str(item.get("uppertyId")) == str(parent_id)
    ]


def choose_item(options: list[dict]) -> dict:
    """사용자가 선택한 사고 항목을 반환한다."""
    for index, item in enumerate(options, start=1):
        name = item.get("acdNtty", "이름 없음")
        print(f"{index}. {name}")

    while True:
        answer = input("\n번호를 선택하세요: ").strip()

        try:
            number = int(answer)
        except ValueError:
            print("숫자를 입력해 주세요.")
            continue

        if 1 <= number <= len(options):
            return options[number - 1]

        print(f"1부터 {len(options)}까지의 번호를 입력해 주세요.")


def select_accident(items: list[dict]) -> dict | None:
    """사고 유형을 단계별로 선택하고 최종 항목을 반환한다."""
    current_options = [
        item
        for item in items
        if int(item.get("dpth", -1)) == 0
    ]

    selected_path = []

    while current_options:
        print("\n===== 사고 상황 선택 =====")
        selected = choose_item(current_options)
        selected_path.append(selected.get("acdNtty", "이름 없음"))

        chart_no = selected.get("chartNo")

        # 도표번호가 있으면 해당 항목의 선택 완료
        if chart_no:
            print("\n===== 선택 완료 =====")
            print("선택 경로:")
            for index, name in enumerate(selected_path, start=1):
                print(f"{index}. {name}")

            print(f"\n도표번호: {chart_no}")
            return selected

        # 도표번호가 없으면 하위 선택지로 이동
        current_options = get_children(
            items,
            selected.get("acdNttyId"),
        )

        if not current_options:
            print("이 항목에는 추가 선택지가 없습니다.")
            return None

    return None



def show_official_result(chart_no: str) -> dict | None:
    """공식 자료를 조회하고 구조화된 데이터로 반환한다."""
    print(f"\n도표번호 {chart_no} 공식 자료 조회 중...")

    try:
        results = fetch_fault_ratio(chart_no)

        if not results:
            print("과실비율 조회 결과가 없습니다.")
            return None

        # API 응답에서 선택한 도표번호와 일치하는 결과 찾기
        result = next(
            (
                item for item in results
                if str(item.get("chartNo")) == chart_no
            ),
            results[0],
        )

        html = fetch_detail_page(chart_no)
        sections = extract_detail_sections(html)

        data = {
            "chart_no": result.get("chartNo"),
            "accident_type": result.get("acdNtty"),
            "fault_ratio": {
                "A": result.get("fltRtA"),
                "B": result.get("fltRtB"),
            },
            "details": sections,
        }

        print("\n===== 공식 과실비율 =====")
        print(f"도표번호: {data['chart_no']}")
        print(f"사고 유형: {data['accident_type']}")
        print(f"A 차량 기본 과실: {data['fault_ratio']['A']}%")
        print(f"B 차량 기본 과실: {data['fault_ratio']['B']}%")

        print("\n===== 공식 상세 설명 =====")
        for name, content in data["details"].items():
            print(f"\n[{name}]")
            print(content or "내용이 없습니다.")

        return data

    except requests.RequestException as error:
        print(f"공식 사이트 요청 중 오류가 발생했습니다: {error}")
        return None

    except (ValueError, json.JSONDecodeError) as error:
        print(f"응답 처리 중 오류가 발생했습니다: {error}")
        return None



def main():
    items = load_accident_steps()

    selected = select_accident(items)

    if selected is None:
        print("사고 유형을 끝까지 선택하지 못했습니다.")
        return

    chart_no = selected.get("chartNo")

    if not chart_no:
        print("선택한 항목에 도표번호가 없습니다.")
        return

    result = show_official_result(chart_no)

    if result is not None:
        output_dir = Path("data")
        output_dir.mkdir(exist_ok=True)

        output_file = output_dir / f"{chart_no}_result.json"
        output_file.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"\nJSON 저장 완료: {output_file}")


if __name__ == "__main__":
    main()
