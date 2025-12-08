from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import uuid

# ★ 모듈 import (services 폴더가 있어야 함)
from services.ocr_parser import detect_text_from_receipt, parse_receipt_text
from services.coupon_manager import issue_coupon_if_qualified

# 경로 설정
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, instance_path=os.path.join(APP_ROOT, 'instance'))
os.makedirs(app.instance_path, exist_ok=True)

# ===== DB 설정 =====
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///members.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ===== 지점 정보 딕셔너리 =====
BRANCH_MAP = {
    "dongdaemun": "동대문점",
    "gmc": "굿모닝시티점",
    "yeongdeungpo": "영등포점",
    "yangjae": "양재점",
    "suwon": "수원영통점",
    "dongtan": "동탄점",
    "lumbini": "룸비니(동묘)"
}

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

class Receipts(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    receipt_no = db.Column(db.String(50), unique=True, nullable=False)
    branch_paid = db.Column(db.String(50))
    amount = db.Column(db.Integer)
    visit_date = db.Column(db.DateTime, default=datetime.now)
    is_coupon_used = db.Column(db.Boolean, default=False) 

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

with app.app_context():
    db.create_all()


# ============================================
# ★ 1. QR 접속 랜딩 페이지 (/start)
# ============================================
@app.route("/start")
def start():
    # URL 예시: /start?branch=dongdaemun
    branch_code = request.args.get("branch", "dongdaemun")
    branch_name = BRANCH_MAP.get(branch_code, "에베레스트")
    
    return render_template("start.html", branch_code=branch_code, branch_name=branch_name)


# ============================================
# ★ 2. 전화번호 확인 및 분기 처리 (/check)
# ============================================
@app.route("/check", methods=["POST"])
def check():
    phone = request.form.get("phone")
    branch_code = request.form.get("branch_code")
    branch_name = BRANCH_MAP.get(branch_code, "에베레스트")

    member = Members.query.filter_by(phone=phone).first()

    if member:
        # [기존 회원] -> 바로 영수증 업로드 화면으로
        today = datetime.now().strftime("%Y-%m-%d")
        if member.last_visit != today:
            member.visit_count += 1
            member.last_visit = today
            db.session.commit()
            
        return render_template("receipt_upload.html", member_id=member.id, name=member.name, branch_name=branch_name)
    else:
        # [신규 회원] -> 가입 화면으로
        return render_template("join.html", phone=phone, branch=branch_name, branch_code=branch_code)


# ============================================
# 3. 신규 가입 처리 (/join)
# ============================================
@app.route("/join", methods=["POST"])
def join():
    name = request.form.get("name")
    phone = request.form.get("phone")
    branch = request.form.get("branch") # 한글 지점명
    branch_code = request.form.get("branch_code")
    birth = request.form.get("birth")

    agree_marketing = "yes" if request.form.get("agree_marketing") else "no"
    agree_privacy = "yes" if request.form.get("agree_privacy") else "no"
    today = datetime.now().strftime("%Y-%m-%d")

    new_member = Members(
        name=name, phone=phone, branch=branch, birth=birth,
        agree_marketing=agree_marketing, agree_privacy=agree_privacy,
        visit_count=1, last_visit=today,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    db.session.add(new_member)
    db.session.commit()

    return render_template("receipt_upload.html", member_id=new_member.id, name=new_member.name, branch_name=branch)


# ============================================
# 4. 영수증 처리 (/receipt/process)
# ============================================
@app.route("/receipt/process", methods=["POST"])
def receipt_process():
    member_id = request.form.get("member_id")
    member = Members.query.get(member_id)

    if 'receipt_image' not in request.files:
        return render_template("result.html", title="오류", message="파일 없음", success=False)
    
    file = request.files['receipt_image']
    ocr_result_text = None
    image_path = None

    try:
        if file.filename == '':
             return render_template("result.html", title="오류", message="파일 선택 필수", success=False)

        # 파일 저장
        image_filename = str(uuid.uuid4()) + ".jpg"
        # ★ 여기가 오류 났던 부분입니다. 괄호를 정확히 닫았습니다.
        image_path = os.path.join(app.instance_path, image_filename)
        file.save(image_path)
        
        # OCR 실행 (여기서 에러 안 나게 services/ocr_parser.py 수정했는지 확인!)
        ocr_result_text = detect_text_from_receipt(image_path)
        
    except Exception as e:
        # 오류 발생 시 파일 정리
        if image_path and os.path.exists(image_path): 
            try:
                os.remove(image_path)
            except:
                pass
        return render_template("result.html", title="오류", message=f"처리 중 오류: {e}", success=False)

    if not ocr_result_text:
        return render_template("result.html", title="실패", message="텍스트 인식 실패", success=False)

    # 파싱 및 저장 로직
    parsed_data = parse_receipt_text(ocr_result_text)
    receipt_no = parsed_data["receipt_no"]
    branch_paid = parsed_data["branch_paid"]
    amount = parsed_data["amount"]

    if "PARSE_FAIL" in receipt_no:
        return render_template("result.html", title="인식 오류", message="영수증 번호 인식 실패", success=False)
    
    if Receipts.query.filter_by(receipt_no=receipt_no).first():
        return render_template("result.html", title="중복", message="이미 등록된 영수증입니다.", success=False)
        
    new_receipt = Receipts(
        member_id=member.id, receipt_no=receipt_no, branch_paid=branch_paid, amount=amount, visit_date=datetime.now()
    )
    db.session.add(new_receipt)
    db.session.commit()
    
    coupon_issued = issue_coupon_if_qualified(db, Receipts, Coupons, member.id)
    
    msg = f"{member.name}님, 영수증({branch_paid}) 등록 완료!"
    if coupon_issued: msg += " 🎉 재방문 쿠폰 발급됨!"
    else: msg += " 쿠폰 미발급 (조건 부족)"

    return render_template("result.html", title="완료", message=msg, success=True)


# ============================================
# 5. 관리자 페이지
# ============================================
@app.route("/admin/members")
def admin_members():
    sort = request.args.get("sort", "date")
    if sort == "name": members = Members.query.order_by(Members.name.asc()).all()
    elif sort == "branch": members = Members.query.order_by(Members.branch.asc()).all()
    elif sort == "visit": members = Members.query.order_by(Members.visit_count.desc()).all()
    else: members = Members.query.order_by(Members.id.desc()).all()

    all_receipts = Receipts.query.order_by(Receipts.visit_date.desc()).all()

    # 통계
    total_members = Members.query.count()
    today = datetime.now().strftime("%Y-%m-%d")
    today_members = Members.query.filter(Members.created_at.contains(today)).count()
    total_visits = db.session.query(db.func.sum(Members.visit_count)).scalar() or 0
    
    # 지점 통계 (없으면 에러 방지)
    branch_group = db.session.query(Members.branch, db.func.count(Members.branch)).group_by(Members.branch).all()
    top_branch_name, top_branch_count = max(branch_group, key=lambda x: x[1]) if branch_group else ("없음", 0)

    return render_template("members.html", members=members, sort=sort, 
                           total_members=total_members, today_members=today_members, 
                           top_branch_name=top_branch_name, top_branch_count=top_branch_count, 
                           total_visits=total_visits, all_receipts=all_receipts)


# 테스트용 메인 리다이렉트
@app.route("/")
def index():
    return redirect("/start?branch=dongdaemun")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)