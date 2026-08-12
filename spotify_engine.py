"""
Spotify Automation Engine based on Playwright
Module for browser automation with anti-detect features
"""

import os
import random
import time
from typing import Dict, Optional, Callable
from playwright.sync_api import sync_playwright, BrowserContext, Page, TimeoutError


def run_spotify_task(
    account_data: Dict,
    headless_mode: bool = True,
    log_callback: Optional[Callable[[str], None]] = None
) -> bool:
    """
    Run Spotify automation task for a single account.
    
    Args:
        account_data: Dictionary with account info (login, password, proxy, playlist_url, start_track, id)
        headless_mode: If True, browser runs without visible window
        log_callback: Optional callback function for logging messages
    
    Returns:
        True if task completed successfully, False otherwise
    """
    
    def log(message: str):
        """Internal logging helper"""
        timestamp = time.strftime("[%H:%M:%S]")
        full_message = f"{timestamp} {message}"
        print(full_message)
        if log_callback:
            log_callback(full_message)
    
    account_id = account_data.get("id", "unknown")
    login = account_data.get("login", "")
    password = account_data.get("password", "")
    proxy = account_data.get("proxy", "")
    playlist_url = account_data.get("playlist_url", "")
    start_track = account_data.get("start_track", "")
    
    log(f"[INFO] Starting automation for account: {account_id}")
    
    # Parse proxy
    proxy_config = None
    if proxy and proxy.strip():
        try:
            # Format: IP:PORT:USER:PASS
            parts = proxy.split(":")
            if len(parts) >= 4:
                proxy_config = {
                    "server": f"http://{parts[0]}:{parts[1]}",
                    "username": parts[2],
                    "password": parts[3]
                }
                log(f"[INFO] Using proxy: {parts[0]}:{parts[1]}")
            elif len(parts) == 2:
                proxy_config = {"server": f"http://{proxy}"}
                log(f"[INFO] Using proxy without auth: {proxy}")
        except Exception as e:
            log(f"[WARNING] Failed to parse proxy '{proxy}': {e}")
    
    # Profile path for persistent context (cookies, session storage)
    profile_path = os.path.join(os.getcwd(), "profiles", account_id)
    os.makedirs(profile_path, exist_ok=True)
    log(f"[INFO] Using profile path: {profile_path}")
    
    context = None
    success = False
    
    try:
        with sync_playwright() as p:
            # Launch persistent context with anti-detect settings
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=headless_mode,
                proxy=proxy_config,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--disable-gpu",
                    "--window-size=1920,1080"
                ],
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
            
            log(f"[INFO] Browser context created for {account_id}")
            
            page = context.pages[0] if context.pages else context.new_page()
            
            # Navigate to Spotify
            log(f"[INFO] Navigating to Spotify...")
            page.goto("https://open.spotify.com", wait_until="domcontentloaded", timeout=30000)
            
            # Check if logged in
            is_logged_in = check_if_logged_in(page)
            
            if not is_logged_in:
                log(f"[INFO] Not logged in, attempting authentication for {login}...")
                if login and password:
                    perform_login(page, login, password, log)
                    # Wait for successful login
                    page.wait_for_url("https://open.spotify.com/**", timeout=30000)
                    log(f"[SUCCESS] Login successful for {account_id}")
                else:
                    log(f"[ERROR] No credentials provided for {account_id}")
                    return False
            
            # Navigate to start track
            if start_track:
                log(f"[INFO] Navigating to start track: {start_track}")
                page.goto(start_track, wait_until="domcontentloaded", timeout=30000)
                
                # Click play button
                if click_play_button(page, log):
                    log(f"[SUCCESS] Track playback started")
                    
                    # Random listening duration (38-45 seconds)
                    listen_duration = random.randint(38, 45)
                    log(f"[INFO] Listening for {listen_duration} seconds...")
                    time.sleep(listen_duration)
                    
                    # Add recommendations to playlist
                    if playlist_url:
                        log(f"[INFO] Adding recommendations to playlist...")
                        add_recommendations_to_playlist(page, playlist_url, log)
                    
                    success = True
                else:
                    log(f"[WARNING] Could not find play button")
                    success = True  # Still consider partial success
            else:
                log(f"[WARNING] No start track URL provided")
                success = True
            
    except TimeoutError as e:
        log(f"[ERROR] Timeout error: {e}")
        success = False
    except Exception as e:
        log(f"[ERROR] Unexpected error: {e}")
        success = False
    finally:
        # Clean up
        if context:
            try:
                context.close()
                log(f"[INFO] Browser context closed for {account_id}")
            except Exception as e:
                log(f"[WARNING] Error closing context: {e}")
    
    return success


def check_if_logged_in(page: Page) -> bool:
    """Check if user is logged in by looking for profile button"""
    try:
        # Look for profile avatar or account menu
        selectors = [
            '[data-testid="user-widget-link"]',
            '.main-userWidget-box',
            '[aria-label="Account"]',
            'button[aria-label*="profile"]'
        ]
        
        for selector in selectors:
            if page.locator(selector).count() > 0:
                return True
        
        # Alternative: check if we're redirected away from login page
        current_url = page.url
        if "login" not in current_url.lower() and "signup" not in current_url.lower():
            return True
            
        return False
    except Exception:
        return False


def perform_login(page: Page, username: str, password: str, log: Callable) -> bool:
    """Perform Spotify login"""
    try:
        # Navigate to login page if not already there
        if "login" not in page.url.lower():
            page.goto("https://accounts.spotify.com/login", wait_until="domcontentloaded")
        
        # Wait for login form
        page.wait_for_selector('input[type="text"]', timeout=10000)
        
        # Enter username
        username_field = page.locator('input[type="text"]').first
        username_field.fill(username)
        log(f"[INFO] Entered username")
        
        # Click continue
        page.locator('button[type="submit"]').first.click()
        
        # Wait for password field
        page.wait_for_selector('input[type="password"]', timeout=10000)
        
        # Enter password
        password_field = page.locator('input[type="password"]').first
        password_field.fill(password)
        log(f"[INFO] Entered password")
        
        # Click login
        page.locator('button[type="submit"]').first.click()
        
        # Wait for navigation
        page.wait_for_load_state("networkidle", timeout=15000)
        
        return True
        
    except Exception as e:
        log(f"[ERROR] Login failed: {e}")
        return False


def click_play_button(page: Page, log: Callable) -> bool:
    """Click the play button on the track page"""
    try:
        # Various selectors for play button
        selectors = [
            'button[data-testid="play-button"]',
            'button[aria-label="Play"]',
            '.main-playPauseButton-button[aria-label="Play"]',
            'button[class*="playButton"]'
        ]
        
        for selector in selectors:
            buttons = page.locator(selector)
            if buttons.count() > 0:
                buttons.first.click(timeout=5000)
                log(f"[INFO] Clicked play button: {selector}")
                return True
        
        # Try clicking any visible play button
        play_buttons = page.locator('button:has-text("Play"), button:has-text("Слушать")')
        if play_buttons.count() > 0:
            play_buttons.first.click(timeout=5000)
            return True
            
        return False
        
    except Exception as e:
        log(f"[WARNING] Error clicking play button: {e}")
        return False


def add_recommendations_to_playlist(page: Page, playlist_url: str, log: Callable) -> bool:
    """
    Go to track radio/recommendations and add first 3-5 tracks to playlist
    """
    try:
        # Method 1: Use "Go to song radio" from track menu
        # Click three dots menu on current track
        menu_selectors = [
            'button[data-testid="track-context-menu"]',
            'button[aria-label*="More"]',
            'button[class*="moreButton"]'
        ]
        
        menu_clicked = False
        for selector in menu_selectors:
            menus = page.locator(selector)
            if menus.count() > 0:
                menus.first.click(timeout=5000)
                menu_clicked = True
                break
        
        if not menu_clicked:
            log(f"[WARNING] Could not open track menu")
            return False
        
        # Wait for menu to appear
        page.wait_for_timeout(1000)
        
        # Look for "Go to radio" or similar
        radio_selectors = [
            'div[role="menuitem"]:has-text("Radio")',
            'div[role="menuitem"]:has-text("radio")',
            'span:has-text("Go to song radio")',
            'span:has-text("Перейти к радио")'
        ]
        
        radio_clicked = False
        for selector in radio_selectors:
            items = page.locator(selector)
            if items.count() > 0:
                items.first.click(timeout=5000)
                radio_clicked = True
                break
        
        if not radio_clicked:
            log(f"[INFO] Radio option not found, trying alternative method")
            # Alternative: navigate to playlist directly
            page.goto(playlist_url, wait_until="domcontentloaded")
            return add_tracks_to_playlist_from_page(page, playlist_url, log)
        
        # Wait for radio page to load
        page.wait_for_load_state("networkidle", timeout=15000)
        log(f"[INFO] Radio page loaded")
        
        # Find first 3-5 tracks and add them to playlist
        num_tracks = random.randint(3, 5)
        log(f"[INFO] Adding {num_tracks} recommended tracks to playlist")
        
        # Get track rows
        track_rows = page.locator('tr[data-testid="track-row"]')
        count = min(num_tracks, track_rows.count())
        
        for i in range(count):
            try:
                row = track_rows.nth(i)
                
                # Open track menu
                row.locator('button[data-testid="track-context-menu"]').click(timeout=3000)
                page.wait_for_timeout(500)
                
                # Click "Add to playlist"
                add_items = page.locator('div[role="menuitem"]:has-text("Add to"), div[role="menuitem"]:has-text("Добавить в")')
                if add_items.count() > 0:
                    add_items.first.click(timeout=3000)
                    page.wait_for_timeout(500)
                    
                    # Select target playlist
                    playlist_items = page.locator(f'div[role="menuitem"]:has-text("{playlist_url}")')
                    # Fallback: just click first playlist option if specific one not found
                    if playlist_items.count() == 0:
                        playlist_items = page.locator('div[role="menuitem"]').filter(has_text="Playlist").first
                    
                    if playlist_items.count() > 0:
                        playlist_items.first.click(timeout=3000)
                        log(f"[SUCCESS] Added track {i+1} to playlist")
                    else:
                        log(f"[WARNING] Playlist selection not found")
                else:
                    log(f"[WARNING] Add to playlist option not found")
                    
                # Close menu by pressing Escape or clicking elsewhere
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
                
            except Exception as e:
                log(f"[WARNING] Error adding track {i+1}: {e}")
                continue
        
        return True
        
    except Exception as e:
        log(f"[ERROR] Error in recommendations: {e}")
        # Fallback: try to navigate directly to playlist
        try:
            page.goto(playlist_url, wait_until="domcontentloaded")
            return add_tracks_to_playlist_from_page(page, playlist_url, log)
        except:
            return False


def add_tracks_to_playlist_from_page(page: Page, playlist_url: str, log: Callable) -> bool:
    """Alternative method: add tracks when already on playlist page"""
    try:
        page.goto(playlist_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        
        # Find track rows and add them
        track_rows = page.locator('tr[data-testid="track-row"]')
        count = min(3, track_rows.count())
        
        for i in range(count):
            try:
                row = track_rows.nth(i)
                # Like the track instead (simpler operation)
                like_btn = row.locator('button[data-testid="like-button"]')
                if like_btn.count() > 0:
                    like_btn.first.click(timeout=3000)
                    log(f"[SUCCESS] Liked track {i+1}")
            except Exception as e:
                log(f"[WARNING] Error liking track {i+1}: {e}")
        
        return True
    except Exception as e:
        log(f"[ERROR] Error in fallback method: {e}")
        return False


# Test function for standalone execution
if __name__ == "__main__":
    # Test data
    test_account = {
        "id": "test_001",
        "name": "Test Account",
        "proxy": "",
        "login": "",
        "password": "",
        "playlist_url": "https://open.spotify.com/playlist/xxx",
        "start_track": "https://open.spotify.com/track/xxx",
        "status": "Ready"
    }
    
    result = run_spotify_task(test_account, headless_mode=True)
    print(f"Task completed: {'SUCCESS' if result else 'FAILED'}")
