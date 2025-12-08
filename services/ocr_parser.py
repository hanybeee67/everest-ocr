import os
import io
import re
import json
from google.cloud import vision
from google.oauth2 import service_account
from datetime import datetime

BRANCH_NAMES = {
    "동대문": ["에베레스트 동대문", "창신동", "동대문점"],
    "굿모닝시티": ["에베레스트 굿모닝", "굿모닝시티점"],
    "영등포": ["에베레스트 영등포", "영등포점"],
    "양재": ["에베레스트 양재", "오룡빌딩", "양재점"],
    "수원 영통": ["에베레스트 수원", "청명남로", "영통점"],
    "동탄": ["에베레스트 동탄", "롯데백화점 동탄", "동탄점"],
    "룸비니": ["룸비니", "동묘역", "자매식당"],
}

def detect_text_from_receipt(image_path):
    # ★★★ [수정됨] 에러를 화면에 보여주기 위해 try-except 방식을 변경했습니다.
    
    # 1. 환경 변수 확인
    credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if not credentials_json:
        # 키가 없으면 바로 에러 발생시킴
        raise Exception("구글 키(JSON)가 Render 환경변수에 등록되지 않았습니다!")

    # 2. 인증 및 클라이언트 생성
    try:
        credentials_info = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(credentials_info)
        client = vision.ImageAnnotatorClient(credentials=credentials)
    except Exception as e:
        raise Exception(f"구글 키(JSON) 형식이 잘못되었습니다. 복사 과정에서 잘렸는지 확인해주세요. 에러내용: {e}")

    # 3. 이미지 읽기 및 요청
    try:
        with io.open(image_path, 'rb') as image_file:
            content = image_file.read()

        image = vision.Image(content=content)
        response = client.text_detection(image=image)
        
        # ★ 구글 API 자체 에러 체크 (API 미사용 설정 등)
        if response.error.message:
            raise Exception(f"구글 API 에러: {response.error.message}")

        texts = response.text_annotations

        # 파일 삭제
        if os.path.exists(image_path):
            os.remove(image_path)

        if texts:
            return texts[0].description
        else:
            return None

    except Exception as e:
        # ★★★ 여기가 핵심: 에러를 숨기지 않고 app.py로 던집니다.
        raise e 


def parse_receipt_text(ocr_text):
    data = { "receipt_no": None, "branch_paid": "미확인 지점", "amount": 0 }
    
    if not ocr_text: return data

    clean_text = ocr_text.replace('\n', ' ').replace(' ', '').lower()
    
    for official_name, keywords in BRANCH_NAMES.items():
        for keyword in keywords:
            if keyword.replace(' ', '') in clean_text:
                data["branch_paid"] = official_name
                break
        if data["branch_paid"] != "미확인 지점": break
            
    amount_match = re.search(r'(합계|결제금액|total|tot|금액)[:\s]*([0-9,]+)', clean_text)
    if amount_match:
        raw_amount = amount_match.group(2).replace(',', '')
        if raw_amount.isdigit(): data["amount"] = int(raw_amount)
        
    if data["amount"] == 0:
        candidates = re.findall(r'([0-9,]+)원', ocr_text)
        for cand in candidates:
            val = int(cand.replace(',', ''))
            if val > data["amount"]: data["amount"] = val

    receipt_no_match = re.search(r'(승인번호|일련번호|no)[:.\s]*([0-9-]{8,20})', clean_text)
    if receipt_no_match:
        data["receipt_no"] = receipt_no_match.group(2).replace('-', '')
    else:
        data["receipt_no"] = "TEMP_" + datetime.now().strftime("%H%M%S")

    return data