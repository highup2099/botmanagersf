"""
Unit tests for Spotify Manager.
"""

import unittest
import os
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDatabaseInit(unittest.TestCase):
    """Test database initialization."""
    
    def test_database_module_imports(self):
        """Test that database module can be imported."""
        from src.database import database
        self.assertTrue(hasattr(database, 'Base'))
        self.assertTrue(hasattr(database, 'init_database'))
    
    def test_models_import(self):
        """Test that models can be imported."""
        from src.database import models
        self.assertTrue(hasattr(models, 'Profile'))
        self.assertTrue(hasattr(models, 'Task'))
        self.assertTrue(hasattr(models, 'ActivityLog'))


class TestSettings(unittest.TestCase):
    """Test configuration settings."""
    
    def test_settings_load(self):
        """Test that settings can be loaded."""
        from src.config.settings import settings
        self.assertIsNotNone(settings.BASE_DIR)
        self.assertIsNotNone(settings.DATA_DIR)
        self.assertIsNotNone(settings.LOGS_DIR)
        self.assertIsNotNone(settings.PROFILES_DIR)
    
    def test_valid_worker_counts(self):
        """Test valid worker counts are defined."""
        from src.config.settings import settings
        self.assertIn(1, settings.VALID_WORKER_COUNTS)
        self.assertIn(5, settings.VALID_WORKER_COUNTS)
        self.assertIn(10, settings.VALID_WORKER_COUNTS)


class TestTaskQueue(unittest.TestCase):
    """Test task queue functionality."""
    
    def test_queue_creation(self):
        """Test that task queue can be created."""
        from src.tasks.task_queue import TaskQueue
        queue = TaskQueue()
        self.assertEqual(queue.size(), 0)
        self.assertTrue(queue.is_empty())
    
    def test_queue_put_get(self):
        """Test adding and retrieving tasks from queue."""
        from src.tasks.task_queue import TaskQueue, TaskItem
        from src.database.models import TaskType, TaskPriority
        
        queue = TaskQueue()
        
        task = TaskItem(
            task_id=1,
            profile_id=1,
            task_type=TaskType.TRACK_REVIEW,
            payload={"test": "data"}
        )
        
        result = queue.put(task)
        self.assertTrue(result)
        self.assertEqual(queue.size(), 1)
        
        retrieved = queue.get(timeout=1.0)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.task_id, 1)


class TestWorkerPool(unittest.TestCase):
    """Test worker pool functionality."""
    
    def test_pool_creation(self):
        """Test that worker pool can be created."""
        from src.tasks.worker_pool import WorkerPool
        pool = WorkerPool(max_workers=3)
        self.assertEqual(pool.max_workers, 3)
        self.assertFalse(pool._running)
    
    def test_pool_status(self):
        """Test getting pool status."""
        from src.tasks.worker_pool import WorkerPool
        pool = WorkerPool(max_workers=5)
        status = pool.get_status()
        self.assertIn("running", status)
        self.assertIn("max_workers", status)
        self.assertIn("queue_size", status)


class TestProfileManager(unittest.TestCase):
    """Test profile manager functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_profile_manager_creation(self):
        """Test that profile manager can be created."""
        from src.browser.profile_manager import ProfileManager
        from pathlib import Path
        
        pm = ProfileManager(profiles_dir=Path(self.test_dir))
        self.assertIsNotNone(pm.profiles_dir)
    
    def test_create_profile_path(self):
        """Test creating profile directory."""
        from src.browser.profile_manager import ProfileManager
        from pathlib import Path
        
        pm = ProfileManager(profiles_dir=Path(self.test_dir))
        profile_path = pm.create_profile(123)
        
        self.assertTrue(profile_path.exists())
        self.assertTrue(profile_path.is_dir())
    
    def test_validate_profile(self):
        """Test profile validation."""
        from src.browser.profile_manager import ProfileManager
        from pathlib import Path
        
        pm = ProfileManager(profiles_dir=Path(self.test_dir))
        pm.create_profile(456)
        
        result = pm.validate_profile(456)
        self.assertTrue(result)
    
    def test_list_profiles(self):
        """Test listing profiles."""
        from src.browser.profile_manager import ProfileManager
        from pathlib import Path
        
        pm = ProfileManager(profiles_dir=Path(self.test_dir))
        pm.create_profile(1)
        pm.create_profile(2)
        
        profiles = pm.list_profiles()
        self.assertIn(1, profiles)
        self.assertIn(2, profiles)


class TestLogger(unittest.TestCase):
    """Test logging functionality."""
    
    def test_logger_creation(self):
        """Test that logger can be created."""
        from src.logging_module.app_logger import AppLogger
        logger = AppLogger()
        self.assertIsNotNone(logger.logger)
    
    def test_logger_methods(self):
        """Test logger has required methods."""
        from src.logging_module.app_logger import AppLogger
        logger = AppLogger()
        
        self.assertTrue(hasattr(logger, 'info'))
        self.assertTrue(hasattr(logger, 'error'))
        self.assertTrue(hasattr(logger, 'warning'))
        self.assertTrue(hasattr(logger, 'debug'))


class TestCompileAll(unittest.TestCase):
    """Test that all Python files compile correctly."""
    
    def test_compile_all_modules(self):
        """Test compiling all source modules."""
        import py_compile
        import tempfile
        
        src_dirs = [
            'src/config',
            'src/database',
            'src/gui',
            'src/spotify',
            'src/browser',
            'src/tasks',
            'src/logging_module'
        ]
        
        for src_dir in src_dirs:
            full_path = Path(__file__).parent.parent / src_dir
            if full_path.exists():
                for py_file in full_path.glob('*.py'):
                    if py_file.name != '__init__.py':
                        try:
                            py_compile.compile(str(py_file), doraise=True)
                        except py_compile.PyCompileError as e:
                            self.fail(f"Compilation failed for {py_file}: {e}")


if __name__ == '__main__':
    unittest.main()
