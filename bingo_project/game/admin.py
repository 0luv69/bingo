from django.contrib import admin
from .models import Room, Player, CalledNumber


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    """Admin interface for Room model."""
    
    list_display = ['code', 'status', 'get_players_count', 'current_turn', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['code']
    readonly_fields = ['created_at']
    
    def get_players_count(self, obj):
        return obj.get_players_count()
    get_players_count.short_description = 'Players'


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    """Admin interface for Player model."""
    
    list_display = ['name', 'room', 'is_host', 'is_ready', 'completed_lines', 'joined_at']
    list_filter = ['is_host', 'is_ready', 'room']
    search_fields = ['name', 'room__code']
    readonly_fields = ['joined_at', 'session_key']


@admin.register(CalledNumber)
class CalledNumberAdmin(admin.ModelAdmin):
    """Admin interface for CalledNumber model."""
    
    list_display = ['number', 'room', 'called_by', 'called_at']
    list_filter = ['room', 'called_at']
    search_fields = ['room__code', 'called_by__name']
    readonly_fields = ['called_at']