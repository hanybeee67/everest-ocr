# services/ocr_parser.py

import os
import io
import re
import json
from google.cloud import vision 
from PIL import Image 
from datetime import datetime

# ============================================
# 1. OCR 지점명 정의
# ============================================
BRANCH_NAMES = {
    "동대문": ["에베레스트 동대문", "창신동", "동대문점"],
    "굿모닝시티": ["에베레스트 굿모닝", "굿모닝시티점"],
    "영등포": ["에베레스트 영등포", "영등포점"],
    "양재": ["에베레스트 양재", "오룡빌딩", "양재점"],
    "수원 영통": ["에베레스트 수원", "청명남로", "영통점"],
    "동탄": ["에베레스트 동탄", "롯데백화점 동탄", "동탄점"],
    "룸비니": ["룸비니", "동묘역", "자매식당"],
}

# ============================================
# 2. OCR 텍스트 추출 함수
# ============================================
def detect_text_from_receipt(image_path):
    """ Google Cloud Vision API를 호출하여 영수증 텍스트를 추출합니다. """
    try:
        # 환경 변수에서 JSON 키 정보를 읽어 클라이언트 생성
        credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        if not credentials_json:
            print("ERROR: GOOGLE_APPLICATION_CREDENTIALS_JSON 환경 변수가 설정되지 않았습니다.")
            return None
            
        # JSON 문자열을 파싱하여 인증 정보로 사용
        client = vision.ImageAnnotatorClient.from_service_account_info(
            info=json.loads(credentials_json)
        )
    except Exception as e:
        print(f"Error loading credentials: {e}")
        return None

    with io.open(image_path, 'rb') as image_file:
        content = image_file.read()

    image = vision.Image(content=content)

    # DOCUMENT_TEXT_DETECTION 사용
    response = client.text_detection(image=image)
    
    if not response.text_annotations:
        return None
        
    # 첫 번째 요소(인덱스 0)가 전체 텍스트를 포함합니다.
    return response.text_annotations[0].description

# ============================================
# 3. 텍스트 파싱 함수
# ============================================
def parse_receipt_text(ocr_text):
    """ OCR로 추출된 텍스트에서 영수증 번호, 지점, 금액을 추출합니다. """
    data = {
        "receipt_no": None,
        "branch_paid": "미확인 지점",
        "amount": 0,
    }
    
    # 텍스트 정규화: 모든 띄어쓰기 제거, 소문자화, 줄바꿈 제거
    clean_text = ocr_text.replace('\n', ' ').replace(' ', '').lower()
    
    
    # --- A. 지점명 추출 ---
    for official_name, keywords in BRANCH_NAMES.items():
        for keyword in keywords:
            if keyword.lower().replace(' ', '') in clean_text:
                data["branch_paid"] = official_name
                break
        if data["branch_paid"] != "미확인 지점":
            break
            
            
    # --- B. 금액 (Amount) 추출 ---
    # 패턴: (합계|결제금액|total|tot|금액|vat포함) 주변의 숫자 (\d[\d,]+)를 찾습니다.
    amount_match = re.search(r'(합계|결제금액|total|tot|금액)[:\s]*(\d[\d,]+)', clean_text)
    if amount_match:
        data["amount"] = int(amount_match.group(2).replace(',', ''))
        
    # 금액이 추출되지 않았을 경우, 4자리 이상 숫자 중 가장 큰 값을 금액으로 가정
    if data["amount"] == 0:
        all_numbers = re.findall(r'\d{4,}', clean_text) 
        if all_numbers:
            data["amount"] = max([int(n) for n in all_numbers if int(n) > 500]) # 500원 이상만 고려
            
            
    # --- C. 영수증 번호 (Receipt No) 추출 ---
    # 패턴: (승인번호|일련번호|no) 주변의 8~12자리의 숫자 (카드 승인번호 패턴)
    receipt_no_match = re.search(r'(승인번호|일련번호|no)[:_]?[-\s]?(\d{8,12})', clean_text)
    if receipt_no_match:
        data["receipt_no"] = receipt_no_match.group(2).replace('-', '')
    else:
        # 영수증 번호가 없으면 OCR 텍스트 해시값을 사용 (중복 체크 보장 안됨)
        data["receipt_no"] = "PARSE_FAIL_" + str(abs(hash(clean_text)))[:10]
        
    return data