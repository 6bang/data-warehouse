from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.warehouse.serializers import AccountTokenObtainPairSerializer


class AccountTokenObtainPairView(TokenObtainPairView):
    serializer_class = AccountTokenObtainPairSerializer

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/token/", AccountTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/", include("apps.warehouse.urls")),
]
