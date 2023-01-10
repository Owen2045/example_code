
from user import views
from django.urls import include, path, re_path

urlpatterns = [
    re_path(r'avatar_change/$', views.AvatarChange.as_view()),

]
