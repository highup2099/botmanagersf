# Spotify Manager

A legitimate internal music-management tool for Spotify. Uses official OAuth/API capabilities where available.

## Features

- **Profile Management**: Isolated browser sessions per profile
- **Task Queue System**: Background task processing with worker pool
- **Spotify OAuth**: Secure authentication (no password storage)
- **SQLite Database**: Proper data persistence with SQLAlchemy ORM
- **Structured Logging**: Real-time activity monitoring
- **Clean GUI**: CustomTkinter-based desktop interface

## Architecture

```
botmanagersf/
├── app.py                 # Main entry point
├── requirements.txt       # Python dependencies
├── .env.example          # Environment template
├── .gitignore            # Git ignore rules
├── README.md             # This file
│
├── data/                 # SQLite database storage
│   └── spotify_manager.db
│
├── profiles/             # Browser profile directories
│   └── <profile_id>/
│
├── logs/                 # Application logs
│
├── src/
│   ├── gui/              # CustomTkinter UI components
│   │   ├── app_window.py
│   │   ├── profile_table.py
│   │   └── ...
│   ├── database/         # SQLAlchemy models & repositories
│   │   ├── models.py
│   │   ├── database.py
│   │   └── repositories.py
│   ├── spotify/          # OAuth & API service
│   │   ├── auth.py
│   │   ├── client.py
│   │   └── service.py
│   ├── browser/          # Playwright worker abstraction
│   │   ├── browser_worker.py
│   │   └── profile_manager.py
│   ├── tasks/            # Task queue & worker pool
│   │   ├── task_queue.py
│   │   ├── worker_pool.py
│   │   └── task_manager.py
│   ├── logging/          # Structured logging
│   │   └── app_logger.py
│   └── config/           # Application settings
│       └── settings.py
│
└── tests/                # Unit tests
```

## Requirements

- Python 3.11+
- macOS (Apple Silicon supported), Linux, or Windows

## Installation (macOS)

```bash
cd /path/to/botmanagersf
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

## Configuration

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your Spotify OAuth credentials:
   ```
   SPOTIFY_CLIENT_ID=your_client_id_here
   SPOTIFY_CLIENT_SECRET=your_client_secret_here
   SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
   ```

   Get credentials from: https://developer.spotify.com/dashboard

## Running Tests

```bash
python -m unittest tests.test_app -v
```

## Security Notes

- **Never** store Spotify passwords in source code, CSV, XLSX, or SQLite
- OAuth tokens are stored in memory (MVP) - production should use encrypted storage
- Proxy passwords are encrypted using `cryptography` library
- `.env` file is gitignored - never commit secrets

## Database Schema

The application uses SQLite with these entities:

- **Profile**: User profiles with isolated browser sessions
- **Proxy**: Proxy configurations (encrypted secrets)
- **Playlist**: Spotify playlists associated with profiles
- **Task**: Background tasks (track_review, playlist_add, playback_control)
- **TaskRun**: Individual task executions
- **ActivityLog**: Application activity logs

## Usage

1. Launch the application: `python app.py`
2. Add profiles via the Profiles tab
3. Configure Spotify OAuth for each profile
4. Create tasks (playlist management, track review, playback control)
5. Monitor activity in the Activity Log panel

## License

Internal use only.
