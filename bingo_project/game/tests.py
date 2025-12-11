
def check_completed_lines(board, called_numbers, finished_lines):
    """
    Check how many lines are completed on a board.
    
    Args:
        board: 2D list (5x5) - Player's board
        called_numbers: List of integers - Numbers that have been called
    
    Returns:
        tuple: (count, completed_lines_info)

        eck_completed_lines() missing 1 required positional argument: 'finished_lines'
    """
    called_set = set(called_numbers)
    new_lines_info = []
    updated_finished_lines = finished_lines.copy()
    
    for line_index, line in enumerate(WINNING_LINES):
        if line_index in finished_lines:
            continue  # Skip already finished lines


        line_complete = all(board[row][col] in called_set for row, col in line)
        
        if line_complete:
            new_lines_info.append({
                'index': line_index,
                'name': LINE_NAMES[line_index],
                'positions': line
            })
            updated_finished_lines.append(line_index)
    
    return len(new_lines_info), new_lines_info, list(updated_finished_lines)


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
    lines_to_win = 5
    
    # First check the caller
    completed_lines, new_lines_info , updated_finished_lines = check_completed_lines(calling_player.board, called_numbers, calling_player.finished_lines  )
    calling_player.completed_lines = completed_lines
    calling_player.finished_lines = updated_finished_lines
    calling_player.save(update_fields=['completed_lines', 'finished_lines'])
    
    if completed_lines >= lines_to_win:
        return [calling_player]  # Caller wins alone
    
    # Check all other players
    winners = []
    for player in game_round.players.exclude(id=calling_player.id):
        completed_lines, new_lines_info , updated_finished_lines = check_completed_lines(player.board, called_numbers, player.finished_lines)
        player.completed_lines = completed_lines
        player.finished_lines = updated_finished_lines
        player.save(update_fields=['completed_lines', 'finished_lines'])
        
        if completed_lines >= lines_to_win:
            winners.append(player)
    
    return winners


