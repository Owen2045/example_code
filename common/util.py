from unicodedata import name
from common.enums import PropertyTypeEnum, LBEnum, IsvalidTypeEnum
from common.address_re import CuttingAddress
from common.models import Obligee, RegionCodeTable

from django.db import connection, connections, close_old_connections, models, reset_queries
from django.core.mail import send_mail
from django.utils import timezone
from django.conf import settings

from datetime import date, datetime, timedelta
from dateutil import parser

# import land.land_serializers as L_s 
# import building.building_serializers as B_s

from scipy import stats
import pandas as pd
import objectpath
import collections
import functools
import requests
import cn2an
import json
import pytz
import time
import sys
import csv
import re

from rest_framework.views import exception_handler

import logging
logger = logging.getLogger(__name__)
tz = pytz.timezone(settings.TIME_ZONE)

LKEY_VALIDATION = re.compile(r"[A-Z]_[0-9]{2}_[0-9]{4}_[0-9]{4}-[0-9]{4}$")
BKEY_VALIDATION = re.compile(r"[A-Z]_[0-9]{2}_[0-9]{4}_[0-9]{5}-[0-9]{3}$")

def landKeyValidate(key):
    if LKEY_VALIDATION.match(key):
        return True
    return False

def buildingKeyValidate(key):
    if BKEY_VALIDATION.match(key):
        return True
    return False

def getLBEnum(lbkey):
    if landKeyValidate(lbkey):
        return LBEnum.LAND
    elif buildingKeyValidate(lbkey):
        return LBEnum.BUILD
    else:
        return LBEnum.UNKNOWN

MAX_COUNT = 3
max_dba_retries = 5
public_list = ['中華民國', '農田水利會']
finance_list = ['銀行', '漁會', '農會', '合作社', '人壽', '保險', '郵政']
rental_list = ['車租賃', '租賃', '中租']
private_list = ['*', '＊']

company_find_list = ['公司', '工會', '公會', '總會', '宮', '廟', '寺', '庵', '堂',
                    '殿', '祀', '壇', '教會', '商會', '祠', '中心', '社', '公業',
                    '宗親會', '農場', '精舍', '協會', '慈善會', '獅子會', '同鄉會', 
                    '聯合會', '學會', '委員會', '同濟會', '協進會', '校友會', '研究會', 
                    '神明會', '道院', '商業會', '健行會', '工業會', '佛院', '工廠', '苑', 
                    '高級中學', '財團法人', '社團法人', '同業公會', '公業法人', '慈祐宮',
                    '祭祀公業', '祭祀公會', '公業', '公號']
# company_find_list = ['財團法人', '社團法人', '同業公會', '公業法人', '慈祐宮']
# company_start_list = ['祭祀公業', '祭祀公會', '公業', '公號']

# 系統變數
SYSTEM_ENVIRONMENT = [
        {'env': 'default_system_L', 'integer': 2, 'remark': '預設查詢系統'},
        {'env': 'default_priority_L', 'integer': 70, 'remark': '預設優先度'},
        {'env': 'default_mark_only_L', 'integer': 0, 'remark': '預設只調標示'},
        {'env': 'default_system_B', 'integer': 2, 'remark': '預設查詢系統'},
        {'env': 'default_priority_B', 'integer': 70, 'remark': '預設優先度'},
        {'env': 'default_mark_only_B', 'integer': 0, 'remark': '預設只調標示'},
    ]
    
def dict_env():
    return {x.get('env') : x for x in SYSTEM_ENVIRONMENT}


# 判斷所他設定型態工具包(請搭配check_property服用)
def is_public(owner, property_type_list):
    if owner in property_type_list.get('goverment'):
        return True
    elif owner.replace('台', '臺') in property_type_list.get('goverment'):
        return True
    else:
        for i in public_list:
            if owner.find(i) >= 0:
                return True
        return False

def is_finance(owner, property_type_list):
    if owner in property_type_list.get('finance'):
        return True
    else:
        for i in finance_list:
            if owner.find(i) >= 0:
                return True
        return False

def is_rental(owner, property_type_list):
    if owner in property_type_list.get('rental'):
        return True
    else:
        for i in rental_list:
            if owner.find(i) >= 0:
                return True
        return False

def is_private(owner, property_type_list):
    for i in private_list:
        if owner.find(i) >= 0:
            return True
    return False


def is_company(owner, property_type_list):
    for i in company_find_list:
        if owner.find(i) >= 0:
            return True
    return False

# 製作所他型態dict
def get_obligee():
    obj_p = Obligee.objects.all()
    result = {}
    unknow = []
    goverment = []
    private = []
    finance = []
    rental = []
    company = []
    for i in obj_p:
        property_type = i.property_type
        name = i.name
        if property_type == 0:
            unknow.append(name)
        elif property_type == 1:
            goverment.append(name)
        elif property_type == 2:
            private.append(name)
        elif property_type == 3:
            finance.append(name)
        elif property_type == 4:
            rental.append(name)
        elif property_type == 5:
            company.append(name)
    result['unknow'] = unknow
    result['goverment'] = goverment
    result['private'] = private
    result['finance'] = finance
    result['rental'] = rental
    result['company'] = company
    return result

# 計算所他型態 input:list包dict
def check_property(regno_data, obligee_dict):
    # 判斷順序注意＝＝銀行機構 > 租貸 > 公司
    unknown_num, goverment_num, private_num, company_num, rental_num, finance_num, last_property_type = 0, 0, 0, 0, 0, 0, 0
    if regno_data:
        sort_dict = {}
        property_dict = {}
        for i in regno_data:                
            target_name = i.get('ownerName')
            regno = i.get('regodr')
            sort_dict[regno] = target_name
            if is_public(target_name, obligee_dict) == True:
                goverment_num += 1
                property_dict[target_name] = 1

            elif is_private(target_name, obligee_dict) == True:
                private_num += 1
                property_dict[target_name] = 2

            elif is_finance(target_name, obligee_dict) == True:
                finance_num += 1
                property_dict[target_name] = 5

            elif is_rental(target_name, obligee_dict) == True:
                rental_num += 1
                property_dict[target_name] = 4

            elif is_company(target_name, obligee_dict) == True:
                company_num += 1
                property_dict[target_name] = 3
                
            else:
                unknown_num += 1
                property_dict[target_name] = 0

        sort_reg = collections.OrderedDict(sorted(sort_dict.items()))
        last_reg = list(sort_reg.values())[-1]
        last_property_type = int(property_dict.get(last_reg, '0'))

    return unknown_num, goverment_num, private_num, company_num, rental_num, finance_num, last_property_type

# 計算所他型態 input:單筆字串
def check_property_one(regno_name, obligee_dict):
    if regno_name:
        if is_public(regno_name, obligee_dict) == True:
            return PropertyTypeEnum.GOVERMENT

        elif is_private(regno_name, obligee_dict) == True:
            return PropertyTypeEnum.PRIVATE

        elif is_finance(regno_name, obligee_dict) == True:
            return PropertyTypeEnum.FINANCE

        elif is_rental(regno_name, obligee_dict) == True:
            return PropertyTypeEnum.RENTAL

        elif is_company(regno_name, obligee_dict) == True:
            return PropertyTypeEnum.COMPANY

        else:
            return PropertyTypeEnum.UNKNOWN
    else:
        return PropertyTypeEnum.UNKNOWN

# 計算所他型態(拆謄本用)
def get_target_amount_one_str(target_str, obligee_dict):
    try:
        if is_public(target_str, obligee_dict) == True:
            res_p = PropertyTypeEnum.GOVERMENT
            res_s = '公'
            num = 0

        elif is_finance(target_str, obligee_dict) == True:
            res_p = PropertyTypeEnum.FINANCE
            res_s = '銀'
            num = 1
        elif is_rental(target_str, obligee_dict) == True:
            res_p = PropertyTypeEnum.RENTAL
            res_s = '租'
            num = 2
        elif is_private(target_str, obligee_dict) == True:
            res_p = PropertyTypeEnum.PRIVATE
            res_s = '私'
            num = 3
        elif is_company(target_str, obligee_dict) == True:
            res_p = PropertyTypeEnum.COMPANY
            res_s = '法'
            num = 4
        else:
            res_p = PropertyTypeEnum.UNKNOWN
            res_s = '未'
            num = 5
    except:
        res_p = PropertyTypeEnum.NONETYPE
        res_s = None
        num = 6
    return res_p, res_s, num

# 批量
def batch(iterable, n=1):
    l = len(iterable)
    for ndx in range(0, l, n):
        yield iterable[ndx:min(ndx + n, l)]


# sql連104db 指定db須到local_settings.py設定
def dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]

def get_dba(sql_cmd, db_name='land_data', retries=0, datarows=True, close=True):
    rows = dict()
    columns = list()
    while retries < max_dba_retries:
        try:
            if close:
                close_old_connections()
            with connections[db_name].cursor() as cursor:
                try:
                    cursor.execute(sql_cmd)
                    if datarows:
                        columns = [col[0] for col in cursor.description]
                        rows = dictfetchall(cursor)
                    cursor.close()
                except Exception as err:
                    print ('{} {} error: {}'.format(datetime.now(), get_dba.__name__, err))
            break
        except Exception as error:
            retries += 1
            time.sleep(1)
            print ('{} {} retries {} error: {}'.format(datetime.now(), get_dba.__name__, retries, error))
    return rows, columns

def get_map_dba(sql_cmd, db_name='map', retries=0, datarows=True, close=True):
    rows = dict()
    columns = list()
    while retries < max_dba_retries:
        try:
            if close:
                close_old_connections()
            with connections[db_name].cursor() as cursor:
                try:
                    cursor.execute(sql_cmd)
                    if datarows:
                        columns = [col[0] for col in cursor.description]
                        rows = dictfetchall(cursor)
                    cursor.close()
                except Exception as err:
                    print ('{} {} error: {}'.format(datetime.now(), get_dba.__name__, err))
            break
        except Exception as error:
            retries += 1
            time.sleep(1)
            print ('{} {} retries {} error: {}'.format(datetime.now(), get_dba.__name__, retries, error))
    return rows, columns

# 地址re
def address_re(address):
    take_list = ['一級', '二級', '門牌']
    done_str = None
    if address:
        try:
            re_address = CuttingAddress()
            t = re_address.start_from_here(address)
            for key in take_list:
                done_str += '{}'.format(t[key])
        except:
            pass
    return done_str

# 取所有登序api (土建要分開)
def find_all_regno(lbkey_list, regno_type='o', retry_count=0):
    while retry_count < MAX_COUNT:
        try:
            if lbkey_list:
                base_url = settings.LBOR_HOST
                token = settings.LBOR_INFO_TOKEN
                lbtype = getLBEnum(lbkey_list[0])
                url = '{}/infos/getownerlistV2/'.format(base_url)
                data = {
                    'lbtype':lbtype,
                    'token':token,
                    'lbkey_list': json.dumps(lbkey_list),
                    'regno_type': regno_type
                }
                a = requests.post(url, data=data)
                res = json.loads(a.text)
                return res
        except Exception as error:                
            print(f'get all regno error : {error}')       
            retry_count += 1
            time.sleep(1)

def time_proV2(time_data=None, plus_8=False):
    format_time = None
    if time_data:
        if isinstance(time_data, datetime):
            format_time = time_data  
            format_time = format_time.astimezone(tz)
        elif isinstance(time_data, date):
            format_time = datetime.combine(time_data, datetime.min.time()).astimezone(tz)
        elif isinstance(time_data, str):
            try:
                time_data = parser.parse(time_data).replace(tzinfo=None)
                format_time = time_data   
                format_time = format_time.astimezone(tz)
            except:
                pass
        else:
            try:
                format_time = str(time_data)
                format_time = parser.parse(format_time).replace(tzinfo=None)
                format_time = format_time.astimezone(tz)
            except Exception as e:
                pass
    if plus_8 == True and format_time:
        format_time = format_time + timedelta(hours=8)
    return format_time

def remove_duplicated_records(model, fields):
    """
    刪除資料庫重複項目
    Removes records from `model` duplicated on `fields`
    while leaving the most recent one (biggest `id`).
    """
    duplicates = model.objects.values(*fields)

    # override any model specific ordering (for `.annotate()`)
    duplicates = duplicates.order_by()

    # group by same values of `fields`; count how many rows are the same
    duplicates = duplicates.annotate(
        max_id=models.Max("id"), count_id=models.Count("id")
    )

    # leave out only the ones which are actually duplicated
    duplicates = duplicates.filter(count_id__gt=1)

    for duplicate in duplicates:
        to_delete = model.objects.filter(**{x: duplicate[x] for x in fields})

        # leave out the latest duplicated record
        # you can use `Min` if you wish to leave out the first record
        to_delete = to_delete.exclude(id=duplicate["max_id"])
        to_delete.delete()

def all_to_half(all_string):
    """全形轉半形"""
    half_string = None
    if all_string:
        half_string = ""
        for char in all_string:
            inside_code = ord(char)
            if inside_code == 12288:  # 全形空格直接轉換,全形和半形的空格的Unicode值相差12256
                inside_code = 32
            elif (inside_code >= 65281 and inside_code <= 65374):  # 全形字元（除空格）根據關係轉化,除空格外的全形和半形的Unicode值相差65248
                inside_code -= 65248
            half_string += chr(inside_code)
    return half_string


def half_to_all(ustring):
    """半形轉全形"""
    rstring = None
    if ustring:
        rstring = ""
        for uchar in ustring:
            inside_code = ord(uchar)
            if inside_code == 32:                 # 半形空格直接轉化
                inside_code = 12288
            elif 32 <= inside_code <= 126:        # 半形字元（除空格）根據關係轉化
                inside_code += 65248
            rstring += chr(inside_code)
    return rstring

# 104取謄本
class GetTranscriptHistory(object):

    def get_lbtype_str(self, lbtype, ortype='owner'):
        if lbtype == 'L':
            table_type = 'transcript_land'
            tran_lb = 'transcript_landtranscript'
            mark_lb = 'transcript_landmark'
        else:
            table_type = 'transcript_building'
            tran_lb = 'transcript_buildingtranscript'
            mark_lb = 'transcript_buildingmark'

        if ortype == 'owner':
            ortype = 'owner'
        else:
            ortype = 'creditor'
        return table_type, ortype, tran_lb, mark_lb

    def format_dataframe(self, data):
        qs_df_o = None
        if isinstance(data, list) == True:
            qs_df_o = pd.DataFrame.from_dict(data, orient='columns').dropna(subset=["lbkey", "query_time"], axis=0, how='any')
            qs_df_o['query_time'] = qs_df_o['query_time'].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S'))
            qs_df_o = qs_df_o.sort_values(by=['lbkey', 'regno', 'query_time']).reset_index(drop=True)
        return qs_df_o

    def main_job(self, lbkey_list, lbtype):
        result = {'status': 'NG', 'msg': ''}
        if lbkey_list and lbtype:
            table_type, ortype, tran_lb, mark_lb = self.get_lbtype_str(lbtype, ortype='owner')
            
            if isinstance(lbkey_list, list):
                if len(lbkey_list) == 1:
                    tup = str(tuple(lbkey_list)).replace(',', '')
                else:
                    tup = tuple(lbkey_list)
                sql_cmd_O = 'SELECT * FROM arsenal.{tr_lb}owner  WHERE lbkey in {lbk_str}'.format(tr_lb=table_type, lbk_str=tup)
                sql_cmd_C = 'SELECT * FROM arsenal.{tr_lb}creditor  WHERE lbkey in {lbk_str} and is_valid = 1'.format(tr_lb=table_type, lbk_str=tup)
                sql_cmd_M = 'SELECT T1.lbkey, T1.owners, T1.creditors, T2.total_area, T1.create_time as "query_time" FROM arsenal.{tran_lb} T1 \
                                LEFT JOIN arsenal.{mark_lb} T2 on T1.mark_id = T2.id WHERE T1.lbkey in {lbk_str}'.format(tran_lb=tran_lb, mark_lb=mark_lb, lbk_str=tup)
                # print(sql_cmd_O)
                result_owners, header_owner = get_dba(sql_cmd_O)
                result_creditor, header_creditor = get_dba(sql_cmd_C)
                result_mark, header_mark = get_dba(sql_cmd_M)
                result['mark'] = result_mark
                result['owner'] = result_owners
                result['creditor'] = result_creditor
                result['status'] = 'OK'
            else:
                result['msg'] = 'lbkey_list 須為list'
        else:
            result['msg'] = '請輸入 lbkey_list and lbtype'
        return result

# 104取標示部(綜合各種資料)
class GetLandMarkInfo(object):

    # 計算眾數
    def get_most(self, list):
        most=[]
        rule = False
        item_num = dict((item, list.count(item)) for item in list)
        for k,v in item_num.items():
            if v == max(item_num.values()) and v != 1:
                rule = True
                most.append(k)
        if rule:
            result = max(most)
        else:
            result = max(list)
        return result

    # 移除英數字
    def remove(self, text):
        remove_chars = '[0-9a-z]'
        return re.sub(remove_chars, '', text)

    # 把字串全形轉半形
    def strQ2B(self, ustring):
        ss = []
        for s in ustring:
            rstring = ""
            for uchar in s:
                inside_code = ord(uchar)
                if inside_code == 12288:  # 全形空格直接轉換
                    inside_code = 32
                elif (inside_code >= 65281 and inside_code <= 65374):  # 全形字元（除空格）根據關係轉化
                    inside_code -= 65248
                rstring += chr(inside_code)
            ss.append(rstring)
        return ''.join(ss)

    # 解門牌代碼用
    def get_char(self, city_id, code):
        url = 'https://104.yeshome.net.tw/api/bigdata/get_word.php'
        Data = {
            "city_id": city_id,
            "code": code,
            "out_type": 'json'
        }
        try:
            req_char = requests.post(url, data=Data, verify=False)
            req_char.encoding = 'utf8'
        except Exception as errors:
            req_char = None
        if req_char:
            if req_char.status_code == 200 and req_char.text:
                response_json = json.loads(req_char.text)
                if response_json['status'] and response_json['status']=='OK':
                    if response_json['word']:
                        return response_json['word']

        subject = '謄本新編碼'
        message = 'city_id：{}, code：{}'.format(city_id, code)
        se = ['richer@wsos.com.tw', 'tim@wsos.com.tw', 'kevin@wsos.com.tw', 'dennis@wsos.com.tw']
        host = 'yhsc@wsos.com.tw'
        send_mail(
            subject,
            message,
            host,
            se,
            html_message=None,
        )
        return '❎'

    def land_mark(self, lkey_list):
        start_t = time.perf_counter()
        result = {'status': 'NG', 'msg': ''}
        rows = []
        bkey_dict = {}
        build_list_t = []
        today = str(int(str(timezone.now())[:7].replace('-',''))-191100)
        lkeys_sql_str = "'" + "','".join(lkey_list) + "'"
        try:
            sql_cmd = "SELECT a.lkey, city_name, area_name, region_name, a.is_valid, ifnull(ab.land_area_size, land_area) as land_area, land_zone, building_num, locate_bkey, \
                        ab.land_notice_value_date,  ab.land_notice_value, ab.land_notice_price, ab.land_notice_price_date, ab.size_changed, \
                        ifnull(ca.owners_num,'') as 'owners_num', ifnull(instr(f.other_remark,'三七五'), '') as other_remark, \
                        ifnull(ad.plan_name, '') as 'plan_name', ad.valid as devel_valid, b.urban_name, c.create_time, c.last_update_time as update_time, \
                        f.reg_date, f.reg_date_str, f.reg_reason, f.land_purpose, f.land_level, \
                        if(owners_num>0 AND owners_goverment_num>0 AND owners_goverment_num=owners_num, '公法人', \
                            if(owners_num>0 AND owners_goverment_num>0 AND owners_goverment_num!=owners_num AND owners_unknown_num=0, '部分公有', \
                                if(owners_num>0 AND owners_goverment_num=0 AND owners_private_num=owners_num, '自然人', \
                                    if(owners_num>0 AND owners_goverment_num=0 AND owners_private_num=0 AND owners_unknown_num=0, '私法人', \
                                        if(owners_num>0 AND owners_goverment_num=0 AND owners_private_num!=owners_num AND owners_unknown_num=0, '非公有', \
                                            if(owners_num>0 AND owners_unknown_num!=0, '權屬樣態未知', '')))))) as 'owner_type', \
                        if(f.land_type!='（空白）' and f.using_zone!='（空白）' and (f.land_type!='' and f.using_zone!=''), land_type,'') as 'land_type'\
                        FROM land_data.land_lkey_list a\
                        left join land_data.land_notice_vp_list ab on a.lkey=ab.lkey\
                        left join land_data.land_use_zone b on a.lkey=b.lkey\
                        left join land_data.developement_landdevelopementlkeyslist ac on a.lkey=ac.lkey\
                        left join land_data.developement_landdevelopementlist ad on ad.id=ac.plan_id\
                        left join lbor_info.infos_landprofilev2 c on a.lkey=c.lbkey\
                        left join lbor_info.infos_landinfochangev2 ca on c.info_id=ca.id\
                        left join arsenal.transcript_landtranscriptindex d on a.lkey=d.lbkey\
                        left join arsenal.transcript_landtranscript e on e.id=d.transcript_id\
                        left join arsenal.transcript_landmark f on f.id=e.mark_id\
                        left join bigdata.city g on substr(a.lkey,1,1)=g.city_id\
                        left join bigdata.area h on substr(a.lkey,1,4)=h.area_id\
                        left join bigdata.region j on substr(a.lkey,1,9)=j.region_id\
                        WHERE a.lkey in ({}) ORDER BY a.lkey ASC;".format(lkeys_sql_str)
            result_lands, header = get_dba(sql_cmd)
            for result_land in result_lands:
                is_valid = result_land['is_valid']
                region = result_land['lkey'][:10]
                lkey = result_land['lkey']
                lno = result_land['lkey'][10:]
                reg_date = result_land['reg_date']
                reg_date_str = result_land['reg_date_str']
                reg_reason = result_land['reg_reason']
                land_purpose = result_land['land_purpose']
                land_level = result_land['land_level']
                city_name = result_land['city_name']
                area_name = result_land['area_name']
                region_name = result_land['region_name']
                if result_land['devel_valid']:
                    plan_name = result_land['plan_name'].replace('(元宏繪製)','') if '(元宏繪製)' in result_land['plan_name'] else result_land['plan_name']
                    plan_name = result_land['plan_name'].replace('(元宏繪製）','') if '(元宏繪製）' in plan_name else plan_name
                else:
                    plan_name = ''
                owners_num = result_land['owners_num'] if result_land['owners_num'] else 0
                owner_type = result_land['owner_type']
                if owner_type == '權屬樣態未知':
                    owner_type = ''
                land_area = result_land['land_area'] if result_land['land_area'] else 0
                land_zone = result_land['land_zone'] if result_land['land_zone'] else ''
                urban_name = result_land['land_type']
                if urban_name == '':
                    urban_name = result_land['urban_name']
                    urban_type = '都內'
                else:
                    urban_type = '都外'
                if result_land['land_notice_value_date'] and result_land['land_notice_value_date'] != '--':
                    day = str(int(str(result_land['land_notice_value_date'])[:7].replace('-',''))-191100).zfill(5)
                    land_notice_value_date = day[:3]+'年'+day[3:]+'月'
                else:
                    land_notice_value_date = ''
                land_notice_value = result_land['land_notice_value'] if result_land['land_notice_value'] else ''
                building_num = result_land['building_num'] if result_land['building_num'] and result_land['building_num'] != -1 else 0
                other_remark = '三七五減租' if result_land['other_remark'] !='' and result_land['other_remark'] != '0' else ''
                other_remark_org = result_land['other_remark']
                create_time = (result_land['create_time'] + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S") if result_land['create_time'] else None
                update_time = (result_land['update_time'] + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S") if result_land['update_time'] else None
                land_notice_price = result_land['land_notice_price']
                land_notice_price_date = result_land['land_notice_price_date']
                size_changed = result_land['size_changed']

                build_list = []
                totol_t = []
                if result_land['locate_bkey'] and not '空白' in result_land['locate_bkey']:
                    totol = result_land['locate_bkey'].split(',')
                    for t_data in totol:
                        try:
                            res = re.search('(?P<bkey1>\d{5}-\d{3})|(?P<bkey2>\d{8})',t_data)
                            if res['bkey1']:
                                totol_t.append(res['bkey1'])
                            elif res['bkey2']:
                                totol_t.append(res['bkey2'][:5]+'-'+res['bkey2'][5:])
                        except:
                            break
                    for build in totol_t:
                        if len(region+build) == 19:
                            build_list.append(region+build)
                build_list_t += build_list
                lkey_data_dict = {'lbkey':lkey,
                                'lno':lno,
                                'city_name':city_name,
                                'area_name':area_name,
                                'region_name':region_name,
                                'plan_name':plan_name,
                                'reg_date':reg_date, 
                                'reg_date_str':reg_date_str, 
                                'reg_reason':reg_reason,
                                'land_purpose':land_purpose,
                                'owners_num':owners_num,
                                'owner_type':owner_type,
                                'land_area':land_area,
                                'urban_type':urban_type,
                                'urban_name':urban_name,
                                'land_zone':land_zone,
                                'land_level':land_level,
                                'land_notice_value_date':land_notice_value_date,
                                'land_notice_value':land_notice_value,
                                'land_notice_price':land_notice_price, 
                                'land_notice_price_date':land_notice_price_date, 
                                'size_changed':size_changed, 
                                'build_num':building_num,
                                'build_finish_day':None,
                                'build_finish_time':None,
                                'build_type':None,
                                'other_remark':other_remark,
                                'other_remark_org':other_remark_org,
                                'create_time':create_time,
                                'update_time':update_time,
                                'is_valid':is_valid,
                                'locate_bkey':build_list,
                                }
                bkey_dict[lkey] = lkey_data_dict

            lkey_data_dict_t = bkey_dict.copy()
            if build_list_t:
                bkeys_sql_str = "'" + "','".join(build_list_t) + "'"
                sql_cmd = "SELECT a.lbkey as 'bkey',ifnull(c.floor_num,a.total_floors) as 'floors', c.built_date_str,\
                            group_concat(CONCAT_ws(',', d.title, d.area) separator ';') as buildingfloor,\
                            if(total_floors>11,'大樓',\
                                if(total_floors<12 AND total_floors>5,'華廈',\
                                    if(total_floors<6 AND total_floors>0,'透天公寓',''))) as 'build_type'\
                            FROM lbor_info.infos_buildingprofilev2 a\
                            left join lbor_info.infos_buildinginfochangev2 b on a.info_id=b.id\
                            left join arsenal.transcript_buildingtranscriptindex ab on a.lbkey=ab.lbkey\
                            left join arsenal.transcript_buildingtranscript bc on bc.id=ab.transcript_id\
                            left join arsenal.transcript_buildingmark c on c.id=bc.mark_id\
                            left join arsenal.transcript_buildingfloor d on a.lbkey=d.lbkey\
                            WHERE a.lbkey in ({}) AND a.is_valid='1' AND c.is_valid='1'\
                            group by a.lbkey ORDER BY a.lbkey ASC;".format(bkeys_sql_str)

                result_builds, header = get_dba(sql_cmd)
                for key in bkey_dict:
                    bkey_data_list = []
                    for result_build in result_builds:
                        bkey = result_build['bkey']
                        if bkey in bkey_dict[key]['locate_bkey']:
                            bkey_data_list.append(result_build)
                    build_age_list = [0]
                    build_type_list = []
                    if bkey_data_list:
                        for result_build in bkey_data_list:
                            level_high = ''
                            level_count = 0
                            floor_list = []
                            if result_build['buildingfloor']:
                                for s,buildingfloor in enumerate(result_build['buildingfloor'].split(';')):
                                    if not '地下' in buildingfloor:
                                        level_high += ',' + buildingfloor.split(',')[0]

                            pattrern1 = '[零一二三四五六七八九十百]{3,}|[零一二三四五六七八九十百]{2,}|[零一二三四五六七八九十百]'
                            time2 = re.findall(pattrern1,level_high)
                            for data in time2:
                                t = cn2an.cn2an(data, "smart")
                                floor_list.append(t)
                            level_count = len(floor_list)
                            if result_build['build_type'] == '透天公寓' and result_build['floors'] == level_count:
                                build_type = '透天'
                            elif result_build['build_type'] == '透天公寓':
                                build_type = '公寓'
                            else:
                                build_type = result_build['build_type']
                            if build_type:
                                build_type_list.append(build_type)
                            if result_build['built_date_str'] and not '空白' in result_build['built_date_str']:
                                try:
                                    year = int(today[:3]) - int(result_build['built_date_str'].split('年')[0])
                                    month = int(today[3:]) - int(result_build['built_date_str'].split('年')[1].split('月')[0])
                                    if year == int(today[:3]) and month == int(today[3:]):
                                        build_age_list = [0]
                                        break
                                except:
                                    build_age_list.append(0)
                                    continue
                                if month < 0:
                                    year -= 1
                                    month += 12
                                year += round(month/12,1)
                                build_age_list.append(year)
                            else:
                                build_age_list.append(0)
                        if build_type_list:
                            build_type = stats.mode(build_type_list)[0][0]
                        else:
                            build_type = ''
                        build_age = self.get_most(build_age_list)
                        if build_age <= 0:
                            build_complete_date = None
                        elif len(result_builds) != 1:
                            year_t = int(today[:3])-int((str(build_age).zfill(5))[:-2])
                            month_t = int(today[3:])-round(int(str(build_age)[-1:])*1.2)
                            if month_t == 0:
                                build_complete_date = str(year_t)
                            elif month_t < 0:
                                year_t -= 1
                                month_t += 12
                                build_complete_date = str(year_t)+'-'+str(month_t).zfill(2)
                            else:
                                build_complete_date = str(year_t)+'-'+str(month_t).zfill(2)
                        else:
                            build_complete_date = str(int(result_build['built_date_str'].split('年')[0]))+'-'+result_build['built_date_str'].split('年')[1].split('月')[0]
                        if build_complete_date == '0' or build_complete_date == '0-00':
                            build_complete_date = None
                        try:
                            build_finish_time = datetime.strptime(str(int(result_build['built_date_str'].split('年')[0])+1911)+"-"+result_build['built_date_str'].split('年')[1].split('月')[0], "%Y-%m")
                            build_finish_time = build_finish_time.strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            build_finish_time = time.strftime('%Y-%m-%d', time.strptime('1970-01-01', '%Y-%m-%d'))
                            if build_complete_date:
                                build_finish_time = None

                        lkey_data_dict_t[key]['build_finish_day'] = build_complete_date
                        lkey_data_dict_t[key]['build_finish_time'] = build_finish_time
                        lkey_data_dict_t[key]['build_type'] = build_type
            for k, lkey_data_dict in lkey_data_dict_t.items():
                rows.append(lkey_data_dict)

            result = {'status': 'OK', 'msg': 'data sent', 'datas': rows}
            end_t = time.perf_counter()
            logger.info('成功傳送地號標示部資料,花費時間：{}'.format(str(end_t - start_t)))
        except Exception as error:
            print(error, 'exception in line', sys.exc_info()[2].tb_lineno)
            print(key)
            logger.info('出錯的建號:{},錯誤的訊息:{}'.format(key, str(error)))
            result = {'status': 'NG', 'msg': 'database access error', 'error': str(error)}
        return result

    def build_mark(self, bkey_list):
        start_t = time.perf_counter()
        result = {'status': 'NG', 'msg': ''}
        rows = []
        bkeys_sql_str = "'" + "','".join(bkey_list) + "'"
        try:
            sql_cmd = """CREATE TEMPORARY TABLE if not exists land_data.ttbl_1 select lbkey, group_concat(CONCAT_ws(',',title, area) separator ';') as buildingfloor
                    from arsenal.transcript_buildingfloor WHERE lbkey in ({}) group by lbkey;""".format(bkeys_sql_str)
            result, header = get_dba(sql_cmd, datarows=False, close=False)
            sql_cmd = """CREATE TEMPORARY TABLE if not exists land_data.ttbl_2 select lbkey, group_concat(CONCAT_ws(',',title, area) separator ';') as buildingattach
                    from arsenal.transcript_buildingattach WHERE lbkey in ({}) group by lbkey;""".format(bkeys_sql_str)
            result, header = get_dba(sql_cmd, datarows=False, close=False)
            sql_cmd = """CREATE TEMPORARY TABLE if not exists land_data.ttbl_3 select lbkey, group_concat(CONCAT_ws(',',right_denominator, right_numerator,
                    total_area, other_remark) separator '；') as commonpart from arsenal.transcript_commonpart WHERE lbkey in ({}) group by lbkey;""".format(bkeys_sql_str)
            result, header = get_dba(sql_cmd, datarows=False, close=False)

            sql_cmd = """SELECT a.lbkey as 'bkey', g.city_name, h.area_name, j.region_name, COMMUNITY_NAME as community_name, ifnull(c.door_number,a.door_number) as door,
                    ifnull(b.owners_num,0) as 'owners_num', ifnull(c.total_area,a.main_area) as main_size, locate_lkey, k.buildingfloor, m.buildingattach, n.commonpart,
                    ifnull(c.floor_num,a.total_floors) as total_level, c.built_date_str as finish_day, c.other_remark, ifnull(c.main_purpose,a.purpose) as main_purpose,
                    ifnull(c.material,a.material) as main_material, i.longitude, i.latitude, a.create_time, a.last_update_time as update_time, c.main_building, a.is_valid,
                    if(owners_num>0 AND owners_goverment_num>0 AND owners_goverment_num=owners_num,'公法人',\
                        if(owners_num>0 AND owners_goverment_num>0 AND owners_goverment_num!=owners_num AND owners_unknown_num=0,'部分公有',\
                            if(owners_num>0 AND owners_goverment_num=0 AND owners_private_num=owners_num,'自然人',\
                                if(owners_num>0 AND owners_goverment_num=0 AND owners_private_num=0 AND owners_unknown_num=0,'私法人',\
                                    if(owners_num>0 AND owners_goverment_num=0 AND owners_private_num!=owners_num AND owners_unknown_num=0,'非公有',\
                                        if(owners_num>0 AND owners_unknown_num!=0,'權屬樣態未知','')))))) as 'owner_type',\
                    if(total_floors>11,'大樓',\
                        if(total_floors<12 AND total_floors>5,'華廈',\
                            if(total_floors<6 AND total_floors>0,'透天公寓',''))) as 'build_type'\
                    FROM lbor_info.infos_buildingprofilev2 a
                    left join lbor_info.infos_buildinginfochangev2 b on a.info_id=b.id
                    left join arsenal.transcript_buildingtranscriptindex ab on a.lbkey=ab.lbkey
                    left join arsenal.transcript_buildingtranscript bc on bc.id=ab.transcript_id
                    left join arsenal.transcript_buildingmark c on c.id=bc.mark_id
                    left join land_data.ttbl_1 k on a.lbkey=k.lbkey
                    left join land_data.ttbl_2 m on a.lbkey=m.lbkey
                    left join land_data.ttbl_3 n on a.lbkey=n.lbkey
                    left join lvr_land.bkey_join_community d on a.lbkey=d.BKEY
                    left join lvr_land.community_info e on d.COMMUNITY_ID=e.id
                    left join build_data.build_coordinate i on a.lbkey=i.bkey
                    left join bigdata.city g on substr(a.lbkey,1,1)=g.city_id
                    left join bigdata.area h on substr(a.lbkey,1,4)=h.area_id
                    left join bigdata.region j on substr(a.lbkey,1,9)=j.region_id
                    WHERE a.lbkey in ({}) ORDER BY a.lbkey ASC;""".format(bkeys_sql_str)
            result_builds, header = get_dba(sql_cmd, close=False)
            for result_build in result_builds:
                # 建號資料
                bkey = result_build['bkey']
                region = bkey[:10]
                city_name = result_build['city_name']
                area_name = result_build['area_name']
                door = result_build['door']
                build_size = float(result_build['main_size']) if result_build['main_size'] else 0
                data_complete = True
                attach_size = 0
                public_size = 0
                parking_size = 0
                parking_no = 0
                level = ''
                level_low = ''
                level_high = ''
                floor_list = []
                floor_t = []
                if result_build['buildingattach']:
                    for attach in result_build['buildingattach'].split(';'):
                        try:
                            attach_size += float(attach.split(',')[1])
                        except:
                            data_complete = False
                if result_build['commonpart']:
                    for commonpart in result_build['commonpart'].split('；'):
                        try:
                            public_size += float(commonpart.split(',')[1]) / float(commonpart.split(',')[0]) * float(commonpart.split(',')[2])
                        except:
                            if commonpart.split(',')[0] == '0' and commonpart.split(',')[1] == '0':
                                pass
                            else:
                                data_complete = False
                        try:
                            parks = json.loads('{' + commonpart.split(',{')[1])['資料']
                            for park in parks:
                                try:
                                    if str(park).find('停車場') != -1 or str(park).find('停車位') != -1:
                                        mol = int(park['#text'].split('分之')[1].split(']')[0])
                                        den = int(park['#text'].split('分之')[0].split('權利範圍:')[1])
                                        parking_no += 1
                                        parking_size += float(commonpart.split(',')[2]) * mol / den
                                except:
                                    pass
                        except:
                            pass
                build_size += attach_size + public_size
                build_size = round(build_size, 2)
                attach_size = round(attach_size, 2)
                public_size = round(public_size, 2)
                parking_size = round(parking_size, 2)
                if result_build['buildingfloor']:
                    for s,buildingfloor in enumerate(result_build['buildingfloor'].split(';')):
                        try:
                            err = buildingfloor.split(',')[1]
                            if '地下' in buildingfloor:
                                level_low += ',' + buildingfloor.split(',')[0]
                            else:
                                level_high += ',' + buildingfloor.split(',')[0]
                            if s == 0:
                                level = buildingfloor.split(',')[0]
                            else:
                                level += ',' + buildingfloor.split(',')[0]
                        except:
                            data_complete = False
                else:
                    data_complete = False
                pattrern1 = '[零一二三四五六七八九十百]{4,}|[零一二三四五六七八九十百]{3,}|[零一二三四五六七八九十百]{2,}|[零一二三四五六七八九十百]'
                time1 = re.findall(pattrern1,level_low)
                for data in time1:
                    t = cn2an.cn2an(data, "smart")
                    floor_list.append(0 - t)
                time2 = re.findall(pattrern1,level_high)
                for data in time2:
                    t = cn2an.cn2an(data, "smart")
                    floor_list.append(t)
                    floor_t.append(t)
                floor_list = sorted(floor_list)
                level_count = len(floor_t)

                use_license_no = ''
                try:
                    use_license_nos = json.loads(result_build['other_remark'])['資料'] if result_build['other_remark'] else None
                except:
                    use_license_nos = ''
                try:
                    for s, use_li in enumerate(use_license_nos):
                        if s == 0:
                            use_license_no = use_li.split('使用執照字號：')[1]
                        else:
                            use_license_no += ';' + use_li.split('使用執照字號：')[1]
                except:
                    pass
                door_re = None
                door_part = None
                road_name = None
                road_name_re = None
                if door:
                    door_t = ''
                    ans = ''
                    action = False
                    if '[' in door:
                        if ']' in door:
                            pattrern = '(\[[A-Z]_\d{2}_\d{2}\]|\[[A-Z]_\d{2}_\d{3}\]|\[[A-Z]_\d{3}_\d{2}\]|\[[A-Z]_\d{3}_\d{3}\])'
                            time3 = re.findall(pattrern, door)
                            for num in time3:
                                df = pd.read_csv('fake_data/common_xchars.csv')
                                door_l = num.split('[')[1].split(']')[0]
                                door_t = (door_l.split('_')[0] + '_' + (hex(int(door_l.split('_')[1])))[2:] + (hex(int(door_l.split('_')[2])))[2:]).upper()
                                try:
                                    select = df[df['city_id_code'] == door_t]
                                    ans = df.loc[select.index[0]]['xchar']
                                except:
                                    action = True
                                    ans = self.get_char(door_t[0], door_t[2:])
                                door = door.replace('[' + door_l + ']', ans)
                        else:
                            door = door.replace('[', '')
                    if '<@>' in door:
                        df = pd.read_csv('fake_data/common_xchars.csv')
                        if '_' in door:
                            door_l = door.split('<@>')[1].split('_')[1]
                            door_t = door.split('<@>')[1]
                        else:
                            door_l = door.split('<@>')[1]
                            door_t = bkey[0] + '_' + door_l
                        try:
                            select = df[df['city_id_code'] == door_t]
                            ans = df.loc[select.index[0]]['xchar']
                            if '_' in door:
                                door = door.replace('<@>' + door_t + '<@>', ans)
                            else:
                                door = door.replace('<@>' + door_l + '<@>', ans)
                        except:
                            action = True
                            ans = self.get_char(bkey[0], door_l)
                        door = door.replace('<@>' + door_l + '<@>', ans)
                    if door_t and ans and action:
                        toAdd = [door_t, ans]
                        if '<@>' in door and '_' in door:
                            door = door.replace('<@>' + door_t + '<@>', ans)
                        elif '<@>' in door:
                            door = door.replace('<@>' + door_l + '<@>', ans)
                        elif '[' in door and ']' in door:
                            door = door.replace('[' + door_l + ']', ans)
                        with open('fake_data/common_xchars.csv', 'r') as infile:
                            reader = list(csv.reader(infile))
                            reader.insert(1, toAdd)
                        with open('fake_data/common_xchars.csv', 'w') as outfile:
                            writer = csv.writer(outfile)
                            for line in reader:
                                writer.writerow(line)
                    try:
                        door_re = door.replace('舘', '館').replace('?s', '館').replace('?J', '槺').replace('?p', '廍').replace('瓦?u', '瓦磘')\
                                .replace('五?}', '五峯').replace('德?}', '德峯').replace('?D', '館').replace('?L', '磘').replace('有??', '有恒')\
                                .replace('愛??', '愛恒')
                    except:
                        door_re = None
                    try:
                        c_t1 = re.findall('[a-z]', door_re)
                        c_t2 = re.findall('[A-Z]', door_re)
                        if door == '(空白)' or door == '（空白）' or door == '*' or door == '（目前無門牌）' or '?' in door_re or c_t1 or c_t2 or '未編' in door_re\
                        or '登記' in door_re:
                            road_name = None
                            door_re = door
                        elif len(door) > 500:
                            door = ''
                            door_re = ''
                            road_name = None
                        elif '公共' in door or '共同' in door or '共有' in door or '公有' in door or '共用' in door or '地下' in door or '公設' in door:
                            road_name = None
                        elif '．' in door or '、' in door or '﹐' in door or '，' in door or '.' in door or '～' in door:
                            door_res = door_re.split('．')[0].split('、')[0].split('﹐')[0].split('，')[0].split('.')[0].split('～')[0]
                            if door_res[0] == '巷':
                                if '巷' in door_res[1:]:
                                    road_name = '巷'+door_res.split('巷')[1]+'巷'
                                elif '段' in door_res:
                                    road_name = door_res.split('段')[0]+'段'
                                elif '路' in door_res:
                                    road_name = door_res.split('路')[0]+'路'
                                elif '街' in door_res:
                                    road_name = door_res.split('街')[0]+'街'
                                else:
                                    road_t = ''
                                    for door_str in door_res:
                                        try:
                                            error_road = int(door_str)
                                            break
                                        except:
                                            road_t += door_str
                                    road_name = road_t
                            elif '巷' in door_res:
                                road_name = door_res.split('巷')[0]+'巷'
                            elif '段' in door_res:
                                road_name = door_res.split('段')[0]+'段'
                            elif '路' in door_res:
                                if '路' in door_res[1:] and door_res[0] == '路':
                                    road_name = '路'+door_res.split('路')[1]+'路'
                                elif '街' in door_res:
                                    road_name = door_res.split('街')[0]+'街'
                                elif not '路' in door_res[1:]:
                                    road_t = ''
                                    for door_str in door_res:
                                        try:
                                            error_road = int(door_str)
                                            break
                                        except:
                                            road_t += door_str
                                    road_name = road_t
                                else:
                                    road_name = door_res.split('路')[0]+'路'
                                road_name = door_res.split('路')[0]+'路'
                            elif '街' in door_res and door_res[0] != '街':
                                road_name = door_res.split('街')[0]+'街'
                            else:
                                road_t = ''
                                for door_str in door_res:
                                    try:
                                        error_road = int(door_str)
                                        break
                                    except:
                                        road_t += door_str
                                road_name = road_t
                        elif not ('．' in door or '、' in door or '﹐' in door or '，' in door or '.' in door or '～' in door):
                            if door_re[0] == '巷':
                                if '巷' in door_re[1:]:
                                    road_name = '巷'+door_re.split('巷')[1]+'巷'
                                elif '段' in door_re:
                                    road_name = door_re.split('段')[0]+'段'
                                elif '路' in door_re:
                                    road_name = door_re.split('路')[0]+'路'
                                elif '街' in door_re:
                                    road_name = door_re.split('街')[0]+'街'
                                else:
                                    road_t = ''
                                    for door_str in door_re:
                                        try:
                                            error_road = int(door_str)
                                            break
                                        except:
                                            road_t += door_str
                                    road_name = road_t
                            elif '巷' in door_re:
                                road_name = door_re.split('巷')[0]+'巷'
                            elif '段' in door_re:
                                road_name = door_re.split('段')[0]+'段'
                            elif '路' in door_re:
                                if '路' in door_re[1:] and door_re[0] == '路':
                                    road_name = '路'+door_re.split('路')[1]+'路'
                                elif '街' in door_re:
                                    road_name = door_re.split('街')[0]+'街'
                                elif not '路' in door_re[1:]:
                                    road_t = ''
                                    for door_str in door_re:
                                        try:
                                            error_road = int(door_str)
                                            break
                                        except:
                                            road_t += door_str
                                    road_name = road_t
                                else:
                                    road_name = door_re.split('路')[0]+'路'
                            elif '街' in door_re and door_re[0] != '街':
                                road_name = door_re.split('街')[0]+'街'
                            else:
                                road_t = ''
                                for door_str in door_re:
                                    try:
                                        error_road = int(door_str)
                                        break
                                    except:
                                        road_t += door_str
                                road_name = road_t
                        else:
                            road_name = None
                    except:
                        road_name = None
                    try:
                        if door == '(空白)':
                            door_part = None
                        elif len(door) > 500:
                            door_part = None
                        elif '公共' in door or '共同' in door or '共有' in door or '公有' in door or '共用' in door or '地下' in door or '公設' in door:
                            door_part = None
                        elif '號' in door:
                            door_part = door.split('號')[0]+'號'
                            if '．' in door or '、' in door or '﹐' in door or '，' in door or '.' in door or '～' in door:
                                pass
                            elif '－' in door_part and '巷' in door_part:
                                door_part = door_part.split('巷')[0]+'巷'+(door_part.split('巷')[1]).split('－')[0]+'號'
                            elif '－' in door_part:
                                door_part = door_part.split('－')[0]+'號'
                            elif '之' in door_part:
                                door_part = door_part.split('之')[0]+'號'
                        else:
                            road_t = ''
                            for door_str in door:
                                try:
                                    error_road = int(door_str)
                                    break
                                except:
                                    road_t += door_str
                            door_part = road_t
                    except:
                        door_part = None
                    try:
                        if len(road_name) > 100:
                            road_name = None
                    except:
                        pass
                    if road_name:
                        try:
                            road_name_re = road_name
                            pattrern1 = '[零一二三四五六七八九十百]{4,}|[零一二三四五六七八九十百]{3,}|[零一二三四五六七八九十百]{2,}|[零一二三四五六七八九十百]'
                            time1 = sorted((re.findall(pattrern1,road_name)), key = lambda i:len(i), reverse=True)
                            for data in time1:
                                t = str(cn2an.cn2an(data, "smart"))
                                road_name_re = road_name_re.replace(data, t)
                        except Exception as e:
                            road_name_re = None
                            logger.info('無法正規化的門牌:{},錯誤訊息:{}'.format(road_name, str(e)))
                    if road_name_re:
                        road_name_re = self.strQ2B(road_name_re)
                
                build_share = True if result_build['main_building'] else False
                if result_build['build_type'] == '透天公寓' and result_build['total_level'] == level_count:
                    build_type = '透天'
                elif result_build['build_type'] == '透天公寓':
                    build_type = '公寓'
                else:
                    build_type = result_build['build_type']
                data = result_build['main_purpose']
                if '國民住宅' in str(data):
                    main_purpose = '國民住宅'
                elif '住商用' in str(data) or (('住宅' in str(data) or '住家' in str(data)) and ('商業' in str(data) or '店舖'  in str(data) or '商場' in str(data) or '餐飲' in str(data) \
                    or '零售' in str(data) or '飲食' in str(data) or '事務所' in str(data) or '金融' in str(data) or '辦公' in str(data) \
                    or '旅館' in str(data) or '店鋪' in str(data))):
                    main_purpose = '住商用'
                elif '住工用' in str(data) or (('住宅' in str(data) or '住家' in str(data)) and ('廠' in str(data) or '加工' in str(data) or '機房' in str(data) or '石油' in str(data))):
                    main_purpose = '住工用'
                elif ('廠' in str(data) or '加工' in str(data) or '機房' in str(data) or '石油' in str(data)) and ('商業' in str(data) \
                    or '店舖'  in str(data) or '商場' in str(data) or '餐飲' in str(data) or '零售' in str(data) or '飲食' in str(data) or \
                    '事務所' in str(data) or '金融' in str(data) or '辦公' in str(data) or '旅館' in str(data) or '店鋪' in str(data)):
                    main_purpose = '工商用'
                elif '住宅' in str(data) or '住家' in str(data):
                    main_purpose = '住家用'
                elif '商業' in str(data) or '店舖'  in str(data) or '商場' in str(data) or '餐飲' in str(data) or '零售' in str(data) \
                    or '飲食' in str(data) or '事務所' in str(data) or '金融' in str(data) or '辦公' in str(data) or '旅館' in str(data) or '店鋪' in str(data):
                    main_purpose = '商業用'
                elif '廠' in str(data) or '加工' in str(data) or '機房' in str(data) or '石油' in str(data):
                    main_purpose = '工業用'
                elif '市場' in str(data) or '攤位' in str(data) or '攤販' in str(data):
                    main_purpose = '市場攤位'
                elif '舍' in str(data):
                    main_purpose = '農舍'
                elif '畜牧' in str(data) or '農業' in str(data) or '溫室' in str(data):
                    main_purpose = '農業用'
                elif '停車' in str(data):
                    main_purpose = '停車空間'
                elif str(data) and str(data) != '(空白)':
                    main_purpose = '其他'
                else:
                    main_purpose = result_build['main_purpose']
                if build_share:
                    door_re = None
                    door_part = None
                    road_name = None
                    road_name_re = None
                    main_purpose = '共有(公設)建物'

                land_list = []
                totol_t = []
                if result_build['locate_lkey'] and not '空白' in result_build['locate_lkey']:
                    totol = result_build['locate_lkey'].split(',')
                    for t_data in totol:
                        try:
                            res = re.search('(?P<lkey1>\d{4}-\d{4})|(?P<lkey2>\d{8})',t_data)
                            if res['lkey1']:
                                totol_t.append(res['lkey1'])
                            elif res['lkey2']:
                                totol_t.append(res['lkey2'][:4]+'-'+res['lkey2'][4:])
                        except:
                            break
                    for land in totol_t:
                        if len(region+land) == 19:
                            land_list.append(region+land)
                try:
                    finish_time = datetime.strptime(str(int(result_build['finish_day'].split('年')[0])+1911)+"-"+result_build['finish_day']\
                        .split('年')[1].split('月')[0]+"-"+result_build['finish_day'].split('月')[1].split('日')[0], "%Y-%m-%d")
                    finish_time = finish_time.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    finish_time = time.strftime('%Y-%m-%d', time.strptime('1970-01-01', '%Y-%m-%d'))

                bkey_dict = {'lbkey': bkey,
                            'city_name':city_name,
                            'area_name':area_name,
                            'region_name':result_build['region_name'],
                            'community_name':result_build['community_name'],
                            'road_name':road_name,
                            'road_name_re':road_name_re,
                            'door':door,
                            'door_re':door_re,
                            'door_part':door_part,
                            'owners_num':result_build['owners_num'],
                            'owner_type':result_build['owner_type'],
                            'build_size':build_size,
                            'main_size':result_build['main_size'],
                            'attach_size':attach_size,
                            'public_size':public_size,
                            'parking_size':parking_size,
                            'parking_no':parking_no,
                            'finish_day':result_build['finish_day'],
                            'finish_time':finish_time,
                            'level':level,
                            'floor_first':floor_list[0] if floor_list else 0,
                            'floor_last':floor_list[-1] if floor_list else 0,
                            'total_level':result_build['total_level'],
                            'use_license_no':use_license_no,
                            'main_purpose':main_purpose,
                            'main_material':result_build['main_material'],
                            'car_type':None,
                            'build_type':build_type,
                            'other_remark':None,
                            'longitude':result_build['longitude'],
                            'latitude':result_build['latitude'],
                            'create_time':result_build['create_time'].strftime("%Y-%m-%d %H:%M:%S") if result_build['create_time'] else None,
                            'update_time':result_build['update_time'].strftime("%Y-%m-%d %H:%M:%S") if result_build['update_time'] else None,
                            'build_share':build_share,
                            'is_valid':result_build['is_valid'],
                            'data_complete':data_complete,
                            'locate_lkey':land_list,
                            }
                rows.append(bkey_dict)

            result = {'status': 'OK', 'msg': 'data sent', 'datas': rows}
            end_t = time.perf_counter()
            logger.info('成功傳送建號標示部資料,花費時間：{}'.format(str(end_t - start_t)))
        except Exception as error:
            print(bkey)
            print(error, 'exception in line', sys.exc_info()[2].tb_lineno)
            logger.info('出錯的建號:{},錯誤的訊息:{}'.format(bkey, str(error)))
            result = {'status': 'NG', 'msg': 'database access error', 'error': str(error)}
        return result

    def main_job(self, lbkey_list, lbtype):
        result = {'status': 'NG', 'msg': ''}
        if lbtype == 'L':
            result = self.land_mark(lkey_list=lbkey_list)
        elif lbtype == 'B':
            result = self.build_mark(bkey_list=lbkey_list)
        else:
            result['msg'] = '地建號型態錯誤'
            return result
        return result

def change_last_regno_time(discard_log, query_time, or_log, or_qs):
    '''
    廢棄最後一筆完成的資料
    變更登序新增與移除時間
    '''
    dels = []
    modifys = []

    for or_obj in or_qs:
        if (discard_log.query_time == or_obj.add_time) or (or_log == None):
            # 解析新增時間為要廢棄的時間 直接刪除
            dels.append(or_obj.id)
        elif discard_log.query_time == or_obj.remove_time:
            # 解析移除時間為最後一筆 移除移除時間 改變狀態
            or_obj.remove_time = None
            or_obj.query_time = query_time
            or_obj.is_valid_type = IsvalidTypeEnum.VALID

            if name := or_log.get(or_obj.regno):
                or_obj.name = name
            modifys.append(or_obj)
    return dels, modifys

def change_regno_time(discard_log, query_time, or_log, or_qs):
    '''
    輸入lbkey > 廢棄選擇的 > 
        解析新增時間為選擇 移除時間為選擇的下一筆 刪除
        解析移除時間為選擇 移除移除時間 改變狀態
    '''
    dels = []
    modifys = []

    for or_obj in or_qs:
        if (discard_log.query_time == or_obj.add_time) and (query_time == or_obj.remove_time or discard_log.query_time == or_obj.remove_time):
            dels.append(or_obj.id)
        elif discard_log.query_time == or_obj.remove_time:
            or_obj.remove_time = None
            or_obj.is_valid_type = IsvalidTypeEnum.VALID
            modifys.append(or_obj)
    return dels, modifys

def query_debugger(func):
    @functools.wraps(func)
    def inner_func(*args, **kwargs):
        reset_queries()
        start_queries = len(connection.queries)
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        end_queries = len(connection.queries)
        print(f"Function : {func.__name__}")
        print(f"Number of Queries : {end_queries - start_queries}")
        print(f"Finished in : {(end - start):.2f}s")
        return result
    return inner_func

def replace_simple(input_str):
    result = None
    if isinstance(input_str, str) == True:
        if input_str.find("'") != -1:
            result = input_str.replace("'", "\"")
            try:
                result = json.loads(result)
            except:
                result = input_str
    # 其他型態處理方式
    elif isinstance(input_str, list) == True:
        result = input_str
    elif isinstance(input_str, dict) == True:
        result = input_str
    return result

class CustomJSONField(models.JSONField):
    ''' json 的 Field'''
    def get_prep_value(self, value):
        if value is None:
            return value
        return json.dumps(value, ensure_ascii=False)

class CombinTranscript(object):

    def regno_process(self, regno):
        regno_list = []
        if isinstance(regno, str):
            if regno != '':
                regno = regno.replace(' ', '').replace('　', '')
                regno_list = regno.split(',')
        return regno_list

    def combin_process(self, tp_json, org_o_list, org_r_list):
        f_result = {}
        f_owner_data = []
        f_right_data = []
        if tp_json:
            owner_all_regno, right_all_regno = [], []
            owner_all_regno.extend(org_o_list)
            right_all_regno.extend(org_r_list)            
            tree = objectpath.Tree(tp_json)

            exstr_M = '$.mark'
            mark = tree.execute(exstr_M)
            if mark:
                f_result['mark'] = mark
            
            exstr_o_list = '$.owners_list'
            owners_list = tree.execute(exstr_o_list)
            if owners_list:
                f_result['owners_list'] = owners_list

            exstr_r_list = '$.rights_list'
            rights_list = tree.execute(exstr_r_list)
            if rights_list:
                f_result['rights_list'] = rights_list

            # 所 -> 他
            if org_o_list:
                for owner in org_o_list:
                    exstr_R = f'$.owners[@.regno is "{owner}"].related_creditor_regno'
                    result = tree.execute(exstr_R)
                    for p in result:
                        if isinstance(p, list):
                            right_all_regno.extend(p)
            # 他 -> 所 -> 他
            if org_r_list:
                for right in org_r_list:
                    exstr_O = f'$.rights[@.regno is "{right}"].related_owner_regno'
                    result = tree.execute(exstr_O)
                    for k in result:
                        if isinstance(k, list):
                            owner_all_regno.extend(k)
                            for j in k:
                                exstr_R2 = f'$.owners[@.regno is "{j}"].related_creditor_regno'
                                resultR2 = tree.execute(exstr_R2)
                                for y in resultR2:
                                    if isinstance(y, list):
                                        right_all_regno.extend(y)
            owner_reg_set = sorted(list(set(owner_all_regno)))
            right_reg_set = sorted(list(set(right_all_regno)))

            for o in owner_reg_set:
                ex_O = f'$.owners[@.regno is "{o}"]'
                result_o = tree.execute(ex_O)  
                sp_owner = [x for x in result_o if result_o]
                f_owner_data.extend(sp_owner)

            for r in right_reg_set:
                ex_R = f'$.rights[@.regno is "{r}"]'
                result_r = tree.execute(ex_R)                
                sp_right = [x for x in result_r if result_r]
                f_right_data.extend(sp_right)

            f_result['owners'] = f_owner_data
            f_result['rights'] = f_right_data
        return f_result

    def do_part(self, lbtype, serializer_set=None, mark=None, owner=None, right=None, tp_log=None, vpdata=None):
        result = {'mark': {}, 'owners': [], 'rights': [], 'owners_list': [], 'rights_list': []}
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
            elif lbtype == 'L':
                mark_vp = mark_obj.marknotice_set.all()
                vp_data = serializer_set.MarkVpSerializer(mark_vp, many=True).data
                vp_data_list = [dict(x) for x in vp_data]
                if vp_data_list:
                    result['mark'].update(vp_data_list[0])
        # 組所有權
        if owner:
            owners_data = serializer_set.OwnerSerializer(owner, many=True).data
            owners_part = [dict(x) for x in owners_data]
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

    def get_CAR(self, lbkey, summary_model, summary_obj=None):
        CAR_json = {}
        if not summary_obj:
            if lbkey:
                try:
                    summary_obj = summary_model.Summary.objects.get(lbkey=lbkey)
                except:
                    pass
            else:
                summary_obj = None

        if summary_obj:
            city = summary_obj.city_code_table_id.city_name
            area = summary_obj.area_code_table_id.area_name
            region = summary_obj.region_code_table_id.region_name
            CAR_json = {'city_name': city, 'area_name': area, 'region_name': region, 'lbno': f'{summary_obj.main_num}-{summary_obj.sub_num}'}

        return CAR_json
    
    def take_(self, regnos_data):
        regno_dict = {}
        if regnos_data:
            for i in regnos_data:
                regno = i.get('regno')
                name = i.get('name')
                regno_dict[regno] = name
        return regno_dict

    def combit_list_process(self, tp_json):
        owners = self.take_(tp_json.get('owners'))
        rights = self.take_(tp_json.get('rights'))
        tp_json['owners_list'] = owners
        tp_json['rights_list'] = rights
        return tp_json
