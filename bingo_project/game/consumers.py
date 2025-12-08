import json
import random
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from datetime import timedelta
from .models import Room, Player, CalledNumber
from .utils import check_completed_lines, is_winner


class GameConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time Bingo game communication.
    
    Handles:
    - Player joining/leaving rooms
    - Game state changes (setup, playing, finished)
    - Number calling and turn management
    - Win detection and announcement
    """
    
    async def connect(self):
        """
        Called when a WebSocket connection is opened.
        
        Flow:
        1. Extract room code from URL
        2.  Get player from session
        3. Add to room group (for broadcasting)
        4. Accept connection
        5.  Broadcast player joined to all
        """
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.room_group_name = f'bingo_{self.room_code}'
        
        # Get session
        self.session = self.scope. get('session', {})
        self.player_id = self.session.get('current_player_id')
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self. channel_name
        )
        
        await self.accept()
        
        # Get player and room data
        player = await self.get_player()
        room = await self.get_room()
        
        if player and room:
            # Broadcast player joined
            await self. channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'player_joined',
                    'player_id': player.id,
                    'player_name': player. name,
                    'is_host': player.is_host,
                    'players': await self.get_all_players_data()
                }
            )
    
    async def disconnect(self, close_code):
        """
        Called when WebSocket connection is closed.
        
        Flow:
        1.  Broadcast player left
        2. Remove from room group
        """
        player = await self.get_player()
        
        if player:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'player_left',
                    'player_id': player.id,
                    'player_name': player.name,
                    'players': await self.get_all_players_data()
                }
            )
        
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        """
        Called when a message is received from WebSocket.
        
        Routes messages to appropriate handler based on 'type' field.
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type', '')
            
            # Route to appropriate handler
            if message_type == 'start_game':
                await self. handle_start_game(data)
            elif message_type == 'player_ready':
                await self.handle_player_ready(data)
            elif message_type == 'update_board':
                await self.handle_update_board(data)
            elif message_type == 'call_number':
                await self. handle_call_number(data)
            elif message_type == 'chat_message':
                await self.handle_chat_message(data)
            else:
                await self.send_error(f'Unknown message type: {message_type}')
                
        except json.JSONDecodeError:
            await self.send_error('Invalid JSON')
        except Exception as e:
            await self.send_error(str(e))
    
    # ════════════════════════════════════════════════════════════
    # MESSAGE HANDLERS
    # ════════════════════════════════════════════════════════════
    
    async def handle_start_game(self, data):
        """
        Host starts the game → Move to setup phase. 
        
        Validates:
        - Player is host
        - Room is in waiting status
        - At least 2 players
        """
        player = await self.get_player()
        room = await self.get_room()
        
        if not player or not room:
            await self.send_error('Room or player not found')
            return
        
        if not player.is_host:
            await self.send_error('Only host can start the game')
            return
        
        if room.status != 'waiting':
            await self.send_error('Game already started')
            return
        
        players_count = await self.get_players_count()
        if players_count < 2:
            await self.send_error('Need at least 2 players')
            return
        
        # Update room status to setup
        setup_duration = 60  # 1 minute for setup
        deadline = timezone.now() + timedelta(seconds=setup_duration)
        await self.update_room_status('setup', deadline)
        
        # Broadcast game starting
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_starting',
                'status': 'setup',
                'deadline': deadline.isoformat(),
                'duration': setup_duration,
                'message': 'Arrange your board!  You have 1 minute.'
            }
        )
    
    async def handle_player_ready(self, data):
        """
        Player clicks ready during setup phase.
        
        Flow:
        1. Mark player as ready
        2.  Broadcast to all
        3. If all ready, start playing phase
        """
        player = await self.get_player()
        room = await self.get_room()
        
        if not player or not room:
            return
        
        if room.status != 'setup':
            await self.send_error('Not in setup phase')
            return
        
        # Mark player ready
        await self.set_player_ready(player.id)
        
        # Get updated data
        players_data = await self.get_all_players_data()
        ready_count = sum(1 for p in players_data if p['is_ready'])
        total_count = len(players_data)
        
        # Broadcast ready status
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'player_ready_update',
                'player_id': player.id,
                'player_name': player.name,
                'ready_count': ready_count,
                'total_count': total_count,
                'players': players_data
            }
        )
        
        # Check if all ready
        if ready_count == total_count:
            await self.start_playing_phase()
    
    async def handle_update_board(self, data):
        """
        Player rearranges their board during setup.
        
        Saves new board arrangement to database.
        """
        player = await self.get_player()
        room = await self.get_room()
        
        if not player or not room:
            return
        
        if room. status != 'setup':
            await self.send_error('Cannot update board now')
            return
        
        if player.is_ready:
            await self.send_error('Already marked ready')
            return
        
        new_board = data.get('board')
        if not new_board or not self.validate_board(new_board):
            await self.send_error('Invalid board')
            return
        
        await self.save_player_board(player.id, new_board)
        
        # Confirm to player
        await self.send(text_data=json.dumps({
            'type': 'board_updated',
            'success': True
        }))
    
    async def handle_call_number(self, data):
        """
        Player calls a number during playing phase.
        
        Flow:
        1. Validate it's player's turn
        2.  Validate number not already called
        3. Add to called numbers
        4. Save to CalledNumber model
        5. Check completed lines for all players
        6. Check for winner
        7. Set next turn
        8. Broadcast update
        """
        player = await self.get_player()
        room = await self.get_room()
        
        if not player or not room:
            return
        
        if room.status != 'playing':
            await self.send_error('Game not in progress')
            return
        
        # Check if it's player's turn
        current_turn_id = await self.get_current_turn_id()
        if current_turn_id != player.id:
            await self.send_error('Not your turn')
            return
        
        number = data.get('number')
        if not number or not isinstance(number, int) or number < 1 or number > 25:
            await self.send_error('Invalid number')
            return
        
        # Check if already called
        called_numbers = await self.get_called_numbers()
        if number in called_numbers:
            await self.send_error('Number already called')
            return
        
        # Call the number
        await self.add_called_number(number, player.id)
        
        # Check lines and winner
        winner_data = await self.check_all_players_lines()
        
        # Get next turn
        next_player = await self.get_and_set_next_turn()
        
        # Set turn deadline
        turn_duration = 60  # 1 minute per turn
        deadline = timezone.now() + timedelta(seconds=turn_duration)
        await self. update_turn_deadline(deadline)
        
        # Broadcast number called
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'number_called',
                'number': number,
                'called_by': {
                    'id': player.id,
                    'name': player.name
                },
                'called_numbers': await self.get_called_numbers(),
                'next_turn': {
                    'id': next_player['id'],
                    'name': next_player['name']
                } if next_player else None,
                'deadline': deadline.isoformat(),
                'duration': turn_duration,
                'players': await self.get_all_players_data(),
                'lines_update': winner_data. get('lines_update', [])
            }
        )
        
        # Check for winner
        if winner_data.get('winner'):
            await self.handle_game_won(winner_data['winner'])
    
    async def handle_chat_message(self, data):
        """Simple chat message broadcast."""
        player = await self. get_player()
        if not player:
            return
        
        message = data.get('message', '').strip()
        if not message:
            return
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_broadcast',
                'player_id': player.id,
                'player_name': player. name,
                'message': message[:200]  # Limit message length
            }
        )
    
    async def handle_game_won(self, winner):
        """Handle game won - broadcast winner and update room status."""
        await self.update_room_status('finished', None)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_won',
                'winner': {
                    'id': winner['id'],
                    'name': winner['name'],
                    'completed_lines': winner['completed_lines']
                },
                'players': await self.get_all_players_data()
            }
        )
    
    async def start_playing_phase(self):
        """Transition from setup to playing phase."""
        # Set first turn
        first_player = await self.get_first_player()
        if not first_player:
            return
        
        await self.set_current_turn(first_player['id'])
        
        # Set turn deadline
        turn_duration = 60
        deadline = timezone.now() + timedelta(seconds=turn_duration)
        await self.update_room_status('playing', deadline)
        
        # Broadcast game started
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_started',
                'status': 'playing',
                'current_turn': {
                    'id': first_player['id'],
                    'name': first_player['name']
                },
                'deadline': deadline.isoformat(),
                'duration': turn_duration,
                'players': await self.get_all_players_data()
            }
        )
    
    # ════════════════════════════════════════════════════════════
    # BROADCAST HANDLERS (Called by channel_layer. group_send)
    # ════════════════════════════════════════════════════════════
    
    async def player_joined(self, event):
        """Broadcast: Player joined the room."""
        await self.send(text_data=json.dumps({
            'type': 'player_joined',
            'player_id': event['player_id'],
            'player_name': event['player_name'],
            'is_host': event['is_host'],
            'players': event['players']
        }))
    
    async def player_left(self, event):
        """Broadcast: Player left the room."""
        await self.send(text_data=json.dumps({
            'type': 'player_left',
            'player_id': event['player_id'],
            'player_name': event['player_name'],
            'players': event['players']
        }))
    
    async def game_starting(self, event):
        """Broadcast: Game is starting (setup phase)."""
        await self. send(text_data=json. dumps({
            'type': 'game_starting',
            'status': event['status'],
            'deadline': event['deadline'],
            'duration': event['duration'],
            'message': event['message']
        }))
    
    async def player_ready_update(self, event):
        """Broadcast: Player ready status changed."""
        await self.send(text_data=json.dumps({
            'type': 'player_ready',
            'player_id': event['player_id'],
            'player_name': event['player_name'],
            'ready_count': event['ready_count'],
            'total_count': event['total_count'],
            'players': event['players']
        }))
    
    async def game_started(self, event):
        """Broadcast: Game started (playing phase)."""
        await self.send(text_data=json.dumps({
            'type': 'game_started',
            'status': event['status'],
            'current_turn': event['current_turn'],
            'deadline': event['deadline'],
            'duration': event['duration'],
            'players': event['players']
        }))
    
    async def number_called(self, event):
        """Broadcast: Number was called."""
        await self.send(text_data=json.dumps({
            'type': 'number_called',
            'number': event['number'],
            'called_by': event['called_by'],
            'called_numbers': event['called_numbers'],
            'next_turn': event['next_turn'],
            'deadline': event['deadline'],
            'duration': event['duration'],
            'players': event['players'],
            'lines_update': event. get('lines_update', [])
        }))
    
    async def game_won(self, event):
        """Broadcast: Game won."""
        await self.send(text_data=json.dumps({
            'type': 'game_won',
            'winner': event['winner'],
            'players': event['players']
        }))
    
    async def chat_broadcast(self, event):
        """Broadcast: Chat message."""
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'player_id': event['player_id'],
            'player_name': event['player_name'],
            'message': event['message']
        }))
    
    # ════════════════════════════════════════════════════════════
    # DATABASE HELPERS (Async database operations)
    # ════════════════════════════════════════════════════════════
    
    @database_sync_to_async
    def get_room(self):
        """Get room by code."""
        try:
            return Room.objects. get(code=self.room_code)
        except Room.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_player(self):
        """Get current player."""
        if not self.player_id:
            return None
        try:
            return Player.objects. get(id=self.player_id, room__code=self.room_code)
        except Player.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_players_count(self):
        """Get number of players in room."""
        return Player.objects. filter(room__code=self.room_code).count()
    
    @database_sync_to_async
    def get_all_players_data(self):
        """Get all players data as list of dicts."""
        players = Player.objects.filter(room__code=self.room_code). order_by('joined_at')
        return [{
            'id': p.id,
            'name': p. name,
            'is_host': p.is_host,
            'is_ready': p.is_ready,
            'completed_lines': p.completed_lines
        } for p in players]
    
    @database_sync_to_async
    def update_room_status(self, status, deadline):
        """Update room status and deadline."""
        Room.objects.filter(code=self.room_code).update(
            status=status,
            turn_deadline=deadline
        )
    
    @database_sync_to_async
    def update_turn_deadline(self, deadline):
        """Update turn deadline."""
        Room.objects.filter(code=self.room_code). update(turn_deadline=deadline)
    
    @database_sync_to_async
    def set_player_ready(self, player_id):
        """Mark player as ready."""
        Player. objects.filter(id=player_id). update(is_ready=True)
    
    @database_sync_to_async
    def save_player_board(self, player_id, board):
        """Save player's board arrangement."""
        Player.objects.filter(id=player_id).update(board=board)
    
    @database_sync_to_async
    def get_called_numbers(self):
        """Get list of called numbers."""
        room = Room.objects.get(code=self.room_code)
        return room.called_numbers
    
    @database_sync_to_async
    def add_called_number(self, number, player_id):
        """Add number to called numbers and create history record."""
        room = Room.objects.get(code=self.room_code)
        player = Player.objects.get(id=player_id)
        
        # Add to room's called_numbers
        if number not in room.called_numbers:
            room.called_numbers. append(number)
            room.save()
        
        # Create history record
        CalledNumber.objects.create(room=room, number=number, called_by=player)
    
    @database_sync_to_async
    def get_current_turn_id(self):
        """Get current turn player ID."""
        room = Room.objects.get(code=self.room_code)
        return room.current_turn_id
    
    @database_sync_to_async
    def set_current_turn(self, player_id):
        """Set current turn to player."""
        Room.objects.filter(code=self.room_code).update(current_turn_id=player_id)
    
    @database_sync_to_async
    def get_first_player(self):
        """Get first player (by join order)."""
        player = Player.objects.filter(room__code=self.room_code).order_by('joined_at').first()
        if player:
            return {'id': player.id, 'name': player.name}
        return None
    
    @database_sync_to_async
    def get_and_set_next_turn(self):
        """Get next player and set as current turn."""
        room = Room.objects.get(code=self.room_code)
        next_player = room.get_next_turn_player()
        if next_player:
            room.current_turn = next_player
            room.save()
            return {'id': next_player.id, 'name': next_player. name}
        return None
    
    @database_sync_to_async
    def check_all_players_lines(self):
        """Check completed lines for all players and detect winner."""
        room = Room. objects.get(code=self. room_code)
        players = Player.objects.filter(room=room)
        called_numbers = room.called_numbers
        
        lines_update = []
        winner = None
        
        for player in players:
            old_lines = player.completed_lines
            new_lines, completed = check_completed_lines(player.board, called_numbers)
            
            if new_lines != old_lines:
                player.completed_lines = new_lines
                player.save()
                
                lines_update.append({
                    'player_id': player.id,
                    'player_name': player. name,
                    'old_lines': old_lines,
                    'new_lines': new_lines,
                    'completed': [c['name'] for c in completed[old_lines:]]
                })
            
            # Check for winner (5 lines)
            if new_lines >= 5 and not winner:
                winner = {
                    'id': player. id,
                    'name': player.name,
                    'completed_lines': new_lines
                }
        
        return {
            'lines_update': lines_update,
            'winner': winner
        }
    
    # ════════════════════════════════════════════════════════════
    # UTILITY METHODS
    # ════════════════════════════════════════════════════════════
    
    def validate_board(self, board):
        """Validate board is a valid 5x5 grid with numbers 1-25."""
        if not isinstance(board, list) or len(board) != 5:
            return False
        
        all_numbers = []
        for row in board:
            if not isinstance(row, list) or len(row) != 5:
                return False
            all_numbers.extend(row)
        
        return sorted(all_numbers) == list(range(1, 26))
    
    async def send_error(self, message):
        """Send error message to client."""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))