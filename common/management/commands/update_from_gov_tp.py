
from django.core.management.base import BaseCommand
from building.models import Tplog
from common.util import get_dba
from common.enums import QuerySystemEnum, RuleTypeEnum
from common.serializers import FeedbackLborSerializer, FeedbackTplogSerializer
from common.models import SystemConfig
from django.core.cache import cache

from multiprocessing import cpu_count, Pool
from dateutil import parser
from tqdm import tqdm

import pandas as pd
import configparser
import logging
import time
import re
import os

logger = logging.getLogger(__name__)
MAX_STEP = 50

'''
備註：
不跑的縣市 R,L,Z

Z匯入有問題
RL升格 資料難處理
'''
Batch_step = 100

def get_query_time(data):
    if data['異動日期'] == '' or data['異動時間'] == '':
        return ''
    query_time = time.strptime(f"{data['異動日期']} {data['異動時間']}", "%Y%m%d %H%M%S")
    query_time = time.strftime("%Y-%m-%d %H:%M:%S", query_time)
    return query_time

def get_lbkey(data, lb_type):
    if lb_type == 'L':
        lbkey = f"{data['縣市代號']}_{data['鄉鎮市區']}_{data['段小段']}_{data['地建號'][:4]}-{data['地建號'][4:]}"
    else:
        lbkey = f"{data['縣市代號']}_{data['鄉鎮市區']}_{data['段小段']}_{data['地建號'][:5]}-{data['地建號'][5:]}"
    if len(lbkey) != 19:
        return ''
    return lbkey

def date_process(data):
    result = None
    try:
        data = str(int(data))
        result = parser.parse(data)
        result = result.strftime('%Y/%m/%d')
    except:
        pass
    return result

def get_code(code_df, code_type, code_num, code_office):
    result = ''
    if not code_df.empty:
        p1 = code_df['代碼類別'] == code_type
        p2 = code_df['代碼代號'] == code_num
        p3 = code_df['事務所代號'] == code_office
        c_class = code_df[(p1 & p2 & p3)]

        if not c_class.empty:
            result = c_class.iloc[0]['代碼內容']
    return result

def get_hide_name(data):
    if data['類別'] == '1':
        return f"{data['姓名'][0]}＊＊"
    return data['姓名']

def rep_blank(data):
    result = ''
    if isinstance(data, str):
        result = data.replace(' ', '')
    else:
        result = data
    return result

def str_cover_dict(data):
    if isinstance(data, dict):
        return data
    else:
        return {}

def id_cover(data):
    result = ''
    if data:
        red = re.match(r'[A-Z][0-9]', data)
        if red and len(data) == 10:
            try:
                result = data.replace(data[4:-1], '*' * len(data[4:-1]))
            except:
                result = data
        else:
            result = data
    return result

def cover_time(f_time):
    if f_time and len(f_time) == 7:        
        y = f_time[0:3]
        m = f_time[3:5]
        d = f_time[5:]
        try:
            y = int(y) + 1911
            f_time = parser.parse(f'{y}-{m}-{d}').strftime('%Y/%m/%d %H:%M:%S')
        except:
            pass
    else:
        try:
            f_time = parser.parse(f_time).strftime('%Y/%m/%d %H:%M:%S')
        except:
            pass
    return f_time

def FA_data(df, name_str, area_str):
    data = []
    for row in df.itertuples():  
        fd = {name_str: row.floor_att,
                area_str: {
                    "@P1": row.層次或附屬建物面積,
                    "#text": f'{row.層次或附屬建物面積} 平方公尺'
                }
            }
        data.append(fd)
    return data

def MC_data(df):
    data = []
    for row in df.itertuples():  
        fd = {
                "權利範圍": {
                    "#text": f'{row.權利範圍分母}分之{row.權利範圍分子} 平方公尺',
                    "@P2": row.權利範圍分子,
                    "@P1": row.權利範圍分母,
                },
                "建號": row.主建物建號,
                "段小段": row.主建物段小段
            }
        data.append(fd)
    return data

def feed_back_tp(data, lbtype):
    if lbtype == 'L':
        ostr = '土地所有權人列表'
        rstr = '土地他項權利人列表'
        mstr = '土地標示部'
    else:
        ostr = '建物所有權人列表'
        rstr = '建物他項權利人列表'
        mstr = '建物標示部'
    entry = []
    for i in data:
        entry_dic = {}
        lbkey = str_cover_dict(i.get(mstr, {})).get('@KEY')
        if not lbkey:
            continue
        entry_dic['lbkey'] = lbkey
        entry_dic['query_system'] = 32
        entry_dic['owners'] = i.get(ostr)
        entry_dic['rights'] = i.get(rstr)
        entry_dic['rules'] = 3
        entry_dic['transcript'] = {'transcript_info': i}
        entry_dic['query_time'] = str_cover_dict(i.get(mstr)).get('query_time')

        entry.append(entry_dic)
        
    serializer = FeedbackTplogSerializer(data=entry, many=True)
    if serializer.is_valid():
        serializer.save()
    # else:
    #     slice_df.to_excel('222.xlsx')
    #     print(serializer.errors)

class DataUpdate(object):
    # 讀取目前處理進度

    def __init__(self, city):
        # 參數 檢測是否完成
        self.city = city
        self.l_complete = False
        self.b_complete = False

        ########################################################
        # 進度讀取
        self.l_schedule, _ = SystemConfig.objects.get_or_create(env=f'{city}_l_tp')
        self.l_step = 0
        if self.l_schedule.integer:
            self.l_step = self.l_schedule.integer

        self.b_schedule, _ = SystemConfig.objects.get_or_create(env=f'{city}_b_tp')
        self.b_step = 0
        if self.b_schedule.integer:
            self.b_step = self.b_schedule.integer
        # ##########################################################################
        
        # 讀取檔案
        fullpath = os.path.join("政府", city)

        # 讀代碼擋
        self.code_df = cache.get(f"{city}_code_df", pd.DataFrame([]))
        print('read code_df')
        if self.code_df.empty:
            print('code_df not in cache')
            self.code_df = self.read_code(fullpath)
            # cache.set(f"{city}_code_df", self.code_df, 3600)

        # 土地: 標示
        self.l_m_df = cache.get(f"{city}_l_m_df", pd.DataFrame([]))
        print('read l_m_df')
        if self.l_m_df.empty:
            print('l_m_df not in cache')
            self.l_m_df = self.get_land_mark_df(fullpath)
            # cache.set(f"{city}_l_m_df", self.l_m_df, 3600)

        # 土地: 所有
        self.l_o_df = cache.get(f"{city}_l_o_df", pd.DataFrame([]))
        print('read l_o_df')
        if self.l_o_df.empty:
            print('l_o_df not in cache')
            self.l_o_df = self.get_land_owner_df(fullpath)
            # cache.set(f"{city}_l_o_df", self.l_o_df, 3600)

        # 建物: 標示
        self.b_m_df = cache.get(f"{city}_b_m_df", pd.DataFrame([]))
        print('read b_m_df')
        if self.b_m_df.empty:
            print('b_m_df not in cache')
            self.b_m_df = self.get_build_mark_df(fullpath)
            # cache.set(f"{city}_b_m_df", self.b_m_df, 3600)

        # 建物: 所有權
        self.b_o_df = cache.get(f"{city}_b_o_df", pd.DataFrame([]))
        print('read b_o_df')
        if self.b_o_df.empty:
            print('b_o_df not in cache')
            self.b_o_df = self.get_build_owner_df(fullpath)
            # cache.set(f"{city}_b_o_df", self.b_o_df, 3600)

        # 他項: 土地 建物
        self.l_r_df = cache.get(f"{city}_l_r_df", pd.DataFrame([]))
        print('read l_r_df')
        if self.l_r_df.empty:
            print('l_r_df not in cache')
            self.l_r_df = self.get_build_land_right_df(fullpath)[0]
            # cache.set(f"{city}_l_r_df", self.l_r_df, 3600)
        
        # 同上
        self.b_r_df = cache.get(f"{city}_b_r_df", pd.DataFrame([]))
        print('read b_r_df')
        if self.b_r_df.empty:
            print('b_r_df not in cache')
            self.b_r_df = self.get_build_land_right_df(fullpath)[1]
            # cache.set(f"{city}_b_r_df", self.b_r_df, 3600)

        # 權利人
        self.p_df = cache.get(f"{city}_p_df", pd.DataFrame([]))
        print('read p_df')
        if self.p_df.empty:
            print('p_df not in cache')
            self.p_df = self.get_people_df(fullpath)
            # cache.set(f"{city}_p_df", self.p_df, 3600)

        # 其他登記事項
        self.other_remark_df = cache.get(f"{city}_other_remark_df", pd.DataFrame([]))
        print('read other_remark_df')
        if self.other_remark_df.empty:
            print('other_remark_df not in cache')
            self.other_remark_df = self.get_other_remark(fullpath)
            # self.other_remark_df.set_index(keys=['段小段', '地建檔號', '登記次序'], inplace=True)
            # self.other_remark_df.reset_index()
            # cache.set(f"{city}_other_remark_df", self.other_remark_df, 3600)
        
        # 土地前次轉移現值
        self.l_l_vp = cache.get(f"{city}_l_l_vp", pd.DataFrame([]))
        if self.l_l_vp.empty:
            print('land_last_vp_df not in cache')
            self.l_l_vp = self.get_last_change_vp(fullpath)
            # cache.set(f"{city}_l_l_vp", self.l_l_vp, 3600)

        # 建物分層 附屬建物
        self.b_fa_df = cache.get(f"{city}_b_fa_df", pd.DataFrame([]))
        if self.b_fa_df.empty:
            print('b_fa_df is not in cache')
            self.b_fa_df = self.get_build_fa(fullpath)
            # cache.set(f"{city}_b_fa_df", self.b_fa_df, 3600)

        # get_MC_df
        self.b_MC_df = cache.get(f"{city}_b_MC_df", pd.DataFrame([]))
        if self.b_MC_df.empty:
            print('b_MC_df is not in cache')
            self.b_MC_df = self.get_MC_df(fullpath)
            # cache.set(f"{city}_b_MC_df", self.b_MC_df, 3600)

############################################################

    def read_code(self, fullpath):
        # 讀代碼擋
        code_df = pd.DataFrame([])
        try:
            code_csv = os.path.join(fullpath, '代碼檔.csv')
            code_df = pd.read_csv(code_csv, dtype=object)
        except:
            pass
        return code_df

    def get_land_mark_df(self, fullpath):
        # 土地標示部
        l_m_csv = os.path.join(fullpath, '土地標示部.csv')
        l_m_df = pd.read_csv(l_m_csv, dtype=object)
        l_m_df = l_m_df.fillna('')
        # 篩選需要欄位
        l_m_del_list = ['縣市', '視中心橫座標', '圖幅號', '原複丈收件年', '原複丈收件字', '原複丈收件號', '地籍藍晒圖幅號', '收件年', '收件字', '收件號', '視中心縱座標']
        for l_m_del in l_m_del_list:
            del l_m_df[l_m_del]
        l_m_df = l_m_df.rename(columns={'地號': '地建號', '使用地': '使用地類別'}) #'計算面積': '面積',
        l_m_df['query_time'] = l_m_df.apply(get_query_time, axis=1)
        del l_m_df['異動日期'], l_m_df['異動時間']
        none_time_idx = l_m_df[l_m_df["query_time"] == ''].index
        l_m_df = l_m_df.drop(none_time_idx)
        l_m_df['lbkey'] = l_m_df.apply(get_lbkey, axis=1, args=('L',))
        none_time_idx = l_m_df[l_m_df["lbkey"] == ''].index
        l_m_df = l_m_df.drop(none_time_idx)
        return l_m_df

    def get_land_owner_df(self, fullpath):
        # 土地所有權部
        l_o_csv = os.path.join(fullpath, '土地所有權部.csv')
        l_o_df = pd.read_csv(l_o_csv, dtype=object)
        l_o_df = l_o_df.fillna('')
        l_o_df = l_o_df.rename(columns={'地號': '地建號', '所有權統一編號': '統一編號'})
        return l_o_df

    def get_build_mark_df(self, fullpath):
        # 建物標示部
        b_m_csv = os.path.join(fullpath, '建物標示部.csv')
        b_m_df = pd.read_csv(b_m_csv, dtype=object)

        b_m_df = b_m_df.fillna('')
        b_m_del_list = ['收件年期','收件字','收件號']
        for b_m_del in b_m_del_list:
            del b_m_df[b_m_del]
        b_m_df = b_m_df.rename(columns={'建號': '地建號'})

        b_m_df['query_time'] = b_m_df.apply(get_query_time, axis=1)
        del b_m_df['異動日期'], b_m_df['異動時間']

        none_time_idx = b_m_df[b_m_df["query_time"]==''].index
        b_m_df = b_m_df.drop(none_time_idx)

        b_m_df['lbkey'] = b_m_df.apply(get_lbkey, axis=1, args=('B',))
        none_time_idx = b_m_df[b_m_df["lbkey"]==''].index
        b_m_df = b_m_df.drop(none_time_idx)
        return b_m_df

    def get_build_owner_df(self, fullpath):
        # 建物所有權部
        b_o_csv = os.path.join(fullpath, '建物所有權部.csv')
        b_o_df = pd.read_csv(b_o_csv, dtype=object)
        b_o_df = b_o_df.fillna('')
        b_o_df = b_o_df.rename(columns={'建號': '地建號', '所有權統一編號': '統一編號'})
        return b_o_df

    def get_build_land_right_df(self, fullpath):
        # 他項權利部
        r_csv = os.path.join(fullpath, '他項權利部.csv')
        r_df = pd.read_csv(r_csv, dtype=object)
        r_df = r_df.fillna('')
        # 地建別: C 地號, F 建號
        r_df = r_df.rename(columns={'權利人統一編號': '統一編號'})
        l_r_df = r_df[r_df['地建別']=='C'].reset_index(drop=True)
        del l_r_df['地建別']

        b_r_df = r_df[r_df['地建別']=='F'].reset_index(drop=True)
        del b_r_df['地建別']

        return l_r_df, b_r_df

    def get_people_df(self, fullpath):
        # 權利人
        p_csv = os.path.join(fullpath, '權利人.csv')
        p_df = pd.read_csv(p_csv, dtype=object)

        p_df = p_df.fillna('')
        p_list = ['地址','權利人出生日期區分','出生日期','異動日期','異動時間']
        for p_del in p_list:
            del p_df[p_del]
        p_df['姓名'] = p_df.apply(get_hide_name, axis=1)
        p_df["姓名"] = p_df["姓名"].str.replace("\u3000","")
        return p_df

    def get_other_remark(self, fullpath):
        # 其他登記事項
        other_csv = os.path.join(fullpath, '其他登記事項.csv')
        other_df = pd.read_csv(other_csv, dtype=object)
        other_df = other_df.fillna('')
        other_df = other_df.rename(columns={'段小段 (或空白)': '段小段', '地(建)號 (或他項權利檔號)': '地建檔號', '登記次序(或空白)': '登記次序'})
        return other_df

    def get_last_change_vp(self, fullpath):
        # 土地前次轉移現值
        other_csv = os.path.join(fullpath, '土地前次移轉現值.csv')
        other_df = pd.read_csv(other_csv, dtype=object)
        other_df = other_df.fillna('')
        other_df = other_df.rename(columns={'地號': '地建號', '所有權登記次序': '登記次序'})
        return other_df

    def get_build_fa(self, fullpath):
        other_csv = os.path.join(fullpath, '建物分層或附屬建物.csv')
        other_df = pd.read_csv(other_csv, dtype=object)
        other_df = other_df.fillna('')
        other_df = other_df.rename(columns={'建號': '地建號'})
        return other_df

    def get_MC_df(self, fullpath):
        other_csv = os.path.join(fullpath, '建物主建物共用部分.csv')
        other_df = pd.read_csv(other_csv, dtype=object)
        other_df = other_df.fillna('')
        # other_df = other_df.rename(columns={'建號': '地建號'})
        return other_df

    def apply_main_use(self, df, code_t, code_n, office_c):
        use_code = get_code(code_df=self.code_df, code_type=code_t, code_num=df[code_n], code_office=df[office_c])
        return use_code


    # 處理標示部格式
    def get_lb_mark_dict(self, data, lbt):
        reg_date = date_process(data['登記日期'])
        reg_res = get_code(code_df=self.code_df, code_type='06', code_num=data['登記原因'], code_office=data['事務所代號'])
        
        # 其他登記事項
        qa = self.other_remark_df['段小段'] == data['段小段']
        qb = self.other_remark_df['地建檔號'] == data['地建號']
        ormk = self.other_remark_df[(qa & qb)]
        ormk_list = ormk.to_dict(orient='records')
        ormk_data = []
        if ormk_list:
            for i in ormk_list:
                o_code = i.get('其他登記事項代碼')
                o_data = i.get('其他登記事項內容')
                office_ = i.get('事務所代號')
                o_res = get_code(code_df=self.code_df, code_type='30', code_num=o_code, code_office=office_)
                full_str = f'{o_res}{o_data}'
                ormk_data.append(full_str)

        mark_dict = {
            "@KEY": data['lbkey'], 
            "登記日期": {"@P1": cover_time(reg_date), "#text": data['登記日期']},
            "登記原因": reg_res,
            "其他登記事項": {"@資料筆數": len(ormk_data), "資料": ormk_data},
            "查詢日期": {"@P1": cover_time(data['query_time']), "#text": ''},
            "query_time": data['query_time']
        }
        if lbt == 'l':
            land_Purpose = get_code(code_df=self.code_df, code_type='08', code_num=data['地目'], code_office=data['事務所代號'])
            use_zone = get_code(code_df=self.code_df, code_type='11', code_num=data['使用分區'], code_office=data['事務所代號'])
            use_classfy = get_code(code_df=self.code_df, code_type='12', code_num=data['使用地類別'], code_office=data['事務所代號'])

            mark_dict["地目"] = land_Purpose
            mark_dict["等則"] = data['等則']
            mark_dict["面積"] = {"@P1": rep_blank(data['面積']), "#text": ''}
            mark_dict["使用分區"] = use_zone
            mark_dict["使用地類別"] = use_classfy
            mark_dict["公告現值"] = {"@P1": '', "@P2": data['公告現值'], "#text": ''}
            mark_dict["公告地價"] = {"@P1": '', "@P2": data['公告地價'], "#text": ''}

        elif lbt == 'b':
            # 附屬 分層=================================================
            f1 = self.b_fa_df['段小段']==data['段小段']
            f2 = self.b_fa_df['事務所代號']==data['事務所代號']
            f3 = self.b_fa_df['地建號']==data['地建號']
            FA = self.b_fa_df[(f1 & f2 & f3)]
            # M = 分層 S = 附屬建物
            floor = FA[FA['分層或附屬物識別碼'] == 'M']
            if not floor.empty:
                floor['floor_att'] = floor.apply(self.apply_main_use, axis=1, args=('14', '層次或附屬建物用途', '事務所代號',))
            floor_data = FA_data(floor, name_str='層次', area_str='層次面積')

            attach = FA[FA['分層或附屬物識別碼'] == 'S']
            if not attach.empty:
                attach['floor_att'] = attach.apply(self.apply_main_use, axis=1, args=('14', '層次或附屬建物用途', '事務所代號',))
            attach_data = FA_data(attach, name_str='附屬建物', area_str='面積')
            # =========================================================
            # 主建 共有=================================================
            m1 = self.b_MC_df['主建物建號']==data['地建號']
            m2 = self.b_MC_df['主建物段小段']==data['段小段']
            M = self.b_MC_df[m1 & m2]
            if not M.empty:
                M['main_build'] = M.apply(self.apply_main_use, axis=1, args=('15', '權利範圍類別', '事務所代號',))
            main_build = MC_data(M)

            c1 = self.b_MC_df['共用部分建號']==data['地建號']
            c2 = self.b_MC_df['共用部分段小段']==data['段小段']
            C = self.b_MC_df[c1 & c2]
            if not C.empty:
                C['main_build'] = C.apply(self.apply_main_use, axis=1, args=('15', '權利範圍類別', '事務所代號',))
            common_build = MC_data(C)
            # print(common_build)
            # =========================================================

            mark_dict["建物門牌"] = data['建物門牌']
            mark_dict["主要用途"] = get_code(code_df=self.code_df, code_type='0B', code_num=data['主要用途'], code_office=data['事務所代號'])
            mark_dict["主要建材"] = get_code(code_df=self.code_df, code_type='0C', code_num=data['主要建材'], code_office=data['事務所代號'])
            mark_dict["建物層數"] = {"@P1": data['建物層數'], "#text": data['建物層數']}
            mark_dict['建築完成日期'] = {"@P1": cover_time(data['建築完成日期']), "#text": data['建築完成日期']}
            mark_dict['建物分層'] = {"@資料筆數": len(floor_data), "資料": floor_data}
            mark_dict['附屬建物'] = {"@資料筆數": len(attach_data), "資料": attach_data}
            mark_dict['主建物資料'] = {"資料": main_build}
            mark_dict['共有部分'] = {"@資料筆數": len(common_build), "資料": common_build}
        return mark_dict
    
    # 處理所他格式
    def get_or_dict(self, data, group_df, ortype='o', lbtype='l'):
        key = (data['段小段'], data['地建號'], data['鄉鎮市區'], data['縣市代號'])
        key_df = group_df.get_group(key)
        key_df = key_df.dropna(subset=['登記次序'], axis=0, how='any')

        or_data = []
        if key_df.size > 0:
            key_df = key_df.fillna('')
            for row in key_df.itertuples():
                reg_res = get_code(code_df=self.code_df, code_type='06', code_num=row.登記原因_y, code_office=row.事務所代號)
                or_dict = {}

                if ortype == 'o':
                    qa = self.other_remark_df['段小段'] == row.段小段
                    qb = self.other_remark_df['登記次序'] == row.登記次序                    
                    qc = self.other_remark_df['事務所代號'] == row.事務所代號
                    qd = self.other_remark_df['地建檔號'] == row.地建號

                    ormk = self.other_remark_df[(qa & qc & qd & qb)]
                    ormk_list = ormk.to_dict(orient='records')
                    ormk_data = []
                    if ormk_list:
                        for i in ormk_list:
                            o_code = i.get('其他登記事項代碼')
                            o_data = i.get('其他登記事項內容')
                            office_ = i.get('事務所代號')
                            o_res = get_code(code_df=self.code_df, code_type='30', code_num=o_code, code_office=office_)
                            full_str = f'{o_res}{o_data}'
                            if full_str not in ['Null', 'null', None, '']:
                                ormk_data.append(full_str)

                    range_type = get_code(code_df=self.code_df, code_type='15', code_num=row.權利範圍類別, code_office=row.事務所代號)
                    or_dict['登記次序'] = row.登記次序
                    or_dict['所有權人'] = row.姓名
                    or_dict['登記日期'] = date_process(row.登記日期_y)
                    or_dict['登記原因'] = reg_res
                    or_dict['原因發生日期'] = date_process(row.登記原因發生日期)
                    or_dict['統一編號'] = id_cover(row.統一編號)
                    if range_type in ['Null', 'null']:
                        range_type = ''
                    or_dict['權利範圍'] = {"@P1": row.權利範圍分子, "@P2": row.權利範圍分母, "#text": f"{range_type}{row.權利範圍分母}分之{row.權利範圍分子}"}
                    or_dict['權狀字號'] = row.權狀年字號
                    or_dict['其他登記事項'] = {"@資料筆數": len(ormk_data), "資料":ormk_data}
                    if lbtype == 'l':
                        or_dict['申報地價'] = {"@P1": "", "@P2": row.申報地價, "#text": ""}

                        text = get_code(code_df=self.code_df, code_type='15', code_num=row.歷次取得權利範圍類別, code_office=row.事務所代號)
                        if text in ['Null', None, 'null']:
                            text = ''
                        full_dict = {'年月': row.前次移轉年月, 
                                     '地價': {'@P2': row.前次移轉現值, '#text': ''},
                                     '歷次取得權利範圍': {'@P1': row.歷次取得持分分子, '@P2':row.歷次取得持分分母, '#text': f'{text}{row.歷次取得持分分母}分之{row.歷次取得持分分子}'}
                                    }

                        or_dict['前次移轉現值或原規定地價'] = {"@資料筆數": len([full_dict]), "資料": [full_dict]}

                elif ortype == 'r':
                    qa = self.other_remark_df['段小段'] == row.段小段
                    qc = self.other_remark_df['事務所代號'] == row.事務所代號
                    qd = self.other_remark_df['地建檔號'] == row.他項權利檔號

                    ormk = self.other_remark_df[(qa & qc & qd)]
                    ormk_list = ormk.to_dict(orient='records')
                    ormk_data = []
                    if ormk_list:
                        for i in ormk_list:
                            o_code = i.get('其他登記事項代碼')
                            o_data = i.get('其他登記事項內容')
                            office_ = i.get('事務所代號')
                            o_res = get_code(code_df=self.code_df, code_type='30', code_num=o_code, code_office=office_)
                            full_str = f'{o_res}{o_data}'
                            if full_str not in ['Null', 'null', None, '']:
                                ormk_data.append(full_str)

                    range_type = get_code(code_df=self.code_df, code_type='15', code_num=row.債權權利範圍類別, code_office=row.事務所代號)
                    gtr = get_code(code_df=self.code_df, code_type='31', code_num=row.限定擔保債權金額種類, code_office=row.事務所代號)
                    or_dict['登記次序'] = row.登記次序
                    or_dict['所有權人'] = row.姓名
                    or_dict['登記日期'] = date_process(row.登記日期_y)
                    or_dict['登記原因'] = reg_res
                    or_dict['流抵約定'] = row.流抵約定種類
                    or_dict['權利標的'] = row.標的種類
                    or_dict['統一編號'] = id_cover(row.統一編號)
                    if range_type in ['Null', 'null', None]:
                        range_type = ''
                    or_dict['設定權利範圍'] = {"@P1": row.設定權利範圍持分分子, "@P2": row.設定權利範圍持分分母, "#text": f"{range_type}{row.設定權利範圍持分分母}分之{row.設定權利範圍持分分子}"}
                    or_dict['收件年期字號'] = f'{row.收件年期}-{row.收件字}-{row.收件號}'
                    or_dict['擔保債權總金額'] = {"@P1": None, "#text": row.限定擔保債權金額說明}
                    or_dict['擔保債權種類及範圍'] = gtr
                or_data.append(or_dict)
        return or_data

    def get_or_list_dict(self, data, group_df, ortype='o', lbtype='l'):
        key = (data['段小段'], data['地建號'], data['鄉鎮市區'], data['縣市代號'])
        key_df = group_df.get_group(key)
        key_df = key_df.dropna(subset=['登記次序'], axis=0, how='any')

        or_dict = {}
        if key_df.size > 0:
            key_df = key_df.fillna('')
            for row in key_df.itertuples():
                or_dict[row.登記次序] = row.姓名
        return or_dict

    def handle(self):
        t = 0
        while True:
            # 組合土地資料
            if self.l_complete == False:
                self.land_handle()
            if self.b_complete == False:
                self.bulid_handle()                

            if self.l_complete and self.b_complete:
                print('查詢完成', self.city)
                return
            t += 1
            print(f'縣市: {self.city} 次數: {t}')

    def land_handle(self):
        new_df = pd.DataFrame([])
        # 標示部來源
        slice_df = self.l_m_df[self.l_step : self.l_step+MAX_STEP].reset_index(drop=True)
        if len(slice_df) <= 0:
            self.l_complete = True
            return
        s1 = time.perf_counter()
        o_merge_df = pd.merge(slice_df, self.l_o_df, on=['縣市代號', '段小段', '地建號', '事務所代號'], how='left')
        o_merge_df = pd.merge(o_merge_df, self.p_df, on=['縣市代號', '統一編號', '事務所代號'], how='left')
        o_merge_df = pd.merge(o_merge_df, self.l_l_vp, on=['縣市代號', '事務所代號', '登記次序', '段小段', '地建號'], how='left')

        r_merge_df = pd.merge(slice_df, self.l_r_df, on=['縣市代號', '段小段', '地建號', '事務所代號'], how='left')
        r_merge_df = pd.merge(r_merge_df, self.p_df, on=['縣市代號', '統一編號', '事務所代號'], how='left')

        o_group_df = o_merge_df.groupby(['段小段', '地建號', '鄉鎮市區', '縣市代號'])
        r_group_df = r_merge_df.groupby(['段小段', '地建號', '鄉鎮市區', '縣市代號'])

        new_df['土地標示部'] = slice_df.apply(self.get_lb_mark_dict, axis=1, args=('l',))
        new_df['土地所有權部'] = slice_df.apply(self.get_or_dict, axis=1, args=(o_group_df, 'o', 'l',))
        new_df['土地他項權利部'] = slice_df.apply(self.get_or_dict, axis=1, args=(r_group_df, 'r', 'l',))
        new_df['土地所有權人列表'] = slice_df.apply(self.get_or_list_dict, axis=1, args=(o_group_df, 'o', 'l',))
        new_df['土地他項權利人列表'] = slice_df.apply(self.get_or_list_dict, axis=1, args=(r_group_df, 'r', 'l',))
        datas = new_df.to_dict(orient='records')
        feed_back_tp(data=datas, lbtype='L')


        self.l_step += MAX_STEP
        self.l_schedule.integer = self.l_step
        self.l_schedule.save()

    def bulid_handle(self):
        new_df = pd.DataFrame([])
        slice_df = self.b_m_df[self.b_step:self.b_step+MAX_STEP].reset_index(drop=True)
        if len(slice_df) <= 0:
            self.b_complete = True
            return

        o_merge_df = pd.merge(slice_df, self.b_o_df, on=['縣市代號', '段小段', '地建號', '事務所代號'], how='left')
        o_merge_df = pd.merge(o_merge_df, self.p_df, on=['縣市代號', '統一編號', '事務所代號'], how='left')
        o_group_df = o_merge_df.groupby(['段小段', '地建號', '鄉鎮市區', '縣市代號'])

        r_merge_df = pd.merge(slice_df, self.b_r_df, on=['縣市代號', '段小段', '地建號', '事務所代號'], how='left')
        r_merge_df = pd.merge(r_merge_df, self.p_df, on=['縣市代號', '統一編號', '事務所代號'], how='left')
        r_group_df = r_merge_df.groupby(['段小段', '地建號', '鄉鎮市區', '縣市代號'])

        new_df['建物標示部'] = slice_df.apply(self.get_lb_mark_dict, axis=1, args=('b',))
        new_df['建物所有權部'] = slice_df.apply(self.get_or_dict, axis=1, args=(o_group_df, 'o', 'b',))
        new_df['建物他項權利部'] = slice_df.apply(self.get_or_dict, axis=1, args=(r_group_df, 'r', 'b',))
        new_df['建物所有權人列表'] = slice_df.apply(self.get_or_list_dict, axis=1, args=(o_group_df, 'o', 'b',))
        new_df['建物他項權利人列表'] = slice_df.apply(self.get_or_list_dict, axis=1, args=(r_group_df, 'r', 'b',))
        datas = new_df.to_dict(orient='records')
        # print(datas[0:3])
        feed_back_tp(data=datas, lbtype='B')
        

        self.b_step += MAX_STEP
        self.b_schedule.integer = self.b_step
        self.b_schedule.save()

def job(city):
    data_update_obj = DataUpdate(city)
    print('資料預載完成')
    data_update_obj.handle()

class Command(BaseCommand):
    """
    從104更新資料
    """
    help = '從104更新資料'

    def add_arguments(self, parser):

        parser.add_argument(
            '-c',
            '--city',
            action='store',
            dest='city',
            default='',
            help=''' input data '''
        )


    def handle(self, *args, **options):
        # 取得資料夾內的縣市清單
        mypath = "政府"
        files = os.listdir(mypath)
        key_list = []
        city = options['city']
        if city:
            key_list.append((city, ))
        else:
            for city in files:
                # (file, 其他參數)
                key_list.append((city, ))
                
        # data_update_obj = DataUpdate('A')
        # data_update_obj.handle()
        # print(key_list)
        pool = Pool(processes=8)
        results = pool.starmap(job, key_list)

#