
from app import create_app, db
from models import Staffs
from config import BRANCH_MAP
import bcrypt

app = create_app()

def seed_staffs():
    with app.app_context():
        # 기본 직원 생성 (테스트용)
        # PIN: 1234
        pin = "1234"
        hashed = bcrypt.hashpw(pin.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # 동대문점 직원
        if not Staffs.query.filter_by(name="관리자").first():
            staff1 = Staffs(branch="dongdaemun", name="관리자", pin_hash=hashed)
            db.session.add(staff1)
            print("Staff '관리자' created for dongdaemun (PIN: 1234)")
        
        # 각 지점별 테스트 직원 생성
        for code, name in BRANCH_MAP.items():
            if code == "dongdaemun": continue
            if not Staffs.query.filter_by(branch=code).first():
                s = Staffs(branch=code, name=f"{name}직원", pin_hash=hashed)
                db.session.add(s)
                print(f"Staff for {name} created.")
                
        db.session.commit()
        print("Staff seeding completed.")

if __name__ == "__main__":
    seed_staffs()
