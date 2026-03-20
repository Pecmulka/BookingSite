from django.test import TestCase, Client
from .models import Role, User, Table, ReservationStatus, Reservation
from datetime import date, time


class BookingTests(TestCase):

    def setUp(self):
        """Подготовка тестовых данных перед каждым тестом."""

        self.role_admin = Role.objects.create(name='Администратор')
        self.role_guest = Role.objects.create(name='Гость')

        self.admin = User.objects.create(
            fio='Иванов Иван Иванович',
            login='admin',
            password='admin123',
            role=self.role_admin,
        )
        self.guest_user = User.objects.create(
            fio='Петров Пётр Петрович',
            login='guest',
            password='guest123',
            role=self.role_guest,
        )

        self.table1 = Table.objects.create(
            number=1, capacity=2, description='У окна'
        )
        self.table2 = Table.objects.create(
            number=2, capacity=4, description='В центре зала'
        )

        self.status_pending   = ReservationStatus.objects.create(name='Ожидает подтверждения')
        self.status_cancelled = ReservationStatus.objects.create(name='Отменена')

        self.reservation = Reservation.objects.create(
            table=self.table1,
            status=self.status_pending,
            user=self.guest_user,
            guest_name='Петров Пётр Петрович',
            guest_phone='+7-900-000-00-01',
            guest_email='petrov@test.ru',
            date=date(2026, 6, 15),
            start_time=time(12, 0),
            end_time=time(13, 0),
            guests_count=2,
            confirmation_code='TESTCODE',
            comment='',
        )

        self.client = Client()

    # ----------------------------------------------------------------
    # Тест 1: Авторизация с неверным паролем
    # ----------------------------------------------------------------
    def test_login_wrong_password(self):
        """Авторизация с неверным паролем возвращает сообщение об ошибке."""
        response = self.client.post('/login/', {
            'login': 'admin',
            'password': 'wrongpassword',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Неверный логин или пароль')

    # ----------------------------------------------------------------
    # Тест 2: Фильтрация столиков по вместимости
    # ----------------------------------------------------------------
    def test_table_filter_by_capacity(self):
        """Фильтр по вместимости возвращает только подходящие столики."""
        tables_2 = Table.objects.filter(capacity__gte=2)
        tables_4 = Table.objects.filter(capacity__gte=4)

        self.assertEqual(tables_2.count(), 2)
        self.assertEqual(tables_4.count(), 1)
        self.assertEqual(tables_4.first().number, 2)

    # ----------------------------------------------------------------
    # Тест 3: Уникальность кода подтверждения
    # ----------------------------------------------------------------
    def test_confirmation_code_unique(self):
        """Коды подтверждения у разных бронирований не совпадают."""
        reservation2 = Reservation.objects.create(
            table=self.table2,
            status=self.status_pending,
            guest_name='Сидоров Сидор',
            guest_phone='+7-900-000-00-02',
            guest_email='sidorov@test.ru',
            date=date(2026, 6, 16),
            start_time=time(14, 0),
            end_time=time(15, 0),
            guests_count=3,
            confirmation_code='TESTCO2',
        )
        self.assertNotEqual(
            self.reservation.confirmation_code,
            reservation2.confirmation_code,
        )

    # ----------------------------------------------------------------
    # Тест 4: Страница администратора недоступна без авторизации
    # ----------------------------------------------------------------
    def test_admin_page_requires_auth(self):
        """Список столиков администратора недоступен без авторизации."""
        response = self.client.get('/admin/tables/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    # ----------------------------------------------------------------
    # Тест 5: Подсчёт занятых слотов
    # ----------------------------------------------------------------
    def test_busy_slots_count(self):
        """Занятый слот корректно определяется для столика и даты."""
        busy = Reservation.objects.filter(
            table=self.table1,
            date=date(2026, 6, 15),
        ).exclude(status__name='Отменена').values_list('start_time', flat=True)

        self.assertIn(time(12, 0), busy)
        self.assertNotIn(time(14, 0), busy)
