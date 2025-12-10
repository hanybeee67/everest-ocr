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
            # 디버깅을 위해 전체 텍스트 로그 출력
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
            
    # 2. 금액 찾기 (관리자님 특별 지시: 합계 줄의 오른쪽 끝 숫자!!)
    
    # 찾을 키워드 (공백 없이 매칭할 것임)
    amount_keywords = ["합계", "결제금액", "청구금액", "받을금액", "승인금액", "매출금액", "total", "tot", "amount", "금액"]
    
    lines = ocr_text.split('\n')
    found_amount = False

    print("\n🔍 [금액 탐색 시작]")

    for line in lines:
        # 정확한 매칭을 위해 특수문자와 공백을 다 뺀 '순수 글자'만 봅니다.
        # 예: "합 계 : 50,000" -> "합계50000" (이렇게 만들어서 키워드를 찾음)
        pure_line_char = re.sub(r'[^가-힣a-zA-Z]', '', line) # 한글과 영어만 남김
        
        # 키워드가 이 줄에 숨어있는지 확인
        if any(k in pure_line_char for k in amount_keywords):
            print(f"👉 후보 줄 발견: {line}")
            
            # 이 줄에 있는 숫자들을 다 긁어모읍니다.
            numbers = re.findall(r'([0-9,]+)', line)
            
            # 숫자가 있다면, 맨 뒤(오른쪽)부터 거꾸로 검사합니다.
            if numbers:
                for num_str in reversed(numbers):
                    clean_num = num_str.replace(',', '')
                    if clean_num.isdigit():
                        val = int(clean_num)
                        
                        # 100원 이상인 것만 '금액'으로 인정 (페이지 번호나 수량 1 무시)
                        if 100 <= val < 20000000:
                            data["amount"] = val
                            found_amount = True
                            print(f"✅ [성공] 오른쪽 끝에서 유효한 금액 찾음: {val}")
                            break # 찾았으면 숫자 루프 종료
                
                if found_amount:
                    break # 찾았으면 줄 루프 종료

    # 3. 키워드로 못 찾았을 때 비상 대책
    if not found_amount:
        print("⚠️ 합계 줄을 못 찾음. 전체 중 가장 큰 숫자 탐색.")
        candidates = re.findall(r'([0-9,]{4,})', ocr_text)
        max_val = 0
        for cand in candidates:
            val_str = cand.replace(',', '').replace('.', '')
            if val_str.isdigit():
                val = int(val_str)
                if 100 <= val < 5000000: 
                    if val > max_val:
                        max_val = val
        if max_val > 0:
            data["amount"] = max_val
            print(f"💰 비상 대책으로 찾은 금액: {data['amount']}")

    # 4. 승인번호 찾기
    receipt_no_match = re.search(r'(승인번호|일련번호|no|number)[:.\s]*([0-9-]{8,20})', clean_text_all)
    if receipt_no_match:
        data["receipt_no"] = receipt_no_match.group(2).replace('-', '')
    else:
        data["receipt_no"] = "AUTO_" + datetime.now().strftime("%Y%m%d%H%M%S")

    return data