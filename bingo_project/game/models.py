import random
import string
from django.db import models
from django.utils import timezone


class Room(models.Model):
   
    STATUS_CHOICES = [
        ('waiting', 'Waiting for Players'),
        ('setup', 'Board Setup Phase'),
        ('playing', 'Game in Progress'),
        ('finished', 'Game Finished'),
    ]
    
    code = models.CharField(max_length=6, unique=True, help_text="Unique room code for joining (e.g., ABC123)")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='waiting', help_text="Current state of the game")
    called_numbers = models.JSONField(default=list, help_text="List of numbers called in the game: [5, 13, 21]")

    current_turn = models.ForeignKey('Player', on_delete=models.SET_NULL, null=True, blank=True, related_name='turn_in_room', help_text="Which player's turn is it?")
    turn_deadline = models.DateTimeField(null=True, blank=True, help_text="Deadline for current phase/turn")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Room {self.code} ({self.status})"
    
    @classmethod
    def generate_room_code(cls):
        """
        Generate a unique 6-character room code.
        Format: 3 uppercase letters + 3 digits (e.g., ABC123)
        """
        while True:
            letters = ''.join(random.choices(string.ascii_uppercase, k=3))
            digits = ''.join(random.choices(string.digits, k=3))
            code = letters + digits
            if not cls.objects.filter(code=code).exists():
                return code
    
    def get_players(self):
        """Get all players in this room."""
        return self.players.all()
    
    def get_players_count(self):
        """Get number of players in room."""
        return self.players.count()
    
    def are_all_players_ready(self):
        """Check if all players have clicked Ready."""
        players = self.players.all()
        if not players.exists():
            return False
        return all(player.is_ready for player in players)
    
    def get_next_turn_player(self):
        """Get the next player in turn order (based on join order)."""
        players = list(self.players.order_by('joined_at'))
        if not players:
            return None
        
        if self.current_turn is None:
            return players[0]
        
        try:
            current_index = players.index(self.current_turn)
            next_index = (current_index + 1) % len(players)
            return players[next_index]
        except ValueError:
            return players[0]
    
    def get_available_numbers(self):
        """Get list of numbers that haven't been called yet."""
        all_numbers = set(range(1, 26))
        called = set(self.called_numbers)
        return list(all_numbers - called)
    
    def is_deadline_passed(self):
        """Check if the current deadline has passed."""
        if self.turn_deadline is None:
            return False
        return timezone.now() > self.turn_deadline


class Player(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='players', help_text="The room this player is in")
    name = models.CharField(max_length=30, help_text="Player's display name")
    session_key = models.CharField(max_length=40, help_text="Browser session key to identify player")
    board = models.JSONField(default=list, help_text="5x5 grid as 2D array: [[1,2,3,4,5], ...]")
    is_ready = models.BooleanField(default=False, help_text="Has player clicked Ready in setup phase?")
    is_host = models.BooleanField(default=False, help_text="Did this player create the room?")
    completed_lines = models.IntegerField(default=0, help_text="Number of Bingo lines completed (5 to win)")
    joined_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['joined_at']
        unique_together = ['room', 'session_key']
    
    def __str__(self):
        return f"{self.name} in Room {self.room.code}"
    
    @staticmethod
    def generate_initial_board():
        """
        Generate a random 5x5 board with numbers 1-25.
        
        Returns:
            2D list: [[7, 12, 3, 21, 5], [18, 1, 14, 9, 22], ...]
        """
        numbers = list(range(1, 26))
        random.shuffle(numbers)
        
        board = []
        for i in range(5):
            row = numbers[i * 5:(i + 1) * 5]
            board.append(row)
        
        return board
    
    def get_number_position(self, number):
        """Find position of a number on board. Returns (row, col) or None."""
        for row_idx, row in enumerate(self.board):
            for col_idx, cell in enumerate(row):
                if cell == number:
                    return (row_idx, col_idx)
        return None
    
    def is_number_marked(self, number):
        """Check if a number has been called in this game."""
        return number in self.room.called_numbers


class CalledNumber(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='called_numbers_history', help_text="The room where this number was called")
    number = models.IntegerField(help_text="The number that was called (1-25)")
    called_by = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='numbers_called', help_text="The player who called this number")
    called_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['called_at']
        unique_together = ['room', 'number']
    
    def __str__(self):
        return f"Number {self.number} by {self.called_by.name} in Room {self.room.code}"