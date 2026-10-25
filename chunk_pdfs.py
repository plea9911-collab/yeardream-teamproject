
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 프로젝트 경로
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# 청킹할 PDF 파일
PDF_FILES = [
    "accident_cases.pdf",
    "related_laws.pdf",
    "precedents_mediation.pdf",
]

# 청킹 설정
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def load_pdf(pdf_path: Path):
    """PDF를 페이지별 Document 목록으로 불러온다."""
    loader = PyPDFLoader(str(pdf_path))
    return loader.load()


def main():
    # 텍스트 분할기
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", " ", ""],
        add_start_index=True,
    )

    all_chunks = []

    for filename in PDF_FILES:
        pdf_path = DATA_DIR / filename

        print("\n" + "=" * 60)
        print(f"PDF 파일: {filename}")
        print("=" * 60)

        if not pdf_path.exists():
            print(f"파일을 찾을 수 없습니다: {pdf_path}")
            continue

        # 1. PDF 로딩
        documents = load_pdf(pdf_path)
        print(f"원본 페이지 수: {len(documents)}")

        # 2. 문서를 작은 조각으로 분할
        chunks = splitter.split_documents(documents)

        # 3. 각 조각에 원본 PDF 이름 보존
        for chunk in chunks:
            chunk.metadata["pdf_name"] = filename

        all_chunks.extend(chunks)

        print(f"생성된 청크 수: {len(chunks)}")

        if chunks:
            first_chunk = chunks[0]

            print("\n[첫 번째 청크의 메타데이터]")
            print(first_chunk.metadata)

            print("\n[첫 번째 청크의 텍스트]")
            print(first_chunk.page_content[:700])

    print("\n" + "=" * 60)
    print("청킹 완료")
    print(f"전체 청크 수: {len(all_chunks)}")
    print(f"청크 크기 설정: {CHUNK_SIZE}자")
    print(f"청크 중첩 설정: {CHUNK_OVERLAP}자")
    print("=" * 60)


if __name__ == "__main__":
    main()
