import os
import io
import re
import json
from google.cloud import vision
from google.oauth2 import service_account
from datetime import datetime

# 지점명 리스트
BRANCH_NAMES = {
    "동대문": ["에베레스트 동대문", "창신동", "동대문점", "종로구"],
    "굿모닝시티": ["에베레스트 굿모닝", "굿모닝시티점", "장충단로"],
    "영등포": ["에베레스트 영등포", "영등포점", "경인로"],
    "양재": ["에베레스트 양재", "오룡빌딩", "양재점", "강남대로"],
    "수원 영통": ["에베레스트 수원", "청명남로", "영통점"],
    "동탄": ["에베레스트 동탄", "롯데백화점 동탄", "동탄점"],
    "룸비니": ["룸비니", "동묘역", "자매식당"],
}

# 1. 구글 API를 이용해서 이미지에서 글자를 읽어오는 함수 (이게 지워졌던 겁니다)
def detect_text_from_receipt(image_path):
    # 환경 변수 확인
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

        # 파일 삭제
        if os.path.exists(image_path):
            os.remove(image_path)

        if texts:
            # ★ 디버깅용 로그
            raw_text = texts[0].description
            print(f"\n====== [OCR RAW DATA START] ======\n{raw_text}\n====== [OCR RAW DATA END] ======\n")
            return raw_text
        else:
            return None

    except Exception as e:
        if os.path.exists(image_path):
            os.remove(image_path)
        raise e 


# 2. 읽어온 글자에서 지점과 금액을 분석하는 함수 (아까 수정한 100원 무시 기능 포함됨)
def parse_receipt_text(ocr_text):
    data = { "receipt_no": None, "branch_paid": "미확인 지점", "amount": 0 }
    
    if not ocr_text: return data

    # 1. 텍스트 정리 (공백 제거, 소문자 변환)
    clean_text = ocr_text.replace(' ', '').lower()
    
    # 2. 지점명 찾기
    for official_name, keywords in BRANCH_NAMES.items():
        for keyword in keywords:
            if keyword.replace(' ', '') in clean_text:
                data["branch_paid"] = official_name
                break
        if data["branch_paid"] != "미확인 지점": break
            
    # 3. 금액 찾기 (수정됨: 100원 미만 무시)
    amount_keywords = [
        "합계", "결제금액", "청구금액", "받을금액", "승인금액", 
        "매출금액", "total", "tot", "amount", "금액", "계"
    ]
    
    found_amount = False
    
    # 방법 A: 키워드("합계" 등) 주변 숫자 찾기
    for keyword in amount_keywords:
        pattern = re.compile(rf'{keyword}[^0-9]*([0-9,]+)')
        match = pattern.search(clean_text)
        if match:
            raw_num = match.group(1).replace(',', '')
            if raw_num.isdigit():
                val = int(raw_num)
                # [핵심] 100원 이상만 인정 (수량 1 무시)
                if val >= 100: 
                    data["amount"] = val
                    found_amount = True
                    print(f"💰 금액 인식 성공 (키워드 '{keyword}'): {data['amount']}")
                    break
    
    # 방법 B: 전체 탐색 (100원 이상인 가장 큰 숫자)
    if not found_amount or data["amount"] == 0:
        candidates = re.findall(r'([0-9,]+)원', ocr_text)
        if not candidates:
            candidates = re.findall(r'([0-9,]{4,})', ocr_text)

        max_val = 0
        for cand in candidates:
            val_str = cand.replace(',', '').replace('.', '')
            if val_str.isdigit():
                val = int(val_str)
                # 100원 ~ 1000만원 사이
                if 100 <= val < 10000000: 
                    if val > max_val:
                        max_val = val
        
        if max_val > 0:
            data["amount"] = max_val
            print(f"💰 최대 숫자 추정 금액: {data['amount']}")

    # 4. 승인번호 찾기
    receipt_no_match = re.search(r'(승인번호|일련번호|no|number)[:.\s]*([0-9-]{8,20})', clean_text)
    if receipt_no_match:
        data["receipt_no"] = receipt_no_match.group(2).replace('-', '')
    else:
        data["receipt_no"] = "AUTO_" + datetime.now().strftime("%Y%m%d%H%M%S")

    return data