import os
import io
import re
import json
from google.cloud import vision
from google.oauth2 import service_account
from datetime import datetime

# ============================================
# 1. OCR 지점명 정의 (파싱 로직 사용)
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
# 2. 진짜 OCR 텍스트 추출 함수 (Google Vision API)
# ============================================
def detect_text_from_receipt(image_path):
    """
    Google Cloud Vision API를 사용하여 이미지에서 텍스트를 추출합니다.
    """
    try:
        # 1. 환경 변수에서 인증 정보 가져오기 (Render 배포 환경용)
        credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        
        if credentials_json:
            # Render 환경: JSON 문자열을 객체로 변환하여 인증
            credentials_info = json.loads(credentials_json)
            credentials = service_account.Credentials.from_service_account_info(credentials_info)
            client = vision.ImageAnnotatorClient(credentials=credentials)
        else:
            # 로컬 환경: 환경 변수가 없으면 기본 설정 시도 (또는 에러 발생)
            # 로컬 테스트 시에는 터미널에서 환경변수를 설정했거나, 아래 줄을 수정해야 합니다.
            client = vision.ImageAnnotatorClient()

        # 2. 이미지 파일 읽기
        with io.open(image_path, 'rb') as image_file:
            content = image_file.read()

        image = vision.Image(content=content)

        # 3. 텍스트 감지 요청
        response = client.text_detection(image=image)
        texts = response.text_annotations

        # 4. 임시 파일 삭제 (보안 및 용량 관리)
        try:
            os.remove(image_path)
        except OSError:
            pass

        if response.error.message:
            raise Exception(f'{response.error.message}')

        if texts:
            return texts[0].description # 전체 텍스트 반환
        else:
            return None

    except Exception as e:
        print(f"OCR Error: {e}")
        # 에러 발생 시에도 파일은 삭제 시도
        if os.path.exists(image_path):
            os.remove(image_path)
        return None


# ============================================
# 3. 텍스트 파싱 함수 (규칙 기반)
# ============================================
def parse_receipt_text(ocr_text):
    data = {
        "receipt_no": None,
        "branch_paid": "미확인 지점",
        "amount": 0,
    }
    
    if not ocr_text:
        return data

    # 텍스트 정규화
    clean_text = ocr_text.replace('\n', ' ').replace(' ', '').lower()
    
    # --- A. 지점명 추출 ---
    for official_name, keywords in BRANCH_NAMES.items():
        for keyword in keywords:
            if keyword.replace(' ', '') in clean_text:
                data["branch_paid"] = official_name
                break
        if data["branch_paid"] != "미확인 지점":
            break
            
    # --- B. 금액 추출 ---
    # '합계', '결제금액' 뒤에 오는 숫자 찾기
    amount_match = re.search(r'(합계|결제금액|total|tot|금액)[:\s]*([0-9,]+)', clean_text)
    if amount_match:
        raw_amount = amount_match.group(2).replace(',', '')
        if raw_amount.isdigit():
            data["amount"] = int(raw_amount)
        
    # 금액을 못 찾았다면, 텍스트 내에서 '원' 앞에 있는 큰 숫자 찾아보기 (보완책)
    if data["amount"] == 0:
        candidates = re.findall(r'([0-9,]+)원', ocr_text)
        for cand in candidates:
            val = int(cand.replace(',', ''))
            if val > data["amount"]: # 가장 큰 금액을 합계로 추정
                data["amount"] = val

    # --- C. 승인번호 추출 ---
    # 8자리 이상 연속된 숫자 (카드 승인번호 패턴)
    receipt_no_match = re.search(r'(승인번호|일련번호|no)[:.\s]*([0-9-]{8,20})', clean_text)
    if receipt_no_match:
        data["receipt_no"] = receipt_no_match.group(2).replace('-', '')
    else:
        # 번호가 없으면 임시로 날짜+금액 조합 (중복 방지용)
        # 실제 서비스에서는 에러를 띄우는 게 좋지만, 테스트를 위해 임시 생성
        data["receipt_no"] = "TEMP_" + datetime.now().strftime("%H%M%S")

    return data