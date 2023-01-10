import functools
import json
import logging
import operator
import os
import re
import time
import zoneinfo
from datetime import datetime
from io import BytesIO, StringIO

import matplotlib.pyplot as plt
import numpy as np
import objectpath
import pandas as pd
import requests as req
from django.conf import settings
from django.db import transaction
from django.db.models import ExpressionWrapper, F, FloatField, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
# pdf 製作需要
from django.template.loader import get_template
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.generic import TemplateView, View
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (OpenApiCallback, OpenApiExample,
                                   OpenApiParameter, OpenApiResponse,
                                   Serializer, extend_schema,
                                   inline_serializer)
from rest_framework import authentication, permissions, serializers
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.views import APIView
from xhtml2pdf import pisa

import building.building_serializers as B_s
import building.models
import land.land_serializers as L_s
import land.models
from common.enums import (IsvalidTypeEnum, LBEnum, LborTpTypeEnum,
                          PropertyTypeEnum, QuerySystemEnum, RuleTypeEnum,
                          TaskTypeEnum)
from common.models import (AreaCodeTable, CityCodeTable, OfficeCodeTable,
                           RegionCodeTable, SystemConfig, UserActionLog)
from common.serializers import (AreaCodeTableSerializer,
                                CityCodeTableSerializer,
                                FeedbackLborErrorSerializer,
                                FeedbackLborSerializer,
                                FeedbackTpErrorSerializer,
                                FeedbackTplogSerializer,
                                GenerateLborTaskSerializer,
                                GetLborTaskSerializer, GetTpPDFSerializer,
                                GetTpSerializer, GetTpTaskSerializer,
                                LborTaskSerializer, OfficeCodeTableSerializer,
                                RegionCodeTableSerializer,
                                RegionListSerializer, RegionQuestionSerializer,
                                RegionQuestionTimeSerializer,
                                SetBlackDetailSerializer,
                                StatsChartBarSerializer,
                                StatsChartLineSerializer,
                                StatsChartPieSerializer, TpTaskSerializer,
                                create_lbor, set_propertyType)
from common.util import (SYSTEM_ENVIRONMENT, CombinTranscript, batch,
                         change_last_regno_time, dict_env, get_dba, getLBEnum,
                         query_debugger, time_proV2)

json_dumps_params = {'ensure_ascii': False}

logger = logging.getLogger(__name__)

paris_tz = zoneinfo.ZoneInfo(settings.TIME_ZONE)

class Car(TemplateView):
    def get(self, request):
        cityCodeTable = CityCodeTable.objects.all()
        return render(request, 'car.html', {'cityCodeTable': cityCodeTable})


class CityUpdateView(TemplateView):
    '''到平台抓取最新的縣市資料'''

    def get(self, request):
        df = pd.DataFrame([{"city_name":"臺北市","city_code":"A"},{"city_name":"臺中市","city_code":"B"},{"city_name":"基隆市","city_code":"C"},
        {"city_name":"臺南市","city_code":"D"},{"city_name":"高雄市","city_code":"E"},{"city_name":"新北市","city_code":"F"},
        {"city_name":"宜蘭縣","city_code":"G"},{"city_name":"桃園市","city_code":"H"},{"city_name":"嘉義市","city_code":"I"},
        {"city_name":"新竹縣","city_code":"J"},{"city_name":"苗栗縣","city_code":"K"},{"city_name":"南投縣","city_code":"M"},
        {"city_name":"彰化縣","city_code":"N"},{"city_name":"新竹市","city_code":"O"},{"city_name":"雲林縣","city_code":"P"},
        {"city_name":"嘉義縣","city_code":"Q"},{"city_name":"屏東縣","city_code":"T"},{"city_name":"花蓮縣","city_code":"U"},
        {"city_name":"臺東縣","city_code":"V"},{"city_name":"金門縣","city_code":"W"},{"city_name":"澎湖縣","city_code":"X"},
        {"city_name":"連江縣","city_code":"Z"}])
        qs = CityCodeTable.objects.values('city_name', 'city_code')
        df1 = pd.DataFrame(qs)

        diff = pd.concat([df, df1]).drop_duplicates(keep=False)
        row_list = []
        for row in diff.itertuples():
            row_list.append(CityCodeTable(city_name=row.city_name, city_code=row.city_code))
        CityCodeTable.objects.bulk_create(row_list)
        return JsonResponse({'data': "更新成功"}, json_dumps_params=json_dumps_params)


def _applyRegion(data):
    if pd.isna(data['小段']):
        return "{}段".format(data['段'])
    else:
        return "{}段{}小段".format(data['段'], data['小段'])

def _applyArea(data):
    return data['所區碼'][2:]

def _applyOffice(data):
    return data['所區碼'][:2]

def _applyRemark(data):
    if pd.isna(data['備註']):
        return True
    if data['備註'] == '註銷':
        return False
    return True

def _applyRegionChange(data):
    if (data['is_valid'] == data['is_valid_y']) and (data['remark'] == data['remark_y']):
        return False
    return True

def _applyCityCode(date, city_name_dict):
    return city_name_dict[date].city_code

def _diff_upday(filename:str):
    if os.path.exists(filename) == False:
        return 999
    datetime_now = datetime.now()
    unix_time = os.path.getmtime(filename)
    datetime_file = datetime.fromtimestamp(unix_time)
    return (datetime_now-datetime_file).days

class LandCodeUpdateView(TemplateView):
    '''
    到行政區,段小段,事務所抓取最新的事務所資料
    行政區 > 只會新增資料
    事務所 > 只會新增資料
    段小段 > 檢測有無效 與新增資料
    '''

    def get(self, request):
        local_filename = '地段代碼.xlsx'
        qs_check = RegionCodeTable.objects.filter(id__in=[1, 2, 3, 4, 5])
        if qs_check:
            return JsonResponse({'data': '已存在段小段資料'}, json_dumps_params=json_dumps_params)

        if _diff_upday(local_filename) > 3:
            # 上次下載時間 大於三天 資料下載
            url = 'https://lisp.land.moi.gov.tw/MMS/Handle/DownloadQuerySection.ashx?DownloadType=xls&CountyCode=&OfficeCode=&TownCode='
            with req.get(url, stream=True) as r:
                r.raise_for_status()
                with open(local_filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
        city_code_table = CityCodeTable.objects.all()

        if city_code_table.exists() == False:
            return JsonResponse({'data': '請先點選縣市更新'}, json_dumps_params=json_dumps_params)

        city_name_dict = {}
        city_dict = {}
        for cityCode in city_code_table:
            city_name_dict[cityCode.city_name] = cityCode
            city_dict[cityCode.city_code] = cityCode

        # 資料處理
        df = pd.read_excel(local_filename, dtype={'代碼': str})
        df['region_name'] = df.apply(_applyRegion, axis=1)
        df['area_code'] = df.apply(_applyArea, axis=1)
        df['office_code'] = df.apply(_applyOffice, axis=1)
        df['is_valid'] = df.apply(_applyRemark, axis=1)
        df['city_name'] = df['縣市名稱'].apply(lambda x: x.replace('台', '臺'))
        df['city_code'] = df['city_name'].apply(_applyCityCode, args=(city_name_dict,))
        df['備註'] = df['備註'].fillna('')
        df = df[['city_name', 'city_code', '鄉鎮名稱', 'area_code', '事務所名稱', 'office_code', 'region_name', '代碼', '備註', 'is_valid']]

        df = df.rename(columns={'代碼': 'region_code',
                                '鄉鎮名稱': 'area_name',
                                '事務所名稱': 'office_name',
                                '備註': 'remark'})

        # 處理行政區表格(新增)
        area_objs = []
        city_area_dict = {}

        areaCodeTable = pd.DataFrame(list(AreaCodeTable.objects.all().values('id', 'city_code_table_id__city_name', 'city_code_table_id__city_code', 'area_name', 'area_code')))
        areaCodeTable = areaCodeTable.rename(columns={'city_code_table_id__city_name': 'city_name', 'city_code_table_id__city_code': 'city_code'})
        # 拆行政區表格
        df_area = df[['city_name', 'city_code', 'area_name', 'area_code']].copy()
        df_area.drop_duplicates(inplace=True, subset=['city_code', 'area_code'])
        df_area = df_area.reset_index(drop=True)

        if len(areaCodeTable):
            # 分新舊
            df_area_diff = df_area.merge(areaCodeTable, how='left', on=['city_code', 'area_code'], indicator=True)
            df_area_diff = df_area_diff.rename(columns={'area_name_x': 'area_name'})
            df_area_new = df_area_diff[df_area_diff['_merge'] == 'left_only']
            df_area_old = df_area_diff[df_area_diff['_merge']=='both']
            for data in df_area_old.itertuples():
                city_area_dict[f'{data.city_code}_{data.area_code}'] = AreaCodeTable.objects.get(id=data.id)
        else:
            df_area_new = df_area

        for data in df_area_new.itertuples():
            area_code_table = AreaCodeTable(city_code_table_id=city_dict[data.city_code], area_name=data.area_name, area_code=data.area_code)
            area_objs.append(area_code_table)
            city_area_dict[f'{data.city_code}_{data.area_code}'] = area_code_table
        AreaCodeTable.objects.bulk_create(area_objs)


        # 處理事務所表格(新增)
        office_objs = []
        city_office_dict = {}

        officeCodeTable = pd.DataFrame(list(OfficeCodeTable.objects.all().values('id', 'city_code_table_id__city_name', 'city_code_table_id__city_code', 'office_name', 'office_code')))
        officeCodeTable = officeCodeTable.rename(columns={'city_code_table_id__city_name': 'city_name', 'city_code_table_id__city_code': 'city_code'})

        # 拆事務所表格
        df_office = df[['city_name', 'city_code', 'office_name', 'office_code']].copy()
        df_office.drop_duplicates(inplace=True, subset=['city_code', 'office_code'])
        df_office = df_office.reset_index(drop=True)

        if len(officeCodeTable):
            # 分新舊
            df_office_diff = df_office.merge(officeCodeTable, how='left', on=['city_code', 'office_code'], indicator=True)
            df_office_diff = df_office_diff.rename(columns={'office_name_x': 'office_name'})
            df_office_new = df_office_diff[df_office_diff['_merge'] == 'left_only']
            df_office_old = df_office_diff[df_office_diff['_merge']=='both']
            for data in df_office_old.itertuples():
                city_office_dict[f'{data.city_code}_{data.office_code}'] = OfficeCodeTable.objects.get(id=data.id)
        else:
            df_office_new = df_office

        for data in df_office_new.itertuples():
            office_code_table = OfficeCodeTable(city_code_table_id=city_dict[data.city_code], office_name=data.office_name, office_code=data.office_code)
            office_objs.append(office_code_table)
            city_office_dict[f'{data.city_code}_{data.office_code}'] = office_code_table
        OfficeCodeTable.objects.bulk_create(office_objs)

        # -----  段小段處理  -----
        regionCodeTable = pd.DataFrame(list(RegionCodeTable.objects.all().values(
            'id', 'area_code_table_id__city_code_table_id__city_name', 'area_code_table_id__area_code', 'region_name', 'region_code', 'is_valid', 'remark')))
        regionCodeTable = regionCodeTable.rename(
            columns={'area_code_table_id__city_code_table_id__city_name': 'city_name', 'area_code_table_id__area_code': 'area_code'})

        if len(regionCodeTable):
            df_diff = df.merge(regionCodeTable, how='left', on=['city_name', 'area_code', 'region_code'], indicator=True)
            df_diff = df_diff.rename(columns={'region_name_x': 'region_name', 'is_valid_x': 'is_valid', 'remark_x': 'remark'})
            df_new = df_diff[df_diff['_merge'] == 'left_only']
            df_old = df_diff[df_diff['_merge'] == 'both'].copy()

            df_old['change'] = df_old.apply(_applyRegionChange, axis=1)
            df_old = df_old[df_old['change'] == True]

            region_objs = []
            for data in df_old.itertuples():
                obj = RegionCodeTable.objects.get(id=data.id)
                obj.is_valid = data.is_valid
                obj.remark = data.remark
                if data.is_valid == False:
                    obj.remove_time = timezone.now()
                region_objs.append(obj)
            RegionCodeTable.objects.bulk_update(region_objs, fields=['is_valid', 'remark', 'remove_time'], batch_size=1000)
        else:
            df_new = df
            df_old = []

        region_objs = []
        for data in df_new.itertuples():
            kargs = {'region_name': data.region_name,
                    'region_code': data.region_code,
                    'area_code_table_id': city_area_dict[f'{data.city_code}_{data.area_code}'],
                    'office_code_table_id': city_office_dict[f'{data.city_code}_{data.office_code}'],
                    'remark': data.remark,
                    'is_valid': data.is_valid}
            if data.is_valid == False:
                kargs['remove_time'] = timezone.now()
            region_objs.append(RegionCodeTable(**kargs))
        RegionCodeTable.objects.bulk_create(region_objs, batch_size=1000)
        return JsonResponse({'data': "新增筆數: {}\n異動筆數: {}".format(len(df_new), len(df_old))}, json_dumps_params=json_dumps_params)


class GetCityListView(APIView):
    '''
    取得縣市清單
    '''
    authentication_classes = [authentication.SessionAuthentication]
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        description='取縣市代碼',
        summary='取縣市代碼',
        request=None,
        responses={
            200: CityCodeTableSerializer,
            401: OpenApiResponse(description='身分認證失敗'),
        },
    )
    def get(self, request):
        serializer = CityCodeTableSerializer(CityCodeTable.objects.all(), many=True)
        return Response(serializer.data)


class GetAreaListView(APIView):
    '''
    取得行政區清單

    '''
    authentication_classes = [authentication.SessionAuthentication]
    permission_classes = [permissions.AllowAny]
    @extend_schema(
        summary='取行政區代碼',
        description='取行政區代碼',
        request=None,
        responses={
            200: AreaCodeTableSerializer,
            401: OpenApiResponse(description='身分認證失敗'),
        },
        parameters=[
            OpenApiParameter("city", OpenApiTypes.STR)
        ],
        examples=[
            OpenApiExample(
                name='新北市',
                value=[{"area_name": "新莊區","area_code": "01"},{"area_name": "林口區","area_code": "02"}],
                response_only=True,
            ),
        ],
        )
    def get(self, request):
        city_code = request.GET.get('city')
        areaCodeTable = AreaCodeTable.objects.filter(city_code_table_id__city_code=city_code)
        serializer = AreaCodeTableSerializer(areaCodeTable, many=True)
        return Response(serializer.data)


class GetOfficeListView(APIView):
    '''
    取得事務所清單
    '''
    authentication_classes = [authentication.SessionAuthentication]
    permission_classes = [permissions.AllowAny]
    @extend_schema(
        summary='取得事務所代碼',
        description='取得事務所代碼',
        request=None,
        responses={
            200: OfficeCodeTableSerializer,
            401: OpenApiResponse(description='身分認證失敗'),
        },
        parameters=[
            OpenApiParameter("city", OpenApiTypes.STR)
        ],
        examples=[
            OpenApiExample(
                name='台北市',
                value=[{"office_name": "松山地政事務所","office_code": "AD"},{"office_name": "大安地政事務所","office_code": "AF"}],
                response_only=True),
        ],
        )
    def get(self, request):
        city_code = request.GET.get('city')
        office_list_qs = OfficeCodeTable.objects.filter(city_code_table_id__city_code=city_code)
        serializer = OfficeCodeTableSerializer(office_list_qs, many=True)
        return Response(serializer.data)


class GetRegionListView(APIView):
    '''
    取得段小段清單
    city=A >> 輸入縣市
    area=01 >> 輸入行政區
    '''
    authentication_classes = [authentication.SessionAuthentication]
    permission_classes = [permissions.AllowAny]
    @extend_schema(
        summary='取得段小段清單',
        description='取得段小段清單',
        request=None,
        responses={
            200: RegionCodeTableSerializer,
            401: OpenApiResponse(description='身分認證失敗'),
        },
        parameters=[
            OpenApiParameter("city", OpenApiTypes.STR),
            OpenApiParameter("area", OpenApiTypes.STR)
        ],
        examples=[
            OpenApiExample(
                name='台北市松山區',
                value=[{"region_name": "西松段一小段","region_code": "0600","car_code": "A_01_0600"},{"region_name": "西松段二小段","region_code": "0601","car_code": "A_01_0601"}],
                response_only=True),
        ])
    def get(self, request):
        city_code = request.GET.get('city')
        area_code = request.GET.get('area')
        kargs = {
            'area_code_table_id__city_code_table_id__city_code': city_code,
            'area_code_table_id__area_code': area_code,
            'is_valid': True
        }
        region_list_qs = RegionCodeTable.objects.filter(**kargs)
        serializer = RegionCodeTableSerializer(region_list_qs, many=True)
        return Response(serializer.data)


class FeedbackLbor(APIView):
    '''
    登序資料新增

    使用者驗證：
    
    headers = {'Authorization': 'token 22a7bfe39c228d32*****11b2f5f24218e6d65ab',}
    '''
    # authentication.SessionAuthentication 使用者認證(利用cookie)
    # authentication.TokenAuthentication token認證(利用Authorization)

    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='回傳登序清單',
        # description='回傳登序清單',
        request=FeedbackLborSerializer,
        # responses=XSerializer(many=True))
        responses={
            200: OpenApiResponse(description='新增成功'),
            401: OpenApiResponse(description='身分認證失敗'),
        },
        # parameters=[FeedbackLborSerializer],
        # examples=[
        #     OpenApiExample(
        #         name='台北市松山區',
        #         value=[{"region_name": "西松段一小段","region_code": "0600","car_code": "A_01_0600"},{"region_name": "西松段二小段","region_code": "0601","car_code": "A_01_0601"}],
        #         response_only=True),
        # ]
        )
    def post(self, request, *args, **kwargs):
        if type(request.data) == list:
            serializer = FeedbackLborSerializer(data=request.data, many=True)
        else:
            serializer = FeedbackLborSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(user=request.user)
        else:
            raise ParseError(serializer.errors)
        return Response({})

class RegionQuestion(APIView):
    '''
    使用者驗證：
    
    headers = {'Authorization': 'token 22a7bfe39c228d32*****11b2f5f24218e6d65ab',}
    '''
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='錯誤log處理',
        description='廢棄最後一筆正常 > 解析異常處理 (admin可處理不是最後一筆的log異常)',
        request=RegionQuestionSerializer,
        responses={
            200: OpenApiResponse(description='處理成功'),
            401: OpenApiResponse(description='身分認證失敗'),
        },
        )
    def post(self, request, *args, **kwargs):
        msg = {}
        lbkeys = request.data['lbkey'].split(',')
        # 輸入lbkey > 最後一筆正常解析廢棄 > 
        #    解析新增時間為最後一筆 直接刪除
        #    解析移除時間為最後一筆 移除移除時間 改變狀態
        #    解析名字因上方改變狀態而去抓取上上筆 改回正常
        #    解析異常改待處理 然後一筆一筆送進原解析流程
        with transaction.atomic(): 
            for lbkey in lbkeys:
                LB_enum = getLBEnum(lbkey)
                if LB_enum == LBEnum.LAND:
                    LB_models = land.models
                elif LB_enum == LBEnum.BUILD:
                    LB_models = building.models
                else:
                    msg[lbkey] = '土建類別錯誤'
                    continue
                summary_qs = LB_models.Summary.objects.filter(lbkey=lbkey)
                if summary_qs.exists() == False:
                    msg[lbkey] = '無此地建號'
                    continue
                summary_id = summary_qs[0]

                regno_log_qs = LB_models.RegnoLog.objects.filter(summary_id=summary_id, state__in=[TaskTypeEnum.COMPLETE, TaskTypeEnum.COMPLETE_NO_CHANGE])

                end_complete_regno_log_qs = regno_log_qs.filter(state__in=[TaskTypeEnum.COMPLETE, TaskTypeEnum.COMPLETE_NO_CHANGE]).order_by('-id')
                discard_log = end_complete_regno_log_qs[0]

                o_complete_log = end_complete_regno_log_qs.exclude(id=discard_log.id).filter(rules__in=[RuleTypeEnum.BOTH, RuleTypeEnum.OWNER]).first()
                r_complete_log = end_complete_regno_log_qs.exclude(id=discard_log.id).filter(rules__in=[RuleTypeEnum.BOTH, RuleTypeEnum.RIGHT]).first()

                if o_complete_log == None and r_complete_log == None:
                    msg[lbkey] = '異常, 查無上一筆所或他log'
                    continue

                if discard_log.query_time < o_complete_log.query_time or discard_log.query_time < r_complete_log.query_time:
                    # 廢棄log查詢時間要比上一筆完成還要新，時間小於的話直接廢棄
                    discard_log.state = TaskTypeEnum.DISCARD
                    discard_log.save()
                    msg[lbkey] = '異常, 最後1筆比最後2筆還舊,直接廢棄'
                    continue

                owner_qs = summary_id.ownerregnosummary_set.all()
                right_qs = summary_id.rightregnosummary_set.all()

                if o_complete_log:
                    o_dels, o_modifys = change_last_regno_time(discard_log, o_complete_log.query_time, o_complete_log.owners, owner_qs)
                else:
                    o_dels, o_modifys = change_last_regno_time(discard_log, None, None, owner_qs)

                if r_complete_log:
                    r_dels, r_modifys = change_last_regno_time(discard_log, r_complete_log.query_time, r_complete_log.rights, right_qs)
                else:
                    r_dels, r_modifys = change_last_regno_time(discard_log, None, None, right_qs)

                if o_complete_log.is_no_list == False:
                    summary_id.is_valid_type = IsvalidTypeEnum.VALID

                owner_qs.filter(id__in=o_dels).delete()
                right_qs.filter(id__in=r_dels).delete()

                LB_models.OwnerRegnoSummary.objects.bulk_update(o_modifys, fields=['name', 'is_valid_type', 'query_time', 'remove_time'])
                LB_models.RightRegnoSummary.objects.bulk_update(r_modifys, fields=['name', 'is_valid_type', 'query_time', 'remove_time'])

                if r_complete_log == None:
                    summary_id.query_time = o_complete_log.query_time
                elif o_complete_log == None:
                    summary_id.query_time = r_complete_log.query_time
                elif o_complete_log.query_time >= r_complete_log.query_time:
                    summary_id.query_time = o_complete_log.query_time
                else:
                    summary_id.query_time = r_complete_log.query_time
                summary_id.save()

                discard_log.state = TaskTypeEnum.DISCARD
                discard_log.save()

                regno_log_qs = LB_models.RegnoLog.objects.filter(summary_id=summary_id, state=TaskTypeEnum.ABNORMAL_PARSER)
                for regno_log in regno_log_qs:
                    regno_log.state = TaskTypeEnum.INIT
                    create_lbor([regno_log], LB_enum)
                msg[lbkey] = 'OK'
            return Response(msg)


class RegionQuestionTime(APIView):
    '''
    使用者驗證：
    
    headers = {'Authorization': 'token 22a7bfe39c228d32*****11b2f5f24218e6d65ab',}
    '''
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='錯誤log時間處理',
        description='地建號內失效的登序，與指定時間一樣，刪除移除時間把失效改成有效',
        request=RegionQuestionTimeSerializer,
        responses={
            200: OpenApiResponse(description='處理成功'),
            401: OpenApiResponse(description='身分認證失敗'),
        },
        )
    def post(self, request, *args, **kwargs):
        serializer = RegionQuestionTimeSerializer(data=request.data)
        if serializer.is_valid() == False:
            raise ParseError('欄位錯誤')

        lbkey = request.data.get('lbkey')
        query_time = request.data.get('query_time')
        query_time = parse_datetime(query_time)
        query_time = query_time.replace(tzinfo=paris_tz)

        LB_enum = getLBEnum(lbkey)
        if LB_enum == LBEnum.LAND:
            LB_models = land.models
        elif LB_enum == LBEnum.BUILD:
            LB_models = building.models
        else:
            raise ParseError('欄位錯誤')

        summarys = LB_models.Summary.objects.filter(lbkey=lbkey)
        if summarys.exists() == False:
            raise ParseError('查無地建號')
        summary_id = summarys[0]

        owner_qs = summary_id.ownerregnosummary_set.all()
        right_qs = summary_id.rightregnosummary_set.all()

        owner_bulk_update = []
        right_bulk_update = []
        for owner in owner_qs:
            if owner.remove_time == None:
                continue
            owner_time = owner.remove_time.replace(microsecond=0)
            if query_time == owner_time:
                owner.remove_time = None
                owner.is_valid_type = IsvalidTypeEnum.VALID
                owner_bulk_update.append(owner)

        for right in right_qs:
            if right.remove_time == None:
                continue
            right_time = right.remove_time.replace(microsecond=0)
            if query_time == right_time:
                right.remove_time = None
                right.is_valid_type = IsvalidTypeEnum.VALID
                right_bulk_update.append(right)
        
        if owner_bulk_update == [] and right_bulk_update == []:
            raise ParseError(f'{lbkey} 移除時間比對失敗')

        LB_models.OwnerRegnoSummary.objects.bulk_update(owner_bulk_update, fields=['remove_time', 'is_valid_type'])
        LB_models.RightRegnoSummary.objects.bulk_update(right_bulk_update, fields=['remove_time', 'is_valid_type'])

        regno_log_qs = LB_models.RegnoLog.objects.filter(summary_id=summary_id, state=TaskTypeEnum.ABNORMAL_PARSER)
        for regno_log in regno_log_qs:
            regno_log.state = TaskTypeEnum.INIT
            create_lbor([regno_log], LB_enum)
        return Response({lbkey: 'OK'})


class RegionList(APIView):
    '''
    所他權清單

    使用者驗證：
    
    headers = {'Authorization': 'token 22a7bfe39c228d32*****11b2f5f24218e6d65ab',}
    '''
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='所他權清單',
        description='取最後查詢的所他權清單',
        request=RegionListSerializer,
        responses={
            200: OpenApiResponse(description='處理成功'),
            401: OpenApiResponse(description='身分認證失敗'),
        },
        )
    def post(self, request, *args, **kwargs):
        msg = {}
        lbkeys = request.data['lbkey'].split(',')
        is_all = request.data['is_all']

        for lbkey in lbkeys:
            LB_enum = getLBEnum(lbkey)
            if LB_enum == LBEnum.LAND:
                LB_models = land.models
            elif LB_enum == LBEnum.BUILD:
                LB_models = building.models
            else:
                msg[lbkey] = '土建類別錯誤'
                continue
            summary_qs = LB_models.Summary.objects.filter(lbkey=lbkey)
            if summary_qs.exists() == False:
                msg[lbkey] = '無此地建號'
                continue
            summary_id = summary_qs[0]

            kwarg = {}
            if is_all == False:
                kwarg = {'is_valid_type': IsvalidTypeEnum.VALID}

            owner_qs = summary_id.ownerregnosummary_set.filter(**kwarg).values('regno', 'name', 'is_valid_type')
            right_qs = summary_id.rightregnosummary_set.filter(**kwarg).values('regno', 'name', 'is_valid_type')
            owner_dict = {}
            right_dict = {}

            for owner in owner_qs:
                owner_dict[owner['regno']] = {'name': owner['name'], 'is_valid_type': owner['is_valid_type']}
            for right in right_qs:
                right_dict[right['regno']] = {'name': right['name'], 'is_valid_type': right['is_valid_type']}

            msg[lbkey] = {"lbkey": lbkey, "owners": owner_dict, "rights": right_dict}
        return Response(msg)


class CreateTpTaskView(APIView):
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def make_obj_df(self, pool_qs):
        pool_dict = []
        if pool_qs:
            pool_dict = [{'lbkey': x.lbkey, 'o_regno_str': x.o_regno_str, 'r_regno_str': x.r_regno_str, 'is_mark_only': x.is_mark_only, 'priority': x.priority, 'inpool_obj': x, 'system': x.system} for x in pool_qs]
        return pool_dict

    def apply_cat_colunm(self, data):
        obj = None
        if data['inpool_obj_x'] != 0:
            obj = data['inpool_obj_x']
        elif data['o_regno_str_y'] != 0:
            obj = data['inpool_obj_y']
        else:
            pass
        return obj

    def apply_set_regno(self, data, reg_type):
        result = None
        if reg_type == 'o':
            or_reg = data['o_regno_str']
            if isinstance(or_reg, str) == True:
                or_reg = sorted(list(set(or_reg.split(','))))
                result = ','.join(x for x in or_reg if x)
        else:
            or_reg = data['r_regno_str']
            if isinstance(or_reg, str) == True:
                or_reg = sorted(list(set(or_reg.split(','))))
                result = ','.join(x for x in or_reg if x)

        return result

    def apply_check_task_type(self, data):
        # both = 重複任務 x=input_task y=inpool_task

        data['is_mark_only'] = False
        # 找到重複任務
        if data['_merge'] == 'both':
            
            #  輸入任務=true 任務池=true 判斷均為只調標示
            if data['is_mark_only_y'] == True and data['is_mark_only_x'] == True:
                # print('both: m_o_X = T m_o_Y = True')
                if data['o_regno_str_x'] or data['r_regno_str_x'] or data['o_regno_str_y'] or data['r_regno_str_y']:
                    data['is_mark_only'] = False
                else:
                    data['o_regno_str_x'] = ''
                    data['r_regno_str_x'] = ''
                    data['is_mark_only'] = True

            # 輸入任務=true 任務池=false 接任務池所他判斷
            elif data['is_mark_only_x'] == True and data['is_mark_only_y'] == False:
                # print('both: m_o_X = T m_o_Y = F')
                # 如果任務池有所他 ==> 合併為特定登序
                if data['o_regno_str_y'] or data['r_regno_str_y']:
                    data['is_mark_only'] = False
                if len(data['o_regno_str_x']) >= 4 or len(data['r_regno_str_x']) >= 7:
                    data['is_mark_only'] = False

            # 輸入=false 任務池=true 接輸入任務所他判斷
            elif data['is_mark_only_x'] == False and data['is_mark_only_y'] == True:
                # print('both: m_o_X = F m_o_Y = T')
                # 如果輸入任務帶登序 ==> 合併為特定登序
                if len(data['o_regno_str_x']) >=4 or len(data['r_regno_str_x']) >= 7:
                    data['is_mark_only'] = False
                else:
                    data['is_mark_only'] = True
        # 沒有重複任務
        elif data['_merge'] == 'left_only':
            # 如果帶登序又下is_mark_only 則合併為特定登序
            if len(data['o_regno_str_x']) >= 4 or len(data['r_regno_str_x']) >= 7:
                data['is_mark_only'] = False
            # 沒帶登序 維持is_mark_only
            else:
                data['is_mark_only'] = True
                data['o_regno_str_x'] = ''
                data['r_regno_str_x'] = ''
                data['o_regno_str_y'] = ''
                data['r_regno_str_y'] = ''

        return data

    def apply_check_priority(self, data):
        if data['_merge'] == 'both':
            # 重複任務 取最高優先度 +1 
            max_priority = max([data['priority_x'], data['priority_y']]) + 1
            return max_priority
        elif data['_merge'] == 'left_only':
            max_priority = max([data['priority_x'], data['priority_y']])
            return max_priority

    def apply_check_lbtype(self, x):
        return getLBEnum(x['lbkey'])

    def apply_df_colunm(self, x):
        non_list = list(set(self.default_df_list) - set(list(x.index)))
        for i in non_list:
            x[i] = None
        return x

    def apply_reg_set(self, col):
        f_col = ''
        if isinstance(col, str):            
            rel = list(set(col.split(',')))
            f_col = ','.join(rel)
        return f_col

    def df_fillna_job(self, df):
        df[['o_regno_str', 'r_regno_str']] = df[['o_regno_str', 'r_regno_str']].fillna('')
        df['system'] = df['system'].fillna(self.d_system)
        df['priority'] = df['priority'].fillna(self.d_priority)
        df[['o_regno_str', 'r_regno_str']] = df.groupby('lbkey')[['o_regno_str', 'r_regno_str']].transform(','.join)
        df['priority'] = df.groupby('lbkey')['priority'].transform(max)
        df['system'] = df.groupby('lbkey')['system'].transform(max)
        df = df.drop_duplicates(subset=['lbkey', 'o_regno_str', 'r_regno_str'], inplace=False, keep='last')
        df = df.reset_index(drop=True)
        df['is_mark_only'] = df['is_mark_only'].fillna(self.d_mark_only)
        df['o_regno_str'] = df['o_regno_str'].apply(self.apply_reg_set)
        df['r_regno_str'] = df['r_regno_str'].apply(self.apply_reg_set)
        return df

    def insert_or_num(self, lbkey_list):
        # 如果
        df = pd.DataFrame([{'lbkey': '', 'owners_num': 0, 'rights_num': 0}], dtype=object)
        # lbkey_list = None # 測試用
        if isinstance(lbkey_list, list) == True:
            qs = list(self.model_set_summary.objects.filter(lbkey__in=lbkey_list).values('lbkey', 'owners_num', 'rights_num'))
            if qs:
                df = pd.DataFrame(qs, dtype=object)
        return df

    def get_or_num(self, df, lbkey):
        owners_num, rights_num = 0, 0
        try:
            df_lbkey = df[df['lbkey'].str.contains(lbkey)]
            if df_lbkey.empty != True:
                owners_num = df_lbkey.head(1).iloc[0]['owners_num']
                rights_num = df_lbkey.head(1).iloc[0]['rights_num']
        except:
            pass
        return owners_num, rights_num

    def check_task_rule(self, owner_str, right_str, mark_only):
        if owner_str and right_str:
            return RuleTypeEnum.BOTH
        elif owner_str and not right_str:
            return RuleTypeEnum.OWNER
        elif not owner_str and right_str:
            return RuleTypeEnum.RIGHT
        elif mark_only:
            return RuleTypeEnum.MARK
        elif not owner_str and not right_str:
            return RuleTypeEnum.BOTH
        else:
            return RuleTypeEnum.APRT

    def process(self, task_data, lbtype):
        user_task_id_list = []
        if task_data:
            if lbtype == 'L':
                self.model_set_task = land.models.TpTaskPool
                self.model_set_summary = land.models.Summary
                self.d_priority = self.env_dict.get('default_priority_L', {}).get('integer')
                self.d_system = self.env_dict.get('default_system_L', {}).get('integer')
                self.d_mark_only = self.env_dict.get('default_mark_only_L', {}).get('integer')
            else:
                self.model_set_task = building.models.TpTaskPool
                self.model_set_summary = building.models.Summary
                self.d_priority = self.env_dict.get('default_priority_B', {}).get('integer')
                self.d_system = self.env_dict.get('default_system_B', {}).get('integer')
                self.d_mark_only = self.env_dict.get('default_mark_only_B', {}).get('integer')

            if self.d_mark_only == 1:
                self.d_mark_only = True
            else:
                self.d_mark_only = False
            lbkey_list = [x.get('lbkey') for x in task_data]
            in_pool_qs = self.model_set_task.objects.filter(lbkey__in=lbkey_list, state=0)
            in_pool_dict = self.make_obj_df(in_pool_qs)

            if not in_pool_qs:
                print('任務池無任務')
                task_df = pd.DataFrame(task_data, dtype=object)

                # 補缺失欄位
                model_col = [x.name for x in self.model_set_task._meta.get_fields()]
                lost_col_list = list(set(model_col) - set(task_df.columns))
                for i in self.remove_colunm_list:
                    if i in lost_col_list:
                        lost_col_list.remove(i)
                for i in lost_col_list:
                    task_df[i] = None
                
                df_res = self.df_fillna_job(df=task_df)
                num_df = self.insert_or_num(df_res['lbkey'].tolist())
                # print(num_df)
                task_dict = df_res.to_dict(orient='records')
                task_entry_list = []
                for task in task_dict:
                    lbkey = task.get('lbkey')
                    owners_num, rights_num = self.get_or_num(num_df, lbkey)
                    task['owners_num'] = owners_num
                    task['rights_num'] = rights_num
                    rule = self.check_task_rule(owner_str=task.get('o_regno_str'), right_str=task.get('r_regno_str'), mark_only=task.get('is_mark_only'))
                    task['rules'] = rule
                    try:
                        del task['lbtype']
                        del task['reg_check']       
                    except:
                        pass             
                    entry = self.model_set_task(**task)
                    task_entry_list.append(entry)

                if task_entry_list:
                    pass
                    self.model_set_task.objects.bulk_create(task_entry_list)

            else:
                print('有重複任務')
                input_df = pd.DataFrame(task_data, dtype=object)
                inpool_df = pd.DataFrame(in_pool_dict, dtype=object)

                # input_df 需要補缺失欄位 system, priority, is_mark_only
                lost_col_list = list(set(inpool_df.columns) - set(input_df.columns))
                for i in lost_col_list:
                    input_df[i] = None

                # 輸入任務去除重複
                input_df = self.df_fillna_job(df=input_df)
                
                # print(f'inpool_df: \n {inpool_df}')
                # print(f'input_df: \n {input_df}')

                # 填滿空值
                df_merge = input_df.merge(inpool_df, how = 'outer', on=['lbkey'], indicator=True) #outer
                df_merge.loc[df_merge['_merge']=='both', ['priority_x', 'priority_y']] = df_merge[df_merge.loc[:, '_merge']=='both'][['priority_x', 'priority_y']].fillna(self.d_priority)
                df_merge[['o_regno_str_x', 'o_regno_str_y', 'r_regno_str_x', 'r_regno_str_y']] = df_merge[['o_regno_str_x', 'o_regno_str_y', 'r_regno_str_x', 'r_regno_str_y']].fillna('') 
                df_merge[['inpool_obj_x', 'inpool_obj_y']] = df_merge[['inpool_obj_x', 'inpool_obj_y']].fillna(0)
                df_merge[['is_mark_only_x', 'is_mark_only_y']] = df_merge[['is_mark_only_x', 'is_mark_only_y']].fillna(self.d_mark_only)

                # 合併標所他
                df_merge = df_merge.apply(self.apply_check_task_type, axis=1)
                df_merge['o_regno_str'] = df_merge['o_regno_str_x'].str.cat(df_merge['o_regno_str_y'], sep=',')
                df_merge['r_regno_str'] = df_merge['r_regno_str_x'].str.cat(df_merge['r_regno_str_y'], sep=',')
                
                # 合併任務 優先度取最高且 +1 系統取最高
                df_merge['priority'] = df_merge.apply(self.apply_check_priority, axis=1)
                df_merge['system'] = df_merge[['system_x', 'system_y']].max(axis=1)
                df_merge['inpool_obj'] = df_merge.apply(self.apply_cat_colunm, axis=1)

                # 刪除不必要欄位
                df_merge = df_merge.drop(['o_regno_str_x', 'o_regno_str_y', 'r_regno_str_x', 'r_regno_str_y', 'priority_x', 'priority_y', 'inpool_obj_x', 'inpool_obj_y', 'is_mark_only_x', 'is_mark_only_y', 'system_x', 'system_y'], axis=1)
                df_merge['o_regno_str'] = df_merge.apply(self.apply_set_regno, axis=1, args=('o', ))
                df_merge['r_regno_str'] = df_merge.apply(self.apply_set_regno, axis=1, args=('r', ))

                # 分割任務: 寫入 or 更新
                update_df = df_merge[df_merge['_merge'] == 'both']
                create_df = df_merge[df_merge['_merge'] == 'left_only']

                # print(f'update_df: \n {update_df}')
                # print('==================================')
                # print(f'create_df: \n {create_df}')

                if update_df.empty != True:
                    num_df_u = self.insert_or_num(update_df['lbkey'].tolist())
                    update_dict = update_df.to_dict('records')
                    update_list = []
                    for i in update_dict:
                        owners_num, rights_num = self.get_or_num(num_df_u, i.get('lbkey'))
                        rule = self.check_task_rule(owner_str=i.get('o_regno_str'), right_str=i.get('r_regno_str'), mark_only=i.get('is_mark_only'))
                        inpool_obj = i.get('inpool_obj')
                        inpool_obj.o_regno_str = i.get('o_regno_str')
                        inpool_obj.r_regno_str = i.get('r_regno_str')
                        inpool_obj.rules = rule
                        inpool_obj.owners_num = owners_num
                        inpool_obj.rights_num = rights_num                        
                        inpool_obj.priority = i.get('priority')
                        inpool_obj.system = i.get('system')
                        inpool_obj.is_mark_only = i.get('is_mark_only')
                        user_task_id_list.append(inpool_obj.id)
                        update_list.append(inpool_obj)        
                    if update_list:
                        self.model_set_task.objects.bulk_update(update_list, fields=['owners_num', 'rights_num', 'o_regno_str', 'r_regno_str',  'priority', 'system', 'is_mark_only', 'rules'], batch_size=1000)

                if create_df.empty != True:
                    num_df_c = self.insert_or_num(create_df['lbkey'].tolist())
                    create_dict = create_df.to_dict('records')
                    create_list = []
                    for j in create_dict:
                        owners_num, rights_num = self.get_or_num(num_df_c, j.get('lbkey'))
                        rule = self.check_task_rule(owner_str=j.get('o_regno_str'), right_str=j.get('r_regno_str'), mark_only=j.get('is_mark_only'))
                        del j['_merge']
                        del j['inpool_obj']
                        del j['lbtype']
                        del j['reg_check']

                        j['owners_num'] = owners_num
                        j['rights_num'] = rights_num
                        create_list.append(self.model_set_task(**j))
                    if create_list:
                        pass
                        over_create_list = self.model_set_task.objects.bulk_create(create_list)
                        user_task_id_list.extend([x.id for x in over_create_list if over_create_list])
        return user_task_id_list

    def get_system_env(self, col_name):
        res = {}
        def_bac = dict_env()
        if col_name:
            for i in col_name:
                try:                  
                    qs = SystemConfig.objects.get(env=i)
                    res[i] = {'env':qs.env, 'string':qs.string, 'integer':qs.integer, 'datetime':qs.datetime, 'json': qs.json, 'remark': qs.remark}
                except:
                    res[i] = def_bac.get(i)
        return res

    def parting_task(self, lbkey_list, lb_model):
        invalid_lbkey_list = []
        if lbkey_list:
            lbkeys = [x.get('lbkey') for x  in lbkey_list]
            summary_qs = lb_model.objects.filter(lbkey__in=lbkeys)
            summary_lbkeys = [x.lbkey for x in summary_qs]
            invalid_lbkey_list = list(set(lbkeys) - set(summary_lbkeys))
        return invalid_lbkey_list

    def check_lb_reg(self, lb_df):
        valid_reg_df, invalid_reg_df = pd.DataFrame([]), pd.DataFrame([])
        if lb_df.empty != True:
            # 新增檢查段小段欄位
            lb_df['reg_check'] = lb_df['lbkey'].str.rsplit('_', 1).str.get(0)
            
            # 切割段
            car_split = lb_df['lbkey'].str.rsplit('_')
            city = list(set(car_split.str.get(0).to_list()))
            area = list(set(car_split.str.get(1).to_list()))
            region = list(set(car_split.str.get(2).to_list()))

            kargs = {
                'area_code_table_id__city_code_table_id__city_code__in': city,
                'area_code_table_id__area_code__in': area,
                'region_code__in': region,
                'is_valid': True
            }
            region_list_qs = RegionCodeTable.objects.filter(**kargs)
            valid_region_list = []

            if region_list_qs:
                for i in region_list_qs:
                    city = i.area_code_table_id.city_code_table_id.city_code
                    area = i.area_code_table_id.area_code
                    region = i.region_code
                    valid_region_list.append(f'{city}_{area}_{region}')

            valid_reg_df = lb_df[lb_df['reg_check'].isin(valid_region_list)]
            invalid_reg_df = lb_df[~lb_df['reg_check'].isin(valid_region_list)]
            # print(valid_reg_df)
            # print('===================================')
            # print(invalid_reg_df)
        return valid_reg_df, invalid_reg_df

    def check_lb_db(self, reg_lb_df, model_set):
        LB_dict_indb, LB_dict_notdb = pd.DataFrame([]), pd.DataFrame([])
        if reg_lb_df.empty != True:
            LB_qs = model_set.objects.filter(lbkey__in=reg_lb_df['lbkey'].tolist())
            # 後面一起刪
            # reg_lb_df = reg_lb_df.drop(['lbtype', 'reg_check'], axis=1)
            LB_dict_indb = reg_lb_df[reg_lb_df['lbkey'].isin([x.lbkey for x in LB_qs])]#.to_dict(orient='records')
            LB_dict_notdb = reg_lb_df[~reg_lb_df['lbkey'].isin([x.lbkey for x in LB_qs])]#.to_dict(orient='records')
        return LB_dict_indb, LB_dict_notdb

    # 加入檢查段小段
    def check_lb_valid(self, data):
        # 順便填缺失欄位
        input_df = pd.DataFrame.from_dict(data, orient='columns', dtype=object)
        input_df = input_df.apply(self.apply_df_colunm, axis=1)
        # 1 -> 檢查格式 且分類土建
        input_df['lbtype'] = input_df.apply(self.apply_check_lbtype, axis=1)

        N_df = input_df[input_df['lbtype']==0] # 格式不正確 lbeky
        illegal_list = N_df.to_dict(orient='records')

        L_df = input_df[input_df['lbtype']==1]
        B_df = input_df[input_df['lbtype']==2]


        # 2 -> 檢查段小段
        # 失效部份觸發lbor更新段小段
        L_reg_valid, L_reg_invalid = self.check_lb_reg(lb_df=L_df)
        B_reg_valid, B_reg_invalid = self.check_lb_reg(lb_df=B_df)

        # 3 -> 檢查DB
        # 失效部份觸發lbor查詢
        L_indb, L_notdb = self.check_lb_db(reg_lb_df=L_reg_valid, model_set=land.models.Summary)
        B_indb, B_notdb = self.check_lb_db(reg_lb_df=B_reg_valid, model_set=building.models.Summary)
        # print(f'土地 段小段有效 \n {L_reg_valid}')
        # print(f'土地 查無段小段 \n {L_reg_invalid}')
        # print('========================================')
        # print(f'土地 資料庫有 \n {L_indb}')
        # print(f'土地 資料庫沒有 \n {L_notdb}')
        # print('========================================')
        # print(f'不合法清單 \n {illegal_list}')
        reg_valid_L = L_reg_valid.to_dict(orient='records') # 段小段有效 土
        reg_invalid_L = L_reg_invalid.to_dict(orient='records') # 段小段無效 土

        reg_valid_B = B_reg_valid.to_dict(orient='records') # 段小段有效 建
        reg_invalid_B = B_reg_invalid.to_dict(orient='records') # 段小段無效 建

        in_db_L = L_indb.to_dict(orient='records')
        notin_db_L = L_notdb.to_dict(orient='records')

        in_db_B = B_indb.to_dict(orient='records')
        notin_db_B = B_notdb.to_dict(orient='records')
        return reg_valid_L, reg_invalid_L, reg_valid_B, reg_invalid_B, in_db_L, notin_db_L, in_db_B, notin_db_B, illegal_list

    def get_or_num_summary(self, task_list):
        lbkey_list_L = [x.get('lbkey') for x in task_list if getLBEnum(x.get('lbkey'))==LBEnum.LAND]
        lbkey_list_B = [x.get('lbkey') for x in task_list if getLBEnum(x.get('lbkey'))==LBEnum.BUILD]

        summary_obj_L = land.models.Summary.objects.filter(lbkey__in=lbkey_list_L)
        summary_obj_B = building.models.Summary.objects.filter(lbkey__in=lbkey_list_B)
        big_dict = {}
        for i in summary_obj_L:
            
            print(i.owners_num)

    @extend_schema(
        summary = '下謄本任務',
        description = '此API限定用程式下任務, 請看README.md',
        request = TpTaskSerializer,        
        responses = {
            200: OpenApiResponse(description='處理成功'),
            401: OpenApiResponse(description='身分認證失敗'),
            },
        )
    def post(self, request, *args, **kwargs):
        result = {}
        debug_mode = request.POST.get('debug')
        self.user_obj = request.user

        if debug_mode in [True, 'True', 1, 'true', '1']:
            print('debug mode on')
            return Response(result)

        request_dict = request.data
        serializer = TpTaskSerializer(data=request_dict)
        if serializer.is_valid() == False:
            # result['msg'] = serializer.errors
            raise ParseError(serializer.errors)

        else:
            task_data = request_dict.get('task_data')
            self.forcibly = request_dict.get('forcibly')
            if not isinstance(task_data, list):
                raise ParseError('task_data 須為list')

            elif task_data:
                self.remove_colunm_list = ['id', 'schedule', 'create_time', 'account', 'extra', 'state', 'rules', 'complete_time', 'take_time']
                self.default_df_list = ['lbkey', 'o_regno_str', 'r_regno_str', 'priority', 'system', 'is_mark_only']
                reg_valid_L, reg_invalid_L, reg_valid_B, reg_invalid_B, in_db_L, notin_db_L, in_db_B, notin_db_B, illegal_list = self.check_lb_valid(task_data)
                self.env_dict = self.get_system_env(col_name=['default_system_L', 'default_system_B', 'default_priority_L', 'default_priority_B', 'default_mark_only_L', 'default_mark_only_B'])
                self.or_num_dict = self.get_or_num_summary(task_list=task_data)
                task_id_l = []
                task_id_b = []
                # 不存在的段小段要更新    不存在的lbkey要觸發lbor查詢
                if self.forcibly == True:
                    print('強制調閱')
                    # print(reg_valid_L)
                    # print(notin_db_L)
                    task_id_l = self.process(reg_valid_L + reg_invalid_L + in_db_L + notin_db_L, lbtype='L')
                    task_id_b = self.process(reg_valid_B + reg_invalid_B + in_db_B + notin_db_B, lbtype='B')
                    # result['reg_invalid_L'] = reg_invalid_L
                    # result['reg_invalid_B'] = reg_invalid_B
                    # result['notin_db_L'] = notin_db_L
                    # result['notin_db_B'] = notin_db_B
                    # result['illegal_lbkey'] = illegal_list

                else:
                    print('非強制調閱')
                    if reg_invalid_L or reg_invalid_B or notin_db_L or notin_db_B or illegal_list:
                        result['msg'] = 'invalid lbkey in task'
                        result['reg_invalid_L'] = reg_invalid_L
                        result['reg_invalid_B'] = reg_invalid_B
                        result['notin_db_L'] = notin_db_L
                        result['notin_db_B'] = notin_db_B
                        result['illegal_lbkey'] = illegal_list
                        # 如果要下合法任務就打開下面
                        # task_id_l = self.process(reg_valid_L, lbtype='L')
                        # task_id_b = self.process(reg_valid_B, lbtype='B')
                        raise ParseError(result)
                    else:
                        task_id_l = self.process(in_db_L, lbtype='L')
                        task_id_b = self.process(in_db_B, lbtype='B')
                        return Response(result)

                if task_id_l or task_id_b:
                    # print(task_id_l, task_id_b)
                    kw = {'lbor_tp_type': LborTpTypeEnum.TP, 'task_id_l': task_id_l, 'task_id_b': task_id_b, 'user': self.user_obj}
                    UserActionLog.objects.create(**kw)

        return Response(result)


class FeedbackTpView(APIView):
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='回傳謄本 log',
        description='some commit',
        request=FeedbackTplogSerializer,
        responses={
            200: OpenApiResponse(description='處理成功'),
            401: OpenApiResponse(description='身分認證失敗'),
            },
        )
    def post(self, request, *args, **kwargs):
        result = {'status': 'NG', 'msg': ''}
        self.user_obj = request.user
        # print(request.data)

        if type(request.data) == list:
            serializer = FeedbackTplogSerializer(data=request.data, many=True)
        else:
            serializer = FeedbackTplogSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            result['status'] = 'OK'
        return Response(result)


class CreateLborTaskView(APIView):
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    '''
    統一傳遞df欄位=['lbkey', 'priority', 'owners_num', 'rights_num', 'rules']
    '''
    def get_system_env(self, col_name):
        res = {}
        def_bac = dict_env()
        if col_name:
            for i in col_name:
                try:                  
                    qs = SystemConfig.objects.get(env=i)
                    res[i] = {'env':qs.env, 'string':qs.string, 'integer':qs.integer, 'datetime':qs.datetime, 'json': qs.json, 'remark': qs.remark}
                except:
                    res[i] = def_bac.get(i)
        return res

    def check_summary(self, lbkey_list, summary_model_set):
        qs_check = []
        if lbkey_list:
            qs_check = list(summary_model_set.objects.filter(lbkey__in=lbkey_list).values('lbkey', 'owners_num', 'rights_num'))
            if not qs_check:
                qs_check = [{'lbkey': None, 'owners_num': None, 'rights_num': None}]
        return qs_check

    def _clean_apply(self, df):
        df['priority'] = max(df['priority_x'], df['priority_y'])
        if df['rules_x'] == df['rules_y']: 
            df['rules'] = df['rules_x']
        else:
            df['rules'] = RuleTypeEnum.BOTH
        df = df.drop(['priority_x', 'priority_y', 'rules_x', 'rules_y'])
        return df

    def _input_clean_apply(self, df):
        df['owners_num'] = max(df['owners_num_x'], df['owners_num_y'])
        df['rights_num'] = max(df['rights_num_x'], df['rights_num_y'])
        df = df.drop(['owners_num_x', 'owners_num_y', 'rights_num_x', 'rights_num_y', 'inpool_obj'])
        df[['owners_num', 'rights_num']] = df[['owners_num', 'rights_num']].fillna(0)
        return df

    def dist_task(self, lbkey_list, forcibly, priority, rules, summary_model_set, pool_model_set):
        result_msg = {'msg': '', 'invalid_task': []}
        user_task_id = []
        if lbkey_list:
            qs_inpool = pool_model_set.objects.filter(lbkey__in=lbkey_list, state=0)

            if not qs_inpool:
                # print('任務池內無任務')
                qs_check = self.check_summary(lbkey_list, summary_model_set)
                valid_df = pd.DataFrame(qs_check, dtype=object)
                # print(valid_df)
                input_df = pd.DataFrame({'lbkey': lbkey_list, 'priority': priority, 'rules': rules}, dtype=object, columns=['lbkey'])

                merge_task = input_df.merge(valid_df, how='left', on=['lbkey'], indicator=True)
                merge_task[['owners_num', 'rights_num']] = merge_task[['owners_num', 'rights_num']].fillna(0)
                create_df = merge_task[merge_task['_merge'] == 'both'].drop(['_merge'], axis=1)
                invalid_df = merge_task[merge_task['_merge'] == 'left_only'].drop(['_merge'], axis=1)
                create_df['priority'] = priority
                invalid_df['priority'] = priority
                create_list = create_df.to_dict(orient='records')
                invalid_list = invalid_df.to_dict(orient='records')

                if forcibly == False:
                    if invalid_df.empty != True:
                        result_msg['msg'] = 'ok'
                        result_msg['invalid_task'] = invalid_list
                else:
                    if create_list or invalid_list:
                        create_entry = [pool_model_set(**x) for x in create_list + invalid_list]
                        task_obj = pool_model_set.objects.bulk_create(create_entry)
                        result_msg['msg'] = 'ok'
                        result_msg['invalid_task'] = invalid_list
                        user_task_id.extend([x.id for x in task_obj if task_obj])

            else:
                # print('有任務')
                pool_dict = [{'lbkey': x.lbkey, 'priority': x.priority, 'owners_num': x.owners_num, 'rights_num': x.rights_num, 'rules': x.rules, 'inpool_obj': x} for x in qs_inpool]
                inpool_df = pd.DataFrame(pool_dict, dtype=object)
                input_df = pd.DataFrame({'lbkey': lbkey_list, 'priority': priority, 'rules': rules}, dtype=object)
                # 合併池子的任務
                input_merge = input_df.merge(inpool_df, how='left', on=['lbkey'], indicator=True)
                input_clean_df = input_merge.apply(self._clean_apply, axis=1)
                update_df = input_clean_df[input_clean_df['_merge'] == 'both']
                # make update df end=================================

                # 檢查summary 與輸入任務合併 回填所他人數
                insert_df = input_clean_df[input_clean_df['_merge'] == 'left_only'].drop(['_merge'], axis=1)
                qs_check = self.check_summary(insert_df['lbkey'].tolist(), summary_model_set)
                if qs_check:
                    summary_df = pd.DataFrame(qs_check, dtype=object)
                else:
                    qs_check = [{'lbkey': None, 'owners_num': 0, 'rights_num': 0}]
                    summary_df = pd.DataFrame(qs_check, dtype=object)
                # 合併輸入任務
                summary_merge_df = insert_df.merge(summary_df, how='left', on=['lbkey'], indicator=True)
                summary_merge_df = summary_merge_df.apply(self._input_clean_apply, axis=1)

                create_df = summary_merge_df[summary_merge_df['_merge'] == 'both'].drop(['_merge'], axis=1)
                illegal_df = summary_merge_df[summary_merge_df['_merge'] == 'left_only'].drop(['_merge'], axis=1)
                create_list = create_df.to_dict(orient='records')
                illegal_list = illegal_df.to_dict(orient='records')
                update_list = update_df.to_dict(orient='records')

                if forcibly == False:
                    if illegal_df.empty != True:
                        result_msg['msg'] = 'ok'
                        result_msg['invalid_task'] = illegal_list
                else:
                    if create_list or illegal_list:
                        create_entry = [pool_model_set(**x) for x in create_list + illegal_list]
                        task_obj = pool_model_set.objects.bulk_create(create_entry)
                        user_task_id.extend([x.id for x in task_obj if task_obj])

                        result_msg['msg'] = 'ok'
                        result_msg['invalid_task'] = illegal_list

                if update_list:
                    obj_list = []
                    for i in update_list:
                        update_obj = i.get('inpool_obj')
                        update_obj.owners_num = i.get('owners_num')
                        update_obj.rights_num = i.get('rights_num')
                        update_obj.priority = i.get('priority')
                        update_obj.rules = i.get('rules')
                        obj_list.append(update_obj)
                        user_task_id.append(update_obj.id)
                    pool_model_set.objects.bulk_update(obj_list, fields=['owners_num', 'rights_num', 'priority', 'rules'], batch_size=500)
                    result_msg['msg'] = 'ok'
                    result_msg['invalid_task'] = illegal_list

        return result_msg, user_task_id


    @extend_schema(
        summary='建立lbor task',
        description='詳細使用方法請參考README文件',
        request=LborTaskSerializer,
        responses={
            200: OpenApiResponse(description='處理成功'),
            401: OpenApiResponse(description='身分認證失敗'),
            },
        )
    def post(self, request, *args, **kwargs):
        result = {}
        self.user_obj = request.user
        # print(request.data)

        if type(request.data) == list:
            serializer = LborTaskSerializer(data=request.data, many=True)
        else:
            serializer = LborTaskSerializer(data=request.data)

        if serializer.is_valid() == False:
            raise ParseError(serializer.errors) # serializer.errors
        else:
            self.env_dict = self.get_system_env(col_name=['default_system_L', 'default_system_B', 'default_priority_L', 'default_priority_B', 'default_mark_only_L', 'default_mark_only_B'])
            # print(self.env_dict)
            if request.data:
                # 一個迴圈為一包任務 任務區分土建
                illegal_task_N = []
                illegal_task_L = []
                illegal_task_B = []
                task_L = []
                task_B = []
                for i in request.data:
                    forcibly = i.get('forcibly')
                    priority = i.get('priority')
                    if not priority:
                        priority_L = self.env_dict.get('default_priority_L', {}).get('integer')
                        priority_B = self.env_dict.get('default_priority_B', {}).get('integer')
                    else:
                        priority_L, priority_B = priority, priority

                    rules = i.get('rules')
                    lbkey_list = i.get('lbkey_list')
                    if not lbkey_list:
                        continue

                    l_task = []
                    b_task = []                    
                    for k in list(set(lbkey_list)):
                        if getLBEnum(k) == LBEnum.LAND:
                            l_task.append(k)
                        elif getLBEnum(k) == LBEnum.BUILD:
                            b_task.append(k)
                        else:
                            illegal_task_N.append({'lbkey': k, 'priority': priority, 'rules': rules, 'forcibly': forcibly})

                    # 檢查且區分土建
                    res_L, task_id_L = self.dist_task(l_task, forcibly, priority_L, rules, land.models.Summary, land.models.LborTaskPool)
                    res_B, task_id_B = self.dist_task(b_task, forcibly, priority_B, rules, building.models.Summary, building.models.LborTaskPool)
                    illegal_task_L.extend(res_L.get('invalid_task'))
                    illegal_task_B.extend(res_B.get('invalid_task'))
                    task_L.extend(task_id_L)
                    task_B.extend(task_id_B)

                if task_L or task_B:
                    kw = {'lbor_tp_type': LborTpTypeEnum.LBOR, 'task_id_l': task_L, 'task_id_b': task_B, 'user': self.user_obj}
                    UserActionLog.objects.create(**kw)

                # result['status'] = 'ok'
                result['illegal_task_N'] = illegal_task_N
                result['illegal_task_L'] = illegal_task_L
                result['illegal_task_B'] = illegal_task_B

        return Response(result)


class GetTpTaskView(APIView):
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='取 謄本任務',
        description='''規則(rule)不填就是不過濾<br>gte大於等於, lte小於等於''',
        request=GetTpTaskSerializer,
        responses={
            200: OpenApiResponse(description='處理成功'),
            400: OpenApiResponse(description='參數格式錯誤'),
            401: OpenApiResponse(description='身分認證失敗'),
            },
        )
    def post(self, request, *args, **kwargs):
        serializer = GetTpTaskSerializer(data=request.data)
        if serializer.is_valid() == False:
            raise ParseError('欄位錯誤')

        city = serializer.data.get('city', 'A')
        count = serializer.data.get('count', 1)
        rule = serializer.data.get('rule', {})
        system = serializer.data.get('query_system', 2)
        lbtype = serializer.data.get('lbtype', 'L')
        debug = serializer.data.get('debug', False)

        if lbtype == 'L':
            LB_models = land.models
        elif lbtype == 'B':
            LB_models = building.models
        else:
            raise ParseError('lbtype error')

        query_system = QuerySystemEnum(system)
        task_qs = LB_models.TpTaskPool.objects.filter(lbkey__startswith=city, system=query_system, **rule).order_by('priority')[:count]

        # 為了迅速的改變狀態
        now = timezone.now()
        for task in task_qs:
            task.state = TaskTypeEnum.PROCESSING
            task.take_time = now
        
        if debug == False:
            LB_models.TpTaskPool.objects.bulk_update(task_qs, fields=['state', 'take_time'])

        task_pool = {}
        # 有特定登序的話 規則要部份查
        for task in task_qs:
            task_pool[task.lbkey] = {
                'owner_num': task.owners_num,
                'right_num': task.rights_num,
                'owner_specify': task.o_regno_str,
                'right_specify': task.r_regno_str,
                'rules': task.rules,
                'task_id': task.id,
                'priority': task.priority}
        return JsonResponse(task_pool)


class GetLborTaskView(APIView):
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='取 列表任務',
        description='''規則(rule, exclude)不填就是不過濾<br>gte大於等於, lte小於等於''',
        request=GetLborTaskSerializer,
        responses={
            200: OpenApiResponse(description='處理成功'),
            401: OpenApiResponse(description='身分認證失敗'),
            },
        )
    def post(self, request, *args, **kwargs):
        serializer = GetLborTaskSerializer(data=request.data)
        if serializer.is_valid() == False:
            raise ParseError('欄位錯誤')

        count = serializer.data.get('count', 20)
        city = serializer.data.get('city', 'A')
        lbtype = serializer.data.get('lbtype', 'L')
        debug = serializer.data.get('debug', False)
        rule = serializer.data.get('rule', {})
        exclude = serializer.data.get('exclude', {})

        if lbtype == 'L':
            LB_models = land.models
        elif lbtype == 'B':
            LB_models = building.models
        else:
            raise ParseError('lbtype error')

        task_qs = LB_models.LborTaskPool.objects.filter(
            lbkey__startswith=city,
            **rule
            )
        if exclude:
            task_qs.exclude(**exclude)
        task_qs = task_qs.order_by('priority')[:count]

        now = timezone.now()
        for task in task_qs:
            task.state = TaskTypeEnum.PROCESSING
            task.take_time = now

        if debug == False:
            LB_models.LborTaskPool.objects.bulk_update(task_qs, fields=['state', 'take_time'])

        task_pool = {}
        for task in task_qs:
            task_pool[task.lbkey] = {
                'owner_num': task.owners_num,
                'right_num': task.rights_num,
                'rules': task.rules,
                'task_id': task.id,
                'priority': task.priority}
        return JsonResponse(task_pool)


class FeedbackLborErrorView(APIView):
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='回傳錯誤結果',
        description='some commit',
        request=FeedbackLborErrorSerializer,
        responses={
            200: OpenApiResponse(description='處理成功'),
            401: OpenApiResponse(description='身分認證失敗'),
            },
        )
    def post(self, request, *args, **kwargs):
        if type(request.data) == list:
            serializer = FeedbackLborErrorSerializer(data=request.data, many=True)
        else:
            serializer = FeedbackLborErrorSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
        else:
            raise ParseError(serializer.errors)
        return Response({})


class FeedbackTpErrorView(APIView):
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='回傳錯誤結果',
        description='輸入地建號，用來判斷土地建物<br>任務id<br>錯誤訊息<br>狀態查詢中與待查詢的任務，會轉換成異常',
        request=FeedbackTpErrorSerializer,
        responses={
            200: OpenApiResponse(description='處理成功'),
            401: OpenApiResponse(description='身分認證失敗'),
            },
        )
    def post(self, request, *args, **kwargs):
        if type(request.data) == list:
            serializer = FeedbackTpErrorSerializer(data=request.data, many=True)
        else:
            serializer = FeedbackTpErrorSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
        else:
            raise ParseError(serializer.errors)
        return Response({})


class GenerateTaskView(APIView):
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def clean_input(self, input_data, colunm_name, table_name, msg=''):
        if input_data:
            if isinstance(input_data, str) == True:
                if input_data.find(',') != -1:
                    # 逗點間隔為條件
                    q1 = input_data.replace(' ', '').replace('　', '').split(',')[0]
                    q2 = input_data.replace(' ', '').replace('　', '').split(',')[1]
                    # print(q1, q2)
                    if q1 in ['*', '＊']:
                        pass
                    else:
                        self.base_query[f'{colunm_name}__gte'] = q1

                    if q2 in ['*', '＊']:
                        pass
                    else:
                        self.base_query[f'{colunm_name}__lte'] = q2
                else:
                    # 沒逗點間隔為CAR, 計畫區
                    self.base_query[f'{colunm_name}__startswith'] = input_data


            elif isinstance(input_data, datetime) == True:
                if msg == 'start':
                    self.base_query[f'{colunm_name}__gte'] = input_data
                else:
                    self.base_query[f'{colunm_name}__lte'] = input_data

    def clean_vp(self, data):
        v1, v2 = None, None
        if isinstance(data, str) == True:
            if data.find(',') != -1:
                # 逗點間隔為條件
                v1 = data.replace(' ', '').replace('　', '').split(',')[0]
                v2 = data.replace(' ', '').replace('　', '').split(',')[1]
                # print(q1, q2)
        return v1, v2

    @query_debugger
    def query(self, kw):
        qs = land.models.Summary.objects.filter(**kw)
        q_list = []
        try:
            v1 = int(self.vp_price_min)
            q_list.append(Q(aveg__gte=v1))
        except:
            pass
        try:
            v2 = int(self.vp_price_max)
            q_list.append(Q(aveg__lte=v2))
        except:
            pass
        # print(q_list)
        if q_list:
            qs = qs.annotate(aveg=ExpressionWrapper((F(f'{self.pri_summ}__notice_value') * F(f'{self.pri_summ}__notice_price')), output_field=FloatField())).filter(functools.reduce(operator.and_, q_list))

        # print(qs)
        # print(len(qs))
        return [x.lbkey for x in qs]

    @extend_schema(
        summary='產製任務',
        description='some commit',
        request=GenerateLborTaskSerializer,
        responses={
            200: OpenApiResponse(description='處理成功'),
            401: OpenApiResponse(description='身分認證失敗'),
            },
        )
    def post(self, request, *args, **kwargs):
        result_msg = {'status':200, 'msg': ''}
        self.pro_summ = 'propertytypesummary'
        self.pri_summ = 'pricesummary'
        self.oth_summ = 'othersummary'
        self.urb_summ = 'urbanplanssummary'
        serializer = GenerateLborTaskSerializer(data=request.data)
        if serializer.is_valid() == False:
            print(serializer.errors)
            result_msg['msg'] = serializer.errors
            raise ParseError(result_msg)
        else:
            self.base_query = {}
            # 文字條件
            c_a_r = self.clean_input(request.data.get('CAR'), colunm_name='lbkey', table_name='')
            development = self.clean_input(request.data.get('development'), colunm_name=f'{self.urb_summ}__developement',  table_name='')
            use_zone = self.clean_input(request.data.get('use_zone'), colunm_name=f'{self.oth_summ}__use_zone',  table_name='')
            
            # 時間條件
            time_start = self.clean_input(time_proV2(request.data.get('time_start')), colunm_name='query_time', table_name='', msg='start')
            time_end = self.clean_input(time_proV2(request.data.get('time_end')), colunm_name='query_time', table_name='', msg='end')
            
            # 數字條件
            owners_num = self.clean_input(request.data.get('owners_num'), colunm_name='owners_num', table_name='')
            rights_num = self.clean_input(request.data.get('rights_num'), colunm_name='rights_num', table_name='')
            building_num = self.clean_input(request.data.get('building_num'), colunm_name=f'{self.pro_summ}__building_num', table_name='')
            
            self.vp_price_min, self.vp_price_max = self.clean_vp(request.data.get('vp_price'))
            # vp = self.clean_input(request.data.get('vp_price'), colunm_name=f'{self.pri_summ}__o_private_num', table_name=self.pro_summ)

            o_private = self.clean_input(request.data.get('o_private'), colunm_name=f'{self.pro_summ}__o_private_num', table_name=self.pro_summ)
            o_rental = self.clean_input(request.data.get('o_rental'), colunm_name=f'{self.pro_summ}__o_rental_num', table_name=self.pro_summ)
            o_goverment = self.clean_input(request.data.get('o_goverment'), colunm_name=f'{self.pro_summ}__o_goverment_num', table_name=self.pro_summ)
            o_company = self.clean_input(request.data.get('o_company'), colunm_name=f'{self.pro_summ}__o_company_num', table_name=self.pro_summ)
            o_finance = self.clean_input(request.data.get('o_finance'), colunm_name=f'{self.pro_summ}__o_finance_num', table_name=self.pro_summ)

            r_private = self.clean_input(request.data.get('r_private'), colunm_name=f'{self.pro_summ}__r_private_num', table_name=self.pro_summ)
            r_rental = self.clean_input(request.data.get('r_rental'), colunm_name=f'{self.pro_summ}__r_rental_num', table_name=self.pro_summ)
            r_goverment = self.clean_input(request.data.get('r_goverment'), colunm_name=f'{self.pro_summ}__r_goverment_num', table_name=self.pro_summ)
            r_company = self.clean_input(request.data.get('r_company'), colunm_name=f'{self.pro_summ}__r_company_num', table_name=self.pro_summ)
            r_finance = self.clean_input(request.data.get('r_finance'), colunm_name=f'{self.pro_summ}__r_finance_num', table_name=self.pro_summ)
            try:
                limit = int(request.data.get('limit'))
            except:
                limit = 1000
            # print(self.base_query)
            lbkey_list = self.query(self.base_query)
            if request.data.get('is_num'):
                result_msg['total_num'] = len(lbkey_list)
            else:
                result_msg['lbkey_list'] = lbkey_list[:limit]

        return JsonResponse(result_msg)


class SavePdfView(APIView):
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='製作pdf',
        description='製作pdf，這裡無法正常顯示結果，布林值欄位請轉成0跟1，筆數越多耗時越多',
        request=None,
        parameters=[
            OpenApiParameter("tp_id", OpenApiTypes.STR, description='謄本總表id'),
            OpenApiParameter("lbkey", OpenApiTypes.STR, description='地建號'),
            OpenApiParameter("mark_only", OpenApiTypes.BOOL, description='只取標示部'),
            OpenApiParameter("owner", OpenApiTypes.STR, description='所有權登序 EX:"0001,0002"'),
            OpenApiParameter("right", OpenApiTypes.STR, description='他項權登序 EX:"0001000,0002000"'),
            OpenApiParameter("full", OpenApiTypes.BOOL, description='是否取用全謄本'),
            OpenApiParameter("query_time", OpenApiTypes.BOOL, description='是否顯示查詢時間'),
        ],
        responses={
            200: OpenApiResponse(description='成功取得pdf(請把產出的連結在其他分頁開啟)'),
            401: OpenApiResponse(description='身分認證失敗'),
        },
        )
    def get(self, request):
        # http://127.0.0.1:8000/common/tp/pdf/?tp_id=10&lbkey=G_07_0846_0311-0000&right=0001000
        # http://127.0.0.1:8000/common/tp/pdf/?tp_id=42&lbkey=K_10_0767_02247-000
        # http://127.0.0.1:8000/common/tp/pdf/?tp_id=64&lbkey=V_01_0090_00103-000&mark_only=1
        # http://127.0.0.1:8000/common/tp/pdf/?lbkey=V_01_0090_00103-000&full=1

        lbkey = request.GET.get('lbkey')

        result_msg = {}
        serializer = GetTpPDFSerializer(data=request.GET)
        if serializer.is_valid() == False:
            # print(serializer.errors)
            result_msg['msg'] = serializer.errors
            raise ParseError(result_msg)

        result_msg = serializer.save()
        if result_msg == {}:
            raise ParseError("取得謄本失敗")

        result_msg = result_msg[lbkey]

        lbEnum = getLBEnum(lbkey)
        if lbEnum == LBEnum.LAND:
            html_file = 'tp_L.html'
        else:
            html_file = 'tp_B.html'

        localtime = time.localtime()
        now_str = "民國{}年{}".format(localtime.tm_year-1911, time.strftime("%m月%d日 %H時%M分%S秒", localtime))
        result_msg['chinese_time'] = now_str

        is_query_time = int(request.GET.get('query_time', 0))
        result_msg['is_query_time'] = is_query_time

        # print(json.dumps(result_msg, ensure_ascii=False))
        # result_msg = result_msg[result_msg.keys()[0]]
        # 輸入英文謄本json 輸出pdf

        # return render(request, html_file, result_msg)
        template=get_template(html_file)
        data_p=template.render(result_msg)
        response=BytesIO()

        pdfPage=pisa.pisaDocument(BytesIO(data_p.encode("UTF-8")), response)
        if not pdfPage.err:
            response =  HttpResponse(response.getvalue(), content_type="application/pdf")
            # response['Content-Disposition'] = 'attachment; filename="output.png"'
            return response
        else:
            return HttpResponse("Error Generating PDF")


class GetTpView(APIView):
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def do_part(self, lbtype, serializer_set, mark=None, owner=None, right=None, tp_log=None, vpdata=None):
        result = {'mark': {}, 'owners': [], 'rights': [], 'owners_list': [], 'rights_list': []}
        # if lbtype == 'L':
        #     serializer_set = L_s
        # else:
        #     serializer_set = B_s

        # 組標示部
        if mark:
            mark_data = serializer_set.MarkSerializer(mark, many=True).data
            mark_obj = mark[0]
            result['mark'] = dict(mark_data[0])
            if lbtype == 'B':
                # 主建物資料
                main_p = mark_obj.mainbuilding_set.all()
                main_building = serializer_set.MainBuildingSerializer(main_p, many=True).data
                main_building_list = [dict(x) for x in main_building]
                if main_building_list:
                    result['mark'].update({'main_building': main_building_list})
                # 附屬建物
                atta_p = mark_obj.buildingattach_set.all()
                atta_building = serializer_set.AttachBuildingSerializer(atta_p, many=True).data
                atta_building_list = [dict(x) for x in atta_building]
                if atta_building_list:
                    result['mark'].update({'building_attach': atta_building_list})
                # 建物分層
                floo_p = mark_obj.buildingfloor_set.all()
                floo_building = serializer_set.FloorBuildingSerializer(floo_p, many=True).data
                floo_building_list = [dict(x) for x in floo_building]
                if floo_building_list:
                    result['mark'].update({'building_floor': floo_building_list})
                # 共有部份
                comm_p = mark_obj.commonpart_set.all()
                comm_building = serializer_set.CommonBuildingSerializer(comm_p, many=True).data
                comm_building_list = [dict(x) for x in comm_building]
                if comm_building_list:
                    result['mark'].update({'common_part': comm_building_list})

        # 組所有權
        if owner:
            owners_data = serializer_set.OwnerSerializer(owner, many=True).data
            owners_part = [dict(x) for x in owners_data]
            # print(owners_list)
            result['owners'] = owners_part

        # 組他項權
        if right:
            rights_data = serializer_set.RightSerializer(right, many=True).data
            rights_part = [dict(x) for x in rights_data]
            result['rights'] = rights_part
        
        # 組所他清單
        if tp_log:
            log_data = serializer_set.TpLogSerializer(tp_log, many=True).data
            if log_data:
                owners_list = log_data[0].get('owners')
                rights_list = log_data[0].get('rights')
                result['owners_list'] = owners_list
                result['rights_list'] = rights_list
        return result

    def distinct_df(self, qs):
        result = []
        if qs:
            pool_dict = [{'lbkey': x.summary_id.lbkey, 'create_time': x.create_time, 'obj': x} for x in qs]
            df = pd.DataFrame(pool_dict, dtype=object)
            df = df.sort_values(by=['lbkey', 'create_time']).drop_duplicates(subset=['lbkey'], keep='last').reset_index(drop=True)
            result = df['obj'].values.tolist()
        return result

    @extend_schema(
        summary='取用謄本',
        description='some commit',
        request=GetTpSerializer,
        responses={
            200: OpenApiResponse(description='處理成功'),
            401: OpenApiResponse(description='身分認證失敗'),
            },
        )
    def post(self, request, *args, **kwargs):

        result_msg = {}
        tp_class = CombinTranscript()
        serializer = GetTpSerializer(data=request.data)
        if serializer.is_valid() == False:
            print(serializer.errors)
            result_msg['msg'] = serializer.errors
            raise ParseError(result_msg)
        else:
            self.lbtype = request.data.get('lbtype')
            if self.lbtype == 'L':
                self.model_set = land.models
                serializer_ = L_s

            elif self.lbtype == 'B':
                self.model_set = building.models
                serializer_ = B_s
            else:
                result_msg['status'] = 400
                result_msg['msg'] = 'wrong lbtype'
                raise ParseError(result_msg)

            tp_id = request.data.get('tp_id')
            lbkey_list = request.data.get('lbkey_list')
            kwargs = {}
            if tp_id:
                kwargs = {'id__in': tp_id}
            elif lbkey_list:
                kwargs = {'summary_id__lbkey__in': lbkey_list}

            qs = self.model_set.TranscriptDetailSummary.objects.filter(**kwargs)
            qs_only = self.distinct_df(qs)

            if qs_only:
                for i in qs_only:
                    lbkey = i.summary_id.lbkey
                    mark_qs = i.markdetail_set.all()
                    owner_qs = i.ownertpdetail_set.all()
                    right_qs = i.righttpdetail_set.all()
                    log = i.tplog_set.all()
                    # TODO 公告地價
                    result = tp_class.do_part(lbtype=self.lbtype, serializer_set=serializer_, mark=mark_qs, owner=owner_qs, right=right_qs, tp_log=log)
                    result_msg[lbkey] = result

            return Response(result_msg)


class GetTpPDFView(APIView):
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='取用謄本(PDF)',
        description='some commit',
        request=GetTpPDFSerializer,
        responses={
            200: OpenApiResponse(description='處理成功'),
            401: OpenApiResponse(description='身分認證失敗'),
            },
        )
    def post(self, request, *args, **kwargs):
        result_msg = {}
        if type(request.data) == list:
            serializer = GetTpPDFSerializer(data=request.data, many=True)
        else:
            serializer = GetTpPDFSerializer(data=request.data)

        if serializer.is_valid() == False:
            result_msg['msg'] = serializer.errors
            raise ParseError(result_msg)
        else:
            result_msg = serializer.save()
            return Response(result_msg)


class StatsView(TemplateView):
    def get(self, request):
        now_date = datetime.now().strftime('%Y-%m-%d')
        data = request.GET.dict()
        cityCodeTable = CityCodeTable.objects.filter(is_valid=True).values('city_name', 'city_code')

        start_date = data.get('startDate', now_date)
        end_date = data.get('endDate', now_date)
        queryType = data.get('queryType', '') # 1 lbor, 2 tp
        city = data.get('city', '')
        area = data.get('area', '')
        request_data = {
            'cityCodeTable': cityCodeTable, 
            'start_date': start_date, 
            'end_date': end_date, 
            'city': city,
            'area': area,
            'lb_data': {}, 
            'ca_data': {},
            'queryType': queryType,
            'msg': ''
        }

        lb_data = {}
        if data:
            if city == '' and area == '':
                # 全縣市路徑
                land_data = land.models.DailyCount.objects.filter(statistics_time__range=[start_date, end_date]).values('statistics_time', 'lbor_sum', 'tp_sum')
                build_data = building.models.DailyCount.objects.filter(statistics_time__range=[start_date, end_date]).values('statistics_time', 'lbor_sum', 'tp_sum')

                if (land_data.exists() and build_data.exists()) == False:
                    request_data['msg'] = '查無資料'
                    return render(request, 'stats.html', request_data)

                l_df = pd.DataFrame(land_data)
                b_df = pd.DataFrame(build_data)
                if queryType == '1':
                    del l_df['tp_sum'], b_df['tp_sum']
                    l_df = l_df.rename(columns={'lbor_sum': 'l_sum'})
                    b_df = b_df.rename(columns={'lbor_sum': 'b_sum'})
                else:
                    del l_df['lbor_sum'], b_df['lbor_sum']
                    l_df = l_df.rename(columns={'tp_sum': 'l_sum'})
                    b_df = b_df.rename(columns={'tp_sum': 'b_sum'})

                lb_df = pd.merge(l_df, b_df, on=['statistics_time'], how='outer')
                lb_df = lb_df.sort_values(by='statistics_time', ascending=False)
                lb_data = lb_df.to_dict(orient='records')
                request_data['lb_data'] = lb_data
                return render(request, 'stats.html', request_data)

            if queryType == '1':
                # 列表模式
                if city and area == '':
                    chang_name = {
                        f'lbor_stats__city__{city}__query_sum': 'query_sum',
                        f'lbor_stats__city__{city}__owner_add_sum': 'owner_add_sum',
                        f'lbor_stats__city__{city}__owner_rm_sum': 'owner_rm_sum',
                        f'lbor_stats__city__{city}__right_add_sum': 'right_add_sum',
                        f'lbor_stats__city__{city}__right_rm_sum': 'right_rm_sum'
                    }
                elif city and area:
                    chang_name = {
                        f'lbor_stats__area__{city}_{area}__query_sum': 'query_sum',
                        f'lbor_stats__area__{city}_{area}__owner_add_sum': 'owner_add_sum',
                        f'lbor_stats__area__{city}_{area}__owner_rm_sum': 'owner_rm_sum',
                        f'lbor_stats__area__{city}_{area}__right_add_sum': 'right_add_sum',
                        f'lbor_stats__area__{city}_{area}__right_rm_sum': 'right_rm_sum'
                    }
                else:
                    return render(request, 'stats.html', request_data)

            else:
                # 謄本模式
                if city and area == '':
                    chang_name = {
                        f'tp_stats__city__{city}__query_sum': 'query_sum',
                        f'tp_stats__city__{city}__tp_o_sum': 'tp_o_sum',
                        f'tp_stats__city__{city}__tp_r_sum': 'tp_r_sum'
                    }
                elif city and area:
                    chang_name = {
                        f'tp_stats__area__{city}_{area}__query_sum': 'query_sum',
                        f'tp_stats__area__{city}_{area}__tp_o_sum': 'tp_o_sum',
                        f'tp_stats__area__{city}_{area}__tp_r_sum': 'tp_r_sum'
                    }
                else:
                    return render(request, 'stats.html', request_data)

            land_data = land.models.DailyCount.objects.filter(statistics_time__range=[start_date, end_date]).values('statistics_time', *tuple(chang_name))
            build_data = building.models.DailyCount.objects.filter(statistics_time__range=[start_date, end_date]).values('statistics_time', *tuple(chang_name))

            l_df = pd.DataFrame(land_data)
            l_df = l_df.rename(columns=chang_name)
            if l_df.empty:
                request_data['msg'] = '查無資料'
                return render(request, 'stats.html', request_data)

            l_df['statistics_time'] = l_df['statistics_time'].apply(lambda x: str(x))
            l_df.set_index(keys=["statistics_time"], inplace=True)
            
            b_df = pd.DataFrame(build_data)
            b_df = b_df.rename(columns=chang_name)
            b_df['statistics_time'] = b_df['statistics_time'].apply(lambda x: str(x))
            b_df.set_index(keys=["statistics_time"], inplace=True)

            lb_df = l_df.add(b_df, fill_value=0)
            lb_df = lb_df.reset_index()
            lb_df = lb_df.sort_values(by='statistics_time', ascending=False)

            lb_df = lb_df.fillna(0)
            ca_data = lb_df.to_dict(orient='records')
            request_data['ca_data'] = ca_data

        return render(request, 'stats.html', request_data)


class Blacklist(APIView):
    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='黑名單',
        description='有寫入模式跟取用模式<br>不填remark就是取用模式<br>透過地建號、查詢系統、列表謄本型態寫入名單',
        request=SetBlackDetailSerializer,
        responses={
            200: OpenApiResponse(description='處理成功'),
            401: OpenApiResponse(description='身分認證失敗'),
            },
        )
    def post(self, request, *args, **kwargs):
        if type(request.data) == list:
            serializer = SetBlackDetailSerializer(data=request.data, many=True)
        else:
            serializer = SetBlackDetailSerializer(data=request.data)

        if serializer.is_valid():
            result = serializer.save()
        else:
            raise ParseError(serializer.errors)
        return Response(result)

class StatsChartView(APIView):
    authentication_classes = [authentication.SessionAuthentication]
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        now_date = datetime.now().strftime('%Y-%m-%d')
        data = request.GET.dict()
        cityCodeTable = CityCodeTable.objects.filter(is_valid=True).values('city_name', 'city_code')

        start_date = data.get('startDate', now_date)
        end_date = data.get('endDate', now_date)
        queryType = data.get('queryType', '') # 1 lbor, 2 tp
        city = data.get('city', '')
        area = data.get('area', '')
        request_data = {
            # 'cityCodeTable': cityCodeTable, 
            'start_date': start_date, 
            'end_date': end_date, 
            'city': city,
            'area': area,
            'lb_data': {}, 
            'ca_data': {},
            'queryType': queryType,
            'msg': ''
        }
        # print(data, type(data))
        request_data['msg'] = '測試圖表'

        lb_data = {}
        if data:
            if city == '' and area == '':
                # 全縣市路徑
                land_data = land.models.DailyCount.objects.filter(statistics_time__range=[start_date, end_date]).values('statistics_time', 'lbor_sum', 'tp_sum')
                build_data = building.models.DailyCount.objects.filter(statistics_time__range=[start_date, end_date]).values('statistics_time', 'lbor_sum', 'tp_sum')

                if (land_data.exists() and build_data.exists()) == False:
                    request_data['msg'] = '查無資料'
                    # return render(request, 'stats.html', request_data)

                l_df = pd.DataFrame(land_data)
                b_df = pd.DataFrame(build_data)
                if queryType == '1':
                    del l_df['tp_sum'], b_df['tp_sum']
                    l_df = l_df.rename(columns={'lbor_sum': 'l_sum'})
                    b_df = b_df.rename(columns={'lbor_sum': 'b_sum'})
                else:
                    del l_df['lbor_sum'], b_df['lbor_sum']
                    l_df = l_df.rename(columns={'tp_sum': 'l_sum'})
                    b_df = b_df.rename(columns={'tp_sum': 'b_sum'})

                lb_df = pd.merge(l_df, b_df, on=['statistics_time'], how='outer')
                lb_df = lb_df.sort_values(by='statistics_time', ascending=False)
                lb_data = lb_df.to_dict(orient='records')
                request_data['lb_data'] = lb_data
                # return render(request, 'stats.html', request_data)

            if queryType == '1':
                # 列表模式
                if city and area == '':
                    chang_name = {
                        f'lbor_stats__city__{city}__query_sum': 'query_sum',
                        f'lbor_stats__city__{city}__owner_add_sum': 'owner_add_sum',
                        f'lbor_stats__city__{city}__owner_rm_sum': 'owner_rm_sum',
                        f'lbor_stats__city__{city}__right_add_sum': 'right_add_sum',
                        f'lbor_stats__city__{city}__right_rm_sum': 'right_rm_sum'
                    }
                elif city and area:
                    chang_name = {
                        f'lbor_stats__area__{city}_{area}__query_sum': 'query_sum',
                        f'lbor_stats__area__{city}_{area}__owner_add_sum': 'owner_add_sum',
                        f'lbor_stats__area__{city}_{area}__owner_rm_sum': 'owner_rm_sum',
                        f'lbor_stats__area__{city}_{area}__right_add_sum': 'right_add_sum',
                        f'lbor_stats__area__{city}_{area}__right_rm_sum': 'right_rm_sum'
                    }
                else:
                    pass
                    # return render(request, 'stats.html', request_data)

            else:
                # 謄本模式
                if city and area == '':
                    chang_name = {
                        f'tp_stats__city__{city}__query_sum': 'query_sum',
                        f'tp_stats__city__{city}__tp_o_sum': 'tp_o_sum',
                        f'tp_stats__city__{city}__tp_r_sum': 'tp_r_sum'
                    }
                elif city and area:
                    chang_name = {
                        f'tp_stats__area__{city}_{area}__query_sum': 'query_sum',
                        f'tp_stats__area__{city}_{area}__tp_o_sum': 'tp_o_sum',
                        f'tp_stats__area__{city}_{area}__tp_r_sum': 'tp_r_sum'
                    }
                else:
                    pass
                    # return render(request, 'stats.html', request_data)

            land_data = land.models.DailyCount.objects.filter(statistics_time__range=[start_date, end_date]).values('statistics_time', *tuple(chang_name))
            build_data = building.models.DailyCount.objects.filter(statistics_time__range=[start_date, end_date]).values('statistics_time', *tuple(chang_name))

            l_df = pd.DataFrame(land_data)
            l_df = l_df.rename(columns=chang_name)
            if l_df.empty:
                request_data['msg'] = '查無資料'
                pass
                # return render(request, 'stats.html', request_data)

            l_df['statistics_time'] = l_df['statistics_time'].apply(lambda x: str(x))
            l_df.set_index(keys=["statistics_time"], inplace=True)
            
            b_df = pd.DataFrame(build_data)
            b_df = b_df.rename(columns=chang_name)
            b_df['statistics_time'] = b_df['statistics_time'].apply(lambda x: str(x))
            b_df.set_index(keys=["statistics_time"], inplace=True)

            lb_df = l_df.add(b_df, fill_value=0)
            lb_df = lb_df.reset_index()
            lb_df = lb_df.sort_values(by='statistics_time', ascending=False)

            lb_df = lb_df.fillna(0)
            ca_data = lb_df.to_dict(orient='records')
            request_data['ca_data'] = ca_data

        # return render(request, 'stats.html', request_data)
        return Response(request_data)

    def do_data(self, qs_dict):
        data_list = {}
        city_list = [x.get('city_code') for x in CityCodeTable.objects.all().values('city_code')]
        col_type = ['modified_sum', 'owner_add_sum', 'owner_rm_sum', 'right_add_sum', 'right_rm_sum', 'query_sum']
        base_df = pd.DataFrame(index=city_list, columns=col_type).fillna(0)
        for data in qs_dict:
            city_data = data.get(self.lbtype, {}).get('city')
            df = pd.DataFrame.from_dict(city_data, orient='index')
            base_df = base_df.add(df, fill_value=0).astype(int)
        result = base_df.to_dict(orient='index')
        return result

    def produce_chart_line(self, data):
        start_date = data.get('start_date', self.now_date)
        end_date = data.get('end_date', self.now_date)
        queryType = data.get('queryType', '') # 1 lbor, 2 tp
        city = data.get('city', '')
        area = data.get('area', '')
        request_data = {
            'start_date': start_date, 
            'end_date': end_date, 
            'city': city,
            'area': area,
            'lb_data': {}, 
            'ca_data': {},
            'queryType': queryType,
            'msg': ''
        }
        request_data['msg'] = '測試圖表'
        lb_data = {}
        if data:
            if city == '' and area == '':
                # 全縣市路徑
                land_data = land.models.DailyCount.objects.filter(statistics_time__range=[start_date, end_date]).values('statistics_time', 'lbor_sum', 'tp_sum')
                build_data = building.models.DailyCount.objects.filter(statistics_time__range=[start_date, end_date]).values('statistics_time', 'lbor_sum', 'tp_sum')

                if (land_data.exists() and build_data.exists()) == False:
                    request_data['msg'] = '查無資料'

                l_df = pd.DataFrame(land_data)
                b_df = pd.DataFrame(build_data)
                if queryType == 1:
                    del l_df['tp_sum'], b_df['tp_sum']
                    l_df = l_df.rename(columns={'lbor_sum': 'l_sum'})
                    b_df = b_df.rename(columns={'lbor_sum': 'b_sum'})
                else:
                    del l_df['lbor_sum'], b_df['lbor_sum']
                    l_df = l_df.rename(columns={'tp_sum': 'l_sum'})
                    b_df = b_df.rename(columns={'tp_sum': 'b_sum'})

                lb_df = pd.merge(l_df, b_df, on=['statistics_time'], how='outer')
                lb_df = lb_df.sort_values(by='statistics_time', ascending=False)
                lb_data = lb_df.to_dict(orient='records')
                request_data['lb_data'] = lb_data

            if queryType == 1:
                # 列表模式
                if city and area == '':
                    chang_name = {
                        f'lbor_stats__city__{city}__query_sum': 'query_sum',
                        f'lbor_stats__city__{city}__owner_add_sum': 'owner_add_sum',
                        f'lbor_stats__city__{city}__owner_rm_sum': 'owner_rm_sum',
                        f'lbor_stats__city__{city}__right_add_sum': 'right_add_sum',
                        f'lbor_stats__city__{city}__right_rm_sum': 'right_rm_sum'
                    }
                elif city and area:
                    chang_name = {
                        f'lbor_stats__area__{city}_{area}__query_sum': 'query_sum',
                        f'lbor_stats__area__{city}_{area}__owner_add_sum': 'owner_add_sum',
                        f'lbor_stats__area__{city}_{area}__owner_rm_sum': 'owner_rm_sum',
                        f'lbor_stats__area__{city}_{area}__right_add_sum': 'right_add_sum',
                        f'lbor_stats__area__{city}_{area}__right_rm_sum': 'right_rm_sum'
                    }
                else:
                    pass

            else:
                # 謄本模式
                if city and area == '':
                    chang_name = {
                        f'tp_stats__city__{city}__query_sum': 'query_sum',
                        f'tp_stats__city__{city}__tp_o_sum': 'tp_o_sum',
                        f'tp_stats__city__{city}__tp_r_sum': 'tp_r_sum'
                    }
                elif city and area:
                    chang_name = {
                        f'tp_stats__area__{city}_{area}__query_sum': 'query_sum',
                        f'tp_stats__area__{city}_{area}__tp_o_sum': 'tp_o_sum',
                        f'tp_stats__area__{city}_{area}__tp_r_sum': 'tp_r_sum'
                    }
                else:
                    pass
            
            land_data = land.models.DailyCount.objects.filter(statistics_time__range=[start_date, end_date]).values('statistics_time', *tuple(chang_name))
            build_data = building.models.DailyCount.objects.filter(statistics_time__range=[start_date, end_date]).values('statistics_time', *tuple(chang_name))
            l_df = pd.DataFrame(land_data)
            l_df = l_df.rename(columns=chang_name)
            if l_df.empty:
                request_data['msg'] = '查無資料'
                return request_data
            l_df['statistics_time'] = l_df['statistics_time'].apply(lambda x: str(x))
            l_df.set_index(keys=["statistics_time"], inplace=True)
            
            b_df = pd.DataFrame(build_data)
            b_df = b_df.rename(columns=chang_name)
            b_df['statistics_time'] = b_df['statistics_time'].apply(lambda x: str(x))
            b_df.set_index(keys=["statistics_time"], inplace=True)

            lb_df = l_df.add(b_df, fill_value=0)
            lb_df = lb_df.reset_index()
            lb_df = lb_df.sort_values(by='statistics_time', ascending=False)

            lb_df = lb_df.fillna(0)
            ca_data = lb_df.to_dict(orient='records')
            request_data['ca_data'] = ca_data
        return request_data

    def produce_chart_pie(self, data):
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        queryType = data.get('queryType')
        if queryType == 1:
            self.lbtype = 'lbor_stats'
        else:
            self.lbtype = 'tp_stats'
        land_data = land.models.DailyCount.objects.filter(statistics_time__range=[start_date, end_date]).values(self.lbtype)
        build_data = building.models.DailyCount.objects.filter(statistics_time__range=[start_date, end_date]).values(self.lbtype)
        result = self.do_data(land_data)
        return result


    def post(self, request, *args, **kwargs):
        # cityCodeTable = CityCodeTable.objects.filter(is_valid=True).values('city_name', 'city_code')
        result = {}
        self.now_date = datetime.now().strftime('%Y-%m-%d')
        datas = request.data
        if isinstance(datas, dict):
            plot_type = datas.get('plot_type')
            if plot_type == 1:
                print('plot_type: 折線圖')
                serializer = StatsChartLineSerializer(data=datas)
                if serializer.is_valid():
                    result = self.produce_chart_line(serializer.data)

            elif plot_type == 2:
                print('plot_type: 圓餅')
                serializer = StatsChartPieSerializer(data=datas)
                if serializer.is_valid():
                    result = self.produce_chart_pie(serializer.data)

        return Response(result)
