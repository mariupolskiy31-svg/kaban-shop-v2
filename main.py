import os
import base64
import requests
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from database import db, init_db, User, Liquid, Pod, Disposable, Consumable

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-secret-key')

# Настройка БД (поддержка и Vercel Postgres, и локальной SQLite)
database_url = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///kaban.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

init_db(app)


# ===== ФУНКЦИЯ ЗАГРУЗКИ ФОТО НА IMGBB =====
def upload_to_imgbb(file):
    """Загрузка фото на ImgBB"""
    api_key = os.environ.get('IMGBB_API_KEY')
    if not api_key:
        print("Ошибка: Не найден IMGBB_API_KEY в переменных окружения")
        return None

    try:
        file_data = file.read()
        encoded = base64.b64encode(file_data).decode('utf-8')

        response = requests.post(
            'https://api.imgbb.com/1/upload',
            data={
                'key': api_key,
                'image': encoded
            },
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                return result['data']['url']
    except Exception as e:
        print(f"Ошибка загрузки на ImgBB: {e}")

    return None


# ===== ПУБЛИЧНЫЕ МАРШРУТЫ =====

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/catalog')
def api_catalog():
    liquids = Liquid.query.all()
    pods = Pod.query.all()
    disposables = Disposable.query.all()
    consumables = Consumable.query.all()

    pods_data = {}
    for pod in pods:
        if pod.device not in pods_data:
            pods_data[pod.device] = {
                'устройство': pod.device,
                'цвета': [],
                'общее_количество': 0,
                'цена': pod.price
            }
        pods_data[pod.device]['цвета'].append({
            'цвет': pod.color,
            'количество': pod.quantity
        })
        pods_data[pod.device]['общее_количество'] += pod.quantity

    data = {
        'liquids': [{
            'id': l.id,
            'бренд': l.brand,
            'никотин': l.nicotine,
            'вкус': l.flavor,
            'количество': l.quantity,
            'цена': l.price,
            'image_url': l.image_url
        } for l in liquids],
        'pods': list(pods_data.values()),
        'disposables': [{
            'id': d.id,
            'устройство': d.device,
            'тяги': d.puffs,
            'вкус': d.flavor,
            'количество': d.quantity,
            'цена': d.price,
            'image_url': d.image_url
        } for d in disposables],
        'consumables': [{
            'id': c.id,
            'бренд': c.brand,
            'на какие устройства': c.compatible_devices,
            'тип': c.type,
            'сопротивление': c.resistance,
            'количество': c.quantity,
            'цена': c.price,
            'image_url': c.image_url
        } for c in consumables]
    }

    return jsonify(data)


# ===== АДМИНКА =====

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        flash('Неверный логин или пароль', 'error')

    return render_template('admin/login.html')


@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/admin')
@login_required
def admin_dashboard():
    return render_template('admin/dashboard.html',
                           liquids=Liquid.query.all(),
                           pods=Pod.query.all(),
                           disposables=Disposable.query.all(),
                           consumables=Consumable.query.all())


# ===== ЖИДКОСТИ =====

@app.route('/admin/liquid/add', methods=['GET', 'POST'])
@login_required
def add_liquid():
    if request.method == 'POST':
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_url = upload_to_imgbb(file)
                if not image_url:
                    flash('Ошибка загрузки фото', 'error')

        liquid = Liquid(
            brand=request.form.get('brand'),
            nicotine=request.form.get('nicotine'),
            flavor=request.form.get('flavor'),
            quantity=int(request.form.get('quantity', 0)),
            price=int(request.form.get('price')),
            image_url=image_url
        )
        db.session.add(liquid)
        db.session.commit()
        flash('Жидкость добавлена', 'success')
        return redirect(url_for('admin_dashboard'))

    existing_brands = [r[0] for r in db.session.query(Liquid.brand).distinct().all() if r[0]]
    return render_template('admin/liquid_form.html', liquid=None, existing_brands=existing_brands)


@app.route('/admin/liquid/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_liquid(id):
    liquid = Liquid.query.get_or_404(id)

    if request.method == 'POST':
        liquid.brand = request.form.get('brand')
        liquid.nicotine = request.form.get('nicotine')
        liquid.flavor = request.form.get('flavor')
        liquid.quantity = int(request.form.get('quantity', 0))
        liquid.price = int(request.form.get('price'))

        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_url = upload_to_imgbb(file)
                if image_url:
                    liquid.image_url = image_url
                else:
                    flash('Ошибка загрузки фото', 'error')

        db.session.commit()
        flash('Жидкость обновлена', 'success')
        return redirect(url_for('admin_dashboard'))

    existing_brands = [r[0] for r in db.session.query(Liquid.brand).distinct().all() if r[0]]
    return render_template('admin/liquid_form.html', liquid=liquid, existing_brands=existing_brands)


@app.route('/admin/liquid/delete/<int:id>')
@login_required
def delete_liquid(id):
    liquid = Liquid.query.get_or_404(id)
    db.session.delete(liquid)
    db.session.commit()
    flash('Жидкость удалена', 'success')
    return redirect(url_for('admin_dashboard'))


# ===== POD СИСТЕМЫ =====

@app.route('/admin/pod/add', methods=['GET', 'POST'])
@login_required
def add_pod():
    if request.method == 'POST':
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_url = upload_to_imgbb(file)
                if not image_url:
                    flash('Ошибка загрузки фото', 'error')

        pod = Pod(
            device=request.form.get('device'),
            color=request.form.get('color'),
            quantity=int(request.form.get('quantity', 0)),
            price=int(request.form.get('price')),
            image_url=image_url
        )
        db.session.add(pod)
        db.session.commit()
        flash('POD добавлен', 'success')
        return redirect(url_for('admin_dashboard'))

    existing_devices = [r[0] for r in db.session.query(Pod.device).distinct().all() if r[0]]
    return render_template('admin/pod_form.html', pod=None, existing_devices=existing_devices)


@app.route('/admin/pod/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_pod(id):
    pod = Pod.query.get_or_404(id)

    if request.method == 'POST':
        pod.device = request.form.get('device')
        pod.color = request.form.get('color')
        pod.quantity = int(request.form.get('quantity', 0))
        pod.price = int(request.form.get('price'))

        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_url = upload_to_imgbb(file)
                if image_url:
                    pod.image_url = image_url
                else:
                    flash('Ошибка загрузки фото', 'error')

        db.session.commit()
        flash('POD обновлён', 'success')
        return redirect(url_for('admin_dashboard'))

    existing_devices = [r[0] for r in db.session.query(Pod.device).distinct().all() if r[0]]
    return render_template('admin/pod_form.html', pod=pod, existing_devices=existing_devices)


@app.route('/admin/pod/delete/<int:id>')
@login_required
def delete_pod(id):
    pod = Pod.query.get_or_404(id)
    db.session.delete(pod)
    db.session.commit()
    flash('POD удалён', 'success')
    return redirect(url_for('admin_dashboard'))


# ===== ОДНОРАЗКИ =====

@app.route('/admin/disposable/add', methods=['GET', 'POST'])
@login_required
def add_disposable():
    if request.method == 'POST':
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_url = upload_to_imgbb(file)
                if not image_url:
                    flash('Ошибка загрузки фото', 'error')

        disposable = Disposable(
            device=request.form.get('device'),
            puffs=request.form.get('puffs'),
            flavor=request.form.get('flavor'),
            quantity=int(request.form.get('quantity', 0)),
            price=int(request.form.get('price')),
            image_url=image_url
        )
        db.session.add(disposable)
        db.session.commit()
        flash('Одноразка добавлена', 'success')
        return redirect(url_for('admin_dashboard'))

    existing_devices = [r[0] for r in db.session.query(Disposable.device).distinct().all() if r[0]]
    return render_template('admin/disposable_form.html', disposable=None, existing_devices=existing_devices)


@app.route('/admin/disposable/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_disposable(id):
    disposable = Disposable.query.get_or_404(id)

    if request.method == 'POST':
        disposable.device = request.form.get('device')
        disposable.puffs = request.form.get('puffs')
        disposable.flavor = request.form.get('flavor')
        disposable.quantity = int(request.form.get('quantity', 0))
        disposable.price = int(request.form.get('price'))

        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_url = upload_to_imgbb(file)
                if image_url:
                    disposable.image_url = image_url
                else:
                    flash('Ошибка загрузки фото', 'error')

        db.session.commit()
        flash('Одноразка обновлена', 'success')
        return redirect(url_for('admin_dashboard'))

    existing_devices = [r[0] for r in db.session.query(Disposable.device).distinct().all() if r[0]]
    return render_template('admin/disposable_form.html', disposable=disposable, existing_devices=existing_devices)


@app.route('/admin/disposable/delete/<int:id>')
@login_required
def delete_disposable(id):
    disposable = Disposable.query.get_or_404(id)
    db.session.delete(disposable)
    db.session.commit()
    flash('Одноразка удалена', 'success')
    return redirect(url_for('admin_dashboard'))


# ===== РАСХОДНИКИ =====

@app.route('/admin/consumable/add', methods=['GET', 'POST'])
@login_required
def add_consumable():
    if request.method == 'POST':
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_url = upload_to_imgbb(file)
                if not image_url:
                    flash('Ошибка загрузки фото', 'error')

        consumable = Consumable(
            brand=request.form.get('brand'),
            compatible_devices=request.form.get('compatible_devices'),
            type=request.form.get('type'),
            resistance=request.form.get('resistance'),
            quantity=int(request.form.get('quantity', 0)),
            price=int(request.form.get('price')),
            image_url=image_url
        )
        db.session.add(consumable)
        db.session.commit()
        flash('Расходник добавлен', 'success')
        return redirect(url_for('admin_dashboard'))

    existing_brands = [r[0] for r in db.session.query(Consumable.brand).distinct().all() if r[0]]
    return render_template('admin/consumable_form.html', consumable=None, existing_brands=existing_brands)


@app.route('/admin/consumable/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_consumable(id):
    consumable = Consumable.query.get_or_404(id)

    if request.method == 'POST':
        consumable.brand = request.form.get('brand')
        consumable.compatible_devices = request.form.get('compatible_devices')
        consumable.type = request.form.get('type')
        consumable.resistance = request.form.get('resistance')
        consumable.quantity = int(request.form.get('quantity', 0))
        consumable.price = int(request.form.get('price'))

        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_url = upload_to_imgbb(file)
                if image_url:
                    consumable.image_url = image_url
                else:
                    flash('Ошибка загрузки фото', 'error')

        db.session.commit()
        flash('Расходник обновлён', 'success')
        return redirect(url_for('admin_dashboard'))

    existing_brands = [r[0] for r in db.session.query(Consumable.brand).distinct().all() if r[0]]
    return render_template('admin/consumable_form.html', consumable=consumable, existing_brands=existing_brands)


@app.route('/admin/consumable/delete/<int:id>')
@login_required
def delete_consumable(id):
    consumable = Consumable.query.get_or_404(id)
    db.session.delete(consumable)
    db.session.commit()
    flash('Расходник удалён', 'success')
    return redirect(url_for('admin_dashboard'))


if __name__ == "__main__":
    app.run(debug=True)