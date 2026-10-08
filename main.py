import os
import base64
import requests
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from database import db, init_db, LiquidBrand, LiquidFlavor, Pod, Disposable, Consumable

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-secret-key')

# Настройка БД
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

init_db(app)


# ===== ФУНКЦИЯ ЗАГРУЗКИ ФОТО НА IMGBB =====
def upload_to_imgbb(file):
    """Загрузка фото на ImgBB"""
    api_key = os.environ.get('IMGBB_API_KEY')
    if not api_key:
        print("Ошибка: Не найден IMGBB_API_KEY")
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
    # Получаем все жидкости с группировкой
    liquid_brands = LiquidBrand.query.all()
    liquids = []
    for lb in liquid_brands:
        for flavor in lb.flavors:
            liquids.append({
                'id': flavor.id,
                'бренд': lb.brand,
                'никотин': lb.nicotine,
                'вкус': flavor.flavor,
                'количество': flavor.quantity,
                'цена': lb.price,
                'image_url': lb.image_url
            })

    pods = Pod.query.all()
    disposables = Disposable.query.all()
    consumables = Consumable.query.all()

    # Группируем PODы
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
        'liquids': liquids,
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


# ===== АДМИНКА (БЕЗ АУТЕНТИФИКАЦИИ) =====

@app.route('/admin')
def admin_dashboard():
    # Получаем параметры поиска и фильтрации
    search = request.args.get('search', '')
    filter_type = request.args.get('filter_type', 'all')

    # Жидкости
    liquid_brands = LiquidBrand.query.all()
    if search:
        liquid_brands = LiquidBrand.query.filter(
            (LiquidBrand.brand.ilike(f'%{search}%')) |
            (LiquidBrand.nicotine.ilike(f'%{search}%'))
        ).all()

    # PODs
    pods = Pod.query.all()
    if search and filter_type in ['all', 'pods']:
        pods = Pod.query.filter(
            (Pod.device.ilike(f'%{search}%')) |
            (Pod.color.ilike(f'%{search}%'))
        ).all()

    # Одноразки
    disposables = Disposable.query.all()
    if search and filter_type in ['all', 'disposables']:
        disposables = Disposable.query.filter(
            (Disposable.device.ilike(f'%{search}%')) |
            (Disposable.flavor.ilike(f'%{search}%'))
        ).all()

    # Расходники
    consumables = Consumable.query.all()
    if search and filter_type in ['all', 'consumables']:
        consumables = Consumable.query.filter(
            (Consumable.brand.ilike(f'%{search}%')) |
            (Consumable.compatible_devices.ilike(f'%{search}%'))
        ).all()

    return render_template('admin/dashboard.html',
                           liquid_brands=liquid_brands,
                           pods=pods,
                           disposables=disposables,
                           consumables=consumables,
                           search=search,
                           filter_type=filter_type)


# ===== ЖИДКОСТИ (НОВАЯ СТРУКТУРА) =====

@app.route('/admin/liquid-brand/add', methods=['GET', 'POST'])
def add_liquid_brand():
    """Добавить бренд жидкости (группу)"""
    if request.method == 'POST':
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_url = upload_to_imgbb(file)
                if not image_url:
                    flash('Ошибка загрузки фото', 'error')

        brand = LiquidBrand(
            brand=request.form.get('brand'),
            nicotine=request.form.get('nicotine'),
            price=int(request.form.get('price')),
            image_url=image_url
        )
        db.session.add(brand)
        db.session.commit()

        # Добавляем первый вкус
        flavors_text = request.form.get('flavors', '')
        for flavor_name in flavors_text.split('\n'):
            flavor_name = flavor_name.strip()
            if flavor_name:
                flavor = LiquidFlavor(
                    brand_group_id=brand.id,
                    flavor=flavor_name,
                    quantity=int(request.form.get('quantity', 0))
                )
                db.session.add(flavor)
        db.session.commit()

        flash('Бренд и вкусы добавлены', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/liquid_brand_form.html', brand=None)


@app.route('/admin/liquid-brand/edit/<int:id>', methods=['GET', 'POST'])
def edit_liquid_brand(id):
    """Редактировать бренд жидкости"""
    brand = LiquidBrand.query.get_or_404(id)

    if request.method == 'POST':
        brand.brand = request.form.get('brand')
        brand.nicotine = request.form.get('nicotine')
        brand.price = int(request.form.get('price'))

        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_url = upload_to_imgbb(file)
                if image_url:
                    brand.image_url = image_url

        db.session.commit()
        flash('Бренд обновлён', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/liquid_brand_form.html', brand=brand)


@app.route('/admin/liquid-flavor/add/<int:brand_id>', methods=['GET', 'POST'])
def add_liquid_flavor(brand_id):
    """Добавить вкус к существующему бренду"""
    brand = LiquidBrand.query.get_or_404(brand_id)

    if request.method == 'POST':
        flavors_text = request.form.get('flavors', '')
        quantity = int(request.form.get('quantity', 0))

        for flavor_name in flavors_text.split('\n'):
            flavor_name = flavor_name.strip()
            if flavor_name:
                flavor = LiquidFlavor(
                    brand_group_id=brand.id,
                    flavor=flavor_name,
                    quantity=quantity
                )
                db.session.add(flavor)

        db.session.commit()
        flash('Вкусы добавлены', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/liquid_flavor_form.html', brand=brand)


@app.route('/admin/liquid-flavor/delete/<int:id>')
def delete_liquid_flavor(id):
    """Удалить вкус"""
    flavor = LiquidFlavor.query.get_or_404(id)
    brand_id = flavor.brand_group_id
    db.session.delete(flavor)
    db.session.commit()
    flash('Вкус удалён', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/liquid-brand/delete/<int:id>')
def delete_liquid_brand(id):
    """Удалить бренд и все его вкусы"""
    brand = LiquidBrand.query.get_or_404(id)
    db.session.delete(brand)
    db.session.commit()
    flash('Бренд и все вкусы удалены', 'success')
    return redirect(url_for('admin_dashboard'))


# ===== POD СИСТЕМЫ =====

@app.route('/admin/pod/add', methods=['GET', 'POST'])
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

    return render_template('admin/pod_form.html', pod=None)


@app.route('/admin/pod/edit/<int:id>', methods=['GET', 'POST'])
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

        db.session.commit()
        flash('POD обновлён', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/pod_form.html', pod=pod)


@app.route('/admin/pod/delete/<int:id>')
def delete_pod(id):
    pod = Pod.query.get_or_404(id)
    db.session.delete(pod)
    db.session.commit()
    flash('POD удалён', 'success')
    return redirect(url_for('admin_dashboard'))


# ===== ОДНОРАЗКИ =====

@app.route('/admin/disposable/add', methods=['GET', 'POST'])
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

    return render_template('admin/disposable_form.html', disposable=None)


@app.route('/admin/disposable/edit/<int:id>', methods=['GET', 'POST'])
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

        db.session.commit()
        flash('Одноразка обновлена', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/disposable_form.html', disposable=disposable)


@app.route('/admin/disposable/delete/<int:id>')
def delete_disposable(id):
    disposable = Disposable.query.get_or_404(id)
    db.session.delete(disposable)
    db.session.commit()
    flash('Одноразка удалена', 'success')
    return redirect(url_for('admin_dashboard'))


# ===== РАСХОДНИКИ =====

@app.route('/admin/consumable/add', methods=['GET', 'POST'])
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

    return render_template('admin/consumable_form.html', consumable=None)


@app.route('/admin/consumable/edit/<int:id>', methods=['GET', 'POST'])
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

        db.session.commit()
        flash('Расходник обновлён', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/consumable_form.html', consumable=consumable)


@app.route('/admin/consumable/delete/<int:id>')
def delete_consumable(id):
    consumable = Consumable.query.get_or_404(id)
    db.session.delete(consumable)
    db.session.commit()
    flash('Расходник удалён', 'success')
    return redirect(url_for('admin_dashboard'))


if __name__ == "__main__":
    app.run(debug=True)