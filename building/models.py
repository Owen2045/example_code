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
    class Meta:
        db_table = 'building_property_type_summary' # 指定table建立名稱
        verbose_name = '地建號所他型態統計表' # admin顯示名稱
        verbose_name_plural = '地建號所他型態統計表' # admin複數顯示名稱

    def __str__(self):
        return self.lbkey


class LbkeyChange(LbkeyChangeMixin):
    class Meta:
        db_table = 'building_lbkey_change'
        verbose_name = '新舊地號對照表'
        verbose_name_plural = '新舊地號對照表'

        indexes = [
            models.Index(fields=['old_lbkey']),
            models.Index(fields=['new_lbkey']),
        ]


class Summary(SummaryMixin):
    main_num = models.CharField(max_length=5, verbose_name='母號')
    sub_num = models.CharField(max_length=3, verbose_name='子號')
    city_code_table_id = models.ForeignKey(CityCodeTable, blank=True, null=True, db_column='city_code_table_id', on_delete=models.CASCADE, related_name='+', verbose_name='縣市')
    area_code_table_id = models.ForeignKey(AreaCodeTable, blank=True, null=True, db_column='area_code_table_id', on_delete=models.CASCADE, related_name='+', verbose_name='行政區')
    region_code_table_id = models.ForeignKey(RegionCodeTable, blank=True, null=True, db_column='region_code_table_id', on_delete=models.CASCADE, related_name='+', verbose_name='段小段')
    last_mark_detail_id = models.ForeignKey('MarkDetail', blank=True, null=True, db_column='last_mark_detail_id', on_delete=models.SET_NULL, related_name='+', verbose_name='最後標示部明細表')

    class Meta:
        db_table = 'building_summary'
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
        db_table = 'building_owner_regno_summary'
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
        db_table = 'building_right_regno_summary'
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
        db_table = 'building_regno_log'
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
        db_table = 'building_daily_count'
        verbose_name = '每日統計表'
        verbose_name_plural = '每日統計表'


class RegnoModified(RegnoModifiedMixin):
    regno_log_id = models.ForeignKey(RegnoLog, db_column='regno_log_id', on_delete=models.CASCADE, verbose_name='登序紀錄表')
    summary_id = models.ForeignKey(Summary, db_column='summary_id', blank=True, null=True, on_delete=models.CASCADE, verbose_name='總表')

    class Meta:
        db_table = 'building_regno_modified'
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
        db_table = 'building_lbor_task_pool'
        verbose_name = '登序任務表'
        verbose_name_plural = '登序任務表'


class BlacklistDetail(BlacklistSummaryMixin):
    class Meta:
        db_table = 'building_blacklist_summary'
        verbose_name = '查詢黑名單'
        verbose_name_plural = '查詢黑名單'
        indexes = [
            models.Index(fields=['lbkey']),
        ]

# 謄本區域 ================================================================================================================

class BuildingObjectMixin(models.Model):
    # 建物物件(繼承用) 附屬,層次
    lbkey = models.CharField(max_length=20, null=True, verbose_name='地建號')
    title = models.CharField(max_length=255, blank=True, null=True, verbose_name='名稱')
    area = models.DecimalField(max_digits=15, decimal_places=5, blank=True, null=True, verbose_name='面積')
    class Meta:
        abstract = True


class BuildingDataMixin(models.Model):
    # 建物資料(繼承用) 主建,共有
    lbkey = models.CharField(max_length=20, null=True, verbose_name='地建號')
    right_numerator = models.BigIntegerField(blank=True, null=True, verbose_name='權利範圍分子')
    right_denominator = models.BigIntegerField(blank=True, null=True, verbose_name='權利範圍分母')
    right_str = models.CharField(max_length=255, blank=True, null=True, verbose_name='權利範圍(字串)')
    total_area = models.DecimalField(max_digits=15, decimal_places=5, blank=True, null=True, verbose_name='面積')
    other_remark = CustomJSONField(default=dict, blank=True, null=True, verbose_name='其他登記事項')
    extra = CustomJSONField(default=dict, blank=True, null=True, verbose_name='額外註記')
    class Meta:
        abstract = True


class OwnerTpDetail(OwnerDetailMixin):
    tp_summary_id = models.ForeignKey('TranscriptDetailSummary', blank=True, null=True, db_column='tp_summary_id', on_delete=models.CASCADE, verbose_name='謄本明細總表')
    other_remark_str = CustomJSONField(default=dict, blank=True, null=True, verbose_name='其他登記事項(原字串)')
    restricted_type = models.IntegerField(choices=RestrictionTypeEnum.choices(), default=RestrictionTypeEnum.NONE, verbose_name='限制登記型態')
    restricted_reason = models.TextField(blank=True, null=True, verbose_name='限制登記原因')
    class Meta:
        db_table = 'building_tp_owner_detail'
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
        db_table = 'building_tp_right_detail'
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
    # road_name = models.TextField(blank=True, null=True, verbose_name='路名')
    door_number = models.CharField(max_length=1023, blank=True, null=True, verbose_name='門牌')
    locate_lkey = CustomJSONField(default=dict, blank=True, null=True, verbose_name='建物坐落地號(列表)')
    main_purpose = models.TextField(blank=True, null=True, verbose_name='主要用途')
    material = models.CharField(max_length=1023, blank=True, null=True, verbose_name='主要建材')
    floor_num = models.IntegerField(blank=True, null=True, verbose_name='層數')
    floor_num_str = models.CharField(max_length=1023, blank=True, null=True, verbose_name='層數(字串)')
    build_date = models.DateField(blank=True, null=True, verbose_name='建築完成日期')
    build_date_str = models.CharField(max_length=255, blank=True, null=True, verbose_name='建築完成日期(字串)')
    use_license_no = models.TextField(blank=True, null=True, verbose_name='使用執照字號')
    class Meta:
        db_table = 'building_tp_mark_detail'
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
    zip_token = models.CharField(max_length=255, null=True, blank=True, verbose_name='ZIP金鑰')
    pdf_token = models.CharField(max_length=255, null=True, blank=True, verbose_name='PDF金鑰')
    is_finish = models.BooleanField(default=False, verbose_name='是否完成')
    class Meta:
        db_table = 'building_tp_detail_summary'
        verbose_name = '謄本明細總表'
        verbose_name_plural = '謄本明細總表'
        indexes = [
            models.Index(fields=['integrity_type']),
            models.Index(fields=['query_time']),
            models.Index(fields=['is_finish']),
        ]

    def __str__(self):
        return "{} {}".format(self.summary_id.lbkey, self.query_time.strftime('%Y-%m-%d'))


class BuildingFloor(BuildingObjectMixin):
    mark_id = models.ForeignKey(MarkDetail, db_column='mark_id', blank=True, null=True, on_delete=models.CASCADE, verbose_name='標示部')
    class Meta:
        db_table = 'building_tp_building_floor'
        verbose_name = '建物層次'
        verbose_name_plural = '建物層次'
        indexes = [
            models.Index(fields=['lbkey']),
            models.Index(fields=['area']),
        ]


class BuildingAttach(BuildingObjectMixin):
    mark_id = models.ForeignKey(MarkDetail, db_column='mark_id', blank=True, null=True, on_delete=models.CASCADE, verbose_name='標示部')
    class Meta:
        db_table = 'building_tp_building_attach'
        verbose_name = '附屬建物'
        verbose_name_plural = '附屬建物'
        indexes = [
            models.Index(fields=['lbkey']),
            models.Index(fields=['area']),
        ]


class CommonPart(BuildingDataMixin):
    mark_id = models.ForeignKey(MarkDetail, db_column='mark_id', blank=True, null=True, on_delete=models.CASCADE, verbose_name='標示部')
    class Meta:
        db_table = 'building_tp_common_part'
        verbose_name = '共有部份'
        verbose_name_plural = '共有部份'
        indexes = [
            models.Index(fields=['lbkey']),
            models.Index(fields=['total_area']),
        ]


class MainBuilding(BuildingDataMixin):
    mark_id = models.ForeignKey(MarkDetail, db_column='mark_id', blank=True, null=True, on_delete=models.CASCADE, verbose_name='標示部')
    class Meta:
        db_table = 'building_tp_main_building'
        verbose_name = '主建物'
        verbose_name_plural = '主建物'
        indexes = [
            models.Index(fields=['lbkey']),
            models.Index(fields=['total_area']),
        ]


class TpTaskPool(TpTaskPoolMixin):
    pass
    class Meta:
        db_table = 'building_tp_task_pool'
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
        db_table = 'building_tp_log'
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
