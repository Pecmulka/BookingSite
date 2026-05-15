import uuid, io, base64
from datetime import datetime, date, timedelta, time
from django.db.models import Q
from django.db.models import Count, Sum
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from .models import Table, User, Role, Reservation, ReservationStatus
import matplotlib.pyplot as plt


# Настройки заведения
OPEN_TIME    = time(10, 0)
CLOSE_TIME   = time(23, 0)
SLOT_MINUTES = 60


def is_admin(request):
    return request.session.get('user_role') == 'Администратор'

def get_time_slots():
    """Возвращает список временных слотов начала брони в течение дня."""
    slots = []
    current = datetime.combine(date.today(), OPEN_TIME)
    end     = datetime.combine(date.today(), CLOSE_TIME)
    while current < end:
        slots.append(current.time())
        current += timedelta(minutes=SLOT_MINUTES)
    return slots


def get_busy_slots(table_id, selected_date):
    """Возвращает множество занятых start_time для стола и даты (кроме отменённых)."""
    return set(
        Reservation.objects
        .filter(table_id=table_id, date=selected_date)
        .exclude(status__name='Отменена')
        .values_list('start_time', flat=True)
    )


# ГЛАВНАЯ

def index(request):
    capacity = request.GET.get('capacity', '')
    tables = Table.objects.filter(delete_date__isnull=True)
    if capacity.isdigit():
        tables = tables.filter(capacity__gte=int(capacity))
    all_capacities = Table.objects.values_list('capacity', flat=True).order_by('capacity').distinct()

    context = {
        'tables': tables,
        'all_capacities': all_capacities,
        'selected': capacity,
    }
    # Если запрос от HTMX — возвращаем только фрагмент таблицы
    if request.headers.get('HX-Request'):
        return render(request, 'index_table_fragment.html', context)
    return render(request, 'index.html', context)


# АВТОРИЗАЦИЯ

def login_view(request):
    if request.session.get('user_id'):
        return redirect('index')
    error = ''
    if request.method == 'POST':
        login = request.POST.get('login', '').strip()
        password = request.POST.get('password', '').strip()
        try:
            user = User.objects.get(login=login, password=password)
            if not user.is_active:
                error = 'Ваш аккаунт деактивирован.'
            else:
                request.session['user_id'] = user.id
                request.session['user_fio'] = user.fio
                request.session['user_role'] = user.role.name
                return redirect('index')
        except User.DoesNotExist:
            error = 'Неверный логин или пароль.'
    return render(request, 'login.html', {'error': error})


def logout_view(request):
    request.session.flush()
    return redirect('index')

# РЕГИСТРАЦИЯ И ЛИЧНЫЙ КАБИНЕТ ГОСТЯ

def register_view(request):
    if request.session.get('user_id'):
        return redirect('profile')
    error = ''
    if request.method == 'POST':
        fio = request.POST.get('fio', '').strip()
        login = request.POST.get('login', '').strip()
        password  = request.POST.get('password', '').strip()
        password2 = request.POST.get('password2', '').strip()
        if not all([fio, login, password, password2]):
            error = 'Заполните все поля.'
        elif password != password2:
            error = 'Пароли не совпадают.'
        elif User.objects.filter(login=login).exists():
            error = 'Пользователь с таким логином уже существует.'
        else:
            role, _ = Role.objects.get_or_create(name='Гость')
            user = User.objects.create(fio=fio, login=login, password=password, role=role)
            request.session['user_id'] = user.id
            request.session['user_fio'] = user.fio
            request.session['user_role'] = user.role.name
            return redirect('profile')
    return render(request, 'register.html', {'error': error})


def profile_view(request):
    if not request.session.get('user_id'):
        return redirect('login')
    reservations = (
        Reservation.objects
        .filter(user_id=request.session['user_id'])
        .select_related('table', 'status')
        .order_by('-date', '-start_time')
    )
    return render(request, 'profile.html', {'reservations': reservations})


def profile_detail(request, code):
    if not request.session.get('user_id'):
        return redirect('login')
    reservation = get_object_or_404(
        Reservation,
        confirmation_code=code,
        user_id=request.session['user_id'],
    )
    return render(request, 'profile_detail.html', {'reservation': reservation})


# БРОНИРОВАНИЕ ДЛЯ ГОСТЕЙ

def book_table(request, pk):
    table = get_object_or_404(Table, pk=pk)

    # Дата: из POST (скрытое поле) или GET, иначе сегодня
    date_str = request.POST.get('date', '') or request.GET.get('date', '')
    try:
        selected_date = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
    except (ValueError, AttributeError):
        selected_date = date.today()

    # Нельзя бронировать прошедшие даты
    if selected_date < date.today():
        selected_date = date.today()

    date_str = selected_date.strftime('%Y-%m-%d')
    all_slots = get_time_slots()
    busy_slots = get_busy_slots(table.pk, selected_date)

    # Собираем слоты с признаком занятости
    slots = []
    for slot in all_slots:
        end_slot = (datetime.combine(date.today(), slot) + timedelta(minutes=SLOT_MINUTES)).time()
        slots.append({
            'start': slot,
            'end': end_slot,
            'label': f'{slot.strftime("%H:%M")} — {end_slot.strftime("%H:%M")}',
            'busy': slot in busy_slots,
        })

    error = ''

    if request.method == 'POST':
        start_str = request.POST.get('start_time', '')
        guest_name = request.POST.get('guest_name', '').strip()
        guest_phone = request.POST.get('guest_phone', '').strip()
        guest_email = request.POST.get('guest_email', '').strip()
        guests_count = request.POST.get('guests_count', '').strip()
        comment = request.POST.get('comment', '').strip()

        if not all([start_str, guest_name, guest_phone, guests_count]):
            error = 'Заполните все обязательные поля.'
        else:
            try:
                start_time = datetime.strptime(start_str, '%H:%M').time()
                end_time = (datetime.combine(date.today(), start_time) + timedelta(minutes=SLOT_MINUTES)).time()

                if start_time in busy_slots:
                    error = 'Выбранное время уже занято. Пожалуйста, выберите другой слот.'
                elif int(guests_count) > table.capacity:
                    error = f'Количество гостей превышает вместимость столика ({table.capacity} мест).'
                else:
                    status, _ = ReservationStatus.objects.get_or_create(name='Ожидает подтверждения')
                    confirmation_code = uuid.uuid4().hex[:8].upper()

                    # Привязываем к пользователю если авторизован
                    user = None
                    user_id = request.session.get('user_id')
                    if user_id:
                        try:
                            user = User.objects.get(pk=user_id)
                        except User.DoesNotExist:
                            pass

                    Reservation.objects.create(
                        table=table,
                        status=status,
                        user=user,
                        guest_name=guest_name,
                        guest_phone=guest_phone,
                        guest_email=guest_email,
                        date=selected_date,
                        start_time=start_time,
                        end_time=end_time,
                        guests_count=int(guests_count),
                        comment=comment,
                        confirmation_code=confirmation_code,
                    )
                    return redirect('book_success', code=confirmation_code)

            except Exception as e:
                error = f'Ошибка при сохранении: {e}'

    return render(request, 'book_table.html', {
        'table': table,
        'slots': slots,
        'selected_date': date_str,
        'today': date.today().strftime('%Y-%m-%d'),
        'error': error,
        'post': request.POST,
    })


def book_success(request, code):
    reservation = get_object_or_404(Reservation, confirmation_code=code)
    return render(request, 'book_success.html', {'reservation': reservation})

# УПРАВЛЕНИЕ СТОЛИКАМИ (только администратор)

def table_list(request):
    if not is_admin(request):
        return redirect('login')
    capacity = request.GET.get('capacity', '')
    qs = Table.objects.filter(delete_date__isnull=True).order_by('number')
    if capacity.isdigit():
        qs = qs.filter(capacity__gte=int(capacity))

    context = {
        'tables': qs,
        'capacities': Table.objects.values_list('capacity', flat=True).distinct().order_by('capacity'),
        'selected_cap': capacity,
    }
    if request.headers.get('HX-Request'):
        return render(request, 'table_list_fragment.html', context)
    return render(request, 'table_list.html', context)


def table_add(request):
    if not is_admin(request):
        return redirect('login')
    error = ''
    if request.method == 'POST':
        number = request.POST.get('number', '').strip()
        capacity = request.POST.get('capacity', '').strip()
        description = request.POST.get('description', '').strip()
        if not number or not capacity:
            error = 'Заполните все обязательные поля.'
        elif Table.objects.filter(number=number).exists():
            error = f'Столик №{number} уже существует.'
        else:
            Table.objects.create(number=number, capacity=capacity, description=description)
            return redirect('table_list')
    return render(request, 'table_form.html', {
        'error': error, 'action': 'Добавить столик', 'table': None,
    })


def table_edit(request, pk):
    if not is_admin(request):
        return redirect('login')
    table = get_object_or_404(Table, pk=pk)
    error = ''
    if request.method == 'POST':
        number = request.POST.get('number', '').strip()
        capacity = request.POST.get('capacity', '').strip()
        description = request.POST.get('description', '').strip()
        if not number or not capacity:
            error = 'Заполните все обязательные поля.'
        elif Table.objects.filter(number=number).exclude(pk=pk).exists():
            error = f'Столик №{number} уже существует.'
        else:
            table.number = number
            table.capacity = capacity
            table.description = description
            table.save()
            return redirect('table_list')
    return render(request, 'table_form.html', {
        'error': error, 'action': 'Редактировать столик', 'table': table,
    })


def table_delete(request, pk):
    if not is_admin(request):
        return redirect('login')
    table = get_object_or_404(Table, pk=pk)
    if request.method == 'POST':
        table.delete_date = timezone.now()
        table.save()
        return redirect('table_list')
    return render(request, 'table_confirm_delete.html', {'table': table})

# УПРАВЛЕНИЕ БРОНИРОВАНИЯМИ (только администратор)

def reservation_list(request):
    if not is_admin(request):
        return redirect('login')
    reservations = (
        Reservation.objects
        .filter(delete_date__isnull=True)
        .select_related('table', 'status', 'user')
        .order_by('-date', '-start_time')
    )
    return render(request, 'reservation_list.html', {'reservations': reservations})


def reservation_add(request):
    if not is_admin(request):
        return redirect('login')
    tables = Table.objects.all().order_by('number')
    statuses = ReservationStatus.objects.all()
    error = ''
    if request.method == 'POST':
        table_id = request.POST.get('table', '')
        status_id = request.POST.get('status', '')
        guest_name = request.POST.get('guest_name', '').strip()
        guest_phone = request.POST.get('guest_phone', '').strip()
        guest_email = request.POST.get('guest_email', '').strip()
        date_val = request.POST.get('date', '').strip()
        start_time = request.POST.get('start_time', '').strip()
        end_time = request.POST.get('end_time', '').strip()
        guests_count = request.POST.get('guests_count', '').strip()
        comment = request.POST.get('comment', '').strip()
        if not all([table_id, status_id, guest_name, guest_phone, date_val, start_time, end_time, guests_count]):
            error = 'Заполните все обязательные поля.'
        else:
            Reservation.objects.create(
                table_id=table_id,
                status_id=status_id,
                user=None,
                guest_name=guest_name,
                guest_phone=guest_phone,
                guest_email=guest_email,
                date=date_val,
                start_time=start_time,
                end_time=end_time,
                guests_count=guests_count,
                comment=comment,
                confirmation_code=uuid.uuid4().hex[:8].upper(),
            )
            return redirect('reservation_list')
    return render(request, 'reservation_form.html', {
        'error': error, 'action': 'Добавить бронирование',
        'reservation': None, 'tables': tables, 'statuses': statuses,
    })


def reservation_edit(request, pk):
    if not is_admin(request):
        return redirect('login')
    reservation = get_object_or_404(Reservation, pk=pk)
    tables = Table.objects.all().order_by('number')
    statuses = ReservationStatus.objects.all()
    error = ''
    if request.method == 'POST':
        table_id = request.POST.get('table', '')
        status_id = request.POST.get('status', '')
        guest_name = request.POST.get('guest_name', '').strip()
        guest_phone = request.POST.get('guest_phone', '').strip()
        guest_email = request.POST.get('guest_email', '').strip()
        date_val = request.POST.get('date', '').strip()
        start_time = request.POST.get('start_time', '').strip()
        end_time = request.POST.get('end_time', '').strip()
        guests_count = request.POST.get('guests_count', '').strip()
        comment = request.POST.get('comment', '').strip()
        if not all([table_id, status_id, guest_name, guest_phone, date_val, start_time, end_time, guests_count]):
            error = 'Заполните все обязательные поля.'
        else:
            reservation.table_id = table_id
            reservation.status_id = status_id
            reservation.guest_name = guest_name
            reservation.guest_phone = guest_phone
            reservation.guest_email = guest_email
            reservation.date = date_val
            reservation.start_time = start_time
            reservation.end_time = end_time
            reservation.guests_count = guests_count
            reservation.comment = comment
            reservation.save()
            return redirect('reservation_list')
    return render(request, 'reservation_form.html', {
        'error': error, 'action': 'Редактировать бронирование',
        'reservation': reservation, 'tables': tables, 'statuses': statuses,
    })


def reservation_delete(request, pk):
    if not is_admin(request):
        return redirect('login')
    reservation = get_object_or_404(Reservation, pk=pk)
    if request.method == 'POST':
        reservation.delete_date = timezone.now()
        reservation.save()
        return redirect('reservation_list')
    return render(request, 'reservation_confirm_delete.html', {'reservation': reservation})


def user_management_view(request):
    if not is_admin(request):
        return redirect('login')
    if request.method == 'POST':
        uid = request.POST.get('user_id')
        try:
            u = User.objects.get(pk=uid)
            u.is_active = not u.is_active
            u.save()
        except: pass
        return redirect('user_management')
    users = User.objects.all().order_by('login')
    return render(request, 'admin_users.html', {'users': users})


def soft_deleted_view(request):
    if not is_admin(request):
        return redirect('login')
    tables = Table.objects.filter(delete_date__isnull=False)
    reservations = Reservation.objects.filter(delete_date__isnull=False).select_related('table')
    return render(request, 'admin_soft_deleted.html', {'tables': tables, 'reservations': reservations})

def table_restore(request, pk):
    if not is_admin(request):
        return redirect('login')
    Table.objects.filter(pk=pk).update(delete_date=None)
    return redirect('soft_deleted')

def reservation_restore(request, pk):
    if not is_admin(request):
        return redirect('login')
    Reservation.objects.filter(pk=pk).update(delete_date=None)
    return redirect('soft_deleted')


def stats_view(request):
    if request.session.get('user_role') != 'Администратор':
        return redirect('login')

    # === ЧИСЛОВЫЕ ПОКАЗАТЕЛИ ===
    today = datetime.now().date()
    current_month = today.month
    current_year = today.year

    # Всего бронирований за текущий месяц
    total_this_month = Reservation.objects.filter(
        date__year=current_year,
        date__month=current_month,
        delete_date__isnull=True
    ).count()

    # Всего гостей за месяц
    guests_this_month = Reservation.objects.filter(
        date__year=current_year,
        date__month=current_month,
        delete_date__isnull=True
    ).aggregate(total=Sum('guests_count'))['total'] or 0

    # Среднее количество гостей на бронь
    avg_guests = round(guests_this_month / total_this_month, 1) if total_this_month > 0 else 0

    # Заполненность столиков (сколько уникальных столов было забронировано)
    booked_tables_count = Reservation.objects.filter(
        date__year=current_year,
        date__month=current_month,
        delete_date__isnull=True
    ).values('table').distinct().count()

    total_tables = Table.objects.count()
    occupancy_rate = round(booked_tables_count / total_tables * 100, 1) if total_tables > 0 else 0

    # Статусы бронирований
    status_counts = Reservation.objects.filter(
        delete_date__isnull=True
    ).values('status__name').annotate(count=Count('id'))
    status_dict = {s['status__name']: s['count'] for s in status_counts}

    # === ГРАФИК 1: Бронирования по месяцам (за последние 6 месяцев) ===
    months_labels = []
    months_counts = []
    for i in range(5, -1, -1):
        target_date = today - timedelta(days=i * 30)
        month = target_date.month
        year = target_date.year
        month_name = {1: 'Янв', 2: 'Фев', 3: 'Мар', 4: 'Апр', 5: 'Май', 6: 'Июн',
                      7: 'Июл', 8: 'Авг', 9: 'Сен', 10: 'Окт', 11: 'Ноя', 12: 'Дек'}
        label = f"{month_name[month]} {year}"
        count = Reservation.objects.filter(
            date__year=year,
            date__month=month,
            delete_date__isnull=True
        ).count()
        months_labels.append(label)
        months_counts.append(count)

    fig1, ax1 = plt.subplots(figsize=(8, 4))
    ax1.bar(months_labels, months_counts, color='#8B5E3C', edgecolor='#6e4a2e')
    ax1.set_title('📊 Бронирования по месяцам', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Количество броней')
    ax1.tick_params(axis='x', rotation=45)
    plt.tight_layout()

    buf1 = io.BytesIO()
    plt.savefig(buf1, format='png', bbox_inches='tight')
    plt.close(fig1)
    buf1.seek(0)
    chart1_b64 = base64.b64encode(buf1.read()).decode('utf-8')

    # === ГРАФИК 2: Загрузка столиков в текущем месяце ===
    table_stats = Reservation.objects.filter(
        date__year=current_year,
        date__month=current_month,
        delete_date__isnull=True
    ).values('table__number').annotate(
        bookings=Count('id'),
        guests=Sum('guests_count')
    ).order_by('-bookings')[:10]  # Топ-10 самых популярных

    table_numbers = [f"№{t['table__number']}" for t in table_stats]
    table_bookings = [t['bookings'] for t in table_stats]

    fig2, ax2 = plt.subplots(figsize=(8, 4))
    colors = ['#3D8B5E' if b >= 5 else '#8B5E3C' if b >= 3 else '#C0392B' for b in table_bookings]
    ax2.barh(table_numbers, table_bookings, color=colors, edgecolor='#6e4a2e')
    ax2.set_title(f'🪑 Загрузка столиков — {month_name[current_month]} {current_year}', fontsize=12, fontweight='bold')
    ax2.set_xlabel('Количество бронирований')
    ax2.invert_yaxis()
    plt.tight_layout()

    buf2 = io.BytesIO()
    plt.savefig(buf2, format='png', bbox_inches='tight')
    plt.close(fig2)
    buf2.seek(0)
    chart2_b64 = base64.b64encode(buf2.read()).decode('utf-8')

    context = {
        'chart1': chart1_b64,
        'chart2': chart2_b64,
        'total_this_month': total_this_month,
        'guests_this_month': guests_this_month,
        'avg_guests': avg_guests,
        'occupancy_rate': occupancy_rate,
        'status_confirmed': status_dict.get('Подтверждена', 0),
        'status_pending': status_dict.get('Ожидает подтверждения', 0),
        'status_cancelled': status_dict.get('Отменена', 0),
        'status_completed': status_dict.get('Завершена', 0),
        'month_name': {1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля', 5: 'мая', 6: 'июня',
                       7: 'июля', 8: 'августа', 9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'}[
            current_month],
        'current_year': current_year,
    }
    return render(request, 'stats.html', context)