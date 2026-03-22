from django.urls import path
from .views import ComputerRegisterView

urlpatterns = [
    path('register/', ComputerRegisterView.as_view(), name='computer-register'),
]