import os
from cryptography.fernet import Fernet

import bcrypt

# 경로 설정
APP_ROOT = os.path.dirname(os.path.abspath(__file__))

# [로컬 개발용] 구글 키 파일 자동 로드
GOOGLE_KEY_FILE = os.path.join(APP_ROOT, "google_keys.json")
if os.path.exists(GOOGLE_KEY_FILE):
    with open(GOOGLE_KEY_FILE, "r", encoding="utf-8") as f:
        os.environ['GOOGLE_APPLICATION_CREDENTIALS_JSON'] = f.read()

# 암호화 키 로드 (환경변수 필수)
FERNET_KEY = os.environ.get("FERNET_KEY")
if not FERNET_KEY:
    raise RuntimeError("FERNET_KEY environment variable is not set. Encryption cannot work.")

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

class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError("FLASK_SECRET_KEY environment variable is not set.")
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = database_url or f'sqlite:///{os.path.join(APP_ROOT, "instance", "members.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 관리자 비밀번호 (Bcrypt 해시, 예: $2b$12$...)
    ADMIN_PASSWORD_BCRYPT = os.environ.get("ADMIN_PASSWORD_BCRYPT", "$2b$12$Kj5KSvJ3W.o7s6mKEabht.PLRuWPoJllo9TiYN/17UwvoMA8RIhke")
    
    # 전화번호 검색용 해시 Salt (Pepper)
    PHONE_HASH_PEPPER = os.environ.get("PHONE_HASH_PEPPER", "default_pepper")
    
    # 파일 업로드 제한 (5MB)
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

def check_admin_password(password):
    """입력받은 비밀번호와 환경변수의 Bcrypt 해시를 비교 검증"""
    if not Config.ADMIN_PASSWORD_BCRYPT:
        # 설정이 없으면 로그인 불가
        return False
    
    # 입력된 비밀번호를 bytes로 변환
    password_bytes = password.encode('utf-8')
    # 환경변수의 해시값도 bytes로 변환
    known_hash = Config.ADMIN_PASSWORD_BCRYPT.encode('utf-8')
    
    return bcrypt.checkpw(password_bytes, known_hash)

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
