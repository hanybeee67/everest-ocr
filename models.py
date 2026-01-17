from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from config import encrypt_data, decrypt_data

db = SQLAlchemy()

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
        # 검색용 해시 생성 및 저장
        if value:
            self.phone_hash_value = Members.generate_phone_hash(value)

    # 검색용 해시 컬럼
    phone_hash_value = db.Column(db.String(128), index=True)

    @staticmethod
    def generate_phone_hash(phone_number):
        import hashlib
        from config import Config
        # 정규화: 하이픈, 공백 제거
        normalized = phone_number.replace("-", "").replace(" ", "").strip()
        # Pepper 추가
        plain = normalized + Config.PHONE_HASH_PEPPER
        # SHA-256 해싱
        return hashlib.sha256(plain.encode()).hexdigest()

    @property
    def birth(self):
        return decrypt_data(self._birth)
    
    @birth.setter
    def birth(self, value):
        self._birth = encrypt_data(value)
        
    branch = db.Column(db.String(50))
    gender = db.Column(db.String(10))     # [신규] 성별
    age_group = db.Column(db.String(20))  # [신규] 연령대
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
