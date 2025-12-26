
from app import app, db, Members

def migrate():
    with app.app_context():
        print("Starting migration...")
        members = Members.query.all()
        count = 0
        for m in members:
            # m.name을 읽을 때:
            # 1. 256비트 암호화 전 평문 데이터 -> decrypt_data -> try/except -> 평문 반환
            # 2. 이미 암호화된 데이터 -> decrypt_data -> 평문 반환
            
            # 읽은 값을 다시 쓰면 setter 호출 -> encrypt_data -> 암호문 저장
            original_name = m.name
            original_phone = m.phone
            original_birth = m.birth
            
            m.name = original_name
            m.phone = original_phone
            m.birth = original_birth
            count += 1
            
        db.session.commit()
        print(f"Migration completed. {count} members processed.")

if __name__ == "__main__":
    migrate()
