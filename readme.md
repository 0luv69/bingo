# 🎱 Bingo Web App

A real-time multiplayer Bingo game built with Django and WebSockets.  Players join persistent rooms, arrange their boards, and compete in turn-based gameplay to complete 5 lines first!

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Django](https://img.shields.io/badge/Django-4.x-green.svg)
![Channels](https://img.shields.io/badge/Django_Channels-4.x-orange.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## 📋 Table of Contents

- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Architecture Overview](#-architecture-overview)
- [Game Flow](#-game-flow)
- [Installation](#-installation)
- [Project Structure](#-project-structure)
- [Data Models](#-data-models)
- [WebSocket API](#-websocket-api)
- [Session Management](#-session-management)
- [Contributing](#-contributing)

---

## ✨ Features

- **Persistent Rooms** - Rooms survive across multiple game rounds
- **Guest Play** - No login required (session-based identification)
- **Real-time Updates** - WebSocket-powered live game state
- **Drag & Drop Board Setup** - Arrange your 5x5 board before playing
- **Turn-based Gameplay** - Fair, ordered number calling
- **Multiple Win Detection** - Supports ties when players complete simultaneously
- **Host Controls** - Kick players, adjust settings, start new rounds
- **Randomized Turn Order** - Fresh turn sequence each round

---

## 🛠 Tech Stack

| Layer                   | Technology                               |
| ----------------------- | ---------------------------------------- |
| **Backend**       | Django 4.x                               |
| **WebSockets**    | Django Channels + Daphne (ASGI)          |
| **Database**      | SQLite (development)                     |
| **Frontend**      | Tailwind CSS + Vanilla JavaScript        |
| **Channel Layer** | InMemoryChannelLayer (no Redis required) |

---

## 🏗 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT (Browser)                        │
│  ┌─────────────────┐              ┌─────────────────────────┐  │
│  │   HTTP Requests │              │   WebSocket Connection  │  │
│  │   (Join/Create) │              │   (Real-time events)    │  │
│  └────────┬────────┘              └────────────┬────────────┘  │
└───────────┼────────────────────────────────────┼────────────────┘
            │                                    │
            ▼                                    ▼
┌───────────────────────┐          ┌──────────────────────────────┐
│     Django Views      │          │    Django Channels Consumer  │
│   (views.py)          │          │    (consumers.py)            │
│                       │          │                              │
│  • create_room()      │          │  • connect()                 │
│  • join_room()        │          │  • receive() → handle_*      │
│  • lobby()            │          │  • disconnect()              │
└───────────┬───────────┘          └──────────────┬───────────────┘
            │                                     │
            │         ┌───────────────┐           │
            └────────▶│    Session    │◀──────────┘
                      │   (Server)    │
                      │               │
                      │ member_id:  42 │
                      │ room_code: X  │
                      └───────┬───────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │    Database     │
                    │                 │
                    │  • Room         │
                    │  • RoomMember   │
                    │  • GameRound    │
                    │  • RoundPlayer  │
                    └─────────────────┘
```

---

## 🎮 Game Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   WAITING    │────▶│    SETUP     │────▶│   PLAYING    │────▶│   FINISHED   │
│              │     │              │     │              │     │              │
│ • Host       │     │ • Arrange    │     │ • Call       │     │ • Show       │
│   creates    │     │   board      │     │   numbers    │     │   winners    │
│ • Players    │     │ • Mark       │     │ • Check      │     │ • New round  │
│   join       │     │   ready      │     │   lines      │     │   option     │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                                                │
                                                ▼
                                    ┌─────────────────────┐
                                    │  First to 5 lines   │
                                    │       WINS!         │
                                    └─────────────────────┘
```

### Detailed Steps:

1. **Host creates Room** → Gets unique 6-character code
2. **Players join** → Enter code and display name
3. **Host starts game** → Setup phase begins
4. **Setup phase** → Players drag/drop to arrange 5x5 board, mark ready
5. **Playing phase** → Turn-based number calling (1-25)
6. **Win detection** → First player to complete 5 lines wins
7. **New round** → Host can start another round in same room

---

## 🚀 Installation

### Prerequisites

- Python 3.10+
- pip

### Setup

```bash
# Clone the repository
git clone https://github.com/0luv69/bingo.git
cd bingo/bingo_project

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start the development server
python manage.py runserver
```

### Access the app

Open `http://localhost:8000` in your browser.

---

## 📁 Project Structure

```
bingo/
└── bingo_project/
    ├── bingo_project/
    │   ├── settings.py      # Django settings
    │   ├── urls.py          # Root URL configuration
    │   └── asgi.py          # ASGI config for Channels
    │
    ├── game/
    │   ├── models.py        # Database models
    │   ├── views.py         # HTTP request handlers
    │   ├── consumers.py     # WebSocket handlers
    │   ├── utils.py         # Helper functions
    │   ├── routing.py       # WebSocket URL routing
    │   └── admin.py         # Django admin config
    │
    ├── templates/
    │   └── game/
    │       ├── home.html    # Landing page
    │       ├── lobby.html   # Game lobby
    │       └── game.html    # Game board
    │
    └── static/
        └── css/             # Tailwind styles
```

---

## 📊 Data Models

### Entity Relationship

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│    Room     │       │  RoomMember │       │  GameRound  │
├─────────────┤       ├─────────────┤       ├─────────────┤
│ code        │◀──┐   │ room (FK)   │   ┌──▶│ room (FK)   │
│ settings_*  │   └───│ display_name│   │   │ status      │
│ is_active   │       │ session_key │   │   │ round_number│
│ created_at  │───────│ role        │   │   │ called_nums │
└─────────────┘       │ is_active   │   │   │ current_turn│
                      └─────────────┘   │   └─────────────┘
                             │          │          │
                             │          │          │
                             ▼          │          ▼
                      ┌─────────────────┴───────────────┐
                      │          RoundPlayer            │
                      ├─────────────────────────────────┤
                      │ game_round (FK)                 │
                      │ room_member (FK)                │
                      │ board (5x5 JSON)                │
                      │ is_ready                        │
                      │ finished_lines (JSON)           │
                      │ turn_order                      │
                      └─────────────────────────────────┘
```

### Model Descriptions

| Model                         | Purpose                                         |
| ----------------------------- | ----------------------------------------------- |
| **Room**                | Persistent game room with settings              |
| **RoomMember**          | Player's membership in a room (survives rounds) |
| **GameRound**           | Single game instance within a room              |
| **RoundPlayer**         | Player's state for a specific round             |
| **CalledNumberHistory** | Audit log of called numbers                     |

---

## 🔌 WebSocket API

### Connection

```javascript
const socket = new WebSocket('ws://localhost:8000/ws/room/ABC123/');
```

### Client → Server Messages

| Type                | Description               | Payload                          |
| ------------------- | ------------------------- | -------------------------------- |
| `start_game`      | Host starts the game      | `{}`                           |
| `player_ready`    | Player marks ready        | `{}`                           |
| `update_board`    | Save board arrangement    | `{board: [[1,2,3,4,5], ... ]}` |
| `call_number`     | Call a number (your turn) | `{number: 15}`                 |
| `update_settings` | Change room settings      | `{settings: {...}}`            |
| `kick_player`     | Remove a player           | `{member_id: 42}`              |
| `new_round`       | Start new round           | `{}`                           |

### Server → Client Messages

| Type                    | Description                  |
| ----------------------- | ---------------------------- |
| `player_connected`    | Player joined the room       |
| `player_disconnected` | Player left the room         |
| `game_starting`       | Setup phase started          |
| `player_ready`        | A player marked ready        |
| `game_started`        | Playing phase started        |
| `number_called`       | Number was called            |
| `game_won`            | Game finished with winner(s) |
| `settings_updated`    | Room settings changed        |
| `player_kicked`       | Player was removed           |
| `new_round_created`   | New round started            |
| `error`               | Error message                |

### Example:  Calling a Number

```javascript
// Client sends
socket.send(JSON.stringify({
    type: 'call_number',
    number: 17
}));

// Server broadcasts to all
{
    "type": "number_called",
    "number": 17,
    "called_by": {"id": 1, "member_id": 42, "name": "Alice"},
    "called_numbers": [5, 12, 17],
    "next_turn": {"id": 2, "member_id": 55, "name": "Bob"},
    "round_players": [...]
}
```

---

## 🔐 Session Management

### How Player Identity Works

```
┌─────────────────────────────────────────────────────────────────┐
│  The browser only stores a SESSION ID (cookie)                  │
│  All actual data is stored on the SERVER                        │
└─────────────────────────────────────────────────────────────────┘

    BROWSER                              SERVER
    ───────                              ──────
    Cookie:                               Session Storage: 
    sessionid="abc123"    ──────────▶    "abc123" → {member_id: 42}
                                       
                                         Database: 
                                         member_id=42 → Alice, Room BINGO1
```

### Flow When Player Joins

```python
# 1. View creates/gets member and stores in session
request. session['current_member_id'] = member. id  # Stored on SERVER

# 2. Browser receives session cookie
Set-Cookie: sessionid=abc123xyz

# 3. WebSocket connection sends cookie automatically
# 4. Consumer reads member_id from session
session = self.scope['session']
self.member_id = session.get('current_member_id')
```

---

## 🎯 Winning Lines

The game checks 12 possible winning lines:

```
ROWS (5):          COLUMNS (5):       DIAGONALS (2):
─────────          ────────────       ──────────────
[0,1,2,3,4]        [0,5,10,15,20]     [0,6,12,18,24]
[5,6,7,8,9]        [1,6,11,16,21]     [4,8,12,16,20]
[10,11,12,13,14]   [2,7,12,17,22]
[15,16,17,18,19]   [3,8,13,18,23]
[20,21,22,23,24]   [4,9,14,19,24]

Board Layout (indices):
┌────┬────┬────┬────┬────┐
│  0 │  1 │  2 │  3 │  4 │
├────┼────┼────┼────┼────┤
│  5 │  6 │  7 │  8 │  9 │
├────┼────┼────┼────┼────┤
│ 10 │ 11 │ 12 │ 13 │ 14 │
├────┼────┼────┼────┼────┤
│ 15 │ 16 │ 17 │ 18 │ 19 │
├────┼────┼────┼────┼────┤
│ 20 │ 21 │ 22 │ 23 │ 24 │
└────┴────┴────┴────┴────┘
```

**First player to complete 5 lines wins! **

---

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Django Channels team for excellent WebSocket support
- Tailwind CSS for beautiful styling utilities

---

<p align="center">
  Made with ❤️ for Bingo lovers
</p>
