"""
URL configuration for booking project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from bookingWeb import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Бронирование мест
    path('book/<int:pk>/', views.book_table, name='book_table'),
    path('book/success/<str:code>/', views.book_success, name='book_success'),

    # Управление столиками
    path('admin/tables/', views.table_list, name='table_list'),
    path('admin/tables/add/', views.table_add, name='table_add'),
    path('admin/tables/<int:pk>/edit/', views.table_edit, name='table_edit'),
    path('admin/tables/<int:pk>/delete/', views.table_delete, name='table_delete'),

    # Управление бронированиями
    path('admin/reservations/', views.reservation_list, name='reservation_list'),
    path('admin/reservations/add/', views.reservation_add, name='reservation_add'),
    path('admin/reservations/<int:pk>/edit/', views.reservation_edit, name='reservation_edit'),
    path('admin/reservations/<int:pk>/delete/', views.reservation_delete, name='reservation_delete'),
]
