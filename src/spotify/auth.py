"""
Spotify OAuth authentication service.
Uses official Spotify OAuth flow - never stores passwords.
"""

import os
from typing import Optional, Dict
from datetime import datetime, timedelta
from authlib.integrations.requests_client import OAuth2Session
from authlib.oauth2.rfc6749 import OAuth2Token

from src.config.settings import settings


class SpotifyAuthError(Exception):
    """Exception raised for Spotify authentication errors."""
    pass


class SpotifyAuthService:
    """
    Handles Spotify OAuth authentication.
    
    Uses Authlib for OAuth2 flow with PKCE support.
    Tokens should be stored securely per profile.
    """
    
    AUTH_URL = "https://accounts.spotify.com/authorize"
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    
    # Required scopes for playback control and playlist management
    SCOPES = [
        "user-read-private",
        "user-read-email",
        "user-read-playback-state",
        "user-modify-playback-state",
        "playlist-read-private",
        "playlist-modify-public",
        "playlist-modify-private",
        "user-library-read",
        "user-library-modify"
    ]
    
    def __init__(self):
        self.client_id = settings.SPOTIFY_CLIENT_ID
        self.client_secret = settings.SPOTIFY_CLIENT_SECRET
        self.redirect_uri = settings.SPOTIFY_REDIRECT_URI
        
        if not self.client_id or not self.client_secret:
            raise SpotifyAuthError(
                "Spotify credentials not configured. "
                "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env"
            )
    
    def get_authorization_url(self, state: str) -> str:
        """
        Generate authorization URL for OAuth flow.
        
        Args:
            state: Random state string for CSRF protection
            
        Returns:
            Authorization URL to present to user
        """
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.SCOPES),
            "state": state,
            "show_dialog": "false"
        }
        
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.AUTH_URL}?{query_string}"
    
    def exchange_code_for_token(self, code: str, state: str) -> Dict:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from callback
            state: State string from callback (should match original)
            
        Returns:
            Token dictionary with access_token, refresh_token, expires_in
        """
        try:
            session = OAuth2Session(
                self.client_id,
                self.client_secret,
                scope=" ".join(self.SCOPES)
            )
            
            token = session.fetch_token(
                self.TOKEN_URL,
                code=code,
                redirect_uri=self.redirect_uri
            )
            
            return dict(token)
            
        except Exception as e:
            raise SpotifyAuthError(f"Failed to exchange code for token: {e}")
    
    def refresh_access_token(self, refresh_token: str) -> Dict:
        """
        Refresh an expired access token.
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            New token dictionary
        """
        try:
            session = OAuth2Session(
                self.client_id,
                self.client_secret,
                scope=" ".join(self.SCOPES)
            )
            
            token = session.refresh_token(
                self.TOKEN_URL,
                refresh_token=refresh_token
            )
            
            return dict(token)
            
        except Exception as e:
            raise SpotifyAuthError(f"Failed to refresh token: {e}")
    
    def validate_token(self, access_token: str) -> bool:
        """
        Validate if an access token is still valid.
        
        Args:
            access_token: Access token to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            session = OAuth2Session(token={"access_token": access_token})
            response = session.get(
                "https://api.spotify.com/v1/me",
                timeout=10
            )
            return response.status_code == 200
        except Exception:
            return False
    
    def get_current_user(self, access_token: str) -> Optional[Dict]:
        """
        Get current authenticated user info.
        
        Args:
            access_token: Valid access token
            
        Returns:
            User info dictionary or None
        """
        try:
            session = OAuth2Session(token={"access_token": access_token})
            response = session.get(
                "https://api.spotify.com/v1/me",
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None


# Global instance (lazy initialization)
_auth_service: Optional[SpotifyAuthService] = None


def get_spotify_auth() -> SpotifyAuthService:
    """Get or create Spotify auth service instance."""
    global _auth_service
    if _auth_service is None:
        try:
            _auth_service = SpotifyAuthService()
        except SpotifyAuthError:
            # Return None if not configured - app can still run without Spotify
            return None
    return _auth_service
