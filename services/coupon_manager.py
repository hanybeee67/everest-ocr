# services/coupon_manager.py

import uuid
from datetime import datetime, timedelta

def issue_coupon_if_qualified(db, Receipts, Coupons, member_id):
    """
    재방문 조건을 확인하고 쿠폰을 발급합니다.
    (db, Receipts, Coupons 객체를 app.py에서 전달받아 사용)
    """
    
    # ★ 재방문 조건: 최근 30일 이내 2회 이상, 2개 이상의 지점에서 결제
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    # 1. 최근 30일간, 아직 쿠폰 발급에 사용되지 않은 유효 영수증 목록 조회
    recent_receipts = Receipts.query.filter(
        (Receipts.member_id == member_id) &
        (Receipts.visit_date >= thirty_days_ago) &
        (Receipts.is_coupon_used == False)
    ).all()
    
    # 2. 횟수 및 지점 다양성 검증
    if len(recent_receipts) >= 2:
        # 방문 지점 목록 추출 (중복 제거)
        unique_branches = {r.branch_paid for r in recent_receipts}
        
        if len(unique_branches) >= 2:
            # 3. 쿠폰 발급
            coupon_code = 'EVR-' + str(uuid.uuid4().hex[:10]).upper() # 고유 쿠폰 코드 생성
            expiry_date = datetime.now() + timedelta(days=90) # 90일 만료 
            
            new_coupon = Coupons(
                member_id=member_id,
                coupon_code=coupon_code,
                coupon_type='사은 쿠폰 (음료 1잔)', # 지급할 쿠폰 종류
                expiry_date=expiry_date
            )
            db.session.add(new_coupon)
            
            # 4. 쿠폰 발급에 사용된 영수증들은 'is_coupon_used'를 True로 업데이트
            for r in recent_receipts:
                r.is_coupon_used = True
                
            db.session.commit()
            return True # 쿠폰 발급 성공
            
    return False # 조건 미충족