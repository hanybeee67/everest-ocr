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
            # 전체 텍스트 로그 (디버깅용)
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
            
    # 2. 금액 찾기
    
    # ★ 추가된 키워드: "카드결제액", "결제액" (롯데백화점 대응)
    keywords_list = ["합계", "결제금액", "청구금액", "받을금액", "승인금액", "매출금액", "total", "tot", "amount", "카드결제액", "결제액"]
    
    lines = ocr_text.split('\n')
    found_amount = False

    # [보조 함수] 한 줄에서 오른쪽 끝에 있는 유효한 금액 추출
    def get_amount_from_line(text):
        # 1. 승인번호, 전화번호 등이 포함된 줄은 위험하므로 거름 (단, 키워드가 명확히 있는 줄이면 통과)
        is_risky_line = any(bad_word in text for bad_word in ["승인번호", "가맹점", "사업자", "Tel", "TEL", "문의"])
        
        numbers = re.findall(r'([0-9,.]+)', text)
        if numbers:
            for num_str in reversed(numbers):
                clean_num = num_str.replace(',', '').replace('.', '')
                if clean_num.isdigit():
                    val = int(clean_num)
                    # 100원 ~ 5천만원
                    if 100 <= val < 50000000:
                        # 위험한 줄인데 숫자가 8자리 이상(승인번호 의심)이면 무시
                        if is_risky_line and len(clean_num) >= 8:
                            continue
                        return val
        return None

    print("\n🔍 [금액 탐색 시작]")

    for i in range(len(lines)):
        line = lines[i]
        # 공백/특수문자 제거 ("합   계" -> "합계", "카 드 결 제 액" -> "카드결제액")
        pure_line = re.sub(r'[^가-힣a-zA-Z]', '', line) 

        if any(k in pure_line for k in keywords_list):
            print(f"👉 키워드 발견(L{i}): {line}")
            
            # [1단계] 같은 줄 확인
            amount = get_amount_from_line(line)
            if amount:
                data["amount"] = amount
                found_amount = True
                print(f"✅ (같은 줄) 금액 발견: {amount}")
                break
            
            # [2단계] 아래 2줄까지 확인 (공백 때문에 밀린 경우)
            print("   ↳ 같은 줄에 없음. 아래 줄 수색.")
            for j in range(1, 3):
                if i + j < len(lines):
                    next_line = lines[i+j]
                    amount_next = get_amount_from_line(next_line)
                    if amount_next:
                        data["amount"] = amount_next
                        found_amount = True
                        print(f"✅ (아래 {j}번째 줄) 금액 발견: {amount_next}")
                        break
            if found_amount: break

    # 3. 비상 대책: 전체 숫자 중 최대값 (단, 승인번호 제외!)
    if not found_amount:
        print("⚠️ 키워드 실패. '승인번호' 제외하고 최대값 추정.")
        max_val = 0
        
        for line in lines:
            # ★ 핵심 수정: 승인번호, 전화번호, 날짜가 있는 줄은 아예 무시합니다.
            if any(bad in line for bad in ["승인", "번호", "Tel", "TEL", "사업자", "Date", "Time", "날짜"]):
                continue

            candidates = re.findall(r'([0-9,]+)', line)
            for cand in candidates:
                val_str = cand.replace(',', '').replace('.', '')
                if val_str.isdigit():
                    val = int(val_str)
                    # 100원 ~ 5천만원
                    if 100 <= val < 50000000: 
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