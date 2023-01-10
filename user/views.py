from user.models import UserProfile
from user.forms import UserProfileForm

from django.shortcuts import render
from django.views.generic import View, TemplateView
from django.http import HttpResponseRedirect
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from rest_framework.authtoken.models import Token

class Index(TemplateView):
    def get(self, request):
        if request.user.is_anonymous:
            return HttpResponseRedirect('/accounts/login/')
        return render(request, 'base.html')

class AvatarChange(TemplateView):
    def get(self, request):
        form = UserProfileForm(instance=request.user.userprofile)
        return render(request, 'avatar_change.html', {'form': form})

    def post(self, request):
        form = UserProfileForm(request.POST, request.FILES, instance=request.user.userprofile) # instance 指定列
        if form.is_valid():
            form.save()
        return render(request, 'avatar_change.html', {'form': form})

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    # 建立帳號時 自動觸發
    if created:
        Token.objects.create(user=instance)
        UserProfile.objects.create(user=instance)
