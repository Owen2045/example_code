import json
from email.policy import default

from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.utils import timezone

from common.enums import (IsvalidTypeEnum, LborTpTypeEnum, PropertyTypeEnum,
                          QuerySystemEnum, RuleTypeEnum, TaskTypeEnum)

# from common.util import CustomJSONField

# Create your models here.

class CustomJSONField(models.JSONField):
    ''' json 的 Field'''
    def get_prep_value(self, value):
        if value is None:
            return value
        return json.dumps(value, ensure_ascii=False)

class CityCodeTable(models.Model):
    city_name = models.CharField(default='', max_length=20, verbose_name='縣市名稱')
    city_code  = models.CharField(max_length=20, verbose_name='縣市代碼')
    is_valid = models.BooleanField(default=True, verbose_name='有效')

    class Meta:
        verbose_name = "縣市代碼表"
        verbose_name_plural = "縣市代碼表"
        db_table = 'common_city_code_table'

    def __str__(self):
        return "{}{}".format(self.city_code, self.city_name)


class OfficeCodeTable(models.Model):
    office_name = models.CharField(max_length=20, verbose_name='事務所名稱')
    office_code  = models.CharField(max_length=20, verbose_name='事務所代碼')
    city_code_table_id = models.ForeignKey(CityCodeTable, on_delete=models.CASCADE, verbose_name='縣市代碼表')
    is_valid = models.BooleanField(default=True, verbose_name='有效')

    class Meta:
        verbose_name = "事務所代碼表"
        verbose_name_plural = "事務所代碼表"
        db_table = 'common_office_code_table'

        indexes = [
            models.Index(fields=['office_code']),
            models.Index(fields=['office_name']),
        ]

    def __str__(self):
        return "{}{}".format(self.office_code, self.office_name)

class AreaCodeTable(models.Model):
    area_name = models.CharField(default='', max_length=20, verbose_name='行政區名稱')
    area_code  = models.CharField(max_length=20, verbose_name='行政區代碼')
    city_code_table_id = models.ForeignKey(CityCodeTable, on_delete=models.CASCADE, verbose_name='縣市代碼表')
    is_valid = models.BooleanField(default=True, verbose_name='有效')

    class Meta:
        verbose_name = "行政區代碼表"
        verbose_name_plural = "行政區代碼表"
        db_table = 'common_area_code_table'

        indexes = [
            models.Index(fields=['area_code']), 
            models.Index(fields=['area_name']), 
        ]

    def __str__(self):
        return "{}{}".format(self.area_code, self.area_name)


class RegionCodeTable(models.Model):
    region_name = models.CharField(max_length=20, verbose_name='段小段名稱')
    region_code  = models.CharField(max_length=20, verbose_name='段小段代碼')
    area_code_table_id = models.ForeignKey(AreaCodeTable, on_delete=models.CASCADE, verbose_name='行政區代碼表')
    office_code_table_id = models.ForeignKey(OfficeCodeTable, on_delete=models.CASCADE, verbose_name='事務所代碼表')
    add_time = models.DateTimeField(default=timezone.now, verbose_name='新增時間')
    remove_time = models.DateTimeField(null=True, blank=True, verbose_name='移除時間')
    remark = models.CharField(max_length=20, null=True, blank=True, verbose_name='備註')
    is_valid = models.BooleanField(default=True, verbose_name='有效')

    class Meta:
        verbose_name = "段小段代碼表"
        verbose_name_plural = "段小段代碼表"
        db_table = 'common_region_code_table'

        indexes = [
            models.Index(fields=['is_valid']), 
        ]

    def __str__(self):
        return "{}{}".format(self.region_code, self.region_name)



class MarkDetailMixin(models.Model):
    lbkey = models.CharField(max_length=20, verbose_name='地建號')
    reg_date = models.DateTimeField(blank=True, null=True, verbose_name='登記日期')
    reg_date_original = models.CharField(max_length=255, blank=True, null=True, verbose_name='登記日期(原字串)')
    reg_reason = models.CharField(max_length=255, blank=True, null=True, verbose_name='登記原因')
    total_area = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name='總面積')
    is_valid = models.BooleanField(default=True, verbose_name='有無效')
    other_remark_str = CustomJSONField(default=list, blank=True, null=True, verbose_name='其他登記事項(原字串)')
    create_time = models.DateTimeField(default=timezone.now, verbose_name='建立日期')
    query_time = models.DateTimeField(default=timezone.now, blank=True, null=True, verbose_name='查詢日期')

    class Meta:
        abstract = True

class OwnerDetailMixin(models.Model):
    lbkey = models.CharField(db_index=True, max_length=20, verbose_name='地建號')
    regno = models.CharField(max_length=4, verbose_name='登記次序')
    reg_date = models.DateField(blank=True, null=True, verbose_name='登記日期')
    reg_date_original = models.CharField(max_length=255, blank=True, null=True, verbose_name='登記日期(原字串)')
    reg_reason = models.CharField(max_length=255, blank=True, null=True, verbose_name='登記原因')
    reason_date = models.DateField(blank=True, null=True, verbose_name='原因發生日期')
    name = models.CharField(max_length=255, blank=True, null=True, verbose_name='所有權人姓名')
    uid = models.CharField(max_length=10, blank=True, null=True, verbose_name='統一編號／身份證字號')
    bday = models.DateField(blank=True, null=True, verbose_name='出生日期')
    address = models.TextField(blank=True, null=True, verbose_name='住址')
    address_re = models.TextField(blank=True, null=True, verbose_name='住址(正規化)')
    admin = CustomJSONField(default=dict, blank=True, null=True, verbose_name='管理者')
    right_numerator = models.BigIntegerField(blank=True, null=True, verbose_name='權利範圍分子')
    right_denominator = models.BigIntegerField(blank=True, null=True, verbose_name='權利範圍分母')
    right_str = models.CharField(max_length=255, blank=True, null=True, verbose_name='權利範圍(字串)')
    cert_id = models.CharField(max_length=255, blank=True, null=True, verbose_name='權狀字號')
    related_creditor_regno = CustomJSONField(default=list, blank=True, null=True, verbose_name='相關他項登記次序')
    related_creditor_num = models.IntegerField(blank=True, null=True, verbose_name='相關他項登記數量')
    query_time = models.DateTimeField(blank=True, null=True, verbose_name='查詢日期')
    query_time_str = models.CharField(max_length=255, blank=True, null=True, verbose_name='查詢日期(字串)')
    create_time = models.DateTimeField(default=timezone.now, verbose_name='建立時間')
    is_valid = models.BooleanField(default=True, verbose_name='有無效')
    extra = CustomJSONField(default=dict, blank=True, null=True, verbose_name='額外資料')

    class Meta:
        abstract = True


class RightDetailMixin(models.Model):
    lbkey = models.CharField(db_index=True, max_length=20, verbose_name='地建號')
    regno = models.CharField(max_length=8, verbose_name='登記次序')
    right_type = models.CharField(max_length=255, blank=True, null=True, verbose_name='權利種類')
    setting_doc_id = models.CharField(max_length=255, blank=True, null=True, verbose_name='收件年期字號')
    reg_date = models.DateField(blank=True, null=True, verbose_name='登記日期')
    reg_date_original = models.CharField(max_length=255, blank=True, null=True, verbose_name='登記日期(原字串)')
    reg_reason = models.CharField(max_length=255, blank=True, null=True, verbose_name='登記原因')
    name = models.CharField(max_length=255, blank=True, null=True, verbose_name='權利人姓名')
    uid = models.CharField(max_length=10, blank=True, null=True, verbose_name='統一編號／身份證字號')
    address = models.TextField(blank=True, null=True, verbose_name='住址')
    address_re = models.TextField(blank=True, null=True, verbose_name='住址(正規化)')
    admin = CustomJSONField(default=dict, blank=True, null=True, verbose_name='管理者')

    right_numerator = models.BigIntegerField(blank=True, null=True, verbose_name='權利範圍分子')
    right_denominator = models.BigIntegerField(blank=True, null=True, verbose_name='權利範圍分母')
    right_str = models.CharField(max_length=255, blank=True, null=True, verbose_name='權利範圍(字串)')

    obligation_numerator = models.BigIntegerField(blank=True, null=True, verbose_name='債權額比例分子')
    obligation_denominator = models.BigIntegerField(blank=True, null=True, verbose_name='債權額比例分母')
    obligation_str = models.CharField(max_length=255, blank=True, null=True, verbose_name='債權額比例(字串)')

    guarantee_amount = models.BigIntegerField(blank=True, null=True, verbose_name='擔保債權總金額')
    guarantee_amount_str = models.CharField(max_length=255, blank=True, null=True, verbose_name='擔保債權總金額(原字串)')
    guarantee_type_range = models.TextField(blank=True, null=True, verbose_name='擔保債權種類及範圍')
    guarantee_date = models.DateField(blank=True, null=True, verbose_name='擔保債權確定期日')
    guarantee_date_str = models.CharField(max_length=255, blank=True, null=True, verbose_name='擔保債權確定期日(字串)')

    duration_start_date = models.DateField(blank=True, null=True, verbose_name='存續起始日期')
    duration_end_date = models.DateField(blank=True, null=True, verbose_name='存續結束日期')
    duration_str = models.CharField(max_length=255, blank=True, null=True, verbose_name='存續期間(字串)')
    
    payoff_date = models.DateField(blank=True, null=True, verbose_name='清償日期')
    payoff_date_str = models.CharField(max_length=255, blank=True, null=True, verbose_name='清償日期(字串)')
    interest = models.CharField(max_length=1023, blank=True, null=True, verbose_name='利息(率)')
    overdue_interest = models.CharField(max_length=1023, blank=True, null=True, verbose_name='遲延利息(率)')
    penalty = models.TextField(blank=True, null=True, verbose_name='違約金')
    other_guarantee = models.TextField(blank=True, null=True, verbose_name='其他擔保範圍約定')
    obligee_ratio = models.TextField(blank=True, null=True, verbose_name='債務人及債務額比例')
    right_target = models.CharField(max_length=255, blank=True, null=True, verbose_name='權利標的')
    related_owner_regno = CustomJSONField(default=list, blank=True, null=True, verbose_name='標的登記次序')
    related_owner_num = models.IntegerField(blank=True, null=True, verbose_name='標的登記數量')
    setting_right_numerator = models.BigIntegerField(blank=True, null=True, verbose_name='設定權利範圍分子')
    setting_right_denominator = models.BigIntegerField(blank=True, null=True, verbose_name='設定權利範圍分母')
    setting_right_str = models.CharField(max_length=255, blank=True, null=True, verbose_name='設定權利範圍(字串)')
    right_cert_doc_id = models.CharField(max_length=255, blank=True, null=True, verbose_name='證明書字號')
    setting_obligee = models.TextField(blank=True, null=True, verbose_name='設定義務人')
    collateral_lkey = CustomJSONField(default=list, blank=True, null=True, verbose_name='共同擔保地號(列表)')
    collateral_bkey = CustomJSONField(default=list, blank=True, null=True, verbose_name='共同擔保建號(列表)')
    setting_creditor_right_type = models.TextField(blank=True, null=True, verbose_name='設定他項權利(列表)')
    setting_creditor_right_regno = models.TextField(blank=True, null=True, verbose_name='設定他項權利登記次序(列表)')
    mortgage_overdue = models.TextField(blank=True, null=True, verbose_name='流抵約定')
    query_time = models.DateTimeField(verbose_name='查詢日期')
    query_time_str = models.CharField(max_length=255, blank=True, null=True, verbose_name='查詢日期(字串)')
    create_time = models.DateTimeField(default=timezone.now, verbose_name='建立時間')
    is_valid = models.BooleanField(default=True, verbose_name='有無效')
    extra = CustomJSONField(default=dict, blank=True, null=True, verbose_name='額外資料')
    class Meta:
        abstract = True

class LbkeyChangeMixin(models.Model):
    old_lbkey = models.CharField(max_length=20, verbose_name='舊地建號')
    new_lbkey = models.CharField(max_length=20, verbose_name='新地建號')

    class Meta:
        abstract = True

class SummaryMixin(models.Model):
    lbkey = models.CharField(max_length=20, verbose_name='地建號')
    owners_num = models.IntegerField(default=0, verbose_name='所有權人數')
    rights_num = models.IntegerField(default=0, verbose_name='他項權人數')
    create_time = models.DateTimeField(auto_now_add=True, null=True, blank=False, verbose_name='建立時間')
    query_time = models.DateTimeField(default=timezone.now, verbose_name='查詢時間')
    remove_time = models.DateTimeField(blank=True, null=True, verbose_name='移除時間')
    is_valid_type = models.IntegerField(choices=IsvalidTypeEnum.choices(), default=IsvalidTypeEnum.VALID, verbose_name='驗證')
    last_mark_update_time = models.DateTimeField(blank=True, null=True, verbose_name='最後標示部更新時間')
    extra = CustomJSONField(default=dict, null=True, blank=True, verbose_name='額外資訊', help_text='moi 協作平台(次數時間)')

    class Meta:
        abstract = True

class RegnoSummaryMixin(models.Model):
    name = models.CharField(blank=True, null=True, max_length=255, verbose_name='姓名')
    property_type = models.IntegerField(choices=PropertyTypeEnum.choices(), default=PropertyTypeEnum.NONETYPE, verbose_name='設定類型')
    is_valid_type = models.IntegerField(choices=IsvalidTypeEnum.choices(), default=IsvalidTypeEnum.VALID, verbose_name='驗證')
    query_time = models.DateTimeField(default=timezone.now, verbose_name='查詢時間')
    add_time = models.DateTimeField(default=timezone.now, blank=True, null=True, verbose_name='新增時間')
    remove_time = models.DateTimeField(blank=True, null=True, verbose_name='移除時間')
    last_tp_update_time = models.DateTimeField(blank=True, null=True, verbose_name='最後謄本更新時間')
    class Meta:
        abstract = True

class PropertyTypeSummaryMixin(models.Model):
    lbkey = models.CharField(max_length=20, blank=True, null=True, verbose_name='地建號')    
    o_unknown_num = models.IntegerField(blank=True, null=True, verbose_name='所_未知')
    o_goverment_num = models.IntegerField(blank=True, null=True, verbose_name='所_政府')
    o_private_num = models.IntegerField(blank=True, null=True, verbose_name='所_私人')
    o_company_num = models.IntegerField(blank=True, null=True, verbose_name='所_公司')
    o_rental_num = models.IntegerField(blank=True, null=True, verbose_name='所_租賃')
    o_finance_num = models.IntegerField(blank=True, null=True, verbose_name='所_金融')
    last_o_property_type = models.IntegerField(blank=True, null=True, choices=PropertyTypeEnum.choices(), verbose_name='最後登記所有權型態', help_text='最後一筆所有權型態')
    r_unknown_num = models.IntegerField(blank=True, null=True, verbose_name='他_未知')
    r_goverment_num = models.IntegerField(blank=True, null=True, verbose_name='他_政府')
    r_private_num = models.IntegerField(blank=True, null=True, verbose_name='他_私人')
    r_company_num = models.IntegerField(blank=True, null=True, verbose_name='他_公司')
    r_rental_num = models.IntegerField(blank=True, null=True, verbose_name='他_租賃')
    r_finance_num = models.IntegerField(blank=True, null=True, verbose_name='他_金融')
    last_r_property_type = models.IntegerField(blank=True, null=True, choices=PropertyTypeEnum.choices(), verbose_name='最後登記所有權型態', help_text='最後一筆所有權型態')

    class Meta:
        abstract = True


class RegnoLogMixin(models.Model):
    lbkey = models.CharField(max_length=20, verbose_name='地建號')
    query_system = models.IntegerField(choices=QuerySystemEnum.choices(), default=QuerySystemEnum.LOR_V2, verbose_name='查詢系統')
    owners = CustomJSONField(default=dict, null=True, blank=True, help_text='{"0001": "測＊＊"}', verbose_name='所有權人清單')
    rights = CustomJSONField(default=dict, null=True, blank=True, help_text='{"0001000": "測試"}', verbose_name='他項權人清單')
    is_no_list = models.BooleanField(default=False, verbose_name='查無列表')
    rules = models.IntegerField(choices=RuleTypeEnum.choices(), default=RuleTypeEnum.BOTH, verbose_name='規則')
    state = models.IntegerField(choices=TaskTypeEnum.choices(), default=TaskTypeEnum.INIT, verbose_name='狀態')
    query_time = models.DateTimeField(default=timezone.now, verbose_name='查詢時間')
    create_time = models.DateTimeField(auto_now_add=True, null=True, blank=False, verbose_name='建立時間')
    task_id = models.IntegerField(blank=True, null=True, verbose_name='任務代號')

    class Meta:
        abstract = True

class DailyCountMixin(models.Model):
    lbor_stats = CustomJSONField(default=dict, null=True, blank=True, verbose_name='列表統計')
    tp_stats = CustomJSONField(default=dict, null=True, blank=True, verbose_name='謄本統計')
    lbor_sum = models.IntegerField(default=0, verbose_name='列表當日查詢量')
    tp_sum = models.IntegerField(default=0, verbose_name='謄本當日查詢量')
    statistics_time = models.DateField(null=True, blank=True, verbose_name='統計日期')
    lbor_update_time = models.DateTimeField(default=None, blank=True, null=True, verbose_name='列表更新時間')
    tp_update_time = models.DateTimeField(default=None, blank=True, null=True, verbose_name='謄本更新時間')
    class Meta:
        abstract = True

class RegnoModifiedMixin(models.Model):
    owner_add_list = CustomJSONField(default=list, null=True, blank=True, help_text='["0001", "0002"]', verbose_name='所有權增加清單')
    owner_rm_list = CustomJSONField(default=list, null=True, blank=True, help_text='["0001", "0002"]', verbose_name='所有權減少清單')
    right_add_list = CustomJSONField(default=list, null=True, blank=True, help_text='["0001001", "0002000"]', verbose_name='他項權增加清單')
    right_rm_list = CustomJSONField(default=list, null=True, blank=True, help_text='["0001001", "0002000"]', verbose_name='他項權減少清單')
    owner_add_num = models.IntegerField(default=0, verbose_name='所有權增加筆數')
    owner_rm_num = models.IntegerField(default=0, verbose_name='所有權減少筆數')
    right_add_num = models.IntegerField(default=0, verbose_name='他項權增加筆數')
    right_rm_num = models.IntegerField(default=0, verbose_name='他項權減少筆數')
    change_time = models.DateTimeField(default=timezone.now, verbose_name='異動時間')
    create_time = models.DateTimeField(auto_now_add=True, null=True, blank=False, verbose_name='建立時間')
    class Meta:
        abstract = True

class LborTaskPoolMixin(models.Model):
    lbkey = models.CharField(max_length=20, verbose_name='地建號')
    state = models.IntegerField(choices=TaskTypeEnum.choices(), default=TaskTypeEnum.INIT, verbose_name='狀態')
    priority = models.IntegerField(default=70, verbose_name='優先度')
    owners_num = models.IntegerField(default=0, verbose_name='所有權人數')
    rights_num = models.IntegerField(default=0, verbose_name='他項權人數')
    rules = models.IntegerField(choices=RuleTypeEnum.choices(), default=RuleTypeEnum.BOTH, verbose_name='規則')

    create_time = models.DateTimeField(auto_now_add=True, null=True, blank=False, verbose_name='建立時間')
    take_time = models.DateTimeField(null=True, blank=True, verbose_name='取用時間')
    complete_time = models.DateTimeField(null=True, blank=True, verbose_name='完成時間')
    extra = CustomJSONField(default=dict, null=True, blank=True, verbose_name='額外資訊')

    class Meta:
        abstract = True


class BlacklistSummaryMixin(models.Model):
    lbkey = models.CharField(max_length=20, verbose_name='地建號')
    query_system = models.IntegerField(choices=QuerySystemEnum.choices(), default=QuerySystemEnum.LOR_V2, verbose_name='查詢系統')
    lbor_tp_type = models.IntegerField(choices=LborTpTypeEnum.choices(), default=LborTpTypeEnum.LBOR, verbose_name='列表謄本型態')
    remark = CustomJSONField(default=list, null=True, blank=True, help_text='["無此段小段", "群旋error"]', verbose_name='備註')
    create_time = models.DateTimeField(auto_now_add=True, null=True, blank=False, verbose_name='建立時間')
    take_time = models.DateTimeField(null=True, blank=True, verbose_name='取用時間')
    take_count = models.IntegerField(default=0, verbose_name='取用計次')

    class Meta:
        abstract = True


class Obligee(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True, verbose_name='名稱')
    property_type = models.IntegerField(choices=PropertyTypeEnum.choices(), default=PropertyTypeEnum.NONETYPE, verbose_name='分類')
    create_time = models.DateTimeField(default=timezone.now, blank=True, null=True, verbose_name='建立時間')
    update_time = models.DateTimeField(default=timezone.now, blank=True, null=True, verbose_name='更新時間')
    is_valid = models.BooleanField(default=True, verbose_name='有無效')
    class Meta:
        verbose_name = '所他型態對照表'
        verbose_name_plural = '所他型態對照表'


class LbkeyMapping(models.Model):
    lkey = models.CharField(max_length=20, blank=True, null=True, verbose_name='地號')
    bkey = models.CharField(max_length=20, blank=True, null=True, verbose_name='建號')
    create_time = models.DateTimeField(auto_now_add=True, null=True, blank=True, verbose_name='建立時間')
    invalid_time = models.DateTimeField(null=True, blank=True, verbose_name='移除時間')
    is_valid = models.BooleanField(default=True, verbose_name='地建號關連')

    class Meta:
        verbose_name = '地建號關聯表'
        verbose_name_plural = '地建號關聯表'
        unique_together = ('lkey', 'bkey')
        indexes = [
            models.Index(fields=['lkey']),
            models.Index(fields=['bkey']),
            models.Index(fields=['is_valid']),
        ]


class SystemConfig(models.Model):
    env = models.CharField(max_length=255, verbose_name='環境變數')
    string = models.CharField(max_length=255, blank=True, null=True, verbose_name='字串')
    integer = models.IntegerField(blank=True, null=True, verbose_name='數值')
    datetime = models.DateTimeField(blank=True, null=True, verbose_name='時間')
    json = CustomJSONField(default=dict, null=True, blank=True, verbose_name='傑森')
    remark = models.TextField(blank=True, null=True, verbose_name='備註')
    class Meta:
        verbose_name = '系統設定表'
        verbose_name_plural = '系統設定表'
        indexes = [
            models.Index(fields=['env']),
        ]


class UserActionLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, help_text='紀錄來源平台用的')
    lbor_tp_type = models.IntegerField(choices=LborTpTypeEnum.choices(), default=LborTpTypeEnum.LBOR, verbose_name='列表謄本型態')
    source_user_id = models.IntegerField(default=0, verbose_name='來源使用者ID')
    task_id_l = models.TextField(null=True, blank=True, verbose_name='任務id土地')
    task_id_b = models.TextField(null=True, blank=True, verbose_name='任務id建物')
    conditions = models.TextField(null=True, blank=True, verbose_name='條件')
    remark = models.TextField(null=True, blank=True, verbose_name='備註')
    action_time = models.DateTimeField(default=timezone.now, verbose_name='動作時間')


class RoadTable(models.Model):
    road = models.CharField(max_length=20, verbose_name='路名')
    area_code_table_id = models.ForeignKey(AreaCodeTable, on_delete=models.CASCADE, verbose_name='行政區代碼表')
    is_valid = models.BooleanField(default=True, verbose_name='有效')
    add_time = models.DateTimeField(default=timezone.now, verbose_name='新增時間')
    remove_time = models.DateTimeField(null=True, blank=True, verbose_name='移除時間')
    remark = models.CharField(max_length=20, null=True, blank=True, verbose_name='備註')

    class Meta:
        verbose_name = "路名表"
        verbose_name_plural = "路名表"
        db_table = 'common_road_table'

        constraints = [
            models.UniqueConstraint(fields=['area_code_table_id', 'road'], name=f'{db_table} unique key regno')
        ]

    def __str__(self):
        return "{}{}".format(self.area_code_table_id, self.road)


class CommunitySummary(models.Model):
    city_code_table_id = models.ForeignKey(CityCodeTable, blank=True, null=True, db_column='city_code_table_id', on_delete=models.CASCADE, verbose_name='縣市')
    area_code_table_id = models.ForeignKey(AreaCodeTable, blank=True, null=True, db_column='area_code_table_id', on_delete=models.CASCADE, verbose_name='行政區')
    road_summary_id = models.ForeignKey(RoadTable, db_column='road_summary_id', on_delete=models.CASCADE, verbose_name='路名')
    
    building_time = models.DateTimeField(null=True, blank=True, verbose_name='建築完成日期')
    community = models.CharField(max_length=50, blank=True, null=True, verbose_name='社區')

    addresses = models.CharField(max_length=1000, blank=True, null=True, verbose_name='門牌', help_text='區域位置或門牌 (路巷弄號) ,間隔 用包含判斷')
    point = models.PointField(geography=True, null=True, blank=True, verbose_name='中心點座標')

    builder = models.CharField(max_length=50, blank=True, null=True, verbose_name='建設公司')
    constructer = models.CharField(max_length=50, blank=True, null=True, verbose_name='營造公司')

    class Meta:
        db_table = 'extra_building_community_summary'
        verbose_name = '社區總表'
        verbose_name_plural = '社區總表'

    def __str__(self):
        return "{}".format(self.community)


class TpTaskPoolMixin(models.Model):
    lbkey = models.CharField(max_length=20, verbose_name='地建號')    
    o_regno_str = models.TextField(blank=True, null=True, verbose_name='所有權登序')
    r_regno_str = models.TextField(blank=True, null=True, verbose_name='他項權登序')
    owners_num = models.IntegerField(default=0, verbose_name='所有權人數')
    rights_num = models.IntegerField(default=0, verbose_name='他項權人數')
    state = models.IntegerField(choices=TaskTypeEnum.choices(), default=TaskTypeEnum.INIT, verbose_name='狀態')
    priority = models.IntegerField(default=70, verbose_name='優先度')
    rules = models.IntegerField(choices=RuleTypeEnum.choices(), default=RuleTypeEnum.BOTH, verbose_name='規則')
    schedule = models.CharField(max_length=255, blank=True, null=True, verbose_name='進度明細')
    is_mark_only = models.BooleanField(default=False, verbose_name='只調標示部')
    account = models.CharField(max_length=255, blank=True, null=True, verbose_name='帳號')
    system = models.IntegerField(choices=QuerySystemEnum.choices(), default=QuerySystemEnum.GAIAS_PC, verbose_name='系統')
    extra = CustomJSONField(default=dict, blank=True, null=True, verbose_name='額外')

    create_time = models.DateTimeField(auto_now_add=True, null=True, blank=False, verbose_name='建立時間')
    take_time = models.DateTimeField(null=True, blank=True, verbose_name='取用時間')
    complete_time = models.DateTimeField(null=True, blank=True, verbose_name='完成時間')
    class Meta:
        abstract = True


class TplogMixin(models.Model):
    lbkey = models.CharField(max_length=20, verbose_name='地建號')
    query_system = models.IntegerField(choices=QuerySystemEnum.choices(), default=QuerySystemEnum.LOR_V2, verbose_name='查詢系統')
    owners = CustomJSONField(default=dict, null=True, blank=True, help_text='{"0001": "測＊＊"}')
    rights = CustomJSONField(default=dict, null=True, blank=True, help_text='{"0001000": "測試"}')
    rules = models.IntegerField(choices=RuleTypeEnum.choices(), default=RuleTypeEnum.BOTH, verbose_name='規則')
    state = models.IntegerField(choices=TaskTypeEnum.choices(), default=TaskTypeEnum.INIT, verbose_name='狀態')
    transcript = CustomJSONField(null=True, blank=True, verbose_name='謄本json')
    owner_result_msg = CustomJSONField(blank=True, null=True, verbose_name='所有權人訊息')
    right_result_msg = CustomJSONField(blank=True, null=True, verbose_name='他項權人訊息')
    mark_result_msg = CustomJSONField(blank=True, null=True, verbose_name='標示部訊息')
    task_id = models.IntegerField(blank=True, null=True, verbose_name='任務id')
    log_id = models.IntegerField(blank=True, null=True, verbose_name='log_id(重新解析用)')
    use_account = models.CharField(max_length=255, blank=True, null=True, verbose_name='使用帳號')    
    query_time = models.DateTimeField(default=timezone.now, verbose_name='查詢時間')
    create_time = models.DateTimeField(auto_now_add=True, null=True, blank=False, verbose_name='建立時間')
    class Meta:
        abstract = True

class NewBkey(models.Model):
    bkey = models.CharField(max_length=20, primary_key=True, verbose_name='建號')
    create_time = models.DateTimeField(auto_now_add=True, null=True, blank=True, verbose_name='建立時間')

    class Meta:
        verbose_name = '新建號表'
        verbose_name_plural = '新建號表'

