import os
from flask import Flask
from flask_migrate import Migrate
from config import Config
from models import db
from routes.public import public_bp
from routes.admin import admin_bp

def create_app():
    # 경로 설정
    APP_ROOT = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__, instance_path=os.path.join(APP_ROOT, 'instance'))
    
    # Instance 폴더 생성
    os.makedirs(app.instance_path, exist_ok=True)

    # 설정 로드
    app.config.from_object(Config)
    
    # DB 초기화
    db.init_app(app)
    
    # Migration 초기화
    migrate = Migrate(app, db)
    
    # Rate Limiter 초기화
    from extensions import limiter
    limiter.init_app(app)
    
    # Blueprint 등록
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    
    from routes.reward import reward_bp
    app.register_blueprint(reward_bp)
    
    from routes.staff import staff_bp
    app.register_blueprint(staff_bp)
    
    # DB 테이블 생성 (앱 컨텍스트 내에서 실행)
    with app.app_context():
        # [보안/운영] 자동 마이그레이션 실행
        # Render 등 배포 환경에서 DB 스키마를 최신 상태로 유지하기 위함
        from flask_migrate import upgrade
        try:
            upgrade()
            print("DB Upgrade (Migration) success!")
        except Exception as e:
            print(f"DB Upgrade failed: {e}")
            # 마이그레이션 실패 시에도 create_all 시도 (혹시 초기 상태일 경우)
            
        # [Self-Healing] 직접 스키마 검사 및 복구 수행
        try:
            from services.db_fixer import check_and_fix_schema
            check_and_fix_schema()
        except Exception as e:
            print(f"DB Self-Healing failed: {e}")

        db.create_all()

    return app

# Gunicorn 구동을 위해 전역 변수로 app 객체 생성
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)