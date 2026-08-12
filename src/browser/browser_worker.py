"""
Browser worker for Playwright-based automation.
Clean abstraction for browser operations - no stealth features.
"""

from typing import Optional, Callable, Dict, Any
from playwright.sync_api import sync_playwright, BrowserContext, Page, TimeoutError

from src.browser.profile_manager import get_profile_manager
from src.logging_module.app_logger import get_logger
from src.config.settings import settings


logger = get_logger()


class BrowserWorkerError(Exception):
    """Exception raised for browser worker errors."""
    pass


class BrowserWorker:
    """
    Browser worker for a single profile.
    
    Manages browser context lifecycle and provides clean API for navigation.
    """
    
    def __init__(self, profile_id: int, headless: bool = False):
        """
        Initialize browser worker.
        
        Args:
            profile_id: Profile ID for isolated session
            headless: Run browser without visible window
        """
        self.profile_id = profile_id
        self.headless = headless
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._playwright = None
        self._is_running = False
    
    def start(self) -> bool:
        """
        Start browser with profile's isolated session.
        
        Returns:
            True if successful
        """
        if self._is_running:
            logger.warning("Browser already running", "BROWSER_ALREADY_RUNNING", self.profile_id)
            return True
        
        try:
            profile_manager = get_profile_manager()
            profile_path = profile_manager.create_profile(self.profile_id)
            
            # Validate profile path
            if not profile_manager.validate_profile(self.profile_id):
                raise BrowserWorkerError(f"Invalid profile path: {profile_path}")
            
            self._playwright = sync_playwright().start()
            
            # Launch persistent context with standard settings
            # No anti-detect or stealth features
            self.context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_path),
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--disable-gpu",
                    "--window-size=1920,1080"
                ],
                viewport={"width": 1920, "height": 1080}
            )
            
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self._is_running = True
            
            logger.browser_event(f"Browser started (headless={self.headless})", self.profile_id)
            return True
            
        except Exception as e:
            logger.error(f"Failed to start browser: {e}", "BROWSER_START_ERROR", self.profile_id)
            self.stop()
            return False
    
    def stop(self) -> None:
        """Stop browser and cleanup resources."""
        try:
            if self.context:
                self.context.close()
                self.context = None
            
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
            
            self.page = None
            self._is_running = False
            
            logger.browser_event("Browser stopped", self.profile_id)
            
        except Exception as e:
            logger.error(f"Error stopping browser: {e}", "BROWSER_STOP_ERROR", self.profile_id)
    
    def open(self, url: str, wait_for_load: bool = True) -> bool:
        """
        Navigate to URL.
        
        Args:
            url: URL to navigate to
            wait_for_load: Wait for page load
            
        Returns:
            True if successful
        """
        if not self._is_running or not self.page:
            logger.error("Browser not running", "BROWSER_NOT_RUNNING", self.profile_id)
            return False
        
        try:
            self.page.goto(url, wait_until="domcontentloaded" if wait_for_load else None, timeout=30000)
            logger.browser_event(f"Navigated to: {url[:50]}...", self.profile_id)
            return True
            
        except TimeoutError:
            logger.warning(f"Navigation timeout: {url[:50]}...", "BROWSER_TIMEOUT", self.profile_id)
            return False
        except Exception as e:
            logger.error(f"Navigation failed: {e}", "BROWSER_NAV_ERROR", self.profile_id)
            return False
    
    def is_running(self) -> bool:
        """Check if browser is currently running."""
        return self._is_running and self.context is not None
    
    def get_page(self) -> Optional[Page]:
        """Get current page object."""
        return self.page
    
    def click(self, selector: str, timeout: int = 5000) -> bool:
        """
        Click element matching selector.
        
        Args:
            selector: CSS selector
            timeout: Click timeout in ms
            
        Returns:
            True if successful
        """
        if not self.page:
            return False
        
        try:
            self.page.locator(selector).first.click(timeout=timeout)
            return True
        except Exception:
            return False
    
    def fill(self, selector: str, value: str) -> bool:
        """
        Fill input field with value.
        
        Args:
            selector: CSS selector
            value: Value to fill
            
        Returns:
            True if successful
        """
        if not self.page:
            return False
        
        try:
            self.page.locator(selector).first.fill(value)
            return True
        except Exception:
            return False
    
    def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        """
        Wait for element to appear.
        
        Args:
            selector: CSS selector
            timeout: Wait timeout in ms
            
        Returns:
            True if element found
        """
        if not self.page:
            return False
        
        try:
            self.page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False
    
    def get_url(self) -> str:
        """Get current URL."""
        if self.page:
            return self.page.url
        return ""
    
    def screenshot(self, path: str) -> bool:
        """
        Take screenshot.
        
        Args:
            path: File path to save screenshot
            
        Returns:
            True if successful
        """
        if not self.page:
            return False
        
        try:
            self.page.screenshot(path=path)
            return True
        except Exception:
            return False


# Worker pool management
class BrowserWorkerPool:
    """
    Pool of browser workers.
    
    Manages multiple workers with concurrency limits.
    """
    
    def __init__(self, max_workers: int = 5):
        """
        Initialize worker pool.
        
        Args:
            max_workers: Maximum concurrent workers
        """
        self.max_workers = max_workers
        self.workers: Dict[int, BrowserWorker] = {}
    
    def get_or_create_worker(self, profile_id: int, headless: bool = False) -> BrowserWorker:
        """
        Get existing worker or create new one.
        
        Args:
            profile_id: Profile ID
            headless: Run in headless mode
            
        Returns:
            BrowserWorker instance
        """
        if profile_id not in self.workers:
            if len(self.workers) >= self.max_workers:
                raise BrowserWorkerError(f"Worker pool full (max={self.max_workers})")
            
            self.workers[profile_id] = BrowserWorker(profile_id, headless)
        
        return self.workers[profile_id]
    
    def remove_worker(self, profile_id: int) -> None:
        """Remove and stop a worker."""
        if profile_id in self.workers:
            self.workers[profile_id].stop()
            del self.workers[profile_id]
    
    def stop_all(self) -> None:
        """Stop all workers."""
        for worker in self.workers.values():
            worker.stop()
        self.workers.clear()
    
    def get_active_count(self) -> int:
        """Get count of active workers."""
        return sum(1 for w in self.workers.values() if w.is_running())


# Global pool instance
_worker_pool: Optional[BrowserWorkerPool] = None


def get_browser_worker_pool(max_workers: int = 5) -> BrowserWorkerPool:
    """Get or create browser worker pool."""
    global _worker_pool
    if _worker_pool is None:
        _worker_pool = BrowserWorkerPool(max_workers)
    return _worker_pool
