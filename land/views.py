from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import authentication, permissions, mixins, generics, viewsets

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample, inline_serializer, OpenApiResponse, Serializer, OpenApiCallback

from land.land_serializers import LandFeedbackTpSerializer

json_dumps_params = {'ensure_ascii': False}

import logging
logger = logging.getLogger(__name__)

class FeedbackTp(APIView):
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
        request=LandFeedbackTpSerializer,
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
            serializer = LandFeedbackTpSerializer(data=request.data, many=True)
        else:
            serializer = LandFeedbackTpSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
        else:
            return Response({'status': 'NG', 'msg': serializer.errors})

        return Response({'status': 'OK'})

