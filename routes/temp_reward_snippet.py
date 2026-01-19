
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
    branch_code = request.form.get("branch_code") # 옵션
    
    # 기존 해시 조회 로직 재사용 권장하지만, 간단히 구현
    input_hash = Members.generate_phone_hash(phone)
    member = Members.query.filter_by(phone_hash_value=input_hash).first()
    
    if not member:
        # Fallback 로직 (필요시 추가, 여기선 생략하고 단순 처리)
        # 실제로는 public.check 로직을 공통 서비스로 빼는게 좋음
        return render_template("my_coupons_login.html", error="등록되지 않은 번호입니다.", phone=phone)
        
    return redirect(url_for('reward.my_coupons', member_id=member.id))
