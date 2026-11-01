from django.contrib import admin
from django.urls import path, include
from ocorrencias import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.login_view, name='login'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('home/', views.home, name='home'),
    path('dashboard/', include('dashboard.urls')),
    path('', include('ocorrencias.urls')),
    # --- API REST ---
    path('api/', include('api.urls')),
    path('api/auth/', include('rest_framework.urls')),
]
