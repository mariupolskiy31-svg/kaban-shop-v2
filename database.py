from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy import text

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'admin_login'


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)  # УВЕЛИЧЕНО ДО 256

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Liquid(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    brand = db.Column(db.String(100), nullable=False)
    nicotine = db.Column(db.String(20))
    flavor = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    price = db.Column(db.Integer, nullable=False)
    image_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Pod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    price = db.Column(db.Integer, nullable=False)
    image_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Disposable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device = db.Column(db.String(100), nullable=False)
    puffs = db.Column(db.String(20))
    flavor = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    price = db.Column(db.Integer, nullable=False)
    image_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Consumable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    brand = db.Column(db.String(100), nullable=False)
    compatible_devices = db.Column(db.String(200))
    type = db.Column(db.String(50))
    resistance = db.Column(db.String(20))
    quantity = db.Column(db.Integer, default=0)
    price = db.Column(db.Integer, nullable=False)
    image_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def init_db(app):
    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    with app.app_context():
        # 1. Создаём таблицы (если их нет)
        db.create_all()

        # 2. ИСПРАВЛЕНИЕ: Принудительно меняем размер колонки в СУЩЕСТВУЮЩЕЙ базе данных
        try:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "user" ALTER COLUMN password_hash TYPE VARCHAR(256)'))
                conn.commit()
        except Exception:
            pass  # Игнорируем ошибку, если колонка уже имеет правильный размер

        # 3. Создаём или обновляем админа
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✅ Админ создан: login=admin, password=admin123")
        else:
            # Если админ есть, но пароль был сохранён с ошибкой (обрезан), обновляем его
            admin.set_password('admin123')
            db.session.commit()
            print("✅ Пароль админа обновлён")