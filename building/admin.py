from django.contrib import admin, messages
from django.db import models
from django.forms import Textarea, TextInput
from django.utils.html import format_html

from building.models import (BlacklistDetail, BuildingAttach, BuildingFloor,
                             CommonPart, DailyCount, LbkeyChange, LborTaskPool,
                             MainBuilding, MarkDetail, OwnerRegnoSummary,
                             OwnerTpDetail, PropertyTypeSummary, RegnoLog,
                             RegnoModified, RightRegnoSummary, RightTpDetail,
                             Summary, Tplog, TpTaskPool,
                             TranscriptDetailSummary)
from common.enums import IsvalidTypeEnum, LBEnum, RuleTypeEnum, TaskTypeEnum
from common.serializers import create_lbor
from common.util import change_regno_time

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


############################################################################################################
# 謄本
class OwnerTpDetailInline(admin.TabularInline):
    model = OwnerTpDetail
    extra = 0
    ordering = ('-regno', )
    formfield_overrides = formfield_overrides
    show_change_link = True # 顯示編輯連結
    # raw_id_fields = ('last_tp_detail_id', ) # 關聯搜尋
    fields=('lbkey', 'regno') # 篩選
    readonly_fields=('lbkey', 'regno') # 只讀
    can_delete = True # 可否刪除按鈕

class RightTpDetailInline(admin.TabularInline):
    model = RightTpDetail
    extra = 0
    ordering = ('-regno', )
    formfield_overrides = formfield_overrides
    show_change_link = True # 顯示編輯連結
    # raw_id_fields = ('last_tp_detail_id', ) # 關聯搜尋
    fields=('lbkey', 'regno') # 篩選
    readonly_fields=('lbkey', 'regno') # 只讀
    can_delete = True # 可否刪除按鈕

class MarkTpDetailInline(admin.TabularInline):
    model = MarkDetail
    extra = 0
    ordering = ('-lbkey', )
    formfield_overrides = formfield_overrides
    show_change_link = True # 顯示編輯連結
    # raw_id_fields = ('last_tp_detail_id', ) # 關聯搜尋
    fields=('lbkey', ) # 篩選
    readonly_fields=('lbkey', ) # 只讀
    can_delete = True # 可否刪除按鈕


# BuildingAttach, BuildingFloor, MainBuilding, CommonPart
class BuildingAttachTpDetailInline(admin.TabularInline):
    model = BuildingAttach
    extra = 0
    ordering = ('-lbkey', )
    formfield_overrides = formfield_overrides
    show_change_link = True # 顯示編輯連結
    # raw_id_fields = ('last_tp_detail_id', ) # 關聯搜尋
    fields=('lbkey', 'title') # 篩選
    readonly_fields=('lbkey', 'title') # 只讀
    can_delete = True # 可否刪除按鈕

class BuildingFloorTpDetailInline(admin.TabularInline):
    model = BuildingFloor
    extra = 0
    ordering = ('-lbkey', )
    formfield_overrides = formfield_overrides
    show_change_link = True # 顯示編輯連結
    fields=('lbkey', 'title') # 篩選
    readonly_fields=('lbkey', 'title') # 只讀
    can_delete = True # 可否刪除按鈕

class MainBuildingTpDetailInline(admin.TabularInline):
    model = MainBuilding
    extra = 0
    ordering = ('-lbkey', )
    formfield_overrides = formfield_overrides
    show_change_link = True # 顯示編輯連結
    fields=('lbkey', 'total_area') # 篩選
    readonly_fields=('lbkey', 'total_area') # 只讀
    can_delete = True # 可否刪除按鈕

class CommonPartTpDetailInline(admin.TabularInline):
    model = CommonPart
    extra = 0
    ordering = ('-lbkey', )
    formfield_overrides = formfield_overrides
    show_change_link = True # 顯示編輯連結
    fields=('lbkey', 'total_area') # 篩選
    readonly_fields=('lbkey', 'total_area') # 只讀
    can_delete = True # 可否刪除按鈕
#=============================================================================

@admin.register(TranscriptDetailSummary)
class TranscriptDetailSummaryAdmin(admin.ModelAdmin):
    list_display = ('summary_id', 'pdf', 'integrity_type', 'query_time', 'create_time', 'zip_token', 'pdf_token')
    search_fields = ['=summary_id__lbkey', ]  # 搜尋條件
    list_filter = ('integrity_type', 'query_time', 'create_time', 'summary_id__city_code_table_id__city_name', )  # 塞選條件
    raw_id_fields = ('summary_id', ) # 關聯搜尋
    paginator = CachingPaginator  # 計算分頁關閉
    list_per_page = 20 # 每頁顯示數量
    paginator = CachingPaginator  # 計算分頁關閉
    inlines = [OwnerTpDetailInline, MarkTpDetailInline, RightTpDetailInline]

    def pdf(self, obj):
        return format_html('<a href="/common/tp/pdf/?lbkey={}&tp_id={}&query_time=1">pdf</a>'.format(str(obj.summary_id), obj.id))

@admin.register(MarkDetail)
class MarkDetailAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'reg_date', 'reg_reason', 'query_time', 'create_time')
    search_fields = ['lbkey', ]  # 搜尋條件
    list_filter = ('query_time', )  # 塞選條件
    raw_id_fields = ('tp_summary_id', ) # 關聯搜尋
    paginator = CachingPaginator  # 計算分頁關閉
    list_per_page = 20 # 每頁顯示數量
    # autocomplete_fields = ('mark_notice_id') # 可搜尋選單
    inlines = [BuildingAttachTpDetailInline, BuildingFloorTpDetailInline, MainBuildingTpDetailInline, CommonPartTpDetailInline]
    fields = [
        ('lbkey', 'tp_summary_id'),
        ('reg_date', 'reg_date_original'),
        ('reg_reason', 'door_number', 'total_area'),
        ('main_purpose', 'material'), 
        'floor_num', 
        'floor_num_str', 
        'build_date', 
        'build_date_str',
        'use_license_no', 
        'locate_lkey',
        'other_remark_str', 
        ('query_time', 'create_time'),
        'is_valid'] # 編輯模式的排版

# BuildingAttach, BuildingFloor, MainBuilding, CommonPart

#########################################################################################
@admin.register(BuildingAttach)
class BuildingAttachAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'title')
    search_fields = ['lbkey', 'title']  # 搜尋條件
    raw_id_fields = ('mark_id', ) # 關聯搜尋
    # list_filter = ('title', )  # 塞選條件
    paginator = CachingPaginator  # 計算分頁關閉
    list_per_page = 20 # 每頁顯示數量
    # autocomplete_fields = ('mark_notice_id') # 可搜尋選單
    fields = [
        'lbkey', 'title', 'area', 'mark_id'
        ] # 編輯模式的排版

@admin.register(BuildingFloor)
class BuildingFloorAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'title')
    search_fields = ['lbkey', 'title']  # 搜尋條件
    raw_id_fields = ('mark_id', ) # 關聯搜尋
    # list_filter = ('lbkey', 'title')  # 塞選條件
    paginator = CachingPaginator  # 計算分頁關閉
    list_per_page = 20 # 每頁顯示數量
    # autocomplete_fields = ('mark_notice_id') # 可搜尋選單
    fields = [
        'lbkey', 'title', 'area', 'mark_id'
        ] # 編輯模式的排版

@admin.register(MainBuilding)
class MainBuildingAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'total_area', 'right_str')
    search_fields = ['lbkey', ]  # 搜尋條件
    raw_id_fields = ('mark_id', ) # 關聯搜尋
    # list_filter = ('lbkey', )  # 塞選條件
    # autocomplete_fields = ('mark_notice_id') # 可搜尋選單
    paginator = CachingPaginator  # 計算分頁關閉
    list_per_page = 20 # 每頁顯示數量
    fields = [
        'lbkey', 'mark_id', 'total_area', 
        'right_str', 'right_numerator', 'right_denominator', 
        'other_remark', 'extra'
        ] # 編輯模式的排版

@admin.register(CommonPart)
class CommonPartAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'total_area', 'right_str')
    search_fields = ['lbkey']  # 搜尋條件
    raw_id_fields = ('mark_id', ) # 關聯搜尋
    # list_filter = ('lbkey', )  # 塞選條件
    # autocomplete_fields = ('mark_notice_id') # 可搜尋選單
    paginator = CachingPaginator  # 計算分頁關閉
    list_per_page = 20 # 每頁顯示數量
    fields = [
        'lbkey', 'mark_id', 'total_area', 
        'right_str', 'right_numerator', 'right_denominator', 
        'other_remark', 'extra'
        ] # 編輯模式的排版

#########################################################################################



@admin.register(OwnerTpDetail)
class OwnerTpDetailAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'regno', 'is_valid', 'create_time')
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
    'other_remark_str',
    ('restricted_reason', 'restricted_type'), 
    'is_valid'] # 編輯模式的排版
    formfield_overrides = formfield_overrides


@admin.register(RightTpDetail)
class RightTpDetailAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'regno', 'is_valid', 'create_time')
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


@admin.register(Tplog)
class TplogAdmin(admin.ModelAdmin):
    list_display = ('lbkey', 'tp_summary_id', 'query_system', 'state', 'query_time', 'create_time')
    search_fields = ['=lbkey']  # 搜尋條件
    list_filter = ('state', 'query_time', )  # 塞選條件
    search_help_text = '可搜尋欄位： {}'.format(', '.join(search_fields))  # 搜尋條件的說明
    raw_id_fields = ('tp_summary_id', )  # 關聯的可搜尋選單
    show_full_result_count = False # 計數器關閉
    paginator = CachingPaginator  # 計算分頁關閉
    list_per_page = 20 # 每頁顯示數量
    actions = [set_init]


