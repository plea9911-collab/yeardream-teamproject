
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma


# 1. 경로 설정
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
VECTOR_DB_DIR = DATA_DIR / "chroma_db"

PDF_FILES = [
    DATA_DIR / "accident_cases.pdf",
    DATA_DIR / "related_laws.pdf",
    DATA_DIR / "precedents_mediation.pdf",
]

# 2. 청크 설정
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# 3. 임베딩 모델 설정
EMBEDDING_MODEL = "nomic-embed-text"


def load_and_split_pdfs():
    """PDF를 읽고 검색에 적합한 청크로 분할한다."""
    documents = []

    for pdf_path in PDF_FILES:
        if not pdf_path.exists():
            raise FileNotFoundError(
                f"PDF 파일을 찾을 수 없습니다: {pdf_path}"
            )

        loader = PyPDFLoader(str(pdf_path))
        pages = loader.load()

        for page in pages:
            page.metadata["pdf_name"] = pdf_path.name

        documents.extend(pages)
        print(f"PDF 로딩 완료: {pdf_path.name} ({len(pages)}페이지)")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", " ", ""],
        add_start_index=True,
    )

    chunks = splitter.split_documents(documents)

    print(f"\n전체 청크 수: {len(chunks)}개")
    return chunks


def build_vector_store(chunks):
    """청크를 벡터로 변환하고 Chroma에 저장한다."""

    embeddings = OllamaEmbeddings(
        model=EMBEDDING_MODEL
    )

    vector_store = Chroma(
        collection_name="traffic_accident_pdfs",
        embedding_function=embeddings,
        persist_directory=str(VECTOR_DB_DIR),
    )

    # 청크마다 고유 ID를 만들어 같은 ID로 재실행 시 중복을 줄인다.
    ids = [
        (
            f"{chunk.metadata['pdf_name']}"
            f"_page{chunk.metadata.get('page', 0)}"
            f"_start{chunk.metadata.get('start_index', 0)}"
        )
        for chunk in chunks
    ]

    vector_store.add_documents(
        documents=chunks,
        ids=ids,
    )

    print(f"벡터 저장 완료: {VECTOR_DB_DIR}")
    return vector_store


def test_search(vector_store):
    """질문과 유사한 자료를 검색해 결과를 확인한다."""

    query = "교차로에서 신호를 위반한 차량과 직진 차량이 충돌한 사고"

    results = vector_store.similarity_search(
        query,
        k=3,
    )

    print("\n===== 검색 테스트 =====")
    print(f"질문: {query}")

    for index, document in enumerate(results, start=1):
        print(f"\n--- 검색 결과 {index} ---")
        print(f"출처: {document.metadata.get('pdf_name')}")
        print(f"페이지: {document.metadata.get('page', 0) + 1}")
        print(document.page_content[:700])


if __name__ == "__main__":
    chunks = load_and_split_pdfs()
    vector_store = build_vector_store(chunks)
    test_search(vector_store)
