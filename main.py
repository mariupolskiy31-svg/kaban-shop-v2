import os
import base64
import requests
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from database import db, init_db, LiquidBrand, LiquidFlavor, PodDevice, PodColor, Disposable, Consumable

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-secret-key')

# ===== НАСТРОЙКА БД =====
database_url = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+psycopg2://', 1)
    elif database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg2://', 1)

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


# ===== ЗАГРУЗКА ФОТО НА IMGBB =====
def upload_to_imgbb(file):
    api_key = os.environ.get('IMGBB_API_KEY')
    if not api_key:
        print("Ошибка: Не найден IMGBB_API_KEY")
        return None

    try:
        file_data = file.read()
        encoded = base64.b64encode(file_data).decode('utf-8')

        response = requests.post(
            'https://api.imgbb.com/1/upload',
            data={'key': api_key, 'image': encoded},
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
    # Жидкости
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

    # POD системы - группируем по устройствам
    pod_devices = PodDevice.query.all()
    pods_data = {}
    for pd in pod_devices:
        device_name = pd.device
        if device_name not in pods_data:
            pods_data[device_name] = {
                'устройство': device_name,
                'цвета': [],
                'общее_количество': 0,
                'цена': 0,
                'image_url': pd.image_url  # ← ДОБАВЛЕНО
            }
        for color in pd.colors:
            pods_data[device_name]['цвета'].append({
                'цвет': color.color,
                'количество': color.quantity
            })
            pods_data[device_name]['общее_количество'] += color.quantity
            if color.price > 0:
                pods_data[device_name]['цена'] = color.price

    # Одноразки и расходники
    disposables = Disposable.query.all()
    consumables = Consumable.query.all()

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


# ===== АДМИНКА =====

@app.route('/admin')
def admin_dashboard():
    search = request.args.get('search', '')
    filter_type = request.args.get('filter_type', 'all')
    brand_filter = request.args.get('brand_filter', '')  # ← НОВОЕ: фильтр по бренду

    # Жидкости
    liquid_query = LiquidBrand.query
    if search:
        liquid_query = liquid_query.filter(
            (LiquidBrand.brand.ilike(f'%{search}%')) |
            (LiquidBrand.nicotine.ilike(f'%{search}%'))
        )
    if brand_filter:
        liquid_query = liquid_query.filter(LiquidBrand.brand == brand_filter)
    liquid_brands = liquid_query.all()

    # Получаем список всех брендов для фильтра
    all_brands = [b.brand for b in LiquidBrand.query.distinct(LiquidBrand.brand).all()]

    # POD устройства
    if search and filter_type in ['all', 'pods']:
        pod_devices = PodDevice.query.filter(PodDevice.device.ilike(f'%{search}%')).all()
    elif filter_type == 'pods':
        pod_devices = PodDevice.query.all()
    else:
        pod_devices = [] if filter_type != 'all' else PodDevice.query.all()

    # Одноразки
    if search and filter_type in ['all', 'disposables']:
        disposables = Disposable.query.filter(
            (Disposable.device.ilike(f'%{search}%')) |
            (Disposable.flavor.ilike(f'%{search}%'))
        ).all()
    elif filter_type == 'disposables':
        disposables = Disposable.query.all()
    else:
        disposables = [] if filter_type != 'all' else Disposable.query.all()

    # Расходники
    if search and filter_type in ['all', 'consumables']:
        consumables = Consumable.query.filter(
            (Consumable.brand.ilike(f'%{search}%')) |
            (Consumable.compatible_devices.ilike(f'%{search}%'))
        ).all()
    elif filter_type == 'consumables':
        consumables = Consumable.query.all()
    else:
        consumables = [] if filter_type != 'all' else Consumable.query.all()

    # Подсчёт стоимости для каждого раздела
    liquids_total = sum(lb.price * sum(f.quantity for f in lb.flavors) for lb in liquid_brands)
    pods_total = sum(sum(c.price * c.quantity for c in pd.colors) for pd in pod_devices)
    disposables_total = sum(d.price * d.quantity for d in disposables)
    consumables_total = sum(c.price * c.quantity for c in consumables)

    return render_template('admin/dashboard.html',
                           liquid_brands=liquid_brands,
                           pod_devices=pod_devices,
                           disposables=disposables,
                           consumables=consumables,
                           all_brands=all_brands,
                           search=search,
                           filter_type=filter_type,
                           brand_filter=brand_filter,
                           liquids_total=liquids_total,
                           pods_total=pods_total,
                           disposables_total=disposables_total,
                           consumables_total=consumables_total)


# ===== ЖИДКОСТИ: БРЕНД =====

@app.route('/admin/liquid-brand/add', methods=['GET', 'POST'])
def add_liquid_brand():
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
        flash('Бренд создан! Теперь добавь к нему вкусы.', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/liquid_brand_form.html', brand=None)


@app.route('/admin/liquid-brand/edit/<int:id>', methods=['GET', 'POST'])
def edit_liquid_brand(id):
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


@app.route('/admin/liquid-brand/delete/<int:id>')
def delete_liquid_brand(id):
    brand = LiquidBrand.query.get_or_404(id)
    db.session.delete(brand)
    db.session.commit()
    flash('Бренд и все вкусы удалены', 'success')
    return redirect(url_for('admin_dashboard'))


# ===== ЖИДКОСТИ: ВКУСЫ =====

@app.route('/admin/liquid-flavor/add/<int:brand_id>', methods=['GET', 'POST'])
def add_liquid_flavor(brand_id):
    brand = LiquidBrand.query.get_or_404(brand_id)

    if request.method == 'POST':
        flavor_name = request.form.get('flavor', '').strip()
        quantity = int(request.form.get('quantity', 0))

        if flavor_name:
            flavor = LiquidFlavor(
                brand_group_id=brand.id,
                flavor=flavor_name,
                quantity=quantity
            )
            db.session.add(flavor)
            db.session.commit()
            flash(f'Вкус "{flavor_name}" добавлен!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Введите название вкуса', 'error')

    return render_template('admin/liquid_flavor_form.html', brand=brand)


@app.route('/admin/liquid-flavor/edit/<int:id>', methods=['GET', 'POST'])
def edit_liquid_flavor(id):
    flavor = LiquidFlavor.query.get_or_404(id)
    brand = flavor.brand_group

    if request.method == 'POST':
        flavor.flavor = request.form.get('flavor', '').strip()
        flavor.quantity = int(request.form.get('quantity', 0))
        db.session.commit()
        flash('Вкус обновлён', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/liquid_flavor_edit_form.html', flavor=flavor, brand=brand)


@app.route('/admin/liquid-flavor/delete/<int:id>')
def delete_liquid_flavor(id):
    flavor = LiquidFlavor.query.get_or_404(id)
    db.session.delete(flavor)
    db.session.commit()
    flash('Вкус удалён', 'success')
    return redirect(url_for('admin_dashboard'))


# ===== POD: УСТРОЙСТВО =====

@app.route('/admin/pod-device/add', methods=['GET', 'POST'])
def add_pod_device():
    if request.method == 'POST':
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_url = upload_to_imgbb(file)
                if not image_url:
                    flash('Ошибка загрузки фото', 'error')

        device = PodDevice(
            device=request.form.get('device'),
            image_url=image_url
        )
        db.session.add(device)
        db.session.commit()
        flash('Устройство создано! Теперь добавь к нему цвета.', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/pod_device_form.html', device=None)


@app.route('/admin/pod-device/edit/<int:id>', methods=['GET', 'POST'])
def edit_pod_device(id):
    device = PodDevice.query.get_or_404(id)

    if request.method == 'POST':
        device.device = request.form.get('device')

        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_url = upload_to_imgbb(file)
                if image_url:
                    device.image_url = image_url

        db.session.commit()
        flash('Устройство обновлено', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/pod_device_form.html', device=device)


@app.route('/admin/pod-device/delete/<int:id>')
def delete_pod_device(id):
    device = PodDevice.query.get_or_404(id)
    db.session.delete(device)
    db.session.commit()
    flash('Устройство и все цвета удалены', 'success')
    return redirect(url_for('admin_dashboard'))


# ===== POD: ЦВЕТА =====

@app.route('/admin/pod-color/add/<int:device_id>', methods=['GET', 'POST'])
def add_pod_color(device_id):
    device = PodDevice.query.get_or_404(device_id)

    if request.method == 'POST':
        color_name = request.form.get('color', '').strip()
        quantity = int(request.form.get('quantity', 0))
        price = int(request.form.get('price', 0))

        if color_name:
            color = PodColor(
                pod_device_id=device.id,
                color=color_name,
                quantity=quantity,
                price=price
            )
            db.session.add(color)
            db.session.commit()
            flash(f'Цвет "{color_name}" добавлен!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Введите название цвета', 'error')

    return render_template('admin/pod_color_form.html', device=device)


@app.route('/admin/pod-color/edit/<int:id>', methods=['GET', 'POST'])
def edit_pod_color(id):
    color = PodColor.query.get_or_404(id)
    device = color.pod_device

    if request.method == 'POST':
        color.color = request.form.get('color', '').strip()
        color.quantity = int(request.form.get('quantity', 0))
        color.price = int(request.form.get('price', 0))
        db.session.commit()
        flash('Цвет обновлён', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/pod_color_edit_form.html', color=color, device=device)


@app.route('/admin/pod-color/delete/<int:id>')
def delete_pod_color(id):
    color = PodColor.query.get_or_404(id)
    db.session.delete(color)
    db.session.commit()
    flash('Цвет удалён', 'success')
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