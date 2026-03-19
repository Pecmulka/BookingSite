import uuid
from datetime import datetime, date, timedelta, time
from django.shortcuts import render, redirect, get_object_or_404
from .models import Table, User, Reservation, ReservationStatus


# Настройки заведения (часы работы, шаг слота в минутах)
OPEN_TIME  = time(10, 0)   # 10:00
CLOSE_TIME = time(23, 0)   # 23:00
SLOT_MINUTES = 60           # шаг бронирования — 1 час


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
    """Возвращает множество занятых start_time для конкретного стола и даты."""
    reservations = Reservation.objects.filter(
        table_id=table_id,
        date=selected_date,
    ).exclude(status__name='Отменена')
    return set(r.start_time for r in reservations)


# ---- Главная страница — список столиков ----

def index(request):
    capacity = request.GET.get('capacity', '')

    tables = Table.objects.all()
    if capacity.isdigit():
        tables = tables.filter(capacity__gte=int(capacity))

    all_capacities = Table.objects.values_list('capacity', flat=True).order_by('capacity').distinct()

    return render(request, 'index.html', {
        'tables': tables,
        'all_capacities': all_capacities,
        'selected': capacity,
    })


# ---- Авторизация / выход ----

def login_view(request):
    if request.session.get('user_id'):
        return redirect('index')

    error = ''
    if request.method == 'POST':
        login = request.POST.get('login', '')
        password = request.POST.get('password', '')
        try:
            user = User.objects.get(login=login, password=password)
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


# ==================================================================
# БРОНИРОВАНИЕ ДЛЯ ГОСТЕЙ
# ==================================================================

def book_table(request, pk):
    """Страница бронирования конкретного столика."""
    table = get_object_or_404(Table, pk=pk)

    # Дата: сначала из POST (скрытое поле), потом из GET, потом сегодня
    date_str = request.POST.get('date', '') or request.GET.get('date', '')
    try:
        selected_date = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
    except (ValueError, AttributeError):
        selected_date = date.today()

    # Нельзя бронировать прошедшие даты
    if selected_date < date.today():
        selected_date = date.today()

    date_str = selected_date.strftime('%Y-%m-%d')

    # Все слоты и занятые для этого стола и даты
    all_slots  = get_time_slots()
    busy_slots = get_busy_slots(table.pk, selected_date)

    # Слоты с пометкой свободен/занят
    slots = []
    for slot in all_slots:
        end_slot = (datetime.combine(date.today(), slot) + timedelta(minutes=SLOT_MINUTES)).time()
        slots.append({
            'start':  slot,
            'end':    end_slot,
            'label':  f'{slot.strftime("%H:%M")} — {end_slot.strftime("%H:%M")}',
            'busy':   slot in busy_slots,
        })

    error = ''

    if request.method == 'POST':
        start_str    = request.POST.get('start_time', '')
        guest_name   = request.POST.get('guest_name', '').strip()
        guest_phone  = request.POST.get('guest_phone', '').strip()
        guest_email  = request.POST.get('guest_email', '').strip()
        guests_count = request.POST.get('guests_count', '').strip()
        comment      = request.POST.get('comment', '').strip()

        if not all([start_str, guest_name, guest_phone, guests_count]):
            error = 'Заполните все обязательные поля.'
        else:
            try:
                start_time = datetime.strptime(start_str, '%H:%M').time()
                end_time   = (datetime.combine(date.today(), start_time) + timedelta(minutes=SLOT_MINUTES)).time()

                # Проверка: слот свободен
                if start_time in busy_slots:
                    error = 'Выбранное время уже занято. Пожалуйста, выберите другой слот.'
                # Проверка: количество гостей не больше вместимости
                elif int(guests_count) > table.capacity:
                    error = f'Количество гостей превышает вместимость столика ({table.capacity} мест).'
                else:
                    status, _ = ReservationStatus.objects.get_or_create(
                        name='Ожидает подтверждения'
                    )
                    code   = uuid.uuid4().hex[:8].upper()

                    Reservation.objects.create(
                        table=table,
                        status=status,
                        guest_name=guest_name,
                        guest_phone=guest_phone,
                        guest_email=guest_email,
                        date=selected_date,
                        start_time=start_time,
                        end_time=end_time,
                        guests_count=int(guests_count),
                        comment=comment,
                        confirmation_code=code,
                    )
                    return redirect('book_success', code=code)

            except (ValueError, ReservationStatus.DoesNotExist):
                error = 'Ошибка при сохранении. Попробуйте ещё раз.'

    return render(request, 'book_table.html', {
        'table':         table,
        'slots':         slots,
        'selected_date': date_str,
        'today':         date.today().strftime('%Y-%m-%d'),
        'error':         error,
        'post':          request.POST,
    })


def book_success(request, code):
    """Страница успешного бронирования с кодом подтверждения."""
    reservation = get_object_or_404(Reservation, confirmation_code=code)
    return render(request, 'book_success.html', {'reservation': reservation})


# ==================================================================
# УПРАВЛЕНИЕ СТОЛИКАМИ (только администратор)
# ==================================================================

def table_list(request):
    if not is_admin(request):
        return redirect('login')
    tables = Table.objects.all()
    return render(request, 'table_list.html', {'tables': tables})


def table_add(request):
    if not is_admin(request):
        return redirect('login')
    error = ''
    if request.method == 'POST':
        number      = request.POST.get('number', '')
        capacity    = request.POST.get('capacity', '')
        description = request.POST.get('description', '')
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
        number      = request.POST.get('number', '')
        capacity    = request.POST.get('capacity', '')
        description = request.POST.get('description', '')
        if not number or not capacity:
            error = 'Заполните все обязательные поля.'
        elif Table.objects.filter(number=number).exclude(pk=pk).exists():
            error = f'Столик №{number} уже существует.'
        else:
            table.number = number; table.capacity = capacity; table.description = description
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
        table.delete()
        return redirect('table_list')
    return render(request, 'table_confirm_delete.html', {'table': table})


# ==================================================================
# УПРАВЛЕНИЕ БРОНИРОВАНИЯМИ (только администратор)
# ==================================================================

def reservation_list(request):
    if not is_admin(request):
        return redirect('login')
    reservations = Reservation.objects.select_related('table').order_by('-date', '-start_time')
    return render(request, 'reservation_list.html', {'reservations': reservations})


def reservation_add(request):
    if not is_admin(request):
        return redirect('login')
    tables   = Table.objects.all()
    statuses = ReservationStatus.objects.all()
    error    = ''
    if request.method == 'POST':
        table_id     = request.POST.get('table')
        status_id    = request.POST.get('status')
        guest_name   = request.POST.get('guest_name', '')
        guest_phone  = request.POST.get('guest_phone', '')
        guest_email  = request.POST.get('guest_email', '')
        date_val     = request.POST.get('date', '')
        start_time   = request.POST.get('start_time', '')
        end_time     = request.POST.get('end_time', '')
        guests_count = request.POST.get('guests_count', '')
        comment      = request.POST.get('comment', '')
        if not all([table_id, status_id, guest_name, guest_phone, date_val, start_time, end_time, guests_count]):
            error = 'Заполните все обязательные поля.'
        else:
            Reservation.objects.create(
                table_id=table_id, status_id=status_id,
                guest_name=guest_name, guest_phone=guest_phone, guest_email=guest_email,
                date=date_val, start_time=start_time, end_time=end_time,
                guests_count=guests_count, comment=comment,
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
    tables   = Table.objects.all()
    statuses = ReservationStatus.objects.all()
    error    = ''
    if request.method == 'POST':
        table_id     = request.POST.get('table')
        status_id    = request.POST.get('status')
        guest_name   = request.POST.get('guest_name', '')
        guest_phone  = request.POST.get('guest_phone', '')
        guest_email  = request.POST.get('guest_email', '')
        date_val     = request.POST.get('date', '')
        start_time   = request.POST.get('start_time', '')
        end_time     = request.POST.get('end_time', '')
        guests_count = request.POST.get('guests_count', '')
        comment      = request.POST.get('comment', '')
        if not all([table_id, status_id, guest_name, guest_phone, date_val, start_time, end_time, guests_count]):
            error = 'Заполните все обязательные поля.'
        else:
            reservation.table_id=table_id; reservation.status_id=status_id
            reservation.guest_name=guest_name; reservation.guest_phone=guest_phone
            reservation.guest_email=guest_email; reservation.date=date_val
            reservation.start_time=start_time; reservation.end_time=end_time
            reservation.guests_count=guests_count; reservation.comment=comment
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
        reservation.delete()
        return redirect('reservation_list')
    return render(request, 'reservation_confirm_delete.html', {'reservation': reservation})