from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from core.views import CurrentUserView, DashboardView, ReportExportView, ProtectedMediaView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/me/", CurrentUserView.as_view(), name="current-user"),
    path("api/dashboard/", DashboardView.as_view(), name="dashboard"),
    path("api/reports/<str:report_type>/", ReportExportView.as_view(), name="reports"),
    path("api/private-files/<path:file_path>", ProtectedMediaView.as_view(), name="private-files"),
    path("api/", include("core.urls")),
]
