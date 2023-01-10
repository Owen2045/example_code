from django.contrib.admin.apps import AdminConfig

#類名隨便，可自己辨認就行
class lbor_v3UserConfig(AdminConfig):
    default_site = 'lbor_v3.admin.ModelIndexReOrder'
