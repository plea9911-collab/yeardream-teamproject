
from pathlib import Path

from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma


BASE_DIR = Path(__file__).resolve().parent
VECTOR_DB_DIR = BASE_DIR / "data" / "chroma_db"

EMBEDDING_MODEL = "nomic-embed-text"

# 자료별 검색 개수
SEARCH_COUNTS = {
    "accident_cases.pdf": 5,
    "precedents_mediation.pdf": 3,
    "related_laws.pdf": 3,
}

PDF_LABELS = {
    "accident_cases.pdf": "과실비율표",
    "precedents_mediation.pdf": "판례·분쟁심의 자료",
    "related_laws.pdf": "관련 법률",
}


def create_vector_store():
    embeddings = OllamaEmbeddings(
        model=EMBEDDING_MODEL
    )

    return Chroma(
        collection_name="traffic_accident_pdfs",
        embedding_function=embeddings,
        persist_directory=str(VECTOR_DB_DIR),
    )


def search_by_pdf(vector_store, question, pdf_name, count):
    """특정 PDF에서만 관련 청크를 검색한다."""

    return vector_store.similarity_search(
        query=question,
        k=count,
        filter={"pdf_name": pdf_name},
    )


def print_results(label, results):
    print(f"\n{'=' * 60}")
    print(f"[{label}] 검색 결과: {len(results)}개")
    print("=" * 60)

    if not results:
        print("검색 결과가 없습니다.")
        return

    for index, document in enumerate(results, start=1):
        page = document.metadata.get("page", 0) + 1

        print(f"\n[{index}] PDF 페이지: {page}")
        print("-" * 40)
        print(document.page_content)


def search_all_sources(vector_store, question):
    for pdf_name, count in SEARCH_COUNTS.items():
        label = PDF_LABELS[pdf_name]

        results = search_by_pdf(
            vector_store=vector_store,
            question=question,
            pdf_name=pdf_name,
            count=count,
        )

        print_results(label, results)


def main():
    if not VECTOR_DB_DIR.exists():
        raise FileNotFoundError(
            "Chroma 저장소가 없습니다. "
            "build_vector_store.py를 먼저 실행해 주세요."
        )

    vector_store = create_vector_store()

    print("교통사고 자료 검색 프로그램")
    print("사고 상황을 입력하세요. 종료하려면 q를 입력하세요.")

    while True:
        question = input("\n사고 상황 > ").strip()

        if question.lower() == "q":
            print("프로그램을 종료합니다.")
            break

        if not question:
            print("사고 상황을 입력해 주세요.")
            continue

        search_all_sources(vector_store, question)


if __name__ == "__main__":
    main()
