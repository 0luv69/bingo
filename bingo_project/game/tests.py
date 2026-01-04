class GameConsumer(AsyncWebsocketConsumer):
    
    # ... existing code ...

    # ════════════════════════════════════════════════════════════════
    # TURN TIMEOUT HANDLING
    # ════════════════════════════════════════════════════════════════
    
    async def start_turn_timer(self, duration, current_player_id):
        """Start a timer that auto-picks a number when turn expires."""
        
        async def on_turn_timeout():
            try:
                # Wait for turn duration + small buffer for network latency
                await asyncio.sleep(duration + 2)
                await self.handle_turn_timeout(current_player_id)
            except asyncio.CancelledError:
                pass  # Timer was cancelled (player made a move)
        
        task = asyncio.create_task(on_turn_timeout())
        DisconnectionManager.set_turn_timer(self.room_code, task)
    
    async def handle_turn_timeout(self, expected_player_id):
        """Handle when a player's turn times out - auto-pick a number."""
        
        # Verify game is still in playing state
        current_round = await self.get_current_round()
        if not current_round or current_round.status != 'playing':
            return
        
        # Verify it's still the expected player's turn (no race condition)
        current_turn_id = await self.get_current_turn_id()
        if current_turn_id != expected_player_id:
            return  # Turn already changed, ignore
        
        # Get the player and their unmarked numbers
        round_player = await self.get_round_player_by_id(expected_player_id)
        if not round_player:
            return
        
        unmarked_numbers = await self.get_player_unmarked_numbers(expected_player_id)
        if not unmarked_numbers:
            return  # No numbers left (shouldn't happen normally)
        
        # Pick a random number from their board
        auto_number = random.choice(unmarked_numbers)
        
        # Call the number using atomic operation
        success, error = await self.add_called_number_atomic(auto_number, expected_player_id)
        if not success:
            # Number was somehow already called, try again with different number
            unmarked_numbers. remove(auto_number)
            if unmarked_numbers:
                auto_number = random.choice(unmarked_numbers)
                success, error = await self.add_called_number_atomic(auto_number, expected_player_id)
            if not success:
                return
        
        # Check for winners
        winners = await self.check_winners(expected_player_id)
        
        # Get room and next turn
        room = await self.get_room()
        next_player_data = await self.set_next_turn()
        
        # Get updated data
        round_players = await self.get_round_players_data()
        called_numbers = await self.get_called_numbers()
        show_score = room.settings_show_score
        
        # Get player info for broadcast
        member = await self.get_member_by_round_player_id(expected_player_id)
        member_name = member.display_name if member else "Unknown"
        member_id = member.id if member else None
        
        # Broadcast the auto-picked number
        await self. channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'number_called',
                'number': auto_number,
                'called_by': {
                    'id': expected_player_id,
                    'member_id': member_id,
                    'name': member_name,
                },
                'is_auto_pick': True,  # NEW: Flag to indicate auto-pick
                'called_numbers': called_numbers,
                'next_turn':  next_player_data,
                'duration': room.settings_turn_duration,
                'deadline': (timezone.now() + timedelta(seconds=room.settings_turn_duration)).isoformat(),
                'round_players': round_players,
                'show_score': show_score,
            }
        )
        
        # Start timer for next player
        if next_player_data and not winners:
            await self.start_turn_timer(room.settings_turn_duration, next_player_data['id'])
        
        # Handle winners
        if winners:
            DisconnectionManager.cancel_turn_timer(self.room_code)
            await self. handle_game_won(winners)


async def handle_call_number(self, data):
    """Player calls a number."""
    member = await self.get_member()
    current_round = await self.get_current_round()
    room = await self.get_room()
    max_number = room.settings_board_size ** 2
    
    if not member or not current_round: 
        return
    
    if current_round.status != 'playing':
        await self.send_error('Game not in progress')
        return
    
    number = data. get('number')
    if not isinstance(number, int) or number < 1 or number > max_number:
        await self.send_error(f'Invalid number (must be 1-{max_number})')
        return
    
    round_player = await self.get_round_player(member.id)
    if not round_player:
        return
    
    # Check turn
    current_turn_id = await self.get_current_turn_id()
    if current_turn_id != round_player.id:
        await self.send_error('Not your turn')
        return
    
    called_numbers = await self.get_called_numbers()
    if number in called_numbers:
        await self.send_error('Number already called')
        return
    
    # ✅ Cancel the turn timer since player made a move
    DisconnectionManager.cancel_turn_timer(self.room_code)
    
    # Call the number
    success, error = await self.add_called_number_atomic(number, round_player.id)
    if not success:
        await self.send_error(error or 'Failed to call number')
        return
    
    # Check for winners
    winners = await self.check_winners(round_player.id)
    
    # Get next turn
    next_player_data = await self.set_next_turn()
    
    # Get updated data
    round_players = await self.get_round_players_data()
    called_numbers = await self.get_called_numbers()
    show_score = room.settings_show_score
    
    await self.channel_layer.group_send(
        self.room_group_name,
        {
            'type': 'number_called',
            'number': number,
            'called_by':  {
                'id': round_player.id,
                'member_id': member.id,
                'name':  member.display_name,
            },
            'is_auto_pick': False,  # ✅ Add this flag
            'called_numbers': called_numbers,
            'next_turn': next_player_data,
            'duration': room.settings_turn_duration,
            'deadline': (timezone.now() + timedelta(seconds=room.settings_turn_duration)).isoformat(),
            'round_players': round_players,
            'show_score': show_score,
        }
    )
    
    # ✅ Start timer for next player (if game continues)
    if next_player_data and not winners:
        await self.start_turn_timer(room.settings_turn_duration, next_player_data['id'])
    
    # Handle winners
    if winners:
        DisconnectionManager.cancel_turn_timer(self.room_code)
        await self.handle_game_won(winners)