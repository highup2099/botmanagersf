"""
Configuration settings for Spotify Manager.
Loads from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""
    
    # Base directories
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    DATA_DIR = BASE_DIR / "data"
    LOGS_DIR = BASE_DIR / "logs"
    PROFILES_DIR = BASE_DIR / "profiles"
    
    # Ensure directories exist
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR}/spotify_manager.db")
    
    # Spotify OAuth
    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
    
    # Application
    APP_ENV = os.getenv("APP_ENV", "development")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # Browser
    BROWSER_TYPE = os.getenv("BROWSER_TYPE", "chromium")
    DEFAULT_HEADLESS = os.getenv("DEFAULT_HEADLESS", "false").lower() == "true"
    
    # Workers
    MAX_WORKERS = int(os.getenv("MAX_WORKERS", "5"))
    
    # Valid worker counts for GUI
    VALID_WORKER_COUNTS = [1, 2, 3, 4, 5, 10]


settings = Settings()
