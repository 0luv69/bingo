from django.dispatch import receiver
from allauth.socialaccount.signals import pre_social_login

@receiver(pre_social_login)
def debug_social_login(sender, request, sociallogin, **kwargs):
    # inspect in console or your logs
    print("PROVIDER:", sociallogin.account.provider)
    print("EXTRA_DATA:", sociallogin.account.extra_data)
    print("USER EMAIL:", sociallogin.user.email)