FROM python:3.10

LABEL maintainer service

# 設定環境變數
# ENV PYTHONDONTWRITEBYTECODE 1防止 Python 將 pyc 文件複製到容器中。
ENV PYTHONDONTWRITEBYTECODE 1
# ENV PYTHONUNBUFFERED 1確保將 Python 輸出記錄到終端，從而可以實時監控 Django 日誌。
ENV PYTHONUNBUFFERED 1
# 忽略PIP用su問題
ENV PIP_ROOT_USER_ACTION=ignore

# 在容器內/var/www/html 建立lbor_v3資料夾
RUN mkdir -p /var/www/html/lbor_v3

# 設定工作目錄
WORKDIR /var/www/html/lbor_v3

# 當前目錄文件 加入工作目錄
COPY requirements.txt /var/www/html/lbor_v3/requirements.txt

RUN apt-get update && apt-get install -y \
    binutils \
    libproj-dev \
    gdal-bin

RUN pip install --upgrade pip
# 安專依賴
RUN pip install six
RUN pip install -r requirements.txt

# 建立郵政編碼索引
RUN python -m zipcodetw.builder
