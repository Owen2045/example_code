# lbor V3 列表 commands 功能介紹

## [失效段小段](/common/management/commands/invalid_region.py)

> 把段小段內的地建號設為失效

範例:

```py
# 預覽失效數量
python manage.py invalid_region

# 設為失效
python manage.py invalid_region -c
```

## [v2 匯入失效清單](/common/management/commands/get_lbor_invalid_104.py)

```py
python manage.py get_lbor_invalid_104 --lb l
```

## [多核心批次解析lbor log](/common/management/commands/parser_lbor_one.py)


```py
# 有其他功能可以使用
python manage.py parser_lbor_one
```

## [排程解析lbor log](/common/management/commands/parser_lbor.py)

```py
python manage.py parser_lbor
```

## [新舊地建號轉換](/common/management/commands/new_old_change.py)

```py
python manage.py new_old_change
```

## [政府資料匯入](/common/management/commands/update_from_gov.py)

```py
python manage.py update_from_gov
```
