"""
gui_manager.py - Графический интерфейс диспетчера задач для Spotify Automation Manager

Этот модуль предоставляет современный GUI на базе customtkinter для управления
мультиаккаунтной автоматизацией Spotify.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
from datetime import datetime
from typing import Optional, List, Dict
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import schedule
import time

from db_manager import DatabaseManager, Account


# Настройка внешнего вида customtkinter
ctk.set_appearance_mode("dark")  # Темная тема
ctk.set_default_color_theme("blue")  # Синяя цветовая схема


class LogConsole(ctk.CTkTextbox):
    """Виджет текстовой консоли для вывода логов"""
    
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(
            state="disabled",
            font=("Consolas", 10),
            wrap="word"
        )
    
    def log(self, message: str, level: str = "INFO") -> None:
        """
        Добавляет сообщение в лог с временной меткой.
        
        Args:
            message: Текст сообщения
            level: Уровень лога (INFO, WARNING, ERROR, SUCCESS)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.configure(state="normal")
        self.insert("end", log_entry)
        
        # Цветовое кодирование по уровням
        if level == "ERROR":
            self.tag_configure("error", foreground="#ff6b6b")
            self.tag_add("error", "end-2c linestart", "end-1c")
        elif level == "SUCCESS":
            self.tag_configure("success", foreground="#51cf66")
            self.tag_add("success", "end-2c linestart", "end-1c")
        elif level == "WARNING":
            self.tag_configure("warning", foreground="#fcc419")
            self.tag_add("warning", "end-2c linestart", "end-1c")
        
        self.configure(state="disabled")
        self.see("end")  # Автопрокрутка вниз


class AccountTable(ctk.CTkFrame):
    """Таблица аккаунтов с возможностью выбора и запуска"""
    
    def __init__(self, master, db_manager: DatabaseManager, log_console: LogConsole, **kwargs):
        super().__init__(master, **kwargs)
        
        self.db_manager = db_manager
        self.log_console = log_console
        self.accounts_data: List[Account] = []
        self.selected_indices = set()
        
        self._create_table()
        self.refresh_data()
    
    def _create_table(self) -> None:
        """Создает таблицу аккаунтов"""
        # Заголовок таблицы
        columns = ("select", "profile_id", "manager_name", "proxy", "playlist_url", "status")
        
        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            selectmode="extended"
        )
        
        # Настройка заголовков
        self.tree.heading("select", text="✓")
        self.tree.heading("profile_id", text="ID профиля")
        self.tree.heading("manager_name", text="Название")
        self.tree.heading("proxy", text="Прокси")
        self.tree.heading("playlist_url", text="Целевой плейлист")
        self.tree.heading("status", text="Статус")
        
        # Настройка ширины колонок
        self.tree.column("select", width=40, anchor="center")
        self.tree.column("profile_id", width=120, anchor="w")
        self.tree.column("manager_name", width=150, anchor="w")
        self.tree.column("proxy", width=180, anchor="w")
        self.tree.column("playlist_url", width=250, anchor="w")
        self.tree.column("status", width=100, anchor="center")
        
        # Добавляем полосу прокрутки
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Размещаем элементы
        self.tree.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=5)
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Привязка события двойного клика
        self.tree.bind("<Double-1>", self._on_double_click)
    
    def refresh_data(self) -> None:
        """Обновляет данные таблицы из базы данных"""
        # Очищаем текущие данные
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Загружаем аккаунты из БД
        self.accounts_data = self.db_manager.read_all_accounts()
        self.selected_indices.clear()
        
        # Заполняем таблицу
        for idx, account in enumerate(self.accounts_data):
            # Сокращаем URL плейлиста для отображения
            playlist_display = account.playlist_url[:40] + "..." if len(account.playlist_url) > 40 else account.playlist_url
            
            values = (
                "",  # Пустое значение для колонки выбора (будет обновляться)
                account.profile_id,
                account.manager_name,
                account.proxy,
                playlist_display,
                account.status
            )
            
            item_id = self.tree.insert("", "end", values=values)
            
            # Сохраняем связь между item_id и индексом в списке
            self.tree.item(item_id, tags=(str(idx),))
    
    def _on_double_click(self, event) -> None:
        """Обработка двойного клика по строке - запуск аккаунта"""
        selection = self.tree.selection()
        if selection:
            item = selection[0]
            values = self.tree.item(item, "values")
            profile_id = values[1]  # profile_id находится на позиции 1
            self.start_account(profile_id)
    
    def toggle_selection(self, item_id: str) -> None:
        """Переключает состояние выделения строки"""
        values = self.tree.item(item_id, "values")
        current_check = values[0]
        
        if current_check == "✓":
            new_check = ""
            idx = int(self.tree.item(item_id, "tags")[0])
            self.selected_indices.discard(idx)
        else:
            new_check = "✓"
            idx = int(self.tree.item(item_id, "tags")[0])
            self.selected_indices.add(idx)
        
        # Обновляем значения строки
        new_values = list(values)
        new_values[0] = new_check
        self.tree.item(item_id, values=new_values)
    
    def get_selected_accounts(self) -> List[Account]:
        """Возвращает список выбранных аккаунтов"""
        return [self.accounts_data[idx] for idx in self.selected_indices if idx < len(self.accounts_data)]
    
    def start_account(self, profile_id: str) -> None:
        """
        Запускает автоматизацию для конкретного аккаунта.
        
        Args:
            profile_id: ID профиля для запуска
        """
        account = self.db_manager.get_account_by_id(profile_id)
        if not account:
            self.log_console.log(f"Аккаунт {profile_id} не найден", "ERROR")
            return
        
        self.log_console.log(f"Запуск аккаунта: {account.manager_name} ({profile_id})", "INFO")
        
        # Обновляем статус в БД
        self.db_manager.update_account_status(profile_id, "В работе")
        self.refresh_data()
        
        # ЗАГЛУШКА: Здесь будет вызов движка автоматизации
        self._start_automation_logic(account)
    
    def start_selected_accounts(self) -> None:
        """Запускает автоматизацию для всех выбранных аккаунтов"""
        selected = self.get_selected_accounts()
        
        if not selected:
            self.log_console.log("Не выбрано ни одного аккаунта", "WARNING")
            return
        
        self.log_console.log(f"Запуск {len(selected)} выбранных аккаунтов...", "INFO")
        
        for account in selected:
            self.start_account(account.profile_id)
    
    def _start_automation_logic(self, account: Account) -> None:
        """
        Запускает автоматизацию Spotify через spotify_engine.
        
        Args:
            account: Объект аккаунта для автоматизации
        """
        # Импортируем движок автоматизации
        from spotify_engine import run_spotify_task
        
        def automation_thread():
            try:
                # Преобразуем Account в словарь для движка
                account_data = {
                    "id": account.profile_id,
                    "name": account.manager_name,
                    "proxy": account.proxy,
                    "login": account.login,
                    "password": account.password,
                    "playlist_url": account.playlist_url,
                    "start_track": account.start_track,
                    "status": account.status
                }
                
                # Получаем настройки из панели управления
                headless = self.account_table.log_console.master.control_panel.headless_mode if hasattr(self.account_table.log_console, 'master') else False
                
                self.log_console.log(f"[{account.manager_name}] Инициализация браузера (headless={headless})...", "INFO")
                
                # Запускаем движок автоматизации
                success = run_spotify_task(
                    account_data=account_data,
                    headless_mode=headless,
                    log_callback=lambda msg: self.log_console.log(msg.replace("[INFO]", f"[{account.manager_name}]").replace("[SUCCESS]", f"[{account.manager_name}]").replace("[ERROR]", f"[{account.manager_name}]").replace("[WARNING]", f"[{account.manager_name}]"), "INFO")
                )
                
                if success:
                    self.log_console.log(f"[{account.manager_name}] Автоматизация завершена успешно", "SUCCESS")
                    self.db_manager.update_account_status(account.profile_id, "Готово")
                else:
                    self.log_console.log(f"[{account.manager_name}] Автоматизация завершена с ошибками", "ERROR")
                    self.db_manager.update_account_status(account.profile_id, "Ошибка")
                    
                self.refresh_data()
                
            except Exception as e:
                self.log_console.log(f"[{account.manager_name}] Критическая ошибка: {str(e)}", "ERROR")
                self.db_manager.update_account_status(account.profile_id, "Ошибка")
                self.refresh_data()
        
        # Запускаем в отдельном потоке, чтобы не блокировать GUI
        thread = threading.Thread(target=automation_thread, daemon=True)
        thread.start()


class ControlPanel(ctk.CTkFrame):
    """Панель управления с кнопками и настройками"""
    
    def __init__(self, master, account_table: AccountTable, log_console: LogConsole, **kwargs):
        super().__init__(master, **kwargs)
        
        self.account_table = account_table
        self.log_console = log_console
        self.headless_mode = False
        self.thread_limit = 3
        
        # Переменные для многопоточности и планировщика
        self.executor: Optional[ThreadPoolExecutor] = None
        self.scheduler_thread: Optional[threading.Thread] = None
        self.is_running_scheduler = False
        self.scheduled_time: Optional[str] = None
        
        self._create_controls()
    
    def _create_controls(self) -> None:
        """Создает элементы управления"""
        # Кнопка обновления списка
        self.btn_refresh = ctk.CTkButton(
            self,
            text="🔄 Обновить список",
            command=self._on_refresh,
            width=150
        )
        self.btn_refresh.grid(row=0, column=0, padx=10, pady=10)
        
        # Чекбокс скрытого режима
        self.chk_headless = ctk.CTkCheckBox(
            self,
            text="Скрытый режим (Headless)",
            command=self._on_headless_toggle,
            width=200
        )
        self.chk_headless.grid(row=0, column=1, padx=10, pady=10)
        
        # Поле ввода лимита потоков
        lbl_threads = ctk.CTkLabel(self, text="Лимит потоков:")
        lbl_threads.grid(row=0, column=2, padx=(10, 5), pady=10)
        
        self.spin_threads = ctk.CTkSpinBox(
            self,
            from_=1,
            to=20,
            width=60,
            command=self._on_thread_limit_change
        )
        self.spin_threads.set(3)
        self.spin_threads.grid(row=0, column=3, padx=5, pady=10)
        
        # Кнопка запуска всех
        self.btn_start_all = ctk.CTkButton(
            self,
            text="▶ Запустить автоматизацию для всех",
            command=self._on_start_all,
            fg_color="#51cf66",
            hover_color="#40c057",
            width=250
        )
        self.btn_start_all.grid(row=0, column=4, padx=10, pady=10)
        
        # Кнопка планировщика
        self.btn_scheduler = ctk.CTkButton(
            self,
            text="⏰ Планировщик",
            command=self._on_scheduler,
            fg_color="#3b82f6",
            hover_color="#2563eb",
            width=130
        )
        self.btn_scheduler.grid(row=0, column=5, padx=10, pady=10)
        
        # Конфигурация сетки
        self.grid_columnconfigure(5, weight=1)
    
    def _on_refresh(self) -> None:
        """Обработчик кнопки обновления списка"""
        self.log_console.log("Обновление списка аккаунтов из файла...", "INFO")
        self.account_table.refresh_data()
        self.log_console.log(f"Загружено {len(self.account_table.accounts_data)} аккаунтов", "SUCCESS")
    
    def _on_headless_toggle(self) -> None:
        """Обработчик переключения скрытого режима"""
        self.headless_mode = self.chk_headless.get()
        mode_str = "ВКЛ" if self.headless_mode else "ВЫКЛ"
        self.log_console.log(f"Скрытый режим: {mode_str}", "INFO")
    
    def _on_thread_limit_change(self, value: str) -> None:
        """Обработчик изменения лимита потоков"""
        try:
            self.thread_limit = int(value)
            self.log_console.log(f"Лимит потоков установлен: {self.thread_limit}", "INFO")
        except ValueError:
            pass
    
    def _on_start_all(self) -> None:
        """Обработчик кнопки запуска всех аккаунтов с использованием ThreadPoolExecutor"""
        self.log_console.log("Запуск автоматизации для всех аккаунтов...", "INFO")
        
        # Получаем все аккаунты
        all_accounts = self.account_table.accounts_data
        
        if not all_accounts:
            self.log_console.log("Нет аккаунтов для запуска", "WARNING")
            return
        
        # Создаем пул потоков с ограничением по лимиту
        if self.executor and not self.executor._shutdown:
            self.log_console.log("Предыдущие задачи еще выполняются", "WARNING")
            return
        
        self.executor = ThreadPoolExecutor(max_workers=self.thread_limit)
        
        def run_account_task(account: Account) -> Dict:
            """Запускает задачу для одного аккаунта и возвращает результат"""
            from spotify_engine import run_spotify_task
            
            account_data = {
                "id": account.profile_id,
                "name": account.manager_name,
                "proxy": account.proxy,
                "login": account.login,
                "password": account.password,
                "playlist_url": account.playlist_url,
                "start_track": account.start_track,
                "status": account.status
            }
            
            # Обновляем статус перед запуском
            self.account_table.db_manager.update_account_status(account.profile_id, "В работе")
            self.account_table.refresh_data()
            
            success = run_spotify_task(
                account_data=account_data,
                headless_mode=self.headless_mode,
                log_callback=lambda msg, level="INFO": self.log_console.log(
                    msg.replace("[INFO]", f"[{account.manager_name}]").replace(
                        "[SUCCESS]", f"[{account.manager_name}]").replace(
                        "[ERROR]", f"[{account.manager_name}]").replace(
                        "[WARNING]", f"[{account.manager_name}]"), level
                )
            )
            
            # Обновляем статус после завершения
            new_status = "Готово" if success else "Ошибка"
            self.account_table.db_manager.update_account_status(account.profile_id, new_status)
            self.account_table.refresh_data()
            
            return {"account": account.manager_name, "success": success}
        
        # Отправляем все задачи в пул
        futures = [self.executor.submit(run_account_task, acc) for acc in all_accounts]
        
        # Обрабатываем результаты по мере завершения
        def process_results():
            completed = 0
            successful = 0
            for future in as_completed(futures):
                try:
                    result = future.result()
                    completed += 1
                    if result["success"]:
                        successful += 1
                        self.log_console.log(f"[{result['account']}] Задача завершена успешно ({completed}/{len(all_accounts)})", "SUCCESS")
                    else:
                        self.log_console.log(f"[{result['account']}] Задача завершена с ошибкой ({completed}/{len(all_accounts)})", "ERROR")
                except Exception as e:
                    completed += 1
                    self.log_console.log(f"Ошибка выполнения задачи: {e}", "ERROR")
            
            self.log_console.log(f"Все задачи завершены. Успешно: {successful}/{len(all_accounts)}", "SUCCESS")
            self.executor = None
        
        # Запускаем обработку результатов в отдельном потоке
        threading.Thread(target=process_results, daemon=True).start()
    
    def _run_scheduled_task(self) -> None:
        """Выполняет запланированную задачу"""
        self.log_console.log("⏰ Запуск по расписанию...", "INFO")
        self._on_start_all()
    
    def _scheduler_runner(self) -> None:
        """Фоновый поток для выполнения планировщика"""
        while self.is_running_scheduler:
            schedule.run_pending()
            time.sleep(1)
    
    def _on_scheduler(self) -> None:
        """Открывает диалог настройки планировщика"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Планировщик задач")
        dialog.geometry("400x300")
        dialog.resizable(False, False)
        
        lbl_title = ctk.CTkLabel(dialog, text="Настройка расписания", font=("Arial", 16, "bold"))
        lbl_title.pack(pady=20)
        
        lbl_info = ctk.CTkLabel(dialog, text="Выберите интервал запуска:")
        lbl_info.pack(pady=5)
        
        # Выбор типа расписания
        schedule_type = ctk.StringVar(value="interval")
        
        radio_interval = ctk.CTkRadioButton(
            dialog,
            text="Каждые N часов",
            variable=schedule_type,
            value="interval"
        )
        radio_interval.pack(pady=5)
        
        spin_hours = ctk.CTkSpinBox(dialog, from_=1, to=24, width=60)
        spin_hours.set(2)
        spin_hours.pack(pady=5)
        
        radio_daily = ctk.CTkRadioButton(
            dialog,
            text="Ежедневно в указанное время",
            variable=schedule_type,
            value="daily"
        )
        radio_daily.pack(pady=5)
        
        entry_time = ctk.CTkEntry(dialog, placeholder_text="HH:MM (например, 10:00)")
        entry_time.pack(pady=5)
        
        def start_scheduler():
            if self.is_running_scheduler:
                self.log_console.log("Планировщик уже запущен", "WARNING")
                dialog.destroy()
                return
            
            stype = schedule_type.get()
            schedule.clear()
            
            if stype == "interval":
                hours = int(spin_hours.get())
                schedule.every(hours).hours.do(self._run_scheduled_task)
                self.log_console.log(f"Планировщик установлен: каждые {hours} ч.", "SUCCESS")
            else:
                time_str = entry_time.get()
                try:
                    schedule.every().day.at(time_str).do(self._run_scheduled_task)
                    self.log_console.log(f"Планировщик установлен: ежедневно в {time_str}", "SUCCESS")
                except Exception as e:
                    self.log_console.log(f"Неверный формат времени: {e}", "ERROR")
                    dialog.destroy()
                    return
            
            self.is_running_scheduler = True
            self.scheduler_thread = threading.Thread(target=self._scheduler_runner, daemon=True)
            self.scheduler_thread.start()
            
            self.log_console.log("Планировщик запущен", "SUCCESS")
            dialog.destroy()
        
        def stop_scheduler():
            if not self.is_running_scheduler:
                self.log_console.log("Планировщик не запущен", "WARNING")
                return
            
            self.is_running_scheduler = False
            schedule.clear()
            self.log_console.log("Планировщик остановлен", "WARNING")
            dialog.destroy()
        
        btn_start = ctk.CTkButton(dialog, text="Запустить планировщик", command=start_scheduler, fg_color="#51cf66")
        btn_start.pack(pady=10)
        
        btn_stop = ctk.CTkButton(dialog, text="Остановить планировщик", command=stop_scheduler, fg_color="#ff6b6b")
        btn_stop.pack(pady=5)
        
        btn_cancel = ctk.CTkButton(dialog, text="Отмена", command=dialog.destroy, fg_color="transparent", border_width=1)
        btn_cancel.pack(pady=10)


class SpotifyAutomationGUI(ctk.CTk):
    """Главное окно приложения"""
    
    def __init__(self):
        super().__init__()
        
        self.title("Spotify Automation Manager - Диспетчер задач")
        self.geometry("1200x700")
        self.minsize(1000, 600)
        
        # Инициализация менеджера базы данных
        self.db_manager = DatabaseManager()
        
        self._create_layout()
    
    def _create_layout(self) -> None:
        """Создает основную компоновку интерфейса"""
        # Настройка сетки главного окна
        self.grid_rowconfigure(0, weight=0)  # Панель управления
        self.grid_rowconfigure(1, weight=1)  # Таблица аккаунтов
        self.grid_rowconfigure(2, weight=0)  # Консоль логов
        self.grid_columnconfigure(0, weight=1)
        
        # 1. Панель управления
        self.control_panel = ControlPanel(
            self,
            account_table=None,  # Будет установлено позже
            log_console=None  # Будет установлено позже
        )
        self.control_panel.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        # 2. Таблица аккаунтов
        self.account_table = AccountTable(
            self,
            db_manager=self.db_manager,
            log_console=None  # Будет установлено позже
        )
        self.account_table.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        # 3. Консоль логов
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        log_frame.grid_columnconfigure(0, weight=1)
        
        lbl_logs = ctk.CTkLabel(log_frame, text="Логи приложения:", anchor="w")
        lbl_logs.grid(row=0, column=0, sticky="w", padx=5, pady=(5, 0))
        
        self.log_console = LogConsole(log_frame, height=100)
        self.log_console.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        
        # Связываем компоненты между собой
        self.control_panel.account_table = self.account_table
        self.control_panel.log_console = self.log_console
        self.account_table.log_console = self.log_console
        
        # Приветственное сообщение
        self.log_console.log("Spotify Automation Manager запущен", "SUCCESS")
        self.log_console.log(f"База данных: {self.db_manager.db_path.absolute()}", "INFO")
        self.log_console.log(f"Директория профилей: {self.db_manager.profiles_dir.absolute()}", "INFO")
        self.log_console.log(f"Загружено аккаунтов: {len(self.account_table.accounts_data)}", "INFO")


def main():
    """Точка входа приложения"""
    app = SpotifyAutomationGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
