from django.contrib import admin
from django.urls import include, path
from finance import views

urlpatterns = [
    path("healthz/", views.healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("", views.landing, name="landing"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("mfa/", include("django_mfa.urls")),
    path("signup/", views.signup, name="signup"),
    path("verify-email/<str:token>/", views.verify_email, name="verify_email"),
    path("privacy/", views.privacy, name="privacy"),
    path("app/", include("finance.urls")),
]
