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

    # 1. 지점명 찾기 (공백 무시하고 전체에서 탐색)
    clean_text_all = ocr_text.replace(' ', '').lower()
    for official_name, keywords in BRANCH_NAMES.items():
        for keyword in keywords:
            if keyword.replace(' ', '') in clean_text_all:
                data["branch_paid"] = official_name
                break
        if data["branch_paid"] != "미확인 지점": break
            
    # 2. 금액 찾기 (★수정 핵심: 줄의 맨 오른쪽 끝 숫자 선택)
    # 영수증 구조: [메뉴명] [단가] [수량] [금액] -> 맨 뒤에 있는게 정답
    
    amount_keywords = [
        "합계", "결제금액", "청구금액", "합계금액", "승인금액", 
        "매출금액", "total", "tot", "amount", "금액", "계"
    ]
    
    lines = ocr_text.split('\n') # 한 줄씩 쪼개기
    found_amount = False

    for line in lines:
        # 이 줄에 '합계'나 '금액' 같은 단어가 있는지 확인
        if any(keyword in line.replace(' ', '').lower() for keyword in amount_keywords):
            
            # 이 줄에 있는 "모든 숫자 덩어리"를 찾습니다. (콤마 포함)
            # 예: "Butter Chicken 15,000 1 15,000" -> ['15,000', '1', '15,000']
            numbers = re.findall(r'([0-9,]+)', line)
            
            if numbers:
                # ★ 핵심: 리스트의 맨 마지막([-1]) 숫자가 바로 '오른쪽 끝 금액'입니다.
                last_number_str = numbers[-1]
                
                # 콤마 제거하고 숫자로 변환
                clean_num = last_number_str.replace(',', '')
                
                if clean_num.isdigit():
                    val = int(clean_num)
                    
                    # 100원 이상이고 1000만원 이하인 경우만 인정 (이상한 숫자 방지)
                    if 100 <= val < 10000000:
                        data["amount"] = val
                        found_amount = True
                        print(f"💰 줄의 맨 오른쪽 끝 금액 발견: {val}")
                        break
    
    # 위에서 못 찾았다면, 최후의 수단으로 전체 텍스트에서 가장 큰 숫자 찾기
    if not found_amount:
        print("⚠️ 합계 줄을 못 찾음. 전체 중 가장 큰 숫자 탐색.")
        candidates = re.findall(r'([0-9,]{4,})', ocr_text)
        max_val = 0
        for cand in candidates:
            val_str = cand.replace(',', '').replace('.', '')
            if val_str.isdigit():
                val = int(val_str)
                # 전화번호 등 제외 필터
                if 100 <= val < 5000000: 
                    if val > max_val:
                        max_val = val
        if max_val > 0:
            data["amount"] = max_val

    # 3. 승인번호 찾기
    receipt_no_match = re.search(r'(승인번호|일련번호|no|number)[:.\s]*([0-9-]{8,20})', clean_text_all)
    if receipt_no_match:
        data["receipt_no"] = receipt_no_match.group(2).replace('-', '')
    else:
        data["receipt_no"] = "AUTO_" + datetime.now().strftime("%Y%m%d%H%M%S")

    return data