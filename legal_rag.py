
import re
import argparse
from pathlib import Path

import unicodedata

from pypdf import PdfReader
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings


# ==========================================
# 1. 경로 및 모델 설정
# ==========================================

PDF_DIR = Path("data/legal_pdfs")
DB_DIR = Path("data/legal_chroma")
COLLECTION_NAME = "accident_legal_documents"

EMBEDDING_MODEL = "nomic-embed-text"

# 검색 결과 관련성 기준
MIN_RELEVANCE_SCORE = 0.50

LAW_TYPES = {
    "도로교통법",
    "자동차손해배상보장법",
    "교통사고처리특례법",
}


# ==========================================
# 2. 임베딩 모델 및 벡터 DB 설정
# ==========================================

embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL)


def get_vector_store() -> Chroma:
    """저장된 Chroma 벡터 데이터베이스를 연다."""

    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(DB_DIR),
    )


# ==========================================
# 3. PDF 읽기
# ==========================================


def load_pdf_documents() -> list[Document]:
    """PDF 파일을 읽고 출처 메타데이터를 보존한다."""

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))

    if not pdf_files:
        raise FileNotFoundError(
            f"{PDF_DIR} 폴더에 PDF 파일이 없습니다."
        )

    documents = []

    for pdf_path in pdf_files:
        print(f"PDF 읽는 중: {pdf_path.name}")

        # macOS 한글 파일명의 유니코드 정규화 차이를 통일한다.
        filename = unicodedata.normalize("NFC", pdf_path.name)

        # 파일명을 기준으로 문서 종류를 분류한다.
        if (
            "자동차사고_과실비율_인정기준" in filename
            or "과실비율" in filename
            or "인정기준" in filename
        ):
            document_type = "과실비율 인정기준"

        elif "도로교통법" in filename:
            document_type = "도로교통법"

        elif "자동차손해배상보장법" in filename:
            document_type = "자동차손해배상보장법"

        elif "교통사고처리특례법" in filename:
            document_type = "교통사고처리특례법"

        elif "민법" in filename:
            document_type = "민법"

        else:
            document_type = "기타"

        reader = PdfReader(str(pdf_path))
        extracted_pages = 0

        for page_index, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()

            if not text:
                continue

            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": pdf_path.name,
                        "page": page_index + 1,
                        "document_type": document_type,
                    },
                )
            )

            extracted_pages += 1

        print(
            f"  문서 종류: {document_type} / "
            f"전체 페이지: {len(reader.pages)} / "
            f"텍스트 추출 페이지: {extracted_pages}"
        )

    print(f"\n총 텍스트 추출 페이지 수: {len(documents)}")

    return documents



# ==========================================
# 4. 문서 분할 및 저장
# ==========================================


def ingest_pdf() -> None:
    """PDF를 분할해 기존 Chroma 컬렉션을 갱신한다."""

    documents = load_pdf_documents()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        separators=["\n\n", "\n", " ", ""],
    )

    chunks = splitter.split_documents(documents)

    print(f"\n읽은 페이지 수: {len(documents)}")
    print(f"생성한 문서 조각 수: {len(chunks)}")

    ids = []
    page_chunk_counts = {}

    for chunk in chunks:
        source = chunk.metadata["source"]
        page = chunk.metadata["page"]
        page_key = (source, page)

        chunk_index = page_chunk_counts.get(page_key, 0)
        page_chunk_counts[page_key] = chunk_index + 1

        ids.append(
            f"{source}-page-{page}-chunk-{chunk_index}"
        )

    vector_store = get_vector_store()

    # 기존 컬렉션의 문서를 삭제해 중복 색인을 방지한다.
    collection = vector_store._collection
    existing_count = collection.count()

    if existing_count > 0:
        print(f"\n기존 청크 {existing_count}개 삭제 중...")
        collection.delete(
            ids=collection.get(
                include=[],
            )["ids"]
        )

    print("\n임베딩 생성 및 저장을 시작합니다...")

    batch_size = 8
    total_chunks = len(chunks)

    for start in range(0, total_chunks, batch_size):
        end = min(start + batch_size, total_chunks)

        vector_store.add_documents(
            documents=chunks[start:end],
            ids=ids[start:end],
        )

        print(
            f"진행 상황: {end}/{total_chunks}개 조각 저장 완료"
        )

    print(f"\n저장 완료: {DB_DIR}")
    print(f"컬렉션 이름: {COLLECTION_NAME}")
    print(f"최종 청크 수: {collection.count()}")



# ==========================================
# 5. 법 조항 및 판례 인용 추출
# ==========================================

def extract_legal_citations(text: str) -> list[str]:
    """원문에서 법 조항과 판례 인용 정보를 추출한다."""

    patterns = [
        (
            r"(?:도로교통법|민법|자동차손해배상보장법|교통사고처리특례법)"
            r"\s*제\s*\d+\s*조"
            r"(?:의\s*\d+)?"
            r"(?:\s*제\s*\d+\s*항)?"
            r"(?:\s*제\s*\d+\s*호)?"
        ),
        (
            r"(?:대법원|[가-힣]{2,10}(?:지방법원|고등법원|가정법원|행정법원))"
            r"\s*\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*"
            r"선고\s*[0-9가-힣]+\s*판결"
        ),
    ]

    citations = []

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            citation = re.sub(r"\s+", " ", match.group()).strip()

            if citation not in citations:
                citations.append(citation)

    return citations


def has_case_citation(text: str) -> bool:
    """원문에 판례 선고 및 판결 인용이 있는지 확인한다."""

    return any(
        "선고" in citation and "판결" in citation
        for citation in extract_legal_citations(text)
    )


# ==========================================
# 6. 사고 상황 관련성 검사
# ==========================================

def get_accident_topics(query: str) -> set[str]:
    """질문에서 검색에 중요한 사고 유형을 추출한다."""

    q = re.sub(r"\s+", "", query.lower())
    topics = set()

    topic_keywords = {
        "신호": [
            "신호위반", "신호등", "신호를위반",
            "적색신호", "적신호", "정상신호",
        ],
        "교차로": ["교차로", "사거리", "십자교차로", "t자교차로"],
        "직진": ["직진", "직진차량", "직진차"],
        "좌회전": ["좌회전"],
        "우회전": ["우회전"],
        "추돌": ["추돌", "후미충돌", "뒤에서충돌"],
        "차로변경": ["차로변경", "진로변경", "끼어들기"],
        "보행자": ["보행자", "횡단보도"],
        "주차": ["주차", "정차"],
        "역주행": ["역주행", "중앙선침범"],
        "음주": ["음주운전", "술에취한"],
        "무면허": ["무면허"],
    }

    for topic, keywords in topic_keywords.items():
        if any(keyword in q for keyword in keywords):
            topics.add(topic)

    return topics



def normalize_text(text: str) -> str:
    """검색어와 문서의 불필요한 공백을 제거한다."""
    return re.sub(r"\s+", "", text or "")


def is_relevant_to_accident(
    query: str,
    text: str,
    document_type: str = "",
) -> bool:
    """사고 상황과 문서 내용의 관련성을 검사한다."""

    normalized_query = normalize_text(query)
    normalized_text = normalize_text(text)

    if not normalized_query or not normalized_text:
        return False

    # 사고 상황별 동의어 및 유사 표현
    topic_keywords = {
        "신호": [
            "신호위반", "신호등", "적색신호", "적신호",
            "진행신호", "신호를위반", "신호준수",
        ],
        "교차로": [
            "교차로", "사거리", "십자교차로",
            "T자교차로", "교차점",
        ],
        "직진": [
            "직진", "직진차량", "직진차",
            "진행신호에따라진행", "직진하던",
        ],
        "좌회전": ["좌회전", "좌회전차량"],
        "우회전": ["우회전", "우회전차량"],
        "추돌": ["추돌", "후미충돌", "뒤에서충돌"],
        "차로변경": [
            "차로변경", "진로변경", "끼어들기",
        ],
        "보행자": ["보행자", "횡단보도"],
        "주차": ["주차", "정차"],
        "역주행": ["역주행", "중앙선침범"],
        "음주": ["음주운전", "술에취한"],
        "무면허": ["무면허"],
    }

    # 사용자가 입력한 상황에서 실제로 언급된 주제만 추출
    matched_topics = []

    for topic, keywords in topic_keywords.items():
        if any(
            normalize_text(keyword) in normalized_query
            for keyword in keywords
        ):
            matched_topics.append((topic, keywords))

    # 사고 유형을 특정할 수 없는 경우에는 임의로 탈락시키지 않는다.
    if not matched_topics:
        return True

    # 문서에 입력 상황의 주제 중 하나라도 나타나는지 확인
    for topic, keywords in matched_topics:
        if any(
            normalize_text(keyword) in normalized_text
            for keyword in keywords
        ):
            return True

    return False



# ==========================================
# 7. 관련 원문 검색
# ==========================================


def search_legal_documents(
    query: str,
    k: int = 10,
) -> list[Document]:
    """관련성이 확인된 법규와 판례를 각각 최대 하나씩 반환한다."""

    if not DB_DIR.exists():
        raise FileNotFoundError(
            "벡터 데이터베이스가 없습니다. 먼저 --ingest를 실행해 주세요."
        )

    vector_store = get_vector_store()
    selected_results = []

    normalized_query = normalize_text(query)

    # --------------------------------------
    # 1. 법규 검색
    # --------------------------------------

    law_types = [
        "도로교통법",
        "교통사고처리특례법",
        "자동차손해배상보장법",
    ]

    law_query = f"{normalized_query} 관련 법률 조항"
    relevant_laws = []

    for law_type in law_types:
        law_results = (
            vector_store.similarity_search_with_relevance_scores(
                law_query,
                k=k,
                filter={"document_type": law_type},
            )
        )

        for doc, score in law_results:
            if score < MIN_RELEVANCE_SCORE:
                continue

            if not is_relevant_to_accident(
                query,
                doc.page_content,
                law_type,
            ):
                continue

            citations = extract_legal_citations(doc.page_content)

            has_law_citation = any(
                "제" in citation and "조" in citation
                for citation in citations
            )

            if not has_law_citation:
                continue

            relevant_laws.append((doc, score))

    if relevant_laws:
        best_law = max(
            relevant_laws,
            key=lambda item: item[1],
        )[0]

        selected_results.append(best_law)


    # --------------------------------------
    # 2. 과실비율 인정기준 검색
    # --------------------------------------

    case_query = normalized_query

    case_results = (
        vector_store.similarity_search_with_relevance_scores(
            case_query,
            k=k,
            filter={"document_type": "과실비율 인정기준"},
        )
    )

    if case_results:
        best_case, best_score = max(
            case_results,
            key=lambda item: item[1],
        )

        best_case.metadata["search_score"] = best_score
        selected_results.append(best_case)

    return selected_results




# ==========================================
# 8. 검색 결과 출력
# ==========================================


def print_search_results(query: str) -> None:
    """검색된 법규와 과실비율 인정기준을 구분해 출력한다."""

    results = search_legal_documents(query)

    print("\n===== 관련 법규/판례 검색 결과 =====")
    print(f"검색 상황: {query}")

    laws = [
        doc for doc in results
        if doc.metadata.get("document_type") in LAW_TYPES
    ]

    cases = [
        doc for doc in results
        if doc.metadata.get("document_type") == "과실비율 인정기준"
    ]

    # 법규 출력
    print("\n===== 관련 법규 =====")

    if not laws:
        print("관련 법규를 찾지 못했습니다.")
    else:
        document = laws[0]
        citations = extract_legal_citations(document.page_content)

        print(f"출처: {document.metadata.get('source', '출처 정보 없음')}")
        print(f"페이지: {document.metadata.get('page', '페이지 정보 없음')}")

        law_citations = [
            citation for citation in citations
            if "제" in citation and "조" in citation
        ]

        print("인용 정보:")
        if law_citations:
            for citation in law_citations:
                print(f"- {citation}")
        else:
            print("- 명시적인 법 조항을 추출하지 못했습니다.")

        print("-" * 50)
        print(document.page_content)

    # 과실비율 인정기준 출력
    print("\n===== 과실비율 인정기준 / 판례 참고자료 =====")

    if not cases:
        print("관련 과실비율 인정기준을 찾지 못했습니다.")
    else:
        document = cases[0]
        citations = extract_legal_citations(document.page_content)

        print(f"출처: {document.metadata.get('source', '출처 정보 없음')}")
        print(f"페이지: {document.metadata.get('page', '페이지 정보 없음')}")

        case_citations = [
            citation for citation in citations
            if "선고" in citation and "판결" in citation
        ]

        print("판례 인용:")
        if case_citations:
            for citation in case_citations:
                print(f"- {citation}")
        else:
            print("- 이 문서에서 판례 인용을 추출하지 못했습니다.")

        print("-" * 50)
        print(document.page_content)

    print(
        "\n※ 검색 결과는 등록된 PDF에서 추출한 참고 자료이며, "
        "실제 사건의 과실비율이나 법률적 판단을 확정하지 않습니다."
    )

# ==========================================
# 9. 실행
# ==========================================


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--ingest",
        action="store_true",
        help="PDF를 읽어 벡터 데이터베이스에 저장",
    )

    parser.add_argument(
        "--search",
        type=str,
        help="검색할 사고 상황",
    )

    parser.add_argument(
        "--debug-search",
        type=str,
        help="검색 후보와 점수를 확인",
    )

    args = parser.parse_args()

    if args.ingest:
        ingest_pdf()

    elif args.debug_search:
        store = get_vector_store()
        query = args.debug_search

        for document_type in [
            "도로교통법",
            "교통사고처리특례법",
            "자동차손해배상보장법",
            "과실비율 인정기준",
        ]:
            print(f"\n===== {document_type} 검색 후보 =====")

            candidates = store.similarity_search_with_relevance_scores(
                query,
                k=5,
                filter={"document_type": document_type},
            )

            for index, (doc, score) in enumerate(candidates, start=1):
                print(f"\n후보 {index} / 점수: {score:.3f}")
                print(f"페이지: {doc.metadata.get('page')}")
                print(doc.page_content[:500])
                print("-" * 40)

    elif args.search:
        print_search_results(args.search)

    else:
        parser.print_help()
