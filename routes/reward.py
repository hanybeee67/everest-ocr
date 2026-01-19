
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from models import Members, Coupons
from services.coupon_service import TIERS, claim_reward_service

reward_bp = Blueprint('reward', __name__, url_prefix='/reward')

@reward_bp.route("/status")
def status():
    # 간단한 인증: member_id를 세션이나 파라미터로 받아야 함. 
    # 현재 구조상 URL 파라미터나 세션 없이 접근 어려움.
    # 영수증 업로드 후나, 전화번호 조회 후 접근한다고 가정.
    member_id = request.args.get("member_id")
    if not member_id:
        return redirect("/")
        
    member = Members.query.get(member_id)
    if not member:
        return "Member not found", 404
        
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
    
    return render_template("my_coupons.html", member=member, active_coupons=active_coupons, inactive_coupons=inactive_coupons)

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
