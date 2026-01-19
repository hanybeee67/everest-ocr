
from sqlalchemy import text, inspect
from models import db
from flask import current_app

def check_and_fix_schema():
    """
    배포 환경에서 마이그레이션이 꼬였을 때를 대비한 Self-Healing 로직.
    직접 DB 스키마를 검사하고 누락된 컬럼이나 테이블이 있으면 Raw SQL로 추가한다.
    """
    try:
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()
        
        with db.engine.connect() as conn:
            # 1. Members 테이블 컬럼 확인 및 복구
            if 'members' in existing_tables:
                columns = [c['name'] for c in inspector.get_columns('members')]
                if 'current_reward_balance' not in columns:
                    print("Fixing Members table: Adding current_reward_balance")
                    conn.execute(text("ALTER TABLE members ADD COLUMN current_reward_balance INTEGER DEFAULT 0"))
                if 'total_lifetime_spend' not in columns:
                    print("Fixing Members table: Adding total_lifetime_spend")
                    conn.execute(text("ALTER TABLE members ADD COLUMN total_lifetime_spend INTEGER DEFAULT 0"))
            
            # 2. Receipts 테이블 컬럼 확인 및 복구
            if 'receipts' in existing_tables:
                columns = [c['name'] for c in inspector.get_columns('receipts')]
                if 'status' not in columns:
                    print("Fixing Receipts table: Adding status")
                    conn.execute(text("ALTER TABLE receipts ADD COLUMN status VARCHAR(20) DEFAULT 'PENDING'"))
                if 'amount_claimed' not in columns:
                    print("Fixing Receipts table: Adding amount_claimed")
                    conn.execute(text("ALTER TABLE receipts ADD COLUMN amount_claimed INTEGER"))
                if 'image_url' not in columns:
                    print("Fixing Receipts table: Adding image_url")
                    conn.execute(text("ALTER TABLE receipts ADD COLUMN image_url VARCHAR(255)"))
                    
            # 3. Coupons 테이블 컬럼 확인 및 복구
            if 'coupons' in existing_tables:
                columns = [c['name'] for c in inspector.get_columns('coupons')]
                if 'status' not in columns:
                    print("Fixing Coupons table: Adding status")
                    conn.execute(text("ALTER TABLE coupons ADD COLUMN status VARCHAR(20) DEFAULT 'AVAILABLE'"))
                if 'redeemed_by_staff_id' not in columns:
                    print("Fixing Coupons table: Adding redeemed_by_staff_id")
                    conn.execute(text("ALTER TABLE coupons ADD COLUMN redeemed_by_staff_id INTEGER"))
                if 'is_substitutable' not in columns:
                    print("Fixing Coupons table: Adding is_substitutable")
                    conn.execute(text("ALTER TABLE coupons ADD COLUMN is_substitutable BOOLEAN DEFAULT TRUE"))

            # 4. Staffs 테이블 생성 (create_all이 실패했을 경우 대비, 또는 테이블은 있는데 컬럼 문제 검사)
            # Staffs는 create_all에서 처리되므로 여기서는 생략하거나, 
            # 만약 테이블이 없으면 create_all이 처리해줄 것임.
            
            conn.commit()
            print("Schema check and fix completed.")
            
    except Exception as e:
        print(f"Schema check failed: {e}")
