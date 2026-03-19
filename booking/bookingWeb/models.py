from django.db import models


class Role(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class User(models.Model):
    role     = models.ForeignKey(Role, on_delete=models.CASCADE)
    fio      = models.CharField(max_length=255)
    login    = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=255)

    def __str__(self):
        return self.fio


class Table(models.Model):
    number      = models.IntegerField()
    capacity    = models.IntegerField()
    description = models.CharField(max_length=300)

    def __str__(self):
        return f'Столик №{self.number}'


class ReservationStatus(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Reservation(models.Model):
    table             = models.ForeignKey(Table, on_delete=models.CASCADE)
    status            = models.ForeignKey(ReservationStatus, on_delete=models.CASCADE)
    guest_name        = models.CharField(max_length=200)
    guest_phone       = models.CharField(max_length=20)
    guest_email       = models.CharField(max_length=200)
    date              = models.DateField()
    start_time        = models.TimeField()
    end_time          = models.TimeField()
    guests_count      = models.IntegerField()
    confirmation_code = models.CharField(max_length=8)
    comment           = models.CharField(max_length=500, blank=True)

    def __str__(self):
        return f'Бронь {self.confirmation_code} — {self.guest_name}'