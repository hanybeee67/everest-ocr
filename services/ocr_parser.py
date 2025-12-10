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
            return texts[0].description
        else:
            return None

    except Exception as e:
        if os.path.exists(image_path):
            os.remove(image_path)
        raise e 

def parse_receipt_text(ocr_text):
    data = { "receipt_no": None, "branch_paid": "미확인 지점", "amount": 0 }
    if not ocr_text: return data

    # 1. 지점명 찾기 (전체 텍스트에서 검색 - 공백 무시하고 찾기)
    clean_text_all = ocr_text.replace(' ', '').lower()
    for official_name, keywords in BRANCH_NAMES.items():
        for keyword in keywords:
            if keyword.replace(' ', '') in clean_text_all:
                data["branch_paid"] = official_name
                break
        if data["branch_paid"] != "미확인 지점": break
            
    # 2. 금액 찾기 (★수정됨: 공백 유지 + 오른쪽 끝 숫자 우선)
    # "금액"이라는 단어는 "주문금액", "할인금액" 등 여기저기 너무 많이 쓰여서 오해를 낳으므로 우선순위를 낮춥니다.
    # 진짜 합계일 확률이 높은 키워드들
    primary_keywords = ["합계", "결제금액", "청구금액", "받을금액", "승인금액", "매출금액", "total", "tot"]
    secondary_keywords = ["금액", "amount"] # 최후의 수단
    
    lines = ocr_text.split('\n') # 줄 단위로 쪼개기
    found_amount = False

    def find_amount_in_lines(target_keywords):
        for line in lines:
            # 공백을 없애지 않고 그대로 둡니다! (15000 1 붙는 것 방지)
            clean_line = line.lower() 
            
            for keyword in target_keywords:
                if keyword in clean_line:
                    # 해당 줄에 있는 모든 숫자들을 찾습니다 (쉼표 포함)
                    # 예: "합계금액 : 15,000" -> ['15,000']
                    # 예: "Butter Chicken 15,000 1 15,000" -> ['15,000', '1', '15,000']
                    numbers = re.findall(r'([0-9,]+)', line)
                    
                    # 뒤에서부터 검사 (보통 합계는 맨 오른쪽에 있음)
                    for num_str in reversed(numbers):
                        raw_num = num_str.replace(',', '')
                        if raw_num.isdigit():
                            val = int(raw_num)
                            # 100원 이상 ~ 1000만원 이하 (수량 1 같은거 거르기 위함)
                            if 100 <= val < 10000000:
                                return val
        return None

    # 1차 시도: 확실한 키워드(합계, total 등)로 찾기
    amount_found = find_amount_in_lines(primary_keywords)
    if amount_found:
        data["amount"] = amount_found
        found_amount = True
        print(f"💰 1차 키워드 탐색 성공: {data['amount']}")

    # 2차 시도: 1차 실패시 '금액' 같은 약한 키워드로 찾기
    if not found_amount:
        amount_found = find_amount_in_lines(secondary_keywords)
        if amount_found:
            data["amount"] = amount_found
            found_amount = True
            print(f"💰 2차 키워드 탐색 성공: {data['amount']}")
    
    # 3차 시도: 키워드 다 실패하면 전체에서 가장 큰 숫자 (Fallback)
    if not found_amount:
        print("⚠️ 키워드 탐색 실패. 전체 숫자 중 추정.")
        # 전화번호 등은 공백 제거된 전체 텍스트에서 패턴으로 거르는게 나음
        # 하지만 여기선 간단히 4자리 이상 숫자 중 큰 것으로
        candidates = re.findall(r'([0-9,]{4,})', ocr_text) 
        max_val = 0
        for cand in candidates:
            val_str = cand.replace(',', '').replace('.', '')
            if val_str.isdigit():
                val = int(val_str)
                # 전화번호(010...)나 사업자번호 방지 위해 범위 제한
                if 100 <= val < 5000000: 
                    if val > max_val:
                        max_val = val
        if max_val > 0:
            data["amount"] = max_val
            print(f"💰 최대 숫자 추정: {data['amount']}")

    # 3. 승인번호 찾기
    receipt_no_match = re.search(r'(승인번호|일련번호|no|number)[:.\s]*([0-9-]{8,20})', clean_text_all)
    if receipt_no_match:
        data["receipt_no"] = receipt_no_match.group(2).replace('-', '')
    else:
        data["receipt_no"] = "AUTO_" + datetime.now().strftime("%Y%m%d%H%M%S")

    return data