"""
Spotify service layer.
Combines auth and client for high-level operations.
"""

from typing import Optional, Dict, List
from datetime import datetime, timedelta

from src.spotify.auth import SpotifyAuthService, get_spotify_auth, SpotifyAuthError
from src.spotify.client import SpotifyClient, SpotifyAPIError
from src.spotify.oauth_callback import start_oauth_listener, stop_oauth_listener, wait_for_oauth_callback, get_oauth_callback_url
from src.logging_module.app_logger import get_logger


logger = get_logger()


class TokenStorage:
    """
    In-memory token storage (for MVP).
    In production, use encrypted database or secure keychain.
    """
    
    def __init__(self):
        self._tokens: Dict[int, Dict] = {}  # profile_id -> token dict
    
    def store(self, profile_id: int, token_data: Dict) -> None:
        """Store tokens for a profile."""
        self._tokens[profile_id] = {
            **token_data,
            "stored_at": datetime.utcnow()
        }
    
    def get(self, profile_id: int) -> Optional[Dict]:
        """Get tokens for a profile."""
        return self._tokens.get(profile_id)
    
    def delete(self, profile_id: int) -> None:
        """Delete tokens for a profile."""
        self._tokens.pop(profile_id, None)
    
    def needs_refresh(self, profile_id: int) -> bool:
        """Check if token needs refresh (5 min buffer)."""
        token_data = self.get(profile_id)
        if not token_data:
            return True
        
        expires_at = token_data.get("expires_at")
        if not expires_at:
            return True
        
        # Refresh 5 minutes before expiry
        return datetime.utcnow() > (expires_at - timedelta(minutes=5))


class SpotifyService:
    """
    High-level Spotify service.
    
    Provides business logic operations combining auth and API client.
    """
    
    def __init__(self):
        self.auth_service: Optional[SpotifyAuthService] = get_spotify_auth()
        self.token_storage = TokenStorage()
        self._clients: Dict[int, SpotifyClient] = {}  # profile_id -> client
        self._pending_states: Dict[str, Dict] = {}  # state -> {profile_id, started_at}
    
    def is_configured(self) -> bool:
        """Check if Spotify OAuth is configured."""
        return self.auth_service is not None
    
    def initiate_auth(self, profile_id: int) -> str:
        """
        Start OAuth flow for a profile.
        
        Args:
            profile_id: Profile ID to authenticate
            
        Returns:
            Authorization URL to present to user
        """
        if not self.auth_service:
            raise SpotifyAuthError("Spotify not configured")
        
        import secrets
        state = secrets.token_urlsafe(32)
        # Store state for validation (in production, use Redis or similar)
        
        auth_url = self.auth_service.get_authorization_url(state)
        logger.spotify_auth(f"OAuth initiated for profile {profile_id}", profile_id)
        
        return auth_url
    
    def initiate_auth_with_callback(self, profile_id: int, port: int = 8888) -> str:
        """
        Start OAuth flow with local callback server.
        
        Args:
            profile_id: Profile ID to authenticate
            port: Port for local callback server
            
        Returns:
            Authorization URL to open in browser
        """
        if not self.auth_service:
            raise SpotifyAuthError("Spotify not configured")
        
        # Start callback listener
        if not start_oauth_listener(port):
            raise SpotifyAuthError(f"Failed to start callback server on port {port}")
        
        import secrets
        state = secrets.token_urlsafe(32)
        
        # Get actual callback URL
        callback_url = get_oauth_callback_url()
        
        # Build authorization URL with correct redirect_uri
        params = {
            "client_id": self.auth_service.client_id,
            "response_type": "code",
            "redirect_uri": callback_url,
            "scope": " ".join(self.auth_service.SCOPES),
            "state": state,
            "show_dialog": "false"
        }
        
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        auth_url = f"{self.auth_service.AUTH_URL}?{query_string}"
        
        logger.spotify_auth(f"OAuth initiated for profile {profile_id} with callback {callback_url}", profile_id)
        
        # Store state for later retrieval (simple in-memory for MVP)
        self._pending_states[state] = {
            'profile_id': profile_id,
            'started_at': datetime.utcnow()
        }
        
        return auth_url
    
    def complete_auth_with_callback(self, profile_id: int, timeout: float = 300.0) -> bool:
        """
        Complete OAuth flow by waiting for callback.
        
        Args:
            profile_id: Profile ID being authenticated
            timeout: Max time to wait for callback
            
        Returns:
            True if successful
        """
        if not self.auth_service:
            return False
        
        # Find pending state for this profile
        state = None
        for s, data in list(self._pending_states.items()):
            if data['profile_id'] == profile_id:
                state = s
                break
        
        if not state:
            logger.error("No pending OAuth state found", "SPOTIFY_AUTH_ERROR", profile_id)
            return False
        
        try:
            # Wait for callback
            callback_data = wait_for_oauth_callback(state, timeout=timeout)
            
            if not callback_data:
                logger.error("OAuth callback timeout", "SPOTIFY_AUTH_TIMEOUT", profile_id)
                return False
            
            error = callback_data.get('error')
            if error:
                logger.error(f"OAuth error: {error}", "SPOTIFY_AUTH_ERROR", profile_id)
                return False
            
            code = callback_data.get('code')
            if not code:
                logger.error("No authorization code in callback", "SPOTIFY_AUTH_ERROR", profile_id)
                return False
            
            # Exchange code for token
            token_data = self.auth_service.exchange_code_for_token(code, state)
            
            # Calculate absolute expiry time
            expires_in = token_data.get("expires_in", 3600)
            token_data["expires_at"] = datetime.utcnow() + timedelta(seconds=expires_in)
            
            # Store tokens
            self.token_storage.store(profile_id, token_data)
            
            # Create client instance
            self._clients[profile_id] = SpotifyClient(token_data["access_token"])
            
            logger.spotify_auth(f"OAuth completed for profile {profile_id}", profile_id)
            return True
            
        except SpotifyAuthError as e:
            logger.error(f"OAuth failed: {e}", "SPOTIFY_AUTH_FAILED", profile_id)
            return False
        finally:
            # Clean up pending state
            self._pending_states.pop(state, None)
    
    def complete_auth(self, profile_id: int, code: str, state: str) -> bool:
        """
        Complete OAuth flow with authorization code.
        
        Args:
            profile_id: Profile ID being authenticated
            code: Authorization code from callback
            state: State string from callback
            
        Returns:
            True if successful
        """
        if not self.auth_service:
            return False
        
        try:
            token_data = self.auth_service.exchange_code_for_token(code, state)
            
            # Calculate absolute expiry time
            expires_in = token_data.get("expires_in", 3600)
            token_data["expires_at"] = datetime.utcnow() + timedelta(seconds=expires_in)
            
            # Store tokens
            self.token_storage.store(profile_id, token_data)
            
            # Create client instance
            self._clients[profile_id] = SpotifyClient(token_data["access_token"])
            
            logger.spotify_auth(f"OAuth completed for profile {profile_id}", profile_id)
            return True
            
        except SpotifyAuthError as e:
            logger.error(f"OAuth failed: {e}", "SPOTIFY_AUTH_FAILED", profile_id)
            return False
    
    def _ensure_valid_token(self, profile_id: int) -> bool:
        """Ensure we have a valid token, refreshing if needed."""
        if not self.auth_service:
            return False
        
        if self.token_storage.needs_refresh(profile_id):
            token_data = self.token_storage.get(profile_id)
            if token_data and token_data.get("refresh_token"):
                try:
                    new_token_data = self.auth_service.refresh_access_token(
                        token_data["refresh_token"]
                    )
                    expires_in = new_token_data.get("expires_in", 3600)
                    new_token_data["expires_at"] = datetime.utcnow() + timedelta(seconds=expires_in)
                    self.token_storage.store(profile_id, new_token_data)
                    self._clients[profile_id] = SpotifyClient(new_token_data["access_token"])
                    logger.spotify_auth("Token refreshed", profile_id)
                except SpotifyAuthError:
                    self.token_storage.delete(profile_id)
                    self._clients.pop(profile_id, None)
                    return False
        
        return profile_id in self._clients
    
    def _get_client(self, profile_id: int) -> Optional[SpotifyClient]:
        """Get API client for profile, ensuring valid token."""
        if not self._ensure_valid_token(profile_id):
            return None
        return self._clients.get(profile_id)
    
    def get_current_user(self, profile_id: int) -> Optional[Dict]:
        """Get current user info for profile."""
        client = self._get_client(profile_id)
        if not client:
            return None
        
        try:
            return client.get_current_user()
        except SpotifyAPIError as e:
            logger.error(f"Failed to get user: {e}", "SPOTIFY_API_ERROR", profile_id)
            return None
    
    def get_playback_state(self, profile_id: int) -> Optional[Dict]:
        """Get current playback state."""
        client = self._get_client(profile_id)
        if not client:
            return None
        
        try:
            return client.get_playback_state()
        except SpotifyAPIError as e:
            logger.error(f"Failed to get playback state: {e}", "SPOTIFY_API_ERROR", profile_id)
            return None
    
    def start_playback(self, profile_id: int, context_uri: Optional[str] = None,
                       uris: Optional[List[str]] = None) -> bool:
        """Start playback."""
        client = self._get_client(profile_id)
        if not client:
            return False
        
        try:
            result = client.start_playback(context_uri=context_uri, uris=uris)
            if result:
                logger.info("Playback started", "PLAYBACK_START", profile_id)
            return result
        except SpotifyAPIError as e:
            logger.error(f"Failed to start playback: {e}", "PLAYBACK_ERROR", profile_id)
            return False
    
    def pause_playback(self, profile_id: int) -> bool:
        """Pause playback."""
        client = self._get_client(profile_id)
        if not client:
            return False
        
        try:
            result = client.pause_playback()
            if result:
                logger.info("Playback paused", "PLAYBACK_PAUSE", profile_id)
            return result
        except SpotifyAPIError as e:
            logger.error(f"Failed to pause playback: {e}", "PLAYBACK_ERROR", profile_id)
            return False
    
    def skip_to_next(self, profile_id: int) -> bool:
        """Skip to next track."""
        client = self._get_client(profile_id)
        if not client:
            return False
        
        try:
            result = client.skip_to_next()
            if result:
                logger.info("Skipped to next track", "PLAYBACK_SKIP", profile_id)
            return result
        except SpotifyAPIError as e:
            logger.error(f"Failed to skip: {e}", "PLAYBACK_ERROR", profile_id)
            return False
    
    def add_tracks_to_playlist(self, profile_id: int, playlist_id: str,
                                track_uris: List[str]) -> bool:
        """Add tracks to playlist."""
        client = self._get_client(profile_id)
        if not client:
            return False
        
        try:
            result = client.add_tracks_to_playlist(playlist_id, track_uris)
            if result:
                logger.info(f"Added {len(track_uris)} tracks to playlist", "PLAYLIST_ADD", profile_id)
            return result
        except SpotifyAPIError as e:
            logger.error(f"Failed to add tracks: {e}", "PLAYLIST_ERROR", profile_id)
            return False
    
    def save_track(self, profile_id: int, track_id: str) -> bool:
        """Save track to library."""
        client = self._get_client(profile_id)
        if not client:
            return False
        
        try:
            result = client.save_track(track_id)
            if result:
                logger.info(f"Saved track {track_id}", "TRACK_SAVE", profile_id)
            return result
        except SpotifyAPIError as e:
            logger.error(f"Failed to save track: {e}", "TRACK_ERROR", profile_id)
            return False
    
    def logout(self, profile_id: int) -> None:
        """Logout and clear tokens for profile."""
        self.token_storage.delete(profile_id)
        self._clients.pop(profile_id, None)
        logger.spotify_auth("Logged out", profile_id)


# Global service instance
_spotify_service: Optional[SpotifyService] = None


def get_spotify_service() -> SpotifyService:
    """Get or create Spotify service instance."""
    global _spotify_service
    if _spotify_service is None:
        _spotify_service = SpotifyService()
    return _spotify_service
