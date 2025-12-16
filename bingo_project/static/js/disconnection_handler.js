/**
 * Disconnection Handler for Bingo Game
 * Handles grace periods, vote kicks, and bot control UI
 */

class DisconnectionHandler {
    constructor(socket, currentMemberId) {
        this.socket = socket;
        this.currentMemberId = currentMemberId;
        this.disconnectedPlayers = new Map(); // member_id -> {timer, deadline, element}
        this.activeVoteKick = null;
        
        this.initVoteModal();
    }
    
    // ═══════════════════════════════════════════════════
    // INITIALIZATION
    // ═══════════════════════════════════════════════════
    
    initVoteModal() {
        // Create vote modal if not exists
        if (!document. getElementById('vote-kick-modal')) {
            const modalHtml = `
                <div id="vote-kick-modal" class="fixed inset-0 bg-black/50 z-50 hidden flex items-center justify-center p-4">
                    <div class="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl transform transition-all">
                        <div class="text-center mb-4">
                            <div class="w-16 h-16 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-3">
                                <svg class="w-8 h-8 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                                </svg>
                            </div>
                            <h3 class="text-xl font-bold text-slate-900">Player Disconnected</h3>
                            <p id="vote-kick-message" class="text-slate-600 mt-2"></p>
                        </div>
                        
                        <div id="vote-progress" class="mb-5">
                            <div class="flex justify-between text-sm font-medium mb-2">
                                <span class="text-red-600">Kick:  <span id="kick-votes">0</span></span>
                                <span class="text-emerald-600">Keep: <span id="keep-votes">0</span></span>
                            </div>
                            <div class="h-3 bg-slate-200 rounded-full overflow-hidden">
                                <div id="vote-bar-kick" class="h-full bg-red-500 transition-all duration-300" style="width: 0%"></div>
                            </div>
                            <p class="text-xs text-slate-500 mt-2 text-center">
                                <span id="votes-cast">0</span> of <span id="total-voters">0</span> players voted
                            </p>
                        </div>
                        
                        <div id="vote-buttons" class="flex gap-3">
                            <button id="btn-vote-kick" 
                                    class="flex-1 py-3 px-4 bg-red-500 hover:bg-red-600 active:bg-red-700 text-white rounded-xl font-semibold transition-all transform hover:scale-[1.02] active:scale-[0.98] flex items-center justify-center gap-2">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                </svg>
                                Kick
                            </button>
                            <button id="btn-vote-keep" 
                                    class="flex-1 py-3 px-4 bg-emerald-500 hover: bg-emerald-600 active:bg-emerald-700 text-white rounded-xl font-semibold transition-all transform hover:scale-[1.02] active:scale-[0.98] flex items-center justify-center gap-2">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                                </svg>
                                Keep
                            </button>
                        </div>
                        
                        <div id="vote-waiting" class="hidden text-center py-4">
                            <div class="inline-flex items-center gap-2 text-slate-500">
                                <svg class="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Waiting for other votes...
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            
            // Add event listeners
            document.getElementById('btn-vote-kick').addEventListener('click', () => this.castVote('kick'));
            document.getElementById('btn-vote-keep').addEventListener('click', () => this.castVote('keep'));
        }
        
        this.voteModal = document.getElementById('vote-kick-modal');
    }
    
    // ═══════════════════════════════════════════════════
    // MESSAGE HANDLERS (called from WebSocket onmessage)
    // ═══════════════════════════════════════════════════
    
    handlePlayerDisconnected(data) {
        const { member_id, member_name, grace_period, deadline } = data;
        
        // Don't show for self (shouldn't happen but safety check)
        if (member_id === this.currentMemberId) return;
        
        // Show notification
        showNotification(`${member_name} disconnected.  Waiting ${grace_period}s... `, 'warning');
        
        // Start countdown timer UI
        this.startDisconnectionCountdown(member_id, member_name, deadline, grace_period);
        
        // Update player card UI
        this.updatePlayerCardStatus(member_id, 'disconnected');
    }
    
    handlePlayerConnected(data) {
        const { member_id, member_name, is_reconnection } = data;
        
        // Clear disconnection timer
        this.clearDisconnectionCountdown(member_id);
        
        // Update player card UI
        this.updatePlayerCardStatus(member_id, 'connected');
        
        // Remove bot badge if any
        this.updateBotBadge(member_id, false);
        
        if (is_reconnection) {
            showNotification(`${member_name} reconnected! `, 'success');
        } else if (member_id !== this.currentMemberId) {
            showNotification(`${member_name} joined the room`, 'info');
        }
    }
    
    handlePlayerBotControlled(data) {
        const { member_id, member_name, message } = data;
        
        showNotification(message, 'warning');
        
        // Clear disconnection countdown
        this.clearDisconnectionCountdown(member_id);
        
        // Update player card with bot badge
        this.updatePlayerCardStatus(member_id, 'bot');
        this.updateBotBadge(member_id, true);
    }
    
    handlePlayerReconnectedFromBot(data) {
        const { member_id, member_name, message } = data;
        
        showNotification(message, 'success');
        
        // Remove bot badge and restore normal status
        this.updateBotBadge(member_id, false);
        this.updatePlayerCardStatus(member_id, 'connected');
    }
    
    handleVoteKickStarted(data) {
        const { target_member_id, target_member_name, message, total_voters } = data;
        
        // Don't show vote modal to the disconnected player themselves
        if (target_member_id === this.currentMemberId) {
            return;
        }
        
        this.activeVoteKick = {
            targetId: target_member_id,
            targetName: target_member_name,
            hasVoted: false
        };
        
        // Reset and show vote modal
        document.getElementById('vote-kick-message').textContent = message;
        document.getElementById('vote-buttons').classList.remove('hidden');
        document.getElementById('vote-waiting').classList.add('hidden');
        document.getElementById('kick-votes').textContent = '0';
        document.getElementById('keep-votes').textContent = '0';
        document.getElementById('votes-cast').textContent = '0';
        document.getElementById('total-voters').textContent = total_voters;
        document.getElementById('vote-bar-kick').style.width = '0%';
        
        this.voteModal.classList.remove('hidden');
        
        // Clear disconnection countdown for this player (vote is happening)
        this.clearDisconnectionCountdown(target_member_id);
    }
    
    handleVoteUpdated(data) {
        const { target_member_id, votes, total_voters, total_voted } = data;
        
        // Update vote counts
        document. getElementById('kick-votes').textContent = votes. kick;
        document.getElementById('keep-votes').textContent = votes.keep;
        document.getElementById('votes-cast').textContent = total_voted;
        document.getElementById('total-voters').textContent = total_voters;
        
        // Update progress bar
        const total = votes.kick + votes.keep;
        const kickPercent = total > 0 ? (votes. kick / total) * 100 : 0;
        document. getElementById('vote-bar-kick').style.width = `${kickPercent}%`;
    }
    
    handleVoteKickCompleted(data) {
        const { result, target_member_id, target_member_name, message, grace_period } = data;
        
        // Hide vote modal
        this.voteModal.classList.add('hidden');
        this.activeVoteKick = null;
        
        if (result === 'kick') {
            showNotification(message, 'info');
            // Player card will be removed by members list update
        } else {
            showNotification(message, 'warning');
            // Restart countdown for the kept player
            if (grace_period) {
                const deadline = new Date(Date.now() + grace_period * 1000).toISOString();
                this.startDisconnectionCountdown(target_member_id, target_member_name, deadline, grace_period);
            }
        }
    }
    
    handleVoteKickCancelled(data) {
        const { member_id, message } = data;
        
        // Hide vote modal if it was for this player
        if (this.activeVoteKick && this.activeVoteKick.targetId === member_id) {
            this.voteModal.classList.add('hidden');
            this.activeVoteKick = null;
        }
        
        showNotification(message, 'success');
    }
    
    // ═══════════════════════════════════════════════════
    // UI HELPERS
    // ═══════════════════════════════════════════════════
    
    startDisconnectionCountdown(memberId, memberName, deadline, gracePeriod) {
        // Clear existing timer for this member
        this.clearDisconnectionCountdown(memberId);
        
        const deadlineTime = new Date(deadline).getTime();
        
        // Create countdown element
        const countdownEl = document.createElement('div');
        countdownEl.id = `disconnect-countdown-${memberId}`;
        countdownEl.className = 'fixed bottom-4 left-4 bg-amber-500 text-white px-4 py-2 rounded-lg shadow-lg z-40 flex items-center gap-2';
        countdownEl.innerHTML = `
            <svg class="w-5 h-5 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
            <span><strong>${memberName}</strong>: <span class="countdown-time">${gracePeriod}</span>s</span>
        `;
        document.body.appendChild(countdownEl);
        
        // Update countdown every second
        const updateCountdown = () => {
            const now = Date.now();
            const remaining = Math.max(0, Math.ceil((deadlineTime - now) / 1000));
            
            const timeSpan = countdownEl.querySelector('.countdown-time');
            if (timeSpan) {
                timeSpan.textContent = remaining;
            }
            
            // Change color when low
            if (remaining <= 5) {
                countdownEl. classList.remove('bg-amber-500');
                countdownEl.classList. add('bg-red-500');
            }
            
            if (remaining <= 0) {
                this.clearDisconnectionCountdown(memberId);
            }
        };
        
        updateCountdown();
        const timer = setInterval(updateCountdown, 1000);
        
        this.disconnectedPlayers.set(memberId, { 
            timer, 
            deadline: deadlineTime, 
            element: countdownEl,
            name: memberName 
        });
    }
    
    clearDisconnectionCountdown(memberId) {
        const data = this.disconnectedPlayers. get(memberId);
        if (data) {
            clearInterval(data.timer);
            if (data.element && data.element.parentNode) {
                data.element. remove();
            }
            this. disconnectedPlayers.delete(memberId);
        }
    }
    
    updatePlayerCardStatus(memberId, status) {
        // Find player card by member ID
        const playerCard = document.querySelector(`[data-member-id="${memberId}"]`);
        if (!playerCard) return;
        
        // Remove all status classes first
        playerCard.classList.remove('opacity-50', 'border-red-400', 'border-purple-400', 'border-2');
        
        // Remove existing badges
        const existingBadge = playerCard.querySelector('.status-badge');
        if (existingBadge) existingBadge.remove();
        
        const nameContainer = playerCard.querySelector('.player-name') || playerCard.querySelector('.font-medium');
        
        if (status === 'disconnected') {
            playerCard.classList.add('opacity-50', 'border-2', 'border-red-400');
            
            if (nameContainer) {
                const badge = document.createElement('span');
                badge.className = 'status-badge ml-2 text-xs bg-red-100 text-red-600 px-2 py-0.5 rounded-full inline-flex items-center gap-1';
                badge.innerHTML = `
                    <span class="w-1. 5 h-1.5 bg-red-500 rounded-full animate-pulse"></span>
                    Offline
                `;
                nameContainer.appendChild(badge);
            }
        } else if (status === 'bot') {
            playerCard.classList.add('border-2', 'border-purple-400');
            // Bot badge added separately
        }
        // 'connected' status = normal appearance (classes already removed)
    }
    
    updateBotBadge(memberId, isBot) {
        const playerCard = document.querySelector(`[data-member-id="${memberId}"]`);
        if (!playerCard) return;
        
        // Remove existing bot badge
        const existingBotBadge = playerCard.querySelector('.bot-badge');
        if (existingBotBadge) existingBotBadge.remove();
        
        if (isBot) {
            const nameContainer = playerCard.querySelector('.player-name') || playerCard.querySelector('.font-medium');
            if (nameContainer) {
                const badge = document.createElement('span');
                badge.className = 'bot-badge ml-2 text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full inline-flex items-center gap-1';
                badge.innerHTML = `
                    <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M10 2a1 1 0 011 1v1.323l3.954 1.582 1.599-. 8a1 1 0 01.894 1.79l-1.233.616 1.738 5.42a1 1 0 01-. 285 1.05A3.989 3.989 0 0115 15a3.989 3.989 0 01-2.667-1.019 1 1 0 01-. 285-1.05l1.715-5.349L11 6.477V16h2a1 1 0 110 2H7a1 1 0 110-2h2V6.477L6.237 7.582l1.715 5.349a1 1 0 01-. 285 1.05A3.989 3.989 0 015 15a3.989 3.989 0 01-2.667-1.019 1 1 0 01-.285-1.05l1.738-5.42-1.233-.617a1 1 0 01.894-1.788l1.599.799L9 4.323V3a1 1 0 011-1z"/>
                    </svg>
                    Bot
                `;
                nameContainer.appendChild(badge);
            }
        }
    }
    
    // ═══════════════════════════════════════════════════
    // ACTIONS
    // ═══════════════════════════════════════════════════
    
    castVote(vote) {
        if (!this. activeVoteKick || this.activeVoteKick. hasVoted) return;
        
        this.socket.send(JSON.stringify({
            type: 'cast_vote',
            target_member_id: this.activeVoteKick.targetId,
            vote: vote  // 'kick' or 'keep'
        }));
        
        this.activeVoteKick. hasVoted = true;
        
        // Hide buttons, show waiting
        document.getElementById('vote-buttons').classList.add('hidden');
        document.getElementById('vote-waiting').classList.remove('hidden');
    }
    
    // Clean up when leaving page
    destroy() {
        // Clear all timers
        for (const [memberId, data] of this.disconnectedPlayers) {
            clearInterval(data. timer);
            if (data. element && data.element.parentNode) {
                data.element. remove();
            }
        }
        this.disconnectedPlayers.clear();
        
        // Remove vote modal
        if (this.voteModal && this.voteModal.parentNode) {
            this.voteModal.remove();
        }
    }
}

// Global instance - will be initialized in page scripts
let disconnectionHandler = null;