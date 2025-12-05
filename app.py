# app.py

from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import func
import os
import uuid
import json

# ★ 새로 만든 모듈 import (services 디렉토리가 있어야 함)
from services.ocr_parser import detect_text_from_receipt, parse_receipt_text
from services.coupon_manager import issue_coupon_if_qualified


app = Flask(__name__, instance_path=os.getcwd() + '/instance') # instance_path 설정
os.makedirs(app.instance_path, exist_ok=True) # instance 폴더가 없으면 생성

# ===== DB 설정 =====
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///members.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# ===== DB 모델 정의 =====
class Members(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    phone = db.Column(db.String(20), unique=True)
    birth = db.Column(db.String(20))
    branch = db.Column(db.String(50))
    agree_marketing = db.Column(db.String(5))
    agree_privacy = db.Column(db.String(5))
    visit_count = db.Column(db.Integer, default=1)      
    last_visit = db.Column(db.String(20))               
    created_at = db.Column(db.String(30))
    
    receipts = db.relationship('Receipts', backref='member', lazy=True)
    coupons = db.relationship('Coupons', backref='member', lazy=True)


# ----------------------------------------------------------------------
# ★ 신규 테이블 1: 영수증 기록 테이블 (OCR 결과 저장소)
# ----------------------------------------------------------------------
class Receipts(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    receipt_no = db.Column(db.String(50), unique=True, nullable=False)
    branch_paid = db.Column(db.String(50))
    amount = db.Column(db.Integer)
    visit_date = db.Column(db.DateTime, default=datetime.now)
    is_coupon_used = db.Column(db.Boolean, default=False) 

# ----------------------------------------------------------------------
# ★ 신규 테이블 2: 쿠폰 관리 테이블
# ----------------------------------------------------------------------
class Coupons(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    coupon_code = db.Column(db.String(50), unique=True, nullable=False)
    coupon_type = db.Column(db.String(50), default='사은 쿠폰')
    issued_date = db.Column(db.DateTime, default=datetime.now)
    expiry_date = db.Column(db.DateTime)
    is_used = db.Column(db.Boolean, default=False)
    used_at_branch = db.Column(db.String(50))
    used_date = db.Column(db.DateTime)


# ===== DB 자동 생성 =====
with app.app_context():
    db.create_all()


# ============================================
# 1) 첫 화면 → 영수증 등록 시작 (OCR 개발용)
# ============================================
@app.route("/")
def index():
    # OCR 개발 테스트를 위해 영수증 등록 페이지로 바로 이동하도록 수정
    return redirect(url_for("receipt_entry"))


# ============================================
# 2) unified: 전화번호 입력 → 신규/재방문 분기 (기존 로직 유지)
# ============================================
@app.route("/unified", methods=["GET", "POST"])
def unified():
    # GET: 지점 선택 화면에서 넘어옴 (기존 멤버십용)
    if request.method == "GET":
        branch = request.args.get("branch", None)
        return render_template("unified.html", branch=branch)

    # POST: 전화번호 입력 후 처리
    phone = request.form.get("phone")
    branch = request.form.get("branch")

    exist = Members.query.filter_by(phone=phone).first()
    today = datetime.now().strftime("%Y-%m-%d")

    if exist:
        # 기존 방문 횟수 증가 로직 (전화번호 입력 기반)
        if exist.last_visit != today:
            exist.visit_count += 1
            exist.last_visit = today
            db.session.commit()

        return render_template("visit.html", name=exist.name)

    # 신규 가입
    return render_template("join.html", phone=phone, branch=branch)


# ============================================
# 3) 신규 가입 처리 (기존 로직 유지)
# ============================================
@app.route("/join", methods=["POST"])
def join():
    name = request.form.get("name")
    phone = request.form.get("phone")
    branch = request.form.get("branch")
    birth = request.form.get("birth")

    agree_marketing = "yes" if request.form.get("agree_marketing") else "no"
    agree_privacy = "yes" if request.form.get("agree_privacy") else "no"

    today = datetime.now().strftime("%Y-%m-%d")

    new_member = Members(
        name=name,
        phone=phone,
        branch=branch,
        birth=birth,
        agree_marketing=agree_marketing,
        agree_privacy=agree_privacy,
        visit_count=1,
        last_visit=today,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    db.session.add(new_member)
    db.session.commit()

    return render_template("success.html", name=name)


# ============================================
# 4) 관리자 페이지 (기존 로직 유지)
# ============================================
@app.route("/admin/members")
def admin_members():
    sort = request.args.get("sort", "date")

    # 정렬 조건
    if sort == "name":
        members = Members.query.order_by(Members.name.asc()).all()
    elif sort == "branch":
        members = Members.query.order_by(Members.branch.asc()).all()
    elif sort == "visit":
        members = Members.query.order_by(Members.visit_count.desc()).all()
    else:
        members = Members.query.order_by(Members.id.desc()).all()

    # ===== 통계 값 계산 =====
    total_members = Members.query.count()

    today = datetime.now().strftime("%Y-%m-%d")
    today_members = Members.query.filter(Members.created_at.contains(today)).count()

    # 지점별 회원수 
    branch_group = db.session.query(
        Members.branch,
        db.func.count(Members.branch)
    ).group_by(Members.branch).all()

    if branch_group:
        top_branch_name, top_branch_count = max(branch_group, key=lambda x: x[1])
    else:
        top_branch_name, top_branch_count = "없음", 0

    # 전체 방문 횟수 합산
    total_visits = db.session.query(db.func.sum(Members.visit_count)).scalar() or 0

    return render_template(
        "members.html",
        members=members,
        sort=sort,
        total_members=total_members,
        today_members=today_members,
        top_branch_name=top_branch_name,
        top_branch_count=top_branch_count,
        total_visits=total_visits
    )


# ============================================
# ★ 5) 영수증 업로드 화면 (전화번호 입력 → 파일 업로드)
# ============================================
@app.route("/receipt/entry", methods=["GET", "POST"])
def receipt_entry():
    if request.method == "GET":
        return render_template("unified_receipt_entry.html")
        
    # POST: 전화번호 입력 처리
    phone = request.form.get("phone")
    member = Members.query.filter_by(phone=phone).first()

    if not member:
        # 신규 가입 페이지로 유도 (지점 정보는 OCR로 추출 예정이므로 임시 값)
        return render_template("join.html", phone=phone, branch="영수증 등록") 

    # 재방문 고객 확인 → 영수증 업로드 페이지로 이동
    return render_template("receipt_upload.html", member_id=member.id, name=member.name)


# ============================================
# ★ 6) 영수증 처리 및 쿠폰 발급 로직
# ============================================
@app.route("/receipt/process", methods=["POST"])
def receipt_process():
    member_id = request.form.get("member_id")
    member = Members.query.get(member_id)

    if 'receipt_image' not in request.files:
        return render_template("result.html", title="처리 오류", message="파일이 업로드되지 않았습니다.", success=False)

    file = request.files['receipt_image']
    
    # 1. 파일 임시 저장
    image_filename = str(uuid.uuid4()) + ".jpg"
    image_path = os.path.join(app.instance_path, image_filename)
    file.save(image_path)
    
    # 2. OCR 실행 및 텍스트 추출
    ocr_result_text = detect_text_from_receipt(image_path)
    
    # 3. 임시 파일 삭제
    os.remove(image_path)
    
    if not ocr_result_text:
        return render_template("result.html", title="처리 실패", message="영수증에서 텍스트를 인식하지 못했습니다. 명확한 사진으로 다시 시도해 주세요.", success=False)


    # 4. OCR 텍스트 파싱 (services/ocr_parser.py 사용)
    parsed_data = parse_receipt_text(ocr_result_text)
    
    receipt_no = parsed_data["receipt_no"]
    branch_paid = parsed_data["branch_paid"]
    amount = parsed_data["amount"]

    # 파싱 실패 (영수증 번호 추출 실패 시)
    if "PARSE_FAIL" in receipt_no:
        return render_template("result.html", title="영수증 번호 인식 오류", 
                               message="영수증 번호(승인번호)를 정확히 인식하지 못했습니다. 명확한 사진으로 다시 시도해 주세요.", success=False)
    
    # 5. 영수증 중복 확인
    if Receipts.query.filter_by(receipt_no=receipt_no).first():
        return render_template("result.html", title="중복 영수증", message="이미 등록된 영수증입니다. 같은 영수증은 두 번 등록할 수 없습니다.", success=False)
        
    # 6. Receipts 테이블에 저장
    new_receipt = Receipts(
        member_id=member.id,
        receipt_no=receipt_no,
        branch_paid=branch_paid,
        amount=amount,
        visit_date=datetime.now()
    )
    db.session.add(new_receipt)
    db.session.commit()
    
    # 7. 쿠폰 발급 조건 확인 및 발급 (services/coupon_manager.py 사용)
    coupon_issued = issue_coupon_if_qualified(db, Receipts, Coupons, member.id)
    
    if coupon_issued:
        return render_template("result.html", title="성공", message=f"{member.name}님, 영수증 등록이 완료되었습니다! 재방문 조건 충족으로 사은 쿠폰이 발급되었습니다!", success=True)
    else:
        return render_template("result.html", title="성공", message=f"{member.name}님, 영수증 등록이 완료되었습니다. 다음 방문을 통해 쿠폰을 받으세요!", success=True)


# ============================================
# 서버 실행
# ============================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)