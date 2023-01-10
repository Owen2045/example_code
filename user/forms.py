from django import forms
from django.core.files.images import get_image_dimensions

from user.models import UserProfile
from allauth.account.adapter import DefaultAccountAdapter

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('avatar', )

    def clean_avatar(self):
        avatar = self.cleaned_data['avatar']
        if avatar:
            w, h = get_image_dimensions(avatar)

            #validate dimensions
            max_width = max_height = 500
            if w > max_width or h > max_height:
                raise forms.ValidationError(u'圖片解析度請小於 %s x %s' % (max_width, max_height))

            #validate content type
            main, sub = avatar.content_type.split('/')
            if not (main == 'image' and sub in ['jpeg', 'pjpeg', 'gif', 'png']):
                raise forms.ValidationError(u'請使用 JPEG, GIF, PNG 圖片格式')

            #validate file size
            if len(avatar) > (1 * 1024 * 1024):
                raise forms.ValidationError(u'頭像請小於1MB')
        return avatar

class NoNewUsersAccountAdapter(DefaultAccountAdapter):

    def is_open_for_signup(self, request):
        """
        Checks whether or not the site is open for signups.

        Next to simply returning True/False you can also intervene the
        regular flow by raising an ImmediateHttpResponse

        (Comment reproduced from the overridden method.)
        """
        return False