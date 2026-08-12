"""
SQLAlchemy models for Spotify Manager database.

Entities:
- Profile: User profile with browser session
- Proxy: Proxy configuration for profiles
- Playlist: Spotify playlists associated with profiles
- Task: Background tasks to execute
- TaskRun: Individual execution of a task
- ActivityLog: Application activity logs
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum, Boolean
from sqlalchemy.orm import relationship
import enum


class ProfileStatus(str, enum.Enum):
    """Profile status values."""
    INACTIVE = "inactive"
    ACTIVE = "active"
    RUNNING = "running"
    ERROR = "error"


class ProxyStatus(str, enum.Enum):
    """Proxy status values."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    INVALID = "invalid"


class TaskType(str, enum.Enum):
    """Task type values."""
    TRACK_REVIEW = "track_review"
    PLAYLIST_ADD = "playlist_add"
    PLAYBACK_CONTROL = "playback_control"
    AUTH_REFRESH = "auth_refresh"


class TaskStatus(str, enum.Enum):
    """Task status values."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(int, enum.Enum):
    """Task priority values (lower = higher priority)."""
    HIGH = 1
    NORMAL = 2
    LOW = 3


class LogLevel(str, enum.Enum):
    """Log level values."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# Import Base from database module
from src.database.database import Base


class Profile(Base):
    """User profile with isolated browser session."""
    
    __tablename__ = "profiles"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    country = Column(String(2), default="US")
    timezone = Column(String(50), default="UTC")
    status = Column(Enum(ProfileStatus), default=ProfileStatus.INACTIVE)
    spotify_user_id = Column(String(255), nullable=True)
    browser_profile_path = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    proxies = relationship("Proxy", back_populates="profile", cascade="all, delete-orphan")
    playlists = relationship("Playlist", back_populates="profile", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="profile", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog", back_populates="profile", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Profile(id={self.id}, name='{self.name}', status={self.status})>"


class Proxy(Base):
    """Proxy configuration for profiles."""
    
    __tablename__ = "proxies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(255), nullable=True)
    encrypted_secret = Column(String(512), nullable=True)  # Encrypted password or reference
    country = Column(String(2), nullable=True)
    status = Column(Enum(ProxyStatus), default=ProxyStatus.ACTIVE)
    
    # Relationships
    profile = relationship("Profile", back_populates="proxies")
    
    def __repr__(self):
        return f"<Proxy(id={self.id}, host='{self.host}:{self.port}')>"


class Playlist(Base):
    """Spotify playlist associated with a profile."""
    
    __tablename__ = "playlists"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    spotify_playlist_id = Column(String(255), nullable=True)
    name = Column(String(255), nullable=False)
    url = Column(String(512), nullable=True)
    
    # Relationships
    profile = relationship("Profile", back_populates="playlists")
    
    def __repr__(self):
        return f"<Playlist(id={self.id}, name='{self.name}')>"


class Task(Base):
    """Background task to execute."""
    
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    type = Column(Enum(TaskType), nullable=False)
    payload = Column(Text, nullable=True)  # JSON string with task parameters
    status = Column(Enum(TaskStatus), default=TaskStatus.QUEUED)
    priority = Column(Enum(TaskPriority), default=TaskPriority.NORMAL)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    profile = relationship("Profile", back_populates="tasks")
    runs = relationship("TaskRun", back_populates="task", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Task(id={self.id}, type={self.type}, status={self.status})>"


class TaskRun(Base):
    """Individual execution of a task."""
    
    __tablename__ = "task_runs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    worker_id = Column(String(50), nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.QUEUED)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    task = relationship("Task", back_populates="runs")
    
    def __repr__(self):
        return f"<TaskRun(id={self.id}, task_id={self.task_id}, status={self.status})>"


class ActivityLog(Base):
    """Application activity log entry."""
    
    __tablename__ = "activity_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=True)
    level = Column(Enum(LogLevel), default=LogLevel.INFO)
    event = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    profile = relationship("Profile", back_populates="activity_logs")
    
    def __repr__(self):
        return f"<ActivityLog(id={self.id}, level={self.level}, event={self.event})>"
