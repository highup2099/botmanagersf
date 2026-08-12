# AUDIT REPORT - botmanagersf (Spotify Manager)

## Date: Current

---

## 1. CURRENT ARCHITECTURE

The current project structure is flat and monolithic:

```
botmanagersf/
├── gui_manager.py       # Main GUI + control logic (620 lines)
├── db_manager.py        # Excel-based "database" manager (305 lines)
├── spotify_engine.py    # Playwright browser automation (407 lines)
├── accounts.xlsx        # CSV/XLSX as database with credentials
├── README.md            # Minimal documentation
├── .gitignore           # Partial ignore rules
└── profiles/
    └── test_001/        # Browser profile storage
```

### Architecture Problems:
- **No separation of concerns**: GUI, database, and browser automation are tightly coupled
- **No task queue system**: Tasks run synchronously or with basic threading
- **No proper logging system**: Logs go to GUI console only
- **No configuration management**: Hard-coded paths and settings
- **No Spotify API abstraction**: Direct browser automation only

---

## 2. DISCOVERED FILES

| File | Purpose | Lines | Issues |
|------|---------|-------|--------|
| gui_manager.py | CustomTkinter GUI | 620 | Uses CTkSpinBox (deprecated), blocks GUI thread |
| db_manager.py | Excel DB manager | 305 | Stores passwords in plain text XLSX |
| spotify_engine.py | Playwright automation | 407 | Contains anti-detect features, hardcoded selectors |
| accounts.xlsx | Credential storage | Binary | Contains passwords, proxy credentials in plain text |
| README.md | Documentation | 4 | Empty/repeated content |
| .gitignore | Git ignore rules | 33 | Missing critical entries (.venv, *.db) |
| profiles/test_001/ | Browser profile | Dir | Exists but unmanaged |

---

## 3. DEPENDENCY PROBLEMS

### Currently Used (in code):
- `customtkinter` - **NOT INSTALLED** in environment
- `openpyxl` - Installed (3.1.5) ✓
- `playwright` - Installed (1.44.0) ✓
- `schedule` - Imported but **NOT INSTALLED**
- `tkinter` - Standard library ✓

### Missing Dependencies:
```
customtkinter  # Required for GUI
schedule       # Used for scheduler feature
```

### Unused/Questionable Dependencies in Environment:
Many packages installed in environment that are not used by this project (browsergym-*, datasets, etc.)

### Recommendation:
Create clean `requirements.txt`:
```
customtkinter>=5.2.0
openpyxl>=3.1.0
playwright>=1.40.0
sqlalchemy>=2.0.0
python-dotenv>=1.0.0
cryptography>=42.0.0
```

---

## 4. RUNTIME ERRORS

### Critical Error (GUI Crash):
```python
# gui_manager.py line 315
self.spin_threads = ctk.CTkSpinBox(  # AttributeError!
    self,
    from_=1,
    to=20,
    ...
)
```

**Error**: `AttributeError: module 'customtkinter' has no attribute 'CTkSpinBox'`

**Cause**: CTkSpinBox was removed from customtkinter. Must use CTkComboBox or custom implementation.

### Other Potential Errors:
1. Import error if customtkinter not installed
2. Import error for `schedule` module
3. Line 242 in gui_manager.py references `self.account_table.log_console.master.control_panel` - fragile coupling

---

## 5. SECURITY PROBLEMS

### CRITICAL - Credentials Stored in Plain Text:

**accounts.xlsx contains:**
- Spotify usernames (emails)
- Spotify passwords
- Proxy credentials (username:password)

Example row:
```
spotify_001 | Account_DE | 192.168.1.1:8080:user1:pass1 | test1@example.com | password123 | ...
```

### Security Violations:
1. ❌ Passwords stored in XLSX file
2. ❌ Proxy passwords visible in plain text
3. ❌ No encryption for sensitive data
4. ❌ `.gitignore` allows xlsx files (currently excluded but should never be tracked)
5. ❌ OAuth not implemented - using username/password login
6. ❌ No secure credential storage

### Required Fixes:
1. Migrate to SQLite with encrypted fields
2. Implement Spotify OAuth flow
3. Never store passwords - use tokens only
4. Use environment variables or OS keychain for secrets
5. Create `.env.example` with placeholders

---

## 6. ARCHITECTURE PROBLEMS

### 6.1 Tight Coupling

**gui_manager.py couples:**
- Database access (direct calls to DatabaseManager)
- Browser automation (imports spotify_engine directly)
- Threading logic (ThreadPoolExecutor in GUI)
- UI state management

### 6.2 Blocking Operations

```python
# gui_manager.py - Line 427
time.sleep(listen_duration)  # Blocks thread
```

While this runs in a worker thread, the pattern encourages blocking code.

### 6.3 No Error Boundaries

- Exceptions caught but often swallowed
- No structured error handling
- No retry logic

### 6.4 No Task System

- Tasks are implicit (run_spotify_task)
- No task status tracking (queued/running/completed/failed)
- No task persistence
- No priority system

### 6.5 Database Anti-Patterns

- Using XLSX as database
- No transactions
- Race conditions possible with concurrent writes
- No schema validation

---

## 7. INCORRECT CUSTOMTKINTER USAGE

| Issue | Location | Problem |
|-------|----------|---------|
| CTkSpinBox | gui_manager.py:315 | Removed from library |
| Direct treeview styling | gui_manager.py:85-117 | Mixing ttk with ctk |
| Fragile parent references | gui_manager.py:242 | `master.control_panel` chaining |

---

## 8. SYNCHRONOUS/BLOCKING CODE IN GUI

### Blocking Patterns Found:

1. **Direct database operations during GUI events:**
   ```python
   def _on_refresh(self):
       self.account_table.refresh_data()  # Reads XLSX synchronously
   ```

2. **Thread pool without proper async:**
   ```python
   self.executor = ThreadPoolExecutor(max_workers=self.thread_limit)
   # Uses time.sleep internally
   ```

3. **Schedule library usage (blocks):**
   ```python
   import schedule
   # schedule.run_pending() must be called in loop
   ```

---

## 9. INCORRECT SPOTIFY API ASSUMPTIONS

### Current Implementation Issues:

1. **Assumes Recommendations API works via browser:**
   - Code tries to find "Go to song radio" menu items
   - These selectors change frequently
   - Not using official Recommendations API

2. **Hardcoded selectors:**
   ```python
   selectors = [
       'button[data-testid="track-context-menu"]',
       'div[role="menuitem"]:has-text("Add to playlist")'
   ]
   ```
   These will break when Spotify updates their UI.

3. **No API rate limiting:**
   - Browser automation doesn't respect API limits
   - Could trigger account restrictions

4. **Assumes playlist modification via UI:**
   - Complex multi-step UI interactions
   - Brittle and slow

### Recommended Approach:
- Use official Spotify Web API for data operations
- Use browser only for interactive playback
- Implement proper OAuth token refresh

---

## 10. COUPLING ANALYSIS

### Current Coupling Map:

```
gui_manager.py
    ├── imports → db_manager.py (DatabaseManager, Account)
    ├── imports → spotify_engine.py (run_spotify_task)
    ├── imports → schedule (scheduler)
    ├── imports → threading (ThreadPoolExecutor)
    └── direct DOM manipulation assumptions

db_manager.py
    └── depends on openpyxl (Excel format)

spotify_engine.py
    ├── depends on playwright
    └── assumes specific Spotify DOM structure
```

### Required Decoupling:

```
GUI Layer (src/gui/)
    ↓ (events/callbacks)
Task Layer (src/tasks/)
    ↓ (commands)
Service Layer (src/spotify/, src/browser/)
    ↓ (data access)
Repository Layer (src/database/)
```

---

## 11. RECOMMENDED REFACTORING

### Phase 1: Immediate Fixes
1. Fix CTkSpinBox → CTkComboBox
2. Install missing dependencies
3. Make GUI launch successfully

### Phase 2: Database Migration
1. Create SQLite schema with SQLAlchemy
2. Migrate data from XLSX to SQLite
3. Remove password fields (use OAuth)
4. Add encryption for sensitive fields

### Phase 3: Architecture Refactor
1. Create `src/` directory structure
2. Move GUI code to `src/gui/`
3. Create database models in `src/database/`
4. Create Spotify service in `src/spotify/`
5. Create browser worker in `src/browser/`
6. Create task system in `src/tasks/`

### Phase 4: Security
1. Implement OAuth flow
2. Remove password storage
3. Add environment variable support
4. Create `.env.example`

### Phase 5: Testing
1. Add unit tests for database
2. Add integration tests for tasks
3. Add GUI smoke tests

---

## 12. MIGRATION PLAN

### Step-by-Step:

```
Week 1:
□ Day 1: Audit complete, create AUDIT.md
□ Day 2: Fix GUI crash (CTkSpinBox)
□ Day 3: Create requirements.txt
□ Day 4: Create SQLite database schema
□ Day 5: Create .env.example and update .gitignore

Week 2:
□ Day 1: Refactor database layer (SQLAlchemy)
□ Day 2: Create Profile model and repository
□ Day 3: Create Task model and repository
□ Day 4: Create task queue system
□ Day 5: Create worker pool

Week 3:
□ Day 1: Refactor GUI to use new architecture
□ Day 2: Create Spotify OAuth service
□ Day 3: Create browser worker abstraction
□ Day 4: Add structured logging
□ Day 5: Write tests

Week 4:
□ Day 1: Update README with macOS instructions
□ Day 2: Test full application flow
□ Day 3: Fix remaining issues
□ Day 4: Documentation
□ Day 5: Final verification
```

---

## 13. FILES TO CREATE

```
src/
├── __init__.py
├── gui/
│   ├── __init__.py
│   ├── app_window.py
│   ├── profile_table.py
│   ├── task_panel.py
│   └── log_panel.py
├── database/
│   ├── __init__.py
│   ├── database.py
│   ├── models.py
│   └── repositories.py
├── spotify/
│   ├── __init__.py
│   ├── auth.py
│   ├── client.py
│   └── service.py
├── browser/
│   ├── __init__.py
│   ├── profile_manager.py
│   └── browser_worker.py
├── tasks/
│   ├── __init__.py
│   ├── task_manager.py
│   ├── task_queue.py
│   └── worker_pool.py
├── logging/
│   ├── __init__.py
│   └── app_logger.py
└── config/
    ├── __init__.py
    └── settings.py

data/                    # SQLite database storage
logs/                    # Application logs
.env.example             # Environment template
requirements.txt         # Clean dependencies
app.py                   # New entry point
```

---

## 14. FILES TO REMOVE/MODIFY

### Remove:
- `accounts.xlsx` (after migration)
- Old flat Python files (after refactor)

### Modify:
- `.gitignore` - add .venv/, *.db, profiles/*, logs/*
- `README.md` - complete documentation

---

## 15. SUCCESS CRITERIA

After refactoring:
- [ ] GUI launches without errors
- [ ] No CTkSpinBox usage
- [ ] SQLite database working
- [ ] No passwords in source/code/storage
- [ ] OAuth authentication implemented
- [ ] Task queue functional
- [ ] Tests pass
- [ ] macOS compatible
- [ ] Clean architecture with separation of concerns

---

*End of Audit Report*
