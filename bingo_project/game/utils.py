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

def generate_winning_lines(size):
    """
    Generate all winning lines for an NxN board.
    
    Returns list of lines, where each line is a list of (row, col) tuples.
    Total lines = size rows + size columns + 2 diagonals = 2*size + 2
    """
    lines = []
    
    # Horizontal rows
    for row in range(size):
        lines.append([(row, col) for col in range(size)])
    
    # Vertical columns
    for col in range(size):
        lines.append([(row, col) for row in range(size)])
    
    # Diagonal:  top-left to bottom-right
    lines.append([(i, i) for i in range(size)])
    
    # Diagonal: top-right to bottom-left
    lines.append([(i, size - 1 - i) for i in range(size)])
    
    return lines


def generate_line_names(size):
    """Generate human-readable names for winning lines."""
    names = []
    
    # Rows
    for i in range(size):
        names.append(f"Row {i + 1}")
    
    # Columns
    for i in range(size):
        names.append(f"Column {i + 1}")
    
    # Diagonals
    names.append("Diagonal ↘")
    names.append("Diagonal ↙")
    
    return names


# def check_completed_lines(board, called_numbers, finished_lines):
#     """
#     Check how many lines are completed on a board.
    
#     Args:
#         board: 2D list (5x5) - Player's board
#         called_numbers: List of integers - Numbers that have been called
    
#     Returns:
#         tuple: (count, completed_lines_info)
#     """
#     called_set = set(called_numbers)
#     completed_lines_info = []
#     updated_finished_lines = finished_lines.copy()
    
#     for line_index, line in enumerate(WINNING_LINES):
#         if line_index in finished_lines:
#             continue  # Skip already finished lines


#         line_complete = all(board[row][col] in called_set for row, col in line)
        
#         if line_complete:
#             completed_lines_info.append({
#                 'index': line_index,
#                 'name': LINE_NAMES[line_index],
#                 'positions': line
#             })
#             updated_finished_lines.append(line_index)
    
#     return list(updated_finished_lines)

def check_completed_lines(board, called_numbers, finished_lines, board_size=5):
    """
    Check how many lines are completed on a board.
    
    Args:
        board: 2D list (NxN) - Player's board
        called_numbers: List of integers - Numbers that have been called
        finished_lines: List of already completed line indices
        board_size: Size of the board (5-10)
    
    Returns:
        list:  Updated finished_lines indices
    """
    winning_lines = generate_winning_lines(board_size)
    called_set = set(called_numbers)
    updated_finished_lines = finished_lines.copy()
    
    for line_index, line in enumerate(winning_lines):
        if line_index in finished_lines:
            continue
        
        line_complete = all(board[row][col] in called_set for row, col in line)
        
        if line_complete:
            updated_finished_lines.append(line_index)
    
    return updated_finished_lines

def determine_winners(game_round, calling_player):
    """
    Determine winner(s) after a number is called.
    Uses room's board_size setting for lines_to_win.
    """
    called_numbers = game_round.called_numbers
    board_size = game_round.room.settings_board_size
    lines_to_win = board_size  # Need N lines to win on NxN board
    
    # Check the caller
    updated_finished_lines = check_completed_lines(
        calling_player.board, 
        called_numbers, 
        calling_player.finished_lines,
        board_size
    )
    calling_player.finished_lines = updated_finished_lines
    calling_player.save(update_fields=['finished_lines'])
    
    if len(updated_finished_lines) >= lines_to_win:
        return [calling_player]
    
    # Check all other players
    winners = []
    for player in game_round.players.exclude(id=calling_player.id):
        updated_finished_lines = check_completed_lines(
            player.board, 
            called_numbers, 
            player. finished_lines,
            board_size
        )
        player.finished_lines = updated_finished_lines
        player.save(update_fields=['finished_lines'])
        
        if len(updated_finished_lines) >= lines_to_win:
            winners.append(player)
    
    return winners


def validate_board(board, expected_size=5):
    """
    Validate that board is a proper NxN grid with numbers 1 to N². 
    """
    if not isinstance(board, list) or len(board) != expected_size:
        return False
    
    total_numbers = expected_size * expected_size
    all_numbers = []
    
    for row in board:
        if not isinstance(row, list) or len(row) != expected_size:
            return False
        all_numbers.extend(row)
    
    return sorted(all_numbers) == list(range(1, total_numbers + 1))

def get_bingo_progress(completed_lines):
    """
    Convert completed lines count to BINGO letter progress.
    
    Args:
        completed_lines: Number of completed lines (0-5+)
    
    Returns:
        dict: {'B': True, 'I': True, 'N': False, 'G': False, 'O': False}
    """
    return {letter: i < completed_lines for i, letter in enumerate(BINGO_LETTERS)}


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
        return room.members.filter(user=user).first()
    elif session_key: 
        return room.members.filter(session_key=session_key).first()
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