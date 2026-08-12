"""
Task queue for managing background tasks.
Thread-safe FIFO queue with priority support.
"""

import threading
import queue
from typing import Optional, Callable, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.database.models import TaskPriority, TaskStatus, TaskType


@dataclass
class TaskItem:
    """Task item for the queue."""
    
    task_id: int
    profile_id: int
    task_type: TaskType
    payload: dict
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: datetime = field(default_factory=datetime.utcnow)
    callback: Optional[Callable[[int, TaskStatus, str], None]] = None
    
    def __lt__(self, other):
        """Compare by priority then creation time."""
        if self.priority != other.priority:
            return self.priority.value < other.priority.value
        return self.created_at < other.created_at


class TaskQueue:
    """
    Thread-safe task queue with priority support.
    
    Tasks are processed in priority order (lower value = higher priority).
    """
    
    def __init__(self):
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._lock = threading.Lock()
        self._task_index: dict = {}  # task_id -> TaskItem
    
    def put(self, task: TaskItem) -> bool:
        """
        Add task to queue.
        
        Args:
            task: Task to add
            
        Returns:
            True if added successfully
        """
        with self._lock:
            if task.task_id in self._task_index:
                return False  # Already queued
            
            self._queue.put(task)
            self._task_index[task.task_id] = task
            return True
    
    def get(self, timeout: Optional[float] = None) -> Optional[TaskItem]:
        """
        Get next task from queue.
        
        Args:
            timeout: Max time to wait (None = block forever)
            
        Returns:
            Next task or None if timeout/empty
        """
        try:
            task = self._queue.get(timeout=timeout)
            with self._lock:
                self._task_index.pop(task.task_id, None)
            return task
        except queue.Empty:
            return None
    
    def remove(self, task_id: int) -> bool:
        """
        Remove a task from queue (if not yet processing).
        
        Note: This only works for tasks not currently being processed.
        
        Args:
            task_id: ID of task to remove
            
        Returns:
            True if removed
        """
        with self._lock:
            if task_id not in self._task_index:
                return False
            
            # Can't easily remove from PriorityQueue, mark as cancelled
            task = self._task_index[task_id]
            task.payload['_cancelled'] = True
            return True
    
    def size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()
    
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return self._queue.empty()
    
    def clear(self) -> None:
        """Clear all tasks from queue."""
        with self._lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            self._task_index.clear()
    
    def get_queued_tasks(self) -> List[TaskItem]:
        """Get list of all queued tasks (for display)."""
        with self._lock:
            return list(self._task_index.values())


# Global queue instance
_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    """Get or create global task queue."""
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue
