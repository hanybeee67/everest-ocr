
from flask import current_app

def send_notification(phone, message):
    """
    [Placeholder] SMS or KakaoTalk notification sender.
    Currently just logs the message. Integrate with Solapi/Aligo later.
    """
    try:
        # 실제 발송 로직이 들어갈 곳
        # 예: api.send_sms(to=phone, text=message)
        
        # 로그로 대체 확인
        current_app.logger.info(f"[NOTIFICATION] To: {phone} | Msg: {message}")
        print(f"📨 [전송됨] {phone}: {message}")
        return True
    except Exception as e:
        current_app.logger.error(f"Notification failed: {e}")
        return False
