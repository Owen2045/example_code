# docker

## 1. 先決條件 安裝docker 環境

[docker-ce 安裝](https://docs.docker.com/engine/install/ubuntu/)

[docker-compose](https://docs.docker.com/compose/install/compose-plugin/)

```bash
# docker-compose
sudo curl -SL https://github.com/docker/compose/releases/download/v2.6.0/docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose
sudo ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose
sudo chmod 777 /usr/bin/docker-compose
```

## 2. 連接埠確認

專案會使用到以下連接埠

> 資料庫 3304
> lbor_v3專案 8000 (debug模式使用)
> redis 快取 6379 (可關可不關)

衝突可以嘗試: sudo service redis stop

> nginx 代理 80 443

衝突可以嘗試: sudo service nginx stop

> rabbitmq-server 5672

衝突可以嘗試: sudo service rabbitmq-server stop

```bash
# 轉換 docker local
sudo service redis stop && sudo service nginx stop && sudo service rabbitmq-server stop
sudo service redis start && sudo service nginx start && sudo service rabbitmq-server start
```

## 3. 容器配置

```bash
# docker-compose.yml
# 可在裡面修改debug模式
# windows runserver 要改成 0:8000
```

## 4. .env 配置

```bash
# .env.example 變更名稱為 .env
```

## 5. config.ini 配置

```bash
# config.ini.example 變更名稱為 config.ini
```

## 6. local_settings.py 配置

```bash
# local_settings.py.example 變更名稱為 local_settings.py
# 並把 docker 相關的取消註解

# CELERY_BROKER_URL的帳號密碼要對應 .env 的 RABBITMQ_DEFAULT_USER RABBITMQ_DEFAULT_PASS
CELERY_BROKER_URL = 'amqp://帳號:密碼@rabbitmq:5672/my_vhost'
```

## 7. 建置相關資料夾

mkdir -p ~/marindb/lbor_v3 && mkdir -p ~/data/lbor_v3

## 8. 建置專案並啟動

```bash
# 啟動
docker-compose up

# 第一次 執行專案須建立資料表
# 進入 lbor_django 容器裡面
docker exec -ti lbor_django /bin/bash
# makemigrations 的動作
python manage.py makemigrations user common land building extra_building extra_land
python manage.py migrate
```

## 9. docker 其他相關指令

```bash
# 檢視容器
docker ps

# uwsgitop 使用
docker exec -ti lbor_django /bin/bash -c "cd /tmp/ && uwsgitop lbor_v3-stat.sock"

# 進入 lbor_django 容器裡面
docker exec -ti lbor_django /bin/bash

# 關閉專案
docker-compose down
```
