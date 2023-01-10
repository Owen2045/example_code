from django.contrib.admin import AdminSite

class ModelIndexReOrder(AdminSite):
    def get_app_list(self, request):
        """
        Return a sorted list of all the installed apps that have been
        registered in this site.
        """
        # re_order = {
        #     'Company': 101,
        #     'Staff': 102,
            
        #     'Customer': 201,
        #     'User': 202,

        # }
        app_dict = self._build_app_dict(request)

        # Sort the apps alphabetically.
        # app_list = sorted(app_dict.values(), key=lambda x: x['name'].lower())

        app_list = app_dict.values()

        # Sort the models alphabetically within each app.
        # for app in app_list:
        #     #對自定義的APP排序，預設的不排序
        #     if app["app_label"] == 'APP名稱':
        #         app['models'].sort(key=lambda x: re_order[x['object_name']])
        #     else:
        #         app['models'].sort(key=lambda x: x['name'])
        return app_list