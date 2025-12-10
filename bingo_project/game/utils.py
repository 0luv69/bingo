"""
Utility functions for Bingo game logic. 

Contains:
- Pre-computed winning line patterns
- Line completion checking
- Winner determination
"""

from .models import RoundPlayer

# ============================================
# PRE-COMPUTED WINNING LINES (Constant)
# ============================================
#
# Total:  12 lines (5 rows + 5 columns + 2 diagonals)
#
# Board positions:
#   (0,0) (0,1) (0,2) (0,3) (0,4)
#   (1,0) (1,1) (1,2) (1,3) (1,4)
#   (2,0) (2,1) (2,2) (2,3) (2,4)
#   (3,0) (3,1) (3,2) (3,3) (3,4)
#   (4,0) (4,1) (4,2) (4,3) (4,4)

WINNING_LINES = [
    # Horizontal rows (5)
    [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)],  # Row 0
    [(1, 0), (1, 1), (1, 2), (1, 3), (1, 4)],  # Row 1
    [(2, 0), (2, 1), (2, 2), (2, 3), (2, 4)],  # Row 2
    [(3, 0), (3, 1), (3, 2), (3, 3), (3, 4)],  # Row 3
    [(4, 0), (4, 1), (4, 2), (4, 3), (4, 4)],  # Row 4
    
    # Vertical columns (5)
    [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)],  # Column 0
    [(0, 1), (1, 1), (2, 1), (3, 1), (4, 1)],  # Column 1
    [(0, 2), (1, 2), (2, 2), (3, 2), (4, 2)],  # Column 2
    [(0, 3), (1, 3), (2, 3), (3, 3), (4, 3)],  # Column 3
    [(0, 4), (1, 4), (2, 4), (3, 4), (4, 4)],  # Column 4
    
    # Diagonals (2)
    [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)],  # Top-left to bottom-right
    [(0, 4), (1, 3), (2, 2), (3, 1), (4, 0)],  # Top-right to bottom-left
]

LINE_NAMES = [
    "Row 1", "Row 2", "Row 3", "Row 4", "Row 5",
    "Column 1", "Column 2", "Column 3", "Column 4", "Column 5",
    "Diagonal ↘", "Diagonal ↙"
]

BINGO_LETTERS = ['B', 'I', 'N', 'G', 'O']


def check_completed_lines(board, called_numbers):
    """
    Check how many lines are completed on a board.
    
    Args:
        board: 2D list (5x5) - Player's board
        called_numbers: List of integers - Numbers that have been called
    
    Returns:
        tuple: (count, completed_lines_info)
    """
    called_set = set(called_numbers)
    completed_lines_info = []
    
    for line_index, line in enumerate(WINNING_LINES):
        line_complete = all(board[row][col] in called_set for row, col in line)
        
        if line_complete:
            completed_lines_info.append({
                'index': line_index,
                'name': LINE_NAMES[line_index],
                'positions': line
            })
    
    return len(completed_lines_info), completed_lines_info


def determine_winners(game_round, calling_player):
    """
    Determine winner(s) after a number is called.
    
    Rules:
    1. If caller completes 5+ lines, caller wins alone
    2. If caller doesn't win, check others
    3. Multiple non-callers can tie for win
    
    Args:
        game_round: GameRound instance
        calling_player: RoundPlayer who called the number
    
    Returns:
        list: List of winning RoundPlayer instances (empty if no winner)
    """
    called_numbers = game_round.called_numbers
    lines_to_win = 1
    
    # First check the caller
    caller_lines, _ = check_completed_lines(calling_player.board, called_numbers)
    calling_player.completed_lines = caller_lines
    calling_player.save(update_fields=['completed_lines'])
    
    if caller_lines >= lines_to_win:
        return [calling_player]  # Caller wins alone
    
    # Check all other players
    winners = []
    for player in game_round.players.exclude(id=calling_player.id):
        player_lines, _ = check_completed_lines(player.board, called_numbers)
        player.completed_lines = player_lines
        player.save(update_fields=['completed_lines'])
        
        if player_lines >= lines_to_win:
            winners.append(player)
    
    return winners


def update_all_players_lines(game_round):
    """
    Update completed lines for all players in a round. 
    Called after each number is called.
    
    Returns:
        list: List of dicts with player line updates
    """
    called_numbers = game_round.called_numbers
    updates = []
    
    for player in game_round.players.all():
        old_lines = player.completed_lines
        new_lines, completed = check_completed_lines(player.board, called_numbers)
        
        if new_lines != old_lines: 
            player.completed_lines = new_lines
            player.save(update_fields=['completed_lines'])
            
            updates.append({
                'player_id': player.id,
                'player_name': player.display_name,
                'old_lines':  old_lines,
                'new_lines': new_lines,
                'completed_line_names': [c['name'] for c in completed[old_lines: ]]
            })
    
    return updates


def get_bingo_progress(completed_lines):
    """
    Convert completed lines count to BINGO letter progress.
    
    Args:
        completed_lines: Number of completed lines (0-5+)
    
    Returns:
        dict: {'B': True, 'I': True, 'N': False, 'G': False, 'O': False}
    """
    return {letter: i < completed_lines for i, letter in enumerate(BINGO_LETTERS)}


def validate_board(board):
    """
    Validate that board is a proper 5x5 grid with numbers 1-25.
    
    Returns:
        bool: True if valid
    """
    if not isinstance(board, list) or len(board) != 5:
        return False
    
    all_numbers = []
    for row in board: 
        if not isinstance(row, list) or len(row) != 5:
            return False
        all_numbers.extend(row)
    
    return sorted(all_numbers) == list(range(1, 26))


def get_room_member(room, user=None, session_key=None):
    """
    Get RoomMember by user or session_key.
    
    Args:
        room: Room instance
        user: User instance (optional)
        session_key: Session key string (optional)
    
    Returns:
        RoomMember or None
    """
    if user and user.is_authenticated:
        return room.members.filter(user=user, is_active=True).first()
    elif session_key: 
        return room.members.filter(session_key=session_key, is_active=True).first()
    return None


def get_or_create_room_member(room, display_name, user=None, session_key=None, is_host=False):
    """
    Get existing room member or create new one.
    
    Returns:
        tuple: (RoomMember, created:  bool)
    """
    # Try to find existing member
    existing = get_room_member(room, user, session_key)
    if existing:
        # Reactivate if inactive
        if not existing.is_active:
            existing.is_active = True
            existing.display_name = display_name
            existing.save()
        return existing, False
    
    # Create new member
    role = 'host' if is_host else 'player'
    member = room.members.create(
        user=user if user and user.is_authenticated else None,
        session_key=session_key if not (user and user.is_authenticated) else None,
        display_name=display_name,
        role=role
    )
    return member, True


def get_or_create_round_player(game_round, room_member):
    """
    Get existing round player or create new one with generated board.
    
    Returns:
        tuple: (RoundPlayer, created:  bool)
    """
    existing = game_round.players.filter(room_member=room_member).first()
    if existing:
        return existing, False
    
    player = game_round.players.create(
        room_member=room_member,
        board=RoundPlayer.generate_board()
    )
    return player, True