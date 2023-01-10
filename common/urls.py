
from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import (SpectacularAPIView, SpectacularRedocView,
                                   SpectacularSwaggerView)
from rest_framework import routers

from common import views, get_all_code_views as views_2

#----------------------------------


urlpatterns = [
    # HTML
    re_path(r'car/$', views.Car.as_view()),
    re_path(r'stats/$', views.StatsView.as_view()),
    re_path(r'city_update/$', views.CityUpdateView.as_view()),
    re_path(r'land_code_update/$', views.LandCodeUpdateView.as_view()),

    # API
    re_path(r'^car/get_city/$', views.GetCityListView.as_view()),
    re_path(r'^car/get_area/$', views.GetAreaListView.as_view()),
    re_path(r'^car/get_office/$', views.GetOfficeListView.as_view()),
    re_path(r'^car/get_region/$', views.GetRegionListView.as_view()),
    #* 取得全臺代碼(縣市、行政區、段小段)
    re_path(r'^car/get_all_code/$', views_2.GetAllCodeView.as_view()),

    re_path(r'^lbor/feedback/$', views.FeedbackLbor.as_view()),
    re_path(r'^lbor/region_question/$', views.RegionQuestion.as_view()),
    re_path(r'^lbor/region_question_time/$', views.RegionQuestionTime.as_view()),

    re_path(r'^lbor/region_list/$', views.RegionList.as_view()),

    # tp
    re_path(r'^tp/input_task/$', views.CreateTpTaskView.as_view()),
    re_path(r'^tp/feedback/$', views.FeedbackTpView.as_view()),
    # lbor
    re_path(r'^lbor/input_task/$', views.CreateLborTaskView.as_view()),
    # tp task
    re_path(r'^tp/get_task/$', views.GetTpTaskView.as_view()),
    re_path(r'^lbor/get_task/$', views.GetLborTaskView.as_view()),
    re_path(r'^lbor/set_blacklist/$', views.Blacklist.as_view()),

    # generate
    re_path(r'^lbor/generate_task/$', views.GenerateTaskView.as_view()),

    re_path(r'^lbor/feedback_error/$', views.FeedbackLborErrorView.as_view()),
    re_path(r'^tp/feedback_error/$', views.FeedbackTpErrorView.as_view()),

    re_path(r'^tp/pdf/$', views.SavePdfView.as_view()),
    re_path(r'^tp/get_tp/system/$', views.GetTpView.as_view()),
    re_path(r'^tp/get_tp/pdf/$', views.GetTpPDFView.as_view()),
    # TODO 顯示圖片，測試中
    re_path(r'^stats_chart/$', views.StatsChartView.as_view()),
]

