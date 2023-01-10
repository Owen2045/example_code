import imp
import json
import logging
import re
import time
import traceback
from datetime import date, datetime, timedelta
from multiprocessing import Pool, cpu_count

import pandas as pd
import pytz
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from numpy import insert

import building.models
import land.models
from building.building_serializers import (BuildingSerializerAttach,
                                           BuildingSerializerCommon,
                                           BuildingSerializerFloor,
                                           BuildingSerializerMain,
                                           BuildingSerializerMark,
                                           BuildingSerializerOwner,
                                           BuildingSerializerRight)
from building.building_serializers import TpLogSerializer as tp_serializer_B
from common.enums import (LBEnum, RestrictionTypeEnum, TaskTypeEnum,
                          TpMenuTypeEnum)
from common.models import RegionCodeTable
from common.util import (address_re, all_to_half, batch, get_dba, half_to_all,
                         time_proV2)
from common.views import FeedbackLborSerializer
from extra_building.management.commands import dismantle_door
from land.land_serializers import (LandSerializerMark, LandSerializerMarkVP,
                                   LandSerializerOwner, LandSerializerRight)
from land.land_serializers import TpLogSerializer as tp_serializer_L

logger = logging.getLogger(__name__)
tz = pytz.timezone(settings.TIME_ZONE)

MAX_TRY_NUM = 5
MAX_JOB_COUNT = 10
def job(regno_logs, LB_enum):
    # create_lbor(regno_logs, LB_enum)
    logger.info('類別:{}, 縣市:{}, 處理數:{}, 進度:{}'.format(LB_enum, regno_logs[0].lbkey[0], len(regno_logs), regno_logs[0].id))

class Command(BaseCommand):
    """
    從104更新資料
    """
    help = '從104更新資料'

    def add_arguments(self, parser):

        parser.add_argument(
            '-t',
            '--lbtype',
            action='store',
            dest='lbtype',
            default='L',
            help=''' input data '''
        )

        parser.add_argument(
                '-b',
                '--batch',
                dest='batch',
                default=100,
                type=int,
                help=''' input batch size '''
            )

        parser.add_argument(
                '-n',
                '--num',
                dest='num',
                default=500,
                type=int,
                help=''' get max task num '''
            )

        parser.add_argument(
                '-rp',
                '--re_parser',
                dest='re_parser',
                default=False,
                type=bool,
                help=''' re parser '''
            )

        parser.add_argument(
                '-i',
                '--id_list',
                dest='id_list',
                nargs='+',
                default='',
                type=str,
                help=''' get designation id '''
            )

    def check_lbor(self, qs_data, query_system, rules, is_fast=False):
        final_msg = '' # 執行結果訊息
        new_list = [] # 寫入lbor清單
        # non_list = [] # 未取得summary 但段小段有效清單
        reg_N2C = {} # 拆分段小段資訊

        lbkey_list = [x.get('lbkey') for x in qs_data]
        exis_qs = self.model_set.Summary.objects.filter(lbkey__in=lbkey_list) # 存在清單
        exis_dict = {}
        exis_list = []
        # if exis_qs:
        for x in exis_qs:
            lbkey = x.lbkey
            exis_list.append(lbkey)
            region_code = f'{x.city_code_table_id.city_code}_{x.area_code_table_id.area_code}_{x.region_code_table_id.region_code}'
            region_name = x.region_code_table_id.region_name
            reg_N2C[region_code] = region_name
            exis_dict[lbkey] = x
        # 檢查段小段合理性
        invalid_list = list(set(lbkey_list) - set(exis_list))
        print(f'無效數量: {len(invalid_list)}')

        for data in qs_data: # 比對到登序
            # 謄本裡的登序
            lbkey = data.get('lbkey')
            ins_o_dict = data.get('owners', {})
            if not ins_o_dict:
                ins_o_dict = {}
            ins_r_dict = data.get('rights', {})
            if not ins_r_dict:
                ins_r_dict = {}
            # 有物件代表summary已經存在
            exis_obj = exis_dict.get(data.get('lbkey'))
            if exis_obj: #　有summary物件
                exis_o_qs = exis_obj.ownerregnosummary_set.all()
                exis_r_qs = exis_obj.rightregnosummary_set.all()
                exis_o_dict = {x.regno: x.name for x in exis_o_qs}
                exis_r_dict = {x.regno: x.name for x in exis_r_qs}
                if set(list(ins_o_dict)) - set(list(exis_o_dict)) == set() and set(list(ins_r_dict)) - set(list(exis_r_dict)) == set():
                    continue
            
            elif lbkey in invalid_list:
                c = f'{lbkey[0]}'
                a = f'{lbkey[2:4]}'
                r = f'{lbkey[5:9]}'
                ans = check_CAR(c, a, r)
                if ans:
                    non_dict = {}
                    non_dict['lbkey'] = lbkey
                    non_dict['owners'] = ins_o_dict
                    non_dict['rights'] = ins_r_dict
                    non_dict['query_time'] = data.get('query_time')
                    non_dict['query_system'] = query_system
                    non_dict['rules'] = rules
                    non_dict['is_fast'] = is_fast
                    new_list.append(non_dict)

            if ins_o_dict or ins_r_dict:
                new_dict = {}
                new_dict['lbkey'] = lbkey
                new_dict['owners'] = ins_o_dict
                new_dict['rights'] = ins_r_dict
                new_dict['query_time'] = data.get('query_time')
                new_dict['query_system'] = query_system
                new_dict['rules'] = rules
                new_dict['is_fast'] = is_fast
                new_list.append(new_dict)

        final_msg = f'lbor須寫入: {len(new_list)}筆'
        if new_list:
            serializer = FeedbackLborSerializer(data=new_list, many=True)
            if serializer.is_valid():
                serializer.save()
                final_msg = f'lbor寫入{len(new_list)}筆完成'
        return final_msg, reg_N2C

    def insert_summary(self, qs):
        # print(qs)
        insert_summary_msg = 'tp_summary 建立失敗'
        tp_dic = {}
        no_car = []
        if not qs:
            insert_summary_msg = 'qs is qmpty 不須建立 summary'
        else:
            inp = []

            for data in qs:
                lbkey = data.get('lbkey')
                pdf_token = data.get('transcript', {}).get('pdf_token')
                zip_token = data.get('transcript', {}).get('zip_token')
                query_time = time_proV2(data.get('query_time'))
                integrity_type = data.get('check_type')
                try:
                    integrity_type = int(integrity_type)
                except:
                    integrity_type = 0
                try:
                    lbkey_obj = self.model_set.Summary.objects.get(lbkey=lbkey)
                except:
                    lbkey_obj = None

                if not lbkey_obj:
                    # 無總表 不建立tp_summary
                    # 觸發查詢

                    no_car.append(lbkey)
                else:                    
                    kw = {'query_time':query_time, 'pdf_token':pdf_token, 'zip_token': zip_token, 'summary_id':lbkey_obj, 'integrity_type': integrity_type} # 'integrity_type': integrity_type, 
                    rnt = self.model_set.TranscriptDetailSummary(**kw)
                    inp.append(rnt)
            res = self.model_set.TranscriptDetailSummary.objects.bulk_create(inp)
            insert_summary_msg = f'tp_summary 建立完成: {len(inp)}筆 {datetime.now()}'
            for i in res:
                lbkey_token = f'{i.summary_id.lbkey}_{i.query_time}'
                tp_dic[lbkey_token] = i
        return tp_dic, insert_summary_msg, no_car

# ==土地========================================================================
    def land_mark_vp(self, vp_data, mark_obj):
        vp_msg = ''
        if vp_data:
            vp_data['mark_detail_id'] = mark_obj

            serializer = LandSerializerMarkVP(data=vp_data)
            if serializer.is_valid():
                land.models.MarkNotice.objects.create(**vp_data)
                vp_msg = 'ok'
            else:
                vp_msg = serializer.errors
        return vp_msg

    def dismantling_mark_land(self, data):
        mark_dict = {}
        mark_msg = ''
        markVP_msg = ''
        mark_fmsg = {}
        lbkey = data.get('lbkey')
        reg_code = lbkey.rsplit('_', 1)[0]
        query_time = time_proV2(data.get('query_time'))
        transcript = data.get('transcript')
        transcript_mark = str_cover_dict(transcript.get('transcript_info')).get('土地標示部')
        usezone_data = self.usezone.get(lbkey, {})
        if isinstance(transcript_mark, dict):
            mark_dict['lbkey'] = lbkey
            mark_dict['reg_date'] = format_reg_date(str_cover_dict(transcript_mark.get('登記日期', {})).get('@P1'))
            mark_dict['reg_date_original'] = str_cover_dict(transcript_mark.get('登記日期', {})).get('#text')
            mark_dict['reg_reason'] = transcript_mark.get('登記原因')
            mark_dict['total_area'] = str2num(str_cover_dict(transcript_mark.get('面積', {})).get('@P1'), typ='f')
            mark_dict['is_valid'] = True
            mark_dict['query_time'] = query_time
            mark_dict['land_purpose'] = transcript_mark.get('地目')
            mark_dict['land_level'] = transcript_mark.get('等則')
            mark_dict['using_zone'] = usezone_data.get('land_zone')
            mark_dict['urban_name'] = usezone_data.get('urban_name')  
            mark_dict[self.dict_key] = locate_lbkey(str_cover_dict(transcript_mark.get(self.lb_key, {})).get('資料'), self.lbtype, self.reg_N2C, reg_code)
            parting, resurvey, merge, add = other_remark_land(str_cover_dict(transcript_mark.get('其他登記事項', {})).get('資料'))
            if parting:
                mark_dict['parting'] = parting
            if resurvey:
                mark_dict['resurvey'] = resurvey
            if merge:
                mark_dict['merge'] = merge
            if add:
                mark_dict['add'] = add
            other_remark_dict = str_cover_dict(transcript_mark.get('其他登記事項', {})).get('資料')
            mark_dict['other_remark_str'] = other_remark_dict
            if self.rp == False:
                mark_dict['tp_summary_id'] = self.tp_dic.get(f'{lbkey}_{query_time}')

            notice_value = str_cover_dict(transcript_mark.get('公告現值', {})).get('@P2')
            notice_price = str_cover_dict(transcript_mark.get('公告地價', {})).get('@P2')

            serializer = LandSerializerMark(data=mark_dict)
            if serializer.is_valid():
                if self.rp == True:
                    # 重新解析用 目前廢棄
                    return mark_dict
                else:
                    vp_data = {'lbkey': lbkey, 'land_notice_value': notice_value, 'land_notice_price': notice_price, 'query_time': query_time}
                    mark_obj = self.model_set.MarkDetail.objects.create(**mark_dict)

                    mark_msg = 'ok'
                    if mark_obj:           
                        markVP_msg = self.land_mark_vp(vp_data, mark_obj)
                        try:
                            model_summary = self.model_set.Summary.objects.get(lbkey=mark_obj.lbkey)
                            if not model_summary.last_mark_update_time:
                                # 沒有查詢時間 直接寫入
                                model_summary.last_mark_detail_id = mark_obj
                                model_summary.last_mark_update_time = mark_obj.query_time
                            elif not mark_obj.query_time:
                                # 沒有查詢時間 判斷解析標示部失敗
                                pass
                            elif model_summary.last_mark_update_time <= mark_obj.query_time:
                                model_summary.last_mark_detail_id = mark_obj
                                model_summary.last_mark_update_time = mark_obj.query_time
                            model_summary.save()
                        except Exception as e:
                            pass                        
                            # print(e)

            else:
                mark_msg = serializer.errors
                logger.info(f'{mark_msg}')
            mark_fmsg = {'mark': mark_msg, 'markVP': markVP_msg}
        return mark_fmsg

    def dismantling_owners(self, data):
        owners_entry = [] if self.rp == False else {}
        total_owens_msg = {}
        lbkey = data.get('lbkey')
        query_time = time_proV2(data.get('query_time'))
        transcript = data.get('transcript')
        transcript_owners = str_cover_dict(transcript.get('transcript_info')).get(self.o_part)

        if transcript_owners:
            for owner in transcript_owners:
                owner_dict = {}    
                owner_dict['lbkey'] = lbkey
                try:
                    regno = (owner.get('登記次序', '') if owner.get('登記次序', '') else '').replace('-', '')
                except:
                    continue

                if regno in ['', None]:
                    continue
                owner_dict['regno'] = regno
                owner_dict['reg_date'] = format_reg_date(str_cover_dict(owner.get('登記日期', {})).get('@P1'))
                owner_dict['reg_date_original'] = str_cover_dict(owner.get('登記日期', {})).get('#text')

                owner_dict['reg_reason'] = owner.get('登記原因')
                owner_dict['reason_date'] = format_reg_date(str_cover_dict(owner.get('原因發生日期', {})).get('@P1'))
                owner_dict['name'] = owner.get('所有權人')
                owner_dict['admin'] = str_cover_dict(owner.get('管理者', {})).get('資料')
                uid = owner.get('統一編號')
                if uid:
                    if len(uid) > 10:
                        uid = None
                owner_dict['uid'] = uid

                address = owner.get('住址')
                owner_dict['address'] = address
                do_address_re = address_re(address)
                if do_address_re:
                    owner_dict['address_re'] = do_address_re
                else:
                    owner_dict['address_re'] = address

                owner_dict['right_numerator'] = str2num(str_cover_dict(owner.get('權利範圍', {})).get('@P2'), typ='i')
                owner_dict['right_denominator'] = str2num(str_cover_dict(owner.get('權利範圍', {})).get('@P1'), typ='i')
                owner_dict['right_str'] = str_cover_dict(owner.get('權利範圍', {})).get('#text')
                owner_dict['cert_id'] = owner.get('權狀字號')
                owner_dict['related_creditor_regno'] = clean_regno(str_cover_dict(owner.get('相關他項權利登記次序', {})).get('資料'), typ='c')
                owner_dict['related_creditor_num'] = str2num(str_cover_dict(owner.get('相關他項權利登記次序', {})).get('@資料筆數'), typ='i')
                owner_dict['query_time'] = query_time
                owner_dict['query_time_str'] = str_cover_dict(owner.get('查詢日期', {})).get('#text')
                if self.lbtype == 'L':
                    owner_dict['declare_value'] = str2num(str_cover_dict(owner.get('申報地價', {})).get('@P2'), typ='i')
                    owner_dict['declare_value_date'] = format_reg_date(str_cover_dict(owner.get('申報地價', {})).get('@P1'))
                    owner_dict['declare_value_date_original'] = str_cover_dict(owner.get('申報地價', {})).get('#text')
                    owner_dict['old_value'] = owner.get('前次移轉現值或原規定地價')
                    owner_dict['land_value_remark'] = owner.get('地價備註事項')

                other_remark_dict = str_cover_dict(owner.get('其他登記事項', {})).get('資料')
                owner_dict['other_remark_str'] = other_remark_dict
                restricted_type, restricted_str = restricted_type_new(owner.get('其他登記事項'))
                owner_dict['restricted_type'] = restricted_type
                owner_dict['restricted_reason'] = restricted_str
                if self.rp == False:
                    owner_dict['tp_summary_id'] = self.tp_dic.get(f'{lbkey}_{query_time}')
                # print(owner_dict)
                serializer = self.tp_serializer_owner(data=owner_dict)

                if serializer.is_valid():
                    if self.rp == False:
                        owners_entry.append(self.model_set.OwnerTpDetail(**owner_dict))
                    else:
                        owners_entry.update({regno: owner_dict})
                    total_owens_msg[regno] = 'ok'
                else:
                    print(serializer.errors)
                    total_owens_msg[regno] = serializer.errors
                    # logger.info(f'{regno} : {total_owens_msg}')

        return owners_entry, total_owens_msg

    def dismantling_rights(self, data):
        rights_entry = [] if self.rp == False else {}
        total_rights_msg = {}
        lbkey = data.get('lbkey')
        query_time = time_proV2(data.get('query_time'))
        transcript = data.get('transcript')
        transcript_rights = str_cover_dict(transcript.get('transcript_info')).get(self.r_part)

        if transcript_rights:
            for rights in transcript_rights:
                right_dict = {}
                right_dict['lbkey'] = lbkey
                try:
                    regno = (rights.get('登記次序', '') if rights.get('登記次序', '') else '').replace('-', '')
                except:
                    continue
                if regno in ['', None]:
                    continue
                right_dict['regno'] = (rights.get('登記次序', '') if rights.get('登記次序', '') else '').replace('-', '')
                right_dict['right_type'] = rights.get('權利種類')
                right_dict['setting_doc_id'] = rights.get('收件年期字號')
                right_dict['reg_date'] = format_reg_date(str_cover_dict(rights.get('登記日期', {})).get('@P1'))
                right_dict['reg_date_original'] = str_cover_dict(rights.get('登記日期', {})).get('#text')
                right_dict['reg_reason'] = rights.get('登記原因')
                right_dict['name'] = rights.get('權利人')
                right_dict['admin'] = str_cover_dict(rights.get('管理者', {})).get('資料')
                uid = rights.get('統一編號')
                if uid:
                    if len(uid) > 10:
                        uid = None
                right_dict['uid'] = uid

                address = rights.get('住址')
                right_dict['address'] = address
                do_address_re = address_re(address)
                if do_address_re:
                    right_dict['address_re'] = do_address_re
                else:
                    right_dict['address_re'] = address
                right_dict['right_numerator'] = str2num(str_cover_dict(rights.get('權利範圍', {})).get('@P2'), typ='i')
                right_dict['right_denominator'] = str2num(str_cover_dict(rights.get('權利範圍', {})).get('@P1'), typ='i')
                right_dict['right_str'] = str_cover_dict(rights.get('權利範圍', {})).get('#text')

                # 債權額比例
                right_dict['obligation_numerator'] = str2num(str_cover_dict(rights.get('債權額比例', {})).get('@P2'), typ='i')
                right_dict['obligation_denominator'] = str2num(str_cover_dict(rights.get('債權額比例', {})).get('@P1'), typ='i')
                right_dict['obligation_str'] = str_cover_dict(rights.get('債權額比例', {})).get('#text')

                # 擔保債權總金額
                right_dict['guarantee_amount'] = str2num(str_cover_dict(rights.get('擔保債權總金額', {})).get('@P1'), typ='i')
                right_dict['guarantee_amount_str'] = str_cover_dict(rights.get('擔保債權總金額', {})).get('#text')
                right_dict['guarantee_type_range'] = rights.get('擔保債權種類及範圍')
                right_dict['guarantee_date'] = format_reg_date(str_cover_dict(rights.get('擔保債權確定期日', {})).get('@P1'))

                gds = str_cover_dict(rights.get('擔保債權確定期日', {})).get('#text')
                if gds:
                    if len(gds) > 255:
                        gds = None
                right_dict['guarantee_date_str'] = gds

                # 存續期間
                right_dict['duration_start_date'] = format_reg_date(str_cover_dict(rights.get('存續期間', {})).get('@P1'))          
                right_dict['duration_end_date'] = format_reg_date(str_cover_dict(rights.get('存續期間', {})).get('@P2'))
                right_dict['duration_str'] = str_cover_dict(rights.get('存續期間', {})).get('#text')

                # 清償日期
                right_dict['payoff_date'] = format_reg_date(all_to_half(str_cover_dict(rights.get('清償日期', {})).get('@P1')))
                right_dict['payoff_date_str'] = str_cover_dict(rights.get('清償日期', {})).get('#text')

                # 遲延利息.率
                right_dict['interest'] = rights.get('利息.率')
                right_dict['overdue_interest'] = rights.get('遲延利息.率')
                right_dict['penalty'] = rights.get('違約金')
                right_dict['other_guarantee'] = rights.get('其他擔保範圍約定')
                right_dict['obligee_ratio'] = rights.get('債務人及債務額比例')
                right_dict['right_target'] = rights.get('權利標的')
                right_dict['related_owner_regno'] = clean_regno(str_cover_dict(rights.get('標的登記次序', {})).get('資料'), typ='o')
                right_dict['related_owner_num'] = str2num(str_cover_dict(rights.get('標的登記次序', {})).get('@資料筆數'), typ='i')
                
                # 設定權利範圍分子
                right_dict['setting_right_numerator'] = str2num(str_cover_dict(rights.get('設定權利範圍')).get('@P2'), typ='i')
                right_dict['setting_right_denominator'] = str2num(str_cover_dict(rights.get('設定權利範圍')).get('@P1'), typ='i')

                srs = str_cover_dict(rights.get('設定權利範圍')).get('#text')
                if srs:
                    if len(srs) > 255:
                        srs = None
                right_dict['setting_right_str'] = srs
                right_dict['right_cert_doc_id'] = rights.get('證明書字號')
                right_dict['setting_obligee'] = str_cover_dict(rights.get('extra', {})).get('義務人')

                # 共同擔保地建號
                c_lk, c_bk = collateral_lbkey(str_cover_dict(rights.get('共同擔保地建號', {})).get('資料'))
                if c_lk:
                    right_dict['collateral_lkey'] = c_lk
                if c_bk:
                    right_dict['collateral_bkey'] = c_bk

                right_dict['setting_creditor_right_type'] = str_cover_dict(rights.get('extra', {})).get('設定他項權利')
                right_dict['setting_creditor_right_regno'] = str_cover_dict(rights.get('extra', {})).get('設定他項權利登記次序')
                other_remark_dict = str_cover_dict(rights.get('其他登記事項', {})).get('資料')
                right_dict['other_remark_str'] = other_remark_dict
                right_dict['mortgage_overdue'] = rights.get('流抵約定')

                right_dict['query_time'] = query_time
                right_dict['query_time_str'] = str_cover_dict(rights.get('查詢日期', {})).get('#text')
                right_dict['extra'] = rights.get('extra')

                restricted_type, restricted_str = restricted_type_new(rights.get('其他登記事項'))
                right_dict['restricted_type'] = restricted_type
                right_dict['restricted_reason'] = restricted_str
                if self.rp == False:
                    right_dict['tp_summary_id'] = self.tp_dic.get(f'{lbkey}_{query_time}')

                serializer = self.tp_serializer_right(data=right_dict)
                if serializer.is_valid():
                    if self.rp == False:
                        rights_entry.append(self.model_set.RightTpDetail(**right_dict))
                    else:
                        rights_entry.update({regno: right_dict})
                    total_rights_msg[regno] = 'ok'
                else:
                    total_rights_msg[regno] = serializer.errors
                    # logger.info(f'{regno} : {total_rights_msg}')
        return rights_entry, total_rights_msg

# ==建物========================================================================

    def building_mark_data(self, qs, mark_obj):
        mark_msg = {}
        msg_main = ''
        msg_common = ''
        msg_attach = ''
        msg_floor = ''
        lbkey = qs.get('lbkey')
        transcript = qs.get('transcript')
        # query_time = time_proV2(qs.get('query_time'), plus_8=True)
        transcript_mark = str_cover_dict(transcript.get('transcript_info')).get('建物標示部')
        if isinstance(transcript_mark, dict):
            # lk = f'{lbkey}_{query_time}'
            common_part = str_cover_dict(transcript_mark.get('共有部分')).get('資料')
            main_part = str_cover_dict(transcript_mark.get('主建物資料')).get('資料')
            attach_part = str_cover_dict(transcript_mark.get('附屬建物')).get('資料')
            floor_part = str_cover_dict(transcript_mark.get('建物分層')).get('資料')

            com = 0
            if common_part and main_part:
                door = all_to_half(transcript_mark.get('建物門牌'))
                for trash in [',', ';', '共有']:
                    if door.find(trash) != -1:
                        com = 1
                        break
                if com == 1 and not floor_part:
                    # print('判斷為公設')
                    msg_main = do_main_part(main_part, mark_obj, lbkey, rp=self.rp)
                elif com == 0 and floor_part:
                    # print('判斷為主建')
                    msg_common = do_common_part(common_part, mark_obj, lbkey, rp=self.rp)
                else:
                    # print('啥都不是的垃圾')
                    msg_common = do_common_part(common_part, mark_obj, lbkey, rp=self.rp)
            
            # 處理共有+主建
            elif common_part and not main_part:                      
                msg_common = do_common_part(common_part, mark_obj, lbkey, rp=self.rp)
            elif not common_part and main_part:
                msg_main = do_main_part(main_part, mark_obj, lbkey, rp=self.rp)

            msg_attach = do_attach_part(attach_part, mark_obj, lbkey, rp=self.rp)
            msg_floor = do_floor_part(floor_part, mark_obj, lbkey, rp=self.rp)
        mark_msg = {'main': msg_main, 'common': msg_common, 'attach': msg_attach, 'floor': msg_floor}
        return mark_msg

    def dismantling_mark_building(self, data):
        mark_dict = {}
        mark_fmsg = {}
        mark_msg = ''
        markAT_msg = {}
        lbkey = data.get('lbkey')
        reg_code = lbkey.rsplit('_', 1)[0]
        query_time = time_proV2(data.get('query_time'))
        # query_time = data.get('query_time')
        transcript = data.get('transcript')
        transcript_mark = str_cover_dict(transcript.get('transcript_info')).get('建物標示部')
        if isinstance(transcript_mark, dict):
            mark_dict['lbkey'] = lbkey
            mark_dict['reg_date'] = format_reg_date(str_cover_dict(transcript_mark.get('登記日期', {})).get('@P1'))
            mark_dict['reg_date_original'] = str_cover_dict(transcript_mark.get('登記日期', {})).get('#text')
            mark_dict['reg_reason'] = transcript_mark.get('登記原因')
            mark_dict['total_area'] = str2num(str_cover_dict(transcript_mark.get('總面積', {})).get('@P1'), typ='f')
            try:
                mark_dict['door_number'] = transcript_mark.get('建物門牌', '').replace(' ', '').replace('　', '')
            except:
                mark_dict['door_number'] = None

            other_remark = transcript_mark.get('其他登記事項')
            main_purpose_t = transcript_mark.get('主要用途')
            material_t = transcript_mark.get('主要建材')
            main_purpose_o, material_o, use_license_no = other_remark_building(other_remark)
            if main_purpose_t == '見其他登記事項' and main_purpose_o != None:
                main_purpose = main_purpose_o
            else:
                main_purpose = main_purpose_t

            if material_t == '見其他登記事項' and material_o != None:
                material = material_o
            else:
                material = material_t
            mark_dict['main_purpose'] = main_purpose
            mark_dict['material'] = material
            mark_dict['use_license_no'] = use_license_no
            mark_dict['floor_num'] = str2num(str_cover_dict(transcript_mark.get('層數', {})).get('@P1'), typ='i')
            mark_dict['floor_num_str'] = str_cover_dict(transcript_mark.get('層數', {})).get('#text')
            mark_dict['build_date'] = format_reg_date(str_cover_dict(transcript_mark.get('建築完成日期', {})).get('@P1'))
            mark_dict['build_date_str'] = str_cover_dict(transcript_mark.get('建築完成日期', {})).get('#text')
            mark_dict[self.dict_key] = locate_lbkey(str_cover_dict(transcript_mark.get(self.lb_key, {})).get('資料'), self.lbtype, self.reg_N2C, reg_code)
            other_remark_dict = str_cover_dict(transcript_mark.get('其他登記事項', {})).get('資料')
            mark_dict['other_remark_str'] = other_remark_dict
            mark_dict['is_valid'] = True
            mark_dict['query_time'] = query_time
            if self.rp == False:
                mark_dict['tp_summary_id'] = self.tp_dic.get(f'{lbkey}_{query_time}')

            serializer = BuildingSerializerMark(data=mark_dict)
            if serializer.is_valid():
                if self.rp == True:
                    return mark_dict
                else:
                    mark_obj = self.model_set.MarkDetail.objects.create(**mark_dict)
                    mark_msg = 'ok'
                    if mark_obj:
                        markAT_msg = self.building_mark_data(data, mark_obj)
                        try:
                            model_summary = self.model_set.Summary.objects.get(lbkey=mark_obj.lbkey)
                            if not model_summary.last_mark_update_time:
                                # 沒有查詢時間 直接寫入
                                model_summary.last_mark_detail_id = mark_obj
                                model_summary.last_mark_update_time = mark_obj.query_time
                            elif not mark_obj.query_time:
                                # 沒有查詢時間 判斷解析標示部失敗
                                pass
                            elif model_summary.last_mark_update_time <= mark_obj.query_time:
                                model_summary.last_mark_detail_id = mark_obj
                                model_summary.last_mark_update_time = mark_obj.query_time
                            model_summary.save()
                        except Exception as e:    
                            pass            
                            # print(e)
            else:
                mark_msg = serializer.errors
                logger.info(f'{mark_msg}')
            mark_fmsg = {'mark': mark_msg, 'mark_att': markAT_msg}
            return mark_fmsg

    def get_all_reg_list(self, data_list):
        result = []
        if isinstance(data_list, list) == True:
            for i in data_list:
                regno = i.get('登記次序')
                result.append(regno)
        return result

    def get_extra(self, extra):
        o_reg_list = []
        r_reg_list = []
        mark_only = None
        if isinstance(extra, dict):
            try:
                owner_list = self.get_all_reg_list(extra.get('transcript_info', {}).get(self.o_part, []))  #.get('所有權人', {}).get('資料', [])
                right_list = self.get_all_reg_list(extra.get('transcript_info', {}).get(self.r_part, []))  #.get('他項權利人', {}).get('資料', [])
                mark_only = extra.get('transcript_info', {}).get('mark_only', False)
                
            except Exception as e:
                owner_list = []
                right_list = []
                mark_only = None

        if owner_list:
            for i in owner_list:
                if isinstance(i, str) == True:
                    i = i.replace('-', '').replace('_', '')
                    reg = re.findall(r'\d{4,4}', i)
                    o_reg_list.extend(reg)

        if right_list:
            for i in right_list:
                if isinstance(i, str) == True:
                    i = i.replace('-', '').replace('_', '')
                    reg = re.findall(r'\d{7,7}', i)
                    r_reg_list.extend(reg)

        return o_reg_list, r_reg_list, mark_only

    def check_rules(self, data):
        try:
            o_lbor = [x for x, y in data['owners'].items()]
        except:
            o_lbor = []
        try:
            c_lbor = [x for x, y in data['rights'].items()]
        except:
            c_lbor = []

        tp_list_o, tp_list_c, mark_only = self.get_extra(data['transcript'])

        check_str = ''
        if not tp_list_o and not tp_list_c:
            check_str += 'N'
        else:
            if set(o_lbor) == set(tp_list_o):
                check_str += 'o'
            if set(c_lbor) == set(tp_list_c):
                check_str += 'c'

        if mark_only == True:
            return TpMenuTypeEnum.MARK_ONLY
        elif check_str == 'N':
            return TpMenuTypeEnum.UNKNOW
        elif check_str == 'oc':
            return TpMenuTypeEnum.FULL
        else:
            return TpMenuTypeEnum.SPECIFY

    def splitint_task(self, query_set):
        ft = []
        if query_set:
            for i in query_set:
                td = {'lbkey': i.lbkey, 'owners': i.owners, 'rights': i.rights, 'create_time': i.create_time, 'transcript': i.transcript, 'query_time': i.query_time}
                ft.append(td)
            df_only = pd.DataFrame(ft, dtype=object)
            # df_only = df.drop_duplicates(subset=['lbkey'], keep='last').reset_index(drop=True)
            df_only['check_type'] = df_only.apply(self.check_rules, axis=1)
            ft = df_only.to_dict(orient='records')
        return ft

# ==重新解析========================================================================
# ---土地-------------------------------------------------------------
    def do_re_update_right(self, qs, reparser):
        res_msg = {}
        if qs:
            for i in qs:
                try:
                    full_data = reparser.get(i.regno, {})
                    # print(full_data)
                    i.right_type = full_data.get('right_type')
                    i.setting_doc_id = full_data.get('setting_doc_id')
                    i.reg_date = full_data.get('reg_date')
                    i.reg_date_original = full_data.get('reg_date_original')
                    i.reg_reason = full_data.get('reg_reason')
                    i.name = full_data.get('name')
                    i.uid = full_data.get('uid')
                    i.address = full_data.get('address')
                    i.address_re = full_data.get('address_re')
                    i.admin = full_data.get('admin')

                    i.right_numerator = full_data.get('right_numerator')
                    i.right_denominator = full_data.get('right_denominator')
                    i.right_str = full_data.get('right_str')

                    i.obligation_numerator = full_data.get('obligation_numerator')
                    i.obligation_denominator = full_data.get('obligation_denominator')
                    i.obligation_str = full_data.get('obligation_str')

                    i.guarantee_amount = full_data.get('guarantee_amount')
                    i.guarantee_amount_str = full_data.get('guarantee_amount_str')
                    i.guarantee_type_range = full_data.get('guarantee_type_range')
                    i.guarantee_date = full_data.get('guarantee_date')
                    i.guarantee_date_str = full_data.get('guarantee_date_str')

                    i.duration_start_date = full_data.get('duration_start_date')
                    i.duration_end_date = full_data.get('duration_end_date')
                    i.duration_str = full_data.get('duration_str')

                    i.payoff_date = full_data.get('payoff_date')
                    i.payoff_date_str = full_data.get('payoff_date_str')
                    i.interest = full_data.get('interest')
                    i.overdue_interest = full_data.get('overdue_interest')
                    i.penalty = full_data.get('penalty')
                    i.other_guarantee = full_data.get('other_guarantee')
                    i.obligee_ratio = full_data.get('obligee_ratio')
                    i.right_target = full_data.get('right_target')
                    i.related_owner_regno = full_data.get('related_owner_regno')
                    i.related_owner_num = full_data.get('related_owner_num')

                    i.setting_right_numerator = full_data.get('setting_right_numerator')
                    i.setting_right_denominator = full_data.get('setting_right_denominator')
                    i.setting_right_str = full_data.get('setting_right_str')

                    i.right_cert_doc_id = full_data.get('right_cert_doc_id')
                    i.setting_obligee = full_data.get('setting_obligee')
                    i.collateral_lkey = full_data.get('collateral_lkey')
                    i.collateral_bkey = full_data.get('collateral_bkey')
                    i.setting_creditor_right_type = full_data.get('setting_creditor_right_type')
                    i.setting_creditor_right_regno = full_data.get('setting_creditor_right_regno')
                    i.mortgage_overdue = full_data.get('mortgage_overdue')
                    # i.query_time = full_data.get('query_time')
                    # i.query_time_str = full_data.get('query_time_str')
                    i.transcript = full_data.get('transcript')
                    i.other_remark_str = full_data.get('other_remark_str')
                    i.restricted_type = full_data.get('restricted_type')
                    i.restricted_reason = full_data.get('restricted_reason')
                    i.save()
                    res_msg[i.regno] = 'ok'
                except Exception as e:
                    res_msg[i.regno] = f'reparser: {e}'
        return res_msg

    def do_re_update_owner(self, qs, reparser):
        res_msg = {}
        if qs:            
            for i in qs:
                try:
                    full_data = reparser.get(i.regno, {})
                    i.reg_date = full_data.get('reg_date')
                    i.reg_date_original = full_data.get('reg_date_original')
                    i.reg_reason = full_data.get('reg_reason')
                    i.reason_date = full_data.get('reason_date')
                    i.name = full_data.get('name')
                    i.uid = full_data.get('uid')
                    i.address = full_data.get('address')
                    i.address_re = full_data.get('address_re')
                    i.right_numerator = full_data.get('right_numerator')
                    i.right_denominator = full_data.get('right_denominator')
                    i.right_str = full_data.get('right_str')
                    i.cert_id = full_data.get('cert_id')
                    i.related_creditor_regno = full_data.get('related_creditor_regno')
                    i.related_creditor_num = full_data.get('related_creditor_num')
                    i.query_time = full_data.get('query_time')
                    i.query_time_str = full_data.get('query_time_str')
                    i.transcript = full_data.get('transcript')

                    if self.lbtype == 'L':
                        i.declare_value = full_data.get('declare_value')
                        i.declare_value_date = full_data.get('declare_value_date')
                        i.declare_value_date_original = full_data.get('declare_value_date_original')
                        i.old_value = full_data.get('old_value')
                        i.land_value_remark = full_data.get('land_value_remark')
                    i.other_remark_str = full_data.get('other_remark_str')
                    i.restricted_type = full_data.get('restricted_type')
                    i.save()
                    res_msg[i.regno] = 'ok'
                except Exception as e:
                    res_msg[i.regno] = f'reparser: {e}'
        return res_msg

    def do_re_update_mark_L(self, qs, reparser):
        msg = {'mark': ''}
        try:
            usezone_data = self.usezone.get(qs.lbkey, {})
            qs.reg_date = reparser.get('reg_date')
            qs.reg_date_original = reparser.get('reg_date_original')
            qs.reg_reason = reparser.get('reg_reason')
            qs.total_area = reparser.get('total_area')
            qs.is_valid = reparser.get('is_valid')
            qs.land_purpose = reparser.get('land_purpose')
            qs.land_level = reparser.get('land_level')
            qs.using_zone = usezone_data.get('land_zone')
            qs.urban_name = usezone_data.get('urban_name')
            qs.locate_bkey = reparser.get('locate_bkey')
            qs.other_remark_str = reparser.get('other_remark_str')
            qs.save()
            msg['mark'] = 'ok'
        except Exception as e:
            msg['mark'] = e
        return msg

    def do_update_mark_vp(self, m_qs):
        msg = {'markVP': ''}
        if len(m_qs) > 0:
            i = m_qs[0]      
            v_qs = i.marknotice_set.filter(is_valid=1)
            vp_data = self.vp_list.get(i.lbkey)
            if vp_data == None:
                msg['markVP'] = 'no vp data'
                return msg
            elif len(v_qs) > 0:
                v = v_qs[0]
                try:
                    v.land_notice_value = vp_data.get('land_notice_value')
                    v.land_notice_value_date = vp_data.get('land_notice_value_date')
                    v.land_notice_price = vp_data.get('land_notice_price')
                    v.land_notice_price_date = vp_data.get('land_notice_price_date')
                    v.land_area_size = vp_data.get('land_area_size')
                    v.size_changed = vp_data.get('size_changed')
                    v.save()
                    msg['markVP'] = 'ok'
                except Exception as e:
                    msg['markVP'] = e
        else:
            msg['markVP'] = 'vp: no markobj'
        return msg

# ---建物--------------------------------------------------------------------
    def do_re_update_mark_B(self, m_qs, m_dict):
        msg = {'mark': ''}
        try:
            m_obj = m_qs[0]
            m_obj.reg_date = m_dict.get('reg_date')
            m_obj.reg_date_original = m_dict.get('reg_date_original')
            m_obj.reg_reason = m_dict.get('reg_reason')
            m_obj.total_area = m_dict.get('total_area')
            m_obj.door_number = m_dict.get('door_number')
            m_obj.main_purpose = m_dict.get('main_purpose')
            m_obj.material = m_dict.get('material')
            m_obj.use_license_no = m_dict.get('use_license_no')
            m_obj.floor_num = m_dict.get('floor_num')
            m_obj.floor_num_str = m_dict.get('floor_num_str')
            m_obj.build_date = m_dict.get('build_date')
            m_obj.build_date_str = m_dict.get('build_date_str')
            m_obj.locate_lkey = m_dict.get('locate_lkey')
            m_obj.other_remark_str = m_dict.get('other_remark_str')
            m_obj.query_time = m_dict.get('query_time')
            m_obj.save()
            msg['mark'] = 'ok'
        except Exception as e:
            msg['mark'] = e
        return msg

    def do_re_bdata(self, obj_list, data, dtype):
        if dtype == 'M':
            seri = BuildingSerializerMain
            bdata_model = self.model_set.MainBuilding
            update_fields = ['lbkey', 'right_numerator', 'right_denominator', 'right_str', 'total_area', 'other_remark', 'extra', 'mark_id']
        elif dtype == 'C':
            seri = BuildingSerializerCommon
            bdata_model = self.model_set.CommonPart
            update_fields = ['lbkey', 'right_numerator', 'right_denominator', 'right_str', 'total_area', 'other_remark', 'extra', 'mark_id']
        elif dtype == 'F':
            seri = BuildingSerializerFloor
            bdata_model = self.model_set.BuildingFloor
            update_fields = ['lbkey', 'title', 'area', 'mark_id']
        elif dtype == 'A':
            seri = BuildingSerializerAttach
            bdata_model = self.model_set.BuildingAttach
            update_fields = ['lbkey', 'title', 'area', 'mark_id']

        update_len = len(obj_list)
        input_len = len(data)
        update_list = []
        if update_len > 0:
            for o, d in zip(obj_list[:update_len], data[:update_len]):
                if dtype in ['M', 'C']:
                    o.lbkey = d.get('lbkey')
                    o.right_numerator = d.get('right_numerator')
                    o.right_denominator = d.get('right_denominator')
                    o.right_str = d.get('right_str')
                    o.total_area = d.get('total_area')
                    o.other_remark = d.get('other_remark')
                    o.extra = d.get('extra')
                    o.mark_id = d.get('mark_id')
                    update_list.append(o)
                elif dtype in ['F', 'A']:
                    o.lbkey = d.get('lbkey')
                    o.title = d.get('title')
                    o.area = d.get('area')
                    o.mark_id = d.get('mark_id')
                    update_list.append(o)

        bdata_model.objects.bulk_update(update_list, fields=update_fields)
        insert_list = []
        if input_len - update_len > 0:
            for ins_d in data[update_len:]:          
                insert_list.append(bdata_model(**ins_d))
        elif input_len - update_len < 0:
            bdata_model.objects.filter(id__in=[x.id for x in obj_list[input_len:]]).delete()
        bdata_model.objects.bulk_create(insert_list)


    def do_re_update_MCFA(self, log_dict, mark_obj):
        # 更新主建共有樓層附屬
        mark_msg = {}
        rp_main, rp_common, rp_attach, rp_floor = [], [], [], []
        lbkey = log_dict.get('lbkey')
        transcript = log_dict.get('transcript')
        transcript_mark = str_cover_dict(transcript.get('transcript_info')).get('建物標示部')
        if isinstance(transcript_mark, dict):
            common_part = str_cover_dict(transcript_mark.get('共有部分')).get('資料')            
            main_part = str_cover_dict(transcript_mark.get('主建物資料')).get('資料')
            attach_part = str_cover_dict(transcript_mark.get('附屬建物')).get('資料')
            floor_part = str_cover_dict(transcript_mark.get('建物分層')).get('資料')
            
            com = 0
            if common_part and main_part:
                door = all_to_half(transcript_mark.get('建物門牌'))
                for trash in [',', ';', '共有']:
                    if door.find(trash) != -1:
                        com = 1
                        break
                if com == 1 and not floor_part:
                    # print('判斷為公設')
                    rp_main = do_main_part(main_part, mark_obj, lbkey, rp=self.rp)
                elif com == 0 and floor_part:
                    # print('判斷為主建')
                    rp_common = do_common_part(common_part, mark_obj, lbkey, rp=self.rp)
                else:
                    # print('啥都不是的垃圾')
                    rp_common = do_common_part(common_part, mark_obj, lbkey, rp=self.rp)
            
            # 處理共有+主建
            elif common_part and not main_part:                      
                rp_common = do_common_part(common_part, mark_obj, lbkey, rp=self.rp)
            elif not common_part and main_part:
                rp_main = do_main_part(main_part, mark_obj, lbkey, rp=self.rp)

            rp_floor = do_floor_part(floor_part, mark_obj, lbkey, rp=self.rp)
            rp_attach = do_attach_part(attach_part, mark_obj, lbkey, rp=self.rp)
            # print(rp_attach, rp_floor, rp_main, rp_common)
            exis_M_obj = mark_obj.mainbuilding_set.all()
            exis_C_obj = mark_obj.commonpart_set.all()
            exis_F_obj = mark_obj.buildingfloor_set.all()
            exis_A_obj = mark_obj.buildingattach_set.all()
            # print(exis_M_obj, exis_C_obj, exis_F_obj, exis_A_obj)
            self.do_re_bdata(obj_list=exis_M_obj, data=rp_main, dtype='M')
            self.do_re_bdata(obj_list=exis_C_obj, data=rp_common, dtype='C')
            self.do_re_bdata(obj_list=exis_F_obj, data=rp_floor, dtype='F')
            self.do_re_bdata(obj_list=exis_A_obj, data=rp_attach, dtype='A')


        # mark_msg = {'main': msg_main, 'common': msg_common, 'attach': msg_attach, 'floor': msg_floor}
        return mark_msg


    def do_re_parser(self):
        # result_msg_owner = {}
        # result_msg_right = {}
        # result_msg_mark = {}
        
        if self.id_list and self.lbtype:
            logger.info(f'task type: 重新解析 lbtype: {self.lbtype} id_num: {len(self.id_list)}')
            log_obj_qs = self.model_set.Tplog.objects.filter(id__in=self.id_list)
            self.usezone = get_usezone(self.lbtype, lbkey_list=[x.lbkey for x in log_obj_qs])

            for log_obj in log_obj_qs:
                log_dict = self.tp_s_log(log_obj).data
                if not log_dict.get('tp_summary_id'):
                    logger.info(f'id: {log_obj.id} no tp_summary_id')
                    continue
                # 解析完成的
                owners_dict, o_msg = self.dismantling_owners(log_dict)
                rights_dict, r_msg = self.dismantling_rights(log_dict)
                
                # 當前謄本關連所他登序
                rp_qs_o = log_obj.tp_summary_id.ownertpdetail_set.all()
                rp_qs_r = log_obj.tp_summary_id.righttpdetail_set.all()

                # 更新所他
                o_msg = self.do_re_update_owner(qs=rp_qs_o, reparser=owners_dict)
                r_msg = self.do_re_update_right(qs=rp_qs_r, reparser=rights_dict)

                # 確認解析訊息
                # ans = check_finish(o=o_msg, r=r_msg, m=None)
                # print(ans)

                if self.lbtype == 'L':
                    pass
                    # rp 土地
                    parse_mark_data = self.dismantling_mark_land(log_dict)
                    rp_qs_m = log_obj.tp_summary_id.markdetail_set.all()
                    if len(rp_qs_m):
                        mark_obj = rp_qs_m[0]
                        mark_msg = self.do_re_update_mark_L(mark_obj, parse_mark_data)
                    # m_vp_msg = self.do_update_mark_vp(m_qs=re_parser_log_qs_m)
                    # m_msg.update(m_vp_msg)
                    # l_ans = check_finish(o=None, r=None, m=m_msg)
                else:
                    pass
                    # rp 建物
                    parse_mark_data = self.dismantling_mark_building(log_dict)
                    rp_qs_m = log_obj.tp_summary_id.markdetail_set.all()
                    # 有找到標示部物件才更新
                    if len(rp_qs_m):
                        mark_obj = rp_qs_m[0]
                        mark_msg = self.do_re_update_mark_B(mark_obj, parse_mark_data)
                        MCFA = self.do_re_update_MCFA(log_dict, mark_obj)

# =================================================================================

    def make_obj_dict(self, data):
        res = {}
        if data:
            for i in data:
                j = {i.regno: i}
                if res.get(i.lbkey):
                    res[i.lbkey].update(j)
                else:
                    res[i.lbkey] = j
        return res

    def update_last_ortp(self, create_obj, ortype):
        if ortype == 'o':
            model_summary = self.model_set.OwnerRegnoSummary
        elif ortype == 'r':
            model_summary = self.model_set.RightRegnoSummary

        if create_obj:
            up_dict = self.make_obj_dict(create_obj)

            lbkey_list = list(set([x.lbkey for x in create_obj]))
            summary_qs = model_summary.objects.filter(summary_id__lbkey__in=lbkey_list)
            if summary_qs:
                for i in summary_qs:
                    lbkey = i.summary_id.lbkey
                    regno = i.regno
                    tp_obj = up_dict.get(lbkey, {}).get(regno)
                    if tp_obj:
                        # 有成功解析謄本才做
                        summary_lut = i.last_tp_update_time
                        tp_lqt = tp_obj.query_time

                        # print(f'summary_lut: {summary_lut}  tp_lqt: {tp_lqt}')
                        if not summary_lut:
                            # print('沒有更新時間(第一次寫入)')
                            # 沒有更新時間(第一次寫入)
                            i.last_tp_detail_id = tp_obj
                            i.last_tp_update_time = tp_lqt
                        elif summary_lut and not tp_lqt:
                            # print('log沒有查詢時間')
                            # log沒有查詢時間
                            pass
                        elif summary_lut <= tp_lqt:
                            # print(lbkey, regno)
                            # print(f'{summary_lut}  2.{tp_lqt}')
                            i.last_tp_detail_id = tp_obj
                            i.last_tp_update_time = tp_lqt
                model_summary.objects.bulk_update(summary_qs, fields=['last_tp_detail_id', 'last_tp_update_time'])
                # print(summary_qs)

    def handle(self, *args, **options):
        max_task = options['num']
        batch_size = options['batch']
        self.lbtype = options['lbtype']
        self.rp = options['re_parser']
        self.id_list = options['id_list']

        if self.lbtype == 'L':
            self.model_set = land.models
            self.tp_serializer_owner = LandSerializerOwner
            self.tp_serializer_right = LandSerializerRight
            self.tp_s_log = tp_serializer_L
            self.lb_key = '地上建物建號'
            self.dict_key = 'locate_bkey'
            self.o_part = '土地所有權部'
            self.r_part = '土地他項權利部'
            self.o_list = '土地所有權人列表'
            self.r_list = '土地他項權利人列表'
        else:
            self.model_set = building.models
            self.tp_serializer_owner = BuildingSerializerOwner
            self.tp_serializer_right = BuildingSerializerRight
            self.tp_s_log = tp_serializer_B
            self.lb_key = '建物坐落地號'
            self.dict_key = 'locate_lkey'
            self.o_part = '建物所有權部'
            self.r_part = '建物他項權利部'
            self.o_list = '建物所有權人列表'
            self.r_list = '建物他項權利人列表'

        input_id_list = []
        if self.id_list:
            for i in self.id_list:
                try:
                    input_id_list.append(int(i))
                except:
                    pass
        else:
            print('no id list')
            # exit()
        
        # 連續解析 改 True 且不+1
        except_count = 0
        job_count = 0
        while except_count < MAX_TRY_NUM and job_count < MAX_JOB_COUNT:
            try:
                if input_id_list:
                    except_count += MAX_TRY_NUM
                    logger.info(f'Do fast task')
                    qs_list = self.model_set.Tplog.objects.filter(id__in=input_id_list, state=0)
                else:
                    qs_list = self.model_set.Tplog.objects.filter(state=0)[:max_task]

                logger.info(f'system info : 最大任務數量: {max_task} 批次處理數量: {batch_size} 土建: {self.lbtype} 取得任務數量: {len(qs_list)}')
                now_task = self.splitint_task(qs_list)
                # print([x.lbkey for x in qs_list])
                # exit()

                # TODO 重新解析
                if self.rp == True:
                    pass
                    except_count += MAX_TRY_NUM
                    self.reg_N2C = {}
                    self.do_re_parser()                       

                elif not now_task:
                    logger.info(f'all log done')
                    return

                else:
                    job_count += 1
                    result_msg_owner = {}
                    result_msg_right = {}
                    result_msg_mark = {}
                    all_tp_dic = {}
                    for qs_batch in batch(now_task, n=batch_size):                        
                        lbor_check_msg, self.reg_N2C = self.check_lbor(qs_data=qs_batch, query_system=30, rules=3, is_fast=True)
                        self.tp_dic, insert_summary_msg, no_car = self.insert_summary(qs_batch)
                        lkey_list = [x.get('lbkey') for x in qs_batch]
                        # vp以謄本內容為主，保持當前謄本資料
                        # self.vp_list = get_vp_list(self.lbtype, lbkey_list=lkey_list)
                        self.usezone = get_usezone(self.lbtype, lbkey_list=lkey_list)
                        total_owners_entry = []
                        total_rights_entry = []                        
                        try:
                            for qs in qs_batch:
                                if self.lbtype == 'L':
                                    m_msg = self.dismantling_mark_land(qs)
                                    owners_entry, o_msg = self.dismantling_owners(qs)
                                    rights_entry, r_msg = self.dismantling_rights(qs)
                                else:
                                    m_msg = self.dismantling_mark_building(qs)
                                    owners_entry, o_msg = self.dismantling_owners(qs)
                                    rights_entry, r_msg = self.dismantling_rights(qs)

                                result_msg_mark[qs.get('lbkey')] = m_msg
                                result_msg_owner[qs.get('lbkey')] = o_msg
                                result_msg_right[qs.get('lbkey')] = r_msg

                                total_owners_entry.extend(owners_entry)
                                total_rights_entry.extend(rights_entry)

                            o_create_result = self.model_set.OwnerTpDetail.objects.bulk_create(total_owners_entry)
                            r_create_result = self.model_set.RightTpDetail.objects.bulk_create(total_rights_entry)
                            logger.info(f'lbor info : {lbor_check_msg} summary info: {insert_summary_msg}')

                            self.update_last_ortp(o_create_result, ortype='o')
                            self.update_last_ortp(r_create_result, ortype='r')
                            # 更新tp_summary (全部無報錯才更新)
                            all_tp_dic.update(self.tp_dic)
                        except Exception as e:
                            logger.info(f'batch exception: {e}')
                            # 一個batch寫入失敗就刪除 tp_summary
                            tp_s_id = [x.id for x in list(self.tp_dic.values())]
                            self.model_set.TranscriptDetailSummary.objects.filter(id__in=tp_s_id).delete()
                            logger.info(f'刪除完成 tp_id {tp_s_id}')
                        
                        update_list = []
                        for tp_s in list(self.tp_dic.values()):
                            tp_s.is_finish = True
                            update_list.append(tp_s)
                        self.model_set.TranscriptDetailSummary.objects.bulk_update(update_list, fields=['is_finish'])

                bkey_list = []
                for i in qs_list:
                    #! 更新建物門牌拆解清單
                    if self.lbtype == 'B':
                        bkey_list.append(i.lbkey)

                    if self.rp:
                        i.state = TaskTypeEnum.COMPLETE
                    else:
                        q_t_z = i.query_time.astimezone(tz)
                        tp_summary_obj = all_tp_dic.get(f'{i.lbkey}_{q_t_z}')
                        if not tp_summary_obj:
                            if i.lbkey in no_car:
                                i.state = TaskTypeEnum.ABNORMAL_CAR
                            else:
                                pass
                                # print(i.lbkey)
                            continue

                        i.tp_summary_id = tp_summary_obj
                        i.owner_result_msg = result_msg_owner.get(i.lbkey)
                        i.right_result_msg = result_msg_right.get(i.lbkey)
                        i.mark_result_msg = result_msg_mark.get(i.lbkey)
                        is_finish = check_finish(result_msg_owner.get(i.lbkey), result_msg_right.get(i.lbkey), result_msg_mark.get(i.lbkey))
                        if is_finish == 'ok':
                            i.state = TaskTypeEnum.COMPLETE
                        else:
                            i.state = TaskTypeEnum.ABNORMAL_PARSER
                self.model_set.Tplog.objects.bulk_update(qs_list, ['state', 'tp_summary_id', 'owner_result_msg', 'right_result_msg', 'mark_result_msg'], batch_size=1000)
                                                                    # state
                logger.info(f'log state 變更完成')

                #! 更新建物門牌拆解
                if self.lbtype == 'B' and bkey_list:
                    logger.info(f'開始建物門牌解析，筆數：{len(bkey_list)}')
                    call_command(dismantle_door.Command(), task_type='C', key=json.dumps(bkey_list))
                    logger.info(f'建物門牌解析結束')

                for i in range(10):
                    logger.info(f'停止點...........{i}秒')
                    time.sleep(1)
                job_count += 1

            except Exception as e:
                except_count += 1
                traceback.print_exc()
                logger.info(f'wrong massage: {e} try count = {except_count}')
            # break


def get_usezone(lbtype, lbkey_list):
    if lbtype == 'B':
        return []
    else:
        result = {}
        if lbkey_list:
            if len(lbkey_list) == 1:
                lk_str = f"('{lbkey_list[0]}')"
            else:            
                lk_str = tuple(lbkey_list)

            sql = f"SELECT lkey, land_zone, urban_name \
                    FROM land_data.land_use_zone WHERE lkey in {lk_str}"
            res, col = get_dba(sql_cmd=sql)
            if res:
                for i in res:
                    result[i.get('lkey')] = i
        return result

def get_vp_list(lbtype, lbkey_list):
    if lbtype == 'B':
        return []
    else:
        result = {}
        if lbkey_list:
            if len(lbkey_list) == 1:
                lk_str = f"('{lbkey_list[0]}')"
            else:            
                lk_str = tuple(lbkey_list)

            sql = f"SELECT lkey, query_time, land_notice_value, land_notice_value_date, land_notice_price, land_notice_price_date, land_area_size, is_valid, size_changed \
                    FROM land_data.land_notice_vp_list WHERE lkey in {lk_str}"
            res, col = get_dba(sql_cmd=sql)
            if res:
                for i in res:
                    result[i.get('lkey')] = i
        return result

def check_finish(o, r, m):
    last_msg = 'ok'
    if not o and not r and not m:
        last_msg = 'NG'

    if isinstance(o, dict):
        o_res = list(filter(lambda x: str(x[1]) != "ok" , o.items()))
        if o_res:
            last_msg = 'NG'
    if isinstance(r, dict):
        r_res = list(filter(lambda x: str(x[1]) != "ok" , r.items()))
        if r_res:
            last_msg = 'NG'
    if isinstance(m, dict):
        if m.get('mark', {}) != 'ok':
            last_msg = 'NG'
        if m.get('markVP', None) not in  ['ok', '', None]:
            last_msg = 'NG'
        m_at = m.get('mark_att', {})
        mat_res = list(filter(lambda x: str(x[1]) != "" , m_at.items()))
        if mat_res:
            last_msg = 'NG'

    return last_msg

def do_common_part(data, m_obj, lbkey, rp):
    msg = ''
    rp_use = []
    last = []
    lbkey_ms = lbkey.rsplit('_', 1)[0]
    if isinstance(data, list):
        for i in data:
            if not isinstance(i, dict):
                continue
            com = {}
            bnum = i.get('建號')
            com['lbkey'] = f'{lbkey_ms}_{bnum}'
            com['right_numerator'] = str2num(str_cover_dict(i.get('權利範圍')).get('@P2'), typ='i')
            com['right_denominator'] = str2num(str_cover_dict(i.get('權利範圍')).get('@P1'), typ='i')
            com['right_str'] = str_cover_dict(i.get('權利範圍')).get('#text')
            com['total_area'] = str2num(str_cover_dict(i.get('總面積')).get('@P1'), typ='f')
            com['other_remark'] = i.get('備註')
            com['mark_id'] = m_obj
            serializer = BuildingSerializerCommon(data=com)
            if serializer.is_valid():
                if rp == True:
                    rp_use.append(com)
                else:
                    last.append(building.models.CommonPart(**com))
            else:
                msg = serializer.errors
        if last and not rp:
            building.models.CommonPart.objects.bulk_create(last)
    if rp:
        return rp_use
    else:
        return msg

def do_attach_part(data, m_obj, lbkey, rp):
    msg = ''
    rp_use = []
    last = []
    if isinstance(data, list):
        # print(data)
        for i in data:
            if not isinstance(i, dict):
                continue
            at = {}
            at['lbkey'] = lbkey
            at['title'] = i.get('附屬建物')
            at['area'] = str2num(str_cover_dict(i.get('面積')).get('@P1'), typ='f')
            at['mark_id'] = m_obj
            serializer = BuildingSerializerAttach(data=at)
            if serializer.is_valid():
                if rp == True:
                    rp_use.append(at)
                else:
                    last.append(building.models.BuildingAttach(**at))
            else:
                msg = serializer.errors
        if last and not rp:
            building.models.BuildingAttach.objects.bulk_create(last)
    if rp:
        return rp_use
    else:
        return msg

def do_floor_part(data, m_obj, lbkey, rp):
    msg = ''
    rp_use = []
    last = []
    if isinstance(data, list):
        for i in data:
            if not isinstance(i, dict):
                continue
            fl = {}
            fl['lbkey'] = lbkey
            fl['title'] = i.get('層次')
            fl['area'] = str2num(str_cover_dict(i.get('層次面積')).get('@P1'), typ='f')
            fl['mark_id'] = m_obj
            serializer = BuildingSerializerFloor(data=fl)
            if serializer.is_valid():
                if rp == True:
                    rp_use.append(fl)
                else:
                    last.append(building.models.BuildingFloor(**fl))
            else:
                msg = serializer.errors
        if last and not rp:
            building.models.BuildingFloor.objects.bulk_create(last)
    if rp:
        return rp_use
    else:
        return msg

def do_main_part(data, m_obj, lbkey, rp):
    msg = ''
    rp_use = []
    last = []
    last = []
    lbkey_ms = lbkey.rsplit('_', 1)[0]
    if isinstance(data, list):
        for i in data:
            if not isinstance(i, dict):
                continue
            com = {}
            bnum = i.get('建號')
            com['lbkey'] = f'{lbkey_ms}_{bnum}'
            com['right_numerator'] = str2num(str_cover_dict(i.get('權利範圍')).get('@P2'), typ='i')
            com['right_denominator'] = str2num(str_cover_dict(i.get('權利範圍')).get('@P1'), typ='i')
            com['right_str'] = str_cover_dict(i.get('權利範圍')).get('#text')
            com['total_area'] = str2num(str_cover_dict(i.get('總面積')).get('@P1'), typ='f')
            com['other_remark'] = i.get('備註')
            com['mark_id'] = m_obj
            serializer = BuildingSerializerMain(data=com)
            if serializer.is_valid():
                if rp == True:
                    rp_use.append(com)
                else:
                    last.append(building.models.MainBuilding(**com))
            else:
                msg = serializer.errors
        if last:
            building.models.MainBuilding.objects.bulk_create(last)
    if rp:
        return rp_use
    else:
        return msg

def other_remark_building(data):
    main_purpose = ''
    material = ''
    use_license_no = ''
    # print(data)
    if isinstance(data, dict):
        info = data.get('資料')
        if isinstance(info, list):
            for i in info:
                i_str = all_to_half(i)
                if i_str:
                    if '主要用途' in i_str:
                        try:
                            main_purpose = i_str.split(':')[1]
                        except:
                            pass
                    elif '主要建材' in i_str:
                        try:
                            material = i_str.split(':')[1].split(' ')[0]
                        except:
                            pass
                    elif '使用執照字號' in i_str:
                        try:
                            use_license_no = i_str.split(':')[1]
                        except:
                            pass
    return main_purpose, material, use_license_no

def cover_str(data):
    res = None
    if data:
        if isinstance(data, list):
            res = data[0]
    return res

def collateral_lbkey(data):
    n_lk = []
    n_bk = []
    reg_rex = r'\d{7,7}'
    zh_rex = r'[\u4e00-\u9fa5]'
    if data:
        for i in data:
            reg = cover_str(re.findall(reg_rex, i))
            zh = ''.join(re.findall(zh_rex, i))
            lk = re.findall(r'\d{4,4}-\d{4,4}', i)
            bk = re.findall(r'\d{5,5}-\d{3,3}', i)
            if lk:
                l_kw = {'lbno': lk[0], 'regno': reg, 'region': zh}
                n_lk.append(l_kw)
            if bk:
                b_kw = {'lbno': bk[0], 'regno': reg, 'region': zh}
                n_bk.append(b_kw)

    return n_lk, n_bk

def format_reg_date(dc_time):
    time_re_YMD = re.compile(r'^[0-9]{4}/[0-9]{2}(/|/[0-9]{2})$')
    time_re_YM = re.compile(r'^[0-9]{4}(/|/[0-9]{2})$')
    time_re_Y = re.compile(r'^[0-9]{4}$')
    ft = None
    if dc_time:
        if isinstance(dc_time, datetime):
            ft = dc_time
        else:
            try:
                if time_re_YMD.match(dc_time):
                    if dc_time[-1] == '/':
                        ft = datetime.strptime(dc_time, "%Y/%m/")
                        ft = time_proV2(ft)
                    else:
                        ft = datetime.strptime(dc_time, "%Y/%m/%d")
                        ft = time_proV2(ft)
                elif time_re_YM.match(dc_time):
                    if dc_time[-1] == '/':
                        ft = datetime.strptime(dc_time, "%Y/")
                        ft = time_proV2(ft)
                    else:
                        ft = datetime.strptime(dc_time, "%Y/%m")
                        ft = time_proV2(ft)

                elif time_re_Y.match(dc_time):
                    ft = datetime.strptime(dc_time, "%Y")
                    ft = time_proV2(ft)
            except Exception as e:
                pass
            # logger.info(f'format_reg_date wrong {e}')
    return ft

def str2num(num_str, typ):
    f_num = None
    if num_str:
        if typ == 'f':
            if isinstance(num_str, (str, int, float)):
                res = re.findall(r'^\d+\.?\d+', num_str)
                if res:
                    f_num = format(float(res[0]), '.2f')

        elif typ == 'i':
            if isinstance(num_str, (int, float)):
                f_num = int(num_str)
            elif isinstance(num_str, str):
                try:                
                    f_num = int(float(num_str))
                except:
                    pass
            
    return f_num

def locate_lbkey(lbno_LB, lbtype, reg_dictqs, reg_code):
    result = {}
    if lbno_LB:
        zh = r'[\u4e00-\u9fa5]'
        if lbtype == "L":
            re_str = r'(\d{5,5}-\d{3,3})|(\d{8,8})'
            main = 5
            sub = 8
        else:
            re_str = r'(\d{4,4}-\d{4,4})|(\d{8,8})'
            main = 4
            sub = 8

        reg_dict = reg_dictqs
        for lbkey_str in lbno_LB:
            regzh = ''.join(re.findall(zh, lbkey_str))
            local_ = re.findall(re_str, lbkey_str)

            if not regzh:
                regzh = reg_dict.get(reg_code)
                if not regzh:
                    c = reg_code.split('_')[0]
                    a = reg_code.split('_')[1]
                    r = reg_code.split('_')[2]
                    try:
                        regzh = RegionCodeTable.objects.get(area_code_table_id__city_code_table_id__city_code=c, 
                                                                area_code_table_id__area_code=a,
                                                                region_code=r).region_name
                    except:
                        regzh = 'unknow'

            if result.get(regzh) == None:
                result[regzh] = []

            if local_:
                find_tuple = local_[0]
                if find_tuple[0]:
                    result[regzh].append(find_tuple[0])
                else:
                    ns = f'{find_tuple[1][0:main]}-{find_tuple[1][main:sub]}'
                    result[regzh].append(ns)
    # print(result)
    return result

def other_remark_land(data):
    parting = [] # 分割
    resurvey = [] # 重測
    merge = [] # 合併
    add = [] # 新增
    if data:
        for tp in data:
            if '分割' in tp:
                parting.append(tp)
            elif '重測' in tp:
                resurvey.append(tp)
            elif '合併' in tp:
                merge.append(tp)
            elif '新增' in tp:
                add.append(tp)
    return parting, resurvey, merge, add

def clean_regno(regno_list, typ):
    result = None
    if regno_list:
        result = []
        for regno in regno_list:
            if typ == 'o':
                rp = regno.replace('-', '')
                reg_re = re.findall(r'\d{4,4}', rp)
                result.extend(reg_re)
            else:
                rp = regno.replace('-', '')
                reg_re = re.findall(r'\d{7,7}', rp)
                result.extend(reg_re)
    return result

def restricted_type_new(restricted_data):
    df_enum = RestrictionTypeEnum.NONE
    df_str = None
    # print(restricted_data)
    if restricted_data:
        if isinstance(restricted_data, dict) == True:
            r_data = restricted_data.get('資料')
            if r_data:
                for other_remark_str in r_data:
                    if other_remark_str.find('其他依法律所為禁止處分登記') != -1:
                        df_enum = RestrictionTypeEnum.LAW_PROHIBITED
                        df_str = other_remark_str
                    elif other_remark_str.find('破產登記') != -1:
                        df_enum = RestrictionTypeEnum.BANKRUPT
                        df_str = other_remark_str
                    elif other_remark_str.find('假處分登記') != -1:
                        df_enum = RestrictionTypeEnum.PROVISIONAL_INJUCTION
                        df_str = other_remark_str
                    elif other_remark_str.find('假扣押登記') != -1:
                        df_enum = RestrictionTypeEnum.PROVISIONAL_ATTACHMENT
                        df_str = other_remark_str
                    elif other_remark_str.find('查封登記') != -1:
                        df_enum = RestrictionTypeEnum.FORECLOSURE
                        df_str = other_remark_str
                    elif other_remark_str.find('預告登記') != -1:
                        df_enum = RestrictionTypeEnum.CAUTION
                        df_str = other_remark_str
                    else:
                        df_enum = RestrictionTypeEnum.NONE
                        df_str = None
    return df_enum, df_str

def str_cover_dict(data):
    if isinstance(data, dict):
        return data
    else:
        return {}

def check_CAR(c, a, r):
    try:
        check = RegionCodeTable.objects.get(region_code=r, area_code_table_id__area_code=a, area_code_table_id__city_code_table_id__city_code=c)
        return True
    except:
        return False