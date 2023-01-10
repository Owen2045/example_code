
from django.core.management.base import BaseCommand
from common.models import SystemConfig
from common.util import get_dba, time_proV2
from common.enums import QuerySystemEnum, RuleTypeEnum
from common.serializers import FeedbackLborSerializer

from building.models import Tplog as BT
from land.models import Tplog as LT

import configparser
import pandas as pd
import threading
import queue
import gc
import time
import json
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """
    從104更新資料
    """
    help = '從104更新資料'

    def add_arguments(self, parser):
        parser.add_argument(
                '--lb',
                action='store',
                dest='lb',
                default='L',
                help='''更新土地或建物'''
            )

    def check_id(self):
        max_id_sql = 'SELECT max(id) FROM lbor_v2.tasks_landlog'
        data, index = get_dba(max_id_sql)
        log_last_id = data[0].get('max(id)')
        return log_last_id

    def handle(self, *args, **options):

        config = configparser.ConfigParser()
        config.read('config.ini')
        lbtype_options = options['lb']

        if lbtype_options == 'L':
            # id_min = int(config["104tp"].get('land_tp_progress', 0))
            id_min = get_id(lbtype=lbtype_options, config_info=None)
            lbor_info_db = 'lbor_v2.tasks_landlog'
            input_log_model = LT
            mark_str = '土地標示部'

        elif lbtype_options == 'B':
            # id_min = int(config["104tp"].get('building_tp_progress', 0))
            id_min = get_id(lbtype=lbtype_options, config_info=None)
            lbor_info_db = 'lbor_v2.tasks_buildinglog'
            input_log_model = BT
            mark_str = '建物標示部'
        else:
            logger.error('參數錯誤')
            exit()

        sql_cid = f'SELECT MAX(id) FROM {lbor_info_db};'
        data_cid, index_cid = get_dba(sql_cid)
        max_104_id = data_cid[0]['MAX(id)']
        logger.info(f'104最大id : {max_104_id}')
        if id_min >= max_104_id:
            logger.info(f'已達最新 {lbtype_options}')
            exit()

        limit = 1000
        id_max = id_min + limit
        test_count = 0
        null_count = 0

        while True:
            time.sleep(0.5)

            logger.info(f'進度起點id: {id_min}')
            sql = f"SELECT id, lbkey, query_end, owners, owners_message, creditors, system, creditors_message, extra \
                    FROM {lbor_info_db} WHERE id>{id_min} and id<{id_max} and extra LIKE '%transcript%' \
                    limit {limit}"

            data, index = get_dba(sql)
            df = pd.DataFrame(data)

            if len(df) <= 0:
                null_count += 1
                logger.info(f'query set is null go next batch {limit}')
                if id_min >= max_104_id:
                    id_min = max_104_id
                save_id(lbtype=lbtype_options, id_num=id_min, config_info=None)
                id_min = id_max
                id_max = id_min + limit

                if max_104_id - id_max <= 1000 or null_count >= 30 or id_min >= max_104_id:
                    break
                continue
            null_count = 0
            id_min = df['id'].max()
            id_max = id_min + limit
            logger.info(f'取清單成功 開始處理...')
            df = df.fillna('')
            df = df.rename(columns={'creditors': 'rights', 'query_end': 'query_time', 'creditors_message': 'rights_message'})
            after_8_hours = pd.Timedelta(hours=8)
            df['query_time'] = df['query_time'] + after_8_hours
            df['query_system'] = df['system'].apply(change_query_system)
            df['rules'] = df.apply(check_rules, axis=1)
            df['owners'] = df['owners'].apply(split_OR_list, args=(4,))
            df['rights'] = df['rights'].apply(split_OR_list, args=(7,))
            del df['owners_message'], df['rights_message'], df['id'], df['system']
            datas = df.to_dict(orient='records')
            final_data = []
            for tp in datas:
                try:
                    tp_info = json.loads(tp.get('extra'))
                except:                    
                    continue
                query_time = str_cover_dict(tp_info.get('transcript_info')).get('query_time')
                transcript = str_cover_dict(tp_info.get('transcript_info')).get('元宏電傳')
                pdf_token = str_cover_dict(tp_info.get('transcript_info')).get('pdf_token')
                zip_token = str_cover_dict(tp_info.get('transcript_info')).get('zip_token')

                mark_check = transcript.get(mark_str)

                if not query_time:
                    continue
                if not mark_check:
                    continue
                if type(mark_check) == str:
                    continue
                query_time = time_proV2(query_time, plus_8=False)
                if not query_time:
                    query_time = tp['query_time']
                tp['query_time'] = query_time
                tp['transcript'] = {'transcript_info': transcript, 'pdf_token': pdf_token, 'zip_token': zip_token}
                del tp['extra']
                final_data.append(input_log_model(**tp))
            input_log_model.objects.bulk_create(final_data)
            logger.info(f'次數: {test_count}  寫入成功 筆數: {len(final_data)}')
            save_id(lbtype=lbtype_options, id_num=id_min, config_info=None)
            # test_count += 1
            # exit()


def get_id(lbtype, config_info):
    if lbtype == 'L':
        info_str = 'land'
        lbid = 27000000
    else:
        info_str = 'building'
        lbid = 17000567
    try:
        lbid = SystemConfig.objects.get(env=f'104tp_{lbtype}').integer
    except:
        pass
        # lbid = int(config_info["104tp"].get(f'{info_str}_tp_progress', 0))
    return lbid

def save_id(lbtype, id_num, config_info):
    # config_info.read('config.ini')
    try:
        l_id = SystemConfig.objects.get(env=f'104tp_{lbtype}')
        l_id.integer = id_num
        l_id.save()
    except:
        SystemConfig.objects.create(env=f'104tp_{lbtype}', integer=id_num)

    # if lbtype == 'L':
    #     info_str = 'land'
    # else:
    #     info_str = 'building'
    # config_info["104tp"][f"{info_str}_tp_progress"] = str(id_num)
    # config_info.write(open("config.ini", 'w'))


def get_qs(db, imin, imax, limit):
    result = []
    try_count = 0
    minus = 1000
    while try_count <= 30:
        sql = f"SELECT id, lbkey, query_end, owners, owners_message, creditors, system, creditors_message, extra \
                FROM {db} WHERE id>{imin} and id<{imax} and extra LIKE '%transcript%' \
                limit {limit}"
        if try_count >= 3:
            minus = 500
        elif try_count >= 5:
            minus = 500
        elif try_count >= 10:
            minus = 100
        elif try_count >= 18:
            minus = 50
        elif try_count >= 23:
            minus = 10

        try:
            data, index = get_dba(sql)     
            print(f'查詢成功batch: {minus} 資料長度: {len(data)}')
            result = data
            return result
        except Exception as e:
            print(f'查詢失敗batch: {minus}')
            print(f'wrong massage {e}')            
            try_count = try_count + 1
            limit = limit - minus
        time.sleep(1)

def split_OR_list(data_str, width):
    if data_str == '':
        return {}

    or_dict = {}
    data_str = data_str.replace('-', '')
    data_list = data_str.split(';')
    for data in data_list:
        regno = data.split(' ')
        try:
            or_dict[regno[0].zfill(width)] = regno[1]
        except:
            print(regno)
    return or_dict

def check_rules(data):
    or_complete = ''
    rules = None
    if data['owners_message'] or data['owners']:
        or_complete += 'O'
        rules = RuleTypeEnum.OWNER.value

    if data['rights_message'] or data['rights']:
        or_complete += 'R'
        rules = RuleTypeEnum.RIGHT.value

    if or_complete == "OR":
        rules = RuleTypeEnum.BOTH.value

    elif rules == None:
        rules = RuleTypeEnum.APRT.value

    return rules

def change_query_system(data):
    if data in [1, 2]:
        return QuerySystemEnum.GAIAS_PC.value
    elif data in [3, 4]:
        return QuerySystemEnum.QUANTA_PC.value
    elif data in [11]:
        return QuerySystemEnum.TELEX_PDF.value
    else:
        return QuerySystemEnum.LOR_V2.value

def str_cover_dict(data):
    if isinstance(data, dict):
        return data
    else:
        return {}
