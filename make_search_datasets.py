
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

SOURCE_FILE = DATA_DIR / "accident_cases.json"
LAWS_FILE = DATA_DIR / "related_laws.json"
PRECEDENTS_FILE = DATA_DIR / "precedents_mediation.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def extract_content(value):
    """문자열이나 객체 목록에서 실제 내용을 추출한다."""
    if not value:
        return []

    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []

    if isinstance(value, dict):
        content = value.get("content")
        if content and str(content).strip():
            return [str(content).strip()]
        return []

    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(extract_content(item))
        return result

    return []


def main():
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"원본 JSON 파일을 찾을 수 없습니다: {SOURCE_FILE}"
        )

    records = load_json(SOURCE_FILE)

    laws = []
    precedents = []

    for record in records:
        chart_no = record.get("chart_no", "")
        chart_name = record.get("accident_type", "")
        source_url = record.get("url", "")

        for index, content in enumerate(
            extract_content(record.get("related_laws")),
            start=1,
        ):
            laws.append({
                "id": f"{chart_no}_law_{index}",
                "chart_no": chart_no,
                "chart_name": chart_name,
                "content": content,
                "source_url": source_url,
            })

        for index, content in enumerate(
            extract_content(record.get("precedents_and_mediation")),
            start=1,
        ):
            precedents.append({
                "id": f"{chart_no}_precedent_{index}",
                "chart_no": chart_no,
                "chart_name": chart_name,
                "content": content,
                "source_url": source_url,
            })

    save_json(LAWS_FILE, laws)
    save_json(PRECEDENTS_FILE, precedents)

    print("=" * 45)
    print("검색용 JSON 생성 완료")
    print(f"원본 도표 수: {len(records)}개")
    print(f"법규 레코드 수: {len(laws)}개")
    print(f"판례·조정 레코드 수: {len(precedents)}개")
    print(f"법규 파일: {LAWS_FILE}")
    print(f"판례·조정 파일: {PRECEDENTS_FILE}")


if __name__ == "__main__":
    main()
