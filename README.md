# LBOR V3

## 相關文件

[celery](/docs/celery.md)

[docker](/docs/docker.md)

### commands 指令

[列表](/docs/commands/lbor_commands.md)

[謄本](/docs/commands/tp_commands.md)

[其他](/docs/commands/other_commands.md)

### API 測試文件

[列表](/docs/api_test/lbor_api_test.md)

[謄本](/docs/api_test/task_api_test.md)

## 常用 django 指令

```bash
# 啟動server
python manage.py runserver 8000

# 建立超級使用者
python manage.py createsuperuser

# 建立新的APP
python manage.py startapp ocr

# 資料表更新
python manage.py makemigrations
python manage.py migrate

# 查看遷移狀態
python manage.py showmigrations

# 重置資料庫(危險)
##(注意：使用此程式碼後，所有現有的超級使用者也將被刪除。)
##(只有表內資料清空)
python manage.py flush
```

## 上code流程

```bash
docker exec -ti lbor_django /bin/bash
git pull
python manage.py makemigrations user common land building extra_building extra_land # 有改到 資料庫欄位再做 (須手動)
python manage.py migrate # 有改到 資料庫欄位再做(啟動容器會執行)
pip install.sh -r requirements.txt # 有新增 (容器內暫時 建立image和啟動容器會執行)
touch server/uwsgi.ini
```


## rest_framework drf-spectacular 介紹

[drf-spectacular](https://drf-spectacular.readthedocs.io/en/latest/)
[rest_framework](https://www.django-rest-framework.org/)

## logger 操作

```py
# 新 APP 建立 
setting.py > LOGGING > loggers > 建立app名的字典

# 使用 logger
import logging
logger = logging.getLogger(__name__)

logger.debug('debug')
logger.info('info')
logger.warning('warning')
logger.error('error')
logger.critical('critical')

# debug 已設定在 setting.py DEBUG = False 的時候使用
```

## geometry 座標

models欄位，座標用到 geometry 需要更改db引擎

```py
# local_settings.py >> DATABASES >> ENGINE
'ENGINE': 'django.contrib.gis.db.backends.mysql', 
```

## 所他型態資料匯入

step1. 右鍵lbor_v3.common_obligee資料表 -> 導入數據

step2. 從表導入 -> 來源:104的lbor_info.infos_obligee

step3. 跳過 id, identity, address欄位

step4. 下一步下一步下一步 完成

## 所他型態def使用方法

```py
from common.util import get_obligee, check_property, check_property_one
obligee_dict = get_obligee()
name = '陳＊＊'
name_dict = [{"ownerName":"華南商業銀行股份有限公司","regodr":"0004000"}]
result_one = check_property_one(name, obligee_dict)
result_many = check_property(name_dict, obligee_dict)
```

多筆
|分類 |未知| 政府| 私人|公司| 租貸| 銀行| 最後登記型態|  
|----|----|----|--- |----|----|----|-----------|
|計算 | 0  | 0  |  0 | 0 | 0   | 1  |   5       |

單筆 : PropertyTypeEnum.PRIVATE


## 其他資訊

Q: django.db.utils.OperationalError: (1153, "Got a packet bigger than 'max_allowed_packet' bytes")

A: 收到的數據包大於max_allowed_packet限制

一次性的解決方案

```sql
-- 進入sql
mysql -u root -p -h 127.0.0.1 -P 3306

-- 變更全域限制
set global net_buffer_length=1000000; 
set global max_allowed_packet=1000000000;

-- 並保持此終端機打開
```

<details><summary>筆記</summary>

## 筆記
### lbor
python manage.py parser_lbor_one
python manage.py update_from_104 --lb l

python manage.py parser_lbor_again --lbkey E_17_2149_0670-0000
python manage.py runserver 8000

### 新環境一定要執行的指令
localhost打開匯入縣市行政區段小段
python manage.py system_env (寫入系統變數)
python manage.py input_obligee (從104匯入obligee)


docker exec -ti lbor_v3_web_1 /bin/bash

發送信號 Nginx 重新加載所有內容
docker kill --signal=HUP lbor_v3-nginx-1

> [xhtml2pdf 頁數未顯示修正 套件問題](https://github.com/xhtml2pdf/xhtml2pdf/pull/628/files)

docker 解決方式

```bash
# 查看套件安裝位置
pip show xhtml2pdf

# 需要安裝 nano 編輯器
sudo apt install nano

cd /usr/local/lib/python3.10/site-packages/xhtml2pdf
nano xhtml2pdf_reportlab.py

# 搜尋列 ctrl + shift + -

按照網址上面的方式解決問題
```


</details>

[連結](https://gitlab+deploy-token-1:uSCw3RN9HwRKvXw7yEjK@gitlab.wsos.com.tw/wsos_dev/lbor_v3.git)
