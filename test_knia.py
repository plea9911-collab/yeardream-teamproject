
import requests

URL = "https://accident.knia.or.kr/selectAccidentStep"

def get_accident_steps(group_code: str):
    response = requests.post(
        URL,
        data={"GROUPCODE": group_code},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


for group_code in ("1", "2", "3"):
    print(f"\n{'=' * 20} GROUPCODE={group_code} {'=' * 20}")

    try:
        items = get_accident_steps(group_code)
        print("조회 항목 수:", len(items))

        for item in items:
            print(
                f"단계={item.get('dpth')} | "
                f"ID={item.get('acdNttyId')} | "
                f"상위 ID={item.get('uppertyId')} | "
                f"사고 유형={item.get('acdNtty')} | "
                f"도표번호={item.get('chartNo')}"
            )

    except (requests.RequestException, ValueError) as exc:
        print("조회 실패:", exc)
