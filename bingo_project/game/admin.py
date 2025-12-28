from django.contrib import admin
from django.utils. html import format_html
from django.utils.safestring import mark_safe
from . models import Room, RoomMember, GameRound, RoundPlayer, CalledNumberHistory


@admin.register(Room)
class RoomAdmin(admin. ModelAdmin):
    list_display = ['code', 'is_active_badge', 'visibility_type_display', 'members_count', 'rounds_count', 'settings_display', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['code']
    readonly_fields = ['code', 'created_at']
    
    fieldsets = (
        ('Room Info', {'fields': ('code', 'visibility_type', 'created_by', 'is_active', 'created_at')}),
        ('Settings', {'fields': ('settings_setup_duration', 'settings_turn_duration', 'settings_max_players')}),
    )
    
    def members_count(self, obj):
        active = obj.get_active_members_count()
        total = obj.members. count()
        return f"{active}/{total}"
    members_count.short_description = 'Members (Active/Total)'

    def visibility_type_display(self, obj):
        return obj.get_visibility_type()
    visibility_type_display.short_description = 'Visibility Type'
    
    def rounds_count(self, obj):
        return obj.rounds.count()
    rounds_count.short_description = 'Rounds'
    
    def is_active_badge(self, obj):
        if obj.is_active:
            return mark_safe('<span style="color: #10b981;">● Active</span>')
        return mark_safe('<span style="color: #ef4444;">● Inactive</span>')
    is_active_badge.short_description = 'Status'
    
    def settings_display(self, obj):
        return f"Setup: {obj.settings_setup_duration}s | Turn: {obj.settings_turn_duration}s | Max:  {obj.settings_max_players}"
    settings_display.short_description = 'Settings'


@admin.register(RoomMember)
class RoomMemberAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'room_code', 'role_badge', 'is_active_badge', 'status_badge', 'identifier_type', 'joined_at']
    list_filter = ['role', 'is_active', 'room']
    search_fields = ['display_name', 'room__code']
    readonly_fields = ['joined_at']
    
    def room_code(self, obj):
        return obj.room.code
    room_code.short_description = 'Room'
    
    def role_badge(self, obj):
        colors = {'host': '#f59e0b', 'co-host': '#3b82f6', 'player': '#6b7280'}
        color = colors.get(obj.role, '#6b7280')
        return format_html('<span style="color:  {};">{}</span>', color, obj.get_role_display())
    role_badge.short_description = 'Role'
    
    def is_active_badge(self, obj):
        if obj.is_active:
            return mark_safe('<span style="color: #10b981;">✅</span>')
        return mark_safe('<span style="color: #ef4444;">❌</span>')
    is_active_badge.short_description = 'Active'

    def status_badge(self, obj):
        colors = {'connected': '#10b981', 'disconnected': '#f59e0b', 'left': '#ef4444'}
        color = colors.get(obj.connection_status, '#6b7280')
        return format_html('<span style="color:  {};">{}</span>', color, obj.get_connection_status_display())
    status_badge.short_description = 'Status'
    
    def identifier_type(self, obj):
        if obj.user:
            return f"User:  {obj.user.username}"
        elif obj.session_key:  # ✅ Check if session_key exists
            return f"Session: {obj.session_key[: 8]}..."
        else:
            return "No identifier" 
    identifier_type.short_description = 'Identifier'


@admin.register(GameRound)
class GameRoundAdmin(admin.ModelAdmin):
    list_display = ['round_display', 'status_badge', 'players_count', 'called_count', 'current_turn_display', 'winner_display']
    list_filter = ['status', 'room']
    search_fields = ['room__code']
    readonly_fields = ['started_at', 'finished_at']
    
    def round_display(self, obj):
        return f"{obj.room.code} - R{obj. round_number}"
    round_display.short_description = 'Round'
    
    def status_badge(self, obj):
        colors = {'waiting': '#f59e0b', 'setup': '#3b82f6', 'playing': '#10b981', 'finished': '#6b7280'}
        color = colors.get(obj.status, '#6b7280')
        return format_html('<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 4px;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = 'Status'
    
    def players_count(self, obj):
        ready = obj.get_ready_count()
        total = obj.get_players_count()
        return f"{ready}/{total} ready"
    players_count. short_description = 'Players'
    
    def called_count(self, obj):
        return f"{len(obj.called_numbers)}/25"
    called_count.short_description = 'Called'
    
    def current_turn_display(self, obj):
        if obj.current_turn:
            return obj.current_turn.display_name
        return "-"
    current_turn_display.short_description = 'Turn'
    
    def winner_display(self, obj):
        if obj.winners.exists():
            winners = ", ".join([winner.display_name for winner in obj.winners.all()])
            return format_html('<span style="color:  #f59e0b;">🏆 {}</span>', winners)
        return "-"
    winner_display.short_description = 'Winner'


@admin.register(RoundPlayer)
class RoundPlayerAdmin(admin.ModelAdmin):
    list_display = ['player_display', 'round_display', 'room_member__connection_status', 'lines_progress', 'joined_at']
    list_filter = ['is_ready', 'game_round__room']
    search_fields = ['room_member__display_name', 'game_round__room__code']
    readonly_fields = ['joined_at', 'board_display']
    
    def player_display(self, obj):
        role_icon = {'host': '👑', 'co-host':  '⭐', 'player': ''}
        icon = role_icon.get(obj.role, '')
        return f"{icon} {obj.display_name}"
    player_display.short_description = 'Player'
    
    def round_display(self, obj):
        return f"{obj.game_round.room.code} - R{obj.game_round.round_number}"
    round_display. short_description = 'Round'
    
    def is_ready_badge(self, obj):
        if obj.is_ready:
            return mark_safe('<span style="color: #10b981;">✅ Ready</span>')
        return mark_safe('<span style="color: #f59e0b;">⏳ Waiting</span>')
    is_ready_badge. short_description = 'Ready'
    
    def lines_progress(self, obj):
        letters = 'BINGO'
        result = ''
        for i, letter in enumerate(letters):
            if i < obj.completed_lines:
                result += f'<span style="color: #10b981; font-weight: bold;">{letter}</span>'
            else: 
                result += f'<span style="color: #d1d5db;">{letter}</span>'
        return mark_safe(result)
    lines_progress.short_description = 'BINGO'
    
    def board_display(self, obj):
        if not obj.board:
            return "No board"
        
        called = set(obj. game_round.called_numbers)
        html = '<table style="border-collapse: collapse; font-family: monospace;">'
        for row in obj.board:
            html += '<tr>'
            for cell in row:
                bg = '#fbbf24' if cell in called else '#f3f4f6'
                html += f'<td style="border:  1px solid #ccc; padding: 8px; text-align: center; background-color: {bg}; min-width: 35px;">{cell}</td>'
            html += '</tr>'
        html += '</table>'
        return mark_safe(html)
    board_display.short_description = 'Board'


@admin.register(CalledNumberHistory)
class CalledNumberHistoryAdmin(admin.ModelAdmin):
    list_display = ['number', 'round_display', 'called_by_display', 'called_at']
    list_filter = ['game_round__room']
    search_fields = ['game_round__room__code']
    ordering = ['-called_at']
    
    def round_display(self, obj):
        return f"{obj.game_round.room.code} - R{obj.game_round.round_number}"
    round_display.short_description = 'Round'
    
    def called_by_display(self, obj):
        return obj.called_by.display_name
    called_by_display.short_description = 'Called By'