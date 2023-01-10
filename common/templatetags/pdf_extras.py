from django import template
from django.utils.safestring import mark_safe

import datetime

register = template.Library()
# 只能接受一個參數
# register.filter

# 可以接受多可參數
# register.simple_tag

@register.filter
def notice_ym(value, data):
    # 公告現值 公告地價
    # {{ mark.land_notice_price_date | notice_ym:mark.query_time }}
    if value:
        return value
    elif data:
        return "民國{}年{}月".format(int(data[:4])-1911, 1)
    else:
        return ''

@register.filter
def other_remark(value):
    # 其他登記事項 換行
    if value:
        text = "，".join(value)
    else:
        text = '(空白)'
    return strNewline(text, 40, 8)

@register.filter
def add_head(value, data):
    # 開頭新增文字 一般用於寫入民國
    if value in data:
        return value
    else:
        return mark_safe("{}{}".format(data, value))

@register.simple_tag
def locate_lbkey(value, num):
    # 地上建物建號 座落地號
    # 這裡還可以優化 開頭空格 多少字要換行 換個段小段要換行
    nbsp = '<br>'
    for _ in range(num):
        nbsp += '&nbsp;'

    key_val_list = []
    for key, vals in value.items():
        key_val = [key] + vals
        key_val_str = ''
        is_one_line = True
        for val in key_val:
            line_num = 115
            if is_one_line:
                line_num -= len(key_val[0])*2
            if len(key_val_str) + len(val)  <= line_num:
                key_val_str += f'{val}&nbsp;'
            else:
                key_val_list.append(key_val_str)
                key_val_str = ''
                is_one_line = False
        key_val_list.append(key_val_str)
    return mark_safe(nbsp.join(key_val_list))

@register.filter
def split_data(value, num):
    # 收件年期 字號
    data = value.split(' ')
    if num <= len(data):
        return data[num]
    return ''

@register.filter
def collateral_lbkey(value):
    # 共同擔保地號 共同擔保建號
    # 原先作法顯示 段小段 地建號 登記次序 但因為有數量龐大導致謄本好幾千頁
    # 改成顯示 段小段 地建號 去除重複
    collateral_dict = {}
    collateral_list = []
    for data in value:
        # collateral_list.append("{} {} {}".format(data.get('region', ''), data.get('lbno', ''), data.get('regno', '')))
        region = data.get('region', '')
        lbno = data.get('lbno', '')
        if region and lbno:
            if region in collateral_dict:
                collateral_dict[region].append(lbno)
            else:
                collateral_dict[region] = [lbno]

    for key, value in collateral_dict.items():
        collateral_list.append("{} {}".format(key, ' '.join(list(set(value)))))
    return mark_safe('<br>'.join(collateral_list))

@register.filter
def time_format(value):
    # 2022-07-26T17:17:34+08:00
    # 轉換成 民國111年09月27日 14時03分35秒
    if value:
        value = value.split('+')[0]
        data_time = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
        now_str = "民國{}年{}".format(data_time.year-1911, data_time.strftime("%m月%d日 %H時%M分%S秒"))
        return now_str
    return value

@register.simple_tag
def strNewline(value, num, num1):
    # 字串換行
    # 使用方式不一樣 {% strNewline mark.urban_name 16 7 %}
    if not value:
        return
    text1 = [value[i:i+num] for i in range(0, len(value), num)]
    nbsp = '<br>'
    for _ in range(num1):
        nbsp += '&nbsp;'
    return mark_safe(nbsp.join(text1))

@register.simple_tag
def listNewline(value, num):
    # 列表換行
    nbsp = '<br>'
    for _ in range(num):
        nbsp += '&nbsp;'
    return mark_safe(nbsp.join(value))