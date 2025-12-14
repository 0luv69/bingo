from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from .models import Room, RoomMember, GameRound, RoundPlayer
from .utils import get_room_member, get_or_create_room_member, get_or_create_round_player
from django.contrib.auth import login
from allauth.socialaccount.models import SocialLogin, SocialAccount
from django.contrib.auth import get_user_model


User = get_user_model()



def home_view(request):
    """
    Landing page - Create or Join a room.
    """
    return render(request,'game/home.html')

def logout_view(request):
    """
    Logout view.Clears session and redirects to home.
    """
    # Clear session
    request.session.flush()
    messages.warning(request, 'You have been logged out.')
    return redirect('home')

def login_view(request):
    """
    Login page view.
    If user is already authenticated, redirect to home.
    """
    if request.user.is_authenticated:
        return redirect('home')
    
    # Get the 'next' parameter for redirect after login
    next_url = request.GET.get('next', '/')
    
    return render(request, 'login.html', {
        'next':  next_url,
    })



from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from allauth.socialaccount.models import SocialLogin, SocialAccount
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

User = get_user_model()


def account_conflict_view(request):
    """
    Display the account conflict resolution page.
    
    Shows options to either: 
    1.Merge the new social account with the existing account
    2.Login with the existing account's provider
    """
    # Check if we have conflict data in session
    sociallogin_data = request.session.get('socialaccount_sociallogin')
    conflict_email = request.session.get('conflict_email')
    existing_providers = request.session.get('existing_providers', [])
    
    if not sociallogin_data or not conflict_email:
        messages.error(request, "No account conflict to resolve.")
        return redirect('home')

    # Deserialize the sociallogin to get provider info
    sociallogin = SocialLogin.deserialize(sociallogin_data)
    new_provider = sociallogin.account.provider

    context = {
        'conflict_email': conflict_email,
        'new_provider': new_provider,
        'new_provider_display': new_provider.title(),
        'existing_providers':  existing_providers,
        'existing_providers_display': [p.title() for p in existing_providers],
    }
    
    return render(request, 'accounts/account_conflict.html', context)


@require_http_methods(["POST"])
def merge_accounts_view(request):
    """
    Handle the account merge action.
    
    This connects the new social account to the existing user account.
    The user must confirm they own the existing account (we verify via email match).
    """
    sociallogin_data = request.session.get('socialaccount_sociallogin')
    conflicting_user_id = request.session.get('conflicting_user_id')
    
    if not sociallogin_data or not conflicting_user_id:
        messages.error(request, "Session expired.Please try signing in again.")
        return redirect('home')

    try:
        # Get the existing user
        existing_user = User.objects.get(pk=conflicting_user_id)
        
        # Deserialize the social login
        sociallogin = SocialLogin.deserialize(sociallogin_data)
        
        # Connect the social account to the existing user
        sociallogin.connect(request, existing_user)
        
        # Log the user in
        login(request, existing_user, backend='allauth.account.auth_backends.AuthenticationBackend')
        
        # Clear the session data
        _clear_conflict_session(request)
        
        messages.success(
            request, 
            f"Success! Your {sociallogin.account.provider.title()} account has been "
            f"linked to your existing account."
        )
        return redirect('dashboard')  # Change to your desired redirect

    except User.DoesNotExist:
        messages.error(request, "User not found.Please try again.")
        _clear_conflict_session(request)
        return redirect('home')
    except Exception as e:
        messages.error(request, f"An error occurred: {str(e)}")
        _clear_conflict_session(request)
        return redirect('home')


def cancel_merge_view(request):
    """Cancel the merge operation and clear session data."""
    _clear_conflict_session(request)
    messages.info(request, "Account linking cancelled.")
    return redirect('home')


def _clear_conflict_session(request):
    """Helper to clear all conflict-related session data."""
    keys_to_clear = [
        'socialaccount_sociallogin',
        'conflicting_user_id', 
        'conflict_email',
        'existing_providers'
    ]
    for key in keys_to_clear: 
        request.session.pop(key, None)











def create_room_view(request):
    """
    Create a new room and join as host.
    
    POST: Create room, create member as host, create first round, redirect to lobby
    """
    if request.method != 'POST':
        return redirect('home')
    
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
    
    # Create room
    room = Room.objects.create(code=Room.generate_room_code())
    
    # Create room member as host
    user = request.user if request.user.is_authenticated else None
    member = RoomMember.objects.create(
        room=room,
        user=user,
        session_key=request.session.session_key if not user else None,
        display_name=player_name,
        role='host'
    )
    
    # Create first game round
    game_round = GameRound.create_new_round(room)
    
    # Create round player
    RoundPlayer.objects.create(
        game_round=game_round,
        room_member=member,
        board=RoundPlayer.generate_board()
    )
    
    # Store in session
    request.session['current_room_code'] = room.code
    request.session['current_member_id'] = member.id
    
    messages.success(request, f'Room {room.code} created!  Share this code with friends.')
    return redirect('lobby', room_code=room.code)


def join_room_view(request):
    """
    Join an existing room.
    
    POST: Find room, create member, redirect to lobby
    """
    if request.method != 'POST':
        return redirect('home')
    
    player_name = request.POST.get('player_name', '').strip()
    room_code = request.POST.get('room_code', '').strip().upper()
    
    if not player_name:
        messages.error(request, 'Please enter your name.')
        return redirect('home')
    
    if len(player_name) > 20:
        messages.error(request, 'Name must be 20 characters or less.')
        return redirect('home')
    
    if not room_code:
        messages.error(request, 'Please enter a room code.')
        return redirect('home')
      
    # Find room
    try:
        room = Room.objects.get(code=room_code)
    except Room.DoesNotExist:
        messages.error(request, f'Room {room_code} not found.')
        return redirect('home')
    
    # Check if player name already exists in this room (case-insensitive)
    if room.members.filter(display_name__iexact=player_name, is_active=True).exists():
        messages.error(request, f'"{player_name}" Name already taken.Choose another.')
        return redirect('home')
    
    # Check if can join
    can_join, reason = room.can_join()
    if not can_join: 
        messages.error(request, reason)
        return redirect('home')
    
    # Ensure session exists
    if not request.session.session_key:
        request.session.create()
    
    # Get or create room member
    user = request.user if request.user.is_authenticated else None
    session_key = request.session.session_key if not user else None
    
    # Check if already a member
    existing_member = get_room_member(room, user, session_key)
    
    if existing_member:
        member = existing_member
        if not member.is_active:
            member.is_active = True
            member.display_name = player_name
            member.save()
    else:
        member = RoomMember.objects.create(
            room=room,
            user=user,
            session_key=session_key,
            display_name=player_name,
            role='player'
        )
    
    # Get current round and create round player if in waiting status
    current_round = room.get_current_round()
    if current_round and current_round.status == 'waiting':
        get_or_create_round_player(current_round, member)
    
    # Store in session
    request.session['current_room_code'] = room.code
    request.session['current_member_id'] = member.id
    
    messages.success(request, f'Joined room {room.code}!')
    return redirect('lobby', room_code=room.code)


def join_room_direct_view(request, room_code):
    """Direct join page via link/QR code."""
    room_code = room_code.upper()
    
    try:
        room = Room.objects.get(code=room_code)
    except Room.DoesNotExist:
        messages.error(request, f'Room {room_code} not found.')
        return redirect('home')
    
    # Check if can join
    can_join, reason = room.can_join()
    
    if request.method == 'POST': 
        if not can_join: 
            messages.error(request, reason)
            return redirect('home')
        player_name = request.POST.get('player_name', '').strip()
        
        # Check if player name already exists in this room (case-insensitive)
        if room.members.filter(display_name__iexact=player_name, is_active=True).exists():
            reason = f'"{player_name}" Name already taken.Choose another.'
            messages.error(request, reason)
            return render(request, 'game/join_direct.html', {'room': room, 'can_join': can_join, 'reason': reason})
        
        if not player_name:
            messages.error(request, 'Please enter your name.')
            return render(request, 'join_direct.html', {'room':  room, 'can_join': can_join, 'reason': reason})
        
        if len(player_name) > 30:
            messages.error(request, 'Name must be 30 characters or less.')
            return render(request, 'join_direct.html', {'room': room, 'can_join': can_join, 'reason': reason})
        
        # Ensure session
        if not request.session.session_key:
            request.session.create()
        
        user = request.user if request.user.is_authenticated else None
        session_key = request.session.session_key if not user else None
        
        # Try to find existing member (including inactive/kicked ones)
        existing_member = None
        if user:
            existing_member = RoomMember.objects.filter(room=room, user=user).first()
        elif session_key:
            existing_member = RoomMember.objects.filter(room=room, session_key=session_key).first()
        
        if existing_member: 
            # Reactivate if was kicked/left
            existing_member.is_active = True
            existing_member.display_name = player_name
            existing_member.save()
            member = existing_member
        else: 
            # Create new member
            member = RoomMember.objects.create(
                room=room,
                user=user,
                session_key=session_key,
                display_name=player_name,
                role='player'
            )
        
        # Add to current round if waiting
        current_round = room.get_current_round()
        if current_round and current_round.status == 'waiting': 
            existing_round_player = current_round.players.filter(room_member=member).first()
            if not existing_round_player: 
                RoundPlayer.objects.create(
                    game_round=current_round,
                    room_member=member,
                    board=RoundPlayer.generate_board()
                )
        
        request.session['current_room_code'] = room.code
        request.session['current_member_id'] = member.id
        
        messages.success(request, f'Joined room {room.code}!')
        return redirect('lobby', room_code=room.code)
    
    return render(request, 'game/join_direct.html', {
        'room': room,
        'can_join': can_join,
        'reason': reason
    })


def lobby_view(request, room_code):
    """
    Waiting room before game starts.
    Shows players, settings, share options.
    """
    room = get_object_or_404(Room, code=room_code)
    
    # Get current member
    member_id = request.session.get('current_member_id')
    current_member = None
    
    if member_id:
        current_member = RoomMember.objects.filter(id=member_id, room=room, is_active=True).first()
    
    if not current_member:
        messages.error(request, 'You are not in this room.')
        return redirect('home')
    
    # Get current round
    current_round = room.get_current_round()
    
    # If game in progress, redirect to game
    if current_round and current_round.status in ['setup', 'playing']: 
        return redirect('game', room_code=room.code)
    
    # Get all active members
    members = room.get_active_members()
    
    # Get round players if round exists
    round_players = []
    current_round_player = None
    if current_round:
        round_players = current_round.players.select_related('room_member').all()
        current_round_player = current_round.players.filter(room_member=current_member).first()
    
    round_history = room.rounds.filter(status='finished').order_by('-round_number').prefetch_related('winners__room_member')

    context = {
        'room': room,
        'current_member': current_member,
        'current_round':  current_round,
        'current_round_player': current_round_player,
        'members':  members,
        'round_players': round_players,
        'is_host': current_member.is_host,
        'share_url': request.build_absolute_uri(f'/join/{room.code}/'),
        'round_history': round_history,
    }
    
    return render(request, 'game/lobby.html', context)


def game_view(request, room_code):
    """
    Main game board page.
    Handles setup and playing phases.
    """
    room = get_object_or_404(Room, code=room_code)
    
    # Get current member
    member_id = request.session.get('current_member_id')
    current_member = None
    
    if member_id:
        current_member = RoomMember.objects.filter(id=member_id, room=room, is_active=True).first()
    
    if not current_member:
        messages.error(request, 'You are not in this room.')
        return redirect('home')
    
    # Get current round
    current_round = room.get_current_round()
    
    if not current_round or current_round.status == 'waiting':
        return redirect('lobby', room_code=room.code)
    
    # Get current player in round
    current_player = current_round.players.filter(room_member=current_member).first()
    
    if not current_player:
        messages.error(request, 'You are not in this game round.')
        return redirect('lobby', room_code=room.code)
    
    # Get all players
    all_players = current_round.players.select_related('room_member').all()
    
    # Determine if it's current player's turn
    is_my_turn = (current_round.current_turn_id == current_player.id) if current_round.current_turn else False
    

    round_history = room.rounds.filter(status='finished').order_by('-round_number').prefetch_related('winners__room_member')

    # Calculate remaining time
    remaining_seconds = 0
    if current_round.turn_deadline:
        delta = current_round.turn_deadline - timezone.now()
        remaining_seconds = max(0, int(delta.total_seconds()))
    context = {
        'room': room,
        'current_round': current_round,
        'current_member': current_member,
        'current_player': current_player,
        'all_players': all_players,
        'is_my_turn': is_my_turn,
        'is_host': current_member.is_host,
        'called_numbers': current_round.called_numbers,
        'remaining_seconds': remaining_seconds,
        'round_history': round_history,
        'show_login': False
    }
    
    return render(request, 'game/game.html', context)


def leave_room_view(request, room_code):
    """
    Leave the current room.
    Handles host transfer if needed.
    """
    if request.method != 'POST': 
        return redirect('home')
    
    room = get_object_or_404(Room, code=room_code)
    
    member_id = request.session.get('current_member_id')
    if not member_id:
        return redirect('home')
    
    member = RoomMember.objects.filter(id=member_id, room=room).first()
    if not member:
        return redirect('home')
    
    member_name = member.display_name
    was_host = member.is_host
    
    # Leave room (handles host transfer internally)
    member.leave_room()
    
    # Clear session
    request.session.pop('current_room_code', None)
    request.session.pop('current_member_id', None)
    
    if was_host:
        new_host = room.get_host()
        if new_host: 
            messages.info(request, f'You left the room.{new_host.display_name} is now the host.')
        else:
            messages.info(request, 'You left the room.Room is now empty.')
    else:
        messages.info(request, 'You left the room.')
    
    return redirect('home')


def room_settings_view(request, room_code):
    """
    Update room settings (host only).
    """
    if request.method != 'POST': 
        return JsonResponse({'error': 'POST required'}, status=405)
    
    room = get_object_or_404(Room, code=room_code)
    
    member_id = request.session.get('current_member_id')
    member = RoomMember.objects.filter(id=member_id, room=room, is_active=True).first()
    
    if not member or not member.is_host:
        return JsonResponse({'error': 'Only host can change settings'}, status=403)
    
    # Update settings
    try:
        setup_duration = int(request.POST.get('setup_duration', 60))
        turn_duration = int(request.POST.get('turn_duration', 30))
        max_players = int(request.POST.get('max_players', 6))
        
        # Validate
        setup_duration = max(15, min(120, setup_duration))
        turn_duration = max(10, min(90, turn_duration))
        max_players = max(2, min(15, max_players))
        
        room.settings_setup_duration = setup_duration
        room.settings_turn_duration = turn_duration
        room.settings_max_players = max_players
        room.save()
        
        return JsonResponse({'success': True})
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid settings'}, status=400)


def kick_player_view(request, room_code):
    """
    Kick a player from the room (host only, lobby only).
    """
    if request.method != 'POST': 
        return JsonResponse({'error':  'POST required'}, status=405)
    
    room = get_object_or_404(Room, code=room_code)
    
    member_id = request.session.get('current_member_id')
    member = RoomMember.objects.filter(id=member_id, room=room, is_active=True).first()
    
    if not member or not member.is_host:
        return JsonResponse({'error': 'Only host can kick players'}, status=403)
    
    # Check room is in lobby state
    current_round = room.get_current_round()
    if current_round and current_round.status not in ['waiting', 'finished']:
        return JsonResponse({'error': 'Cannot kick during game'}, status=400)
    
    # Get player to kick
    kick_member_id = request.POST.get('member_id')
    kick_member = RoomMember.objects.filter(id=kick_member_id, room=room, is_active=True).first()
    
    if not kick_member:
        return JsonResponse({'error': 'Player not found'}, status=404)
    
    if kick_member.is_host:
        return JsonResponse({'error': 'Cannot kick the host'}, status=400)
    
    # Kick the player
    kick_member.is_active = False
    kick_member.save()
    
    # Remove from current round if exists
    if current_round: 
        current_round.players.filter(room_member=kick_member).delete()
    
    return JsonResponse({
        'success': True,
        'kicked_name': kick_member.display_name
    })


# API Endpoints

def room_status_api(request, room_code):
    """
    API:  Get current room status.
    """
    room = get_object_or_404(Room, code=room_code)
    current_round = room.get_current_round()
    
    members_data = [{
        'id': m.id,
        'name': m.display_name,
        'role': m.role,
        'is_active': m.is_active,
    } for m in room.members.filter(is_active=True)]
    
    round_data = None
    if current_round: 
        players_data = [{
            'id': p.id,
            'member_id': p.room_member.id,
            'name': p.display_name,
            'role': p.role,
            'is_ready': p.is_ready,
            'completed_lines': p.completed_lines,
        } for p in current_round.players.all()]
        
        round_data = {
            'round_number': current_round.round_number,
            'status': current_round.status,
            'called_numbers': current_round.called_numbers,
            'current_turn_id': current_round.current_turn_id,
            'players': players_data,
        }
    
    return JsonResponse({
        'code': room.code,
        'is_active': room.is_active,
        'settings': {
            'setup_duration': room.settings_setup_duration,
            'turn_duration': room.settings_turn_duration,
            'max_players': room.settings_max_players,
        },
        'members': members_data,
        'current_round': round_data,
    })