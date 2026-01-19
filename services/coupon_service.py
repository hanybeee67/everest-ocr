
from datetime import datetime, timedelta
import uuid
from models import db, Members, Coupons, Receipts

TIERS = {
    1: {"cost": 100000, "name": "Lv1. 사모사/굴자빵"},
    2: {"cost": 200000, "name": "Lv2. 모모/초우면"},
    3: {"cost": 300000, "name": "Lv3. 커리(단품)"},
    4: {"cost": 400000, "name": "Lv4. 탄두리치킨/세쿠와"}
}

def claim_reward_service(user_id, tier_level):
    """
    사용자가 리워드를 수령(포인트 차감 -> 쿠폰 발급).
    유효기간: 30일
    """
    member = Members.query.get(user_id)
    if not member:
        return {"success": False, "message": "사용자를 찾을 수 없습니다."}

    tier_info = TIERS.get(tier_level)
    if not tier_info:
        return {"success": False, "message": "잘못된 리워드 등급입니다."}
    
    cost = tier_info["cost"]
    
    # 잔액 확인
    current_balance = member.current_reward_balance or 0
    if current_balance < cost:
        return {"success": False, "message": f"포인트가 부족합니다. (필요: {cost:,} P, 보유: {current_balance:,} P)"}
    
    # 1. 포인트 차감
    member.current_reward_balance = current_balance - cost
    
    # 2. 쿠폰 발급
    expiry_date = datetime.now() + timedelta(days=30) # 유효기간 30일
    unique_code = f"CP-{uuid.uuid4().hex[:8].upper()}"
    
    new_coupon = Coupons(
        member_id=member.id,
        coupon_code=unique_code,
        coupon_type=tier_info["name"],
        issued_date=datetime.now(),
        expiry_date=expiry_date,
        status='AVAILABLE',
        is_used=False
    )
    
    db.session.add(new_coupon)
    
    try:
        db.session.commit()
        
        # [Notification] 쿠폰 발급 알림 발송 (Magic Link)
        # itsdangerous를 사용하여 member_id가 담긴 토큰 생성
        from flask import current_app
        from itsdangerous import URLSafeTimedSerializer
        from services.notification_service import send_notification
        
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        token = s.dumps(member.id, salt='coupon-access')
        
        msg = f"[에베레스트] {tier_info['name']} 쿠폰이 발급되었습니다.\n바로가기: https://everest-membership.com/reward/my-coupons?token={token}"
        send_notification(member.phone, msg)
        
        return {
            "success": True, 
            "message": f"{tier_info['name']} 쿠폰이 발급되었습니다!",
            "coupon_code": unique_code,
            "remaining_balance": member.current_reward_balance
        }
    except Exception as e:
        db.session.rollback()
        return {"success": False, "message": f"처리 중 오류가 발생했습니다: {e}"}

def redeem_coupon_service(coupon_code, staff_pin, branch_code):
    """
    직원이 쿠폰을 사용 처리 (PIN 인증 필수).
    """
    from models import Staffs
    import bcrypt
    
    # 1. 쿠폰 조회
    coupon = Coupons.query.filter_by(coupon_code=coupon_code).first()
    if not coupon:
        return {"success": False, "message": "유효하지 않은 쿠폰 코드입니다."}
    
    if coupon.status != 'AVAILABLE':
        return {"success": False, "message": f"이미 사용되었거나 만료된 쿠폰입니다. (상태: {coupon.status})"}
    
    # 만료일 체크
    if coupon.expiry_date and coupon.expiry_date < datetime.now():
        coupon.status = 'EXPIRED'
        db.session.commit()
        return {"success": False, "message": "유효기간이 만료된 쿠폰입니다."}

    # 2. 직원 승인 (PIN 검증)
    # branch_code에 해당하는 직원들 중 PIN이 일치하는 사람이 있는지 확인
    # (보안상 직원을 먼저 선택하고 PIN을 넣는게 좋지만, 편의상 해당 지점의 어떤 직원이라도 PIN 맞으면 통과)
    staffs = Staffs.query.filter_by(branch=branch_code).all()
    valid_staff = None
    
    for staff in staffs:
        if bcrypt.checkpw(staff_pin.encode('utf-8'), staff.pin_hash.encode('utf-8')):
            valid_staff = staff
            break
            
    if not valid_staff:
        return {"success": False, "message": "직원 인증 실패: PIN 번호가 올바르지 않습니다."}
        
    # 3. 사용 처리
    coupon.status = 'USED'
    coupon.is_used = True
    coupon.used_date = datetime.now()
    coupon.used_at_branch = branch_code
    coupon.redeemed_by_staff_id = valid_staff.id
    
    try:
        db.session.commit()
        return {
            "success": True, 
            "message": f"쿠폰 사용이 완료되었습니다. (처리자: {valid_staff.name})",
            "coupon": coupon.coupon_type
        }
    except Exception as e:
        db.session.rollback()
        return {"success": False, "message": f"처리 중 오류: {e}"}
