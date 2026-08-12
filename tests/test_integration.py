"""
Integration tests for Spotify Manager.

Tests full workflows including:
- Database initialization
- Profile creation and management
- Task creation and execution
- Worker queue processing
- Configuration loading
"""

import unittest
import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDatabaseIntegration(unittest.TestCase):
    """Test database integration."""
    
    def setUp(self):
        """Set up test database."""
        self.test_db = tempfile.mktemp(suffix='.db')
        os.environ['SPOTIFY_MANAGER_DB'] = self.test_db
        
    def tearDown(self):
        """Clean up test database."""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        os.environ.pop('SPOTIFY_MANAGER_DB', None)
    
    def test_database_initialization(self):
        """Test that database initializes with all tables."""
        from src.database.database import init_database, DatabaseManager
        from src.database.models import Base
        
        # Reinitialize with test DB
        from src.config import settings as app_settings
        original_db = app_settings.settings.DATABASE_PATH
        app_settings.settings.DATABASE_PATH = self.test_db
        
        try:
            init_database()
            
            with DatabaseManager() as session:
                # Check tables exist
                tables = Base.metadata.tables.keys()
                self.assertIn('profiles', tables)
                self.assertIn('proxies', tables)
                self.assertIn('playlists', tables)
                self.assertIn('tasks', tables)
                self.assertIn('task_runs', tables)
                self.assertIn('activity_logs', tables)
        finally:
            app_settings.settings.DATABASE_PATH = original_db
    
    def test_profile_crud(self):
        """Test profile create, read, update, delete."""
        from src.database.database import init_database, DatabaseManager
        from src.database.repositories import ProfileRepository
        from src.database.models import ProfileStatus
        
        from src.config import settings as app_settings
        original_db = app_settings.settings.DATABASE_PATH
        app_settings.settings.DATABASE_PATH = self.test_db
        
        try:
            init_database()
            
            with DatabaseManager() as session:
                repo = ProfileRepository(session)
                
                # Create
                profile = repo.create(name="Test Profile", country="US")
                profile_id = profile.id  # Store ID before leaving context
                self.assertIsNotNone(profile_id)
                self.assertEqual(profile.name, "Test Profile")
                self.assertEqual(profile.status, ProfileStatus.INACTIVE)
                
                # Read - need new session since profile is detached
                with DatabaseManager() as session2:
                    repo2 = ProfileRepository(session2)
                    all_profiles = repo2.get_all()
                    self.assertEqual(len(all_profiles), 1)
                    
                    # Update
                    updated = repo2.update_status(profile_id, ProfileStatus.ACTIVE)
                    self.assertEqual(updated.status, ProfileStatus.ACTIVE)
                
                # Delete (via session)
                with DatabaseManager() as session3:
                    profile_to_delete = session3.query(type(profile)).filter(type(profile).id == profile_id).first()
                    if profile_to_delete:
                        session3.delete(profile_to_delete)
                        session3.commit()
                    
                    # Verify deletion
                    repo3 = ProfileRepository(session3)
                    all_profiles = repo3.get_all()
                    self.assertEqual(len(all_profiles), 0)
        finally:
            app_settings.settings.DATABASE_PATH = original_db


class TestTaskIntegration(unittest.TestCase):
    """Test task system integration."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_db = tempfile.mktemp(suffix='.db')
        os.environ['SPOTIFY_MANAGER_DB'] = self.test_db
        
        from src.config import settings as app_settings
        app_settings.settings.DATABASE_PATH = self.test_db
        
        from src.database.database import init_database
        init_database()
    
    def tearDown(self):
        """Clean up."""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        os.environ.pop('SPOTIFY_MANAGER_DB', None)
        
        # Reset task manager singleton
        from src.tasks import task_manager
        task_manager._task_manager = None
    
    def test_task_creation_and_queue(self):
        """Test creating tasks and adding to queue."""
        from src.database.database import DatabaseManager
        from src.database.repositories import ProfileRepository
        from src.tasks.task_manager import TaskManager
        from src.database.models import TaskType, TaskPriority
        
        # Create a profile first
        with DatabaseManager() as session:
            profile_repo = ProfileRepository(session)
            profile = profile_repo.create(name="Task Test Profile")
        
        # Create task manager
        tm = TaskManager(max_workers=2)
        
        # Create track review task
        task_id = tm.create_track_review_task(
            profile_id=profile.id,
            track_uri="spotify:track:4iV5W9uYEdYUVa79Axb7Rh",
            priority=TaskPriority.HIGH
        )
        
        self.assertIsNotNone(task_id)
        self.assertEqual(tm.queue.size(), 1)
    
    def test_task_status_transitions(self):
        """Test task status transitions."""
        from src.database.database import DatabaseManager
        from src.database.repositories import TaskRepository
        from src.database.models import TaskStatus, TaskPriority
        
        with DatabaseManager() as session:
            repo = TaskRepository(session)
            
            # Create task with proper enum
            task = repo.create(
                profile_id=1,
                task_type="track_review",
                payload='{}',
                priority=TaskPriority.NORMAL
            )
            
            # Initial status should be QUEUED
            self.assertEqual(task.status, TaskStatus.QUEUED)
            
            # Transition to RUNNING
            repo.update_status(task.id, TaskStatus.RUNNING)
            
            # Refresh from DB
            session.refresh(task)
            self.assertEqual(task.status, TaskStatus.RUNNING)
            
            # Transition to COMPLETED
            repo.update_status(task.id, TaskStatus.COMPLETED)
            session.refresh(task)
            self.assertEqual(task.status, TaskStatus.COMPLETED)


class TestWorkerPoolIntegration(unittest.TestCase):
    """Test worker pool integration."""
    
    def test_worker_pool_lifecycle(self):
        """Test starting and stopping worker pool."""
        from src.tasks.worker_pool import WorkerPool
        
        pool = WorkerPool(max_workers=3)
        
        # Start pool
        pool.start()
        self.assertTrue(pool._running)
        self.assertEqual(len(pool._workers), 3)
        
        # Wait a bit for workers to initialize
        import time
        time.sleep(0.5)
        
        # Check active workers
        status = pool.get_status()
        self.assertTrue(status['running'])
        self.assertEqual(status['max_workers'], 3)
        
        # Stop pool
        pool.stop(wait=True, timeout=2.0)
        self.assertFalse(pool._running)
    
    def test_worker_processes_task(self):
        """Test that worker can process a simple task."""
        from src.tasks.task_queue import TaskQueue, TaskItem
        from src.tasks.worker_pool import WorkerPool
        from src.database.models import TaskType, TaskPriority
        
        # Setup
        queue = TaskQueue()
        task = TaskItem(
            task_id=999,
            profile_id=1,
            task_type=TaskType.AUTH_REFRESH,  # Simple task that doesn't need browser
            payload={}
        )
        queue.put(task)
        
        pool = WorkerPool(max_workers=1)
        pool.queue = queue  # Use our test queue
        
        # Start pool
        pool.start()
        
        # Wait for task processing
        import time
        time.sleep(2.0)
        
        # Stop pool
        pool.stop(wait=True, timeout=2.0)
        
        # Queue should be empty (task processed)
        self.assertEqual(queue.size(), 0)


class TestConfigurationLoading(unittest.TestCase):
    """Test configuration loading."""
    
    def test_settings_from_env(self):
        """Test loading settings from environment."""
        # Set test environment variables
        os.environ['SPOTIFY_CLIENT_ID'] = 'test_client_id'
        os.environ['SPOTIFY_CLIENT_SECRET'] = 'test_client_secret'
        os.environ['SPOTIFY_REDIRECT_URI'] = 'http://localhost:8888/callback'
        
        # Reload settings
        import importlib
        from src.config import settings
        importlib.reload(settings)
        
        try:
            self.assertEqual(settings.settings.SPOTIFY_CLIENT_ID, 'test_client_id')
            self.assertEqual(settings.settings.SPOTIFY_CLIENT_SECRET, 'test_client_secret')
            self.assertEqual(settings.settings.SPOTIFY_REDIRECT_URI, 'http://localhost:8888/callback')
        finally:
            # Clean up
            os.environ.pop('SPOTIFY_CLIENT_ID', None)
            os.environ.pop('SPOTIFY_CLIENT_SECRET', None)
            os.environ.pop('SPOTIFY_REDIRECT_URI', None)
            importlib.reload(settings)
    
    def test_valid_worker_counts(self):
        """Test that valid worker counts are properly defined."""
        from src.config.settings import settings
        
        expected_counts = [1, 2, 3, 4, 5, 10]
        for count in expected_counts:
            self.assertIn(count, settings.VALID_WORKER_COUNTS)


class TestProfileManagerIntegration(unittest.TestCase):
    """Test profile manager integration."""
    
    def setUp(self):
        """Set up test profiles directory."""
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test directory."""
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_profile_isolation(self):
        """Test that profiles have isolated directories."""
        from src.browser.profile_manager import ProfileManager
        from pathlib import Path
        
        pm = ProfileManager(profiles_dir=Path(self.test_dir))
        
        # Create multiple profiles
        path1 = pm.create_profile(100)
        path2 = pm.create_profile(200)
        path3 = pm.create_profile(300)
        
        # Verify isolation
        self.assertNotEqual(path1, path2)
        self.assertNotEqual(path2, path3)
        self.assertNotEqual(path1, path3)
        
        # Verify directories exist
        self.assertTrue(path1.exists())
        self.assertTrue(path2.exists())
        self.assertTrue(path3.exists())
        
        # Verify no overlap
        self.assertFalse(path1.is_relative_to(path2))
        self.assertFalse(path2.is_relative_to(path3))


if __name__ == '__main__':
    unittest.main()
