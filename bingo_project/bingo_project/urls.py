from django.contrib import admin
from django.urls import path, include

from django.views.generic import RedirectView
from django.conf import settings

from game.views import login_view, logout_view, account_conflict_view, merge_accounts_view, cancel_merge_view


urlpatterns = [
    path('favicon.ico', RedirectView.as_view(url=settings.STATIC_URL + 'favicon.ico')),
    path('admin/', admin.site.urls),

    path('accounts/login/', login_view, name='login'),
    path('accounts/signup/', login_view, name='login'),
    path('accounts/logout/', logout_view, name='logout'),


    path(
        'account-conflict/', 
        account_conflict_view, 
        name='account_conflict'
    ),
    path(
        'merge-accounts/', 
        merge_accounts_view, 
        name='merge_accounts'
    ),
    path(
        'cancel-merge/', 
        cancel_merge_view, 
        name='cancel_merge'
    ),


    path('accounts/', include('allauth.urls')), 

    path('', include('game.urls')),   
]
