
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    KeepTogether,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# macOS에서 사용할 한글 폰트 후보
FONT_CANDIDATES = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]

FONT_NAME = "KoreanFont"


def register_korean_font():
    """사용 가능한 한글 폰트를 찾아 등록한다."""
    for font_path in FONT_CANDIDATES:
        if Path(font_path).exists():
            try:
                pdfmetrics.registerFont(
                    TTFont(FONT_NAME, font_path, subfontIndex=0)
                )
                print(f"한글 폰트 사용: {font_path}")
                return
            except Exception as error:
                print(f"폰트 등록 시도 실패: {font_path}")
                print(f"이유: {error}")

    raise FileNotFoundError(
        "사용 가능한 한글 폰트를 찾지 못했습니다. "
        "FONT_CANDIDATES에 설치된 한글 폰트 경로를 추가해 주세요."
    )


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def make_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="KoreanTitle",
        fontName=FONT_NAME,
        fontSize=20,
        leading=28,
        alignment=TA_CENTER,
        spaceAfter=15 * mm,
    ))

    styles.add(ParagraphStyle(
        name="KoreanHeading",
        fontName=FONT_NAME,
        fontSize=14,
        leading=20,
        spaceBefore=5 * mm,
        spaceAfter=3 * mm,
        textColor=colors.HexColor("#234E70"),
    ))

    styles.add(ParagraphStyle(
        name="KoreanBody",
        fontName=FONT_NAME,
        fontSize=9,
        leading=14,
        spaceAfter=3 * mm,
        wordWrap="CJK",
    ))

    styles.add(ParagraphStyle(
        name="KoreanSmall",
        fontName=FONT_NAME,
        fontSize=8,
        leading=12,
        textColor=colors.HexColor("#555555"),
        wordWrap="CJK",
    ))

    return styles


def safe_text(value):
    """PDF 문단에서 특수문자가 태그로 해석되지 않도록 처리한다."""
    if value is None:
        return ""

    text = str(value)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace("\n", "<br/>")
    return text


def add_field(story, styles, label, value):
    if value is None or value == "" or value == []:
        return

    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, indent=2)

    story.append(Paragraph(
        f"<b>{safe_text(label)}</b>",
        styles["KoreanBody"],
    ))
    story.append(Paragraph(
        safe_text(value),
        styles["KoreanBody"],
    ))


def add_record(story, styles, record, index, title_field):
    title = (
        record.get(title_field)
        or record.get("chart_name")
        or record.get("chart_no")
        or f"자료 {index}"
    )

    story.append(Paragraph(
        f"{index}. {safe_text(title)}",
        styles["KoreanHeading"],
    ))

    # ID와 사고 도표 번호
    add_field(story, styles, "ID", record.get("id"))
    add_field(story, styles, "도표 번호", record.get("chart_no"))

    # 사고 도표 원본에 들어 있는 모든 항목을 보존한다.
    for key, value in record.items():
        if key in ("id", title_field, "chart_name", "chart_no"):
            continue

        add_field(story, styles, key, value)

    story.append(Spacer(1, 4 * mm))


def create_pdf(source_file, output_file, title, title_field):
    if not source_file.exists():
        print(f"[건너뜀] 파일을 찾을 수 없습니다: {source_file}")
        return

    records = load_json(source_file)

    if not isinstance(records, list):
        raise ValueError(f"{source_file.name}의 최상위 구조가 리스트가 아닙니다.")

    styles = make_styles()

    document = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
        author="교통사고 과실비율 프로젝트",
    )

    story = [
        Paragraph(safe_text(title), styles["KoreanTitle"]),
        Paragraph(
            f"총 {len(records)}개 레코드",
            styles["KoreanBody"],
        ),
        Spacer(1, 5 * mm),
    ]

    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            continue

        add_record(story, styles, record, index, title_field)

    document.build(story)

    print(f"[완료] {output_file.name} ({len(records)}개 레코드)")


def main():
    register_korean_font()

    tasks = [
        (
            DATA_DIR / "accident_cases.json",
            DATA_DIR / "accident_cases.pdf",
            "교통사고 과실비율 전체 자료",
            "accident_type",
        ),
        (
            DATA_DIR / "related_laws.json",
            DATA_DIR / "related_laws.pdf",
            "교통사고 관련 법규",
            "chart_name",
        ),
        (
            DATA_DIR / "precedents_mediation.json",
            DATA_DIR / "precedents_mediation.pdf",
            "교통사고 판례 및 조정 사례",
            "chart_name",
        ),
    ]

    print("=" * 50)
    print("PDF 생성 시작")
    print("=" * 50)

    for source, output, title, title_field in tasks:
        create_pdf(source, output, title, title_field)

    print("=" * 50)
    print("PDF 생성 작업 종료")
    print(f"저장 위치: {DATA_DIR}")
    print("=" * 50)


if __name__ == "__main__":
    main()
