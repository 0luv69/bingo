import random
import string
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class Room(models.Model):
    """
    Persistent room container that survives multiple game rounds.
    
    Room holds:
    - Unique code for joining
    - Settings (timeouts, max players)
    - Members (via RoomMember)
    - Game rounds (via GameRound)
    
    Room lifecycle:
    - Created when host creates room
    - Persists through multiple game rounds
    - Soft-deleted when all members leave (is_active=False)
    """
    
    code = models.CharField(max_length=6, unique=True, help_text="Unique room code (e.g., ABC123)")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_rooms', help_text="User who created room (null for guests)")
    is_active = models.BooleanField(default=True, help_text="False when room is abandoned")
    
    # Room Settings
    settings_setup_duration = models.IntegerField(default=60, help_text="Seconds for board arrangement phase")
    settings_turn_duration = models.IntegerField(default=20, help_text="Seconds per turn")
    settings_max_players = models.IntegerField(default=8, help_text="Maximum players allowed (2-15)")
    settings_show_score = models.BooleanField(default=False, help_text="Whether to show bingo score to players of others")
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Room {self.code}"
    
    @classmethod
    def generate_room_code(cls):
        """Generate unique 6-char room code:  3 letters + 3 digits."""
        while True:
            letters = ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ', k=3))
            digits = ''.join(random.choices('23456789', k=3))
            code = letters + digits
            if not cls.objects.filter(code=code).exists():
                return code
    
    def get_active_members(self):
        """Get all active members in this room."""
        return self.members.filter(is_active=True)
    
    def get_active_members_count(self):
        """Get count of active members."""
        return self.get_active_members().count()
    
    def get_host(self):
        """Get current host of the room."""
        return self.members.filter(is_active=True, role='host').first()
    
    def get_current_round(self):
        """Get the current (latest) game round."""
        return self.rounds.order_by('-round_number').first()
    
    def get_share_url(self):
        """Get shareable URL for this room."""
        return f"/join/{self.code}/"
    
    def can_join(self):
        """Check if new players can join this room."""
        if not self.is_active:
            return False, "Room is no longer active"
        
        current_round = self.get_current_round()
        if current_round and current_round.status not in ['waiting', 'finished']:
            return False, "Game in progress, please wait"
        
        if self.get_active_members_count() >= self.settings_max_players:
            return False, "Room is full"
        
        return True, "OK"
    
    def transfer_host(self, exclude_member=None):
        """Transfer host role to next available member."""
        query = self.members.filter(is_active=True, role='player')
        if exclude_member:
            query = query.exclude(id=exclude_member.id)
        
        # First try co-hosts
        co_host = self.members.filter(is_active=True, role='co-host').first()
        if co_host:
            co_host.role = 'host'
            co_host.save()
            return co_host
        
        # Then regular players
        new_host = query.order_by('joined_at').first()
        if new_host:
            new_host.role = 'host'
            new_host.save()
            return new_host
        
        return None


class RoomMember(models.Model):
    """
    Represents a person's membership in a room.
    Persists across game rounds.
    
    Identified by:
    - user (if logged in)
    - session_key (if guest)
    """
    
    ROLE_CHOICES = [
        ('host', 'Host'),
        ('co-host', 'Co-Host'),
        ('player', 'Player'),
    ]
    
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='room_memberships', help_text="Logged in user (null for guests)")
    session_key = models.CharField(max_length=40, blank=True, null=True, help_text="Browser session for guests")
    display_name = models.CharField(max_length=30, help_text="Player's display name")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='player')
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, help_text="False when member leaves room")
    
    class Meta:
        ordering = ['joined_at']
        constraints = [
            models.UniqueConstraint(fields=['room', 'session_key'], name='unique_room_session', condition=models.Q(session_key__isnull=False)),
            models.UniqueConstraint(fields=['room', 'user'], name='unique_room_user', condition=models.Q(user__isnull=False)),
        ]
    
    def __str__(self):
        return f"{self.display_name} in {self.room.code} ({self.role})"
    
    @property
    def is_host(self):
        return self.role == 'host'
    
    @property
    def is_co_host(self):
        return self.role == 'co-host'
    
    @property
    def show_score(self):
        return self.room.settings_show_score
    
    def get_identifier(self):
        """Get unique identifier for this member."""
        if self.user:
            return f"user_{self.user.id}"
        return f"session_{self.session_key}"
    
    def leave_room(self):
        """Handle member leaving the room."""
        was_host = self.is_host
        self.is_active = False
        self.save()
        
        if was_host:
            self.room.transfer_host(exclude_member=self)
        
        # Check if room should be deactivated
        if self.room.get_active_members_count() == 0:
            self.room.is_active = False
            self.room.save()


class GameRound(models.Model):
    """
    Represents a single game round within a room.
    
    A room can have multiple rounds (Play Again feature).
    Each round has its own: 
    - Status progression (waiting → setup → playing → finished)
    - Called numbers
    - Winner
    - Round players with their boards
    """
    
    STATUS_CHOICES = [
        ('waiting', 'Waiting for Players'),
        ('setup', 'Board Setup Phase'),
        ('playing', 'Game in Progress'),
        ('finished', 'Game Finished'),
    ]
    
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='rounds')
    round_number = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='waiting')
    called_numbers = models.JSONField(default=list, help_text="List of called numbers [5, 13, 21]")
    current_turn = models.ForeignKey('RoundPlayer', on_delete=models.SET_NULL, null=True, blank=True, related_name='current_turn_round', help_text="Whose turn is it")
    turn_deadline = models.DateTimeField(null=True, blank=True, help_text="When current turn/phase expires")
    winner = models.ForeignKey('RoundPlayer', on_delete=models.SET_NULL, null=True, blank=True, related_name='won_rounds')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-round_number']
        unique_together = ['room', 'round_number']
    
    def __str__(self):
        return f"Room {self.room.code} - Round {self.round_number} ({self.status})"
    
    def get_players(self):
        """Get all players in this round."""
        return self.players.all()
    
    def get_players_count(self):
        """Get number of players in this round."""
        return self.players.count()
    
    def get_ready_count(self):
        """Get number of ready players."""
        return self.players.filter(is_ready=True).count()
    
    def are_all_players_ready(self):
        """Check if all players are ready."""
        players = self.players.all()
        if not players.exists():
            return False
        return all(p.is_ready for p in players)
    
    def get_available_numbers(self):
        """Get numbers that haven't been called yet."""
        all_numbers = set(range(1, 26))
        called = set(self.called_numbers)
        return list(all_numbers - called)
    
    def get_next_turn_player(self):
        """Get next player in turn order."""
        players = list(self.players.order_by('turn_order'))
        if not players:
            return None
        
        if self.current_turn is None:
            return players[0]
        
        try:
            current_index = next(i for i, p in enumerate(players) if p.id == self.current_turn.id)
            next_index = (current_index + 1) % len(players)
            return players[next_index]
        except StopIteration:
            return players[0]
    
    def is_deadline_passed(self):
        """Check if current deadline has passed."""
        if self.turn_deadline is None:
            return False
        return timezone.now() > self.turn_deadline
    
    def add_called_number(self, number):
        """Add a number to called numbers list."""
        if number not in self.called_numbers:
            self.called_numbers.append(number)
            self.save(update_fields=['called_numbers'])
    
    def start_setup_phase(self):
        """Transition to setup phase."""
        self.status = 'setup'
        self.turn_deadline = timezone.now() + timedelta(seconds=self.room.settings_setup_duration)
        self.started_at = timezone.now()
        self.save()
    
    def start_playing_phase(self):
        """Transition to playing phase."""
        self.status = 'playing'
        
        # Set first turn
        first_player = self.players.order_by('joined_at').first()
        if first_player: 
            self.current_turn = first_player
            self.turn_deadline = timezone.now() + timedelta(seconds=self.room.settings_turn_duration)
        
        self.save()
    
    def end_game(self, winner):
        """End the game with a winner."""
        self.status = 'finished'
        self.winner = winner
        self.finished_at = timezone.now()
        self.turn_deadline = None
        self.save()
    
    @classmethod
    def create_new_round(cls, room):
        """Create a new round for the room."""
        last_round = room.rounds.order_by('-round_number').first()
        round_number = (last_round.round_number + 1) if last_round else 1
        
        return cls.objects.create(room=room, round_number=round_number)


class RoundPlayer(models.Model):
    """
    Represents a player's participation in a specific game round.
    
    Each round has its own set of RoundPlayer records.
    Stores round-specific data: 
    - Board arrangement
    - Ready status
    - Completed lines
    """
    
    game_round = models.ForeignKey(GameRound, on_delete=models.CASCADE, related_name='players')
    room_member = models.ForeignKey(RoomMember, on_delete=models.CASCADE, related_name='round_participations')
    board = models.JSONField(default=list, help_text="5x5 grid [[1,2,3,4,5], ...]")
    is_ready = models.BooleanField(default=False)
    finished_lines = models.JSONField(default=list, help_text="List of completed line indices from winning lines [0,1,5,8]") 
    turn_order = models.PositiveIntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)
    
    class Meta: 
        ordering = ['turn_order']
        unique_together = ['game_round', 'room_member']
    
    def __str__(self):
        return f"{self.room_member.display_name} in Round {self.game_round.round_number}"
    @property
    def completed_lines(self):
        return len(self.finished_lines)

    @property
    def display_name(self):
        return self.room_member.display_name
    
    @property
    def role(self):
        return self.room_member.role
    
    @property
    def is_host(self):
        return self.room_member.is_host
    
    @property
    def is_co_host(self):
        return self.room_member.is_co_host
    
    @property
    def show_score(self):
        return self.game_round.room.settings_show_score
    
    @staticmethod
    def generate_board():
        """Generate random 5x5 board with numbers 1-25."""
        numbers = list(range(1, 26))
        random.shuffle(numbers)
        return [numbers[i*5:(i+1)*5] for i in range(5)]
    
    def get_number_position(self, number):
        """Find position of number on board. Returns (row, col) or None."""
        for row_idx, row in enumerate(self.board):
            for col_idx, cell in enumerate(row):
                if cell == number:
                    return (row_idx, col_idx)
        return None
    
    def mark_ready(self):
        """Mark player as ready."""
        self.is_ready = True
        self.save(update_fields=['is_ready'])
    
    def update_board(self, new_board):
        """Update player's board arrangement."""
        self.board = new_board
        self.save(update_fields=['board'])


class CalledNumberHistory(models.Model):
    """
    Historical record of called numbers for analytics.
    Tracks who called what number and when.
    """
    
    game_round = models.ForeignKey(GameRound, on_delete=models.CASCADE, related_name='call_history')
    number = models.IntegerField(help_text="The number called (1-25)")
    called_by = models.ForeignKey(RoundPlayer, on_delete=models.CASCADE, related_name='calls_made')
    called_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['called_at']
        unique_together = ['game_round', 'number']
    
    def __str__(self):
        return f"#{self.number} by {self.called_by.display_name} in Round {self.game_round.round_number}"