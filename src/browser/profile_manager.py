"""
Browser profile manager.
Manages isolated browser session directories for each profile.
No stealth or anti-detect features - legitimate browser automation only.
"""

from pathlib import Path
from typing import Optional
import shutil

from src.config.settings import settings
from src.logging_module.app_logger import get_logger


logger = get_logger()


class ProfileManagerError(Exception):
    """Exception raised for profile management errors."""
    pass


class ProfileManager:
    """
    Manages browser profile directories.
    
    Each profile gets an isolated directory for browser session data.
    """
    
    def __init__(self, profiles_dir: Optional[Path] = None):
        """
        Initialize profile manager.
        
        Args:
            profiles_dir: Base directory for profiles (defaults to settings.PROFILES_DIR)
        """
        self.profiles_dir = profiles_dir or settings.PROFILES_DIR
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
    
    def get_profile_path(self, profile_id: int) -> Path:
        """
        Get the browser profile directory path for a profile.
        
        Args:
            profile_id: Profile ID
            
        Returns:
            Path to profile directory
        """
        return self.profiles_dir / f"profile_{profile_id}"
    
    def create_profile(self, profile_id: int) -> Path:
        """
        Create a new browser profile directory.
        
        Args:
            profile_id: Profile ID
            
        Returns:
            Path to created directory
        """
        profile_path = self.get_profile_path(profile_id)
        
        if profile_path.exists():
            logger.warning(f"Profile directory already exists: {profile_path}", "PROFILE_EXISTS", profile_id)
            return profile_path
        
        profile_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created profile directory: {profile_path}", "PROFILE_CREATED", profile_id)
        
        return profile_path
    
    def validate_profile(self, profile_id: int) -> bool:
        """
        Validate that a profile directory exists and is accessible.
        
        Args:
            profile_id: Profile ID
            
        Returns:
            True if valid
        """
        profile_path = self.get_profile_path(profile_id)
        
        if not profile_path.exists():
            logger.error(f"Profile directory does not exist: {profile_path}", "PROFILE_INVALID", profile_id)
            return False
        
        if not profile_path.is_dir():
            logger.error(f"Profile path is not a directory: {profile_path}", "PROFILE_INVALID", profile_id)
            return False
        
        # Check write access
        try:
            test_file = profile_path / ".write_test"
            test_file.touch()
            test_file.unlink()
            return True
        except Exception as e:
            logger.error(f"Profile directory not writable: {e}", "PROFILE_INVALID", profile_id)
            return False
    
    def clear_profile(self, profile_id: int) -> bool:
        """
        Clear browser data from a profile directory.
        
        Args:
            profile_id: Profile ID
            
        Returns:
            True if successful
        """
        profile_path = self.get_profile_path(profile_id)
        
        if not profile_path.exists():
            return True  # Nothing to clear
        
        try:
            # Remove all contents but keep directory
            for item in profile_path.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            
            logger.info("Cleared profile data", "PROFILE_CLEARED", profile_id)
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear profile: {e}", "PROFILE_CLEAR_ERROR", profile_id)
            return False
    
    def delete_profile(self, profile_id: int) -> bool:
        """
        Delete a profile directory entirely.
        
        Args:
            profile_id: Profile ID
            
        Returns:
            True if successful
        """
        profile_path = self.get_profile_path(profile_id)
        
        if not profile_path.exists():
            return True  # Already deleted
        
        try:
            shutil.rmtree(profile_path)
            logger.info("Deleted profile directory", "PROFILE_DELETED", profile_id)
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete profile: {e}", "PROFILE_DELETE_ERROR", profile_id)
            return False
    
    def get_profile_status(self, profile_id: int) -> dict:
        """
        Get status information about a profile.
        
        Args:
            profile_id: Profile ID
            
        Returns:
            Dictionary with status info
        """
        profile_path = self.get_profile_path(profile_id)
        
        status = {
            "exists": profile_path.exists(),
            "is_directory": profile_path.is_dir() if profile_path.exists() else False,
            "path": str(profile_path),
            "size_bytes": 0,
            "file_count": 0
        }
        
        if status["exists"] and status["is_directory"]:
            try:
                status["size_bytes"] = sum(
                    f.stat().st_size for f in profile_path.rglob("*") if f.is_file()
                )
                status["file_count"] = len(list(profile_path.rglob("*")))
            except Exception:
                pass
        
        return status
    
    def list_profiles(self) -> list:
        """
        List all existing profile directories.
        
        Returns:
            List of profile IDs (integers)
        """
        profile_ids = []
        
        for item in self.profiles_dir.iterdir():
            if item.is_dir() and item.name.startswith("profile_"):
                try:
                    profile_id = int(item.name.replace("profile_", ""))
                    profile_ids.append(profile_id)
                except ValueError:
                    continue
        
        return sorted(profile_ids)


# Global instance
_profile_manager: Optional[ProfileManager] = None


def get_profile_manager() -> ProfileManager:
    """Get or create profile manager instance."""
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = ProfileManager()
    return _profile_manager
