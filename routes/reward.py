
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
