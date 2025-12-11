from datetime import datetime, timedelta
from sqlalchemy import func

# 1. [방문 횟수] 보상 규칙 (3-6-9)
VISIT_RULES = {
    3: "난(Naan) 1개 무료 쿠폰 (버터/갈릭 선택)",
    6: "라씨(Lassi) 2잔 무료 쿠폰",
    9: "탄두리 치킨(반마리) 무료 쿠폰"
}

# 2. [누적 금액] 보상 규칙 (20만원 달성 시마다)
AMOUNT_THRESHOLD = 200000 
AMOUNT_REWARD_NAME = "1만원 식사 할인권"

def issue_coupon_if_qualified(db, Receipts, Coupons, member_id):
    """
    방문 횟수와 누적 금액을 동시에 체크하여 쿠폰을 발급함.
    반환값: 발급된 쿠폰 이름들의 리스트 (없으면 빈 리스트)
    """
    issued_coupons = []
    
    # --- 1. 방문 횟수 체크 (Track A) ---
    visit_count = Receipts.query.filter_by(member_id=member_id).count()
    
    if visit_count in VISIT_RULES:
        coupon_name = VISIT_RULES[visit_count]
        code_suffix = f"VISIT_{visit_count}" # 중복 방지 코드 예: VISIT_3
        
        # 이미 받았는지 확인
        existing = Coupons.query.filter_by(member_id=member_id, coupon_code=code_suffix).first()
        if not existing:
            create_coupon(db, Coupons, member_id, code_suffix, coupon_name, days=90)
            issued_coupons.append(coupon_name)
            print(f"🎉 [횟수 보상] {coupon_name} 발급!")

    # --- 2. 누적 금액 체크 (Track B) ---
    # 이 회원의 총 결제 금액 계산
    total_spent = db.session.query(func.sum(Receipts.amount)).filter_by(member_id=member_id).scalar() or 0
    
    # 20만원 단위로 몇 장을 받아야 하는지 계산 (예: 45만원 -> 2장)
    qualified_count = total_spent // AMOUNT_THRESHOLD
    
    if qualified_count > 0:
        # 지금까지 발급된 '금액 쿠폰'이 몇 장인지 DB에서 세어봄
        # 쿠폰 코드를 "AMOUNT_1", "AMOUNT_2" 식으로 저장할 예정
        issued_amount_coupons = Coupons.query.filter(
            Coupons.member_id == member_id,
            Coupons.coupon_code.like("AMOUNT_%")
        ).count()
        
        # 받아야 할 개수(qualified)가 이미 받은 개수(issued)보다 많으면, 그 차이만큼 발급
        to_issue = qualified_count - issued_amount_coupons
        
        if to_issue > 0:
            for i in range(to_issue):
                # 코드 번호는 (현재 가지고 있는 것 + 1 + i) 
                seq_num = issued_amount_coupons + 1 + i
                code_suffix = f"AMOUNT_{seq_num}"
                
                create_coupon(db, Coupons, member_id, code_suffix, AMOUNT_REWARD_NAME, days=180) # 금액권은 유효기간 6개월
                issued_coupons.append(AMOUNT_REWARD_NAME)
                print(f"💰 [금액 보상] {AMOUNT_REWARD_NAME} {to_issue}장 발급!")

    return issued_coupons

def create_coupon(db, Coupons, member_id, code, name, days):
    """DB에 쿠폰을 저장하는 내부 함수"""
    expiry_date = datetime.now() + timedelta(days=days)
    new_coupon = Coupons(
        member_id=member_id,
        coupon_code=code,
        coupon_type=name,
        issued_date=datetime.now(),
        expiry_date=expiry_date,
        is_used=False
    )
    db.session.add(new_coupon)
    db.session.commit()