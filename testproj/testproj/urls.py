from django.contrib import admin
from django.urls import path

from .testapp import views

urlpatterns = [
    path("", views.secret_list, name="secret_list"),
    path("admin/", admin.site.urls),
]
