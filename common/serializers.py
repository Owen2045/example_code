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


class CityCodeTableSerializer(serializers.ModelSerializer):
    class Meta:
        model = CityCodeTable
        # fields = '__all__'
        fields = ('city_name', 'city_code')

class AreaCodeTableSerializer(serializers.ModelSerializer):
    class Meta:
        model = AreaCodeTable
        # fields = '__all__'
        fields = ('area_name', 'area_code')

class OfficeCodeTableSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfficeCodeTable
        # fields = '__all__'
        fields = ('office_name', 'office_code')

class RegionCodeTableSerializer(serializers.ModelSerializer):
    car_code = serializers.SerializerMethodField() # 序列方法字段

    class Meta:
        model = RegionCodeTable
        fields = ('region_name', 'region_code', 'car_code')
        read_only_fields = ['car_code'] # 只讀字串
        # depth = 2 # 關聯階級

    def get_car_code(self, obj) -> str: # 輸出類型
        return "{}_{}_{}".format(obj.area_code_table_id.city_code_table_id.city_code, obj.area_code_table_id.area_code, obj.region_code)


def _get_CAR_table(lbkey:str, cache_dict:dict) -> Tuple[object, object, object]:
    '''
    取得或建立 縣市 行政區 段小段 欄位

    cache_dict: 空字典 快取用的
    '''
    if cache_dict == {}:
        cache_dict['city'] = {}
        cache_dict['region'] = {}

    cityCodeTable = cache_dict['city'].get(f"{lbkey[0]}")
    if cityCodeTable == None:
        cityCodeTable = CityCodeTable.objects.get(city_code=lbkey[0])
        cache_dict['city'][lbkey[0]] = cityCodeTable

    regionCodeTable = cache_dict['region'].get(f"{lbkey[0]}{lbkey[5:9]}")
    if regionCodeTable == None:
        regionCodeTables = RegionCodeTable.objects.filter(area_code_table_id__city_code_table_id=cityCodeTable, region_code=lbkey[5:9])
        if regionCodeTables.exists():
            if len(regionCodeTables) == 1:
                regionCodeTable = regionCodeTables[0]
                cache_dict['region'][f"{lbkey[0]}{lbkey[5:9]}"] = regionCodeTable
            else:
                regionCodeTables_double = regionCodeTables.filter(is_valid=True)
                if regionCodeTables_double.exists():
                    regionCodeTable = regionCodeTables_double[0]
                    cache_dict['region'][f"{lbkey[0]}{lbkey[5:9]}"] = regionCodeTable

    if regionCodeTable == None or regionCodeTable.area_code_table_id != lbkey[2:4]:
        return None, None, None

    return cityCodeTable, regionCodeTable.area_code_table_id, regionCodeTable

def if_contain_symbol(keyword):
    keyword_str = keyword.replace('＊', '')
    res = re.search(u"([^\u4e00-\u9fa5\u0030-\u0039])", keyword_str)
    res1 = re.search(u"([温黄禇龎甯鍾])", keyword_str)
    if res or res1 or keyword_str == '':
        return True
    else:
        return False

def check_regno_name(regno_id:land.models.OwnerRegnoSummary, name:str):
    '''
    無特殊字 更新名子
    '''
    if regno_id and regno_id.name:
        if if_contain_symbol(regno_id.name):
            regno_id.name = name

def set_propertyType(rule_type:RuleTypeEnum, summary_id, propertyType_id, property_count_dict:dict, regno_log:list, last_property_type:PropertyTypeEnum):
    if rule_type == RuleTypeEnum.OWNER:
        summary_id.owners_num = len(regno_log)
        propertyType_id.o_unknown_num = property_count_dict[PropertyTypeEnum.UNKNOWN]
        propertyType_id.o_goverment_num = property_count_dict[PropertyTypeEnum.GOVERMENT]
        propertyType_id.o_private_num = property_count_dict[PropertyTypeEnum.PRIVATE]
        propertyType_id.o_company_num = property_count_dict[PropertyTypeEnum.COMPANY]
        propertyType_id.o_rental_num = property_count_dict[PropertyTypeEnum.RENTAL]
        propertyType_id.o_finance_num = property_count_dict[PropertyTypeEnum.FINANCE]
        propertyType_id.last_o_property_type = last_property_type
    else:
        summary_id.rights_num = len(regno_log)
        propertyType_id.r_unknown_num = property_count_dict[PropertyTypeEnum.UNKNOWN]
        propertyType_id.r_goverment_num = property_count_dict[PropertyTypeEnum.GOVERMENT]
        propertyType_id.r_private_num = property_count_dict[PropertyTypeEnum.PRIVATE]
        propertyType_id.r_company_num = property_count_dict[PropertyTypeEnum.COMPANY]
        propertyType_id.r_rental_num = property_count_dict[PropertyTypeEnum.RENTAL]
        propertyType_id.r_finance_num = property_count_dict[PropertyTypeEnum.FINANCE]
        propertyType_id.last_r_property_type = last_property_type


def _create_lbor_regno(
    summary_id:land.models.Summary|building.models.Summary, 
    propertyType_id:land.models.PropertyTypeSummary|building.models.PropertyTypeSummary, 
    regno_log:land.models.RegnoLog|building.models.RegnoLog, 
    LB_models:land.models, rule_type:RuleTypeEnum, 
    is_new:bool, 
    obligee_dict:get_obligee,
    regno_check_repeat:dict):
    # 舊資料

    '''
    2022/5/18 更新紀錄表 無變動不寫入

    所他權處理 > 判斷查詢時間

    判斷為最新和完整的資料走上路
    1. 判斷總表有無效 > 無效改地建號狀態
    2. 區分有無效登序，並且把有效登序改無效(狀態轉換清單)
    3. 登序for迴圈處理
        1. 存在 狀態轉換清單: 
            狀態轉換清單改回有效 並更新最後查詢時間
            比對完整性(姓名欄位非特殊字且有資料 與 資料庫比對)
        2. 不存在:
            1. 存在 無效登序:
                已經失效卻在完整新資料 > 變更log狀態為異常解析
            2. 不存在
                有異動 完整新資料 發現新登序
                查詢所他設定類別 > 建立登序總表 建立異動明細表 建立登序明細表
        4. 記錄各登序設定類別與記數
    4. 狀態轉換清單，還是無效為失效資料
        登序總表 寫入移除時間
        建立登序明細表
        建立異動明細表

    判斷為不是最新或不完整的資料走下路
    1. 建立資料庫的登序字典
    2. 登序for迴圈處理
        1. 存在 登序字典
            時間處理(資料庫跟新資料比對)
            保持 新增 為最先發現時間
            保持 查詢時間 為最後發現時間
            保持 移除時間 為最先發現時間
        2. 不存在
            有異動 發現新資料
            1. 舊資料發現
                設為失效+移除時間
                建立登序總表

            2. 新資料發現
                變更總表狀態: 有效 不完整查有異動
                建立登序總表 建立異動明細表
                建立登序明細表
    4. 資料庫登序for迴圈處理(更新失效移除時間)
        1. 過濾未在登序清單的登序
        2. 判斷是失效狀態
        3. 查詢時間小於移除時間
            1. 寫入移除時間和查詢時間
            2. 建立登序明細表
    '''
    regno_dict = {}

    if rule_type == RuleTypeEnum.OWNER:
        RegnoSummary = LB_models.OwnerRegnoSummary
        regno_log_dict = regno_log.owners
        regno_len = 4
    else:
        RegnoSummary = LB_models.RightRegnoSummary
        regno_log_dict = regno_log.rights
        regno_len = 7

    property_count_dict = {PropertyTypeEnum.UNKNOWN: 0,
                            PropertyTypeEnum.GOVERMENT: 0,
                            PropertyTypeEnum.PRIVATE: 0,
                            PropertyTypeEnum.COMPANY: 0,
                            PropertyTypeEnum.RENTAL: 0,
                            PropertyTypeEnum.FINANCE: 0}

    regno_summary = RegnoSummary.objects.filter(summary_id=summary_id)
    regno_bulk_update = []
    regno_bulk_create = []
    add_list = [] # 登序異動表
    rm_list = [] # 登序異動表
    last_property_type = None

    if len(regno_log_dict) == 0:
        if regno_log.rules in [RuleTypeEnum.BOTH, rule_type]:
            regno_log_dict = {}
        else:
            return [], [], [], [], None

    if regno_log.rules in [RuleTypeEnum.BOTH, rule_type] and is_new:
        # 是完整且是新的

        if summary_id.is_valid_type // 10 == 4:
            # 總表無效轉換
            summary_id.is_valid_type = IsvalidTypeEnum.VALID_INVALID_CHANGE

        regno_summary_is_valid = regno_summary.filter(is_valid_type=IsvalidTypeEnum.VALID)
        regno_summary_not_valid = regno_summary.exclude(is_valid_type=IsvalidTypeEnum.VALID)

        # 有效變成無效
        for regno_id in regno_summary_is_valid:
            regno_id.is_valid_type = IsvalidTypeEnum.INVALID
            regno_dict[regno_id.regno] = regno_id

        for regno, name in regno_log_dict.items():
            regno_check_key = f"{summary_id.lbkey}-{regno}"
            regno_id = regno_dict.get(regno)

            if (len(regno) > regno_len) or ('\n0' in name) or (regno.isalnum() == False):
                # 登序長度異常 或 名子內包含登序 或 登序包含非英文數字
                return [], [], [], [], TaskTypeEnum.DISCARD

            check_regno_name(regno_id, name)
            if regno_id:
                regno_id.is_valid_type = IsvalidTypeEnum.VALID
                regno_id.query_time = regno_log.query_time # 保持 查詢時間 為最後發現時間

                regno_bulk_update.append(regno_id)
            else:
                if regno_summary_not_valid.filter(regno=regno).exists():
                    # 已經失效 卻在完整新資料
                    return [], [], [], [], TaskTypeEnum.ABNORMAL_PARSER

                else:
                    # 有異動 完整新資料 發現新登序
                    if regno_check_key in regno_check_repeat.keys():
                        regno_id = regno_check_repeat[regno_check_key]
                    else:
                        property_type = check_property_one(name, obligee_dict)
                        regnoKarg = {
                            'summary_id': summary_id,
                            'regno': regno,
                            'name': name,
                            'property_type': property_type,
                            'is_valid_type': IsvalidTypeEnum.VALID,
                            'query_time': regno_log.query_time,
                            'add_time': regno_log.query_time,
                        }
                        regno_id = RegnoSummary(**regnoKarg)
                        regno_check_repeat[regno_check_key] = regno_id
                        regno_bulk_create.append(regno_id)
                        add_list.append(regno)

            property_count_dict[regno_id.property_type] += 1
            last_property_type = regno_id.property_type

        for regno_id in regno_summary_is_valid:
            # 有異動 資料被移除了 也要建立明細表
            if regno_id.is_valid_type == IsvalidTypeEnum.INVALID:
                regno_id.remove_time = regno_log.query_time
                regno_bulk_update.append(regno_id)
                rm_list.append(regno_id.regno)
        set_propertyType(rule_type, summary_id, propertyType_id, property_count_dict, list(regno_log_dict), last_property_type)
    else:
        for regno_id in regno_summary:
            regno_dict[regno_id.regno] = regno_id

        for regno, name in regno_log_dict.items():
            regno_check_key = f"{summary_id.lbkey}-{regno}"
            regno_id = regno_dict.get(regno)

            if (len(regno) > regno_len) or ('\n0' in name) or (regno.isalnum() == False):
                # 登序長度異常 或 名子內包含登序 或 登序包含非英文數字
                return [], [], [], [], TaskTypeEnum.DISCARD

            if regno_id:
                if regno_log.query_time < regno_id.add_time:
                    regno_id.add_time = regno_log.query_time # 保持 新增時間 為最先發現時間

                if regno_log.query_time > regno_id.query_time:
                    regno_id.query_time = regno_log.query_time # 保持 查詢時間 為最後發現時間

                if regno_id.is_valid_type // 10 == 4 and regno_id.remove_time < regno_log.query_time:
                    regno_id.remove_time = regno_log.query_time

                check_regno_name(regno_id, name)

                regno_bulk_update.append(regno_id)

            else: # 有異動 發現新資料
                if regno_check_key in regno_check_repeat.keys():
                    regno_id = regno_check_repeat[regno_check_key]
                else:
                    property_type = check_property_one(name, obligee_dict)
                    regnoKarg = {
                        'summary_id': summary_id,
                        'regno': regno,
                        'name': name,
                        'property_type': property_type,
                        'is_valid_type': IsvalidTypeEnum.VALID,
                        'query_time': regno_log.query_time,
                        'add_time': regno_log.query_time,
                    }
                    if is_new:
                        # 是最新 不完整 有新增
                        summary_id.is_valid_type = IsvalidTypeEnum.VALID_NEED_QUERY
                        add_list.append(regno)
                    else:
                        regnoKarg['is_valid_type'] = IsvalidTypeEnum.INVALID
                        regnoKarg['remove_time'] = regno_log.query_time # 舊資料發現 設為失效+移除時間

                    regno_id = RegnoSummary(**regnoKarg)
                    regno_check_repeat[regno_check_key] = regno_id
                    regno_bulk_create.append(regno_id)
    return regno_bulk_update, regno_bulk_create, add_list, rm_list, None

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

def check_continuous(df, or_str, or_list):
    # 3. 確認連貫性
    output = []
    if or_str == 'owners':
        owner_df = df[df['rules'].isin([0,3])].reset_index(drop=True)
    else:
        owner_df = df[df['rules'].isin([1,3])].reset_index(drop=True)

    err_area = [] # 存放錯誤的範圍
    err_list = [] # 存放範圍索引
    err_regno = [] # 有不連貫的登序
    cut_post = 0
    # 3-1. 分所他 取連續清單
    for index in range(len(or_list)):
        owner = or_list[index]
        owner_df['exclude'] = owner_df.apply(contains_regno, axis=1, args=(or_str, owner))
        t_exclude = list(owner_df[owner_df['exclude']==True].index)

        if index == 0:
            # 最小值不在第1筆 = 第1筆有問題
            if owner_df.iloc[0][or_str] and (0 not in t_exclude) and len(t_exclude)>3:
                output.append(owner_df.iloc[0]['id'])
                return output, err_regno

        if (t_exclude[-1] - t_exclude[0]) == (len(t_exclude)-1):
            # 判斷是否連續(長度=尾-頭)
            continue
        t_match = [] # 連續清單
        s = []
        for i in t_exclude:
            if len(s) == 0 or s[-1] + 1 == i:
                s.append(i)
            else:
                t_match.append(s)
                s = []
                s.append(i)
        t_match.append(s)

        if len(t_match)-1 > cut_post:
            # 計算最大段點數量
            cut_post = len(t_match)-1

        # 3-1-1. 不連貫循環
        for i in range(len(t_match)-1):
            # print(t_match)
            f_set = set([x for x in range(t_match[i][-1]+1, t_match[i+1][0])])
            f_len = len(f_set)
            t_set = set(t_match[i])
            t_len = len(t_set)
            t1_set = set(t_match[i+1])
            t1_len = len(t1_set)
            err_regno.append(owner)

            # 3-1-1-1 t比f大 t1比f大 = f 問題
            if (t_len >= f_len < t1_len) or (t_len > f_len <= t1_len):
                if f_set not in err_area:
                    err_area.append(f_set)
                err_list.append(err_area.index(f_set))
            # 3-1-1-2 t比t1大 f比t1大 = t1 問題
            elif t_len >= t1_len < f_len:
                if t1_set not in err_area:
                    err_area.append(t1_set)
                err_list.append(err_area.index(t1_set))
            # 3-1-1-3 t1比t大 f比t大 = t 問題
            elif t1_len >= t_len < f_len:
                if t_set not in err_area:
                    err_area.append(t_set)
                err_list.append(err_area.index(t_set))
            # 3-1-1-4 f只有1筆 t1大於3筆 = f 問題 (針對錯誤在第2筆)
            elif f_len == 1 and t1_len >= 3:
                if f_set not in err_area:
                    err_area.append(f_set)
                err_list.append(err_area.index(f_set))

    if cut_post > 1:
        cut_post = 1

    # 3-3. 統計
    if err_list:
        for x, i in Counter(err_list).most_common(cut_post):
            output.extend(list(owner_df[owner_df.index.isin(list(err_area[x]))]['id']))
    return output, err_regno

def check_history(regno_log_qs:List[land.models.RegnoLog], init_regno_log:land.models.RegnoLog):
    # 1. 廢棄空資料
    discard_ids = []
    df = pd.DataFrame(regno_log_qs.values('id', 'owners', 'rights', 'query_time', 'rules'))
    df['exclude'] = df.apply(exclude_null, axis=1)
    df['owners'] = df.apply(check_or_type, axis=1, args=('owners', ))
    df['rights'] = df.apply(check_or_type, axis=1, args=('rights', ))

    exclude_df = df[df['exclude'] == True]
    discard_ids.extend(list(exclude_df.id))
    df.drop(exclude_df.index, inplace=True)

    # 1. 過濾當日重複資料
    df['query_time'] = pd.to_datetime(df['query_time']).dt.date
    new_df = df.groupby(['query_time', 'rules']).last()
    exclude_ids = list(set(df['id']) - set(new_df['id']))
    discard_ids.extend(exclude_ids)
    regno_log_qs.filter(id__in=discard_ids).update(state=TaskTypeEnum.DISCARD)
    exclude_df = df[df['id'].isin(exclude_ids)]
    df.drop(exclude_df.index, inplace=True)
    df.reset_index(drop=True)

    # 2. 取歷史登序清單
    owners_set = set()
    rights_set = set()
    for regno_log in df.itertuples():
        owners_set.update(set(list(regno_log.owners)))
        rights_set.update(set(list(regno_log.rights)))

    owners = sorted(list(owners_set))
    rights = sorted(list(rights_set))

    # 3. 比對不連續的資料
    o_output, o_err_regno = check_continuous(df, 'owners', owners)
    r_output, r_err_regno = check_continuous(df, 'rights', rights)

    output = list(set(o_output+r_output))
    if output:
        if (3 <= len(regno_log_qs) < 8 and len(output) < 2) or \
            (8 <= len(regno_log_qs) < 40 and len(output) < 6) or \
            (40 <= len(regno_log_qs) and len(output) < 15):
            # 要改變資料庫 也要改變當前log狀態
            regno_log_qs.filter(id__in=output).update(state=TaskTypeEnum.DISCARD)

            if init_regno_log.id not in output:
                init_regno_log.state=TaskTypeEnum.INIT
            else:
                init_regno_log.state=TaskTypeEnum.DISCARD
        else:
            logger.error("{} {} {}\n{}".format(init_regno_log.lbkey, o_err_regno, r_err_regno, output))
            regno_log_qs.filter(state__in=[TaskTypeEnum.INIT, TaskTypeEnum.PARSER]).update(state=TaskTypeEnum.ABNORMAL)
            init_regno_log.state=TaskTypeEnum.ABNORMAL
        return True
    return False

def create_lbor(regno_log_list, lbEnum):
    obligee_dict = get_obligee()
    cache_dict = dict()
    if lbEnum == LBEnum.LAND:
        LB_models = land.models
    elif lbEnum == LBEnum.BUILD:
        LB_models = building.models
    else:
        return

    # 第零層 狀態變更
    for regno_log in regno_log_list:
        regno_log.state = TaskTypeEnum.PARSER
    LB_models.RegnoLog.objects.bulk_update(regno_log_list, fields=['state'])

    summary_bulk_create = []
    property_type_bulk_create = []
    summary_new_create_dict = {} # 第二層用
    lbkey_check_repeat = [] # 過濾地建號重複

    # 第一層 總表處理
    for regno_log in regno_log_list[::-1]:
        lbkey = regno_log.lbkey

        if lbkey in lbkey_check_repeat:
            # 處理重複地建號 (原先寫在第二層，但是被判斷成舊資料處理，log第1新第2舊)
            regno_log.state = TaskTypeEnum.ABNORMAL_REPEAT
            continue

        if lbEnum == LBEnum.LAND:
            main_num = lbkey[10:14]
            sub_num = lbkey[15:19]
        elif lbEnum == LBEnum.BUILD:
            main_num = lbkey[10:15]
            sub_num = lbkey[16:19]
        else:
            regno_log.state = TaskTypeEnum.DISCARD
            continue

        summarys = LB_models.Summary.objects.filter(lbkey=lbkey)

        if summarys.exists() == False:
            cityCodeTable, areaCodeTable, regionCodeTable = _get_CAR_table(lbkey, cache_dict)
            if cityCodeTable == None:
                # 無縣市行政區段小段
                regno_log.state = TaskTypeEnum.ABNORMAL_CAR
                continue

            if regno_log.is_no_list == True:
                # 無總表第一筆就失效
                regno_log.state = TaskTypeEnum.DISCARD
                continue

            # ------------------------------------------------
            # 第一筆資料正確性驗證 和 取得最舊的查詢時間
            # 登序連貫性驗證
            # ~~資料初始匯入時專用~~
            regno_log_qs = LB_models.RegnoLog.objects.filter(lbkey=lbkey, state__in=[TaskTypeEnum.INIT, TaskTypeEnum.PARSER], 
                rules=RuleTypeEnum.BOTH, is_no_list=False).order_by('query_time')
            if len(regno_log_qs) >= 3:
                if check_history(regno_log_qs, regno_log):
                    continue
            # 假如有斷點就不去解析
            # ------------------------------------------------

            summary_data = {
                'lbkey': lbkey,
                'city_code_table_id': cityCodeTable,
                'area_code_table_id': areaCodeTable,
                'region_code_table_id': regionCodeTable,
                'main_num': main_num,
                'sub_num': sub_num,
                'query_time': regno_log.query_time
                }

            if len(regno_log.owners) + len(regno_log.rights) == 0:
                summary_data['is_valid_type'] = IsvalidTypeEnum.VALID_NEED_QUERY

            summary_id = LB_models.Summary(**summary_data)
            summary_new_create_dict[lbkey] = summary_id
            summary_bulk_create.append(summary_id)
            property_type_bulk_create.append(LB_models.PropertyTypeSummary(lbkey=summary_id.lbkey, summary_id=summary_id))

        else:
            summary_id = summarys[0]
            regno_log.summary_id = summary_id

            # 總表已失效 卻還有log進來的處理
            if summary_id.is_valid_type == IsvalidTypeEnum.INVALID:
                if regno_log.is_no_list == False:
                    # 有效 回報異常
                    regno_log.state = TaskTypeEnum.ABNORMAL_PARSER
                    continue

            summary_new_create_dict[lbkey] = summarys[0]

            # 不是第一筆且沒有所他 >> 廢棄
            if len(regno_log.owners) + len(regno_log.rights) == 0 and regno_log.is_no_list == False:
                regno_log.state = TaskTypeEnum.DISCARD

        # 完成總表創建才新增
        lbkey_check_repeat.append(lbkey)

    # 第一層 總表 地建號所他型態統計表 創建
    LB_models.Summary.objects.bulk_create(summary_bulk_create)
    LB_models.PropertyTypeSummary.objects.bulk_create(property_type_bulk_create)

    # 第二層 登序總表處理
    summary_id_bulk_update = []
    propertyType_id_bulk_update = []
    regno_check_repeat = {} # 過濾登序重複

    o_all_regno_bulk_update = []
    o_all_regno_bulk_create = []
    r_all_regno_bulk_update = []
    r_all_regno_bulk_create = []

    regno_modified_bulk_create = []

    for regno_log in regno_log_list:
        if regno_log.state // 10 in [0, 4, 5]: # 狀態為異常 或待處理(上方轉換)
            continue

        if regno_log.summary_id == None:
            regno_log.summary_id = summary_new_create_dict.get(regno_log.lbkey)

            if regno_log.summary_id == None:
                regno_log.state = TaskTypeEnum.ABNORMAL_PARSER
                continue

        regno_log.state = TaskTypeEnum.COMPLETE

        summary_id = regno_log.summary_id # 會變動 要向外傳
        propertyType_id = summary_id.propertytypesummary # 會變動 要向外傳

        if regno_log.is_no_list == True:
            # 有總表的失效處理(無總表或異常，在第一階段就處理了)
            # 要處理總表失效log失效，總表有效log失效

            if regno_log.rules != RuleTypeEnum.BOTH:
                # 規則不是所他都查，直接廢棄
                regno_log.state = TaskTypeEnum.DISCARD

            is_summary_valid = False
            if summary_id.is_valid_type == IsvalidTypeEnum.VALID:
                is_summary_valid = True
                summary_id.is_valid_type = IsvalidTypeEnum.INVALID

            is_old_query_time = False
            if summary_id.remove_time and (summary_id.query_time < regno_log.query_time < summary_id.remove_time):
                is_old_query_time = True

            # 總表不是有效和是新的失效紀錄 或 失效比最後有效的時間還舊
            if (is_summary_valid or is_old_query_time) == False or (regno_log.query_time < summary_id.query_time):
                regno_log.state = TaskTypeEnum.DISCARD
                continue

            owner_qs = summary_id.ownerregnosummary_set.all()
            right_qs = summary_id.rightregnosummary_set.all()

            if len(owner_qs) == 0 and len(right_qs) == 0:
                lbkey_change = LB_models.LbkeyChange.objects.filter(old_lbkey=regno_log.lbkey)
                if lbkey_change.exists() == False:
                    # 在新舊轉換的舊 有出現 那就不刪除總表
                    # 總表 無所他權清單 刪除總表 廢棄相關log
                    summary_id.delete()
                    regno_log.state = TaskTypeEnum.DISCARD
                    regno_log.summary_id = None
                    regnoLogs = LB_models.RegnoLog.objects.filter(lbkey=regno_log.lbkey).exclude(id=regno_log.id)
                    for regnoLog in regnoLogs:
                        regnoLog.state = TaskTypeEnum.DISCARD
                        regno_log_list.append(regnoLog)
                    continue

            summary_id.remove_time = regno_log.query_time

            o_regno_bulk_update, o_rm_list = _invalid_lbor_regno(
                summary_id=summary_id, regno_log=regno_log, rule_type=RuleTypeEnum.OWNER, is_summary_valid=is_summary_valid, is_old_query_time=is_old_query_time)
            r_regno_bulk_update, r_rm_list = _invalid_lbor_regno(
                summary_id=summary_id, regno_log=regno_log, rule_type=RuleTypeEnum.RIGHT, is_summary_valid=is_summary_valid, is_old_query_time=is_old_query_time)

            summary_id.is_valid_type = IsvalidTypeEnum.INVALID
            summary_id_bulk_update.append(summary_id)

            o_rm_num = len(o_rm_list)
            r_rm_num = len(r_rm_list)

            regno_modified_bulk_create.append(LB_models.RegnoModified(
                regno_log_id=regno_log,
                summary_id=summary_id,
                owner_rm_list=o_rm_list,
                right_rm_list=r_rm_list,
                owner_rm_num=o_rm_num,
                right_rm_num=r_rm_num,
                change_time=regno_log.query_time,
            ))
            o_all_regno_bulk_update.extend(o_regno_bulk_update)
            r_all_regno_bulk_update.extend(r_regno_bulk_update)

            # 重置型態統計表
            propertyType_id.o_unknown_num = 0
            propertyType_id.o_goverment_num = 0
            propertyType_id.o_private_num = 0
            propertyType_id.o_company_num = 0
            propertyType_id.o_rental_num = 0
            propertyType_id.o_finance_num = 0
            propertyType_id.last_o_property_type = None
            propertyType_id.r_unknown_num = 0
            propertyType_id.r_goverment_num = 0
            propertyType_id.r_private_num = 0
            propertyType_id.r_company_num = 0
            propertyType_id.r_rental_num = 0
            propertyType_id.r_finance_num = 0
            propertyType_id.last_r_property_type = None
            summary_id.owners_num = 0
            summary_id.rights_num = 0
        else:

            # 判斷查詢時間
            is_new = False
            if regno_log.query_time >= summary_id.query_time:
                is_new = True

            o_regno_bulk_update, o_regno_bulk_create, o_add_list, o_rm_list, o_task_type = _create_lbor_regno(
                summary_id, propertyType_id, regno_log, LB_models, RuleTypeEnum.OWNER, is_new, obligee_dict, regno_check_repeat)
            r_regno_bulk_update, r_regno_bulk_create, r_add_list, r_rm_list, r_task_type = _create_lbor_regno(
                summary_id, propertyType_id, regno_log, LB_models, RuleTypeEnum.RIGHT, is_new, obligee_dict, regno_check_repeat)

            if o_task_type:
                regno_log.state = o_task_type
            elif r_task_type:
                regno_log.state = r_task_type
            else:
                if is_new:
                    # 避免解析異常回寫到查詢時間
                    summary_id.query_time = regno_log.query_time

                o_all_regno_bulk_update.extend(o_regno_bulk_update)
                o_all_regno_bulk_create.extend(o_regno_bulk_create)

                r_all_regno_bulk_update.extend(r_regno_bulk_update)
                r_all_regno_bulk_create.extend(r_regno_bulk_create)

                o_add_num = len(o_add_list)
                o_rm_num = len(o_rm_list)
                r_add_num = len(r_add_list)
                r_rm_num = len(r_rm_list)

                if (o_add_num+o_rm_num+r_add_num+r_rm_num) > 0:
                    # 有異動的資料處理
                    regno_modified_bulk_create.append(LB_models.RegnoModified(
                        regno_log_id=regno_log,
                        summary_id=summary_id,
                        owner_add_list=o_add_list,
                        owner_rm_list=o_rm_list,
                        right_add_list=r_add_list,
                        right_rm_list=r_rm_list,
                        owner_add_num=o_add_num,
                        owner_rm_num=o_rm_num,
                        right_add_num=r_add_num,
                        right_rm_num=r_rm_num,
                        change_time=regno_log.query_time,
                    ))
                else:
                    if is_new:
                        # 避免解析異常回寫到查詢時間
                        summary_id.query_time = regno_log.query_time
                    regno_log.state = TaskTypeEnum.COMPLETE_NO_CHANGE

            if regno_log.rules == RuleTypeEnum.BOTH and is_new == True and (len(regno_log.owners) + len(regno_log.rights) > 0):
                # 1. 規則是全查 2. 是最新的 3. 有資料
                summary_id.is_valid_type = IsvalidTypeEnum.VALID

        summary_id_bulk_update.append(summary_id)
        propertyType_id_bulk_update.append(propertyType_id)

    LB_models.Summary.objects.bulk_update(summary_id_bulk_update, fields=['query_time', 'owners_num', 'rights_num', 'is_valid_type', 'remove_time'], batch_size=1000)
    LB_models.PropertyTypeSummary.objects.bulk_update(propertyType_id_bulk_update, fields=[
        "o_unknown_num", "o_goverment_num", "o_private_num", "o_company_num", "o_rental_num", "o_finance_num", "last_o_property_type", 
        "r_unknown_num", "r_goverment_num", "r_private_num", "r_company_num", "r_rental_num", "r_finance_num", "last_r_property_type"
    ], batch_size=1000)
    LB_models.OwnerRegnoSummary.objects.bulk_update(o_all_regno_bulk_update, fields=['name', 'is_valid_type', 'query_time', 'add_time', 'remove_time'], batch_size=1000)
    LB_models.OwnerRegnoSummary.objects.bulk_create(o_all_regno_bulk_create, batch_size=1000)

    LB_models.RightRegnoSummary.objects.bulk_update(r_all_regno_bulk_update, fields=['name', 'is_valid_type', 'query_time', 'add_time', 'remove_time'], batch_size=1000)
    LB_models.RightRegnoSummary.objects.bulk_create(r_all_regno_bulk_create, batch_size=1000)

    LB_models.RegnoLog.objects.bulk_update(regno_log_list, fields=['state', 'summary_id'], batch_size=1000)
    LB_models.RegnoModified.objects.bulk_create(regno_modified_bulk_create, batch_size=1000)


def _invalid_lbor_regno(
    summary_id:land.models.Summary|building.models.Summary, 
    regno_log:land.models.RegnoLog|building.models.RegnoLog, 
    rule_type:RuleTypeEnum,
    is_summary_valid:bool,
    is_old_query_time:bool):

    # 登序異動表
    rm_list = []

    # 登序更新
    regno_bulk_update = []

    if rule_type == RuleTypeEnum.OWNER:
        regno_qs = summary_id.ownerregnosummary_set.all()
    else:
        regno_qs = summary_id.rightregnosummary_set.all()

    if is_summary_valid:
        # 總表有效 log失效
        for regno_id in regno_qs:
            if regno_id.is_valid_type == IsvalidTypeEnum.VALID:
                regno_id.is_valid_type = IsvalidTypeEnum.INVALID
                regno_id.remove_time = regno_log.query_time
                regno_bulk_update.append(regno_id)
                rm_list.append(regno_id.regno)

    elif is_old_query_time:
        # 總表失效 log失效 且是舊的
        for regno_id in regno_qs:
            if regno_id.remove_time >= regno_log.query_time:
                regno_id.remove_time = regno_log.query_time
                regno_bulk_update.append(regno_id)

    return regno_bulk_update, rm_list


def _create_lbor_log(validated_datas):
    # 建立 土建的登序紀錄表
    land_bulk_create = []
    land_bulk_create_fast = [] # 加速清單
    land_task_bulk_update = []

    buliding_bulk_create = []
    buliding_bulk_create_fast = [] # 加速清單
    buliding_task_bulk_update = []

    for item in validated_datas:
        lbkey = item['lbkey']
        lbEnum = getLBEnum(lbkey)

        task_id = item['task_id']
        is_fast = item['is_fast']

        if lbEnum == LBEnum.LAND:
            bulk_create = land_bulk_create
            bulk_create_fast = land_bulk_create_fast
            task_bulk_update = land_task_bulk_update
            LB_models = land.models
        elif lbEnum == LBEnum.BUILD:
            bulk_create = buliding_bulk_create
            bulk_create_fast = buliding_bulk_create_fast
            task_bulk_update = buliding_task_bulk_update
            LB_models = building.models
        else:
            continue

        lborTaskQs = LB_models.LborTaskPool.objects.filter(id=task_id)
        now = timezone.now()
        for lborTask in lborTaskQs:
            lborTask.state = TaskTypeEnum.COMPLETE
            lborTask.complete_time = now
            task_bulk_update.append(lborTask)

        regno_log_kwarg = {
            'lbkey': lbkey,
            'query_system': item['query_system'],
            'owners': item['owners'],
            'rights': item['rights'],
            'rules': item['rules'],
            'query_time': item['query_time'],
            'is_no_list': item['is_no_list'],
            'task_id': task_id,
            'inquirer_id': item.get('user')
        }

        if is_fast:
            regno_log_kwarg['state'] = TaskTypeEnum.PROCESSING
            bulk_create_fast.append(
                LB_models.RegnoLog(**regno_log_kwarg)
            )
        else:
            bulk_create.append(
                LB_models.RegnoLog(**regno_log_kwarg)
            )
    # --------------
    land_regno_log = land.models.RegnoLog.objects.bulk_create(land_bulk_create + land_bulk_create_fast)
    land.models.LborTaskPool.objects.bulk_update(land_task_bulk_update, fields=['state', 'complete_time'])
    if land_bulk_create_fast:
        create_lbor(land_bulk_create_fast, LBEnum.LAND)
    # --------------
    building_regno_log = building.models.RegnoLog.objects.bulk_create(buliding_bulk_create + buliding_bulk_create_fast)
    building.models.LborTaskPool.objects.bulk_update(buliding_task_bulk_update, fields=['state', 'complete_time'])
    if buliding_bulk_create_fast:
        create_lbor(buliding_bulk_create_fast, LBEnum.BUILD)
    # --------------
    return land_regno_log, building_regno_log


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


class FeedbackLborListSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        with transaction.atomic():
            return _create_lbor_log(validated_data)

class FeedbackLborSerializer(serializers.Serializer):
    lbkey = serializers.CharField(default="", help_text='A_01_0600_0000-0000', min_length=19, max_length=19)
    owners = serializers.JSONField(default={}, help_text='{"0001": "測＊＊"}')
    rights = serializers.JSONField(default={}, help_text='{"0001000": "測試"}')
    is_no_list = serializers.BooleanField(default=False, help_text='查無列表')
    query_time = serializers.DateTimeField(default="2022-5-5 10:10:10")
    query_system = serializers.ChoiceField(choices=QuerySystemEnum.choices(), default=QuerySystemEnum.LOR_V2, help_text=str(QuerySystemEnum.choices()))
    rules = serializers.ChoiceField(choices=RuleTypeEnum.choices(), default=RuleTypeEnum.BOTH, help_text=str(RuleTypeEnum.choices()))
    is_fast = serializers.BooleanField(default=False, help_text='是否要加速')
    task_id = serializers.IntegerField(default=None, help_text='任務代號')

    class Meta:
        list_serializer_class = FeedbackLborListSerializer

    def create(self, validated_data):
        with transaction.atomic():
            return _create_lbor_log([validated_data])

class RegionQuestionSerializer(serializers.Serializer):
    lbkey = serializers.CharField(default="A_01_0600_0000-0000,A_01_0600_0000-0001", help_text='多筆,分隔')

class RegionQuestionTimeSerializer(serializers.Serializer):
    lbkey = serializers.CharField(default="A_01_0600_0000-0000", min_length=19, max_length=19)
    query_time = serializers.DateTimeField(default="2022-5-5 10:10:10")

class RegionListSerializer(serializers.Serializer):
    lbkey = serializers.CharField(default="A_01_0600_0000-0000,A_01_0600_0000-0001", help_text='多筆,分隔')
    is_all = serializers.BooleanField(default=False, help_text='取全部的登序')

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

class LborTaskListSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        # _create_lbor_task(validated_data)
        return True

class LborTaskSerializer(serializers.Serializer):
    lbkey_list = serializers.ListField(default=[], help_text=['A_01_0600_0000-0000'])
    forcibly = serializers.BooleanField(default=False, help_text='強制調閱')
    priority = serializers.IntegerField(default=70, help_text='優先度')
    rules = serializers.ChoiceField(choices=RuleTypeEnum.choices(), default=RuleTypeEnum.BOTH, help_text=str(RuleTypeEnum.choices()))
    class Meta:
        list_serializer_class = LborTaskListSerializer

    def create(self, validated_data):
        # _create_lbor_task([validated_data])
        return True

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

class GetTpTaskSerializer(serializers.Serializer):
    query_system = serializers.IntegerField(default=QuerySystemEnum.GAIAS_PC.value, help_text=str(QuerySystemEnum.choices()))
    count = serializers.IntegerField(default=1, min_value=1, max_value=50, help_text='數量')
    city = serializers.CharField(default="", min_length=0, max_length=1, help_text='縣市')
    lbtype = serializers.CharField(default="L", min_length=1, max_length=1, help_text='土建類別')
    rule = serializers.JSONField(default={
        "priority__gte": 80, "priority__lte": 90, 
        }, help_text='優先範圍')
    debug = serializers.BooleanField(default=False, help_text='測試模式，不改寫任務')

class GetLborTaskSerializer(serializers.Serializer):
    count = serializers.IntegerField(default=20, min_value=1, max_value=50, help_text='數量')
    city = serializers.CharField(default="A", min_length=1, max_length=9, help_text='縣市')
    lbtype = serializers.CharField(default="L", min_length=1, max_length=1, help_text='土建類別')
    rule = serializers.JSONField(default={
        "priority__gte": 80, "priority__lte": 90, 
        "owners_num__gte": -1, "owners_num__lte": 100,
        "rights_num__gte": -1, "rights_num__lte": 100,
        }, help_text='填入所、他、優先範圍')
    exclude = serializers.JSONField(default={}, help_text='所他排除清單 {"owners_num": 1, "rights_num": 1}')
    debug = serializers.BooleanField(default=False, help_text='測試模式，不改寫任務')

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

def _update_lbor_error(validated_datas):
    for item in validated_datas:
        lbkey = item['lbkey']
        lbEnum = getLBEnum(lbkey)
        task_id = item['task_id']
        extra = item['extra']
        if lbEnum == LBEnum.LAND:
            LB_models = land.models
        elif lbEnum == LBEnum.BUILD:
            LB_models = building.models
        else:
            continue

        task_pool_qs = LB_models.LborTaskPool.objects.filter(id=task_id, state__in=[TaskTypeEnum.PROCESSING, TaskTypeEnum.INIT])
        if task_pool_qs.exists():
            task_pool = task_pool_qs[0]
            new_extra = {**(task_pool.extra), **(extra)}
            task_pool.state = TaskTypeEnum.ABNORMAL
            task_pool.extra = new_extra
            task_pool.save()

        # TODO 後續可以銜接，查詢失敗的自動處理方式
        # 爬蟲回填 task_pool.extra 的內容
        # 1. {"msg": "無此段小段"}
        # 4. {"msg": "群旋error"}


class FeedbackLborErrorListSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        with transaction.atomic():
            _update_lbor_error(validated_data)
        return True


class FeedbackLborErrorSerializer(serializers.Serializer):
    lbkey = serializers.CharField(default="", help_text='A_01_0600_0000-0000', min_length=19, max_length=19) # 用來區分土建
    task_id = serializers.IntegerField(default=None, help_text='任務代號')
    extra = serializers.JSONField(default={}, help_text='異常回報: {"msg":"查無此地建號資料"}')

    class Meta:
        list_serializer_class = FeedbackLborErrorListSerializer

    def create(self, validated_data):
        with transaction.atomic():
            _update_lbor_error([validated_data])
        return True

def _update_tp_error(validated_datas):
    for item in validated_datas:
        lbkey = item['lbkey']
        lbEnum = getLBEnum(lbkey)
        task_id = item['task_id']
        extra = item['extra']
        if lbEnum == LBEnum.LAND:
            LB_models = land.models
        elif lbEnum == LBEnum.BUILD:
            LB_models = building.models
        else:
            continue

        task_pool_qs = LB_models.TpTaskPool.objects.filter(id=task_id, state__in=[TaskTypeEnum.PROCESSING, TaskTypeEnum.INIT])
        if task_pool_qs.exists():
            task_pool = task_pool_qs[0]
            new_extra = {**(task_pool.extra), **(extra)}
            task_pool.state = TaskTypeEnum.ABNORMAL
            task_pool.extra = new_extra
            task_pool.save()

        # TODO 後續可以銜接，查詢失敗的自動處理方式
        # 爬蟲回填 task_pool.extra 的內容
        # 1. {"msg": "無此段小段"}
        # 2. {"msg": "特定人數太多"}
        # 3. {"msg": "群旋error"}
        # 4. {"msg": "人數太多"}


class FeedbackTpErrorListSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        with transaction.atomic():
            _update_tp_error(validated_data)
        return True


class FeedbackTpErrorSerializer(serializers.Serializer):
    lbkey = serializers.CharField(default="", help_text='A_01_0600_0000-0000', min_length=19, max_length=19) # 用來區分土建
    task_id = serializers.IntegerField(default=None, help_text='任務代號')
    extra = serializers.JSONField(default={}, help_text='異常回報: {"msg":"查無此地建號資料"}')

    class Meta:
        list_serializer_class = FeedbackTpErrorListSerializer

    def create(self, validated_data):
        with transaction.atomic():
            _update_tp_error([validated_data])
        return True


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


class SetBlackListDetailSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        res = _create_blacklist(validated_data)
        return res

class SetBlackDetailSerializer(serializers.Serializer):
    lbkey = serializers.CharField(default="A_01_0600_0000-0000", min_length=19, max_length=19, help_text='地建號')
    query_system = serializers.ChoiceField(choices=QuerySystemEnum.choices(), default=QuerySystemEnum.LOR_V2, help_text=str(QuerySystemEnum.choices()))
    lbor_tp_type = serializers.ChoiceField(choices=LborTpTypeEnum.choices(), default=LborTpTypeEnum.LBOR, help_text=str(LborTpTypeEnum.choices()))
    remark = serializers.CharField(default='', allow_null=True, help_text='群旋error(不填就是取用模式)')

    class Meta:
        list_serializer_class = SetBlackListDetailSerializer

    def create(self, validated_data):
        # with transaction.atomic():
        res = _create_blacklist([validated_data])
        return res

class StatsChartLineSerializer(serializers.Serializer):
    start_date = serializers.DateField(default='', allow_null=True, help_text='2021-01-01')
    end_date = serializers.DateField(default='', allow_null=True, help_text='2021-01-01')
    queryType = serializers.IntegerField(default=0, allow_null=True, help_text='lbor 或 tp')
    city = serializers.CharField(default='', allow_null=True, allow_blank=True, help_text='A')
    area = serializers.CharField(default='', allow_null=True, allow_blank=True, help_text='A_01')
    
class StatsChartPieSerializer(serializers.Serializer):
    start_date = serializers.DateField(default='', allow_null=True, help_text='2021-01-01')
    end_date = serializers.DateField(default='', allow_null=True, help_text='2021-01-01')
    queryType = serializers.IntegerField(default=0, allow_null=True, help_text='lbor 或 tp')
    city_list = serializers.ListField(default=list, allow_null=True, help_text='城市列表')    

class StatsChartBarSerializer(serializers.Serializer):
    pass

