"""
Repository classes for database operations.
Provides clean abstraction over SQLAlchemy models.
"""

from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.database.models import (
    Profile, ProfileStatus,
    Proxy, ProxyStatus,
    Playlist,
    Task, TaskStatus, TaskType, TaskPriority,
    TaskRun,
    ActivityLog, LogLevel
)


class ProfileRepository:
    """Repository for Profile operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, name: str, country: str = "US", timezone: str = "UTC") -> Profile:
        """Create a new profile."""
        profile = Profile(
            name=name,
            country=country,
            timezone=timezone,
            status=ProfileStatus.INACTIVE
        )
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return profile
    
    def get_by_id(self, profile_id: int) -> Optional[Profile]:
        """Get profile by ID."""
        return self.session.query(Profile).filter(Profile.id == profile_id).first()
    
    def get_all(self) -> List[Profile]:
        """Get all profiles."""
        return self.session.query(Profile).order_by(desc(Profile.created_at)).all()
    
    def update_status(self, profile_id: int, status: ProfileStatus) -> bool:
        """Update profile status."""
        profile = self.get_by_id(profile_id)
        if profile:
            profile.status = status
            profile.updated_at = datetime.utcnow()
            self.session.commit()
            return True
        return False
    
    def delete(self, profile_id: int) -> bool:
        """Delete profile."""
        profile = self.get_by_id(profile_id)
        if profile:
            self.session.delete(profile)
            self.session.commit()
            return True
        return False
    
    def get_or_create_browser_path(self, profile_id: int) -> str:
        """Get or create browser profile path for a profile."""
        from pathlib import Path
        from src.config.settings import settings
        
        profile = self.get_by_id(profile_id)
        if not profile:
            raise ValueError(f"Profile {profile_id} not found")
        
        if not profile.browser_profile_path:
            # Create unique profile directory
            profile_dir = settings.PROFILES_DIR / f"profile_{profile_id}"
            profile_dir.mkdir(parents=True, exist_ok=True)
            profile.browser_profile_path = str(profile_dir)
            self.session.commit()
        
        return profile.browser_profile_path


class ProxyRepository:
    """Repository for Proxy operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, profile_id: int, host: str, port: int, 
               username: Optional[str] = None, encrypted_secret: Optional[str] = None,
               country: Optional[str] = None) -> Proxy:
        """Create a new proxy."""
        proxy = Proxy(
            profile_id=profile_id,
            host=host,
            port=port,
            username=username,
            encrypted_secret=encrypted_secret,
            country=country,
            status=ProxyStatus.ACTIVE
        )
        self.session.add(proxy)
        self.session.commit()
        self.session.refresh(proxy)
        return proxy
    
    def get_by_profile(self, profile_id: int) -> List[Proxy]:
        """Get all proxies for a profile."""
        return self.session.query(Proxy).filter(Proxy.profile_id == profile_id).all()
    
    def get_active_proxy(self, profile_id: int) -> Optional[Proxy]:
        """Get active proxy for a profile."""
        return self.session.query(Proxy).filter(
            Proxy.profile_id == profile_id,
            Proxy.status == ProxyStatus.ACTIVE
        ).first()


class PlaylistRepository:
    """Repository for Playlist operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, profile_id: int, name: str, 
               spotify_playlist_id: Optional[str] = None,
               url: Optional[str] = None) -> Playlist:
        """Create a new playlist."""
        playlist = Playlist(
            profile_id=profile_id,
            name=name,
            spotify_playlist_id=spotify_playlist_id,
            url=url
        )
        self.session.add(playlist)
        self.session.commit()
        self.session.refresh(playlist)
        return playlist
    
    def get_by_profile(self, profile_id: int) -> List[Playlist]:
        """Get all playlists for a profile."""
        return self.session.query(Playlist).filter(Playlist.profile_id == profile_id).all()


class TaskRepository:
    """Repository for Task operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, profile_id: int, task_type: TaskType, 
               payload: Optional[str] = None,
               priority: TaskPriority = TaskPriority.NORMAL) -> Task:
        """Create a new task."""
        task = Task(
            profile_id=profile_id,
            type=task_type,
            payload=payload,
            priority=priority,
            status=TaskStatus.QUEUED
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task
    
    def get_by_id(self, task_id: int) -> Optional[Task]:
        """Get task by ID."""
        return self.session.query(Task).filter(Task.id == task_id).first()
    
    def get_queued_tasks(self, limit: int = 10) -> List[Task]:
        """Get queued tasks ordered by priority."""
        return self.session.query(Task).filter(
            Task.status == TaskStatus.QUEUED
        ).order_by(Task.priority, Task.created_at).limit(limit).all()
    
    def update_status(self, task_id: int, status: TaskStatus, 
                      error_message: Optional[str] = None) -> bool:
        """Update task status."""
        task = self.get_by_id(task_id)
        if task:
            task.status = status
            if status == TaskStatus.RUNNING:
                task.started_at = datetime.utcnow()
            elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                task.finished_at = datetime.utcnow()
            if error_message:
                task.error_message = error_message
            self.session.commit()
            return True
        return False
    
    def get_by_profile(self, profile_id: int) -> List[Task]:
        """Get all tasks for a profile."""
        return self.session.query(Task).filter(Task.profile_id == profile_id).all()


class TaskRunRepository:
    """Repository for TaskRun operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, task_id: int, worker_id: str) -> TaskRun:
        """Create a new task run."""
        task_run = TaskRun(
            task_id=task_id,
            worker_id=worker_id,
            started_at=datetime.utcnow(),
            status=TaskStatus.RUNNING
        )
        self.session.add(task_run)
        self.session.commit()
        self.session.refresh(task_run)
        return task_run
    
    def complete(self, task_run_id: int, status: TaskStatus,
                 error_message: Optional[str] = None) -> bool:
        """Complete a task run."""
        task_run = self.session.query(TaskRun).filter(TaskRun.id == task_run_id).first()
        if task_run:
            task_run.status = status
            task_run.finished_at = datetime.utcnow()
            if error_message:
                task_run.error_message = error_message
            self.session.commit()
            return True
        return False


class ActivityLogRepository:
    """Repository for ActivityLog operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, event: str, message: str, level: LogLevel = LogLevel.INFO,
               profile_id: Optional[int] = None) -> ActivityLog:
        """Create a new activity log entry."""
        log_entry = ActivityLog(
            profile_id=profile_id,
            level=level,
            event=event,
            message=message
        )
        self.session.add(log_entry)
        self.session.commit()
        self.session.refresh(log_entry)
        return log_entry
    
    def get_recent(self, limit: int = 100) -> List[ActivityLog]:
        """Get recent activity logs."""
        return self.session.query(ActivityLog).order_by(
            desc(ActivityLog.created_at)
        ).limit(limit).all()
    
    def get_by_profile(self, profile_id: int, limit: int = 50) -> List[ActivityLog]:
        """Get recent logs for a specific profile."""
        return self.session.query(ActivityLog).filter(
            ActivityLog.profile_id == profile_id
        ).order_by(desc(ActivityLog.created_at)).limit(limit).all()
