from django.contrib import admin
from django.urls import include, path
from finance import views

urlpatterns = [
    path("healthz/", views.healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("", views.landing, name="landing"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("signup/", views.signup, name="signup"),
    path("privacy/", views.privacy, name="privacy"),
    path("app/", include("finance.urls")),
]
