from flask import Blueprint, render_template, request, redirect, session, current_app
from sqlalchemy import func
from datetime import datetime
import uuid
import hashlib
from models import db, Members, Receipts, Coupons
from config import Config, check_admin_password

admin_bp = Blueprint('admin', __name__, url_prefix='/admin_8848')
from extensions import limiter

@admin_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute") # [보안] 관리자 비밀번호 대입 공격 방지
def admin_login():
    if request.method == "POST":
        password = request.form.get("password")
        # Bcrypt 검증
        if check_admin_password(password):
            session['admin_logged_in'] = True
            return redirect("/admin_8848/members")
        else:
            return render_template("login.html", error="암호가 틀렸습니다.")
    return render_template("login.html")

@admin_bp.route("/logout")
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect("/admin_8848/login")

@admin_bp.route("/members")
def admin_members():
    if not session.get('admin_logged_in'):
        return redirect("/admin_8848/login")

    sort = request.args.get("sort", "date")
    if sort == "name": members = Members.query.order_by(Members._name.asc()).all()
    elif sort == "branch": members = Members.query.order_by(Members.branch.asc()).all()
    elif sort == "visit": members = Members.query.order_by(Members.visit_count.desc()).all()
    else: members = Members.query.order_by(Members.id.desc()).all()
    
    all_receipts = Receipts.query.order_by(Receipts.visit_date.desc()).all()
    total_members = Members.query.count()
    total_visits = db.session.query(func.sum(Members.visit_count)).scalar() or 0
    
    return render_template("members.html", members=members, sort=sort, total_members=total_members, total_visits=total_visits, all_receipts=all_receipts)

@admin_bp.route("/delete_member/<int:id>")
def delete_member(id):
    if not session.get('admin_logged_in'):
        return redirect("/admin_8848/login")
    member = Members.query.get(id)
    if member:
        Receipts.query.filter_by(member_id=id).delete()
        Coupons.query.filter_by(member_id=id).delete()
        db.session.delete(member)
        db.session.commit()
    return redirect("/admin_8848/members")

# [신규] 쿠폰 관리 페이지
@admin_bp.route("/coupons")
def admin_coupons():
    if not session.get('admin_logged_in'):
        return redirect("/admin_8848/login")
    
    keyword = request.args.get("keyword", "").strip()
    member = None
    coupons = []
    
    if keyword:
        # 암호화 적용으로 인해 like 검색 불가 -> 메모리 필터링
        all_members = Members.query.all()
        # 이름 또는 전화번호에 키워드가 포함된 회원 찾기
        member_candidates = [m for m in all_members if keyword in m.name or keyword in m.phone]
        
        # 첫 번째 매칭 회원 선택 (기존 로직 유지)
        if member_candidates:
            member = member_candidates[0]

        if member:
            coupons = Coupons.query.filter_by(member_id=member.id).order_by(Coupons.is_used.asc(), Coupons.expiry_date.asc()).all()
            
    return render_template("admin_coupons.html", member=member, coupons=coupons, keyword=keyword)

# [신규] 쿠폰 사용 처리
@admin_bp.route("/use_coupon/<int:coupon_id>")
def use_coupon(coupon_id):
    if not session.get('admin_logged_in'):
        return redirect("/admin_8848/login")
    
    coupon = Coupons.query.get(coupon_id)
    keyword = request.args.get("keyword", "")
    
    if coupon and not coupon.is_used:
        coupon.is_used = True
        coupon.used_date = datetime.now()
        coupon.used_at_branch = "관리자처리" 
        db.session.commit()
    
    return redirect(f"/admin_8848/coupons?keyword={keyword}")

@admin_bp.route("/member/<int:member_id>/edit", methods=["GET", "POST"])
def edit_member(member_id):
    if not session.get('admin_logged_in'):
        return redirect("/admin_8848/login")
    
    member = Members.query.get(member_id)
    if not member:
        return "회원 정보를 찾을 수 없습니다."

    # 현재 누적 금액 계산
    current_total = db.session.query(func.sum(Receipts.amount)).filter_by(member_id=member.id).scalar() or 0

    curr_receipts = Receipts.query.filter_by(member_id=member.id).order_by(Receipts.visit_date.desc()).all()
    
    # [신규] 쿠폰 목록 조회
    coupons = Coupons.query.filter_by(member_id=member.id).order_by(Coupons.issued_date.desc()).all()

    if request.method == "POST":
        # 1. 기본 정보 수정
        member.name = request.form.get("name")
        member.phone = request.form.get("phone")
        member.birth = request.form.get("birth")
        member.visit_count = int(request.form.get("visit_count", 0))

        # 2. 누적 금액 수정 (보정 영수증 생성)
        target_total = int(request.form.get("total_amount", 0))
        diff = target_total - current_total

        if diff != 0:
            # 보정용 영수증 생성
            adjustment_receipt = Receipts(
                member_id=member.id,
                receipt_no=f"ADJ-{uuid.uuid4().hex[:8]}", # 고유한 보정 번호
                branch_paid="관리자보정",
                amount=diff,
                visit_date=datetime.now(),
                is_coupon_used=False
            )
            db.session.add(adjustment_receipt)
        
        db.session.commit()
        return redirect("/admin_8848/members")

    return render_template("edit_member.html", member=member, total_amount=current_total, receipts=curr_receipts, coupons=coupons)

@admin_bp.route("/receipt/<int:receipt_id>/update", methods=["POST"])
def update_receipt(receipt_id):
    if not session.get('admin_logged_in'):
        return redirect("/admin_8848/login")
        
    receipt = Receipts.query.get(receipt_id)
    if receipt:
        try:
            new_amount = int(request.form.get("amount", 0))
            old_amount = receipt.amount
            
            # [Fix] 금액 변경 시 멤버 포인트/누적금액도 연동하여 수정
            # 단, 'APPROVED' 상태이거나 아직 상태가 없는(구데이터) 경우에만 반영 감안
            # 현재 로직상 PENDING인 고액 건을 수정해서 승인하는 로직은 별도지만, 
            # 여기선 단순 금액 수정이므로 즉시 반영으로 통일 (테스트 편의성)
            member = Members.query.get(receipt.member_id)
            if member:
                diff = new_amount - old_amount
                member.current_reward_balance = (member.current_reward_balance or 0) + diff
                member.total_lifetime_spend = (member.total_lifetime_spend or 0) + diff
            
            receipt.amount = new_amount
            db.session.commit()
        except ValueError:
            pass
            
    return redirect(f"/admin_8848/member/{receipt.member_id}/edit")

@admin_bp.route("/receipt/<int:receipt_id>/delete", methods=["POST"])
def delete_receipt(receipt_id):
    if not session.get('admin_logged_in'):
        return redirect("/admin_8848/login")
        
    receipt = Receipts.query.get(receipt_id)
    if receipt:
        member_id = receipt.member_id
        member = Members.query.get(member_id)
        
        # [Fix] 삭제 시 포인트 차감
        if member:
            member.current_reward_balance = (member.current_reward_balance or 0) - receipt.amount
            member.total_lifetime_spend = (member.total_lifetime_spend or 0) - receipt.amount
            
            if member.visit_count > 0:
                member.visit_count -= 1
        
        db.session.delete(receipt)
        db.session.commit()
        return redirect(f"/admin_8848/member/{member_id}/edit")
        
    return redirect("/admin_8848/members")
