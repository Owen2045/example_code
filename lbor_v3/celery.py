# coding:utf-8
import os
from celery import Celery

project_name = os.path.split(os.path.abspath('.'))[-1]
project_settings = '%s.settings' % project_name

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', project_settings)

# 使用redis作為中間人(broker)
# 使用redis作為定時任務存取地方(backend)
# 預設redis為本地127.0.0.1:6379/1(redis)
# ★★★ 此處須注意(若本地沒有redis卻設置redis預設 -> 則會顯示10061連線錯誤)
# app = Celery(project_name, broker='redis://127.0.0.1:6379/15')
app = Celery(project_name)
# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))
