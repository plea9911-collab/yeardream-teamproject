
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def load_json(filename: str) -> list[dict]:
    """JSON 파일을 읽어 레코드 목록으로 반환한다."""
    path = DATA_DIR / filename

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def lookup_by_chart(chart_no: str) -> None:
    """도표번호에 해당하는 사고 정보, 법규, 판례를 조회한다."""

    # 1. JSON 파일 읽기
    accident_cases = load_json("accident_cases.json")
    related_laws = load_json("related_laws.json")
    precedents = load_json("precedents_mediation.json")

    # 2. 사고 도표 찾기
    chart = next(
        (
            item for item in accident_cases
            if item.get("chart_no") == chart_no
        ),
        None,
    )

    if chart is None:
        print(f"\n'{chart_no}' 도표를 찾을 수 없습니다.")
        return

    print("\n" + "=" * 60)
    print(f"도표번호: {chart['chart_no']}")
    print(f"사고유형: {chart.get('accident_type', '정보 없음')}")
    print("=" * 60)

    print("\n[사고 상황]")
    print(chart.get("accident_situation", "정보 없음"))

    # 3. 같은 도표번호의 법규 찾기
    laws = [
        item for item in related_laws
        if item.get("chart_no") == chart_no
    ]

    print("\n[관련 법규]")
    if laws:
        for index, law in enumerate(laws, start=1):
            print(f"\n자료 {index}")
            print(law.get("content", "내용 없음"))
            if law.get("source_url"):
                print(f"출처: {law['source_url']}")
    else:
        print("해당 도표번호의 법규 자료가 없습니다.")

    # 4. 같은 도표번호의 판례·분쟁심의 자료 찾기
    matched_precedents = [
        item for item in precedents
        if item.get("chart_no") == chart_no
    ]

    print("\n[관련 판례·분쟁심의 자료]")
    if matched_precedents:
        for index, precedent in enumerate(
            matched_precedents, start=1
        ):
            print(f"\n자료 {index}")
            print(precedent.get("content", "내용 없음"))
            if precedent.get("source_url"):
                print(f"출처: {precedent['source_url']}")
    else:
        print("해당 도표번호의 판례·분쟁심의 자료가 없습니다.")


def main() -> None:
    print("교통사고 도표번호 자료 조회")
    print("예시: 차1-1")
    print("종료하려면 q를 입력하세요.")

    while True:
        chart_no = input("\n도표번호 입력: ").strip()

        if chart_no.lower() == "q":
            print("프로그램을 종료합니다.")
            break

        if not chart_no:
            print("도표번호를 입력해 주세요.")
            continue

        lookup_by_chart(chart_no)


if __name__ == "__main__":
    main()
