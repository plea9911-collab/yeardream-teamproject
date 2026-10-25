
import requests

from fetch_knia_result import (
    fetch_fault_ratio,
    fetch_detail_page,
    extract_detail_sections,
)


def get_official_result(chart_no: str) -> dict:
    """도표번호에 해당하는 공식 과실비율과 상세 설명을 반환한다."""

    results = fetch_fault_ratio(chart_no)

    if not results:
        raise ValueError(
            f"도표번호 {chart_no}에 대한 과실비율 조회 결과가 없습니다."
        )

    # 요청한 도표번호와 일치하는 결과를 우선 선택한다.
    result = next(
        (
            item for item in results
            if str(item.get("chartNo")) == chart_no
        ),
        None,
    )

    if result is None:
        raise ValueError(
            f"응답에서 도표번호 {chart_no}와 일치하는 항목을 찾지 못했습니다."
        )

    html = fetch_detail_page(chart_no)
    sections = extract_detail_sections(html)

    return {
        "chart_no": result.get("chartNo"),
        "accident_type": result.get("acdNtty"),
        "fault_ratio": {
            "A": result.get("fltRtA"),
            "B": result.get("fltRtB"),
        },
        "details": sections,
    }
