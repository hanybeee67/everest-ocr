
from flask import current_app


def get_alimtalk_template(template_type, **kwargs):
    """
    카카오 알림톡 심사 기준 강화(2026.01.01)에 따른 표준 템플릿 생성.
    - 정보성 메시지 한정 (광고성 문구 금지)
    - 발송 근거 명시 필수
    - 유효기간 안내 필수
    """
    base_footer = "\n\n[발송 근거]\n"
    
    if template_type == "WELCOME":
        # 가입 축하 쿠폰 (계약/가입에 의한 혜택 지급)
        coupon_name = kwargs.get("coupon_name")
        link = kwargs.get("link")
        expiry_date = kwargs.get("expiry_date") # datetime object or string
        
        msg = f"""[에베레스트] 멤버십 가입이 완료되었습니다.

고객님께 감사의 마음을 담아 아래 쿠폰이 지급되었습니다.

- 쿠폰명: {coupon_name}
- 유효기간: {expiry_date} 까지
- 사용조건: 카카오톡 채널 추가 후 직원 제시

▶ 쿠폰 확인하기:
{link}

[발송 근거]
이 메시지는 멤버십 회원가입 계약에 따라 지급된 혜택 안내 메시지입니다."""
        return msg

    elif template_type == "REWARD":
        # 포인트 교환 쿠폰 (적립된 포인트로 구매/교환한 결과)
        coupon_name = kwargs.get("coupon_name")
        link = kwargs.get("link")
        expiry_date = kwargs.get("expiry_date")
        points_used = kwargs.get("points_used")
        
        msg = f"""[에베레스트] 리워드 교환이 완료되었습니다.

보유하신 포인트로 아래 쿠폰이 교환(발급)되었습니다.

- 교환 상품: {coupon_name}
- 차감 포인트: {points_used:,} P
- 유효기간: {expiry_date} 까지

▶ 쿠폰 확인하기:
{link}

[발송 근거]
이 메시지는 고객님이 적립된 포인트로 교환하신 쿠폰 내역 안내 메시지입니다."""
        return msg
        
    return ""

def send_alimtalk(phone, template_code, variable_map, button_info=None):
    """
    알리고 알림톡 발송 (Placeholder)
    - template_code: 알리고 템플릿 코드 (예: TB_1234)
    - variable_map: 템플릿 내 변수 치환값 (예: {'#{이름}': '홍길동'})
    - button_info: 버튼 정보 (JSON string or dict)
    """
    try:
        # 실제 알리고 API 연동 시 필요한 데이터 구조
        payload = {
            "receiver": phone,
            "tpl_code": template_code,
            "replacements": variable_map, # 알리고 API에 따라 포맷 조정 필요
            "button_1": button_info
        }
        
        # 로그로 데이터 확인
        current_app.logger.info(f"[ALIGO ALIMTALK] To: {phone} | Tpl: {template_code}")
        current_app.logger.info(f"Vars: {variable_map}")
        current_app.logger.info(f"Button: {button_info}")
        
        # 콘솔 출력 (개발용)
        print(f"📨 [알림톡 발송 요청]\n수신: {phone}\n템플릿: {template_code}\n변수: {variable_map}\n버튼: {button_info}")
        return True
    except Exception as e:
        current_app.logger.error(f"Alimtalk failed: {e}")
        return False

def send_notification(phone, message):
    """
    [Legacy] 일반 문자/알림톡 발송 (단순 텍스트)
    """
    try:
        current_app.logger.info(f"[NOTIFICATION] To: {phone} | Msg: {message}")
        print(f"📨 [전송됨] {phone}: \n{message}")
        return True
    except Exception as e:
        current_app.logger.error(f"Notification failed: {e}")
        return False
