"""
Task manager - high-level interface for task operations.
Combines queue, worker pool, and database operations.
"""

import json
from typing import Optional, Callable, List, Dict
from datetime import datetime

from src.database.models import TaskType, TaskStatus, TaskPriority
from src.database.database import DatabaseManager
from src.database.repositories import TaskRepository, ActivityLogRepository
from src.tasks.task_queue import TaskQueue, TaskItem, get_task_queue
from src.tasks.worker_pool import WorkerPool, get_worker_pool
from src.logging_module.app_logger import get_logger


logger = get_logger()


class TaskManager:
    """
    High-level task management interface.
    
    Provides methods to create, queue, and manage tasks.
    """
    
    def __init__(self, max_workers: int = 5):
        """
        Initialize task manager.
        
        Args:
            max_workers: Maximum concurrent workers
        """
        self.max_workers = max_workers
        self.queue: TaskQueue = get_task_queue()
        self.worker_pool: WorkerPool = get_worker_pool(max_workers)
        self._started = False
    
    def start(self) -> None:
        """Start the task processing system."""
        if not self._started:
            self.worker_pool.start()
            self._started = True
            logger.info("Task manager started", "TASK_MANAGER_START")
    
    def stop(self, wait: bool = True) -> None:
        """Stop the task processing system."""
        if self._started:
            self.worker_pool.stop(wait=wait)
            self._started = False
            logger.info("Task manager stopped", "TASK_MANAGER_STOP")
    
    def create_track_review_task(
        self,
        profile_id: int,
        track_uri: str,
        playlist_id: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        callback: Optional[Callable[[int, TaskStatus, str], None]] = None
    ) -> Optional[int]:
        """
        Create a track review task.
        
        Args:
            profile_id: Profile to execute task for
            track_uri: Spotify track URI to review
            playlist_id: Optional playlist to add to
            priority: Task priority
            callback: Optional callback on completion
            
        Returns:
            Task ID or None if failed
        """
        payload = {
            "track_uri": track_uri,
            "playlist_id": playlist_id
        }
        
        return self._create_task(
            profile_id=profile_id,
            task_type=TaskType.TRACK_REVIEW,
            payload=payload,
            priority=priority,
            callback=callback
        )
    
    def create_playlist_add_task(
        self,
        profile_id: int,
        playlist_id: str,
        track_uris: List[str],
        priority: TaskPriority = TaskPriority.NORMAL,
        callback: Optional[Callable[[int, TaskStatus, str], None]] = None
    ) -> Optional[int]:
        """
        Create a task to add tracks to playlist.
        
        Args:
            profile_id: Profile to execute task for
            playlist_id: Spotify playlist ID
            track_uris: List of track URIs to add
            priority: Task priority
            callback: Optional callback on completion
            
        Returns:
            Task ID or None if failed
        """
        payload = {
            "playlist_id": playlist_id,
            "track_uris": track_uris
        }
        
        return self._create_task(
            profile_id=profile_id,
            task_type=TaskType.PLAYLIST_ADD,
            payload=payload,
            priority=priority,
            callback=callback
        )
    
    def create_playback_control_task(
        self,
        profile_id: int,
        action: str,  # 'play', 'pause', 'skip'
        context_uri: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        callback: Optional[Callable[[int, TaskStatus, str], None]] = None
    ) -> Optional[int]:
        """
        Create a playback control task.
        
        Args:
            profile_id: Profile to execute task for
            action: Action to perform (play/pause/skip)
            context_uri: Optional context URI for play action
            priority: Task priority
            callback: Optional callback on completion
            
        Returns:
            Task ID or None if failed
        """
        payload = {
            "action": action,
            "context_uri": context_uri
        }
        
        return self._create_task(
            profile_id=profile_id,
            task_type=TaskType.PLAYBACK_CONTROL,
            payload=payload,
            priority=priority,
            callback=callback
        )
    
    def _create_task(
        self,
        profile_id: int,
        task_type: TaskType,
        payload: dict,
        priority: TaskPriority = TaskPriority.NORMAL,
        callback: Optional[Callable[[int, TaskStatus, str], None]] = None
    ) -> Optional[int]:
        """
        Create and queue a task.
        
        Args:
            profile_id: Profile to execute task for
            task_type: Type of task
            payload: Task parameters
            priority: Task priority
            callback: Optional callback on completion
            
        Returns:
            Task ID or None if failed
        """
        with DatabaseManager() as session:
            task_repo = TaskRepository(session)
            log_repo = ActivityLogRepository(session)
            
            # Create task in database
            task = task_repo.create(
                profile_id=profile_id,
                task_type=task_type,
                payload=json.dumps(payload),
                priority=priority
            )
            
            # Log creation
            log_repo.create(
                event="TASK_CREATED",
                message=f"Created {task_type.value} task",
                profile_id=profile_id
            )
            
            # Create queue item
            task_item = TaskItem(
                task_id=task.id,
                profile_id=profile_id,
                task_type=task_type,
                payload=payload,
                priority=priority,
                callback=callback
            )
            
            # Add to queue
            if not self.queue.put(task_item):
                logger.error(f"Failed to queue task {task.id}", "TASK_QUEUE_ERROR", profile_id)
                return None
            
            logger.info(f"Task {task.id} queued ({task_type.value})", "TASK_QUEUED", profile_id)
            return task.id
    
    def cancel_task(self, task_id: int) -> bool:
        """
        Cancel a queued task.
        
        Args:
            task_id: ID of task to cancel
            
        Returns:
            True if cancelled
        """
        return self.queue.remove(task_id)
    
    def get_queued_tasks(self) -> List[Dict]:
        """Get list of queued tasks."""
        tasks = self.queue.get_queued_tasks()
        return [
            {
                "task_id": t.task_id,
                "profile_id": t.profile_id,
                "task_type": t.task_type.value,
                "priority": t.priority.name,
                "created_at": t.created_at.isoformat()
            }
            for t in tasks
        ]
    
    def get_status(self) -> dict:
        """Get task manager status."""
        return {
            "started": self._started,
            "max_workers": self.max_workers,
            **self.worker_pool.get_status()
        }


# Global instance
_task_manager: Optional[TaskManager] = None


def get_task_manager(max_workers: int = 5) -> TaskManager:
    """Get or create task manager instance."""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager(max_workers)
    return _task_manager
