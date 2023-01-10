# celery

## celery 寫法

```py
# 進入終端機
# > python manage.py shell

# 測試定期任務
from common.tasks import add
from celery.execute import apply_async
# 三種方式意思一樣
add.apply_async((2, 2))
apply_async(add, (2, 2, ))
add.delay(2, 2)
```

## celery 本地測試須安裝套件

```bash
# Celery 監控程式 (docker 需要更改setting CELERY_BROKER_URL CELERY_RESULT_BACKEND)
安裝花 進入花管理介面
$ pip install flower
$ celery -A lbor_v3 flower --port=5555
http://localhost:5555/

# rebbitMQ 桌面管理器
安裝兔子 進入兔子管理介面
$ sudo rabbitmq-plugins enable rabbitmq_management
http://127.0.0.1:15672/

# 創建一個兔子用戶
$ sudo rabbitmqctl add_user USERNAME PASSWORD
# 使用“管理員”標記用戶以獲得完整的管理 UI 和 HTTP API 訪問權限
$ sudo rabbitmqctl set_user_tags USERNAME administrator
```
## celery 本地測試流程
step1. 開啟 celery 服務並寫入任務
```bash
# 啟動 celery 服務
$ celery -A lbor_v3 worker -l INFO
# 啟動定期任務
# celery -A lbor_v3 beat
# 啟動定期任務 並加入資料庫內
$ celery -A lbor_v3 beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
```
step2. 手動執行指定排程

到admin管理介面，左邊拉到底點Periodic tasks

把要跑的任務打勾，選 Run selected tasks

備註：更新task的時候本地端要先刪掉所有Periodic tasks，再重啟step1
## 參考資料

[signatures](https://docs.celeryq.dev/en/latest/userguide/canvas.html#signatures)
[docker-django-celery](https://github.com/twtrubiks/docker-django-celery-tutorial)

[redis 桌面管理器](https://snapcraft.io/redis-desktop-manager)