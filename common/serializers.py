import logging
import re
from collections import Counter
from subprocess import Popen
from typing import Dict, List, Tuple

import pandas as pd
import pytz
from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

import building.building_serializers as B_s
import building.models
import land.land_serializers as L_s
import land.models
from common.enums import (IsvalidTypeEnum, LBEnum, LborTpTypeEnum,
                          PropertyTypeEnum, QuerySystemEnum, RuleTypeEnum,
                          TaskTypeEnum)
from common.models import (AreaCodeTable, CityCodeTable, OfficeCodeTable,
                           RegionCodeTable)
from common.util import (CombinTranscript, check_property_one, get_obligee,
                         getLBEnum)

logger = logging.getLogger(__name__)


tz = pytz.timezone(settings.TIME_ZONE)


def exclude_null(data):
    if (len(data['owners']) + len(data['rights'])) == 0:
        return True
    return False

def check_or_type(data, or_str):
    if len(data[or_str]) == 0:
        return {}
    return data[or_str]

def contains_regno(data, or_type, owner):
    if owner in data[or_type]:
        return True
    return False

def _create_tp_log(validated_data):
    if validated_data:
        fast_task_L = []
        fast_task_B = []
        normal_task_L = []
        normal_task_B = []
        task_update_L = []
        task_update_B = []

        for i in validated_data:
            if getLBEnum(i.get('lbkey')) == LBEnum.LAND:
                model_set = land.models
                fast_task = fast_task_L
                normal_task = normal_task_L
                task_update = task_update_L

            elif getLBEnum(i.get('lbkey')) == LBEnum.BUILD:
                model_set = building.models
                fast_task = fast_task_B
                normal_task = normal_task_B
                task_update = task_update_B
            else:
                continue

            if i.get('is_fast') == True:
                del i['is_fast']
                fast_task.append(model_set.Tplog(**i))
            else:
                del i['is_fast']
                normal_task.append(model_set.Tplog(**i))

            task_id = i.get('task_id')

            now = timezone.now()
            if isinstance(task_id, int) == True:
                qs = model_set.TpTaskPool.objects.filter(id=task_id)
                for i in qs:
                    i.state = TaskTypeEnum.COMPLETE
                    i.complete_time = now
                    task_update.append(i)
                    
        # for i in validated_data:
        #     if getLBEnum(i.get('lbkey')) == LBEnum.LAND:
        #         if i.get('is_fast') == True:
        #             del i['is_fast']
        #             fast_task_L.append(land.models.Tplog(**i))
        #         else:
        #             del i['is_fast']
        #             normal_task_L.append(land.models.Tplog(**i))

        #     elif getLBEnum(i.get('lbkey')) == LBEnum.BUILD:
        #         if i.get('is_fast') == True:
        #             del i['is_fast']
        #             fast_task_B.append(building.models.Tplog(**i))
        #         else:
        #             del i['is_fast']
        #             normal_task_B.append(building.models.Tplog(**i))

        # 更新任務狀態
        if task_update_L:
            land.models.TpTaskPool.objects.bulk_update(task_update_L, fields=['state', 'complete_time'])
        if task_update_B:
            building.models.TpTaskPool.objects.bulk_update(task_update_B, fields=['state', 'complete_time'])
        
        # 新增log
        if normal_task_L:
            land.models.Tplog.objects.bulk_create(normal_task_L)
        if normal_task_B:
            building.models.Tplog.objects.bulk_create(normal_task_B)
        
        # 快速解析
        if fast_task_L:
            cre_obj = land.models.Tplog.objects.bulk_create(fast_task_L)
            id_list = [str(x.id) for x in cre_obj]
            if id_list:
                Popen(['python', 'manage.py', 'parser_tp', '-t', 'L', '-i', ' '.join(id_list)])

        if fast_task_B:
            cre_obj = building.models.Tplog.objects.bulk_create(fast_task_B)
            id_list = [str(x.id) for x in cre_obj]
            if id_list:
                Popen(['python', 'manage.py', 'parser_tp', '-t', 'B', '-i', ' '.join(id_list)])

class TpTaskSerializer(serializers.Serializer):
    task_data = serializers.ListField(default=[{'lbkey': 'A_11_0132_0572-0000', 'priority':50, 'is_mark_only':True},
                                               {'lbkey': 'F_01_0307_0322-0006', 'o_regno_str':'0009,0008', 'r_regno_str':'0009000,0630000', 'priority': 60}],
                                        help_text='多筆,分隔')
    forcibly = serializers.BooleanField(default=False, allow_null=True, help_text='強制非強制調閱')

    # lbkey = serializers.CharField(default="A_01_0600_0000-0000", min_length=19, max_length=19)
    # o_regno_str = serializers.CharField(default="0001,0002", allow_null=True, help_text='所有權登序多筆","分隔')
    # r_regno_str = serializers.CharField(default="0001000,0002000", allow_null=True, help_text='他項權登序多筆","分隔')
    # priority = serializers.IntegerField(default=70, allow_null=True, help_text='優先度 預設70')
    # is_mark_only = serializers.BooleanField(default=False, allow_null=True, help_text='只調標示部 預設False')
    # system = serializers.IntegerField(default=2, allow_null=True, help_text='系統 預設2(群旋)')

class FeedbackTpListSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        _create_tp_log(validated_data)
        return True

class FeedbackTplogSerializer(serializers.Serializer):
    lbkey = serializers.CharField(default="", help_text='A_01_0600_0000-0000', min_length=19, max_length=19)
    query_system = serializers.ChoiceField(choices=QuerySystemEnum.choices(), default=QuerySystemEnum.LOR_V2, help_text=str(QuerySystemEnum.choices()))
    owners = serializers.JSONField(default={}, help_text='{"0001": "測＊＊"}')
    rights = serializers.JSONField(default={}, help_text='{"0001000": "測試"}')
    rules = serializers.ChoiceField(choices=RuleTypeEnum.choices(), default=RuleTypeEnum.BOTH, help_text=str(RuleTypeEnum.choices()))
    state = serializers.ChoiceField(choices=TaskTypeEnum.choices(), default=TaskTypeEnum.INIT, help_text=str(TaskTypeEnum.choices()))
    transcript = serializers.JSONField(default={}, help_text='{"transcript_info": {"標示部":{}, "所有權":{}, "他項權":{}}}')
    is_fast = serializers.BooleanField(default=False, help_text='是否要加速')
    task_id = serializers.IntegerField(default=None, help_text='任務代號')
    query_time = serializers.DateTimeField(default="2022-5-5 10:10:10")

    class Meta:
        list_serializer_class = FeedbackTpListSerializer

    def create(self, validated_data):
        _create_tp_log([validated_data])
        return True


class GenerateLborTaskSerializer(serializers.Serializer):
    CAR = serializers.CharField(default="", help_text='縣市行政區段小段 EX: "A_01_0006"')
    development = serializers.CharField(default="", help_text='計畫區 EX: "溫仔圳第一期"')
    use_zone = serializers.CharField(default="", help_text='使用分區 EX: "農業區"')
    time_start = serializers.DateTimeField(default="2022-5-5 10:10:10 EX: 2022-09-22")
    time_end = serializers.DateTimeField(default="2022-5-5 10:10:10 EX: 2022-09-28")

    owners_num = serializers.CharField(default="", help_text='所有權人數量 EX: "1,50"')
    rights_num = serializers.CharField(default="", help_text='他項權人數量 EX: "5,10"')
    building_num = serializers.CharField(default="", help_text='地上建物數量 EX: "1,100"')
    vp_price = serializers.CharField(default="", help_text='土地價值 EX: ""')
    
    o_private = serializers.CharField(default="", help_text='所_私設 EX: "0,10"')
    o_rental = serializers.CharField(default="", help_text='所_租賃 EX: "0,10"')
    o_goverment = serializers.CharField(default="", help_text='所_政府 EX: "0,10"')
    o_company = serializers.CharField(default="", help_text='所_公司 EX: "0,10"')
    o_finance = serializers.CharField(default="", help_text='所_金融 EX: "0,10"')
    
    r_private = serializers.CharField(default="", help_text='他_私設 EX: "0,10"')
    r_rental = serializers.CharField(default="", help_text='他_租賃 EX: "0,10"')
    r_goverment = serializers.CharField(default="", help_text='他_政府 EX: "0,10"')
    r_company = serializers.CharField(default="", help_text='他_公司 EX: "0,10"')
    r_finance = serializers.CharField(default="", help_text='他_金融 EX: "0,10"')
    
    limit = serializers.IntegerField(default=100, help_text='限制筆數 EX: 1000')
    is_num = serializers.BooleanField(default=False, allow_null=True, help_text='計算機')

class GetTpSerializer(serializers.Serializer):
    tp_id = serializers.ListField(default=[], help_text='謄本總表id')
    lbkey_list = serializers.ListField(default=[], help_text='地建號清單')
    lbtype = serializers.CharField(default='L', help_text='地建號型態')


def _create_tp_json(validated_datas):
    tp_class = CombinTranscript()
    result_msg = {}
    if validated_datas:
        for dict_data in validated_datas:       
            tp_id = dict_data.get('tp_id')
            lbkey = dict_data.get('lbkey')
            full = dict_data.get('full')
            mark_only = dict_data.get('mark_only')
            org_o_list = tp_class.regno_process(dict_data.get('owner'))
            org_r_list = tp_class.regno_process(dict_data.get('right'))

            if getLBEnum(lbkey) == LBEnum.LAND:
                model_set = land.models
                serializer_ = L_s
                lbtype_ = 'L'
            elif getLBEnum(lbkey) == LBEnum.BUILD:
                model_set = building.models
                serializer_ = B_s
                lbtype_ = 'B'
            else:
                continue

            if full:
                # 取最新全登序謄本
                try:
                    q_obj = model_set.Summary.objects.get(lbkey=lbkey)
                except:
                    q_obj = None
                    continue
                if q_obj:

                    if q_obj.last_mark_detail_id:
                        mark_qs = [q_obj.last_mark_detail_id]
                    else:
                        mark_qs = None
                    
                    owner_qs = [x.last_tp_detail_id for x in q_obj.ownerregnosummary_set.all() if x.last_tp_detail_id]
                    right_qs = [x.last_tp_detail_id for x in q_obj.rightregnosummary_set.all() if x.last_tp_detail_id]
                    print(len(owner_qs), len(right_qs))
                    full_tp = tp_class.do_part(lbtype=lbtype_, serializer_set=serializer_, mark=mark_qs, owner=owner_qs, right=right_qs, tp_log=None)
                    print('do_part 完成')
                    full_tp = tp_class.combit_list_process(tp_json=full_tp)
                    print('combit_list_process 完成')
                    if not full_tp.get('mark'):
                        result_msg[lbkey] = {}
                    else:
                        car_json = tp_class.get_CAR(lbkey=lbkey, summary_model=model_set, summary_obj=q_obj)
                        print('car_json 完成')
                        car_json['tp_type'] = '全部'
                        full_tp.update(car_json)
                        result_msg[lbkey] = full_tp
                        print('全部 完成')
                return result_msg

            else:
                # 取指定id謄本
                try:
                    q_obj = model_set.TranscriptDetailSummary.objects.get(id=tp_id)
                except:
                    q_obj = None
                    continue

                if q_obj:
                    if q_obj.summary_id.lbkey == lbkey:
                        if mark_only == True:
                            tp_type = '標示部'
                        elif not org_o_list and not org_r_list:
                            tp_type = q_obj.integrity_type
                            if tp_type == 1:
                                tp_type = '全部'
                            elif tp_type == 3:
                                tp_type = '標示部'
                            else:
                                tp_type = '部份'                        
                        else:
                            tp_type = '部份'
                                                
                        mark_qs = q_obj.markdetail_set.all()
                        owner_qs = q_obj.ownertpdetail_set.all()
                        right_qs = q_obj.righttpdetail_set.all()
                        log = q_obj.tplog_set.all()
                        full_tp = tp_class.do_part(lbtype=lbtype_, serializer_set=serializer_, mark=mark_qs, owner=owner_qs, right=right_qs, tp_log=log)
                        if not full_tp.get('mark'):
                            result_msg[lbkey] = {}
                        else:
                            car_json = tp_class.get_CAR(lbkey=lbkey, summary_model=model_set)
                            car_json['tp_type'] = tp_type
                            # 檢查搜尋物件debug
                            # print(mark_qs, owner_qs, right_qs, log)
                            # print(org_o_list, org_r_list)
                            # =======================================
                            if mark_only == True:
                                result = {'mark': full_tp.get('mark')}
                            elif not org_o_list and not org_r_list:
                                result = full_tp
                            else:
                                result = tp_class.combin_process(full_tp, org_o_list, org_r_list)
                            result.update(car_json)
                            result_msg[lbkey] = result
    return result_msg

class GetTpPDFListSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        # with transaction.atomic():
        res = _create_tp_json(validated_data)
        return res

class GetTpPDFSerializer(serializers.Serializer):
    tp_id = serializers.IntegerField(default=0, allow_null=True, help_text='謄本總表id')
    lbkey = serializers.CharField(default='O_01_0082_00130-000', help_text='地建號')
    mark_only = serializers.BooleanField(default=False, allow_null=True, help_text='只取標示部')
    owner = serializers.CharField(default='', allow_null=True, allow_blank=True, help_text='所有權登序 EX:"0001,0002"')
    right = serializers.CharField(default='', allow_null=True, allow_blank=True, help_text='他項權登序 EX:"0001000,0002000"')
    full = serializers.BooleanField(default=False, allow_null=True, help_text='是否取用全謄本')
    class Meta:
        list_serializer_class = GetTpPDFListSerializer

    def create(self, validated_data):
        # with transaction.atomic():
        res = _create_tp_json([validated_data])
        return res


def _create_blacklist(validated_data:list[dict]):
    land_bulk_create = []
    land_bulk_update = []
    buliding_bulk_create = []
    buliding_bulk_update = []
    result = {}

    for i in validated_data:
        lbkey = i.get('lbkey')
        lbEnum = getLBEnum(lbkey)
        query_system = QuerySystemEnum(i.get('query_system', 30))
        lbor_tp_type = LborTpTypeEnum(i.get('lbor_tp_type', 1))
        remark = i.get('remark', '')

        if lbEnum == LBEnum.LAND:
            LB_models = land.models
            LB_bulk_create = land_bulk_create
            LB_bulk_update = land_bulk_update
        elif lbEnum == LBEnum.BUILD:
            LB_models = building.models
            LB_bulk_create = buliding_bulk_create
            LB_bulk_update = buliding_bulk_update
        else:
            continue

        black_details = LB_models.BlacklistDetail.objects.filter(lbkey=lbkey, query_system=query_system, lbor_tp_type=lbor_tp_type)
        if black_details.exists():
            black_detail = black_details[0]
            if remark:
                if remark not in black_detail.remark:
                    black_detail.remark.append(remark)
            black_detail.take_count += 1
            black_detail.take_time = timezone.now()
            LB_bulk_update.append(black_detail)

            result[lbkey] = {"msg": black_detail.remark}
        else:
            if remark:
                LB_bulk_create.append(
                    LB_models.BlacklistDetail(lbkey=lbkey, query_system=query_system, lbor_tp_type=lbor_tp_type, remark=[remark]))

    if land_bulk_create:
        land.models.BlacklistDetail.objects.bulk_create(land_bulk_create, batch_size=1000)
    if land_bulk_update:
        land.models.BlacklistDetail.objects.bulk_update(land_bulk_update, fields=['take_count', 'take_time', 'remark'])
    if buliding_bulk_create:
        building.models.BlacklistDetail.objects.bulk_create(buliding_bulk_create, batch_size=1000)
    if buliding_bulk_update:
        building.models.BlacklistDetail.objects.bulk_update(buliding_bulk_update, fields=['take_count', 'take_time', 'remark'])
    return result
