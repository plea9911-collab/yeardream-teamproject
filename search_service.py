import os

from dotenv import load_dotenv
from tavily import TavilyClient
from langchain_core.prompts import PromptTemplate

# 1. 환경변수 불러오기
load_dotenv()

api_key = os.getenv("TAVILY_API_KEY")

if not api_key:
    raise ValueError("TAVILY_API_KEY 를 .env 에서 찾을 수 없습니다.")

client = TavilyClient(api_key=api_key)


# 2. 사고정보 4개를 검색어로 조합하는 템플릿
search_prompt = PromptTemplate.from_template(
    """
    자동차 사고 과실비율 인정기준을 검색한다.

    사고상황 : {accident_situation}
    상세 사고상황 : {detailed_situation}
    진행방향 : {direction}
    세부사항 : {details}

    위 사고와 유사한 사고의 과실비율 및 판단 근거를 찾아라.

    """
)


# 3. 공식 과실비율 정보포털 검색함수

def search_official_portal(
        accident_situation: str,
        detailed_situation: str,
        direction: str,
        details: str
):
   # 사고정보 4개를 하나의 검색어로 조합

   query = search_prompt.format(
      accident_situation=accident_situation,
      detailed_situation=detailed_situation,
      direction=direction,
      details=details,
   )

   print("\n=====생성된 검색어=====")
   print(query)

   # 공식포털 도메인으로 검색범위 제한
   results = client.search(
      query=query,
      max_results=5,
      include_domains=["accident.knia.or.kr"],
   )

   return results


# 4. 테스트 실행
if __name__ == "__main__":

    results = search_official_portal(
        accident_situation="교차로(+자로, T자로 등) 사고",
        detailed_situation="양쪽 신호등 있는 교차로",
        direction="직진 대 직진 사고 - 사고차량이 측면에서 진입",
        details="녹색직진 대 적색직진",
    )

    print("\n=====공식 포털 검색 결과=====")

    for index, result in enumerate(
        results.get("results", []),
        start=1
    ):
        print(f"\n[{index}] {result['title']}")
        print(f"URL: {result['url']}")
        print(f"내용: {result.get('content', '')[:300]}")

    if not results.get("results"):
        print("공식 포털에서 검색 결과를 찾지 못했습니다.")

    print("\n=====테스트 종료=====")
