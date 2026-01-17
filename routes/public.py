from flask import Blueprint, render_template, request, redirect, current_app
from sqlalchemy import func
from datetime import datetime
import os
import uuid
from models import db, Members, Receipts, Coupons
from config import BRANCH_MAP
from services.ocr_parser import detect_text_from_receipt, parse_receipt_text
from services.coupon_manager import issue_coupon_if_qualified

from PIL import Image

public_bp = Blueprint('public', __name__)

@public_bp.route("/")
def index():
    return redirect("/start?branch=dongdaemun")

@public_bp.route("/start")
def start():
    branch_code = request.args.get("branch", "dongdaemun")
    branch_name = BRANCH_MAP.get(branch_code, "에베레스트")
    return render_template("start.html", branch_code=branch_code, branch_name=branch_name)

@public_bp.route("/check", methods=["POST"])
def check():
    phone = request.form.get("phone")
    branch_code = request.form.get("branch_code")
    branch_name = BRANCH_MAP.get(branch_code, "에베레스트")
    
    # [수정] 암호화된 전화번호 매칭을 위해 전체 검색 + 정규화(하이픈/공백 제거) 비교
    # [수정] phone_hash_value를 이용한 고속 검색
    try:
        input_hash = Members.generate_phone_hash(phone)
        member = Members.query.filter_by(phone_hash_value=input_hash).first()
    except Exception as e:
        # 해시 생성 실패 등 예외 발생 시 안전하게 None 처리
        current_app.logger.error(f"Phone lookup failed: {e}")
        member = None

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

@public_bp.route("/join", methods=["POST"])
def join():
    name = request.form.get("name")
    phone = request.form.get("phone")
    branch = request.form.get("branch")
    birth = request.form.get("birth")
    gender = request.form.get("gender")       # [신규]
    age_group = request.form.get("age_group") # [신규]
    
    agree_marketing = "yes" if request.form.get("agree_marketing") else "no"
    agree_privacy = "yes" if request.form.get("agree_privacy") else "no"
    today = datetime.now().strftime("%Y-%m-%d")

    new_member = Members(
        name=name, phone=phone, branch=branch, birth=birth,
        gender=gender, age_group=age_group,
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

@public_bp.route("/receipt/process", methods=["POST"])
def receipt_process():
    member_id = request.form.get("member_id")
    member = Members.query.get(member_id)

    if 'receipt_image' not in request.files:
        return render_template("result.html", title="오류", message="파일이 없습니다.", success=False)
    
    file = request.files['receipt_image']
    if file.filename == '':
        return render_template("result.html", title="오류", message="파일을 선택해주세요.", success=False)
    
    # [보안] 파일 확장자 검사
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in ALLOWED_EXTENSIONS:
        return render_template("result.html", title="오류", message="jpg, jpeg, png 파일만 업로드 가능합니다.", success=False)

    ocr_result_text = None
    image_path = None

    try:
        image_filename = str(uuid.uuid4()) + ".jpg"
        image_path = os.path.join(current_app.instance_path, image_filename)
        file.save(image_path)
        
        # [보안] 이미지 무결성 검사 (Pillow)
        try:
            with Image.open(image_path) as img:
                img.verify()
        except Exception:
            try: os.remove(image_path)
            except: pass
            return render_template("result.html", title="보안 경고", message="유효하지 않은 이미지 파일입니다.", success=False)
            
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
