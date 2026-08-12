"""
Worker pool for executing tasks.
Manages concurrent worker threads with proper lifecycle handling.
"""

import threading
import time
import json
from typing import Optional, Dict, Callable, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from src.database.models import TaskStatus, TaskType
from src.database.database import DatabaseManager
from src.database.repositories import (
    TaskRepository, TaskRunRepository, ActivityLogRepository, ProfileRepository
)
from src.tasks.task_queue import TaskQueue, TaskItem, get_task_queue
from src.logging_module.app_logger import get_logger


logger = get_logger()


class WorkerPool:
    """
    Pool of worker threads for processing tasks.
    
    Workers pull tasks from the queue and execute them.
    """
    
    def __init__(self, max_workers: int = 5):
        """
        Initialize worker pool.
        
        Args:
            max_workers: Maximum number of concurrent workers
        """
        self.max_workers = max_workers
        self.queue: TaskQueue = get_task_queue()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._running = False
        self._workers: List[threading.Thread] = []
        self._stop_event = threading.Event()
    
    def start(self) -> None:
        """Start the worker pool."""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        
        # Start worker threads
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"TaskWorker-{i}",
                daemon=True
            )
            worker.start()
            self._workers.append(worker)
        
        logger.info(f"Started worker pool with {self.max_workers} workers", "WORKER_POOL_START")
    
    def stop(self, wait: bool = True, timeout: float = 5.0) -> None:
        """
        Stop the worker pool.
        
        Args:
            wait: Wait for workers to finish current tasks
            timeout: Max time to wait for each worker
        """
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if wait:
            for worker in self._workers:
                worker.join(timeout=timeout)
        
        self._workers.clear()
        logger.info("Stopped worker pool", "WORKER_POOL_STOP")
    
    def _worker_loop(self) -> None:
        """Main loop for worker thread."""
        while not self._stop_event.is_set():
            # Get next task from queue
            task = self.queue.get(timeout=1.0)
            
            if task is None:
                continue
            
            # Check if cancelled
            if task.payload.get('_cancelled'):
                logger.info(f"Task {task.task_id} cancelled", "TASK_CANCELLED", task.profile_id)
                continue
            
            # Execute task
            self._execute_task(task)
    
    def _execute_task(self, task: TaskItem) -> None:
        """
        Execute a single task.
        
        Args:
            task: Task to execute
        """
        logger.task_started(task.task_type.value, task.profile_id)
        
        with DatabaseManager() as session:
            task_repo = TaskRepository(session)
            run_repo = TaskRunRepository(session)
            log_repo = ActivityLogRepository(session)
            
            # Update task status
            task_repo.update_status(task.task_id, TaskStatus.RUNNING)
            
            # Create task run
            run = run_repo.create(task.task_id, threading.current_thread().name)
            
            try:
                # Execute based on task type
                success = self._run_task_logic(task)
                
                if success:
                    task_repo.update_status(task.task_id, TaskStatus.COMPLETED)
                    run_repo.complete(run.id, TaskStatus.COMPLETED)
                    logger.task_completed(task.task_type.value, task.profile_id)
                else:
                    task_repo.update_status(task.task_id, TaskStatus.FAILED, "Task logic returned failure")
                    run_repo.complete(run.id, TaskStatus.FAILED, "Task logic returned failure")
                    logger.task_failed(task.task_type.value, "Task logic returned failure", task.profile_id)
                
                # Call callback if provided
                if task.callback:
                    status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
                    task.callback(task.task_id, status, "" if success else "Failed")
                    
            except Exception as e:
                error_msg = str(e)
                task_repo.update_status(task.task_id, TaskStatus.FAILED, error_msg)
                run_repo.complete(run.id, TaskStatus.FAILED, error_msg)
                logger.task_failed(task.task_type.value, error_msg, task.profile_id)
                
                # Call callback with error
                if task.callback:
                    task.callback(task.task_id, TaskStatus.FAILED, error_msg)
    
    def _run_task_logic(self, task: TaskItem) -> bool:
        """
        Execute task-specific logic.
        
        Args:
            task: Task to execute
            
        Returns:
            True if successful
        """
        if task.task_type == TaskType.TRACK_REVIEW:
            return self._handle_track_review(task)
        elif task.task_type == TaskType.PLAYLIST_ADD:
            return self._handle_playlist_add(task)
        elif task.task_type == TaskType.PLAYBACK_CONTROL:
            return self._handle_playback_control(task)
        elif task.task_type == TaskType.AUTH_REFRESH:
            return self._handle_auth_refresh(task)
        else:
            logger.error(f"Unknown task type: {task.task_type}", "TASK_UNKNOWN_TYPE", task.profile_id)
            return False
    
    def _handle_track_review(self, task: TaskItem) -> bool:
        """Handle track review task using browser workflow."""
        from src.tasks.track_review import execute_track_review_task
        
        payload = task.payload
        track_uri = payload.get('track_uri')
        playlist_id = payload.get('playlist_id')
        
        if not track_uri:
            logger.error("Missing track_uri in task payload", "TRACK_REVIEW_ERROR", task.profile_id)
            return False
        
        # Execute track review workflow
        return execute_track_review_task(
            profile_id=task.profile_id,
            track_uri=track_uri,
            playlist_id=playlist_id,
            headless=False  # Show browser for user interaction
        )
    
    def _handle_playlist_add(self, task: TaskItem) -> bool:
        """Handle playlist add task."""
        payload = task.payload
        track_uris = payload.get('track_uris', [])
        playlist_id = payload.get('playlist_id')
        
        if not track_uris or not playlist_id:
            logger.error("Missing track_uris or playlist_id", "PLAYLIST_ADD_ERROR", task.profile_id)
            return False
        
        # Use Spotify service if configured
        from src.spotify.service import get_spotify_service
        spotify = get_spotify_service()
        
        if spotify.is_configured():
            return spotify.add_tracks_to_playlist(task.profile_id, playlist_id, track_uris)
        
        logger.warning("Spotify not configured, skipping playlist add", "SPOTIFY_NOT_CONFIGURED", task.profile_id)
        return True  # Don't fail if not configured
    
    def _handle_playback_control(self, task: TaskItem) -> bool:
        """Handle playback control task."""
        payload = task.payload
        action = payload.get('action')  # play, pause, skip
        
        from src.spotify.service import get_spotify_service
        spotify = get_spotify_service()
        
        if not spotify.is_configured():
            logger.warning("Spotify not configured, skipping playback control", "SPOTIFY_NOT_CONFIGURED", task.profile_id)
            return True
        
        if action == 'play':
            context_uri = payload.get('context_uri')
            return spotify.start_playback(task.profile_id, context_uri=context_uri)
        elif action == 'pause':
            return spotify.pause_playback(task.profile_id)
        elif action == 'skip':
            return spotify.skip_to_next(task.profile_id)
        else:
            logger.error(f"Unknown playback action: {action}", "PLAYBACK_ERROR", task.profile_id)
            return False
    
    def _handle_auth_refresh(self, task: TaskItem) -> bool:
        """Handle auth refresh task."""
        from src.spotify.service import get_spotify_service
        spotify = get_spotify_service()
        
        if not spotify.is_configured():
            return True
        
        # This will trigger token refresh if needed
        return spotify._ensure_valid_token(task.profile_id)
    
    def get_status(self) -> dict:
        """Get worker pool status."""
        return {
            "running": self._running,
            "max_workers": self.max_workers,
            "active_workers": len([w for w in self._workers if w.is_alive()]),
            "queue_size": self.queue.size()
        }


# Global pool instance
_worker_pool: Optional[WorkerPool] = None


def get_worker_pool(max_workers: int = 5) -> WorkerPool:
    """Get or create global worker pool."""
    global _worker_pool
    if _worker_pool is None:
        _worker_pool = WorkerPool(max_workers)
    return _worker_pool
