import json
import random
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from datetime import timedelta
from .models import Room, RoomMember, GameRound, RoundPlayer, CalledNumberHistory
from .utils import determine_winners, update_all_players_lines, validate_board


class GameConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time Bingo game communication.
    """
    
    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.room_group_name = f'bingo_{self.room_code}'
        
        # Get member from session
        session = self.scope.get('session', {})
        self.member_id = session.get('current_member_id')
        
        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        
        # Broadcast player connected
        member = await self.get_member()
        if member:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'player_connected',
                    'member_id': member.id,
                    'member_name': member.display_name,
                    'members': await self.get_all_members_data(),
                    'round_players': await self.get_round_players_data(),
                }
            )
    
    async def disconnect(self, close_code):
        member = await self.get_member()
        if member:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'player_disconnected',
                    'member_id': member.id,
                    'member_name':  member.display_name,
                }
            )
        
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type', '')
            
            handlers = {
                'start_game': self.handle_start_game,
                'player_ready': self.handle_player_ready,
                'update_board': self.handle_update_board,
                'call_number': self.handle_call_number,
                'update_settings': self.handle_update_settings,
                'kick_player':  self.handle_kick_player,
                'new_round': self.handle_new_round,
            }
            
            handler = handlers.get(message_type)
            if handler:
                await handler(data)
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
        """Host starts the game."""
        member = await self.get_member()
        if not member or not member.is_host:
            await self.send_error('Only host can start the game')
            return
        
        room = await self.get_room()
        current_round = await self.get_current_round()
        
        if not current_round or current_round.status != 'waiting':
            await self.send_error('Cannot start game now')
            return
        
        players_count = await self.get_round_players_count()
        if players_count < 2:
            await self.send_error('Need at least 2 players')
            return
        
        # Start setup phase
        setup_duration = room.settings_setup_duration
        await self.start_setup_phase(setup_duration)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_starting',
                'status': 'setup',
                'duration': setup_duration,
                'deadline': (timezone.now() + timedelta(seconds=setup_duration)).isoformat(),
                'message': f'Arrange your board!  You have {setup_duration} seconds.',
                'round_players': await self.get_round_players_data(),
            }
        )
    
    async def handle_player_ready(self, data):
        """Player marks themselves as ready."""
        member = await self.get_member()
        current_round = await self.get_current_round()
        
        if not member or not current_round:
            return
        
        if current_round.status != 'setup':
            await self.send_error('Not in setup phase')
            return
        
        # Mark player ready
        round_player = await self.get_round_player(member.id)
        if round_player:
            await self.mark_player_ready(round_player.id)
        
        # Get updated data
        round_players = await self.get_round_players_data()
        ready_count = sum(1 for p in round_players if p['is_ready'])
        total_count = len(round_players)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'player_ready_update',
                'member_id': member.id,
                'member_name': member.display_name,
                'ready_count':  ready_count,
                'total_count': total_count,
                'round_players': round_players,
            }
        )
        
        # Check if all ready
        if ready_count == total_count:
            await self.transition_to_playing()
    
    async def handle_update_board(self, data):
        """Player updates their board arrangement."""
        member = await self.get_member()
        current_round = await self.get_current_round()
        
        if not member or not current_round: 
            return
        
        if current_round.status != 'setup':
            await self.send_error('Cannot update board now')
            return
        
        round_player = await self.get_round_player(member.id)
        if not round_player or round_player.is_ready:
            await self.send_error('Cannot update board')
            return
        
        new_board = data.get('board')
        if not new_board or not validate_board(new_board):
            await self.send_error('Invalid board')
            return
        
        await self.save_player_board(round_player.id, new_board)
        
        await self.send(text_data=json.dumps({
            'type': 'board_updated',
            'success': True
        }))
    
    async def handle_call_number(self, data):
        """Player calls a number."""
        member = await self.get_member()
        current_round = await self.get_current_round()
        
        if not member or not current_round:
            return
        
        if current_round.status != 'playing':
            await self.send_error('Game not in progress')
            return
        
        round_player = await self.get_round_player(member.id)
        if not round_player: 
            return
        
        # Check turn
        current_turn_id = await self.get_current_turn_id()
        if current_turn_id != round_player.id:
            await self.send_error('Not your turn')
            return
        
        number = data.get('number')
        if not isinstance(number, int) or number < 1 or number > 25:
            await self.send_error('Invalid number')
            return
        
        called_numbers = await self.get_called_numbers()
        if number in called_numbers:
            await self.send_error('Number already called')
            return
        
        # Call the number
        await self.add_called_number(number, round_player.id)
        
        # Check for winners
        winners = await self.check_winners(round_player.id)
        
        # Get next turn
        room = await self.get_room()
        next_player_data = await self.set_next_turn()
        
        # Get updated data
        round_players = await self.get_round_players_data()
        called_numbers = await self.get_called_numbers()
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'number_called',
                'number':  number,
                'called_by': {
                    'id': round_player.id,
                    'member_id': member.id,
                    'name': member.display_name,
                },
                'called_numbers': called_numbers,
                'next_turn': next_player_data,
                'duration': room.settings_turn_duration,
                'deadline': (timezone.now() + timedelta(seconds=room.settings_turn_duration)).isoformat(),
                'round_players': round_players,
            }
        )
        
        # Handle winners
        if winners:
            await self.handle_game_won(winners)
    
    async def handle_update_settings(self, data):
        """Host updates room settings."""
        member = await self.get_member()
        if not member or not member.is_host:
            await self.send_error('Only host can change settings')
            return
        
        room = await self.get_room()
        current_round = await self.get_current_round()
        
        if current_round and current_round.status not in ['waiting', 'finished']: 
            await self.send_error('Cannot change settings during game')
            return
        
        settings = data.get('settings', {})
        await self.update_room_settings(settings)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'settings_updated',
                'settings': {
                    'setup_duration':  room.settings_setup_duration,
                    'turn_duration':  room.settings_turn_duration,
                    'max_players':  room.settings_max_players,
                },
                'updated_by': member.display_name,
            }
        )
    
    async def handle_kick_player(self, data):
        """Host kicks a player."""
        member = await self.get_member()
        if not member or not member.is_host:
            await self.send_error('Only host can kick players')
            return
        
        current_round = await self.get_current_round()
        if current_round and current_round.status not in ['waiting', 'finished']:
            await self.send_error('Cannot kick during game')
            return
        
        kick_member_id = data.get('member_id')
        kicked_member = await self.kick_member(kick_member_id)
        
        if kicked_member:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'player_kicked',
                    'kicked_member_id': kick_member_id,
                    'kicked_name': kicked_member['name'],
                    'members': await self.get_all_members_data(),
                    'round_players': await self.get_round_players_data(),
                }
            )
    
    async def handle_new_round(self, data):
        """Host starts a new round (after game finished)."""
        member = await self.get_member()
        if not member or not member.is_host:
            await self.send_error('Only host can start new round')
            return
        
        current_round = await self.get_current_round()
        if current_round and current_round.status != 'finished':
            await self.send_error('Current round not finished')
            return
        
        # Create new round
        new_round = await self.create_new_round()
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'new_round_created',
                'round_number': new_round['round_number'],
                'message': 'New round started!  Returning to lobby.',
            }
        )
    
    async def handle_game_won(self, winners):
        """Handle game won."""
        await self.end_game(winners[0]['id'])
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_won',
                'winners': winners,
                'is_tie': len(winners) > 1,
                'round_players': await self.get_round_players_data(),
            }
        )
    
    async def transition_to_playing(self):
        """Transition from setup to playing phase."""
        room = await self.get_room()
        first_player = await self.start_playing_phase()
        
        if first_player:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_started',
                    'status': 'playing',
                    'current_turn': first_player,
                    'duration': room.settings_turn_duration,
                    'deadline': (timezone.now() + timedelta(seconds=room.settings_turn_duration)).isoformat(),
                    'round_players': await self.get_round_players_data(),
                }
            )
    
    # ════════════════════════════════════════════════════════════
    # BROADCAST HANDLERS
    # ════════════════════════════════════════════════════════════
    
    async def player_connected(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_connected',
            'member_id': event['member_id'],
            'member_name':  event['member_name'],
            'members': event['members'],
            'round_players': event['round_players'],
        }))
    
    async def player_disconnected(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_disconnected',
            'member_id': event['member_id'],
            'member_name': event['member_name'],
        }))
    
    async def game_starting(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_starting',
            'status': event['status'],
            'duration':  event['duration'],
            'deadline': event['deadline'],
            'message': event['message'],
            'round_players': event['round_players'],
        }))
    
    async def player_ready_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_ready',
            'member_id': event['member_id'],
            'member_name': event['member_name'],
            'ready_count': event['ready_count'],
            'total_count': event['total_count'],
            'round_players': event['round_players'],
        }))
    
    async def game_started(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_started',
            'status': event['status'],
            'current_turn': event['current_turn'],
            'duration': event['duration'],
            'deadline': event['deadline'],
            'round_players':  event['round_players'],
        }))
    
    async def number_called(self, event):
        await self.send(text_data=json.dumps({
            'type': 'number_called',
            'number': event['number'],
            'called_by': event['called_by'],
            'called_numbers': event['called_numbers'],
            'next_turn': event['next_turn'],
            'duration': event['duration'],
            'deadline': event['deadline'],
            'round_players': event['round_players'],
        }))
    
    async def game_won(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_won',
            'winners': event['winners'],
            'is_tie': event['is_tie'],
            'round_players': event['round_players'],
        }))
    
    async def settings_updated(self, event):
        await self.send(text_data=json.dumps({
            'type': 'settings_updated',
            'settings': event['settings'],
            'updated_by': event['updated_by'],
        }))
    
    async def player_kicked(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_kicked',
            'kicked_member_id': event['kicked_member_id'],
            'kicked_name': event['kicked_name'],
            'members': event['members'],
            'round_players': event['round_players'],
        }))
    
    async def new_round_created(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_round_created',
            'round_number': event['round_number'],
            'message': event['message'],
        }))
    
    # ════════════════════════════════════════════════════════════
    # DATABASE HELPERS
    # ════════════════════════════════════════════════════════════
    
    @database_sync_to_async
    def get_room(self):
        try:
            return Room.objects.get(code=self.room_code)
        except Room.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_member(self):
        if not self.member_id:
            return None
        try:
            return RoomMember.objects.get(id=self.member_id, room__code=self.room_code, is_active=True)
        except RoomMember.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_current_round(self):
        try:
            room = Room.objects.get(code=self.room_code)
            return room.get_current_round()
        except Room.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_round_player(self, member_id):
        try:
            room = Room.objects.get(code=self.room_code)
            current_round = room.get_current_round()
            if current_round: 
                return current_round.players.filter(room_member_id=member_id).first()
        except: 
            pass
        return None
    
    @database_sync_to_async
    def get_all_members_data(self):
        try:
            room = Room.objects.get(code=self.room_code)
            return [{
                'id': m.id,
                'name': m.display_name,
                'role': m.role,
                'is_host': m.is_host,
            } for m in room.get_active_members()]
        except:
            return []
    
    @database_sync_to_async
    def get_round_players_data(self):
        try:
            room = Room.objects.get(code=self.room_code)
            current_round = room.get_current_round()
            if not current_round:
                return []
            return [{
                'id': p.id,
                'member_id': p.room_member.id,
                'name': p.display_name,
                'role':  p.role,
                'is_host': p.is_host,
                'is_ready': p.is_ready,
                'completed_lines': p.completed_lines,
            } for p in current_round.players.select_related('room_member').all()]
        except:
            return []
    
    @database_sync_to_async
    def get_round_players_count(self):
        try:
            room = Room.objects.get(code=self.room_code)
            current_round = room.get_current_round()
            return current_round.get_players_count() if current_round else 0
        except:
            return 0
    
    @database_sync_to_async
    def start_setup_phase(self, duration):
        room = Room.objects.get(code=self.room_code)
        current_round = room.get_current_round()
        if current_round:
            current_round.status = 'setup'
            current_round.turn_deadline = timezone.now() + timedelta(seconds=duration)
            current_round.started_at = timezone.now()
            current_round.save()
    
    @database_sync_to_async
    def mark_player_ready(self, player_id):
        RoundPlayer.objects.filter(id=player_id).update(is_ready=True)
    
    @database_sync_to_async
    def save_player_board(self, player_id, board):
        RoundPlayer.objects.filter(id=player_id).update(board=board)
    
    @database_sync_to_async
    def start_playing_phase(self):
        room = Room.objects.get(code=self.room_code)
        current_round = room.get_current_round()
        if not current_round:
            return None
        
        current_round.status = 'playing'
        first_player = current_round.players.order_by('joined_at').first()
        if first_player:
            current_round.current_turn = first_player
            current_round.turn_deadline = timezone.now() + timedelta(seconds=room.settings_turn_duration)
        current_round.save()
        
        if first_player:
            return {
                'id': first_player.id,
                'member_id': first_player.room_member.id,
                'name': first_player.display_name,
            }
        return None
    
    @database_sync_to_async
    def get_current_turn_id(self):
        room = Room.objects.get(code=self.room_code)
        current_round = room.get_current_round()
        return current_round.current_turn_id if current_round else None
    
    @database_sync_to_async
    def get_called_numbers(self):
        room = Room.objects.get(code=self.room_code)
        current_round = room.get_current_round()
        return current_round.called_numbers if current_round else []
    
    @database_sync_to_async
    def add_called_number(self, number, player_id):
        room = Room.objects.get(code=self.room_code)
        current_round = room.get_current_round()
        player = RoundPlayer.objects.get(id=player_id)
        
        if number not in current_round.called_numbers:
            current_round.called_numbers.append(number)
            current_round.save()
        
        CalledNumberHistory.objects.create(
            game_round=current_round,
            number=number,
            called_by=player
        )
    
    @database_sync_to_async
    def check_winners(self, calling_player_id):
        room = Room.objects.get(code=self.room_code)
        current_round = room.get_current_round()
        calling_player = RoundPlayer.objects.get(id=calling_player_id)
        
        winners = determine_winners(current_round, calling_player)
        
        return [{
            'id': w.id,
            'member_id': w.room_member.id,
            'name':  w.display_name,
            'completed_lines': w.completed_lines,
        } for w in winners]
    
    @database_sync_to_async
    def set_next_turn(self):
        room = Room.objects.get(code=self.room_code)
        current_round = room.get_current_round()
        
        next_player = current_round.get_next_turn_player()
        if next_player:
            current_round.current_turn = next_player
            current_round.turn_deadline = timezone.now() + timedelta(seconds=room.settings_turn_duration)
            current_round.save()
            return {
                'id': next_player.id,
                'member_id': next_player.room_member.id,
                'name': next_player.display_name,
            }
        return None
    
    @database_sync_to_async
    def end_game(self, winner_id):
        room = Room.objects.get(code=self.room_code)
        current_round = room.get_current_round()
        winner = RoundPlayer.objects.get(id=winner_id)
        
        current_round.status = 'finished'
        current_round.winner = winner
        current_round.finished_at = timezone.now()
        current_round.turn_deadline = None
        current_round.save()
    
    @database_sync_to_async
    def update_room_settings(self, settings):
        room = Room.objects.get(code=self.room_code)
        
        if 'setup_duration' in settings:
            room.settings_setup_duration = max(15, min(120, int(settings['setup_duration'])))
        if 'turn_duration' in settings:
            room.settings_turn_duration = max(10, min(90, int(settings['turn_duration'])))
        if 'max_players' in settings:
            room.settings_max_players = max(2, min(15, int(settings['max_players'])))
        
        room.save()
    
    @database_sync_to_async
    def kick_member(self, member_id):
        try:
            member = RoomMember.objects.get(id=member_id, room__code=self.room_code)
            if member.is_host:
                return None
            
            name = member.display_name
            member.is_active = False
            member.save()
            
            # Remove from current round
            room = Room.objects.get(code=self.room_code)
            current_round = room.get_current_round()
            if current_round:
                current_round.players.filter(room_member=member).delete()
            
            return {'name': name}
        except RoomMember.DoesNotExist:
            return None
    
    @database_sync_to_async
    def create_new_round(self):
        room = Room.objects.get(code=self.room_code)
        new_round = GameRound.create_new_round(room)
        
        # Add all active members as players
        for member in room.get_active_members():
            RoundPlayer.objects.create(
                game_round=new_round,
                room_member=member,
                board=RoundPlayer.generate_board()
            )
        
        return {
            'round_number': new_round.round_number,
        }
    
    async def send_error(self, message):
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))