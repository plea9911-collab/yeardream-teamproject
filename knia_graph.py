
import json
from pathlib import Path
from typing import TypedDict

import requests
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END

from knia_service import get_official_result


# ==========================================
# 1. 파일 경로 및 상태 정의
# ==========================================

DATA_FILE = Path("data/knia_accident_steps.json")


class AccidentState(TypedDict, total=False):
    chart_no: str
    official_data: dict
    summary: str
    summary_error: str
    error: str


# ==========================================
# 2. 사고 유형 데이터 불러오기
# ==========================================

def load_accident_steps() -> list[dict]:
    """저장된 공식 사고 유형 목록을 불러온다."""

    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"{DATA_FILE} 파일을 찾을 수 없습니다. "
            "먼저 collect_knia.py를 실행해 주세요."
        )

    with DATA_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


# ==========================================
# 3. 하위 사고 유형 찾기
# ==========================================

def get_children(
    items: list[dict],
    parent_id,
) -> list[dict]:
    """특정 사고 유형의 하위 항목들을 반환한다."""

    return [
        item
        for item in items
        if str(item.get("uppertyId")) == str(parent_id)
    ]


# ==========================================
# 4. 사용자에게 선택지 보여주기
# ==========================================

def choose_item(options: list[dict]) -> dict:
    """번호를 입력받아 선택한 사고 유형을 반환한다."""

    for index, item in enumerate(options, start=1):
        print(f"{index}. {item.get('acdNtty', '이름 없음')}")

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


# ==========================================
# 5. 사고 유형 선택 과정
# ==========================================

def select_accident(items: list[dict]) -> dict | None:
    """사용자가 사고 유형을 단계별로 선택하도록 한다."""

    options = [
        item
        for item in items
        if int(item.get("dpth", -1)) == 0
    ]

    selected_path = []

    while options:
        print("\n===== 사고 상황 선택 =====")

        selected = choose_item(options)
        selected_name = selected.get("acdNtty", "이름 없음")

        # 상위 항목과 이름이 같으면 경로에 중복 표시하지 않는다.
        if not selected_path or selected_path[-1] != selected_name:
            selected_path.append(selected_name)

        chart_no = selected.get("chartNo")

        # 도표번호가 있으면 최종 선택 완료
        if chart_no:
            print("\n===== 선택 완료 =====")

            for index, name in enumerate(selected_path, start=1):
                print(f"{index}. {name}")

            print(f"\n도표번호: {chart_no}")
            return selected

        # 하위 사고 유형 가져오기
        options = get_children(
            items,
            selected.get("acdNttyId"),
        )

        if not options:
            print("추가 선택지가 없습니다.")
            return None

    return None


# ==========================================
# 6. LangGraph 노드: 공식 자료 조회
# ==========================================

def lookup_official_data(state: AccidentState) -> dict:
    """선택한 도표번호로 공식 과실비율 자료를 조회한다."""

    chart_no = state.get("chart_no")

    if not chart_no:
        return {"error": "조회할 도표번호가 없습니다."}

    try:
        official_data = get_official_result(chart_no)

        return {
            "official_data": official_data
        }

    except requests.RequestException as error:
        return {
            "error": f"공식 사이트 요청 오류: {error}"
        }

    except ValueError as error:
        return {
            "error": str(error)
        }


# ==========================================
# 7. Gemma 모델 설정
# ==========================================

llm = ChatOllama(
    model="gemma4:e4b",
    temperature=0.2,
)


# ==========================================
# 8. LangGraph 노드: Gemma 요약
# ==========================================

def summarize_with_gemma(state: AccidentState) -> dict:
    """공식 조회 결과를 바탕으로 친근한 한국어 설명을 생성한다."""

    # 공식 자료 조회에 실패했다면 요약하지 않는다.
    if state.get("error") or not state.get("official_data"):
        return {}

    official_data = state["official_data"]


    prompt = f"""
    너는 교통사고 과실비율을 쉽게 설명해 주는 친근한 대화형 챗봇이야.

    아래 공식 조회 결과만 근거로 사용해서 사용자에게 답변해 줘.

    [공식 조회 결과]
    {json.dumps(official_data, ensure_ascii=False, indent=2)}

    [말투와 답변 규칙]
    1. 반드시 자연스러운 한국어 반말로 대화해.
    2. 친절하고 따뜻한 말투를 사용하되, 과하게 들뜨거나 유치하게 말하지 마.
    3. 사용자가 이미 웹앱의 목적을 알고 있으므로 인사, 자기소개, 챗봇 소개를 하지 마.
    4. "안녕하세요", "나는 과실비율 안내 챗봇이야",
    "조회하신 자료를 바탕으로 설명해 드릴게요" 같은
    서론이나 형식적인 안내 문구를 절대 쓰지 마.
    5. 첫 문장부터 해당 사고의 유형이나 핵심 과실비율을 설명해.
    6. 사고 상황과 과실 해설을 일상적인 표현으로 쉽게 풀어 줘.
    7. A와 B가 각각 어떤 차량인지 공식 자료에 나타나 있다면 정확하게 설명해.
    8. A와 B의 의미가 공식 자료에 없다면 임의로 추측하지 마.
    9. 공식 자료에 있는 과실비율과 조건을 정확하게 전달해.
    10. 적용 및 비적용 조건에 중요한 내용이 있으면 함께 설명해.
    11. 공식 자료에 없는 사실이나 법률적 판단을 만들어 내지 마.
    12. 기본 과실비율과 개별 사고의 최종 과실비율은 다를 수 있다는 점을
        마지막에 짧고 자연스럽게 알려 줘.
    13. 불필요하게 긴 목록이나 반복을 피하고, 실제 대화처럼 자연스럽게 작성해.
    14. 필요한 경우에만 이모지를 가볍게 사용해.
    15. "공식 조회 결과", "기본 과실 해설" 같은 내부 데이터의 제목을
        그대로 반복하지 말고 자연스러운 문장으로 설명해.
    16. 자료에 없는 내용은 확인되지 않았다고 솔직하게 알려 줘.

    17. 공식 자료에 서로 다른 사고 상황이나 적용 조건이 여러 개 있으면
        각각을 반드시 구분해서 설명해.
    18. 각 사고 상황에 해당하는 과실비율을 바로 옆에 표시해.
    19. 여러 비율을 설명할 때는 단순히 범위로 표현하지 말고,
        어떤 조건에서 어떤 비율이 적용되는지 명확하게 연결해.
    20. A와 B의 과실비율 순서를 바꾸지 마.
    21. 공식 자료에 조건별 과실비율이 서로 다르면
        하나의 대표 비율만 선택해서 설명하지 마.
    22. 공식 조회 결과의 fault_ratio와 상세 해설의 과실비율이 서로 다르면,
        두 값을 무조건 동일하게 취급하지 마.
        상세 해설에 조건별 과실비율이 명시되어 있다면 해당 조건과 연결해서 설명하고,
        각 비율의 적용 상황이 불분명하면 임의로 판단하지 마.


    [답변 구성]
    - 첫 문장: 사고 유형과 핵심 과실비율을 자연스럽게 소개
    - 다음: 왜 이런 비율이 나왔는지 쉬운 말로 설명
    - 마지막: 필요한 적용 조건과 실제 사고에 대한 주의사항 안내

    사용자에게 직접 이야기하는 최종 답변만 출력해.
    """

    try:
        response = llm.invoke(prompt)

        # 모델 응답을 문자열로 변환
        content = response.content

        if isinstance(content, str):
            summary = content.strip()
        else:
            summary = str(content).strip()

        if not summary:
            raise ValueError("Gemma가 빈 답변을 반환했습니다.")

        return {"summary": summary}

    except Exception as error:
        # 모델 실행에 실패해도 공식 조회 결과는 유지한다.
        return {
            "summary_error": (
                f"Gemma 요약에 실패했습니다: {error}"
            )
        }


# ==========================================
# 9. LangGraph 구성
# ==========================================

builder = StateGraph(AccidentState)

builder.add_node(
    "lookup_official_data",
    lookup_official_data,
)

builder.add_node(
    "summarize_with_gemma",
    summarize_with_gemma,
)

# 시작 → 공식 자료 조회 → Gemma 요약 → 종료
builder.add_edge(
    START,
    "lookup_official_data",
)

builder.add_edge(
    "lookup_official_data",
    "summarize_with_gemma",
)

builder.add_edge(
    "summarize_with_gemma",
    END,
)

graph = builder.compile()


# ==========================================
# 10. 프로그램 실행
# ==========================================

def main():
    try:
        # 1) 사고 유형 데이터 불러오기
        items = load_accident_steps()

        # 2) 사용자에게 사고 유형 선택받기
        selected = select_accident(items)

        if selected is None:
            print("사고 유형을 끝까지 선택하지 못했습니다.")
            return

        # 3) 선택한 도표번호 가져오기
        chart_no = selected.get("chartNo")

        if not chart_no:
            print("선택한 항목에 도표번호가 없습니다.")
            return

        print(f"\n선택한 도표번호: {chart_no}")

        # 4) LangGraph 실행
        print("\n공식 과실비율 자료를 조회하고 있습니다...")

        final_state = graph.invoke({
            "chart_no": chart_no
        })

        # 5) 공식 조회 실패 처리
        if "error" in final_state:
            print("\n조회 실패:", final_state["error"])
            return

        # 6) 공식 조회 결과 확인
        official_data = final_state.get("official_data", {})

                # 6) 공식 사고 자료 출력
        print("\n===== 사고 유형 =====")
        print(official_data.get("accident_type", "정보 없음"))
        print(f"도표번호: {official_data.get('chart_no', '정보 없음')}")

        print("\n===== 1. 공식 사고 자료 =====")

        details = official_data.get("details", {})

        for title in ["사고 상황", "적용(비적용)", "기본 과실 해설"]:
            content = details.get(title)

            if content:
                print(f"\n[{title}]")
                print(content)

        # 7) Gemma 요약 결과 출력
        print("\n===== 2. Gemma 요약 답변 =====")

        if final_state.get("summary"):
            print(final_state["summary"])

        elif final_state.get("summary_error"):
            print(final_state["summary_error"])
            print("\n공식 사고 자료는 위에서 확인할 수 있습니다.")

        else:
            print("요약 결과가 생성되지 않았습니다.")

    except FileNotFoundError as error:
        print(f"\n파일 오류: {error}")

    except json.JSONDecodeError as error:
        print(f"\nJSON 파일 읽기 오류: {error}")


if __name__ == "__main__":
    main()
