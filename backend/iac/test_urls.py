"""URL harness for retained legacy IaC code; never included in the product router."""
from django.urls import include, path

urlpatterns = [path('api/iac/', include('iac.urls'))]
