
import json
from pathlib import Path

from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_DIR = DATA_DIR / "chroma_db"

COLLECTION_NAME = "traffic_accident_charts"
EMBEDDING_MODEL = "nomic-embed-text"


def load_json(filename: str) -> list[dict]:
    path = DATA_DIR / filename

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def create_chart_documents() -> list[Document]:
    """각 사고 도표를 검색용 Document로 만든다."""
    charts = load_json("accident_cases.json")
    documents = []

    for chart in charts:
        text = (
            f"사고유형: {chart.get('accident_type', '')}\n"
            f"사고상황: {chart.get('accident_situation', '')}\n"
            f"적용기준: {chart.get('application_criteria', '')}"
        )

        documents.append(
            Document(
                page_content=text,
                metadata={
                    "chart_no": chart["chart_no"],
                    "chart_name": chart.get("accident_type", ""),
                },
            )
        )

    return documents


def create_vector_store() -> Chroma:
    """사고 도표 전용 검색 인덱스를 준비한다."""
    embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL)

    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(DB_DIR),
    )

    # 최초 실행 시에만 색인한다.
    if vector_store._collection.count() == 0:
        documents = create_chart_documents()

        ids = [
            doc.metadata["chart_no"]
            for doc in documents
        ]

        vector_store.add_documents(
            documents=documents,
            ids=ids,
        )

        print(f"사고 도표 {len(documents)}개를 색인했습니다.")

    return vector_store


def show_chart_details(chart_no: str) -> None:
    """선택한 도표번호로 법규와 판례 원문을 조회한다."""
    charts = load_json("accident_cases.json")
    laws = load_json("related_laws.json")
    precedents = load_json("precedents_mediation.json")

    chart = next(
        (
            item for item in charts
            if item.get("chart_no") == chart_no
        ),
        None,
    )

    if chart is None:
        print("해당 도표를 찾을 수 없습니다.")
        return

    print("\n" + "=" * 60)
    print(f"도표번호: {chart['chart_no']}")
    print(f"사고유형: {chart.get('accident_type', '')}")
    print("\n[사고 상황]")
    print(chart.get("accident_situation", ""))

    matched_laws = [
        item for item in laws
        if item.get("chart_no") == chart_no
    ]

    print("\n[관련 법규 원문]")
    if matched_laws:
        for item in matched_laws:
            print(item.get("content", ""))
            print(f"출처: {item.get('source_url', '')}")
    else:
        print("관련 법규 자료가 없습니다.")

    matched_precedents = [
        item for item in precedents
        if item.get("chart_no") == chart_no
    ]

    print("\n[관련 판례·분쟁심의 원문]")
    if matched_precedents:
        for item in matched_precedents:
            print(item.get("content", ""))
            print(f"출처: {item.get('source_url', '')}")
    else:
        print("관련 판례·분쟁심의 자료가 없습니다.")



def rerank_results(question: str, results: list) -> list:
    """사고 상황의 핵심 조건을 이용해 검색 후보를 재정렬한다."""

    question = question.replace(" ", "")

    # 질문에서 확인할 핵심 조건
    conditions = {
        "직진": ["직진"],
        "좌회전": ["좌회전"],
        "우회전": ["우회전"],
        "녹색신호": ["녹색신호", "녹색"],
        "적색신호": ["적색신호", "적색"],
        "황색신호": ["황색신호", "황색"],
    }

    active_conditions = [
        (name, keywords)
        for name, keywords in conditions.items()
        if name.replace("신호", "") in question
        or name in question
    ]

    scored_results = []

    for doc, distance in results:
        text = (
            doc.metadata.get("chart_name", "")
            + doc.page_content
        ).replace(" ", "")

        score = 0

        for _, keywords in active_conditions:
            if any(keyword in text for keyword in keywords):
                score += 1

        # 기존 임베딩 검색 결과의 순서도 약하게 반영
        scored_results.append(
            (doc, distance, score)
        )

    # 핵심 조건 일치 개수가 많은 순서,
    # 그다음 임베딩 거리가 가까운 순서
    scored_results.sort(
        key=lambda item: (-item[2], item[1])
    )

    return scored_results


def main() -> None:
    vector_store = create_vector_store()

    while True:
        question = input(
            "\n사고 상황을 입력하세요 (종료: q): "
        ).strip()

        if question.lower() == "q":
            break

        if not question:
            print("사고 상황을 입력해 주세요.")
            continue

        # 사고 설명과 의미적으로 유사한 도표 3개 검색
        results = vector_store.similarity_search_with_score(
    question,
    k=10,
)

        results = rerank_results(question, results)
        results = results[:3]

        if not results:
            print("관련 도표를 찾지 못했습니다.")
            continue

        print("\n[검색된 관련 도표]")
        for index, (doc, distance, condition_score) in enumerate(
            results, start=1
        ):
            print(f"\n{index}. 도표번호: {doc.metadata['chart_no']}")
            print(f"사고유형: {doc.metadata['chart_name']}")
            print(f"검색 거리: {distance:.4f}")
            print(f"핵심 조건 일치 수: {condition_score}")
            print(f"사고 설명: {doc.page_content}")

        print(
            "\n검색 결과는 후보입니다. "
            "사고 상황과 신호, 진행 방향 등을 확인하세요."
        )

        choice = input(
            "관련 도표 번호를 선택하세요 (1~3, Enter: 건너뛰기): "
        ).strip()

        if choice not in {"1", "2", "3"}:
            continue

        selected_doc = results[int(choice) - 1][0]
        chart_no = selected_doc.metadata["chart_no"]

        show_chart_details(chart_no)


if __name__ == "__main__":
    main()
