# lbor V3 列表 commands 功能介紹

## [map 資料匯入 lbor_v3](/extra_land/management/commands/polygon_input.py)

```py
# map 資料匯入 lbor_v3 (-k：輸入地號範圍，例：A、A_01、A_01_0600)
python manage.py polygon_input -k A_01
```

## [謄本列表統計](/common/management/commands/daily_statistics.py)

```py
'''
參數說明
-l 土建類別： 1.全部 2.土地 3.建物
-t 謄本列表類別： 1.全部 2.列表 3.謄本
-f 強制模式(更新時間大於查詢時間是否強制更新)： 0.不強制 1.強制
--date 起始日期 2017-11-2
--date1 結束日期 2022-9-10
'''

python manage.py daily_statistics -l 1 -t 1 --date 2022-7-1 --date1 2022-11-1 -f 1
```
