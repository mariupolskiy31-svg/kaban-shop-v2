from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class LiquidBrand(db.Model):
    """Бренд жидкости (группа)"""
    id = db.Column(db.Integer, primary_key=True)
    brand = db.Column(db.String(100), nullable=False)
    nicotine = db.Column(db.String(20))
    price = db.Column(db.Integer, nullable=False)
    image_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    flavors = db.relationship('LiquidFlavor', backref='brand_group', lazy=True, cascade='all, delete-orphan')


class LiquidFlavor(db.Model):
    """Вкус жидкости"""
    id = db.Column(db.Integer, primary_key=True)
    brand_group_id = db.Column(db.Integer, db.ForeignKey('liquid_brand.id'), nullable=False)
    flavor = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PodDevice(db.Model):
    """Устройство POD (группа)"""
    id = db.Column(db.Integer, primary_key=True)
    device = db.Column(db.String(100), nullable=False)
    image_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    colors = db.relationship('PodColor', backref='pod_device', lazy=True, cascade='all, delete-orphan')


class PodColor(db.Model):
    """Цвет POD"""
    id = db.Column(db.Integer, primary_key=True)
    pod_device_id = db.Column(db.Integer, db.ForeignKey('pod_device.id'), nullable=False)
    color = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    price = db.Column(db.Integer, nullable=False)
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

    with app.app_context():
        db.create_all()
        print("✅ База данных инициализирована")