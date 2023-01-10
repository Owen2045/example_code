from django.contrib import admin
# Register your models here.
from user.models import UserProfile
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as AuthUserAdmin

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    max_num = 1
    can_delete = False

class UserAdmin(AuthUserAdmin):
    inlines = [UserProfileInline]

# 註銷舊用戶管理員
admin.site.unregister(User)
# 註冊新用戶管理員
admin.site.register(User, UserAdmin)

@admin.register(UserProfile)
class Share_receiptAdmin(admin.ModelAdmin):
    list_display = ('user', 'avatar')
