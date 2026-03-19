from django.shortcuts import render, redirect, get_object_or_404
from .models import Table, User, Reservation, ReservationStatus

def is_admin(request):
    return request.session.get('user_role') == 'Администратор'


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
        'error': error,
        'action': 'Добавить столик',
        'table': None,
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
            table.number = number
            table.capacity = capacity
            table.description = description
            table.save()
            return redirect('table_list')

    return render(request, 'table_form.html', {
        'error': error,
        'action': 'Редактировать столик',
        'table': table,
    })


def table_delete(request, pk):
    if not is_admin(request):
        return redirect('login')

    table = get_object_or_404(Table, pk=pk)
    if request.method == 'POST':
        table.delete()
        return redirect('table_list')

    return render(request, 'table_confirm_delete.html', {'table': table})

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
        table_id = request.POST.get('table')
        status_id = request.POST.get('status')
        guest_name = request.POST.get('guest_name', '')
        guest_phone = request.POST.get('guest_phone', '')
        guest_email = request.POST.get('guest_email', '')
        date = request.POST.get('date', '')
        start_time = request.POST.get('start_time', '')
        end_time = request.POST.get('end_time', '')
        guests_count = request.POST.get('guests_count', '')
        comment = request.POST.get('comment', '')

        if not all([table_id, status_id, guest_name, guest_phone, date, start_time, end_time, guests_count]):
            error = 'Заполните все обязательные поля.'
        else:
            import uuid
            Reservation.objects.create(
                table_id=table_id,
                status_id=status_id,
                guest_name=guest_name,
                guest_phone=guest_phone,
                guest_email=guest_email,
                date=date,
                start_time=start_time,
                end_time=end_time,
                guests_count=guests_count,
                comment=comment,
                confirmation_code=uuid.uuid4().hex[:8].upper(),
            )
            return redirect('reservation_list')

    return render(request, 'reservation_form.html', {
        'error': error,
        'action': 'Добавить бронирование',
        'reservation': None,
        'tables': tables,
        'statuses': statuses,
    })


def reservation_edit(request, pk):
    if not is_admin(request):
        return redirect('login')

    reservation = get_object_or_404(Reservation, pk=pk)
    tables = Table.objects.all()
    statuses = ReservationStatus.objects.all()
    error = ''

    if request.method == 'POST':
        table_id = request.POST.get('table')
        status_id = request.POST.get('status')
        guest_name = request.POST.get('guest_name', '')
        guest_phone = request.POST.get('guest_phone', '')
        guest_email = request.POST.get('guest_email', '')
        date = request.POST.get('date', '')
        start_time = request.POST.get('start_time', '')
        end_time = request.POST.get('end_time', '')
        guests_count = request.POST.get('guests_count', '')
        comment = request.POST.get('comment', '')

        if not all([table_id, status_id, guest_name, guest_phone, date, start_time, end_time, guests_count]):
            error = 'Заполните все обязательные поля.'
        else:
            reservation.table_id = table_id
            reservation.status_id = status_id
            reservation.guest_name = guest_name
            reservation.guest_phone = guest_phone
            reservation.guest_email = guest_email
            reservation.date = date
            reservation.start_time = start_time
            reservation.end_time = end_time
            reservation.guests_count = guests_count
            reservation.comment = comment
            reservation.save()
            return redirect('reservation_list')

    return render(request, 'reservation_form.html', {
        'error': error,
        'action': 'Редактировать бронирование',
        'reservation': reservation,
        'tables': tables,
        'statuses': statuses,
    })


def reservation_delete(request, pk):
    if not is_admin(request):
        return redirect('login')

    reservation = get_object_or_404(Reservation, pk=pk)
    if request.method == 'POST':
        reservation.delete()
        return redirect('reservation_list')

    return render(request, 'reservation_confirm_delete.html', {'reservation': reservation})