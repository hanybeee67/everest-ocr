
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from models import Members, Coupons
from services.coupon_service import TIERS, claim_reward_service

reward_bp = Blueprint('reward', __name__, url_prefix='/reward')

@reward_bp.route("/status")
def status():
    # 간단한 인증: member_id 또는 phone으로 접근 허용
    member_id = request.args.get("member_id")
    phone = request.args.get("phone")
    
    member = None
    
    if member_id:
        member = Members.query.get(member_id)
    elif phone:
        # 전화번호로 조회 (해시 -> Fallback)
        input_hash = Members.generate_phone_hash(phone)
        member = Members.query.filter_by(phone_hash_value=input_hash).first()
        
        if not member:
        if not member:
            # Fallback (전체 검색) - 테스트 편의성을 위해
            all_members = Members.query.all()
            # 숫자만 추출하여 정규화
            norm_input = "".join(filter(str.isdigit, phone))
            
            print(f"[DEBUG] Looking for phone(digits): {norm_input}")
            
            for m in all_members:
                 try:
                     db_phone = m.phone or ""
                     norm_db = "".join(filter(str.isdigit, db_phone))
                     if norm_db == norm_input:
                         member = m
                         print(f"[DEBUG] Found match! ID: {m.id}, Phone: {db_phone}")
                         break
                 except Exception as e:
                     continue # 복호화 실패 등 무시
                     
    if not member:
        return f"회원 정보를 찾을 수 없습니다. (입력: {phone})", 404
        
    # 사용 가능 쿠폰 조회
    available_coupons = Coupons.query.filter_by(member_id=member.id, status='AVAILABLE').all()
    
    return render_template("reward_status.html", 
                           member=member, 
                           tiers=TIERS, 
                           available_coupons=available_coupons)

@reward_bp.route("/claim", methods=["POST"])
def claim():
    member_id = request.form.get("member_id")
    tier_level = int(request.form.get("tier_level"))
    
    result = claim_reward_service(member_id, tier_level)
    
    if result["success"]:
        return jsonify(result) # 프론트에서 성공 처리
    else:
        return jsonify(result), 400

@reward_bp.route("/my-coupons")
def my_coupons():
    member_id = request.args.get("member_id")
    token = request.args.get("token")
    
    # [Magic Link] 토큰이 있으면 검증하여 자동 로그인 처리
    if token:
        try:
            from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
            s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
            # salt는 생성시와 동일하게 'coupon-access'
            # max_age는 예: 30일(2592000초) 등으로 설정 가능
            decoded_id = s.loads(token, salt='coupon-access', max_age=2592000)
            member_id = decoded_id
        except (SignatureExpired, BadSignature):
            # 토큰 만료나 위변조 시 -> 로그인 페이지로 Fallback
            pass

    # 1. 로그인(전화번호 입력) 안된 상태면 입력 페이지 렌더링
    if not member_id:
        return render_template("my_coupons_login.html")
    
    member = Members.query.get(member_id)
    if not member:
        return render_template("my_coupons_login.html", error="회원 정보를 찾을 수 없습니다.")
        
    # 2. 쿠폰 분류 (사용가능 / 사용완료+만료)
    active_coupons = Coupons.query.filter_by(member_id=member.id, status='AVAILABLE').order_by(Coupons.expiry_date.asc()).all()
    
    # 사용했거나(USED) 만료된(EXPIRED) 쿠폰
    inactive_coupons = Coupons.query.filter(
        Coupons.member_id == member.id,
        Coupons.status.in_(['USED', 'EXPIRED'])
    ).order_by(Coupons.used_date.desc(), Coupons.expiry_date.desc()).all()
    
    # 지점 목록 (모달에서 사용)
    from services.ocr_parser import BRANCH_NAMES
    # BRANCH_NAMES 키들(동대문, 굿모닝시티 등)을 리스트로 전달
    branch_list = list(BRANCH_NAMES.keys())
    
    return render_template("my_coupons.html", member=member, active_coupons=active_coupons, inactive_coupons=inactive_coupons, branch_list=branch_list)

@reward_bp.route("/redeem-mobile", methods=["POST"])
def redeem_mobile():
    """
    모바일 웹에서 직원이 PIN을 입력하여 쿠폰을 즉시 사용하는 API
    """
    coupon_code = request.json.get("coupon_code")
    staff_pin = request.json.get("staff_pin")
    branch_name = request.json.get("branch_name") # '동대문', '영등포' 등 한글 이름
    
    if not all([coupon_code, staff_pin, branch_name]):
        return jsonify({"success": False, "message": "필수 정보가 누락되었습니다."}), 400
        
    # branch_name(한글) -> branch_code(영문) 매핑 필요
    # models.py나 config에 매핑이 있어야 정확하지만, 
    # 현재 ocr_parser의 BRANCH_NAMES 구조상 역매핑이 필요하거나, 
    # staff 테이블의 branch 필드값(영문/코드)과 맞춰야 함.
    # [임시 조치] 현재 Staff 테이블의 branch 컬럼이 영문('dongdaemun')인지 한글('동대문')인지 확인 필요.
    # 보통 코드('dongdaemun')를 쓰므로 매핑 로직 추가.
    
    # 간단 매핑 (하드코딩 or config 참조 권장)
    branch_map = {
        "동대문": "dongdaemun",
        "굿모닝시티": "goodmorning",
        "영등포": "yeongdeungpo",
        "양재": "yangjae",
        "수원 영통": "suwon",
        "동탄": "dongtan",
        "룸비니": "lumbini"
    }
    
    branch_code = branch_map.get(branch_name, "dongdaemun") # 기본값 동대문
    
    from services.coupon_service import redeem_coupon_service
    result = redeem_coupon_service(coupon_code, staff_pin, branch_code)
    
    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 400

@reward_bp.route("/my-coupons/auth", methods=["POST"])
def my_coupons_auth():
    phone = request.form.get("phone")
    
    # 해시 조회
    input_hash = Members.generate_phone_hash(phone)
    member = Members.query.filter_by(phone_hash_value=input_hash).first()
    
    if not member:
        # 간단한 Fallback: 해시 실패시 전체 검색 (public.py와 동일 로직이 좋지만 여기선 약식 구현)
        # 운영상 필요시 public.check 로직을 서비스로 분리해야 함.
        # 일단 약식으로 폰번호 뒷자리 비교 등 없이 정확히 일치해야 하는 것으로 가정 
        # (편의상 전체 검색 fallback 하나만 추가)
        all_members = Members.query.all()
        norm_input = phone.replace("-", "").replace(" ", "").strip()
        for m in all_members:
             if m.phone and m.phone.replace("-", "").replace(" ", "").strip() == norm_input:
                 member = m
                 break
    
    if not member:
        return render_template("my_coupons_login.html", error="등록되지 않은 번호입니다.", phone=phone)
        
    return redirect(url_for('reward.my_coupons', member_id=member.id))
