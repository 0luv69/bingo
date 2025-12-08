from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from .models import Room, Player


def home_view(request):
    """
    Landing page - Create or Join a room.
    
    GET: Display the home page with create/join forms
    """
    return render(request, 'game/home.html')


def create_room_view(request):
    """
    Create a new room and join as host.
    
    POST: Create room, create player as host, redirect to lobby
    
    Flow:
    1. Validate player name
    2.Generate unique room code
    3.Create room in database
    4.Create player as host with generated board
    5.Store player info in session
    6.Redirect to lobby
    """
    if request.method != 'POST':
        return redirect('home')
    
    # Get player name from form
    player_name = request.POST.get('player_name', '').strip()
    
    if not player_name:
        messages.error(request, 'Please enter your name.')
        return redirect('home')
    
    if len(player_name) > 30:
        messages.error(request, 'Name must be 30 characters or less.')
        return redirect('home')
    
    # Ensure session exists
    if not request.session.session_key:
        request.session.create()
    
    # Create the room
    room = Room.objects.create(code=Room.generate_room_code())
    
    # Create the player as host
    player = Player.objects.create(
        room=room,
        name=player_name,
        session_key=request.session.session_key,
        board=Player.generate_initial_board(),
        is_host=True
    )
    
    # Store current room and player in session for easy access
    request.session['current_room_code'] = room.code
    request.session['current_player_id'] = player.id
    
    messages.success(request, f'Room {room.code} created!  Share this code with friends.')
    return redirect('lobby', room_code=room.code)


def join_room_view(request):
    """
    Join an existing room.
    
    POST: Find room, create player, redirect to lobby
    
    Flow:
    1. Validate player name and room code
    2.Find existing room
    3.Check room is joinable (waiting status)
    4.Check player not already in room
    5.Create player with generated board
    6.Store player info in session
    7.Redirect to lobby
    """
    if request.method != 'POST':
        return redirect('home')
    
    player_name = request.POST.get('player_name', '').strip()
    room_code = request.POST.get('room_code', '').strip().upper()
    
    # Validate inputs
    if not player_name:
        messages.error(request, 'Please enter your name.')
        return redirect('home')
    
    if len(player_name) > 30:
        messages.error(request, 'Name must be 30 characters or less.')
        return redirect('home')
    
    if not room_code:
        messages.error(request, 'Please enter a room code.')
        return redirect('home')
    
    # Find the room
    try:
        room = Room.objects.get(code=room_code)
    except Room.DoesNotExist:
        messages.error(request, f'Room {room_code} not found.')
        return redirect('home')
    
    # Check room status
    if room.status != 'waiting':
        messages.error(request, 'This room is no longer accepting players.')
        return redirect('home')
    
    # Ensure session exists
    if not request.session.session_key:
        request.session.create()
    
    # Check if player already in this room
    existing_player = Player.objects.filter(
        room=room,
        session_key=request.session.session_key
    ).first()
    
    if existing_player:
        # Player already in room, just redirect to lobby
        request.session['current_room_code'] = room.code
        request.session['current_player_id'] = existing_player.id
        return redirect('lobby', room_code=room.code)
    
    # Create new player
    player = Player.objects.create(
        room=room,
        name=player_name,
        session_key=request.session.session_key,
        board=Player.generate_initial_board()
    )
    
    # Store in session
    request.session['current_room_code'] = room.code
    request.session['current_player_id'] = player.id
    
    messages.success(request, f'Joined room {room.code}!')
    return redirect('lobby', room_code=room.code)


def lobby_view(request, room_code):
    """
    Waiting room before game starts.
    
    GET: Display lobby with player list and room info
    
    Features:
    - Show room code (for sharing)
    - Show all players and their ready status
    - Host can start game when all ready
    - Real-time updates via WebSocket
    """
    room = get_object_or_404(Room, code=room_code)
    
    # Get current player
    player_id = request.session.get('current_player_id')
    current_player = None
    
    if player_id:
        current_player = Player.objects.filter(id=player_id, room=room).first()
    
    # If player not in this room, redirect to home
    if not current_player:
        messages.error(request, 'You are not in this room.')
        return redirect('home')
    
    # If game already started, redirect to game page
    if room.status in ['setup', 'playing']:
        return redirect('game', room_code=room.code)
    
    # If game finished, show message
    if room.status == 'finished':
        messages.info(request, 'This game has ended.')
        return redirect('home')
    
    context = {
        'room': room,
        'players': room.get_players(),
        'current_player': current_player,
        'is_host': current_player.is_host,
    }
    
    return render(request, 'game/lobby.html', context)


def game_view(request, room_code):
    """
    Main game board page.
    
    GET: Display game board with all game info
    
    Phases handled:
    - SETUP: Show board with drag/drop, timer, ready button
    - PLAYING: Show board, turn info, number buttons
    - FINISHED: Show winner announcement
    """
    room = get_object_or_404(Room, code=room_code)
    
    # Get current player
    player_id = request.session.get('current_player_id')
    current_player = None
    
    if player_id:
        current_player = Player.objects.filter(id=player_id, room=room).first()
    
    # If player not in this room, redirect to home
    if not current_player:
        messages.error(request, 'You are not in this room.')
        return redirect('home')
    
    # If still waiting, redirect to lobby
    if room.status == 'waiting':
        return redirect('lobby', room_code=room.code)
    
    # Get all players for scoreboard
    players = room.get_players()
    
    # Determine if it's current player's turn
    is_my_turn = (room.current_turn == current_player) if room.current_turn else False
    
    # Get available numbers (not yet called)
    available_numbers = room.get_available_numbers()
    
    # Calculate remaining time if deadline exists
    remaining_seconds = 0
    if room.turn_deadline:
        delta = room.turn_deadline - timezone.now()
        remaining_seconds = max(0, int(delta.total_seconds()))
    
    context = {
        'room': room,
        'current_player': current_player,
        'players': players,
        'is_my_turn': is_my_turn,
        'available_numbers': available_numbers,
        'called_numbers': room.called_numbers,
        'remaining_seconds': remaining_seconds,
    }
    
    return render(request, 'game/game.html', context)


def leave_room_view(request, room_code):
    """
    Leave the current room.
    
    POST: Remove player from room, handle host transfer
    
    Logic:
    - Remove player from room
    - If host leaves, transfer to next player
    - If last player leaves, delete room
    - Clear session data
    """
    if request.method != 'POST':
        return redirect('home')
    
    room = get_object_or_404(Room, code=room_code)
    
    player_id = request.session.get('current_player_id')
    if not player_id:
        return redirect('home')
    
    player = Player.objects.filter(id=player_id, room=room).first()
    if not player:
        return redirect('home')
    
    was_host = player.is_host
    player_name = player.name
    
    # Delete the player
    player.delete()
    
    # Clear session
    request.session.pop('current_room_code', None)
    request.session.pop('current_player_id', None)
    
    # Check remaining players
    remaining_players = room.get_players()
    
    if not remaining_players.exists():
        # No players left, delete room
        room.delete()
        messages.info(request, 'You left the room. Room was deleted (no players remaining).')
    elif was_host:
        # Transfer host to next player
        new_host = remaining_players.first()
        new_host.is_host = True
        new_host.save()
        messages.info(request, f'You left the room.{new_host.name} is now the host.')
    else:
        messages.info(request, 'You left the room.')
    
    return redirect('home')


# ============================================
# API Views (for AJAX requests if needed)
# ============================================

def room_status_api(request, room_code):
    """
    API endpoint to get current room status.
    Useful for polling if WebSocket isn't available.
    
    GET: Return room status as JSON
    """
    room = get_object_or_404(Room, code=room_code)
    
    players_data = []
    for player in room.get_players():
        players_data.append({
            'id': player.id,
            'name': player.name,
            'is_host': player.is_host,
            'is_ready': player.is_ready,
            'completed_lines': player.completed_lines,
        })
    
    data = {
        'code': room.code,
        'status': room.status,
        'current_turn_id': room.current_turn.id if room.current_turn else None,
        'called_numbers': room.called_numbers,
        'players': players_data,
    }
    
    return JsonResponse(data)