def parse_receipt_text(ocr_text):
    data = { "receipt_no": None, "branch_paid": "미확인 지점", "amount": 0 }
    
    if not ocr_text: return data

    # 1. 텍스트 정리 (공백 제거, 소문자 변환)
    clean_text = ocr_text.replace(' ', '').lower()
    
    # 2. 지점명 찾기 (기존과 동일)
    for official_name, keywords in BRANCH_NAMES.items():
        for keyword in keywords:
            if keyword.replace(' ', '') in clean_text:
                data["branch_paid"] = official_name
                break
        if data["branch_paid"] != "미확인 지점": break
            
    # 3. 금액 찾기 (★수정된 부분★)
    amount_keywords = [
        "합계", "결제금액", "청구금액", "받을금액", "승인금액", 
        "매출금액", "total", "tot", "amount", "금액", "계"
    ]
    
    found_amount = False
    
    # 방법 A: 키워드("합계" 등) 주변 숫자 찾기
    for keyword in amount_keywords:
        # 패턴: 키워드 뒤에 나오는 숫자 찾기
        pattern = re.compile(rf'{keyword}[^0-9]*([0-9,]+)')
        match = pattern.search(clean_text)
        if match:
            raw_num = match.group(1).replace(',', '')
            if raw_num.isdigit():
                val = int(raw_num)
                # [★ 핵심 수정] 100원보다 작은 숫자는 '수량'일 확률이 높으므로 무시합니다.
                if val >= 100: 
                    data["amount"] = val
                    found_amount = True
                    print(f"💰 금액 인식 성공 (키워드 '{keyword}'): {data['amount']}")
                    break
                else:
                    print(f"⚠️ 금액 키워드 '{keyword}' 옆에서 숫자 '{val}'을 찾았으나, 너무 작아(수량 추정) 무시함.")
    
    # 방법 B: 키워드로 못 찾았거나, 찾은게 100원 미만이면 전체에서 가장 큰 숫자 찾기
    if not found_amount or data["amount"] == 0:
        print("🔄 숫자 전체 탐색 모드 가동 (가장 큰 금액 찾기)")
        # '원' 글자 앞 숫자 혹은 4자리 이상 숫자 덩어리 검색
        candidates = re.findall(r'([0-9,]+)원', ocr_text)
        if not candidates:
            candidates = re.findall(r'([0-9,]{4,})', ocr_text) # 4자리 이상만

        max_val = 0
        for cand in candidates:
            val_str = cand.replace(',', '').replace('.', '')
            if val_str.isdigit():
                val = int(val_str)
                # 100원 ~ 1000만원 사이의 숫자 중 가장 큰 것 선택
                if 100 <= val < 10000000: 
                    if val > max_val:
                        max_val = val
        
        if max_val > 0:
            data["amount"] = max_val
            print(f"💰 최대 숫자 추정 금액: {data['amount']}")

    # 4. 승인번호 찾기 (기존과 동일)
    receipt_no_match = re.search(r'(승인번호|일련번호|no|number)[:.\s]*([0-9-]{8,20})', clean_text)
    if receipt_no_match:
        data["receipt_no"] = receipt_no_match.group(2).replace('-', '')
    else:
        data["receipt_no"] = "AUTO_" + datetime.now().strftime("%Y%m%d%H%M%S")

    return data