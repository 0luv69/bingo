from django.urls import path
from . import views
from game.views import (
    home_view,
    create_room_view,
    join_room_view,
    lobby_view,
    game_view,
    leave_room_view,
    room_status_api,
)

urlpatterns = [
    # Main pages
    path('', home_view, name='home'),
    path('create/', create_room_view, name='create_room'),
    path('join/', join_room_view, name='join_room'),
    
    # Room pages
    path('room/<str:room_code>/lobby/', lobby_view, name='lobby'),
    path('room/<str:room_code>/game/', game_view, name='game'),
    path('room/<str:room_code>/leave/', leave_room_view, name='leave_room'),
    
    # API endpoints
    path('api/room/<str:room_code>/status/', room_status_api, name='room_status_api'),
]
