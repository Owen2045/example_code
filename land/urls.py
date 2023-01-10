from django.urls import re_path

from land import views_polygon, views

urlpatterns = [
    re_path(r'^insidepolygon/$', views_polygon.PolyProcess.as_view(), name="insidepolygon"),
    re_path(r'^feedback_tp/$', views.FeedbackTp.as_view()),
]