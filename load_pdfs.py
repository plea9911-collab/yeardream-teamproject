
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader

# 현재 파이썬 파일이 있는 프로젝트 폴더
BASE_DIR = Path(__file__).resolve().parent

# PDF 파일이 저장된 폴더
DATA_DIR = BASE_DIR / "data"

# 읽어올 PDF 파일 목록
PDF_FILES = [
    "accident_cases.pdf",
    "related_laws.pdf",
    "precedents_mediation.pdf",
]


def load_pdf(pdf_path: Path):
    """PDF를 읽어 LangChain Document 목록으로 반환한다."""

    loader = PyPDFLoader(str(pdf_path))
    documents = loader.load()

    return documents


def main():
    all_documents = []

    for filename in PDF_FILES:
        pdf_path = DATA_DIR / filename

        print("\n" + "=" * 60)
        print(f"PDF 파일: {filename}")
        print("=" * 60)

        if not pdf_path.exists():
            print(f"파일을 찾을 수 없습니다: {pdf_path}")
            continue

        documents = load_pdf(pdf_path)
        all_documents.extend(documents)

        print(f"추출된 페이지 수: {len(documents)}")

        # 첫 페이지의 텍스트만 미리 확인
        if documents:
            first_page = documents[0]

            print("\n[첫 페이지 메타데이터]")
            print(first_page.metadata)

            print("\n[첫 페이지 텍스트 미리보기]")
            print(first_page.page_content[:1000])

    print("\n" + "=" * 60)
    print("PDF 로딩 완료")
    print(f"전체 문서 페이지 수: {len(all_documents)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
