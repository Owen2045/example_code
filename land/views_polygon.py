from django.contrib.gis.geos import GEOSGeometry
from django.http import HttpResponse
from django.db import transaction
from django.views import View

from land.models import Summary

from shapely.geometry import Point, shape
# from tqdm import tqdm
import pymysql
import json
import sys

from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import authentication, permissions, mixins, generics, viewsets
from rest_framework import serializers, status
from rest_framework.parsers import JSONParser

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample, inline_serializer, OpenApiResponse, Serializer, OpenApiCallback
from drf_spectacular.types import OpenApiTypes


class PolyProcess(APIView):
    '''
    多邊形資料匯入

    使用者驗證：
    
    headers = {'Authorization': 'token 22a7bfe39c228d32*****11b2f5f24218e6d65ab',}
    '''

    authentication_classes = [authentication.TokenAuthentication, authentication.SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary='土地多邊形匯入',
        # description='回傳登序清單',
        request=None,

        # responses=XSerializer(many=True))
        responses={
            200: OpenApiResponse(description='新增成功'),
            401: OpenApiResponse(description='身分認證失敗'),
        },
        parameters=[
            OpenApiParameter("city", OpenApiTypes.STR)
        ],

        # examples=[
        #     OpenApiExample(
        #         name='台北市松山區',
        #         value=[{"region_name": "西松段一小段","region_code": "0600","car_code": "A_01_0600"},{"region_name": "西松段二小段","region_code": "0601","car_code": "A_01_0601"}],
        #         response_only=True),
        # ]
        )
    def get(self, request, *args, **kwargs):
        city_code = request.GET.get('city')
        print('開始執行資料匯入')
        try:
            lkey_list = []
            conn = pymysql.connect(host='192.168.1.18', port=3306, db='polygon', user='root', password='78951235', charset='utf8', cursorclass=pymysql.cursors.DictCursor)
            cursor = conn.cursor()
            cursor.execute("select lkey,ST_AsGeoJSON(point),ST_AsGeoJSON(Polygon) from lkey where lkey like '{}%'".format(city_code))
            results = cursor.fetchall()
            # progress = tqdm(total=len(results))
            for s,data in enumerate(results):
                # progress.update(1)
                # if s == 2100:
                #     break
                kwargss = {
                        'lbkey':data['lkey'],
                        'point':GEOSGeometry(str(json.loads(data['ST_AsGeoJSON(point)']))) if data['ST_AsGeoJSON(point)'] else None,
                        'polygon':GEOSGeometry(str(json.loads(data['ST_AsGeoJSON(Polygon)']))) if data['ST_AsGeoJSON(Polygon)'] else None
                        }

                lkey_create = Summary(**kwargss)
                lkey_list.append(lkey_create)
                if ((s+1) % 1000) == 0:
                    with transaction.atomic():
                        if len(lkey_list):
                            Summary.objects.bulk_create(lkey_list, ignore_conflicts=True)
                            lkey_list = []
                if (s+1) == len(results):
                    with transaction.atomic():
                        if len(lkey_list):
                            Summary.objects.bulk_create(lkey_list, ignore_conflicts=True)
        except Exception as e:
            print(e, 'exception in line', sys.exc_info()[2].tb_lineno)
        conn.close()
        result = {'msg':'OK'}
        return HttpResponse(json.dumps(result, ensure_ascii=False), content_type="application/json; charset=utf-8")








