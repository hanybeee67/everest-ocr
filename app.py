from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime
import datetime as dt_module # datetime 객체 충돌 방지용
import os
import uuid
import json
import hashlib

# OCR 및 쿠폰 서비스 모듈
# (주의: services/ocr_parser.py 파일은 아까 수정한 최신 버전을 그대로 둡니다)
from services.ocr_parser import detect_text_from_receipt, parse_receipt_text
from services.coupon_manager import issue_coupon_if_qualified

# 경로 설정
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, instance_path=os.path.join(APP_ROOT, 'instance'))
os.makedirs(app.instance_path, exist_ok=True)

# [로컬 개발용] 구글 키 파일 자동 로드
GOOGLE_KEY_FILE = os.path.join(APP_ROOT, "google_keys.json")
if os.path.exists(GOOGLE_KEY_FILE):
    with open(GOOGLE_KEY_FILE, "r", encoding="utf-8") as f:
        os.environ['GOOGLE_APPLICATION_CREDENTIALS_JSON'] = f.read()

from cryptography.fernet import Fernet

# 보안 키 (세션용)
app.secret_key = "everest_secret_key_8848" 

# 관리자 비밀번호 해시 (SHA-256) -> "everest1234"
ADMIN_PASSWORD_HASH = "1b77f72b1a137d87dc8e667a47c2c4ffb6fa8156aed1de7bc9d62e0cc5a8fefd"

# 암호화 키 로드 (없으면 생성 - 임시 방편, 배포 시 주의)
KEY_FILE = "encryption_key.txt"
if not os.path.exists(KEY_FILE):
    with open(KEY_FILE, "wb") as f:
        f.write(Fernet.generate_key())

with open(KEY_FILE, "r", encoding="utf-8") as f:
    FERNET_KEY = f.read().strip()
cipher_suite = Fernet(FERNET_KEY)

def encrypt_data(data):
    if not data: return data
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(data):
    if not data: return data
    try:
        return cipher_suite.decrypt(data.encode()).decode()
    except:
        return data  # 마이그레이션 전 평문일 경우 그대로 반환

# DB 설정
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(app.instance_path, "members.db")}'
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
    _name = db.Column("name", db.String(255))  # DB 컬럼명 'name' 매핑
    _phone = db.Column("phone", db.String(255), unique=True) # DB 컬럼명 'phone' 매핑
    _birth = db.Column("birth", db.String(255)) # DB 컬럼명 'birth' 매핑
    
    @property
    def name(self):
        return decrypt_data(self._name)
    
    @name.setter
    def name(self, value):
        self._name = encrypt_data(value)

    @property
    def phone(self):
        return decrypt_data(self._phone)
    
    @phone.setter
    def phone(self, value):
        self._phone = encrypt_data(value)

    @property
    def birth(self):
        return decrypt_data(self._birth)
    
    @birth.setter
    def birth(self, value):
        self._birth = encrypt_data(value)
        
    # 기존 코드 호환을 위해 생성자 오버라이드 불필요 (kwargs로 설정 시 setter 호출됨)
    
    branch = db.Column(db.String(50))
    agree_marketing = db.Column(db.String(5))
    agree_privacy = db.Column(db.String(5))
    visit_count = db.Column(db.Integer, default=0)      
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
    
    # [수정] 암호화된 전화번호 매칭을 위해 전체 검색 + 정규화(하이픈/공백 제거) 비교
    all_members = Members.query.all()
    member = None
    
    # 입력된 전화번호 정규화 (숫자만 남김)
    normalized_input_phone = phone.replace("-", "").replace(" ", "").strip()
    
    for m in all_members:
        # DB에 저장된 번호 복호화 후 정규화
        stored_phone = m.phone or ""
        normalized_stored_phone = stored_phone.replace("-", "").replace(" ", "").strip()
        
        if normalized_stored_phone == normalized_input_phone:
            member = m
            break

    if member:
        # 최근 3건 내역 조회 (누적 금액 포함)
        all_receipts = Receipts.query.filter_by(member_id=member.id).order_by(Receipts.visit_date.asc()).all()
        history = []
        cumulative_total = 0
        for r in all_receipts:
            cumulative_total += r.amount
            history.append({
                "date": r.visit_date.strftime("%Y-%m-%d"),
                "amount": r.amount,
                "total": cumulative_total
            })
        
        # 최근 3건만 추출하고 역순 정렬 (최신순)
        recent_history = history[-3:][::-1]

        return render_template("receipt_upload.html", 
                               member_id=member.id, 
                               name=member.name, 
                               branch_name=branch_name, 
                               visit_count=member.visit_count,
                               recent_history=recent_history)
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
    
    # 신규 회원은 내역 없음
    recent_history = []
    
    return render_template("receipt_upload.html", 
                           member_id=new_member.id, 
                           name=new_member.name, 
                           branch_name=branch, 
                           visit_count=0,
                           recent_history=recent_history)

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
        ocr_result_text = detect_text_from_receipt(image_path)
        
    except Exception as e:
        if image_path and os.path.exists(image_path):
            try: os.remove(image_path)
            except: pass
        return render_template("result.html", title="시스템 오류", message=f"처리 중 오류 발생: {e}", success=False)

    if not ocr_result_text:
        return render_template("result.html", title="인식 실패", message="영수증 글자를 읽을 수 없습니다.", success=False)

    parsed_data = parse_receipt_text(ocr_result_text)
    receipt_no = parsed_data["receipt_no"]
    branch_paid = parsed_data["branch_paid"]
    amount = parsed_data["amount"]

    # [Rule 1] 1일 1회 적립 제한
    # 단, 환불(음수)인 경우는 제한에서 제외하여 언제든 취소 가능하게 함
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 오늘 이 회원이 올린 영수증이 있는지 확인
    today_receipt = Receipts.query.filter(
        Receipts.member_id == member.id, 
        Receipts.visit_date >= today_start
    ).first()

    # 금액이 양수(일반 적립)인데 이미 오늘 내역이 있다면 차단
    if amount > 0 and today_receipt:
        return render_template("result.html", 
                               title="적립 제한", 
                               message="하루에 한 번만 적립 가능합니다. (내일 다시 방문해주세요!)", 
                               success=False)

    # [Rule 2] 중복 영수증 차단 (기존 로직)
    if Receipts.query.filter_by(receipt_no=receipt_no).first():
        return render_template("result.html", title="이미 등록된 영수증", message="이미 등록하신 영수증입니다.", success=False)

    new_receipt = Receipts(
        member_id=member.id, receipt_no=receipt_no, branch_paid=branch_paid, amount=amount, visit_date=datetime.now()
    )
    db.session.add(new_receipt)
    
    # 방문 횟수 증가 로직 (강화됨)
    today = datetime.now().strftime("%Y-%m-%d")
    current_count = member.visit_count if member.visit_count is not None else 0
    
    # 환불(amount < 0)이 아닐 때만 방문 횟수 증가
    if amount > 0:
        if current_count == 0 or member.last_visit != today:
            member.visit_count = current_count + 1
            member.last_visit = today
    
    db.session.commit()
    
    # ★ 쿠폰 발급 (리스트 반환 지원)
    issued_coupons_list = issue_coupon_if_qualified(db, Receipts, Coupons, member.id)
    if issued_coupons_list:
        coupon_message = ", ".join(issued_coupons_list)
    else:
        coupon_message = None

    total_spent = db.session.query(func.sum(Receipts.amount)).filter_by(member_id=member.id).scalar() or 0

    return render_template("result.html", 
                           success=True,
                           title="적립 완료",
                           member_name=member.name,
                           visit_count=member.visit_count,
                           current_amount=amount,
                           total_amount=total_spent,
                           coupon_issued=coupon_message)

# --- 관리자 및 쿠폰 시스템 ---

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password")
        # SHA-256 해시 비교
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if password_hash == ADMIN_PASSWORD_HASH:
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

@app.route("/admin/delete_member/<int:id>")
def delete_member(id):
    if not session.get('admin_logged_in'):
        return redirect("/admin/login")
    member = Members.query.get(id)
    if member:
        Receipts.query.filter_by(member_id=id).delete()
        Coupons.query.filter_by(member_id=id).delete()
        db.session.delete(member)
        db.session.commit()
    return redirect("/admin/members")

# [신규] 쿠폰 관리 페이지
@app.route("/admin/coupons")
def admin_coupons():
    if not session.get('admin_logged_in'):
        return redirect("/admin/login")
    
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
@app.route("/admin/use_coupon/<int:coupon_id>")
def use_coupon(coupon_id):
    if not session.get('admin_logged_in'):
        return redirect("/admin/login")
    
    coupon = Coupons.query.get(coupon_id)
    keyword = request.args.get("keyword", "")
    
    if coupon and not coupon.is_used:
        coupon.is_used = True
        coupon.used_date = datetime.now()
        coupon.used_at_branch = "관리자처리" 
        db.session.commit()
    
    return redirect(f"/admin/coupons?keyword={keyword}")

@app.route("/admin/member/<int:member_id>/edit", methods=["GET", "POST"])
def edit_member(member_id):
    if not session.get('admin_logged_in'):
        return redirect("/admin/login")
    
    member = Members.query.get(member_id)
    if not member:
        return "회원 정보를 찾을 수 없습니다."

    # 현재 누적 금액 계산
    current_total = db.session.query(func.sum(Receipts.amount)).filter_by(member_id=member.id).scalar() or 0

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
        return redirect("/admin/members")

    return render_template("edit_member.html", member=member, total_amount=current_total)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)