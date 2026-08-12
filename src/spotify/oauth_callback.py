"""
OAuth Callback Handler - Local server for Spotify OAuth redirect.

Runs a lightweight HTTP server to receive OAuth callbacks from Spotify.
"""

import threading
import http.server
import socketserver
import urllib.parse
from typing import Optional, Callable, Dict
from datetime import datetime

from src.logging_module.app_logger import get_logger
from src.config.settings import settings


logger = get_logger()


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callbacks."""
    
    # Class-level storage for callback results
    _callback_results: Dict[str, Dict] = {}
    _callback_events: Dict[str, threading.Event] = {}
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def do_GET(self):
        """Handle GET requests (OAuth redirect)."""
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/callback':
            # Parse query parameters
            params = urllib.parse.parse_qs(parsed_path.query)
            
            # Extract code and state
            code = params.get('code', [None])[0]
            state = params.get('state', [None])[0]
            error = params.get('error', [None])[0]
            
            # Store result
            if state:
                self._callback_results[state] = {
                    'code': code,
                    'state': state,
                    'error': error,
                    'received_at': datetime.utcnow()
                }
                
                # Signal event
                if state in self._callback_events:
                    self._callback_events[state].set()
            
            # Send response
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            if error:
                response = f"""
                <html>
                    <head><title>Authentication Failed</title></head>
                    <body style="font-family: Arial; text-align: center; padding: 50px;">
                        <h1>Authentication Failed</h1>
                        <p>Error: {error}</p>
                        <p>You can close this window.</p>
                    </body>
                </html>
                """
            elif code:
                response = f"""
                <html>
                    <head><title>Authentication Successful</title></head>
                    <body style="font-family: Arial; text-align: center; padding: 50px;">
                        <h1>✅ Authentication Successful!</h1>
                        <p>Your Spotify account has been connected.</p>
                        <p>You can close this window and return to the application.</p>
                    </body>
                </html>
                """
            else:
                response = """
                <html>
                    <head><title>Invalid Callback</title></head>
                    <body style="font-family: Arial; text-align: center; padding: 50px;">
                        <h1>Invalid Callback</h1>
                        <p>No authorization code received.</p>
                        <p>You can close this window.</p>
                    </body>
                </html>
                """
            
            self.wfile.write(response.encode())
        else:
            self.send_response(404)
            self.end_headers()


class OAuthCallbackServer:
    """
    Local HTTP server for receiving OAuth callbacks.
    
    Runs on localhost and listens for Spotify OAuth redirects.
    """
    
    def __init__(self, port: int = 8888):
        """
        Initialize callback server.
        
        Args:
            port: Port to listen on (default: 8888)
        """
        self.port = port
        self.server: Optional[socketserver.TCPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
    
    def start(self) -> bool:
        """
        Start the callback server in a background thread.
        
        Returns:
            True if successful
        """
        if self._running:
            logger.warning("Callback server already running", "OAUTH_SERVER_RUNNING")
            return True
        
        try:
            # Allow port reuse
            socketserver.TCPServer.allow_reuse_address = True
            
            self.server = socketserver.TCPServer(
                ('127.0.0.1', self.port),
                OAuthCallbackHandler
            )
            
            self._thread = threading.Thread(
                target=self._serve_forever,
                name="OAuthCallbackServer",
                daemon=True
            )
            self._thread.start()
            self._running = True
            
            logger.info(f"OAuth callback server started on port {self.port}", "OAUTH_SERVER_START")
            return True
            
        except OSError as e:
            logger.error(f"Failed to start callback server: {e}", "OAUTH_SERVER_ERROR")
            return False
    
    def _serve_forever(self):
        """Run server loop."""
        if self.server:
            self.server.serve_forever()
    
    def stop(self):
        """Stop the callback server."""
        if not self._running:
            return
        
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        
        self._running = False
        self.server = None
        self._thread = None
        
        logger.info("OAuth callback server stopped", "OAUTH_SERVER_STOP")
    
    def wait_for_callback(self, state: str, timeout: float = 300.0) -> Optional[Dict]:
        """
        Wait for OAuth callback with specific state.
        
        Args:
            state: State string to wait for
            timeout: Max time to wait in seconds
            
        Returns:
            Callback data dict or None if timeout
        """
        if not self._running:
            logger.error("Callback server not running", "OAUTH_SERVER_NOT_RUNNING")
            return None
        
        # Create event for this state
        event = threading.Event()
        OAuthCallbackHandler._callback_events[state] = event
        
        # Wait for callback
        success = event.wait(timeout=timeout)
        
        # Clean up
        OAuthCallbackHandler._callback_events.pop(state, None)
        
        if success:
            result = OAuthCallbackHandler._callback_results.pop(state, None)
            if result:
                logger.info("OAuth callback received", "OAUTH_CALLBACK_RECEIVED")
                return result
        
        logger.warning("OAuth callback timeout", "OAUTH_CALLBACK_TIMEOUT")
        return None
    
    def get_callback_url(self) -> str:
        """Get the callback URL for OAuth configuration."""
        return f"http://127.0.0.1:{self.port}/callback"


# Global server instance
_callback_server: Optional[OAuthCallbackServer] = None


def get_oauth_callback_server(port: int = 8888) -> OAuthCallbackServer:
    """Get or create OAuth callback server instance."""
    global _callback_server
    if _callback_server is None:
        _callback_server = OAuthCallbackServer(port)
    return _callback_server


def start_oauth_listener(port: int = 8888) -> bool:
    """
    Start OAuth callback listener.
    
    Args:
        port: Port to listen on
        
    Returns:
        True if successful
    """
    server = get_oauth_callback_server(port)
    return server.start()


def stop_oauth_listener():
    """Stop OAuth callback listener."""
    global _callback_server
    if _callback_server:
        _callback_server.stop()
        _callback_server = None


def wait_for_oauth_callback(state: str, timeout: float = 300.0) -> Optional[Dict]:
    """
    Wait for OAuth callback with specific state.
    
    Args:
        state: State string to wait for
        timeout: Max time to wait in seconds
        
    Returns:
        Callback data dict or None if timeout
    """
    global _callback_server
    if _callback_server is None:
        logger.error("OAuth callback server not initialized", "OAUTH_SERVER_NOT_INIT")
        return None
    
    return _callback_server.wait_for_callback(state, timeout)


def get_oauth_callback_url() -> str:
    """Get the current callback URL."""
    global _callback_server
    if _callback_server is None:
        return settings.SPOTIFY_REDIRECT_URI or "http://127.0.0.1:8888/callback"
    
    return _callback_server.get_callback_url()
