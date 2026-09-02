import os
from flask import Flask
from database import db, init_db, User
import requests

app = Flask(__name__)

# Настройка БД (точно так же, как в main.py)
database_url = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    if 'sslmode' not in database_url:
        if '?' in database_url:
            database_url += '&sslmode=require'
        else:
            database_url += '?sslmode=require'
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///kaban.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()

    # Проверяем, есть ли админ
    admin = User.query.filter_by(username='admin').first()

    if admin:
        print(f"️ Админ уже существует! ID: {admin.id}")
        # Обновляем пароль
        admin.set_password('admin123')
        db.session.commit()
        print("✅ Пароль админа обновлён на 'admin123'")
    else:
        # Создаём нового админа
        admin = User(username='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("✅ Админ создан: login=admin, password=admin123")

    # Выводим всех пользователей
    users = User.query.all()
    print(f"\n📋 Всего пользователей в базе: {len(users)}")
    for user in users:
        print(f"  - ID: {user.id}, Логин: {user.username}")