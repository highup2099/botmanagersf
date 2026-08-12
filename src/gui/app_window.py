"""
Main application window for Spotify Manager.
Uses CustomTkinter with clean architecture.
"""

import customtkinter as ctk
from typing import Optional, Callable
import threading

from src.config.settings import settings
from src.logging_module.app_logger import get_logger


logger = get_logger()


# Configure customtkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class Sidebar(ctk.CTkFrame):
    """Navigation sidebar."""
    
    def __init__(self, master, on_navigate: Callable[[str], None], **kwargs):
        super().__init__(master, width=150, corner_radius=0, **kwargs)
        
        self.on_navigate = on_navigate
        self.current_page = "dashboard"
        
        self._create_buttons()
    
    def _create_buttons(self):
        """Create navigation buttons."""
        pages = [
            ("dashboard", "📊 Dashboard"),
            ("profiles", "👤 Profiles"),
            ("tasks", "📋 Tasks"),
            ("queue", "⏱ Queue"),
            ("activity", "📝 Activity"),
            ("settings", "⚙️ Settings")
        ]
        
        self.buttons = {}
        
        for i, (page_id, text) in enumerate(pages):
            btn = ctk.CTkButton(
                self,
                text=text,
                command=lambda p=page_id: self._on_click(p),
                anchor="w",
                padx=20
            )
            btn.grid(row=i, column=0, sticky="ew", pady=5, padx=10)
            self.buttons[page_id] = btn
        
        # Highlight dashboard by default
        self._highlight_button("dashboard")
        
        self.grid_columnconfigure(0, weight=1)
    
    def _on_click(self, page_id: str):
        """Handle button click."""
        self._highlight_button(page_id)
        self.on_navigate(page_id)
    
    def _highlight_button(self, page_id: str):
        """Highlight selected button."""
        for pid, btn in self.buttons.items():
            if pid == page_id:
                btn.configure(fg_color="#3b82f6")
            else:
                btn.configure(fg_color="transparent")
        
        self.current_page = page_id


class LogPanel(ctk.CTkFrame):
    """Real-time log display panel."""
    
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create log widgets."""
        # Title
        title = ctk.CTkLabel(self, text="Activity Log", font=ctk.CTkFont(size=14, weight="bold"))
        title.pack(fill="x", padx=10, pady=5)
        
        # Log textbox
        self.log_text = ctk.CTkTextbox(self, state="disabled", height=200)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Clear button
        clear_btn = ctk.CTkButton(
            self,
            text="Clear Log",
            command=self._clear_log,
            width=100,
            fg_color="transparent",
            border_width=1
        )
        clear_btn.pack(anchor="e", padx=10, pady=5)
    
    def log(self, message: str, level: str = "INFO"):
        """Add log entry."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        self.log_text.configure(state="normal")
        
        # Color coding
        colors = {
            "ERROR": "#ff6b6b",
            "WARNING": "#fcc419",
            "SUCCESS": "#51cf66",
            "INFO": "#74c0fc"
        }
        color = colors.get(level, "#ffffff")
        
        entry = f"[{timestamp}] [{level}] {message}\n"
        self.log_text.insert("end", entry)
        
        # Apply color to last line
        end_pos = "end-1c"
        start_pos = f"end-{len(entry)+1}c linestart"
        self.log_text.tag_configure(level.lower(), foreground=color)
        self.log_text.tag_add(level.lower(), start_pos, end_pos)
        
        self.log_text.configure(state="disabled")
        self.log_text.see("end")
    
    def _clear_log(self):
        """Clear log display."""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")


class WorkerSelector(ctk.CTkFrame):
    """Worker/concurrency selector using ComboBox instead of SpinBox."""
    
    def __init__(self, master, on_change: Callable[[int], None] = None, **kwargs):
        super().__init__(master, **kwargs)
        
        self.on_change = on_change
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create selector widgets."""
        label = ctk.CTkLabel(self, text="Workers:")
        label.pack(side="left", padx=(0, 5))
        
        # Use CTkComboBox instead of CTkSpinBox
        self.combo = ctk.CTkComboBox(
            self,
            values=["1", "2", "3", "4", "5", "10"],
            width=60,
            command=self._on_select
        )
        self.combo.set("3")  # Default value
        self.combo.pack(side="left")
    
    def _on_select(self, value: str):
        """Handle selection change."""
        if self.on_change:
            self.on_change(int(value))
    
    def get_value(self) -> int:
        """Get current worker count."""
        return int(self.combo.get())
    
    def set_value(self, value: int):
        """Set worker count."""
        if value in settings.VALID_WORKER_COUNTS:
            self.combo.set(str(value))


def create_main_window(title: str = "Spotify Manager") -> ctk.CTk:
    """Create and configure main application window."""
    window = ctk.CTk()
    window.title(title)
    window.geometry("1200x800")
    window.minsize(900, 600)
    
    return window
