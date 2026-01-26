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
from extensions import limiter

@public_bp.route("/")
def index():
    return redirect("/start?branch=dongdaemun")

@public_bp.route("/admin")
def admin_redirect():
    return redirect("/admin_8848/login")

@public_bp.route("/start")
def start():
    branch_code = request.args.get("branch", "dongdaemun")
    branch_name = BRANCH_MAP.get(branch_code, "에베레스트")
    return render_template("start.html", branch_code=branch_code, branch_name=branch_name)

@public_bp.route("/check", methods=["POST"])
@limiter.limit("5 per minute") # [보안] 전화번호 조회 폭탄 방지
def check():
    phone = request.form.get("phone")
    branch_code = request.form.get("branch_code")
    branch_name = BRANCH_MAP.get(branch_code, "에베레스트")
    
    # [수정] 암호화된 전화번호 매칭을 위해 전체 검색 + 정규화(하이픈/공백 제거) 비교
    # [수정] phone_hash_value를 이용한 고속 검색
    try:
        input_hash = Members.generate_phone_hash(phone)
        member = Members.query.filter_by(phone_hash_value=input_hash).first()
        
        # [Fallback] 해시 조회 실패 시, 전체 검색 (Legacy Data 또는 해시 미생성 건 대응)
        if not member:
            current_app.logger.info(f"Hash lookup failed for {phone}, trying fallback...")
            # 입력값 정규화
            norm_input = phone.replace("-", "").replace(" ", "").strip()
            
            # 전체 회원 순회 (성능 이슈 가능성 있으나, 정확도 우선)
            # 최적화를 위해 fetchall 대신 yield_per 사용 고려 가능하나, 일단 단순 순회
            all_members = Members.query.all() 
            for m in all_members:
                try:
                    # m.phone은 복호화된 값 반환
                    db_phone = m.phone
                    if not db_phone: continue
                    
                    norm_db = db_phone.replace("-", "").replace(" ", "").strip()
                    if norm_db == norm_input:
                        member = m
                        # [Self-Healing] 해시가 없거나 잘못되었다면 갱신
                        if m.phone_hash_value != input_hash:
                            m.phone_hash_value = input_hash
                            db.session.commit()
                            current_app.logger.info(f"Self-healed hash for member {m.id}")
                        break
                except Exception:
                    continue

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

@public_bp.route("/my-coupons")
def my_coupons_redirect():
    # [Short URL Support] /my-coupons -> /reward/my-coupons (쿼리 파라미터 유지)
    from flask import url_for
    return redirect(url_for('reward.my_coupons', **request.args))

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

    today_date = datetime.now()
    new_member = Members(
        name=name, phone=phone, branch=branch, birth=birth,
        gender=gender, age_group=age_group,
        agree_marketing=agree_marketing, agree_privacy=agree_privacy,
        visit_count=0, 
        last_visit=today,
        created_at=today_date.strftime("%Y-%m-%d %H:%M:%S")
    )
    db.session.add(new_member)
    db.session.flush() # ID 생성을 위해 flush
    
    db.session.flush() # ID 생성을 위해 flush
    
    # [Start-Up Event] 신규 가입 웰컴 쿠폰 (플레인 난) 발급
    # [Refactor] 비즈니스 로직 분리 (services/coupon_service.py)
    try:
        from services.coupon_service import process_signup_bonus
        process_signup_bonus(new_member)
    except Exception as e:
        current_app.logger.error(f"Signup bonus process failed: {e}")
        # 오류 발생해도 가입은 완료 처리 (보수적 접근)
        db.session.commit()
    
    # 신규 회원은 내역 없음
    recent_history = []
    
    return render_template("receipt_upload.html", 
                           member_id=new_member.id, 
                           name=new_member.name, 
                           branch_name=branch, 
                           visit_count=0,
                           recent_history=recent_history,
                           coupon_issued="회원가입 완료!<br><b>카톡 채널을 추가</b>하시고 직원에게 보여주시면<br>'플레인 난'을 무료로 드립니다.")
    
    # 신규 회원은 내역 없음
    recent_history = []
    
    return render_template("receipt_upload.html", 
                           member_id=new_member.id, 
                           name=new_member.name, 
                           branch_name=branch, 
                           visit_count=0,
                           recent_history=recent_history,
                           coupon_issued="회원가입 완료!<br><b>카톡 채널을 추가</b>하시고 직원에게 보여주시면<br>'플레인 난'을 무료로 드립니다.")

@public_bp.route("/receipt/process", methods=["POST"])
@limiter.limit("3 per minute") # [보안] 이미지 업로드 폭탄 방지
def receipt_process():
    member_id = request.form.get("member_id")
    member = Members.query.get(member_id)

    if 'receipt_image' not in request.files:
        return render_template("result.html", title="오류", message="파일이 없습니다.", success=False)
    
    file = request.files['receipt_image']
    if file.filename == '':
        return render_template("result.html", title="오류", message="파일을 선택해주세요.", success=False)
    
    # [보안] 파일 확장자 검사 (heic 추가 support attempt)
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'heic', 'heif'}
    if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in ALLOWED_EXTENSIONS:
        return render_template("result.html", title="오류", message="이미지 파일(jpg, png 등)만 업로드 가능합니다.", success=False)

    ocr_result_text = None
    image_path = None

    try:
        # 파일명 안전하게 저장
        ext = file.filename.rsplit('.', 1)[1].lower()
        image_filename = str(uuid.uuid4()) + f".{ext}"
        image_path = os.path.join(current_app.instance_path, image_filename)
        file.save(image_path)
        
        current_app.logger.info(f"Image saved to {image_path}, size: {os.path.getsize(image_path)}")

        # [보안] 이미지 무결성 검사 (Pillow) - HEIC는 Pillow 기본 미지원일 수 있으므로 try-except 완화
        try:
            with Image.open(image_path) as img:
                img.verify()
        except Exception as e:
            current_app.logger.warning(f"Image verification warning (might be HEIC): {e}")
            # HEIC라면 검증 실패해도 일단 진행 (Google Vision이 처리하도록)
            if ext not in ['heic', 'heif']:
                try: os.remove(image_path)
                except: pass
                return render_template("result.html", title="보안 경고", message="유효하지 않은 이미지 파일입니다.", success=False)
            
        ocr_result_text = detect_text_from_receipt(image_path)
        current_app.logger.info(f"OCR Result Length: {len(ocr_result_text) if ocr_result_text else 0}")
        

        
        # [보안 강화] 사업자등록번호 검증 (가짜/수기 영수증 차단)
        # 이제 단순 키워드('에베레스트')가 아닌, 등록된 사업자번호 유무로 판단합니다.
        from services.ocr_parser import check_business_number
        is_valid_biz, matched_biz = check_business_number(ocr_result_text)
        
        if is_valid_biz:
            current_app.logger.info(f"Valid Business Number Found: {matched_biz}")
        else:
            # 실패 시에도 이미지는 삭제해야 함
            if image_path and os.path.exists(image_path):
                os.remove(image_path)
            
            if ocr_result_text:
                current_app.logger.warning(f"Invalid Receipt (No Biz Num): {ocr_result_text[:100]}...")
                
            return render_template("result.html", 
                                 title="인증 실패", 
                                 message="영수증에서 '사업자등록번호'를 식별할 수 없습니다.<br>화질이 흐릿하거나 구겨진 영수증은 인식이 어렵습니다.<br>선명하게 다시 촬영해주시거나 직원에게 문의해주세요.", 
                                 success=False)
        
    except Exception as e:
        current_app.logger.error(f"Receipt Process Error: {e}", exc_info=True)
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
    
    current_app.logger.info(f"Parsed Data: {parsed_data}")

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
    
    # [수정] 조건부 자동 승인 로직 (15만원 기준)
    THRESHOLD_AUTO_APPROVE = 150000
    status = 'PENDING'
    save_message = ""
    
    if amount < THRESHOLD_AUTO_APPROVE:
        status = 'APPROVED'
        # 자동 승인: 포인트 즉시 적립
        member.current_reward_balance = (member.current_reward_balance or 0) + amount
        member.total_lifetime_spend = (member.total_lifetime_spend or 0) + amount
        save_message = "적립이 완료되었습니다. (자동 승인)"
        
        # 자동 승인된 건은 이미지 삭제 (용량 절약)
        if image_path and os.path.exists(image_path):
            try: os.remove(image_path)
            except: pass
        image_url = None
        
    else:
        status = 'PENDING'
        # 고액 건: 관리자 승인 대기 (포인트 적립 보류)
        save_message = "15만원 이상 고액 결제는 관리자 승인 후 적립됩니다."
        
        # 승인 대기 건은 이미지 보존 (관리자 확인용)
        # 이미지 경로는 웹에서 접근 가능하도록 상대 경로로 저장하거나 별도 처리 필요
        # 현재는 instance 폴더에 있으므로, static 등으로 옮기거나, 일단 파일명 기록
        image_url = image_filename 
    
    db.session.add(new_receipt)
    new_receipt.status = status
    new_receipt.amount_claimed = amount
    new_receipt.image_url = image_url
    
    try:
        db.session.commit()
    except Exception as e:
        # [예외 처리] 중복 키 오류(IntegrityError) 등 DB 커밋 실패 대응
        db.session.rollback()
        current_app.logger.error(f"Receipt DB Commit Error: {e}")
        
        # 이미지는 삭제
        if image_path and os.path.exists(image_path):
            try: os.remove(image_path)
            except: pass
            
        # 중복 에러일 가능성이 높으므로 안내 메시지
        if "UNIQUE constraint" in str(e) or "UniqueViolation" in str(e):
             return render_template("result.html", title="이미 등록된 영수증", message="이미 등록하신 영수증입니다.", success=False)
             
        return render_template("result.html", title="시스템 오류", message="데이터 저장 중 오류가 발생했습니다. 다시 시도해주세요.", success=False)
    
    total_spent = member.total_lifetime_spend or 0

    return render_template("result.html", 
                           success=True,
                           title="처리 완료",
                           member_name=member.name,
                           visit_count=member.visit_count,
                           current_amount=amount,
                           total_amount=total_spent,
                           coupon_issued=save_message,
                           member_id=member.id,
                           phone=member.phone)
