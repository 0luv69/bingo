from django.contrib import admin
from django.urls import path
from game. views import (
    home_view,
    create_room_view,
    join_room_view,
    join_room_direct_view,
    lobby_view,
    game_view,
    leave_room_view,
    room_settings_view,
    kick_player_view,
    room_status_api,
    login_view,
    logout_view,
)

urlpatterns = [
    path('login/', login_view, name='login'),

    
    # Main pages
    path('', home_view, name='home'),
    path('create/', create_room_view, name='create_room'),
    path('join/', join_room_view, name='join_room'),
    path('join/<str:room_code>/', join_room_direct_view, name='join_room_direct'),

    path('logout/', logout_view, name='logout'),
    
    # Room pages
    path('room/<str:room_code>/lobby/', lobby_view, name='lobby'),
    path('room/<str:room_code>/game/', game_view, name='game'),
    path('room/<str:room_code>/leave/', leave_room_view, name='leave_room'),
    path('room/<str:room_code>/settings/', room_settings_view, name='room_settings'),
    path('room/<str:room_code>/kick/', kick_player_view, name='kick_player'),
    
    # API
    path('api/room/<str:room_code>/status/', room_status_api, name='room_status_api'),
]