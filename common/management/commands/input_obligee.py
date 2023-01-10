from django.core.management.base import BaseCommand
from common.util import batch, get_dba, time_proV2
from common.models import Obligee


import logging

logger = logging.getLogger(__name__)



class Command(BaseCommand):

    def input_obligee_from104(self):
        sql = 'SELECT name, property_type, is_valid FROM lbor_info.infos_obligee'
        res, col = get_dba(sql)
        for i in batch(res, n=5000):
            kw = []
            for j in i:
                kw.append(Obligee(**j))
            Obligee.objects.bulk_create(kw)


    def handle(self, *args, **options):
        logger.info('檢查 obligee')
        try:
            a = Obligee.objects.get(pk=1)
            logger.info('obligee 已存在資料')
        except:            
            logger.info('開始匯入 obligee')
            self.input_obligee_from104()
            logger.info('obligee 匯入完成')
