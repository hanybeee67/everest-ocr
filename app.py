from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime
import os
import uuid
import json

# OCR 및 쿠폰 서비스 모듈
from services.ocr_parser import detect_text_from_receipt, parse_receipt_text
from services.coupon_manager import issue_coupon_if_qualified

# 경로 설정
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, instance_path=os.path.join(APP_ROOT, 'instance'))
os.makedirs(app.instance_path, exist_ok=True)

# ★ [보안] 세션 암호화 키
app.secret_key = "everest_secret_key_8848" 

# DB 설정
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///members.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 지점 정보
BRANCH_MAP = {
    "dongdaemun": "동대문점",
    "gmc": "굿모닝시티점",
    "yeongdeungpo": "영등포점",
    "yangjae": "양재점",
    "suwon": "수원영통점",
    "dongtan": "동탄점",
    "lumbini": "룸비니(동묘)"
}

# 모델 정의
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

# --- 라우트 ---

@app.route("/")
def index():
    return redirect("/start?branch=dongdaemun")

@app.route("/start")
def start():
    branch_code = request.args.get("branch", "dongdaemun")
    branch_name = BRANCH_MAP.get(branch_code, "에베레스트")
    return render_template("start.html", branch_code=branch_code, branch_name=branch_name)

@app.route("/check", methods=["POST"])
def check():
    phone = request.form.get("phone")
    branch_code = request.form.get("branch_code")
    branch_name = BRANCH_MAP.get(branch_code, "에베레스트")

    member = Members.query.filter_by(phone=phone).first()

    if member:
        # 재방문 고객: DB에 있는 방문 횟수 그대로 전달
        return render_template("receipt_upload.html", member_id=member.id, name=member.name, branch_name=branch_name, visit_count=member.visit_count)
    else:
        return render_template("join.html", phone=phone, branch=branch_name, branch_code=branch_code)

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
        name=name, phone=phone, branch=branch, birth=birth,
        agree_marketing=agree_marketing, agree_privacy=agree_privacy,
        visit_count=0, 
        last_visit=today,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    db.session.add(new_member)
    db.session.commit()

    # ★ [수정 1] 신규 가입 직후 '1번째 방문'이라고 뜨게 하기 위해 visit_count=1을 강제로 전달
    return render_template("receipt_upload.html", member_id=new_member.id, name=new_member.name, branch_name=branch, visit_count=1)

@app.route("/receipt/process", methods=["POST"])
def receipt_process():
    member_id = request.form.get("member_id")
    member = Members.query.get(member_id)

    if 'receipt_image' not in request.files:
        return render_template("result.html", title="오류", message="파일이 없습니다.", success=False)
    
    file = request.files['receipt_image']
    if file.filename == '':
        return render_template("result.html", title="오류", message="파일을 선택해주세요.", success=False)

    ocr_result_text = None
    image_path = None

    try:
        image_filename = str(uuid.uuid4()) + ".jpg"
        image_path = os.path.join(app.instance_path, image_filename)
        file.save(image_path)
        
        # OCR 실행
        ocr_result_text = detect_text_from_receipt(image_path)
        
    except Exception as e:
        if image_path and os.path.exists(image_path):
            try: os.remove(image_path)
            except: pass
        return render_template("result.html", title="시스템 오류", message=f"처리 중 오류 발생: {e}", success=False)

    if not ocr_result_text:
        return render_template("result.html", title="인식 실패", message="영수증 글자를 읽을 수 없습니다.", success=False)

    # 파싱
    parsed_data = parse_receipt_text(ocr_result_text)
    receipt_no = parsed_data["receipt_no"]
    branch_paid = parsed_data["branch_paid"]
    amount = parsed_data["amount"]

    # 중복 체크
    if Receipts.query.filter_by(receipt_no=receipt_no).first():
        return render_template("result.html", title="이미 등록된 영수증", 
                               message="이미 등록하신 영수증입니다.", success=False)

    # 영수증 저장
    new_receipt = Receipts(
        member_id=member.id, receipt_no=receipt_no, branch_paid=branch_paid, amount=amount, visit_date=datetime.now()
    )
    db.session.add(new_receipt)
    
    # 방문 정보 업데이트
    today = datetime.now().strftime("%Y-%m-%d")
    if member.last_visit != today:
        member.visit_count += 1
        member.last_visit = today
    
    db.session.commit()
    
    # 쿠폰 발급
    coupon_issued = issue_coupon_if_qualified(db, Receipts, Coupons, member.id)
    
    # 총 누적 금액
    total_spent = db.session.query(func.sum(Receipts.amount)).filter_by(member_id=member.id).scalar() or 0

    return render_template("result.html", 
                           success=True,
                           title="적립 완료",
                           member_name=member.name,
                           visit_count=member.visit_count,
                           current_amount=amount,
                           total_amount=total_spent,
                           coupon_issued=coupon_issued)

# --- [보안 및 관리자 기능] ---

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password")
        if password == "everest1234":
            session['admin_logged_in'] = True
            return redirect("/admin/members")
        else:
            return render_template("login.html", error="암호가 틀렸습니다.")
    return render_template("login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect("/admin/login")

@app.route("/admin/members")
def admin_members():
    if not session.get('admin_logged_in'):
        return redirect("/admin/login")

    sort = request.args.get("sort", "date")
    if sort == "name": members = Members.query.order_by(Members.name.asc()).all()
    elif sort == "branch": members = Members.query.order_by(Members.branch.asc()).all()
    elif sort == "visit": members = Members.query.order_by(Members.visit_count.desc()).all()
    else: members = Members.query.order_by(Members.id.desc()).all()
    
    all_receipts = Receipts.query.order_by(Receipts.visit_date.desc()).all()
    
    total_members = Members.query.count()
    total_visits = db.session.query(db.func.sum(Members.visit_count)).scalar() or 0
    
    return render_template("members.html", members=members, sort=sort, total_members=total_members, total_visits=total_visits, all_receipts=all_receipts)

# ★ [수정 2] 관리자용 회원 삭제 기능 추가
@app.route("/admin/delete_member/<int:id>")
def delete_member(id):
    if not session.get('admin_logged_in'):
        return redirect("/admin/login")
    
    member = Members.query.get(id)
    if member:
        # 회원을 지우기 전에 관련된 영수증과 쿠폰을 먼저 지워야 에러가 안 납니다.
        Receipts.query.filter_by(member_id=id).delete()
        Coupons.query.filter_by(member_id=id).delete()
        db.session.delete(member)
        db.session.commit()
    
    return redirect("/admin/members")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)