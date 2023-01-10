from os import system
from django.core.management.base import BaseCommand
from common.models import SystemConfig
from common.util import SYSTEM_ENVIRONMENT, get_dba, batch, time_proV2
from common.models import RegionCodeTable
import pandas as pd
import logging
import building.models
import land.models


logger = logging.getLogger(__name__)



class Command(BaseCommand):
    '''
    舊的謄本log轉入lbor_v3
    (一次性作業)
    指定state=87避免混到
    '''
    def handle(self, *args, **options):
        # building
        sql = f'SELECT * FROM lbor_v3.building_tp_log WHERE lbkey LIKE "O%" and state=87 and query_time < "2014-01-01" '
        res, col = get_dba(sql_cmd=sql, db_name='local')
        print(f'總筆數 {len(res)}')
        for ind, batch_list in enumerate(batch(res, 10000)):
            print(f'batch id: {ind}')
            # if ind <= 1747:
            #     continue
            entry = []
            for i in batch_list:
                del i['id']
                del i['create_time']
                del i['tp_summary_id']
                i['query_time'] = time_proV2(i['query_time'])
                # print(i)
                entry.append(building.models.Tplog(**i))
            # print(entry)
            building.models.Tplog.objects.bulk_create(entry)
        print('全部匯完')