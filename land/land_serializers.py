from django.conf import settings
from rest_framework import serializers
from common.models import CityCodeTable, AreaCodeTable, OfficeCodeTable, RegionCodeTable
from common.enums import LBEnum, IsvalidTypeEnum, PropertyTypeEnum, MenuTypeEnum, RightClassifyEnum, RestrictionTypeEnum, QuerySystemEnum, RuleTypeEnum
from common.util import get_obligee, check_property_one, getLBEnum, replace_simple
from typing import (
    Dict,
    List,
    Tuple,
)
from land.models import MarkNotice, MarkDetail, OwnerTpDetail, RightTpDetail, Tplog, TranscriptDetailSummary
import json
import pytz

tz = pytz.timezone(settings.TIME_ZONE)

# 解析謄本用序列器(反序列)=======================================================
class LandSerializerMarkVP(serializers.ModelSerializer):
    class Meta:
        model = MarkNotice
        # fields = ('__all__')

        exclude = ('mark_detail_id', 'query_time')

class LandSerializerMark(serializers.ModelSerializer):
    class Meta:
        model = MarkDetail
        # fields = ('__all__')

        exclude = ('reg_date', 'other_remark_str', 'locate_bkey', 
                    'parting', 'resurvey', 'merge', 'add', 'normal_mark',
                    'tp_summary_id')

class LandSerializerOwner(serializers.ModelSerializer):
    class Meta:
        model = OwnerTpDetail
        # fields = ('__all__')

        exclude = ('reg_date', 'reason_date', 'old_value',
                    'related_creditor_regno', 'declare_value_date', 
                    'land_value_remark', 'other_remark_str', 
                    'restricted_type', 'restricted_reason', 'tp_summary_id', 'extra')

class LandSerializerRight(serializers.ModelSerializer):
    class Meta:
        model = RightTpDetail
        # fields = ('__all__')

        exclude = ('reg_date', 'guarantee_date', 'duration_start_date', 'duration_end_date',
                    'payoff_date', 'restricted_type', 'collateral_lkey', 'collateral_bkey',
                    'other_remark_str', 'tp_summary_id', 'extra')
# ==============================================================================================================


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
    locate_bkey = serializers.SerializerMethodField()
    other_remark_str = serializers.SerializerMethodField()
    parting = serializers.SerializerMethodField()
    resurvey = serializers.SerializerMethodField()
    merge = serializers.SerializerMethodField()
    add = serializers.SerializerMethodField()
    normal_mark = serializers.SerializerMethodField()

    def get_locate_bkey(self, obj):
        res = replace_simple(obj.locate_bkey)
        return res

    def get_other_remark_str(self, obj):
        res = replace_simple(obj.other_remark_str)
        return res

    def get_parting(self, obj):
        res = replace_simple(obj.parting)
        return res

    def get_resurvey(self, obj):
        res = replace_simple(obj.resurvey)
        return res

    def get_merge(self, obj):
        res = replace_simple(obj.merge)
        return res

    def get_add(self, obj):
        res = replace_simple(obj.add)
        return res

    def get_normal_mark(self, obj):
        res = replace_simple(obj.normal_mark)
        return res
    class Meta:
        # 繼承用
        # abstract = True
        model = MarkDetail
        # fields = '__all__'
        exclude = ('id', 'is_valid', 'tp_summary_id')

class MarkVpSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarkNotice
        # fields = '__all__'
        exclude = ('id', 'mark_detail_id', 'query_time', 'is_valid')


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
