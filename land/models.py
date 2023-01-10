from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.utils import timezone

from common.enums import RestrictionTypeEnum, TpMenuTypeEnum
from common.models import (AreaCodeTable, BlacklistSummaryMixin, CityCodeTable,
                           DailyCountMixin, LbkeyChangeMixin,
                           LborTaskPoolMixin, MarkDetailMixin,
                           OwnerDetailMixin, PropertyTypeSummaryMixin,
                           RegionCodeTable, RegnoLogMixin, RegnoModifiedMixin,
                           RegnoSummaryMixin, RightDetailMixin, SummaryMixin,
                           TplogMixin, TpTaskPoolMixin)
from common.util import CustomJSONField


class PropertyTypeSummary(PropertyTypeSummaryMixin):
    ''' 地建號所他型態統計表 '''
    summary_id = models.OneToOneField('Summary', blank=True, null=True, db_column='summary_id', on_delete=models.CASCADE, verbose_name='設定總覽')
    building_num = models.IntegerField(blank=True, null=True, verbose_name='地上建物數量')

    class Meta:
        db_table = 'land_property_type_summary' # 指定table建立名稱
        verbose_name = '地建號所他型態統計表' # admin顯示名稱
        verbose_name_plural = '地建號所他型態統計表' # admin複數顯示名稱

    def __str__(self):
        return self.lbkey

class LbkeyChange(LbkeyChangeMixin):
    class Meta:
        db_table = 'land_lbkey_change'
        verbose_name = '新舊地號對照表'
        verbose_name_plural = '新舊地號對照表'

        indexes = [
            models.Index(fields=['old_lbkey']),
            models.Index(fields=['new_lbkey']),
        ]


class Summary(SummaryMixin):
    main_num = models.CharField(max_length=4, verbose_name='母號')
    sub_num = models.CharField(max_length=4, verbose_name='子號')
    city_code_table_id = models.ForeignKey(CityCodeTable, blank=True, null=True, db_column='city_code_table_id', on_delete=models.CASCADE, related_name='+', verbose_name='縣市')
    area_code_table_id = models.ForeignKey(AreaCodeTable, blank=True, null=True, db_column='area_code_table_id', on_delete=models.CASCADE, related_name='+', verbose_name='行政區')
    region_code_table_id = models.ForeignKey(RegionCodeTable, blank=True, null=True, db_column='region_code_table_id', on_delete=models.CASCADE, related_name='+', verbose_name='段小段')
    last_mark_detail_id = models.ForeignKey('MarkDetail', blank=True, null=True, db_column='last_mark_detail_id', on_delete=models.SET_NULL, related_name='+', verbose_name='最後標示部明細表')

    class Meta:
        db_table = 'land_summary'
        verbose_name = '總表'
        verbose_name_plural = '總表'

        constraints = [
            models.UniqueConstraint(fields=['lbkey'], name=f'{db_table} unique key')
        ]

        indexes = [
            models.Index(fields=['is_valid_type']),
            models.Index(fields=['query_time']),
            models.Index(fields=['last_mark_update_time']),
        ]

    def __str__(self):
        return self.lbkey

class OwnerRegnoSummary(RegnoSummaryMixin):
    summary_id = models.ForeignKey(Summary, db_column='summary_id', on_delete=models.CASCADE, verbose_name='總表')
    regno = models.CharField(max_length=4, verbose_name='登序')
    last_tp_detail_id = models.ForeignKey('OwnerTpDetail', blank=True, null=True, db_column='last_tp_detail_id', on_delete=models.SET_NULL, related_name='+', verbose_name='最後所有權謄本明細表')

    class Meta:
        db_table = 'land_owner_regno_summary'
        verbose_name = '所有權登序總表'
        verbose_name_plural = '所有權登序總表'
        constraints = [
            models.UniqueConstraint(fields=['summary_id', 'regno'], name=f'{db_table} unique key regno')
        ]

        indexes = [
            models.Index(fields=['is_valid_type']),
            models.Index(fields=['last_tp_update_time']),
        ]

    def __str__(self):
        return "{} {}".format(self.summary_id.lbkey, self.regno)


class RightRegnoSummary(RegnoSummaryMixin):
    summary_id = models.ForeignKey(Summary, db_column='summary_id', on_delete=models.CASCADE, verbose_name='總表')
    regno = models.CharField(max_length=7, verbose_name='登序')
    last_tp_detail_id = models.ForeignKey('RightTpDetail', blank=True, null=True, db_column='last_tp_detail_id', on_delete=models.SET_NULL, related_name='+', verbose_name='最後他項權謄本明細表')

    class Meta:
        db_table = 'land_right_regno_summary'
        verbose_name = '他項權登序總表'
        verbose_name_plural = '他項權登序總表'
        constraints = [
            models.UniqueConstraint(fields=['summary_id', 'regno'], name=f'{db_table} unique key regno')
        ]

        indexes = [
            models.Index(fields=['is_valid_type']),
            models.Index(fields=['last_tp_update_time']),
        ]

    def __str__(self):
        return "{} {}".format(self.summary_id.lbkey, self.regno)


class RegnoLog(RegnoLogMixin):
    summary_id = models.ForeignKey(Summary, db_column='summary_id', blank=True, null=True, on_delete=models.SET_NULL, verbose_name='總表')
    inquirer_id = models.ForeignKey(User, db_column='inquirer_id', related_name='+', blank=True, null=True, on_delete=models.SET_NULL, verbose_name='查詢者')

    class Meta:
        db_table = 'land_regno_log'
        verbose_name = '登序紀錄表'
        verbose_name_plural = '登序紀錄表'

        indexes = [
            models.Index(fields=['lbkey']),
            models.Index(fields=['query_system']),
            models.Index(fields=['state']),
            models.Index(fields=['query_time']),
            models.Index(fields=['create_time']),
        ]

    def __str__(self):
        return "{}".format(self.lbkey)

class DailyCount(DailyCountMixin):
    class Meta:
        db_table = 'land_daily_count'
        verbose_name = '每日統計表'
        verbose_name_plural = '每日統計表'


class RegnoModified(RegnoModifiedMixin):
    regno_log_id = models.ForeignKey(RegnoLog, db_column='regno_log_id', on_delete=models.CASCADE, verbose_name='登序紀錄表')
    summary_id = models.ForeignKey(Summary, db_column='summary_id', blank=True, null=True, on_delete=models.CASCADE, verbose_name='總表')

    class Meta:
        db_table = 'land_regno_modified'
        verbose_name = '登序異動表'
        verbose_name_plural = '登序異動表'
        indexes = [
            models.Index(fields=['change_time']),
            models.Index(fields=['create_time']),
            models.Index(fields=['owner_add_num']),
            models.Index(fields=['owner_rm_num']),
            models.Index(fields=['right_add_num']),
            models.Index(fields=['right_rm_num']),
        ]


class LborTaskPool(LborTaskPoolMixin):
    class Meta:
        db_table = 'land_lbor_task_pool'
        verbose_name = '登序任務表'
        verbose_name_plural = '登序任務表'


class BlacklistDetail(BlacklistSummaryMixin):
    class Meta:
        db_table = 'land_blacklist_summary'
        verbose_name = '查詢黑名單'
        verbose_name_plural = '查詢黑名單'
        indexes = [
            models.Index(fields=['lbkey']),
        ]

# 謄本區域 ================================================================================================================

class MarkNotice(models.Model):
    mark_detail_id = models.ForeignKey('MarkDetail', blank=True, null=True, db_column='mark_detail_id', on_delete=models.CASCADE, verbose_name='標示部明細表')
    lbkey = models.CharField(max_length=255, verbose_name='地號')
    land_notice_value = models.CharField(max_length=255, blank=True, null=True, verbose_name='公告現值')
    land_notice_value_date = models.CharField(max_length=255, blank=True, null=True, verbose_name='公告現值年月')
    land_notice_price = models.CharField(max_length=255, blank=True, null=True, verbose_name='公告地價')
    land_notice_price_date = models.CharField(max_length=255, blank=True, null=True, verbose_name='公告地價年月')
    land_area_size = models.DecimalField(max_digits=15, decimal_places=5, blank=True, null=True, verbose_name='土地面積')
    size_changed = models.DecimalField(max_digits=15, decimal_places=5, blank=True, null=True, verbose_name='面積增減')
    query_time = models.DateTimeField(default=timezone.now, verbose_name='查詢時間')
    is_valid = models.BooleanField(default=True, verbose_name='驗證')
    class Meta:
        db_table = 'land_tp_mark_notice'
        verbose_name = '標示部公告現值地價'
        verbose_name_plural = '標示部公告現值地價'
        indexes = [
            models.Index(fields=['lbkey']),
            models.Index(fields=['is_valid']),
        ]

    def __str__(self):
        return self.lbkey


class OwnerTpDetail(OwnerDetailMixin):
    tp_summary_id = models.ForeignKey('TranscriptDetailSummary', blank=True, null=True, db_column='tp_summary_id', on_delete=models.CASCADE, verbose_name='謄本明細總表')
    declare_value = models.IntegerField(blank=True, null=True, verbose_name='申報地價')
    declare_value_date = models.DateField(blank=True, null=True, verbose_name='申報地價年月')
    declare_value_date_original = models.CharField(max_length=255, blank=True, null=True, verbose_name='申報地價年月(字串)')
    old_value = CustomJSONField(default=dict, blank=True, null=True, verbose_name='前次移轉現值或原規定地價')
    land_value_remark = models.TextField(blank=True, null=True, verbose_name='地價備註事項')
    other_remark_str = CustomJSONField(default=dict, blank=True, null=True, verbose_name='其他登記事項(原字串)')
    restricted_type = models.IntegerField(choices=RestrictionTypeEnum.choices(), default=RestrictionTypeEnum.NONE, verbose_name='限制登記型態')
    restricted_reason = models.TextField(blank=True, null=True, verbose_name='限制登記原因')
    class Meta:
        db_table = 'land_tp_owner_detail'
        verbose_name = '所有權謄本明細表'
        verbose_name_plural = '所有權謄本明細表'

        indexes = [
            models.Index(fields=['lbkey']),
            models.Index(fields=['lbkey', 'regno']),
            models.Index(fields=['reg_reason']),
            models.Index(fields=['is_valid']),
        ]
    def __str__(self):
        return "{} {}".format(self.lbkey, self.regno)


class RightTpDetail(RightDetailMixin):
    tp_summary_id = models.ForeignKey('TranscriptDetailSummary', blank=True, null=True, db_column='tp_summary_id', on_delete=models.CASCADE, verbose_name='謄本明細總表')
    other_remark_str = CustomJSONField(default=dict, blank=True, null=True, verbose_name='其他登記事項(原字串)')
    restricted_type = models.IntegerField(choices=RestrictionTypeEnum.choices(), default=RestrictionTypeEnum.NONE, verbose_name='限制登記型態')
    restricted_reason = models.TextField(blank=True, null=True, verbose_name='限制登記原因')
    class Meta:
        db_table = 'land_tp_right_detail'
        verbose_name = '他項權謄本明細表'
        verbose_name_plural = '他項權謄本明細表'

        indexes = [
            models.Index(fields=['lbkey']),
            models.Index(fields=['lbkey', 'regno']),
            models.Index(fields=['reg_reason']),
            models.Index(fields=['is_valid']),
        ]
    def __str__(self):
        return "{} {}".format(self.lbkey, self.regno)


class MarkDetail(MarkDetailMixin):
    tp_summary_id = models.ForeignKey('TranscriptDetailSummary', blank=True, null=True, db_column='tp_summary_id', on_delete=models.CASCADE, verbose_name='謄本明細總表')
    land_purpose = models.CharField(max_length=255, blank=True, null=True, verbose_name='地目')
    land_level = models.CharField(max_length=255, blank=True, null=True, verbose_name='等則')
    using_zone = models.CharField(max_length=255, blank=True, null=True, verbose_name='使用分區')
    urban_name = models.CharField(max_length=255, blank=True, null=True, verbose_name='使用地類別')
    locate_bkey = CustomJSONField(default=dict, blank=True, null=True, verbose_name='地上建物建號(列表)')
    parting = CustomJSONField(default=list, blank=True, null=True, verbose_name='分割')
    resurvey = CustomJSONField(default=list, blank=True, null=True, verbose_name='重測')
    merge = CustomJSONField(default=list, blank=True, null=True, verbose_name='合併')
    add = CustomJSONField(default=list, blank=True, null=True, verbose_name='新增')
    normal_mark = CustomJSONField(default=list, blank=True, null=True, verbose_name='一般註記事項')
    class Meta:
        db_table = 'land_tp_mark_detail'
        verbose_name = '標示部明細表'
        verbose_name_plural = '標示部明細表'
        indexes = [
            models.Index(fields=['lbkey']),
            models.Index(fields=['is_valid']),
        ]
        
    def __str__(self):
        return "{}".format(self.lbkey)


class TranscriptDetailSummary(models.Model):
    summary_id = models.ForeignKey(Summary, db_column='summary_id', on_delete=models.CASCADE, related_name='+', verbose_name='總表')
    integrity_type = models.IntegerField(choices=TpMenuTypeEnum.choices(), default=TpMenuTypeEnum.UNKNOW, verbose_name='謄本選單')
    query_time = models.DateTimeField(default=timezone.now, verbose_name='查詢時間')
    create_time = models.DateTimeField(auto_now_add=True, null=True, blank=False, verbose_name='建立時間')
    zip_token = models.CharField(max_length=255, blank=True, null=True, verbose_name='ZIP金鑰')
    pdf_token = models.CharField(max_length=255, blank=True, null=True, verbose_name='PDF金鑰')
    is_finish = models.BooleanField(default=False, verbose_name='是否完成')
    class Meta:
        db_table = 'land_tp_detail_summary'
        verbose_name = '謄本明細總表'
        verbose_name_plural = '謄本明細總表'
        indexes = [
            models.Index(fields=['integrity_type']),
            models.Index(fields=['query_time']),
            models.Index(fields=['is_finish']),
        ]

    def __str__(self):
        return "{} {}".format(self.summary_id.lbkey, self.query_time.strftime('%Y-%m-%d'))


class TpTaskPool(TpTaskPoolMixin):
    class Meta:
        db_table = 'land_tp_task_pool'
        verbose_name = '謄本任務表'
        verbose_name_plural = '謄本任務表'
        
        indexes = [
            models.Index(fields=['lbkey']),
            models.Index(fields=['owners_num']),
            models.Index(fields=['rights_num']),
            models.Index(fields=['state']),
            models.Index(fields=['priority']),
            models.Index(fields=['rules']),
            models.Index(fields=['account']),
            models.Index(fields=['system']),
            models.Index(fields=['create_time']),
        ]

class Tplog(TplogMixin):
    tp_summary_id = models.ForeignKey(TranscriptDetailSummary, db_column='tp_summary_id', blank=True, null=True, on_delete=models.SET_NULL, verbose_name='總表')
    inquirer_id = models.ForeignKey(User, blank=True, null=True, db_column='inquirer_id', related_name='+', on_delete=models.SET_NULL, verbose_name='查詢者')
    class Meta:
        db_table = 'land_tp_log'
        verbose_name = '謄本紀錄表'
        verbose_name_plural = '謄本紀錄表'

        indexes = [
            models.Index(fields=['lbkey']),
            models.Index(fields=['query_system']),
            models.Index(fields=['state']),
            models.Index(fields=['task_id']),
            models.Index(fields=['log_id']),
            models.Index(fields=['query_time']),
            models.Index(fields=['create_time']),
        ]
