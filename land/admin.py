from django.contrib import admin, messages
from django.db import models
from django.forms import Textarea, TextInput
from django.utils.html import format_html

from common.enums import IsvalidTypeEnum, LBEnum, RuleTypeEnum, TaskTypeEnum
from common.serializers import create_lbor
from common.util import change_regno_time
from land.models import (BlacklistDetail, DailyCount, LbkeyChange,
                         LborTaskPool, MarkDetail, MarkNotice,
                         OwnerRegnoSummary, OwnerTpDetail, PropertyTypeSummary,
                         RegnoLog, RegnoModified, RightRegnoSummary,
                         RightTpDetail, Summary, Tplog, TpTaskPool,
                         TranscriptDetailSummary)

# Register your models here.

formfield_overrides = {
    models.TextField: {
        'widget': Textarea(
            attrs={'rows': 3,
                'cols': 30,})
    },
    models.CharField: {
        'widget': TextInput(
            attrs={'cols': 20,})
    }
}
from django.core.paginator import Paginator


class CachingPaginator(Paginator):
    '''
    快取分頁記數
    '''
    @property
    def count(self):
        return 999 


def get_new_queryset(qs, request):
    if '/change/' not in request.build_absolute_uri():
        if qs.exists() and qs.latest('id').id > 1000000:
            query_id = qs.latest('id').id-1000000
            qs = qs.filter(id__gte=query_id)
    return qs

# state 欄位處理
@admin.action(description='設定為廢棄')
def set_discard(modeladmin, request, queryset):
    queryset.update(state=TaskTypeEnum.DISCARD)
    modeladmin.message_user(request, '變更成功', level=messages.INFO)

@admin.action(description='設定為待處理')
def set_init(modeladmin, request, queryset):
    queryset.update(state=TaskTypeEnum.INIT)
    modeladmin.message_user(request, '變更成功', level=messages.INFO)

@admin.action(description='設定為解析中')
def set_parser(modeladmin, request, queryset):
    queryset.update(state=TaskTypeEnum.PARSER)
    modeladmin.message_user(request, '變更成功', level=messages.INFO)

@admin.action(description='設定為完成')
def set_complete(modeladmin, request, queryset):
    queryset.update(state=TaskTypeEnum.COMPLETE)
    modeladmin.message_user(request, '變更成功', level=messages.INFO)

# is_valid_type 欄位處理
@admin.action(description='設定為無效')
def set_invalid(modeladmin, request, queryset):
    queryset.update(is_valid_type=IsvalidTypeEnum.INVALID)
    modeladmin.message_user(request, '變更成功', level=messages.INFO)

@admin.action(description='設定為有效')
def set_valid(modeladmin, request, queryset):
    queryset.update(is_valid_type=IsvalidTypeEnum.VALID)
    modeladmin.message_user(request, '變更成功', level=messages.INFO)


class OwnerRegnoSummaryInline(admin.TabularInline):
    model = OwnerRegnoSummary
    extra = 0
    ordering = ('-regno', )
    formfield_overrides = formfield_overrides
    show_change_link = True # 顯示編輯連結
    # raw_id_fields = ('last_tp_detail_id', ) # 關聯搜尋
    fields=('regno', 'name', 'property_type', 'is_valid_type', 'query_time', 'add_time', 'remove_time', 'last_tp_detail_id') # 篩選
    readonly_fields=('regno', 'name', 'property_type', 'is_valid_type', 'query_time', 'add_time', 'remove_time', 'last_tp_detail_id') # 只讀
    # can_delete = False
    # def has_add_permission(self, request, obj=None):
    #     return False
    # def has_change_permission(self, request, obj=None):
    #     return False
    # def has_delete_permission(self, request, obj=None):
    #     return False


class RightRegnoSummaryInline(admin.TabularInline):
    model = RightRegnoSummary
    extra = 0
    ordering = ('-regno', )
    formfield_overrides = formfield_overrides
    show_change_link = True # 顯示編輯連結
    # raw_id_fields = ('last_tp_detail_id', ) # 關聯搜尋
    fields=('regno', 'name', 'property_type', 'is_valid_type', 'query_time', 'add_time', 'remove_time', 'last_tp_detail_id')
    readonly_fields=('regno', 'name', 'property_type', 'is_valid_type', 'query_time', 'add_time', 'remove_time', 'last_tp_detail_id')
    # can_delete = False
    # def has_delete_permission(self, request, obj=None):
    #     return False


class PropertyTypeSummaryInline(admin.TabularInline):
    model = PropertyTypeSummary
    extra = 0
    fields = ['o_unknown_num', 'o_goverment_num', 'o_private_num', 'o_company_num', 'o_rental_num', 'o_finance_num', 'last_o_property_type', 
            'r_unknown_num', 'r_goverment_num', 'r_private_num', 'r_company_num', 'r_rental_num', 'r_finance_num', 'last_r_property_type']
    readonly_fields = ['o_unknown_num', 'o_goverment_num', 'o_private_num', 'o_company_num', 'o_rental_num', 'o_finance_num', 'last_o_property_type', 
            'r_unknown_num', 'r_goverment_num', 'r_private_num', 'r_company_num', 'r_rental_num', 'r_finance_num', 'last_r_property_type']
    formfield_overrides = formfield_overrides
    can_delete = False


@admin.register(Summary)
class SummaryAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'owners_num', 'rights_num', 'create_time', 'query_time', 'remove_time', 'is_valid_type')
    search_fields = ['^lbkey']  # 搜尋條件
    list_filter = ('is_valid_type', 'create_time', 'query_time')  # 塞選條件
    # autocomplete_fields = ('city_code_table_id', 'area_code_table_id', 'region_code_table_id', 'last_mark_detail_id') # 可搜尋選單
    raw_id_fields = ('city_code_table_id', 'area_code_table_id', 'region_code_table_id', 'last_mark_detail_id', )  # 關聯的可搜尋選單
    inlines = [PropertyTypeSummaryInline, OwnerRegnoSummaryInline, RightRegnoSummaryInline]
    fields = [('lbkey'), 
            'is_valid_type',
            ('city_code_table_id', 'area_code_table_id', 'region_code_table_id'),
            ('main_num', 'sub_num'),
            ('owners_num', 'rights_num'), ('create_time', 'query_time', 'remove_time'),
            # ('point', 'polygon'), # 座標礙眼先關掉
            'last_mark_detail_id', 'extra'] # 編輯模式的排版
    readonly_fields=('create_time',)
    formfield_overrides = formfield_overrides
    show_full_result_count = False
    paginator = CachingPaginator
    search_help_text = '可搜尋欄位： {}'.format(', '.join(search_fields))
    list_per_page = 20
    actions = [set_invalid, set_valid]


@admin.register(OwnerRegnoSummary)
class OwnerRegnoSummaryAdmin(admin.ModelAdmin):
    list_display = ('summary_id', 'regno', 'name', 'property_type', 'is_valid_type', 'query_time', 'add_time', 'remove_time', 'last_tp_detail_id')
    search_fields = ['=summary_id__lbkey', '=regno']  # 搜尋條件
    search_help_text = '可搜尋欄位： {}'.format(', '.join(search_fields))  # 搜尋條件的說明
    list_filter = ('is_valid_type', 'query_time', 'add_time', 'remove_time', )  # 塞選條件
    # autocomplete_fields = ('summary_id', 'last_tp_detail_id')  # 關聯的可搜尋下拉選單
    raw_id_fields = ('summary_id', 'last_tp_detail_id', )  # 關聯的可搜尋選單
    show_full_result_count = False # 計數器關閉
    paginator = CachingPaginator  # 計算分頁關閉
    list_per_page = 20 # 每頁顯示數量

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return get_new_queryset(qs, request)


@admin.register(RightRegnoSummary)
class RightRegnoSummaryAdmin(admin.ModelAdmin):
    list_display = ('summary_id', 'regno', 'name', 'property_type', 'is_valid_type', 'query_time', 'add_time', 'remove_time', 'last_tp_detail_id')
    search_fields = ['=summary_id__lbkey', '=regno']  # 搜尋條件
    search_help_text = '可搜尋欄位： {}'.format(', '.join(search_fields))  # 搜尋條件的說明
    list_filter = ('is_valid_type', 'query_time', 'add_time', 'remove_time', )  # 塞選條件
    # autocomplete_fields = ('summary_id', 'last_tp_detail_id')  # 關聯的可搜尋下拉選單
    raw_id_fields = ('summary_id', 'last_tp_detail_id', )  # 關聯的可搜尋選單
    show_full_result_count = False # 計數器關閉
    paginator = CachingPaginator  # 計算分頁關閉
    list_per_page = 20 # 每頁顯示數量

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return get_new_queryset(qs, request)


@admin.register(RegnoLog)
class RegnoLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'lbkey', 'query_system', 'state', 'rules', 'query_time', 'owners', 'rights', 'is_no_list', 'inquirer_id', 'task_id')
    search_fields = ['=lbkey']  # 搜尋條件
    list_filter = ('state', 'rules', 'query_time', 'query_system', )  # 塞選條件
    search_help_text = '可搜尋欄位： {}'.format(', '.join(search_fields))  # 搜尋條件的說明
    raw_id_fields = ('summary_id', )  # 關聯的可搜尋選單
    actions = [set_init, set_parser, set_complete, set_discard, 'delete_this', 'parser_this']

    show_full_result_count = False # 計數器關閉
    paginator = CachingPaginator  # 計算分頁關閉
    list_per_page = 50 # 每頁顯示數量

    @admin.action(description='廢棄這筆log和變更時間')
    def delete_this(self, request, queryset):
        # 請使用時間排序，且需要有上一筆與下一筆
        # 輸入lbkey > 廢棄選擇的 > 
        #    解析新增時間為選擇 移除時間為選擇的下一筆 刪除
        #    解析移除時間為選擇 移除移除時間 改變狀態 （無範例）
        #    解析名字因上方改變狀態而去抓取上上筆 改回正常
        #    解析異常改待處理 然後一筆一筆送進原解析流程
        if len(queryset) != 1:
            self.message_user(request, '變更失敗 只能選取一筆', level=messages.ERROR)
            return

        discard_log = queryset[0]

        summary_id = discard_log.summary_id
        if summary_id == None:
            self.message_user(request, '變更失敗 查無總表', level=messages.ERROR)
            return

        regno_log_qs = RegnoLog.objects.filter(summary_id=summary_id, state__in=[TaskTypeEnum.COMPLETE, TaskTypeEnum.COMPLETE_NO_CHANGE])

        end_complete_regno_log_qs = regno_log_qs.filter(state__in=[TaskTypeEnum.COMPLETE, TaskTypeEnum.COMPLETE_NO_CHANGE]).order_by('-query_time')
        # 大於 "廢棄的查詢時間" 的最後一筆
        o_complete_log = end_complete_regno_log_qs.filter(rules__in=[RuleTypeEnum.BOTH, RuleTypeEnum.OWNER], query_time__gt=discard_log.query_time).last()
        r_complete_log = end_complete_regno_log_qs.filter(rules__in=[RuleTypeEnum.BOTH, RuleTypeEnum.RIGHT], query_time__gt=discard_log.query_time).last()
        if o_complete_log == None or r_complete_log == None:
            self.message_user(request, '變更失敗 查無上筆所或他資料', level=messages.ERROR)
            return

        if o_complete_log.is_no_list == False:
            summary_id.is_valid_type = IsvalidTypeEnum.VALID

        owner_qs = summary_id.ownerregnosummary_set.all()
        right_qs = summary_id.rightregnosummary_set.all()
        o_dels, o_modifys = change_regno_time(discard_log, o_complete_log.query_time, o_complete_log.owners, owner_qs)
        r_dels, r_modifys = change_regno_time(discard_log, r_complete_log.query_time, r_complete_log.rights, right_qs)

        owner_qs.filter(id__in=o_dels).delete()
        right_qs.filter(id__in=r_dels).delete()

        OwnerRegnoSummary.objects.bulk_update(o_modifys, fields=['name', 'is_valid_type', 'query_time', 'remove_time'])
        RightRegnoSummary.objects.bulk_update(r_modifys, fields=['name', 'is_valid_type', 'query_time', 'remove_time'])

        discard_log.state = TaskTypeEnum.DISCARD
        discard_log.save()

        regno_log_qs = RegnoLog.objects.filter(summary_id=summary_id, state=TaskTypeEnum.ABNORMAL_PARSER)
        for regno_log in regno_log_qs:
            regno_log.state = TaskTypeEnum.INIT
            create_lbor([regno_log], LBEnum.LAND)
        self.message_user(request, '變更成功', level=messages.INFO)

    @admin.action(description='解析此筆(限地建號最舊的待處理)')
    def parser_this(self, request, queryset):
        for regno_log in queryset:
            if regno_log.state == TaskTypeEnum.INIT:
                create_lbor([regno_log], LBEnum.LAND)
        self.message_user(request, '完成解析', level=messages.INFO)

@admin.register(LbkeyChange)
class LbkeyChangeAdmin(admin.ModelAdmin):
    list_display = ('old_lbkey', 'new_lbkey')
    search_fields = ['=old_lbkey', '=new_lbkey']  # 搜尋條件


@admin.register(RegnoModified)
class RegnoModifiedAdmin(admin.ModelAdmin):
    list_display = ('summary_id', 'owner_add_num', 'owner_rm_num', 'right_add_num', 'right_rm_num', 'create_time', 'change_time')
    list_filter = ('create_time', 'change_time', )  # 塞選條件
    raw_id_fields = ('summary_id', 'regno_log_id')  # 關聯的可搜尋選單

    paginator = CachingPaginator
    show_full_result_count = False
    list_per_page = 20
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if '/change/' not in request.build_absolute_uri():
            if qs.exists() and qs.latest('id').id > 1000000:
                query_id = qs.latest('id').id-1000000
                qs = qs.filter(id__gte=query_id)
        return qs

@admin.register(DailyCount)
class DailyCountAdmin(admin.ModelAdmin):
    list_display = ('statistics_time', 'lbor_sum', 'tp_sum')
    list_filter = ('statistics_time', )  # 塞選條件


@admin.register(LborTaskPool)
class LborTaskPoolAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'state', 'priority', 'owners_num', 'rights_num', 'rules', 'create_time', 'take_time', 'complete_time', 'extra')
    search_fields = ['^lbkey']  # 搜尋條件
    list_filter = ('create_time', 'complete_time', 'owners_num', 'rights_num', 'priority')  # 塞選條件
    actions = [set_init, set_discard]


@admin.register(BlacklistDetail)
class BlacklistSummaryAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'query_system', 'lbor_tp_type', 'remark', 'take_time', 'take_count')
    search_fields = ['^lbkey', '^remark']  # 搜尋條件
    search_help_text = '可搜尋欄位： {}'.format(', '.join(search_fields))  # 搜尋條件的說明
    list_filter = ('query_system', 'lbor_tp_type', 'take_time')  # 塞選條件



# 謄本區域 ================================================================================================================

class MarkTpDetailInline(admin.TabularInline):
    model = MarkDetail
    extra = 0
    ordering = ('-lbkey', )
    formfield_overrides = formfield_overrides
    show_change_link = True # 顯示編輯連結
    fields=('lbkey', ) # 篩選
    readonly_fields=('lbkey', ) # 只讀
    can_delete = True # 可否刪除按鈕

class MarkNoticeInline(admin.TabularInline):
    model = MarkNotice
    extra = 0
    ordering = ('-lbkey', )
    formfield_overrides = formfield_overrides
    show_change_link = True # 顯示編輯連結
    fields=('lbkey', ) # 篩選
    readonly_fields=('lbkey', ) # 只讀
    can_delete = True # 可否刪除按鈕


class OwnerTpDetailInline(admin.TabularInline):
    model = OwnerTpDetail
    extra = 0
    ordering = ('-regno', )
    formfield_overrides = formfield_overrides
    show_change_link = True # 顯示編輯連結
    fields=('lbkey', 'regno') # 篩選
    readonly_fields=('lbkey', 'regno') # 只讀
    can_delete = True # 可否刪除按鈕


class RightTpDetailInline(admin.TabularInline):
    model = RightTpDetail
    extra = 0
    ordering = ('-regno', )
    formfield_overrides = formfield_overrides
    show_change_link = True # 顯示編輯連結
    fields=('lbkey', 'regno') # 篩選
    readonly_fields=('lbkey', 'regno') # 只讀
    can_delete = True # 可否刪除按鈕


@admin.register(TranscriptDetailSummary)
class TranscriptDetailSummaryAdmin(admin.ModelAdmin):
    list_display = ('summary_id', 'pdf', 'integrity_type', 'query_time', 'create_time', 'zip_token', 'pdf_token')
    search_fields = ['=summary_id__lbkey', ]  # 搜尋條件
    list_filter = ('integrity_type', 'query_time', 'create_time', 'summary_id__city_code_table_id__city_name', )  # 塞選條件
    raw_id_fields = ('summary_id', ) # 關聯搜尋
    list_per_page = 20 # 每頁顯示數量
    paginator = CachingPaginator  # 計算分頁關閉
    inlines = [OwnerTpDetailInline, MarkTpDetailInline, RightTpDetailInline]

    def pdf(self, obj):
        return format_html('<a href="/common/tp/pdf/?lbkey={}&tp_id={}&query_time=1">pdf</a>'.format(str(obj.summary_id), obj.id))

@admin.register(MarkDetail)
class MarkDetailAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'reg_date', 'reg_reason', 'using_zone', 'urban_name', 'query_time')
    search_fields = ['lbkey', ]  # 搜尋條件
    list_filter = ('query_time', )  # 塞選條件
    raw_id_fields = ('tp_summary_id', ) # 關聯搜尋
    # autocomplete_fields = ('mark_notice_id') # 可搜尋選單
    paginator = CachingPaginator  # 計算分頁關閉
    inlines = [MarkNoticeInline]
    fields = ['lbkey', 'tp_summary_id',
        ('land_purpose', 'land_level'),
        ('using_zone', 'urban_name'),
        'locate_bkey',        
        ('reg_date', 'reg_date_original'),
        'reg_reason', 'total_area',
        ('query_time', 'create_time'),
        'is_valid'] # 編輯模式的排版


@admin.register(MarkNotice)
class MarkNoticeAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'land_notice_value', 'land_notice_price', 'query_time')
    search_fields = ['lbkey', ]

    fields = ['lbkey', 
        ('land_notice_value', 'land_notice_value_date'),
        ('size_changed'),
        'query_time', 'is_valid'] # 編輯模式的排版


@admin.register(OwnerTpDetail)
class OwnerTpDetailAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'regno', 'is_valid')
    search_fields = ['lbkey', ]
    autocomplete_fields = ('tp_summary_id', ) # 可搜尋選單
    paginator = CachingPaginator  # 計算分頁關閉
    list_per_page = 20 # 每頁顯示數量
    fields = [
    ('lbkey', 'regno', 'tp_summary_id'), 
    ('reg_date', 'reg_reason', 'reason_date'),
    ('name', 'uid', 'bday', 'address', 'address_re'),
    'admin', 
    ('right_numerator', 'right_denominator', 'right_str'),
    'cert_id', 
    ('related_creditor_regno', 'related_creditor_num'),
    ('query_time', 'query_time_str', 'create_time'),
    'extra',
    ('declare_value', 'declare_value_date', 'declare_value_date_original'),
    ('old_value', 'land_value_remark'),
    'other_remark_str',
    ('restricted_reason', 'restricted_type'), 
    'is_valid'] # 編輯模式的排版
    formfield_overrides = formfield_overrides


@admin.register(RightTpDetail)
class RightTpDetailAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'regno', 'is_valid')
    search_fields = ['lbkey', ]
    autocomplete_fields = ('tp_summary_id', ) # 可搜尋選單
    paginator = CachingPaginator  # 計算分頁關閉
    list_per_page = 20 # 每頁顯示數量
    fields = [
    ('lbkey', 'regno', 'tp_summary_id'),
    ('right_type', 'setting_doc_id'), 
    ('reg_date', 'reg_reason'),
    ('name', 'uid', 'address', 'address_re'),
    'admin',
    ('right_numerator', 'right_denominator', 'right_str'),
    ('other_remark_str', 'restricted_type', 'restricted_reason'),
    ('obligation_numerator', 'obligation_denominator', 'obligation_str'),
    ('guarantee_amount', 'guarantee_amount_str', 'guarantee_type_range', 'guarantee_date'),
    ('duration_start_date', 'duration_end_date', 'duration_str'),
    ('payoff_date', 'payoff_date_str'),
    ('interest', 'overdue_interest'),
    ('penalty', 'other_guarantee'),
    ('obligee_ratio', 'right_target'),
    ('related_owner_regno', 'related_owner_num'),
    ('setting_right_numerator', 'setting_right_denominator', 'setting_right_str'),
    'right_cert_doc_id', 'setting_obligee',
    ('collateral_lkey', 'collateral_bkey'),
    ('setting_creditor_right_type', 'setting_creditor_right_regno'),
    'mortgage_overdue', 
    ('query_time', 'query_time_str', 'create_time'), 
    'extra',
    'is_valid'] # 編輯模式的排版
    formfield_overrides = formfield_overrides


@admin.register(TpTaskPool)
class TpTaskPoolAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'state', 'owners_num', 'rights_num', 'priority', 'rules', 'account', 'system', 'extra', 'create_time', 'take_time', 'complete_time')
    search_fields = ['lbkey', 'priority']  # 搜尋條件
    list_filter = ('state', 'create_time')  # 塞選條件
    list_per_page = 50 # 每頁顯示數量
    actions = [set_init, set_discard]


state = models.IntegerField(choices=TaskTypeEnum.choices(), default=TaskTypeEnum.INIT, verbose_name='狀態')
@admin.register(Tplog)
class TplogAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'tp_summary_id', 'query_system', 'state', 'query_time', 'create_time')
    search_fields = ['=lbkey']  # 搜尋條件
    list_filter = ('state', 'query_time', )  # 塞選條件 # query_system
    search_help_text = '可搜尋欄位： {}'.format(', '.join(search_fields))  # 搜尋條件的說明
    raw_id_fields = ('tp_summary_id', )  # 關聯的可搜尋選單
    show_full_result_count = False # 計數器關閉
    paginator = CachingPaginator  # 計算分頁關閉
    list_per_page = 20 # 每頁顯示數量
    actions = [set_init]
