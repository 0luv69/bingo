import json
import random
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from datetime import timedelta
from .models import Room, RoomMember, GameRound, RoundPlayer, CalledNumberHistory
from .utils import determine_winners, validate_board


# In-memory storage for grace period timers
# Format: {room_code: {member_id: asyncio. Task}}
disconnection_timers = {}

# Format: {room_code: {round_player_id: asyncio.Task}} for bot auto-play
bot_timers = {}


class GameConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time Bingo game communication.
    Handles disconnection grace periods, reconnection, and bot control.
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
        
        # Handle connection/reconnection
        member = await self.get_member()
        if member:
            is_reconnection = member.connection_status == 'disconnected'
            
            # Cancel any pending disconnection timer
            await self.cancel_disconnection_timer(member. id)
            
            # Mark as connected
            await self.mark_member_connected(member. id, self.channel_name)
            
            # If reconnecting, handle restoration
            if is_reconnection: 
                await self.handle_reconnection(member)
            
            # Broadcast player connected
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type':  'player_connected',
                    'member_id': member.id,
                    'member_name': member.display_name,
                    'is_reconnection': is_reconnection,
                    'members': await self.get_all_members_data(),
                    'round_players': await self.get_round_players_data(),
                }
            )
    
    async def disconnect(self, close_code):
        member = await self.get_member()
        if member:
            # Mark as disconnected
            await self. mark_member_disconnected(member.id)
            
            # Get grace period from room settings
            grace_period = await self.get_grace_period()
            
            # Broadcast disconnection with countdown info
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type':  'player_disconnected',
                    'member_id': member.id,
                    'member_name':  member.display_name,
                    'grace_period': grace_period,
                    'deadline': (timezone.now() + timedelta(seconds=grace_period)).isoformat(),
                }
            )
            
            # Start grace period timer
            await self.start_disconnection_timer(member.id, grace_period)
        
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
                'kick_player': self.handle_kick_player,
                'new_round': self.handle_new_round,
                # Vote kick handlers
                'cast_vote': self.handle_cast_vote,
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
    # DISCONNECTION & RECONNECTION HANDLING
    # ════════════════════════════════════════════════════════════
    
    async def start_disconnection_timer(self, member_id, grace_period):
        """Start a grace period timer for disconnected player."""
        if self.room_code not in disconnection_timers:
            disconnection_timers[self.room_code] = {}
        
        # Cancel existing timer if any
        await self.cancel_disconnection_timer(member_id)
        
        # Create new timer task
        async def grace_period_callback():
            try:
                await asyncio.sleep(grace_period)
                await self.handle_grace_period_expired(member_id)
            except asyncio.CancelledError:
                pass  # Timer was cancelled (player reconnected)
        
        task = asyncio.create_task(grace_period_callback())
        disconnection_timers[self. room_code][member_id] = task
    
    async def cancel_disconnection_timer(self, member_id):
        """Cancel a pending disconnection timer."""
        if self.room_code in disconnection_timers:
            if member_id in disconnection_timers[self.room_code]: 
                task = disconnection_timers[self.room_code][member_id]
                task. cancel()
                del disconnection_timers[self.room_code][member_id]
    
    async def handle_grace_period_expired(self, member_id):
        """Handle when grace period expires for a disconnected player."""
        member = await self.get_member_by_id(member_id)
        if not member or member.connection_status != 'disconnected': 
            return  # Player reconnected or already left
        
        current_round = await self.get_current_round()
        
        # Determine action based on game phase
        if current_round and current_round.status == 'playing':
            # GAME PHASE: Enable bot control (no vote kick)
            await self.enable_bot_control(member_id)
            
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'player_bot_controlled',
                    'member_id': member_id,
                    'member_name': member.display_name,
                    'message': f'{member.display_name} is now controlled by bot',
                    'round_players': await self.get_round_players_data(),
                }
            )
            
            # Check if it's this player's turn - schedule bot play
            round_player = await self.get_round_player(member_id)
            current_turn_id = await self.get_current_turn_id()
            if round_player and current_turn_id == round_player.id:
                await self.schedule_bot_play(round_player. id)
        
        else: 
            # LOBBY or ARRANGEMENT PHASE: Start vote kick
            await self.start_vote_kick(member_id)
    
    async def handle_reconnection(self, member):
        """Handle player reconnecting."""
        current_round = await self.get_current_round()
        if not current_round:
            return
        
        round_player = await self.get_round_player(member.id)
        if not round_player: 
            return
        
        # If bot was controlling, restore player control
        if round_player.is_bot_controlled:
            await self.disable_bot_control(member.id)
            
            # Cancel any pending bot play
            await self.cancel_bot_timer(round_player.id)
            
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'player_reconnected_from_bot',
                    'member_id': member.id,
                    'member_name': member.display_name,
                    'message': f'{member.display_name} reconnected and resumed control',
                    'round_players': await self.get_round_players_data(),
                }
            )
    
    # ════════════════════════════════════════════════════════════
    # BOT CONTROL LOGIC
    # ════════════════════════════════════════════════════════════
    
    async def enable_bot_control(self, member_id):
        """Enable bot control for a player."""
        await self.set_bot_controlled(member_id, True)
    
    async def disable_bot_control(self, member_id):
        """Disable bot control for a player."""
        await self.set_bot_controlled(member_id, False)
    
    async def schedule_bot_play(self, round_player_id):
        """Schedule bot to play after random 3-5 seconds."""
        if self.room_code not in bot_timers:
            bot_timers[self.room_code] = {}
        
        # Cancel existing bot timer
        await self.cancel_bot_timer(round_player_id)
        
        # Random delay 3-5 seconds
        delay = random.uniform(3, 5)
        
        async def bot_play_callback():
            try:
                await asyncio.sleep(delay)
                await self.execute_bot_play(round_player_id)
            except asyncio.CancelledError:
                pass
        
        task = asyncio. create_task(bot_play_callback())
        bot_timers[self.room_code][round_player_id] = task
    
    async def cancel_bot_timer(self, round_player_id):
        """Cancel pending bot play timer."""
        if self.room_code in bot_timers: 
            if round_player_id in bot_timers[self. room_code]:
                task = bot_timers[self.room_code][round_player_id]
                task.cancel()
                del bot_timers[self.room_code][round_player_id]
    
    async def execute_bot_play(self, round_player_id):
        """Execute bot's turn - pick random unmarked number."""
        round_player = await self.get_round_player_by_id(round_player_id)
        if not round_player:
            return
        
        current_round = await self.get_current_round()
        if not current_round or current_round.status != 'playing':
            return
        
        # Verify still this player's turn and still bot controlled
        current_turn_id = await self. get_current_turn_id()
        if current_turn_id != round_player_id:
            return
        
        is_bot = await self.is_player_bot_controlled(round_player_id)
        if not is_bot:
            return  # Player reconnected
        
        # Get unmarked numbers and pick random one
        unmarked = await self.get_unmarked_numbers(round_player_id)
        if not unmarked:
            return
        
        number = random. choice(unmarked)
        
        # Call the number as bot
        await self.add_called_number(number, round_player_id, is_bot=True)
        
        # Check for winners
        winners = await self.check_winners(round_player_id)
        
        # Get next turn
        room = await self.get_room()
        next_player_data = await self.set_next_turn()
        
        # Get updated data
        round_players = await self.get_round_players_data()
        called_numbers = await self.get_called_numbers()
        member_data = await self.get_round_player_member_data(round_player_id)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'number_called',
                'number':  number,
                'called_by': {
                    'id': round_player_id,
                    'member_id': member_data['member_id'],
                    'name': member_data['name'],
                    'is_bot': True,
                },
                'called_numbers': called_numbers,
                'next_turn': next_player_data,
                'duration': room.settings_turn_duration,
                'deadline': (timezone.now() + timedelta(seconds=room.settings_turn_duration)).isoformat(),
                'round_players': round_players,
                'show_score': room.settings_show_score,
            }
        )
        
        # Handle winners
        if winners:
            await self.handle_game_won(winners)
        else:
            # Check if next player is also bot controlled
            if next_player_data and next_player_data.get('is_bot_controlled'):
                await self.schedule_bot_play(next_player_data['id'])
    
    # ════════════════════════════════════════════════════════════
    # VOTE KICK LOGIC (Lobby & Arrangement phases only)
    # ════════════════════════════════════════════════════════════
    
    # In-memory vote tracking (simpler than database for real-time)
    # Format: {room_code: {target_member_id: {'votes': {'kick': set(), 'keep': set()}, 'started_at': datetime}}}
    
    async def start_vote_kick(self, member_id):
        """Start a vote kick session for disconnected player."""
        member = await self.get_member_by_id(member_id)
        if not member:
            return
        
        # Initialize vote tracking
        if not hasattr(self, 'vote_kicks'):
            self.vote_kicks = {}
        
        room_votes = getattr(GameConsumer, 'room_vote_kicks', {})
        if self.room_code not in room_votes:
            room_votes[self.room_code] = {}
        
        room_votes[self.room_code][member_id] = {
            'votes': {'kick': set(), 'keep': set()},
            'target_name': member.display_name,
            'started_at': timezone. now(),
        }
        GameConsumer.room_vote_kicks = room_votes
        
        total_voters = await self.get_connected_voters_count(member_id)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'vote_kick_started',
                'target_member_id': member_id,
                'target_member_name': member.display_name,
                'message': f'Vote:  Kick or Keep {member.display_name}? ',
                'total_voters':  total_voters,
            }
        )
    
    async def handle_cast_vote(self, data):
        """Handle a player casting their vote."""
        target_member_id = data. get('target_member_id')
        vote = data.get('vote')  # 'kick' or 'keep'
        
        if not target_member_id or vote not in ['kick', 'keep']:
            await self.send_error('Invalid vote')
            return
        
        member = await self.get_member()
        if not member:
            return
        
        # Can't vote for yourself
        if member.id == target_member_id:
            return
        
        # Record vote
        room_votes = getattr(GameConsumer, 'room_vote_kicks', {})
        if self.room_code not in room_votes or target_member_id not in room_votes[self.room_code]: 
            await self.send_error('No active vote for this player')
            return
        
        vote_data = room_votes[self.room_code][target_member_id]
        
        # Remove previous vote if any
        vote_data['votes']['kick'].discard(member.id)
        vote_data['votes']['keep'].discard(member. id)
        
        # Add new vote
        vote_data['votes'][vote]. add(member.id)
        
        kick_count = len(vote_data['votes']['kick'])
        keep_count = len(vote_data['votes']['keep'])
        total_voters = await self.get_connected_voters_count(target_member_id)
        total_voted = kick_count + keep_count
        
        # Broadcast vote update
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'vote_updated',
                'target_member_id': target_member_id,
                'votes': {'kick': kick_count, 'keep': keep_count},
                'total_voters': total_voters,
                'total_voted':  total_voted,
            }
        )
        
        # Check if voting complete (all voted)
        if total_voted >= total_voters:
            await self.complete_vote_kick(target_member_id)
    
    async def complete_vote_kick(self, target_member_id):
        """Complete vote kick and take action."""
        room_votes = getattr(GameConsumer, 'room_vote_kicks', {})
        if self.room_code not in room_votes or target_member_id not in room_votes[self.room_code]:
            return
        
        vote_data = room_votes[self.room_code][target_member_id]
        kick_count = len(vote_data['votes']['kick'])
        keep_count = len(vote_data['votes']['keep'])
        target_name = vote_data['target_name']
        
        # Determine result (majority wins, tie = keep)
        result = 'kick' if kick_count > keep_count else 'keep'
        
        # Clean up vote data
        del room_votes[self.room_code][target_member_id]
        
        if result == 'kick':
            # Remove the player
            await self.remove_member(target_member_id)
            
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'vote_kick_completed',
                    'result': 'kick',
                    'target_member_id': target_member_id,
                    'target_member_name': target_name,
                    'message': f'{target_name} was kicked by vote ({kick_count} kick, {keep_count} keep)',
                    'members':  await self.get_all_members_data(),
                    'round_players': await self. get_round_players_data(),
                }
            )
        else:
            # Keep - restart grace period
            grace_period = await self.get_grace_period()
            
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'vote_kick_completed',
                    'result': 'keep',
                    'target_member_id': target_member_id,
                    'target_member_name': target_name,
                    'message': f'Players voted to keep {target_name} ({kick_count} kick, {keep_count} keep). Waiting again.. .',
                    'grace_period': grace_period,
                }
            )
            
            # Restart grace period timer (loop)
            await self.start_disconnection_timer(target_member_id, grace_period)
    
    async def cancel_vote_kick_for_member(self, member_id):
        """Cancel active vote kick when player reconnects."""
        room_votes = getattr(GameConsumer, 'room_vote_kicks', {})
        if self.room_code in room_votes and member_id in room_votes[self.room_code]:
            target_name = room_votes[self.room_code][member_id]['target_name']
            del room_votes[self.room_code][member_id]
            
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'vote_kick_cancelled',
                    'member_id': member_id,
                    'message': f'Vote cancelled - {target_name} reconnected',
                }
            )
    
    # ════════════════════════════════════════════════════════════
    # EXISTING MESSAGE HANDLERS (with updates)
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
            await self. send_error('Need at least 2 players')
            return
        
        # Check for disconnected players
        disconnected = await self.get_disconnected_members()
        if disconnected: 
            names = ', '.join([m['name'] for m in disconnected])
            await self.send_error(f'Cannot start:  {names} disconnected')
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
        
        round_player = await self.get_round_player(member.id)
        if round_player:
            await self. mark_player_ready(round_player.id)
        
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
            await self. transition_to_playing()
    
    async def handle_update_board(self, data):
        """Player updates their board arrangement."""
        member = await self. get_member()
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
            await self. send_error('Number already called')
            return
        
        # Call the number
        await self.add_called_number(number, round_player.id)
        
        # Check for winners
        winners = await self.check_winners(round_player.id)
        
        # Get next turn
        room = await self.get_room()
        next_player_data = await self.set_next_turn()
        
        round_players = await self.get_round_players_data()
        called_numbers = await self.get_called_numbers()
        
        await self.channel_layer. group_send(
            self. room_group_name,
            {
                'type': 'number_called',
                'number': number,
                'called_by': {
                    'id': round_player.id,
                    'member_id': member.id,
                    'name': member.display_name,
                    'is_bot': False,
                },
                'called_numbers': called_numbers,
                'next_turn': next_player_data,
                'duration': room.settings_turn_duration,
                'deadline': (timezone.now() + timedelta(seconds=room.settings_turn_duration)).isoformat(),
                'round_players': round_players,
                'show_score': room.settings_show_score,
            }
        )
        
        if winners:
            await self.handle_game_won(winners)
        else:
            # Check if next player is bot controlled
            if next_player_data and next_player_data. get('is_bot_controlled'):
                await self.schedule_bot_play(next_player_data['id'])
    
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
        
        room = await self.get_room()
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'settings_updated',
                'settings': {
                    'setup_duration': room.settings_setup_duration,
                    'turn_duration': room.settings_turn_duration,
                    'max_players': room.settings_max_players,
                    'show_score': room.settings_show_score,
                    'grace_period': room.settings_grace_period,
                },
                'updated_by': member.display_name,
            }
        )
    
    async def handle_kick_player(self, data):
        """Host kicks a player."""
        member = await self.get_member()
        if not member or not member. is_host:
            await self.send_error('Only host can kick players')
            return
        
        current_round = await self.get_current_round()
        if current_round and current_round.status not in ['waiting', 'finished']:
            await self.send_error('Cannot kick during game')
            return
        
        kick_member_id = data.get('member_id')
        kicked_member = await self.kick_member(kick_member_id)
        
        if kicked_member:
            await self. channel_layer.group_send(
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
        """Host starts a new round."""
        current_round = await self.get_current_round()
        if current_round and current_round.status != 'finished':
            await self.send_error('Current round not finished')
            return
        
        # Reset bot control for all
        await self.reset_all_bot_control()
        
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
        await self.end_game([w['id'] for w in winners])
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
            await self. channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_started',
                    'status': 'playing',
                    'current_turn': first_player,
                    'duration': room.settings_turn_duration,
                    'deadline': (timezone.now() + timedelta(seconds=room.settings_turn_duration)).isoformat(),
                    'round_players': await self.get_round_players_data(),
                    'show_score': room.settings_show_score,
                }
            )
            
            # If first player is bot controlled, schedule bot play
            if first_player.get('is_bot_controlled'):
                await self.schedule_bot_play(first_player['id'])
    
    # ════════════════════════════════════════════════════════════
    # BROADCAST HANDLERS
    # ════════════════════════════════════════════════════════════
    
    async def player_connected(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_connected',
            'member_id': event['member_id'],
            'member_name': event['member_name'],
            'is_reconnection': event. get('is_reconnection', False),
            'members': event['members'],
            'round_players': event['round_players'],
        }))
    
    async def player_disconnected(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_disconnected',
            'member_id': event['member_id'],
            'member_name': event['member_name'],
            'grace_period': event['grace_period'],
            'deadline': event['deadline'],
        }))
    
    async def player_bot_controlled(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_bot_controlled',
            'member_id': event['member_id'],
            'member_name': event['member_name'],
            'message': event['message'],
            'round_players': event['round_players'],
        }))
    
    async def player_reconnected_from_bot(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_reconnected_from_bot',
            'member_id': event['member_id'],
            'member_name': event['member_name'],
            'message': event['message'],
            'round_players': event['round_players'],
        }))
    
    async def vote_kick_started(self, event):
        await self.send(text_data=json.dumps({
            'type': 'vote_kick_started',
            'target_member_id': event['target_member_id'],
            'target_member_name': event['target_member_name'],
            'message': event['message'],
            'total_voters': event['total_voters'],
        }))
    
    async def vote_updated(self, event):
        await self.send(text_data=json.dumps({
            'type': 'vote_updated',
            'target_member_id': event['target_member_id'],
            'votes': event['votes'],
            'total_voters': event['total_voters'],
            'total_voted': event['total_voted'],
        }))
    
    async def vote_kick_completed(self, event):
        await self.send(text_data=json.dumps({
            'type': 'vote_kick_completed',
            'result': event['result'],
            'target_member_id': event['target_member_id'],
            'target_member_name': event['target_member_name'],
            'message': event['message'],
            'members': event. get('members', []),
            'round_players': event. get('round_players', []),
            'grace_period': event.get('grace_period'),
        }))
    
    async def vote_kick_cancelled(self, event):
        await self.send(text_data=json.dumps({
            'type':  'vote_kick_cancelled',
            'member_id': event['member_id'],
            'message': event['message'],
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
            'round_players': event['round_players'],
            'show_score': event['show_score'],
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
            'round_players':  event['round_players'],
            'show_score': event['show_score'],
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
            return Room.objects. get(code=self.room_code)
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
    def get_member_by_id(self, member_id):
        try:
            return RoomMember.objects.get(id=member_id, room__code=self.room_code)
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
                return current_round.players.filter(room_member_id=member_id).select_related('room_member').first()
        except: 
            pass
        return None
    
    @database_sync_to_async
    def get_round_player_by_id(self, player_id):
        try:
            return RoundPlayer.objects.select_related('room_member').get(id=player_id)
        except RoundPlayer.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_round_player_member_data(self, player_id):
        try:
            player = RoundPlayer.objects.select_related('room_member').get(id=player_id)
            return {
                'member_id': player.room_member.id,
                'name': player.room_member.display_name,
            }
        except: 
            return {'member_id': None, 'name': 'Unknown'}
    
    @database_sync_to_async
    def get_all_members_data(self):
        try:
            room = Room.objects.get(code=self.room_code)
            return [{
                'id': m.id,
                'name': m.display_name,
                'role': m.role,
                'is_host': m.is_host,
                'connection_status': m.connection_status,
                'is_disconnected': m.is_disconnected,
            } for m in room.get_active_members()]
        except:
            return []
    
    @database_sync_to_async
    def get_round_players_data(self):
        try:
            room = Room.objects. get(code=self.room_code)
            current_round = room.get_current_round()
            if not current_round:
                return []
            return [{
                'id': p. id,
                'member_id': p.room_member.id,
                'name':  p.display_name,
                'role': p.role,
                'is_host': p.is_host,
                'is_co_host': p.is_co_host,
                'is_ready': p.is_ready,
                'completed_lines': p.completed_lines,
                'is_bot_controlled':  p.is_bot_controlled,
                'is_disconnected':  p.room_member.is_disconnected,
            } for p in current_round. players.select_related('room_member').all()]
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
    def get_grace_period(self):
        """Get grace period from room settings."""
        try:
            room = Room.objects.get(code=self.room_code)
            return room.settings_grace_period
        except:
            return 10  # Default fallback
    
    @database_sync_to_async
    def get_disconnected_members(self):
        """Get list of disconnected members."""
        try:
            room = Room.objects.get(code=self.room_code)
            return [{'id': m.id, 'name': m.display_name} 
                    for m in room.members.filter(is_active=True, connection_status='disconnected')]
        except:
            return []
    
    @database_sync_to_async
    def get_connected_voters_count(self, exclude_member_id):
        """Get count of connected members who can vote (excluding target)."""
        try:
            room = Room.objects.get(code=self.room_code)
            return room.members.filter(
                is_active=True,
                connection_status='connected'
            ).exclude(id=exclude_member_id).count()
        except:
            return 0
    
    @database_sync_to_async
    def mark_member_connected(self, member_id, channel_name):
        try:
            member = RoomMember.objects. get(id=member_id)
            member.mark_connected(channel_name)
        except RoomMember.DoesNotExist:
            pass
    
    @database_sync_to_async
    def mark_member_disconnected(self, member_id):
        try:
            member = RoomMember. objects.get(id=member_id)
            member.mark_disconnected()
        except RoomMember.DoesNotExist:
            pass
    
    @database_sync_to_async
    def set_bot_controlled(self, member_id, value):
        try:
            room = Room.objects.get(code=self.room_code)
            current_round = room.get_current_round()
            if current_round:
                player = current_round.players.filter(room_member_id=member_id).first()
                if player:
                    player.set_bot_controlled(value)
        except:
            pass
    
    @database_sync_to_async
    def is_player_bot_controlled(self, round_player_id):
        try:
            player = RoundPlayer.objects.get(id=round_player_id)
            return player.is_bot_controlled
        except: 
            return False
    
    @database_sync_to_async
    def reset_all_bot_control(self):
        """Reset bot control for all players."""
        try:
            room = Room.objects.get(code=self.room_code)
            current_round = room.get_current_round()
            if current_round:
                current_round.players.update(is_bot_controlled=False)
        except:
            pass
    
    @database_sync_to_async
    def get_unmarked_numbers(self, round_player_id):
        try:
            player = RoundPlayer.objects.get(id=round_player_id)
            called = set(player.game_round. called_numbers)
            unmarked = []
            for row in player.board: 
                for num in row:
                    if num not in called:
                        unmarked.append(num)
            return unmarked
        except: 
            return []
    
    @database_sync_to_async
    def remove_member(self, member_id):
        """Remove a member from the room."""
        try:
            member = RoomMember.objects. get(id=member_id, room__code=self.room_code)
            member.leave_room()
            
            room = Room.objects.get(code=self.room_code)
            current_round = room.get_current_round()
            if current_round:
                current_round.players.filter(room_member=member).delete()
            
            return True
        except:
            return False
    
    @database_sync_to_async
    def start_setup_phase(self, duration):
        room = Room.objects.get(code=self.room_code)
        current_round = room.get_current_round()
        if current_round:
            current_round. status = 'setup'
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
        room = Room.objects. get(code=self.room_code)
        current_round = room.get_current_round()
        if not current_round:
            return None
        
        current_round. status = 'playing'
        first_player = current_round.players.order_by('turn_order').first()
        if first_player:
            current_round.current_turn = first_player
            current_round.turn_deadline = timezone.now() + timedelta(seconds=room.settings_turn_duration)
        current_round.save()
        
        if first_player:
            return {
                'id': first_player.id,
                'member_id': first_player.room_member.id,
                'name': first_player.display_name,
                'is_bot_controlled': first_player.is_bot_controlled,
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
    def add_called_number(self, number, player_id, is_bot=False):
        room = Room. objects.get(code=self. room_code)
        current_round = room.get_current_round()
        player = RoundPlayer.objects.get(id=player_id)
        
        if number not in current_round.called_numbers:
            current_round. called_numbers.append(number)
            current_round.save()
        
        CalledNumberHistory.objects.create(
            game_round=current_round,
            number=number,
            called_by=player,
            is_bot_call=is_bot
        )
    
    @database_sync_to_async
    def check_winners(self, calling_player_id):
        room = Room.objects. get(code=self.room_code)
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
        room = Room.objects. get(code=self.room_code)
        current_round = room.get_current_round()
        
        next_player = current_round.get_next_turn_player()
        if next_player:
            current_round.current_turn = next_player
            current_round.turn_deadline = timezone.now() + timedelta(seconds=room.settings_turn_duration)
            current_round. save()
            return {
                'id': next_player.id,
                'member_id': next_player.room_member.id,
                'name': next_player.display_name,
                'is_bot_controlled': next_player.is_bot_controlled,
            }
        return None
    
    @database_sync_to_async
    def end_game(self, winner_ids:  list):
        room = Room.objects.get(code=self.room_code)
        current_round = room.get_current_round()
        winners = RoundPlayer.objects.filter(id__in=winner_ids)
        
        current_round.status = 'finished'
        current_round.winners. set(winners)
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
        if 'show_score' in settings:
            room.settings_show_score = bool(settings['show_score'])
        if 'grace_period' in settings:
            room.settings_grace_period = max(5, min(60, int(settings['grace_period'])))

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
            
            room = Room. objects.get(code=self. room_code)
            current_round = room.get_current_round()
            if current_round:
                current_round.players.filter(room_member=member).delete()
            
            return {'name': name}
        except RoomMember.DoesNotExist:
            return None
    
    @database_sync_to_async
    def create_new_round(self):
        room = Room.objects. get(code=self.room_code)
        new_round = GameRound.create_new_round(room)

        members = list(room.get_active_members())
        random.shuffle(members)
        for order, member in enumerate(members, start=1):
            RoundPlayer.objects.create(
                game_round=new_round,
                room_member=member,
                board=RoundPlayer.generate_board(),
                turn_order=order
            )
        
        return {
            'round_number': new_round.round_number,
        }
    
    async def send_error(self, message):
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))