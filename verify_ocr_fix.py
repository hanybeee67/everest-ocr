from services.ocr_parser import parse_receipt_text

def test_ocr_logic():
    print("Testing OCR Logic...")
    
    # Case 1: Ideal receipt
    text1 = """
    에베레스트 동대문점
    합계 30,000
    승인번호 12345678
    """
    res1 = parse_receipt_text(text1)
    print(f"Case 1 (Ideal): Amount={res1['amount']} (Exp: 30000) / Receipt={res1['receipt_no']}")
    assert res1['amount'] == 30000

    # Case 2: Approval num looks like amount but no comma
    text2 = """
    에베레스트
    승인번호 : 30012345
    주문번호 : 0001
    """
    res2 = parse_receipt_text(text2)
    # The heuristic should filter out 30012345 because it's > 8 digits and has no comma, 
    # and also it is on a 'risky' line (승인번호)
    print(f"Case 2 (Approval Trap): Amount={res2['amount']} (Exp: 0 or fallback max < 10M)")
    # Should be 0 if nothing else found, or maybe some other small number
    if res2['amount'] > 1000000:
        print("FAIL: Picked up approval number as amount!")
    else:
        print("SUCCESS: Ignored approval number")

    # Case 3: Amount with comma vs Approval without
    text3 = """
    영수증
    No. 99887766
    결제금액: 15,000원
    승인: 12341234
    """
    res3 = parse_receipt_text(text3)
    print(f"Case 3 (Mixed): Amount={res3['amount']} (Exp: 15000)")
    assert res3['amount'] == 15000
    
    # Case 4: No keywords, fallback. 
    # Should pick 12,000 (comma) over 12345678 (no comma, long)
    text4 = """
    청국장 8,000
    된장 4,000
    ----------------
    12,000
    
    BarCode: 880912341234
    """
    res4 = parse_receipt_text(text4)
    print(f"Case 4 (Fallback): Amount={res4['amount']} (Exp: 12000)")
    assert res4['amount'] == 12000

if __name__ == "__main__":
    test_ocr_logic()
