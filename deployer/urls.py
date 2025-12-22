from django.urls import path
from . import views

app_name = 'deployer'

urlpatterns = [
    path('', views.index, name='index'),
]
