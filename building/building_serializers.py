from multiprocessing import context
from attr import field
from django.conf import settings
from django.db import transaction
from rest_framework import serializers
from common.models import CityCodeTable, AreaCodeTable, OfficeCodeTable, RegionCodeTable
from common.enums import LBEnum, IsvalidTypeEnum, PropertyTypeEnum, MenuTypeEnum, RightClassifyEnum, RestrictionTypeEnum, QuerySystemEnum, RuleTypeEnum
from common.util import getLBEnum, replace_simple
from building.models import OwnerTpDetail, RightTpDetail, MarkDetail, BuildingAttach, BuildingFloor, MainBuilding, CommonPart, Tplog, TranscriptDetailSummary

from common.util import get_obligee, check_property_one
from typing import (
    Dict,
    List,
    Tuple,
)

import pytz

tz = pytz.timezone(settings.TIME_ZONE)



# 謄本解析用序列器
class BuildingSerializerFloor(serializers.ModelSerializer):
    class Meta:
        model = BuildingFloor
        exclude = ('mark_id',)

class BuildingSerializerAttach(serializers.ModelSerializer):
    class Meta:
        model = BuildingAttach
        exclude = ('mark_id',)

class BuildingSerializerCommon(serializers.ModelSerializer):
    class Meta:
        model = CommonPart
        exclude = ('mark_id', 'other_remark')

class BuildingSerializerMain(serializers.ModelSerializer):
    class Meta:
        model = MainBuilding
        exclude = ('mark_id', 'other_remark')

class BuildingSerializerMark(serializers.ModelSerializer):
    class Meta:
        model = MarkDetail
        # fields = ('__all__')

        exclude = ('reg_date', 'locate_lkey', 'main_purpose', 'use_license_no', 'material',
                    'query_time', 'build_date',
                    'other_remark_str', 'tp_summary_id')

class BuildingSerializerOwner(serializers.ModelSerializer):
    class Meta:
        model = OwnerTpDetail
        # fields = ('__all__')

        exclude = ('reg_date', 'reason_date', 
                    'related_creditor_regno', 
                    'other_remark_str', 
                    'restricted_type', 'restricted_reason', 'tp_summary_id', 'extra')

class BuildingSerializerRight(serializers.ModelSerializer):
    class Meta:
        model = RightTpDetail
        # fields = ('__all__')

        exclude = ('reg_date', 'guarantee_date', 'duration_start_date', 'duration_end_date',
                    'payoff_date', 'restricted_type', 'collateral_lkey', 'collateral_bkey',
                    'other_remark_str', 'tp_summary_id', 'extra')




# 謄本api(正序列)==============================================================================================================
# tp_summary序列器 (測試用)
class TpSerializer(serializers.ModelSerializer):
    # data = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    class Meta:
        model = TranscriptDetailSummary
        
        # 排除特定欄位
        exclude = ('summary_id',)
        # 指定輸出欄位
        # fields = ['summary_id', 'integrity_type', 'markdetail_set']
        # fields = '__all__'


# 標示部
class MarkSerializer(serializers.ModelSerializer):
    locate_lkey = serializers.SerializerMethodField()
    other_remark_str = serializers.SerializerMethodField()

    def get_locate_lkey(self, obj):
        res = replace_simple(obj.locate_lkey)
        return res

    def get_other_remark_str(self, obj):
        res = replace_simple(obj.other_remark_str)
        return res

    class Meta:
        # 繼承用
        # abstract = True
        model = MarkDetail
        # fields = '__all__'
        exclude = ('id', 'is_valid', 'tp_summary_id')

# class MarkVpSerializer(serializers.ModelSerializer):
#     pass


class OwnerSerializer(serializers.ModelSerializer):

    class Meta:
        # 繼承用
        # abstract = True
        model = OwnerTpDetail
        # fields = '__all__'s
        exclude = ('id', 'is_valid', 'tp_summary_id')

class RightSerializer(serializers.ModelSerializer):

    class Meta:
        # 繼承用
        # abstract = True
        model = RightTpDetail
        # fields = '__all__'
        exclude = ('id', 'is_valid', 'tp_summary_id')

class TpLogSerializer(serializers.ModelSerializer):
    class Meta:
        # 繼承用
        # abstract = True
        model = Tplog
        # fields = ('owners', 'rights')
        fields = '__all__'
        # exclude = ('id', 'is_valid', 'tp_summary_id')


class MainBuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = MainBuilding
        exclude = ('id', 'mark_id')

class AttachBuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingAttach
        exclude = ('id', 'mark_id')

class FloorBuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingFloor
        exclude = ('id', 'mark_id')

class CommonBuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommonPart
        exclude = ('id', 'mark_id')
