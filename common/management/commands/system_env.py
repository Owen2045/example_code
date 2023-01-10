from os import system
from django.core.management.base import BaseCommand
from common.models import SystemConfig
from common.util import SYSTEM_ENVIRONMENT
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# 系統變數最底層設定, 防止刪資料庫或是變動到時, 找不到變數的備案(遷移資料表時需要更新進去)




class Command(BaseCommand):
    '''
    檢查欄位env
    重複: 更新後面參數
    新增: 寫入
    '''


    def handle(self, *args, **options):
        u = 0
        n = 0
        if SYSTEM_ENVIRONMENT:
            for i in SYSTEM_ENVIRONMENT:
                env_ = i.get('env')
                try:
                    qs = SystemConfig.objects.get(env=env_)
                    qs.string = i.get('string')
                    qs.integer = i.get('integer')
                    qs.datetime = i.get('datetime')
                    qs.json = i.get('json')
                    qs.remark = i.get('remark')
                    qs.save()
                    u += 1
                except:
                    SystemConfig.objects.create(**i)
                    n += 1
        logger.info(f'更新: {u} 新增: {n} done!')
        # print(qs)

