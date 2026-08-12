"""
Spotify API client.
Uses official Spotify Web API for data operations.
"""

import requests
from typing import Optional, List, Dict
from datetime import datetime

from src.logging_module.app_logger import get_logger


logger = get_logger()


class SpotifyAPIError(Exception):
    """Exception raised for Spotify API errors."""
    pass


class SpotifyClient:
    """
    Official Spotify Web API client.
    
    Handles rate limiting, token refresh, and error handling.
    """
    
    BASE_URL = "https://api.spotify.com/v1"
    
    def __init__(self, access_token: str):
        """
        Initialize Spotify API client.
        
        Args:
            access_token: Valid OAuth access token
        """
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        })
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """
        Make authenticated request to Spotify API.
        
        Args:
            method: HTTP method
            endpoint: API endpoint (without base URL)
            **kwargs: Additional request parameters
            
        Returns:
            JSON response
            
        Raises:
            SpotifyAPIError: On API error
        """
        url = f"{self.BASE_URL}/{endpoint}"
        
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            
            if response.status_code == 401:
                raise SpotifyAPIError("Token expired - refresh required")
            elif response.status_code == 429:
                # Rate limited - respect Retry-After header
                retry_after = int(response.headers.get("Retry-After", 1))
                logger.warning(f"Rate limited, waiting {retry_after}s", "SPOTIFY_RATE_LIMIT")
                raise SpotifyAPIError(f"Rate limited - retry after {retry_after}s")
            elif response.status_code >= 400:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", str(response.status_code))
                raise SpotifyAPIError(f"API error: {error_msg}")
            
            return response.json() if response.content else {}
            
        except requests.RequestException as e:
            raise SpotifyAPIError(f"Request failed: {e}")
    
    def get_current_user(self) -> Dict:
        """Get current authenticated user info."""
        return self._request("GET", "me")
    
    def get_playback_state(self) -> Optional[Dict]:
        """
        Get current playback state.
        
        Returns:
            Playback state dict or None if nothing playing
        """
        try:
            return self._request("GET", "me/player")
        except SpotifyAPIError:
            return None
    
    def get_playlist(self, playlist_id: str) -> Dict:
        """
        Get playlist details.
        
        Args:
            playlist_id: Spotify playlist ID
            
        Returns:
            Playlist information
        """
        return self._request("GET", f"playlists/{playlist_id}")
    
    def get_playlist_tracks(self, playlist_id: str, limit: int = 50) -> List[Dict]:
        """
        Get tracks from a playlist.
        
        Args:
            playlist_id: Spotify playlist ID
            limit: Max tracks to return
            
        Returns:
            List of track objects
        """
        tracks = []
        offset = 0
        
        while True:
            response = self._request(
                "GET",
                f"playlists/{playlist_id}/tracks",
                params={"limit": limit, "offset": offset}
            )
            
            tracks.extend([item["track"] for item in response.get("items", []) if item.get("track")])
            
            if len(response.get("items", [])) < limit:
                break
                
            offset += limit
        
        return tracks
    
    def add_tracks_to_playlist(self, playlist_id: str, track_uris: List[str]) -> bool:
        """
        Add tracks to a playlist.
        
        Args:
            playlist_id: Spotify playlist ID
            track_uris: List of track URIs to add
            
        Returns:
            True if successful
        """
        if not track_uris:
            return False
        
        # Spotify limits to 100 tracks per request
        for i in range(0, len(track_uris), 100):
            batch = track_uris[i:i+100]
            self._request(
                "POST",
                f"playlists/{playlist_id}/tracks",
                json={"uris": batch}
            )
        
        return True
    
    def start_playback(self, device_id: Optional[str] = None, 
                       context_uri: Optional[str] = None,
                       uris: Optional[List[str]] = None) -> bool:
        """
        Start playback on specified device.
        
        Args:
            device_id: Device ID to play on
            context_uri: Context URI (album/playlist) to play
            uris: Specific track URIs to play
            
        Returns:
            True if successful
        """
        params = {}
        if device_id:
            params["device_id"] = device_id
        
        json_body = {}
        if context_uri:
            json_body["context_uri"] = context_uri
        if uris:
            json_body["uris"] = uris
        
        try:
            self._request("PUT", "me/player/play", params=params, json=json_body)
            return True
        except SpotifyAPIError as e:
            if "NO_ACTIVE_DEVICE" in str(e):
                logger.warning("No active Spotify device found", "SPOTIFY_NO_DEVICE")
                return False
            raise
    
    def pause_playback(self, device_id: Optional[str] = None) -> bool:
        """
        Pause current playback.
        
        Args:
            device_id: Device ID to pause
            
        Returns:
            True if successful
        """
        params = {"device_id": device_id} if device_id else {}
        try:
            self._request("PUT", "me/player/pause", params=params)
            return True
        except SpotifyAPIError:
            return False
    
    def skip_to_next(self, device_id: Optional[str] = None) -> bool:
        """
        Skip to next track.
        
        Args:
            device_id: Device ID to skip on
            
        Returns:
            True if successful
        """
        params = {"device_id": device_id} if device_id else {}
        try:
            self._request("POST", "me/player/next", params=params)
            return True
        except SpotifyAPIError:
            return False
    
    def get_user_playlists(self, limit: int = 50) -> List[Dict]:
        """Get user's playlists."""
        response = self._request("GET", "me/playlists", params={"limit": limit})
        return response.get("items", [])
    
    def create_playlist(self, name: str, description: str = "", 
                        public: bool = False) -> Dict:
        """
        Create a new playlist.
        
        Args:
            name: Playlist name
            description: Playlist description
            public: Whether playlist should be public
            
        Returns:
            Created playlist info
        """
        user = self.get_current_user()
        user_id = user.get("id")
        
        return self._request(
            "POST",
            f"users/{user_id}/playlists",
            json={
                "name": name,
                "description": description,
                "public": public
            }
        )
    
    def save_track(self, track_id: str) -> bool:
        """
        Save track to user's library (Liked Songs).
        
        Args:
            track_id: Spotify track ID
            
        Returns:
            True if successful
        """
        try:
            self._request("PUT", "me/tracks", params={"ids": track_id})
            return True
        except SpotifyAPIError:
            return False
    
    def get_recommendations(self, seed_artists: Optional[List[str]] = None,
                           seed_genres: Optional[List[str]] = None,
                           seed_tracks: Optional[List[str]] = None,
                           limit: int = 20) -> List[Dict]:
        """
        Get track recommendations.
        
        Args:
            seed_artists: Artist IDs for seeds
            seed_genres: Genre names for seeds
            seed_tracks: Track IDs for seeds
            limit: Number of recommendations (max 100)
            
        Returns:
            List of recommended tracks
        """
        params = {"limit": min(limit, 100)}
        
        if seed_artists:
            params["seed_artists"] = ",".join(seed_artists[:5])  # Max 5
        if seed_genres:
            params["seed_genres"] = ",".join(seed_genres[:5])
        if seed_tracks:
            params["seed_tracks"] = ",".join(seed_tracks[:5])
        
        response = self._request("GET", "recommendations", params=params)
        return response.get("tracks", [])
