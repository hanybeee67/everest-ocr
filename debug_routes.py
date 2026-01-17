
import os
os.environ['FERNET_KEY'] = 'bho7aodqh1g7xKCf2yLxmAOKLivmY7ZYXqSlZWyGdsE='
os.environ['FLASK_SECRET_KEY'] = 'test_secret'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app

try:
    app = create_app()
    print("Map:")
    print(app.url_map)
except Exception as e:
    print(e)
