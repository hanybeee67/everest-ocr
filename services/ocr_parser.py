import os
import io
import re
import json
from google.cloud import vision
from google.oauth2 import service_account
from datetime import datetime

BRANCH_NAMES = {
    "동대문": ["에베레스트 동대문", "창신동", "동대문점", "종로구"],
    "굿모닝시티": ["에베레스트 굿모닝", "굿모닝시티점", "장충단로"],
    "영등포": ["에베레스트 영등포", "영등포점", "경인로"],
    "양재": ["에베레스트 양재", "오룡빌딩", "양재점", "강남대로"],
    "수원 영통": ["에베레스트 수원", "청명남로", "영통점"],
    "동탄": ["에베레스트 동탄", "롯데백화점 동탄", "동탄점"],
    "룸비니": ["룸비니", "동묘역", "자매식당"],
}

def detect_text_from_receipt(image_path):
    credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if not credentials_json:
        raise Exception("구글 키(JSON)가 Render 환경변수에 등록되지 않았습니다!")

    try:
        credentials_info = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(credentials_info)
        client = vision.ImageAnnotatorClient(credentials=credentials)
    except Exception as e:
        raise Exception(f"구글 키 오류: {e}")

    try:
        with io.open(image_path, 'rb') as image_file:
            content = image_file.read()

        image = vision.Image(content=content)
        response = client.text_detection(image=image)
        
        if response.error.message:
            raise Exception(f"구글 API 에러: {response.error.message}")

        texts = response.text_annotations
        if os.path.exists(image_path):
            os.remove(image_path)

        if texts:
            # 디버깅용: 전체 텍스트 로그
            full_text = texts[0].description
            print(f"\n[OCR 원본 데이터]\n{full_text}\n[OCR 끝]\n")
            return full_text
        else:
            return None

    except Exception as e:
        if os.path.exists(image_path):
            os.remove(image_path)
        raise e 

def parse_receipt_text(ocr_text):
    data = { "receipt_no": None, "branch_paid": "미확인 지점", "amount": 0 }
    if not ocr_text: return data

    # 1. 지점명 찾기
    clean_text_all = ocr_text.replace(' ', '').lower()
    for official_name, keywords in BRANCH_NAMES.items():
        for keyword in keywords:
            if keyword.replace(' ', '') in clean_text_all:
                data["branch_paid"] = official_name
                break
        if data["branch_paid"] != "미확인 지점": break
            
    # 2. 금액 찾기 (관리자님 지시: 오른쪽 옆에 있는 숫자 필사적으로 찾기)
    
    # 띄어쓰기 무시하고 찾을 키워드들
    keywords_list = ["합계", "결제금액", "청구금액", "받을금액", "승인금액", "매출금액", "total", "tot", "amount"]
    
    lines = ocr_text.split('\n')
    found_amount = False

    # [보조 함수] 한 줄의 텍스트에서 '맨 오른쪽'에 있는 유효한 금액 추출
    def get_amount_from_line(text):
        # 숫자만 추출 (쉼표, 마침표 포함)
        numbers = re.findall(r'([0-9,.]+)', text)
        if numbers:
            # 뒤에서부터 확인 (오른쪽 끝이 진짜 금액일 확률 높음)
            for num_str in reversed(numbers):
                # 쉼표(,) 제거. 마침표(.)도 제거 (가끔 52.500으로 인식됨)
                clean_num = num_str.replace(',', '').replace('.', '')
                if clean_num.isdigit():
                    val = int(clean_num)
                    # 100원 ~ 5천만원 사이 (수량 1, 페이지 번호 등 제외)
                    if 100 <= val < 50000000:
                        return val
        return None

    print("\n🔍 [금액 탐색 시작 - 오른쪽 끝 집중]")

    for i in range(len(lines)):
        line = lines[i]
        # 공백/특수문자 제거 후 키워드 확인 ("합 계  금 액" -> "합계금액")
        pure_line = re.sub(r'[^가-힣a-zA-Z]', '', line) 

        if any(k in pure_line for k in keywords_list):
            print(f"👉 키워드 발견(L{i}): {line}")
            
            # [1단계] 바로 그 줄의 오른쪽 끝 확인
            amount = get_amount_from_line(line)
            if amount:
                data["amount"] = amount
                found_amount = True
                print(f"✅ (같은 줄) 오른쪽 끝 금액 발견: {amount}")
                break
            
            # [2단계] 그 줄에 없으면? 공백 때문에 다음 줄로 밀렸을 수 있음. 바로 아래 2줄까지 뒤짐.
            # "합계" 찾았는데 옆이 비어있으면 무조건 아래에 숫자가 있다고 가정
            print("   ↳ 같은 줄에 없음. 아래 줄 수색 시작.")
            for j in range(1, 3): # 바로 아래(1), 그 다음 아래(2) 까지 확인
                if i + j < len(lines):
                    next_line = lines[i+j]
                    amount_next = get_amount_from_line(next_line)
                    if amount_next:
                        data["amount"] = amount_next
                        found_amount = True
                        print(f"✅ (아래 {j}번째 줄) 금액 발견: {amount_next}")
                        break
            if found_amount: break

    # 3. 키워드 탐색 실패 시 비상 대책
    if not found_amount:
        print("⚠️ 키워드로 못 찾음. '금액' 단어 포함 줄 재검색.")
        # '금액'이라는 단어가 들어간 줄을 한번 더 봅니다 (단가, 수량 있는 헤더 제외)
        for line in lines:
            if ("금액" in line or "amount" in line.lower()) and "수량" not in line and "단가" not in line:
                amount = get_amount_from_line(line)
                if amount:
                    data["amount"] = amount
                    found_amount = True
                    print(f"✅ '금액' 줄에서 발견: {amount}")
                    break
        
        # 그래도 없으면 전체 최대값
        if not found_amount:
            print("🚨 전체 숫자 중 최대값 추정.")
            candidates = re.findall(r'([0-9,]{4,})', ocr_text)
            max_val = 0
            for cand in candidates:
                val_str = cand.replace(',', '').replace('.', '')
                if val_str.isdigit():
                    val = int(val_str)
                    if 100 <= val < 10000000: 
                        if val > max_val:
                            max_val = val
            if max_val > 0:
                data["amount"] = max_val
                print(f"💰 최대 숫자 추정: {data['amount']}")

    # 4. 승인번호 찾기
    receipt_no_match = re.search(r'(승인번호|일련번호|no|number)[:.\s]*([0-9-]{8,20})', clean_text_all)
    if receipt_no_match:
        data["receipt_no"] = receipt_no_match.group(2).replace('-', '')
    else:
        data["receipt_no"] = "AUTO_" + datetime.now().strftime("%Y%m%d%H%M%S")

    return data