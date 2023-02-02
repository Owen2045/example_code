from django.contrib import admin
from common.models import OfficeCodeTable, CityCodeTable, AreaCodeTable, RegionCodeTable, Obligee, RoadTable, SystemConfig
# Register your models here.


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ('env', 'string', 'integer', 'datetime', 'json', 'remark')
    search_fields = ['env']  # 搜尋條件
