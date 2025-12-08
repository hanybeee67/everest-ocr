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
            # ★ 디버깅용: 구글이 읽은 전체 텍스트를 로그에 찍어봅니다.
            raw_text = texts[0].description
            print(f"\n====== [OCR RAW DATA START] ======\n{raw_text}\n====== [OCR RAW DATA END] ======\n")
            return raw_text
        else:
            return None

    except Exception as e:
        if os.path.exists(image_path):
            os.remove(image_path)
        raise e 


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
            
    # 3. 금액 찾기 (업그레이드 버전)
    # 찾을 키워드 대폭 추가
    amount_keywords = [
        "합계", "결제금액", "청구금액", "받을금액", "승인금액", 
        "매출금액", "total", "tot", "amount", "금액", "계"
    ]
    
    found_amount = False
    
    # 방법 A: "합계 : 50,000" 패턴 찾기
    for keyword in amount_keywords:
        # 패턴: 키워드 + (특수문자/공백) + 숫자 + (원)
        pattern = re.compile(rf'{keyword}[^0-9]*([0-9,]+)')
        match = pattern.search(clean_text)
        if match:
            raw_num = match.group(1).replace(',', '')
            if raw_num.isdigit() and int(raw_num) > 0:
                data["amount"] = int(raw_num)
                found_amount = True
                print(f"💰 금액 인식 성공 (키워드 '{keyword}'): {data['amount']}")
                break
    
    # 방법 B: 못 찾았으면, 텍스트 전체에서 가장 큰 숫자를 찾음 (단, 날짜/전화번호 제외)
    if not found_amount or data["amount"] == 0:
        print("⚠️ 키워드로 금액을 못 찾음. 숫자 탐색 모드 가동.")
        # '원' 글자 앞에 있는 숫자들 우선 검색
        candidates = re.findall(r'([0-9,]+)원', ocr_text)
        
        # '원'이 없어도 그냥 숫자 덩어리들 검색 (4자리 이상)
        if not candidates:
            candidates = re.findall(r'([0-9,]{4,})', ocr_text)

        max_val = 0
        for cand in candidates:
            # 쉼표 제거
            val_str = cand.replace(',', '').replace('.', '')
            if val_str.isdigit():
                val = int(val_str)
                # 8자리 이상은 전화번호나 승인번호일 확률 높음 -> 제외
                # 100원 이하는 제외
                if 100 < val < 10000000: 
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
        # 못 찾으면 날짜+시간으로 대체
        data["receipt_no"] = "AUTO_" + datetime.now().strftime("%Y%m%d%H%M%S")

    return data