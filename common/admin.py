from django.contrib import admin
from common.models import OfficeCodeTable, CityCodeTable, AreaCodeTable, RegionCodeTable, Obligee, RoadTable, SystemConfig
# Register your models here.

@admin.register(CityCodeTable)
class CityCodeTableAdmin(admin.ModelAdmin):
    list_display = ('city_name', 'city_code', 'is_valid')
    search_fields = ['city_name', 'city_code']  # 搜尋條件
    list_filter = ('is_valid', )  # 塞選條件

@admin.register(OfficeCodeTable)
class OfficeCodeTableAdmin(admin.ModelAdmin):
    list_display = ('office_name', 'office_code', 'is_valid')
    search_fields = ['office_name', 'office_code']  # 搜尋條件
    list_filter = ('is_valid', 'city_code_table_id')  # 塞選條件

@admin.register(AreaCodeTable)
class AreaCodeTableAdmin(admin.ModelAdmin):
    list_display = ('area_name', 'area_code', 'city_code_table_id', 'is_valid')
    search_fields = ['area_name', 'area_code']  # 搜尋條件
    list_filter = ('is_valid', 'city_code_table_id')  # 塞選條件

@admin.register(RegionCodeTable)
class RegionCodeTableAdmin(admin.ModelAdmin):
    list_display = ('region_code', 'region_name', 'office_code_table_id', 'area_code_table_id', 'add_time', 'remove_time', 'is_valid', 'remark')
    search_fields = ['region_name', 'region_code', 'area_code_table_id__area_name']  # 搜尋條件
    list_filter = ('is_valid', 'area_code_table_id__city_code_table_id')  # 塞選條件



@admin.register(Obligee)
class ObligeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'property_type', 'create_time', 'update_time', 'is_valid')
    search_fields = ['name']  # 搜尋條件
    list_filter = ('property_type', 'is_valid')  # 塞選條件

@admin.register(RoadTable)
class RoadTableAdmin(admin.ModelAdmin):
    list_display = ('area_code_table_id', 'road', 'is_valid', 'add_time', 'remove_time')
    search_fields = ['area_code_table_id__area_name', 'road']  # 搜尋條件
    list_filter = ('is_valid', 'area_code_table_id__city_code_table_id')  # 塞選條件
    raw_id_fields = ('area_code_table_id', )


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ('env', 'string', 'integer', 'datetime', 'json', 'remark')
    search_fields = ['env']  # 搜尋條件
