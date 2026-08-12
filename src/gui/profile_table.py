"""
Profile table component for displaying and managing profiles.
"""

import customtkinter as ctk
from tkinter import ttk
from typing import List, Dict, Optional, Callable
from datetime import datetime

from src.database.database import DatabaseManager
from src.database.repositories import ProfileRepository
from src.database.models import ProfileStatus


class ProfileTable(ctk.CTkFrame):
    """Table displaying all profiles with actions."""
    
    def __init__(self, master, on_action: Optional[Callable[[str, int], None]] = None, **kwargs):
        super().__init__(master, **kwargs)
        
        self.on_action = on_action
        self.profiles_data: List[Dict] = []
        
        self._create_table()
    
    def _create_table(self):
        """Create the profile table."""
        # Title row
        title = ctk.CTkLabel(
            self,
            text="Profiles",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title.grid(row=0, column=0, sticky="w", padx=10, pady=10)
        
        # Add profile button
        add_btn = ctk.CTkButton(
            self,
            text="+ New Profile",
            command=self._on_add_profile,
            width=120
        )
        add_btn.grid(row=0, column=1, sticky="e", padx=10, pady=10)
        
        # Table frame
        table_frame = ctk.CTkFrame(self)
        table_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        
        # Treeview with scrollbars
        columns = ("status", "name", "country", "spotify", "proxy", "browser", "task", "activity")
        
        style = ttk.Style()
        style.configure("Treeview", rowheight=30)
        style.configure("Treeview.Heading", font=("", 10, "bold"))
        
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse"
        )
        
        # Configure headings
        headers = {
            "status": "Status",
            "name": "Profile",
            "country": "Country",
            "spotify": "Spotify",
            "proxy": "Proxy",
            "browser": "Browser",
            "task": "Current Task",
            "activity": "Last Activity"
        }
        
        widths = {
            "status": 80,
            "name": 150,
            "country": 70,
            "spotify": 100,
            "proxy": 80,
            "browser": 80,
            "task": 120,
            "activity": 150
        }
        
        for col in columns:
            self.tree.heading(col, text=headers.get(col, col))
            self.tree.column(col, width=widths.get(col, 100), anchor="w")
        
        # Scrollbars
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        
        # Layout
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        
        # Action buttons
        action_frame = ctk.CTkFrame(self)
        action_frame.grid(row=2, column=0, columnspan=2, sticky="e", padx=10, pady=10)
        
        self.action_buttons = {
            "open": ctk.CTkButton(action_frame, text="Open", command=self._on_open, width=80),
            "start": ctk.CTkButton(action_frame, text="Start Task", command=self._on_start, width=100, fg_color="#51cf66"),
            "stop": ctk.CTkButton(action_frame, text="Stop", command=self._on_stop, width=80, fg_color="#ff6b6b"),
            "edit": ctk.CTkButton(action_frame, text="Edit", command=self._on_edit, width=80),
            "test": ctk.CTkButton(action_frame, text="Test Connection", command=self._on_test, width=120)
        }
        
        btn_col = 0
        for btn in self.action_buttons.values():
            btn.grid(row=0, column=btn_col, padx=5)
            btn_col += 1
        
        # Double-click to open
        self.tree.bind("<Double-1>", lambda e: self._on_open())
        
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)
    
    def refresh_data(self):
        """Refresh table data from database."""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Load profiles
        self.profiles_data = []
        
        try:
            with DatabaseManager() as session:
                repo = ProfileRepository(session)
                profiles = repo.get_all()
                
                for profile in profiles:
                    data = {
                        "id": profile.id,
                        "status": profile.status.value if profile.status else "inactive",
                        "name": profile.name,
                        "country": profile.country or "US",
                        "spotify": profile.spotify_user_id or "-",
                        "proxy": "✓" if profile.proxies else "-",
                        "browser": "✓" if profile.browser_profile_path else "-",
                        "task": self._get_current_task(profile.id),
                        "activity": self._format_activity(profile.updated_at)
                    }
                    self.profiles_data.append(data)
                    
                    self.tree.insert("", "end", values=(
                        data["status"],
                        data["name"],
                        data["country"],
                        data["spotify"],
                        data["proxy"],
                        data["browser"],
                        data["task"],
                        data["activity"]
                    ))
        except Exception as e:
            pass  # Handle gracefully - app works without DB
    
    def _get_current_task(self, profile_id: int) -> str:
        """Get current task for profile (placeholder)."""
        return "-"
    
    def _format_activity(self, dt) -> str:
        """Format datetime for display."""
        if not dt:
            return "Never"
        try:
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "Unknown"
    
    def _get_selected_profile_id(self) -> Optional[int]:
        """Get ID of selected profile."""
        selection = self.tree.selection()
        if not selection:
            return None
        
        item = self.tree.item(selection[0])
        name = item["values"][1]  # name column
        
        for p in self.profiles_data:
            if p["name"] == name:
                return p["id"]
        
        return None
    
    def _on_add_profile(self):
        """Handle add profile action."""
        if self.on_action:
            self.on_action("add_profile", 0)
    
    def _on_open(self):
        """Handle open action."""
        profile_id = self._get_selected_profile_id()
        if profile_id and self.on_action:
            self.on_action("open_profile", profile_id)
    
    def _on_start(self):
        """Handle start task action."""
        profile_id = self._get_selected_profile_id()
        if profile_id and self.on_action:
            self.on_action("start_task", profile_id)
    
    def _on_stop(self):
        """Handle stop action."""
        profile_id = self._get_selected_profile_id()
        if profile_id and self.on_action:
            self.on_action("stop_task", profile_id)
    
    def _on_edit(self):
        """Handle edit action."""
        profile_id = self._get_selected_profile_id()
        if profile_id and self.on_action:
            self.on_action("edit_profile", profile_id)
    
    def _on_test(self):
        """Handle test connection action."""
        profile_id = self._get_selected_profile_id()
        if profile_id and self.on_action:
            self.on_action("test_connection", profile_id)
