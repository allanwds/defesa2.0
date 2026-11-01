from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard_page, name="dashboard"),
    path("dados/", views.dashboard_dados, name="dashboard_dados"),
]
