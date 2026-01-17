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
    
    # Blueprint 등록
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    
    # DB 테이블 생성 (앱 컨텍스트 내에서 실행)
    with app.app_context():
        db.create_all()

    return app

# Gunicorn 구동을 위해 전역 변수로 app 객체 생성
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)