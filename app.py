"""
Spotify Manager - Main Application Entry Point

A legitimate internal music-management tool for Spotify.
Uses official OAuth/API capabilities where available.
"""

import sys
import customtkinter as ctk
from typing import Optional

# Import application components
from src.config.settings import settings
from src.database.database import init_database, DatabaseManager
from src.database.repositories import ProfileRepository, ActivityLogRepository
from src.database.models import ProfileStatus
from src.gui.app_window import create_main_window, Sidebar, LogPanel, WorkerSelector
from src.gui.profile_table import ProfileTable
from src.logging_module.app_logger import get_logger
from src.tasks.task_manager import get_task_manager


logger = get_logger()


class SpotifyManagerApp:
    """Main application class."""
    
    def __init__(self):
        self.window: Optional[ctk.CTk] = None
        self.current_frame: Optional[ctk.CTkFrame] = None
        self.task_manager = None
        
        # Initialize database
        self._init_database()
        
        # Create UI
        self._create_ui()
        
        # Start task manager
        self._start_task_manager()
    
    def _init_database(self):
        """Initialize SQLite database."""
        try:
            init_database()
            logger.info("Database initialized", "DB_INIT")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}", "DB_INIT_ERROR")
    
    def _start_task_manager(self):
        """Start background task processing."""
        try:
            self.task_manager = get_task_manager(max_workers=settings.MAX_WORKERS)
            self.task_manager.start()
            logger.info("Task manager started", "TASK_MANAGER_INIT")
        except Exception as e:
            logger.error(f"Task manager initialization failed: {e}", "TASK_MANAGER_ERROR")
    
    def _create_ui(self):
        """Create the main user interface."""
        self.window = create_main_window("Spotify Manager")
        
        # Main container
        main_container = ctk.CTkFrame(self.window)
        main_container.pack(fill="both", expand=True)
        
        # Sidebar
        self.sidebar = Sidebar(
            main_container,
            on_navigate=self._on_navigate
        )
        self.sidebar.pack(side="left", fill="y")
        
        # Content area
        content_area = ctk.CTkFrame(main_container)
        content_area.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        
        # Top bar with worker selector
        top_bar = ctk.CTkFrame(content_area)
        top_bar.pack(fill="x", pady=(0, 10))
        
        title_label = ctk.CTkLabel(
            top_bar,
            text="Dashboard",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(side="left")
        
        self.worker_selector = WorkerSelector(
            top_bar,
            on_change=self._on_worker_change
        )
        self.worker_selector.pack(side="right")
        
        # Content frames
        self.content_frames = {}
        
        for frame_name in ["dashboard", "profiles", "tasks", "queue", "activity", "settings"]:
            frame = ctk.CTkScrollableFrame(content_area)
            self.content_frames[frame_name] = frame
            
            if frame_name == "dashboard":
                self._create_dashboard(frame)
            elif frame_name == "profiles":
                self._create_profiles_frame(frame)
            elif frame_name == "activity":
                self._create_activity_frame(frame)
            else:
                placeholder = ctk.CTkLabel(
                    frame,
                    text=f"{frame_name.title()} - Coming Soon",
                    font=ctk.CTkFont(size=16)
                )
                placeholder.pack(expand=True)
        
        # Show dashboard by default
        self._show_frame("dashboard")
    
    def _create_dashboard(self, parent):
        """Create dashboard view."""
        # Stats row
        stats_frame = ctk.CTkFrame(parent)
        stats_frame.pack(fill="x", pady=10)
        
        stats = [
            ("Total Profiles", self._get_profile_count),
            ("Active Tasks", lambda: str(self.task_manager.queue.size() if self.task_manager else 0)),
            ("Workers Active", lambda: str(len(self.task_manager.worker_pool._workers) if self.task_manager else 0)),
            ("Spotify Connected", lambda: "Yes" if self._is_spotify_configured() else "No")
        ]
        
        for i, (label, getter) in enumerate(stats):
            stat_box = ctk.CTkFrame(stats_frame, width=200, height=100)
            stat_box.grid(row=0, column=i, padx=10, pady=5)
            
            val_label = ctk.CTkLabel(
                stat_box,
                text=getter(),
                font=ctk.CTkFont(size=24, weight="bold"),
                text_color="#3b82f6"
            )
            val_label.pack(pady=(20, 5))
            
            name_label = ctk.CTkLabel(stat_box, text=label)
            name_label.pack()
        
        stats_frame.grid_columnconfigure(0, weight=1)
        stats_frame.grid_columnconfigure(1, weight=1)
        stats_frame.grid_columnconfigure(2, weight=1)
        stats_frame.grid_columnconfigure(3, weight=1)
        
        # Quick actions
        actions_frame = ctk.CTkFrame(parent)
        actions_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(actions_frame, text="Quick Actions", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w")
        
        btn_frame = ctk.CTkFrame(actions_frame)
        btn_frame.pack(fill="x", pady=5)
        
        ctk.CTkButton(btn_frame, text="+ Add Profile", command=lambda: self._on_navigate("profiles")).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="View Logs", command=lambda: self._on_navigate("activity")).pack(side="left", padx=5)
    
    def _create_profiles_frame(self, parent):
        """Create profiles management view."""
        self.profile_table = ProfileTable(parent, on_action=self._on_profile_action)
        self.profile_table.pack(fill="both", expand=True)
        self.profile_table.refresh_data()
    
    def _create_activity_frame(self, parent):
        """Create activity log view."""
        self.log_panel = LogPanel(parent)
        self.log_panel.pack(fill="both", expand=True)
        
        # Load recent logs
        try:
            with DatabaseManager() as session:
                repo = ActivityLogRepository(session)
                logs = repo.get_recent(limit=50)
                for log in reversed(logs):
                    self.log_panel.log(log.message, log.level.value.upper())
        except Exception:
            pass
    
    def _show_frame(self, frame_name: str):
        """Show a specific frame."""
        # Hide all frames
        for frame in self.content_frames.values():
            frame.pack_forget()
        
        # Show selected frame
        self.content_frames[frame_name].pack(fill="both", expand=True)
    
    def _on_navigate(self, page_id: str):
        """Handle navigation."""
        self._show_frame(page_id)
        
        # Refresh data when navigating to certain pages
        if page_id == "profiles" and hasattr(self, "profile_table"):
            self.profile_table.refresh_data()
        elif page_id == "activity" and hasattr(self, "log_panel"):
            pass  # Already loaded
    
    def _on_worker_change(self, count: int):
        """Handle worker count change."""
        logger.info(f"Worker count changed to {count}", "WORKER_CHANGE")
        # Could restart task manager with new count here
    
    def _on_profile_action(self, action: str, profile_id: int):
        """Handle profile table actions."""
        logger.info(f"Profile action: {action} for ID {profile_id}", "PROFILE_ACTION")
        
        if action == "add_profile":
            self._add_profile()
        elif action == "open_profile":
            logger.info(f"Opening profile {profile_id}", "PROFILE_OPEN", profile_id)
    
    def _add_profile(self):
        """Add a new profile."""
        try:
            with DatabaseManager() as session:
                repo = ProfileRepository(session)
                profile = repo.create(name=f"Profile {repo.get_all().__len__() + 1}")
                logger.info(f"Created profile {profile.id}", "PROFILE_CREATED", profile.id)
                
                # Create browser profile path
                repo.get_or_create_browser_path(profile.id)
                
                # Refresh table if visible
                if hasattr(self, "profile_table"):
                    self.profile_table.refresh_data()
        except Exception as e:
            logger.error(f"Failed to create profile: {e}", "PROFILE_CREATE_ERROR")
    
    def _get_profile_count(self) -> str:
        """Get total profile count."""
        try:
            with DatabaseManager() as session:
                repo = ProfileRepository(session)
                return str(len(repo.get_all()))
        except Exception:
            return "0"
    
    def _is_spotify_configured(self) -> bool:
        """Check if Spotify OAuth is configured."""
        return bool(settings.SPOTIFY_CLIENT_ID and settings.SPOTIFY_CLIENT_SECRET)
    
    def run(self):
        """Run the application."""
        logger.info("Application starting", "APP_START")
        self.window.mainloop()
        logger.info("Application stopped", "APP_STOP")
        
        # Cleanup
        if self.task_manager:
            self.task_manager.stop(wait=False)


def main():
    """Main entry point."""
    app = SpotifyManagerApp()
    app.run()


if __name__ == "__main__":
    main()
