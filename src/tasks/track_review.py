"""
Track Review Task - Browser workflow for reviewing Spotify tracks.

Allows users to:
- Open a Spotify track in browser
- Review it (accept/reject)
- Add to selected playlist
- Add notes
- Assign category/tag
"""

import time
from typing import Optional, Dict, Any, Callable
from datetime import datetime

from src.browser.browser_worker import BrowserWorker
from src.logging_module.app_logger import get_logger
from src.database.database import DatabaseManager
from src.database.repositories import TaskRepository, PlaylistRepository, ActivityLogRepository
from src.database.models import TaskStatus


logger = get_logger()


class TrackReviewResult:
    """Result of a track review."""
    
    def __init__(
        self,
        track_uri: str,
        track_name: str = "",
        artist_name: str = "",
        accepted: bool = False,
        playlist_id: Optional[str] = None,
        notes: str = "",
        category: str = "",
        reviewed_at: Optional[datetime] = None
    ):
        self.track_uri = track_uri
        self.track_name = track_name
        self.artist_name = artist_name
        self.accepted = accepted
        self.playlist_id = playlist_id
        self.notes = notes
        self.category = category
        self.reviewed_at = reviewed_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_uri": self.track_uri,
            "track_name": self.track_name,
            "artist_name": self.artist_name,
            "accepted": self.accepted,
            "playlist_id": self.playlist_id,
            "notes": self.notes,
            "category": self.category,
            "reviewed_at": self.reviewed_at.isoformat()
        }


class TrackReviewTask:
    """
    Browser-based track review workflow.
    
    Opens a track in Spotify web player and waits for user review.
    """
    
    def __init__(self, profile_id: int, track_uri: str, headless: bool = False):
        """
        Initialize track review task.
        
        Args:
            profile_id: Profile ID for browser session
            track_uri: Spotify track URI (e.g., spotify:track:xxx)
            headless: Run browser without visible window
        """
        self.profile_id = profile_id
        self.track_uri = track_uri
        self.headless = headless
        self.browser: Optional[BrowserWorker] = None
        self.result: Optional[TrackReviewResult] = None
    
    def start(self) -> bool:
        """Start browser session."""
        logger.info("Starting track review browser session", "TRACK_REVIEW_START", self.profile_id)
        
        self.browser = BrowserWorker(self.profile_id, headless=self.headless)
        return self.browser.start()
    
    def stop(self) -> None:
        """Stop browser session."""
        if self.browser:
            self.browser.stop()
            logger.info("Track review browser session stopped", "TRACK_REVIEW_STOP", self.profile_id)
    
    def open_track(self) -> bool:
        """
        Open track in Spotify web player.
        
        Returns:
            True if successful
        """
        if not self.browser or not self.browser.is_running():
            logger.error("Browser not running", "BROWSER_NOT_RUNNING", self.profile_id)
            return False
        
        # Convert Spotify URI to web URL
        # Format: spotify:track:4iV5W9uYEdYUVa79Axb7Rh -> https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh
        parts = self.track_uri.split(":")
        if len(parts) != 3 or parts[0] != "spotify" or parts[1] != "track":
            logger.error(f"Invalid track URI: {self.track_uri}", "INVALID_TRACK_URI", self.profile_id)
            return False
        
        track_id = parts[2]
        track_url = f"https://open.spotify.com/track/{track_id}"
        
        logger.info(f"Opening track: {track_url}", "TRACK_OPEN", self.profile_id)
        return self.browser.open(track_url)
    
    def wait_for_user_review(
        self,
        timeout_seconds: int = 300,
        on_accept: Optional[Callable[[], None]] = None,
        on_reject: Optional[Callable[[], None]] = None
    ) -> Optional[TrackReviewResult]:
        """
        Wait for user to complete review.
        
        In a real implementation, this would:
        - Display UI buttons for accept/reject
        - Allow adding notes and categories
        - Wait for user input
        
        For MVP, this is a placeholder that simulates the workflow.
        
        Args:
            timeout_seconds: Max time to wait for review
            on_accept: Callback when track is accepted
            on_reject: Callback when track is rejected
            
        Returns:
            TrackReviewResult or None if timeout/cancelled
        """
        logger.info("Waiting for user review...", "TRACK_REVIEW_WAIT", self.profile_id)
        
        # Extract track info (in production, fetch from Spotify API)
        track_id = self.track_uri.split(":")[2]
        
        # Placeholder: In real implementation, this would be a GUI dialog
        # or web interface where user makes decisions
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            # Check if browser is still running
            if not self.browser or not self.browser.is_running():
                logger.warning("Browser closed during review", "TRACK_REVIEW_CANCELLED", self.profile_id)
                return None
            
            # In production, check for user action here
            # For now, just wait
            time.sleep(1)
        
        logger.warning("Review timeout", "TRACK_REVIEW_TIMEOUT", self.profile_id)
        return None
    
    def submit_review(
        self,
        accepted: bool,
        playlist_id: Optional[str] = None,
        notes: str = "",
        category: str = ""
    ) -> TrackReviewResult:
        """
        Submit review result.
        
        Args:
            accepted: Whether track was accepted
            playlist_id: Optional playlist to add to
            notes: User notes
            category: Category/tag
            
        Returns:
            TrackReviewResult
        """
        track_id = self.track_uri.split(":")[2]
        
        self.result = TrackReviewResult(
            track_uri=self.track_uri,
            track_name=f"Track {track_id[:8]}...",  # Placeholder
            artist_name="Unknown Artist",  # Placeholder
            accepted=accepted,
            playlist_id=playlist_id,
            notes=notes,
            category=category
        )
        
        logger.info(
            f"Track review submitted: accepted={accepted}, category={category}",
            "TRACK_REVIEW_SUBMITTED",
            self.profile_id
        )
        
        # If accepted and playlist specified, add to playlist
        if accepted and playlist_id:
            self._add_to_playlist(playlist_id)
        
        return self.result
    
    def _add_to_playlist(self, playlist_id: str) -> bool:
        """Add track to playlist if accepted."""
        try:
            with DatabaseManager() as session:
                playlist_repo = PlaylistRepository(session)
                playlist = playlist_repo.get_by_spotify_id(playlist_id)
                
                if not playlist:
                    logger.warning(f"Playlist {playlist_id} not found in database", "PLAYLIST_NOT_FOUND", self.profile_id)
                    return False
                
                # Use Spotify service to add track
                from src.spotify.service import get_spotify_service
                spotify = get_spotify_service()
                
                if spotify.is_configured():
                    success = spotify.add_tracks_to_playlist(
                        self.profile_id,
                        playlist_id,
                        [self.track_uri]
                    )
                    
                    if success:
                        logger.info(
                            f"Added track to playlist {playlist.name}",
                            "TRACK_ADDED_TO_PLAYLIST",
                            self.profile_id
                        )
                        return True
                    else:
                        logger.error("Failed to add track to playlist", "PLAYLIST_ADD_FAILED", self.profile_id)
                        return False
                else:
                    logger.warning("Spotify not configured, skipping playlist add", "SPOTIFY_NOT_CONFIGURED", self.profile_id)
                    return False
                    
        except Exception as e:
            logger.error(f"Error adding to playlist: {e}", "PLAYLIST_ADD_ERROR", self.profile_id)
            return False
    
    def execute(self, timeout_seconds: int = 300) -> bool:
        """
        Execute complete review workflow.
        
        Args:
            timeout_seconds: Max time for entire workflow
            
        Returns:
            True if workflow completed successfully
        """
        try:
            # Start browser
            if not self.start():
                return False
            
            # Open track
            if not self.open_track():
                self.stop()
                return False
            
            # Wait for user review (placeholder)
            # In production, this would display UI and wait for input
            logger.info("Track opened for review - waiting for user input", "TRACK_REVIEW_PENDING", self.profile_id)
            
            # For automated testing, we can simulate a review
            # In production, this would be replaced with actual user interaction
            time.sleep(2)  # Give user time to see the track
            
            # Placeholder: Auto-accept for demo purposes
            # In production, remove this and rely on actual user input
            self.submit_review(
                accepted=True,
                notes="Auto-reviewed (demo)",
                category="pending_manual_review"
            )
            
            self.stop()
            return self.result is not None
            
        except Exception as e:
            logger.error(f"Track review failed: {e}", "TRACK_REVIEW_ERROR", self.profile_id)
            self.stop()
            return False


def execute_track_review_task(
    profile_id: int,
    track_uri: str,
    playlist_id: Optional[str] = None,
    headless: bool = False,
    timeout_seconds: int = 300
) -> bool:
    """
    Execute a track review task.
    
    This is the entry point called by the worker pool.
    
    Args:
        profile_id: Profile to execute for
        track_uri: Spotify track URI
        playlist_id: Optional playlist to add accepted tracks to
        headless: Run browser without visible window
        timeout_seconds: Max time for review
        
    Returns:
        True if successful
    """
    logger.info(f"Executing track review for {track_uri}", "TRACK_REVIEW_EXEC", profile_id)
    
    task = TrackReviewTask(profile_id, track_uri, headless=headless)
    
    try:
        # Start browser and open track
        if not task.start():
            return False
        
        if not task.open_track():
            task.stop()
            return False
        
        # In production, wait for actual user input via GUI
        # For now, log and return success
        logger.info(f"Track {track_uri} opened for review", "TRACK_REVIEW_OPENED", profile_id)
        
        # Store result in database
        with DatabaseManager() as session:
            log_repo = ActivityLogRepository(session)
            log_repo.create(
                profile_id=profile_id,
                level="INFO",
                event="TRACK_REVIEWED",
                message=f"Track {track_uri} reviewed"
            )
        
        task.stop()
        return True
        
    except Exception as e:
        logger.error(f"Track review failed: {e}", "TRACK_REVIEW_FAILED", profile_id)
        task.stop()
        return False
