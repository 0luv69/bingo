"""
Utility functions for Bingo game logic. 

Contains:
- Pre-computed winning line patterns
- Line completion checking
- Winner determination
"""

# ============================================
# PRE-COMPUTED WINNING LINES (Constant)
# ============================================
# 
# These never change, so we compute once and reuse. 
# Total: 12 lines (5 rows + 5 columns + 2 diagonals)
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
    [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)],  # Top-left to bottom-right ↘
    [(0, 4), (1, 3), (2, 2), (3, 1), (4, 0)],  # Top-right to bottom-left ↙
]

# Human-readable names for each line (same order as WINNING_LINES)
LINE_NAMES = [
    "Row 1", "Row 2", "Row 3", "Row 4", "Row 5",
    "Column 1", "Column 2", "Column 3", "Column 4", "Column 5",
    "Diagonal ↘", "Diagonal ↙"
]


def check_completed_lines(board, called_numbers):
    """
    Check how many lines are completed on a board.
    
    Args:
        board: 2D list (5x5) - Player's board
        called_numbers: List of integers - Numbers that have been called
    
    Returns:
        tuple: (count, completed_lines_info)
            - count: Number of completed lines (0-12)
            - completed_lines_info: List of dicts with line details
    
    Example:
        >>> board = [[1,2,3,4,5], [6,7,8,9,10], ...]
        >>> called = [1, 2, 3, 4, 5]
        >>> count, lines = check_completed_lines(board, called)
        >>> count
        1
        >>> lines
        [{'index': 0, 'name': 'Row 1', 'positions': [(0,0), (0,1), ... ]}]
    """
    called_set = set(called_numbers)  # Convert to set for O(1) lookup
    completed_lines_info = []
    
    for line_index, line in enumerate(WINNING_LINES):
        # Check if all 5 cells in this line are marked
        line_complete = True
        for (row, col) in line:
            number = board[row][col]
            if number not in called_set:
                line_complete = False
                break
        
        if line_complete:
            completed_lines_info. append({
                'index': line_index,
                'name': LINE_NAMES[line_index],
                'positions': line
            })
    
    return len(completed_lines_info), completed_lines_info


def get_completed_line_positions(board, called_numbers):
    """
    Get all cell positions that are part of completed lines.
    Useful for highlighting completed lines in UI.
    
    Args:
        board: 2D list (5x5)
        called_numbers: List of called numbers
    
    Returns:
        set: Set of (row, col) tuples that are part of completed lines
    
    Example:
        >>> positions = get_completed_line_positions(board, called)
        >>> (0, 0) in positions  # Is cell (0,0) part of a completed line?
        True
    """
    _, completed_lines = check_completed_lines(board, called_numbers)
    
    positions = set()
    for line_info in completed_lines:
        for pos in line_info['positions']:
            positions.add(pos)
    
    return positions


def is_winner(board, called_numbers, lines_to_win=5):
    """
    Check if a player has won the game.
    
    Args:
        board: Player's 5x5 board
        called_numbers: List of called numbers
        lines_to_win: Lines needed to win (default: 5)
    
    Returns:
        bool: True if player has won
    """
    count, _ = check_completed_lines(board, called_numbers)
    return count >= lines_to_win


def get_line_name(line_index):
    """
    Get human-readable name for a line by index.
    
    Args:
        line_index: Index of line (0-11)
    
    Returns:
        str: Name like "Row 1", "Column 3", "Diagonal ↘"
    """
    if 0 <= line_index < len(LINE_NAMES):
        return LINE_NAMES[line_index]
    return "Unknown"


def calculate_player_lines(player):
    """
    Calculate and update completed lines for a player.
    
    Args:
        player: Player model instance
    
    Returns:
        tuple: (new_line_count, newly_completed_lines)
    """
    count, completed_lines = check_completed_lines(
        player.board, 
        player.room.called_numbers
    )
    
    old_count = player.completed_lines
    newly_completed = completed_lines[old_count:] if count > old_count else []
    
    # Update player's completed lines count
    if count != old_count:
        player. completed_lines = count
        player.save(update_fields=['completed_lines'])
    
    return count, newly_completed


def get_board_as_dict(board):
    """
    Convert 2D board array to dictionary for easy number lookup.
    
    Args:
        board: 2D list (5x5)
    
    Returns:
        dict: {number: (row, col)} mapping
    
    Example:
        >>> board = [[7, 12, 3, ... ], ...]
        >>> mapping = get_board_as_dict(board)
        >>> mapping[7]
        (0, 0)
    """
    mapping = {}
    for row_idx, row in enumerate(board):
        for col_idx, number in enumerate(row):
            mapping[number] = (row_idx, col_idx)
    return mapping

