from lbor_v3.celery import app
from celery.schedules import crontab

from django.core.management import call_command
from common.management.commands import update_from_104, parser_lbor, update_from_104_tp, parser_tp

@app.task
def update_from_104_celery(lb):
    call_command(update_from_104.Command(), lb=lb)

@app.task
def parser_lbor_celery():
    call_command(parser_lbor.Command())

@app.task
def update_from_104_tp_celery(lb):
    call_command(update_from_104_tp.Command(), lb=lb)

@app.task
def parser_tp_celery(t):
    call_command(parser_tp.Command(), lbtype=t)



app.conf.beat_schedule['l_update_from_104_celery'] = {
        'task': 'common.tasks.update_from_104_celery',
        'schedule': crontab(minute='15,45'),
        'kwargs': {'lb': 'l'},
        'description': '土地 取104資料庫 lbor log 15分 45分',
        'enabled': False
    }
app.conf.beat_schedule['b_update_from_104_celery'] = {
        'task': 'common.tasks.update_from_104_celery',
        'schedule': crontab(minute='15,45'),
        'kwargs': {'lb': 'b'},
        'description': '建物 取104資料庫 lbor log 15分 45分',
        'enabled': False
    }

app.conf.beat_schedule['parser_lbor_celery'] = {
        'task': 'common.tasks.parser_lbor_celery',
        'schedule': crontab(minute='20,50'),
        'kwargs': {},
        'description': '解析log資料 20分 50分',
        'enabled': False
    }
# 抓tplog
app.conf.beat_schedule['L_update_from_104_tp_celery'] = {
        'task': 'common.tasks.update_from_104_tp_celery',
        'schedule': crontab(minute='0,30'),
        'kwargs': {'lb': 'L'},
        'description': '取土地 104 log資料 00分 30分',
        'enabled': False
    }

app.conf.beat_schedule['B_update_from_104_tp_celery'] = {
        'task': 'common.tasks.update_from_104_tp_celery',
        'schedule': crontab(minute='0,30'),
        'kwargs': {'lb': 'B'},
        'description': '取建物 104 log資料 00分 30分',
        'enabled': False
    }
# 解析謄本log
app.conf.beat_schedule['L_parser_tp_celery'] = {
        'task': 'common.tasks.parser_tp_celery',
        'schedule': crontab(minute='10,40'),
        'kwargs': {'t': 'L'},
        'description': '解析 tp log  10分 40分',
        'enabled': False
    }

app.conf.beat_schedule['B_parser_tp_celery'] = {
        'task': 'common.tasks.parser_tp_celery',
        'schedule': crontab(minute='10,40'),
        'kwargs': {'t': 'B'},
        'description': '解析 tp log 10分 40分',
        'enabled': False
    }

# schedule 範例:
# crontab() 每分鐘執行1次
# crontab(minute=0, hour=0) 每天凌晨執行1次
# crontab(minute=0, hour='*/3') 每3個小時執行1次
# crontab(minute='*/15') 每15分鐘執行1次
# crontab(minute='15,45') 每小時15分45分各執行1次
# crontab(minute='*/10', hour='3,17,22', day_of_week='thu,fri') 每10分鐘執行1次 但僅在周四或週五的凌晨 3-4 點、下午 5-6 點和晚上 10-11 點之間執行。