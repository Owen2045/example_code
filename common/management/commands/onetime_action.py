import logging
import os
import time

import pandas as pd
from django.core.management import call_command
from django.core.management.base import BaseCommand
from common.management.commands import parser_tp
import building.models
import land.models
from common.enums import IsvalidTypeEnum, LBEnum, TaskTypeEnum
from common.serializers import create_lbor
from common.util import get_dba

logger = logging.getLogger(__name__)



class Command(BaseCommand):
    """
    重新解析
    一次性動作
    """
    help = '一次性動作'
    def handle(self, *args, **options):
        max_id = building.models.Tplog.objects.filter().last().id
        batch_size = 100
        lbkey_list_id = [x for x in range(1, max_id)]

        bat_lbkey = [lbkey_list_id[x:x+batch_size] for x in range(0, len(lbkey_list_id), batch_size)]
        for batchid, update_id_list in enumerate(bat_lbkey):
            print(f'batch id = {batchid}')
            call_command(parser_tp.Command(), lbtype='B', re_parser=True, id_list=update_id_list)










