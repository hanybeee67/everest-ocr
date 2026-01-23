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

# [Security] 사업자등록번호 리스트 (가짜 영수증 방지)
VALID_BIZ_NUMBERS = [
    "101-05-48485", # 동대문 01
    "107-14-87718", # 영등포 02
    "201-86-18242", # 굿모닝 03
    "769-85-00538", # 수원 04
    "436-85-01826", # 동탄 07
    "612-85-18896", # 양재 08
    "715-85-00297", # 하남스타필드
    "637-85-00323", # 고양스타필드(폐점)
    "502-85-42712"  # 룸비니
]

def check_business_number(ocr_text):
    """
    OCR 텍스트에서 유효한 사업자번호가 존재하는지 확인.
    하이픈(-), 공백 등을 제거하고 순수 숫자열로 비교.
    """
    if not ocr_text: str = ""
    
    # OCR 텍스트 정규화 (숫자만 남김)
    normalized_text = re.sub(r'[^0-9]', '', ocr_text)
    
    for biz_num in VALID_BIZ_NUMBERS:
        # 비교군도 정규화
        clean_biz = biz_num.replace('-', '')
        if clean_biz in normalized_text:
            return True, biz_num
            
    return False, None

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
    data = { "receipt_no": None, "branch_paid": "미확인 지점", "amount": 0, "date": None }
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
        # "카드번호", "가맹점번호" 등도 추가
        bad_words = ["승인번호", "승인", "가맹점", "사업자", "Tel", "TEL", "문의", "카드번호", "Card", "No", "NO", "ID"]
        is_risky_line = any(bad_word in text for bad_word in bad_words)
        
        numbers = re.findall(r'([0-9,.]+)', text)
        if numbers:
            for num_str in reversed(numbers):
                clean_num = num_str.replace(',', '').replace('.', '')
                if clean_num.isdigit():
                    val = int(clean_num)
                    # 100원 ~ 5천만원
                    if 100 <= val < 50000000:
                        # [핵심 수정] 8자리 이상 숫자는 '승인번호'일 확률이 매우 높음
                        # 금액이 1000만원 이상일 경우 반드시 콤마(,)가 있어야만 인정 (휴리스틱)
                        if len(clean_num) >= 8:
                            if ',' not in num_str:
                                continue # 콤마 없는 큰 숫자는 무시 (승인번호 오인 방지)
                            if is_risky_line:
                                continue # 위험한 단어가 있는 줄의 큰 숫자는 무시
                        
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
            # "No", "ID", "Code" 등 추가
            if any(bad in line for bad in ["승인", "번호", "Tel", "TEL", "사업자", "Date", "Time", "날짜", "Card", "No", "NO", "ID", "Code"]):
                continue

            candidates = re.findall(r'([0-9,]+)', line)
            for cand in candidates:
                val_str = cand.replace(',', '').replace('.', '')
                if val_str.isdigit():
                    val = int(val_str)
                    # 100원 ~ 5천만원
                    if 100 <= val < 50000000: 
                        # [비상대책 강화] 콤마가 없는 8자리 이상 숫자는 절대 금액으로 인정 안 함 (승인번호 회피)
                        if len(val_str) >= 8 and ',' not in cand:
                            continue
                        
                        if val > max_val:
                            max_val = val
                            
        if max_val > 0:
            data["amount"] = max_val
            print(f"💰 비상 대책으로 찾은 금액: {data['amount']}")

    # 4. 날짜 찾기 (추가)
    date_match = re.search(r'(\d{4}[-/.]\d{2}[-/.]\d{2})|(\d{2}[-/.]\d{2}[-/.]\d{2})', ocr_text)
    if date_match:
        data["date"] = date_match.group(0).replace('-', '').replace('/', '').replace('.', '')
    else:
        data["date"] = datetime.now().strftime("%Y%m%d")

    # 5. 승인번호 찾기 (강화)
    # 승인번호, 일련번호, 거래번호, APPROVAL, Auth No 등 다양한 패턴 대응
    receipt_no_match = re.search(r'(승인번호|일련번호|거래번호|결제번호|approval|auth|no|number)[:.\s]*([0-9-]{8,20})', clean_text_all)
    if receipt_no_match:
        data["receipt_no"] = receipt_no_match.group(2).replace('-', '')
    else:
        # [핵심] 승인번호가 없을 경우: 지점+금액+날짜 조합으로 결정적 ID 생성 (중복 방지용)
        # 같은 영수증을 다시 찍으면 항상 같은 AUTO_ID가 나옵니다.
        safe_branch = data["branch_paid"].replace(' ', '')
        data["receipt_no"] = f"AUTO_{safe_branch}_{data['amount']}_{data['date']}"

    # 6. 환불/단품취소 감지 (NEW)
    refund_keywords = ["취소", "반품", "걸제취소", "승인취소", "매출취소"]
    is_refund = False
    
    # 텍스트 전체에서 환불 키워드 검색
    if any(k in clean_text_all for k in refund_keywords):
        is_refund = True
        print(f"⚠️ 환불/취소 영수증 감지됨!")

    # 환불이면 금액 마이너스 처리
    if is_refund and data["amount"] > 0:
        data["amount"] = data["amount"] * -1

    return data