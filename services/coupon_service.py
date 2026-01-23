
from datetime import datetime, timedelta
import uuid
from models import db, Members, Coupons, Receipts

TIERS = {
    1: {"cost": 100000, "name": "Lv1. 사모사/굴자빵 중 택1"},
    2: {"cost": 200000, "name": "Lv2. 모모/차오면 무료"},
    3: {"cost": 300000, "name": "Lv3. 커리(Curry) 1개 무료"},
    4: {"cost": 400000, "name": "Lv4. 탄두리 치킨(1마리) 또는 세꾸와 무료"}
}

def get_coupon_name_by_amount(amount):
    """
    금액(포인트)에 따른 쿠폰 표시명 반환 (알림톡 변수용)
    """
    if amount >= 400000:
        return "탄두리 치킨(1마리) 또는 세꾸와 무료"
    elif amount >= 300000:
        return "커리(Curry) 1개 무료"
    elif amount >= 200000:
        return "모모 또는 짜오미엔 무료"
    elif amount >= 100000:
        return "사모사 또는 굴자빵 무료"
    else:
        return "Unknown Reward"

def claim_reward_service(user_id, tier_level):
    """
    사용자가 리워드를 수령(포인트 차감 -> 쿠폰 발급).
    유효기간: 30일
    """
    import os
    import json
    
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
    
    # 쿠폰 타입명은 TIERS의 이름을 그대로 사용 (DB 저장용)
    # 알림톡 발송 시에는 get_coupon_name_by_amount로 변환된 이름을 사용
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
        
        # [Notification] 알림톡 발송 (Aligo)
        from flask import current_app
        from itsdangerous import URLSafeTimedSerializer
        from services.notification_service import send_alimtalk
        
        # 환경변수 템플릿 코드 (없으면 기본값)
        template_code = os.environ.get("ALIGO_TPL_REWARD", "TB_REWARD_001")
        
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        token = s.dumps(member.id, salt='coupon-access')
        link_url = f"https://membership.everestfood.com/my-coupons?token={token}"
        formatted_expiry = expiry_date.strftime("%Y-%m-%d")
        
        # [Logic] 금액에 따른 쿠폰명 매핑
        display_coupon_name = get_coupon_name_by_amount(cost)
        
        # 변수 매핑
        variable_map = {
            "#{이름}": member.name,
            "#{쿠폰이름}": display_coupon_name,
            "#{유효기간}": formatted_expiry
        }
        
        # 버튼 설정
        button_data = {
            "name": "쿠폰 확인하기",
            "linkType": "WL",
            "linkTypeName": "웹링크",
            "linkMo": link_url,
            "linkPc": link_url
        }
        button_json = json.dumps({"button": [button_data]})
        
        send_alimtalk(member.phone, template_code, variable_map, button_json)
        
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

def process_signup_bonus(member):
    """
    신규 회원 가입 시 환영 쿠폰 발급 및 알림톡 발송
    - Coupon: 플레인 난(Plain Naan) 1개 무료
    - Notification: AlimTalk (ALIGO_TPL_SIGNUP)
    """
    import os
    import json
    from flask import current_app
    from itsdangerous import URLSafeTimedSerializer
    from services.notification_service import send_alimtalk
    
    # 1. 쿠폰 생성
    today_date = datetime.now()
    expiry_date = today_date + timedelta(days=30)
    unique_code = f"WC-{uuid.uuid4().hex[:8].upper()}"
    
    welcome_coupon = Coupons(
        member_id=member.id,
        coupon_code=unique_code,
        coupon_type="플레인 난(Plain Naan) 1개 무료", # [요청사항 반영]
        issued_date=today_date,
        expiry_date=expiry_date,
        status='AVAILABLE',
        is_used=False
    )
    db.session.add(welcome_coupon)
    
    # 2. 알림톡 발송 준비
    try:
        # 환경변수에서 템플릿 코드 로드 (없으면 기본값)
        template_code = os.environ.get("ALIGO_TPL_SIGNUP", "TB_SIGNUP_001")
        
        # 매직 링크 생성
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        token = s.dumps(member.id, salt='coupon-access')
        link_url = f"https://membership.everestfood.com/my-coupons?token={token}"
        
        # 변수 매핑
        variable_map = {
            "#{이름}": member.name,
            "#{발급일}": today_date.strftime("%Y-%m-%d"),
            "#{유효기간}": expiry_date.strftime("%Y-%m-%d")
        }
        
        # 버튼 설정
        button_data = {
            "name": "쿠폰 확인하기", # 버튼명 (템플릿 설정에 따름)
            "linkType": "WL", # Web Link
            "linkTypeName": "웹링크",
            "linkMo": link_url,
            "linkPc": link_url
        }
        button_json = json.dumps({"button": [button_data]}) # 알리고 형식 (버튼 리스트)
        
        # 알림톡 발송 요청
        send_alimtalk(member.phone, template_code, variable_map, button_json)
        
    except Exception as e:
        current_app.logger.error(f"Signup bonus notification failed: {e}")
        # 알림 실패해도 쿠폰은 저장되어야 함

    db.session.commit()
    return True
