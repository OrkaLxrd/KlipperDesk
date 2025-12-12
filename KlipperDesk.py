import sys
import json
import asyncio
import threading
import time
import os
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Callable

from PyQt5 import QtWidgets, QtCore, QtGui

end = False
updates_paused = False
# Defaults
CONFIG_FILE = "KDconfig.json"

# Default subscribe payload for Moonraker
DEFAULT_SUBSCRIBE_PAYLOAD = {
    "jsonrpc": "2.0",
    "method": "printer.objects.subscribe",
    "params": {
        "objects": {
            "extruder": ["temperature", "target"],
            "heater_bed": ["temperature", "target"],
            "print_stats": ["state", "filename", "print_duration", "total_duration"],
            "display_status": ["progress", "message"],
            "virtual_sdcard": ["progress", "file_position", "file_size"],
        }
    },
    "id": 42
}


# ---------------------------
# Configuration Management
# ---------------------------
class Config:
    def __init__(self, filename=CONFIG_FILE):
        self.filename = filename
        self.default_config = {
            "printers": [
                {"name": "Printer 1", "ip": "", "enabled": False},
                {"name": "Printer 2", "ip": "", "enabled": False},
                {"name": "Printer 3", "ip": "", "enabled": False},
                {"name": "Printer 4", "ip": "", "enabled": False},
                {"name": "Printer 5", "ip": "", "enabled": False},
                {"name": "Printer 6", "ip": "", "enabled": False},
                {"name": "Printer 7", "ip": "", "enabled": False},
                {"name": "Printer 8", "ip": "", "enabled": False},
                {"name": "Printer 9", "ip": "", "enabled": False},
                {"name": "Printer 10", "ip": "", "enabled": False}
            ],
            "multiple_widgets": True,
            "widget_opacity": 0.88,
            "widget_width": 360,
            "widget_height": 150,
            "first_run": True
        }
        self.config = self.load_config()
    
    def load_config(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    for key, value in self.default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
            except Exception as e:
                print(f"Error loading config: {e}")
                return self.default_config.copy()
        return self.default_config.copy()
    
    def save_config(self):
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def get_enabled_printers(self) -> List[Dict]:
        return [p for p in self.config.get("printers", []) if p.get("enabled", False)]
    
    def update_printer(self, index: int, name: str, ip: str, enabled: bool):
        printers = self.config.get("printers", [])
        if index < len(printers):
            printers[index]["name"] = name
            printers[index]["ip"] = ip
            printers[index]["enabled"] = enabled
    
    def set_widget_size(self, width: int, height: int):
        self.config["widget_width"] = width
        self.config["widget_height"] = height
    
    def set_widget_opacity(self, opacity: float):
        self.config["widget_opacity"] = opacity
    
    def set_multiple_widgets(self, enabled: bool):
        self.config["multiple_widgets"] = enabled
    
    def mark_first_run_complete(self):
        self.config["first_run"] = False


# ---------------------------
# Settings Dialog
# ---------------------------
class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Настройки KlipperDesk")
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowCloseButtonHint)
        self.setFixedSize(500, 650)
        self.setup_ui()
        self.load_settings()
    
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Printer list
        printer_group = QtWidgets.QGroupBox("Принтеры")
        printer_layout = QtWidgets.QVBoxLayout()
        
        self.printer_widgets = []
        for i in range(10):
            widget = self.create_printer_widget(i)
            printer_layout.addWidget(widget)
            self.printer_widgets.append(widget)
        
        printer_group.setLayout(printer_layout)
        layout.addWidget(printer_group)
        
        
        # Widget settings
        settings_group = QtWidgets.QGroupBox("Настройки виджета")
        settings_layout = QtWidgets.QVBoxLayout()
        
        # Opacity
        opacity_layout = QtWidgets.QHBoxLayout()
        opacity_layout.addWidget(QtWidgets.QLabel("Прозрачность:"))
        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity_slider.setRange(20, 100)
        opacity_layout.addWidget(self.opacity_slider)
        self.opacity_label = QtWidgets.QLabel("88%")
        opacity_layout.addWidget(self.opacity_label)
        settings_layout.addLayout(opacity_layout)
        
        # Size
        size_layout = QtWidgets.QHBoxLayout()
        size_layout.addWidget(QtWidgets.QLabel("Ширина:"))
        self.width_spin = QtWidgets.QSpinBox()
        self.width_spin.setRange(200, 800)
        self.width_spin.setSingleStep(10)
        size_layout.addWidget(self.width_spin)
        
        size_layout.addSpacing(20)
        size_layout.addWidget(QtWidgets.QLabel("Высота:"))
        self.height_spin = QtWidgets.QSpinBox()
        self.height_spin.setRange(120, 600)
        self.height_spin.setSingleStep(10)
        size_layout.addWidget(self.height_spin)
        settings_layout.addLayout(size_layout)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        save_button = QtWidgets.QPushButton("Сохранить и применить")
        save_button.clicked.connect(self.save_settings)
        button_layout.addWidget(save_button)
        
        cancel_button = QtWidgets.QPushButton("Отмена")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Connect signals
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%")
        )
    
    def create_printer_widget(self, index: int) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Checkbox for enabled
        enabled_check = QtWidgets.QCheckBox()
        enabled_check.setObjectName(f"enabled_{index}")
        layout.addWidget(enabled_check)
        
        # Printer name
        name_label = QtWidgets.QLabel(f"Принтер {index + 1}:")
        layout.addWidget(name_label)
        
        # Name edit
        name_edit = QtWidgets.QLineEdit()
        name_edit.setPlaceholderText(f"Название принтера {index + 1}")
        name_edit.setMinimumWidth(120)
        name_edit.setObjectName(f"name_{index}")
        layout.addWidget(name_edit)
        
        # IP edit
        ip_edit = QtWidgets.QLineEdit()
        ip_edit.setPlaceholderText("192.168.x.x")
        ip_edit.setMinimumWidth(100)
        ip_edit.setObjectName(f"ip_{index}")
        layout.addWidget(ip_edit)
        
        widget.setLayout(layout)
        return widget
    
    def on_mode_changed(self):
        """Enable/disable height setting based on mode"""
        single_mode = self.single_widget_radio.isChecked()
        self.height_spin.setEnabled(not single_mode)
    
    def get_widget_value(self, index: int, field: str):
        """Get value from printer widget"""
        widget = self.printer_widgets[index]
        if field == "enabled":
            checkbox = widget.findChild(QtWidgets.QCheckBox, f"enabled_{index}")
            return checkbox.isChecked() if checkbox else False
        elif field == "name":
            line_edit = widget.findChild(QtWidgets.QLineEdit, f"name_{index}")
            return line_edit.text().strip() if line_edit else ""
        elif field == "ip":
            line_edit = widget.findChild(QtWidgets.QLineEdit, f"ip_{index}")
            return line_edit.text().strip() if line_edit else ""
        return None
    
    def load_settings(self):
        printers = self.config.config.get("printers", [])
        
        for i in range(min(10, len(printers))):
            printer = printers[i]
            
            # Set enabled checkbox
            enabled_check = self.printer_widgets[i].findChild(QtWidgets.QCheckBox, f"enabled_{i}")
            if enabled_check:
                enabled_check.setChecked(printer.get("enabled", False))
            
            # Set name
            name_edit = self.printer_widgets[i].findChild(QtWidgets.QLineEdit, f"name_{i}")
            if name_edit:
                name_edit.setText(printer.get("name", ""))
            
            # Set IP
            ip_edit = self.printer_widgets[i].findChild(QtWidgets.QLineEdit, f"ip_{i}")
            if ip_edit:
                ip_edit.setText(printer.get("ip", ""))
        
        # Set widget mode
        multiple_widgets = self.config.config.get("multiple_widgets", False)
        
        # Set opacity and size
        opacity = self.config.config.get("widget_opacity", 0.88)
        self.opacity_slider.setValue(int(opacity * 100))
        
        width = self.config.config.get("widget_width", 360)
        height = self.config.config.get("widget_height", 150)
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)
        
    
    def save_settings(self):
        # Update printers
        printers = []
        any_enabled = False  # Флаг для проверки хотя бы одной галочки
        ip_enabled = False
        for i in range(10):
            enabled = self.get_widget_value(i, "enabled")
            name = self.get_widget_value(i, "name")
            ip = self.get_widget_value(i, "ip")
            
            if enabled:
                any_enabled = True  # нашёл хотя бы одну включённую галочку
            if ip:
                ip_enabled = True

            printers.append({
                "name": name or f"Printer {i + 1}",
                "ip": ip,
                "enabled": enabled
            })
        
        # Проверка: если ни одна галочка не включена
        if not any_enabled:
            QtWidgets.QMessageBox.warning(
                self, 
                "Ошибка", 
                "Нужно включить хотя бы один принтер!"
            )
            return  # Прерываем сохранение, диалог остаётся открытым
        if not ip_enabled:
            QtWidgets.QMessageBox.warning(
                self, 
                "Ошибка", 
                "Введите ip адрес!"
            )
            return  # Прерываем сохранение, диалог остаётся открытым
    
        # Сохраняем конфиг
        self.config.config["printers"] = printers
        self.config.config["multiple_widgets"] = True
        self.config.config["widget_opacity"] = self.opacity_slider.value() / 100.0
        self.config.config["widget_width"] = self.width_spin.value()
        self.config.config["widget_height"] = self.height_spin.value()
        
        if self.config.save_config():
            self.accept()  # Закрываем диалог только при успешном сохранении
        else:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Не удалось сохранить настройки!")
        # Не закрываем диалог при ошибке сохранения


# ---------------------------
# WebSocket Client Manager
# ---------------------------
class WebSocketManager(QtCore.QObject):
    """Manages WebSocket connections in separate threads"""
    data_received = QtCore.pyqtSignal(dict)  # Signal emitted when data is received
    
    def __init__(self):
        super().__init__()
        self.ws_threads = {}
        self.stop_events = {}
    
    def start_printer(self, printer_info: Dict):
        """Start WebSocket connection for a printer"""
        import websockets
        
        ip = printer_info.get("ip", "")
        if not ip:
            return
        
        ws_url = f"ws://{ip}/websocket"
        printer_name = printer_info.get("name", "Unknown")
        
        # Create stop event for this printer
        stop_event = threading.Event()
        self.stop_events[ip] = stop_event
        
        # Create and start thread
        thread = threading.Thread(
            target=self._ws_thread_func,
            args=(ws_url, printer_name, ip, stop_event),
            daemon=True
        )
        self.ws_threads[ip] = thread
        thread.start()
        print(f"[WebSocketManager] Started connection for {printer_name} ({ip})")
    
    def _ws_thread_func(self, ws_url: str, printer_name: str, printer_ip: str, stop_event: threading.Event):
        """WebSocket thread function"""
        import websockets
        
        async def consume():
            backoff = 1
            if end:
                loop.close()
            while not stop_event.is_set():
                try:
                    if end:
                        break
                    async with websockets.connect(ws_url) as ws:
                        print(f"[{printer_name}] WebSocket подключен к {ws_url}")
                        await ws.send(json.dumps(DEFAULT_SUBSCRIBE_PAYLOAD))
                        backoff = 1
                        
                        async for raw in ws:
                            if stop_event.is_set():
                                break
                            if end:
                                break
                            try:
                                data = json.loads(raw)
                                # Emit signal with data
                                self.data_received.emit({
                                    "type": "ws_message",
                                    "raw": data,
                                    "printer_name": printer_name,
                                    "printer_ip": printer_ip,
                                    "ts": time.time()
                                })
                            except Exception:
                                continue
                                
                except Exception as e:
                    print(f"[{printer_name}] Ошибка подключения: {e}; повтор через {backoff}с")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 20)
        
        # Run event loop in thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(consume())
        finally:
            loop.close()
    
    def stop_printer(self, ip: str):
        """Stop WebSocket connection for a printer"""
        if ip in self.stop_events:
            self.stop_events[ip].set()
            if ip in self.ws_threads:
                self.ws_threads[ip].join(timeout=2)
                del self.ws_threads[ip]
            del self.stop_events[ip]
    
    def stop_all(self):
        """Stop all WebSocket connections"""
        for ip in list(self.stop_events.keys()):
            self.stop_printer(ip)


# ---------------------------
# Thumbnail Loader
# ---------------------------
class ThumbnailLoader:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.cache = {}
        
    def fetch_thumbnail(self, ip: str, filename: str) -> Optional[QtGui.QPixmap]:
        """Fetch thumbnail for given filename from printer IP"""
        if not ip or not filename:
            return None
        
        cache_key = f"{ip}:{filename}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # First, get file metadata
            metadata_url = f"http://{ip}/server/files/metadata?filename={urllib.parse.quote(filename)}"
            with urllib.request.urlopen(metadata_url, timeout=5) as response:
                metadata = json.loads(response.read())
                
            thumbnails = metadata.get('result', {}).get('thumbnails', [])
            if not thumbnails:
                return None
                
            # Get the largest thumbnail
            thumbnail = sorted(thumbnails, key=lambda x: x.get('width', 0) * x.get('height', 0))[-1]
            relative_path = thumbnail.get('relative_path')
            
            if relative_path:
                # Download thumbnail image
                thumb_url = f"http://{ip}/server/files/gcodes/{urllib.parse.quote(relative_path)}"
                with urllib.request.urlopen(thumb_url, timeout=5) as response:
                    img_data = response.read()
                
                # Convert to QPixmap
                pixmap = QtGui.QPixmap()
                pixmap.loadFromData(img_data)
                self.cache[cache_key] = pixmap
                return pixmap
                
        except Exception as e:
            print(f"[Thumbnail] Ошибка загрузки превью: {e}")
            return None


# ---------------------------
# Printer Data Container
# ---------------------------
class PrinterData(QtCore.QObject):
    """Thread-safe printer data container with signals"""
    data_updated = QtCore.pyqtSignal(object)  # Signal emitted when data changes
    
    def __init__(self, name: str, ip: str):
        super().__init__()
        self.name = name
        self.ip = ip
        self._progress = 0.0
        self._filename = ""
        self._hotend_temp = (0.0, 0.0)  # actual, target
        self._bed_temp = (0.0, 0.0)
        self._status = "idle"
        self.thumbnail = None
        self.last_thumbnail_filename = ""
        self.progress_history = []
        self.last_update = time.time()
    
    @property
    def progress(self):
        return self._progress
    
    @progress.setter
    def progress(self, value):
        self._progress = value
        self.data_updated.emit(self)
    
    @property
    def filename(self):
        return self._filename
    
    @filename.setter
    def filename(self, value):
        self._filename = value
        self.data_updated.emit(self)
    
    @property
    def hotend_temp(self):
        return self._hotend_temp
    
    @hotend_temp.setter
    def hotend_temp(self, value):
        self._hotend_temp = value
        self.data_updated.emit(self)
    
    @property
    def bed_temp(self):
        return self._bed_temp
    
    @bed_temp.setter
    def bed_temp(self, value):
        self._bed_temp = value
        self.data_updated.emit(self)
    
    @property
    def status(self):
        return self._status
    
    @status.setter
    def status(self, value):
        self._status = value
        self.data_updated.emit(self)
    
    def update_from_parsed(self, parsed: Dict):
        """Update data from parsed message"""
        updated = False
        
        if 'progress' in parsed:
            val = int(round(float(parsed['progress'])))
            val = max(0, min(100, val))
            
            # Filter progress jumps
            if self.progress_history:
                last_val = self.progress_history[-1]
                if abs(val - last_val) > 10 and abs(val - last_val) < 90:
                    if len(self.progress_history) >= 3:
                        avg_val = sum(self.progress_history[-3:]) / 3
                        val = int((val + avg_val * 2) / 3)
            
            self.progress = val
            self.progress_history.append(val)
            if len(self.progress_history) > 5:
                self.progress_history.pop(0)
            updated = True
        
        if 'filename' in parsed:
            self.filename = parsed['filename'] or ""
            updated = True
        
        if 'hotend' in parsed:
            h = parsed['hotend']
            self.hotend_temp = (
                float(h.get('actual')) if h.get('actual') is not None else None,
                float(h.get('target')) if h.get('target') is not None else None
            )
            updated = True
        
        if 'bed' in parsed:
            b = parsed['bed']
            self.bed_temp = (
                float(b.get('actual')) if b.get('actual') is not None else None,
                float(b.get('target')) if b.get('target') is not None else None
            )
            updated = True
        
        if 'status' in parsed:
            self.status = parsed['status']
            updated = True
        
        if updated:
            self.last_update = time.time()


# ---------------------------
# Message Parser
# ---------------------------
def parse_moonraker_message(raw: Dict) -> Optional[Dict]:
    try:
        if not isinstance(raw, dict):
            return None
        
        method = raw.get('method')
        if method == 'notify_status_update':
            params = raw.get('params', [])
            if params and isinstance(params, list) and len(params) > 0:
                data = params[0]
            else:
                return None
        elif 'result' in raw and raw.get('result', {}).get('status'):
            data = raw['result']['status']
        else:
            return None
        
        if not data or not isinstance(data, dict):
            return None
        
        result = {}
        
        # Hotend temperature
        if 'extruder' in data and isinstance(data['extruder'], dict):
            extruder = data['extruder']
            if 'temperature' in extruder:
                temp = extruder['temperature']
                result['hotend'] = {
                    "actual": float(temp) if isinstance(temp, (int, float)) else None,
                    "target": float(extruder.get('target')) if extruder.get('target') is not None else None
                }
        
        # Bed temperature
        if 'heater_bed' in data and isinstance(data['heater_bed'], dict):
            heater_bed = data['heater_bed']
            if 'temperature' in heater_bed:
                temp = heater_bed['temperature']
                result['bed'] = {
                    "actual": float(temp) if isinstance(temp, (int, float)) else None,
                    "target": float(heater_bed.get('target')) if heater_bed.get('target') is not None else None
                }
        
        # Print stats
        if 'print_stats' in data and isinstance(data['print_stats'], dict):
            print_stats = data['print_stats']
            
            if 'filename' in print_stats:
                result['filename'] = print_stats['filename']
            
            if 'state' in print_stats:
                result['status'] = print_stats['state']
        
        # Progress from virtual_sdcard (most reliable)
        if 'virtual_sdcard' in data and isinstance(data['virtual_sdcard'], dict):
            vsd = data['virtual_sdcard']
            if 'progress' in vsd:
                try:
                    progress = float(vsd['progress'])
                    result['progress'] = int(round(progress * 100))
                except Exception:
                    pass
        
        return result
        
    except Exception as e:
        print(f"[Parser] Error: {e}")
        return None


# ---------------------------
# Printer Display Widget (embedded version)
# ---------------------------
class PrinterDisplayWidget(QtWidgets.QWidget):
    """Widget to display a single printer's data (embedded version)"""
    def __init__(self, printer_data: PrinterData, config: Config, embedded: bool = False):
        super().__init__()
        self.printer_data = printer_data
        self.config = config
        self.embedded = embedded
        self.thumbnail_loader = ThumbnailLoader()
        
        self.init_ui()
        
        # Connect to data updates
        self.printer_data.data_updated.connect(self.on_data_updated)
    
    def init_ui(self):
        layout = QtWidgets.QVBoxLayout()
        
        # Встраиваемый виджет имеет меньшие отступы
        if self.embedded:
            layout.setContentsMargins(8, 4, 8, 4)
        else:
            layout.setContentsMargins(8, 8, 8, 8)
            
        layout.setSpacing(6)
        
        # Printer name
        self.name_label = QtWidgets.QLabel(self.printer_data.name)
        self.name_label.setStyleSheet("""
            font-weight: bold;
            font-size: 14px;
            color: #fff;
            padding-bottom: 2px;
        """)
        self.name_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.name_label)
        
        # Thumbnail and filename row
        thumb_row = QtWidgets.QHBoxLayout()
        
        # Thumbnail
        self.thumb_label = QtWidgets.QLabel()
        self.thumb_label.setFixedSize(80, 60)
        self.thumb_label.setStyleSheet("""
            background: rgba(0,0,0,0.35);
            border-radius: 4px;
            border: 1px solid rgba(255,255,255,0.1);
        """)
        self.thumb_label.setAlignment(QtCore.Qt.AlignCenter)
        self.thumb_label.setText("Нет\nпревью")
        self.thumb_label.setWordWrap(True)
        thumb_row.addWidget(self.thumb_label)
        
        # Filename
        self.filename_label = QtWidgets.QLabel("—")
        self.filename_label.setStyleSheet("""
            font-weight: 600;
            color: #fff;
            font-size: 12px;
        """)
        self.filename_label.setWordWrap(True)
        self.filename_label.setAlignment(QtCore.Qt.AlignTop)
        thumb_row.addWidget(self.filename_label)
        
        layout.addLayout(thumb_row)
        
        # Progress bar
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(int(self.printer_data.progress))
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border-radius: 6px;
                text-align: center;
                color: #000;
                background: rgba(255,255,255,0.12);
                border: 1px solid rgba(255,255,255,0.1);
                font-weight: bold;
            }
            QProgressBar::chunk {
                border-radius: 6px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #75c9ff, stop:1 #2d9cff);
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # Temperatures row
        temp_row = QtWidgets.QHBoxLayout()
        
        self.hotend_label = QtWidgets.QLabel("Hotend: — °C")
        self.bed_label = QtWidgets.QLabel("Bed: — °C")
        self.status_label = QtWidgets.QLabel("Status: —")
        
        for label in [self.hotend_label, self.bed_label, self.status_label]:
            label.setStyleSheet("color: #fff; font-size: 12px;")
        
        temp_row.addWidget(self.hotend_label)
        temp_row.addStretch(1)
        temp_row.addWidget(self.bed_label)
        temp_row.addStretch(1)
        temp_row.addWidget(self.status_label)
        
        layout.addLayout(temp_row)
        
        self.setLayout(layout)
        self.update_display()
    
    def paintEvent(self, e):
        # Рисуем фон только для отдельных виджетов
        if not self.embedded:
            p = QtGui.QPainter(self)
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            rect = self.rect()
            p.setBrush(QtGui.QColor(18, 20, 25, 220))
            p.setPen(QtCore.Qt.NoPen)
            p.drawRoundedRect(rect, 10, 10)
        super().paintEvent(e)
    
    @QtCore.pyqtSlot(object)
    def on_data_updated(self, printer_data):
        """Update display when data changes"""
        self.update_display()
        
        # Update thumbnail if needed
        if printer_data.filename and printer_data.filename != printer_data.last_thumbnail_filename:
            printer_data.last_thumbnail_filename = printer_data.filename
            self.load_thumbnail(printer_data.ip, printer_data.filename)
    
    def update_display(self):
        """Update display from printer data"""
        data = self.printer_data
        if updates_paused:
            return
        # Update name (in case it was changed)
        self.name_label.setText(data.name)
        
        # Update filename
        self.filename_label.setText(data.filename or "—")
        
        # Update progress
        self.progress_bar.setValue(int(data.progress))
        self.progress_bar.setFormat(f"{int(data.progress)}%")
        
        # Update temperatures
        hotend_text = f"Hotend: {data.hotend_temp[0]:.1f}°C" if data.hotend_temp[0] is not None else "Hotend: —"
        if data.hotend_temp[1] is not None:
            hotend_text += f" / {data.hotend_temp[1]:.0f}°C"
        self.hotend_label.setText(hotend_text)
        
        bed_text = f"Bed: {data.bed_temp[0]:.1f}°C" if data.bed_temp[0] is not None else "Bed: —"
        if data.bed_temp[1] is not None:
            bed_text += f" / {data.bed_temp[1]:.0f}°C"
        self.bed_label.setText(bed_text)
        
        # Update status
        self.status_label.setText(f"Status: {data.status}")
    
    def load_thumbnail(self, ip: str, filename: str):
        """Load thumbnail in background"""
        def load_and_update():
            pixmap = self.thumbnail_loader.fetch_thumbnail(ip, filename)
            if pixmap and not pixmap.isNull():
                scaled = pixmap.scaled(self.thumb_label.size(),
                                      QtCore.Qt.KeepAspectRatio,
                                      QtCore.Qt.SmoothTransformation)
                QtCore.QMetaObject.invokeMethod(self, "set_thumbnail",
                                              QtCore.Qt.QueuedConnection,
                                              QtCore.Q_ARG(QtGui.QPixmap, scaled))
        
        self.thumbnail_loader.executor.submit(load_and_update)
    
    @QtCore.pyqtSlot(QtGui.QPixmap)
    def set_thumbnail(self, pixmap: QtGui.QPixmap):
        if pixmap and not pixmap.isNull():
            self.thumb_label.setPixmap(pixmap)
            self.thumb_label.setText("")
        else:
            self.thumb_label.setPixmap(QtGui.QPixmap())
            self.thumb_label.setText("Нет\nпревью")
# ---------------------------
# MultiPrinter Widget (unified version)
# ---------------------------
# ---------------------------
# MultiPrinter Widget (unified version with same layout as PrinterDisplayWidget)
# ---------------------------
class MultiPrinterWidget(QtWidgets.QWidget):
    """Single unified widget showing all printers with same layout as PrinterDisplayWidget"""
    def __init__(self, printers_data: List[PrinterData], config: Config, on_settings_callback: Callable):
        super().__init__()
        self.printers_data = printers_data
        self.config = config
        self.on_settings_callback = on_settings_callback
        self.thumbnail_loader = ThumbnailLoader()
        self.thumbnails = {}  # Cache for thumbnails: {printer_index: pixmap}
        
        self._drag_pos = None
        self.footer_visible = False
        self.hovered_printer = -1  # Index of currently hovered printer, -1 for none
        
        self.init_ui()
        self.setup_animations()
        
        # Connect to data updates for all printers
        for printer_data in printers_data:
            printer_data.data_updated.connect(self.on_data_updated)
    
    def init_ui(self):
        self.setWindowTitle("Klipper - Все принтеры")
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        
        self.width = self.config.config.get("widget_width", 360)
        self.opacity = self.config.config.get("widget_opacity", 0.88)
        
        # Constants for layout (matching PrinterDisplayWidget embedded mode)
        self.printer_height = 140  # Slightly increased for better spacing
        self.spacing = 6  # Increased spacing between printers
        self.padding_h = 8  # Horizontal padding
        self.padding_v = 4  # Vertical padding for embedded mode
        self.footer_height = 0  # Initially hidden
        
        # Calculate total height
        self.printer_count = len(self.printers_data)
        self.total_height = (self.printer_height * self.printer_count) + \
                          (self.spacing * (self.printer_count - 1)) + self.footer_height
        
        self.setFixedSize(self.width, self.total_height)
        self.setWindowOpacity(self.opacity)
        
        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
    
    def setup_animations(self):
        # Animation for footer
        self.footer_height = 0
        self.footer_animation = QtCore.QVariantAnimation()
        self.footer_animation.setDuration(300)
        self.footer_animation.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self.footer_animation.valueChanged.connect(self.update_footer_height)
    
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        
        # Draw main background
        rect = self.rect()
        p.setBrush(QtGui.QColor(18, 20, 25, 220))
        p.setPen(QtCore.Qt.NoPen)
        p.drawRoundedRect(rect, 10, 10)
        
        # Draw each printer's block
        for i, printer_data in enumerate(self.printers_data):
            self.draw_printer_block(p, i, printer_data)
        
        # Draw footer if visible
        if self.footer_height > 0:
            self.draw_footer(p)
        
        super().paintEvent(e)
    
    def draw_printer_block(self, p: QtGui.QPainter, index: int, printer_data: PrinterData):
        """Draw a single printer's information block matching PrinterDisplayWidget layout"""
        y_pos = index * (self.printer_height + self.spacing)
        
        # Draw printer block background (matching embedded widget)
        block_rect = QtCore.QRect(0, y_pos, self.width, self.printer_height)
        
        # Hover effect (subtle)
        if index == self.hovered_printer:
            p.setBrush(QtGui.QColor(35, 40, 50, 180))
        else:
            p.setBrush(QtGui.QColor(30, 35, 45, 180))
        
        p.setPen(QtCore.Qt.NoPen)
        p.drawRect(block_rect)
        
        # Draw separator line (except for last printer)
        if index < self.printer_count - 1:
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 20)))
            p.drawLine(0, y_pos + self.printer_height, 
                      self.width, y_pos + self.printer_height)
        
        # Draw printer name (center top)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255)))
        font = p.font()
        font.setBold(True)
        font.setPointSize(14)
        p.setFont(font)
        
        name_rect = QtCore.QRect(self.padding_h, y_pos + self.padding_v, 
                                self.width - 2 * self.padding_h, 24)
        p.drawText(name_rect, QtCore.Qt.AlignCenter, printer_data.name)
        
        # Draw thumbnail area (left side, 80x60)
        thumb_y = y_pos + self.padding_v + 24 + 6  # Name height + spacing
        thumb_rect = QtCore.QRect(self.padding_h, thumb_y, 80, 60)
        self.draw_thumbnail(p, thumb_rect, index, printer_data)
        
        # Draw filename (right side of thumbnail)
        font.setBold(True)
        font.setPointSize(12)
        p.setFont(font)
        
        filename = printer_data.filename or "—"
        # Wrap filename if too long
        if len(filename) > 30:
            # Try to find a good break point
            if len(filename) > 60:
                filename = filename[:57] + "..."
        
        filename_rect = QtCore.QRect(self.padding_h + 80 + 6, thumb_y, 
                                    self.width - self.padding_h - (80 + 6) - self.padding_h, 60)
        
        # Draw filename with word wrap - ИСПРАВЛЕНО
        p.save()
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255)))
        
        # Используем правильную перегрузку drawText
        text_option = QtGui.QTextOption()
        text_option.setWrapMode(QtGui.QTextOption.WordWrap)
        text_option.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        
        # Преобразуем QRect в QRectF и используем правильную сигнатуру
        p.drawText(QtCore.QRectF(filename_rect), filename, text_option)
        p.restore()
        
        # Draw progress bar (below thumbnail row)
        progress_y = thumb_y + 60 + 6  # Thumbnail height + spacing
        self.draw_progress_bar(p, progress_y, printer_data)
        
        # Draw temperatures and status (below progress bar)
        temp_y = progress_y + 18 + 6  # Progress bar height + spacing
        self.draw_temperatures(p, temp_y, printer_data)
    
    def draw_thumbnail(self, p: QtGui.QPainter, rect: QtCore.QRect, index: int, printer_data: PrinterData):
        """Draw thumbnail matching the style from PrinterDisplayWidget"""
        # Draw background (matching the style)
        p.setBrush(QtGui.QColor(0, 0, 0, 90))  # rgba(0,0,0,0.35) but adjusted for painter
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 25)))  # rgba(255,255,255,0.1)
        p.drawRoundedRect(rect, 4, 4)
        
        # Draw thumbnail if available
        if index in self.thumbnails and not self.thumbnails[index].isNull():
            pixmap = self.thumbnails[index]
            # Scale pixmap to fit while keeping aspect ratio
            scaled = pixmap.scaled(rect.size(), 
                                 QtCore.Qt.KeepAspectRatio, 
                                 QtCore.Qt.SmoothTransformation)
            pixmap_x = rect.x() + (rect.width() - scaled.width()) // 2
            pixmap_y = rect.y() + (rect.height() - scaled.height()) // 2
            p.drawPixmap(pixmap_x, pixmap_y, scaled)
        else:
            # Draw placeholder text (matching the original)
            p.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
            font = p.font()
            font.setPointSize(9)
            p.setFont(font)
            
            # Draw centered text with line break - ИСПРАВЛЕНО
            text = "Нет\nпревью"
            lines = text.split('\n')
            line_height = font.pointSize() + 2
            
            for i, line in enumerate(lines):
                # Используем правильную перегрузку drawText
                p.drawText(rect.x(), 
                          rect.y() + (rect.height() - len(lines) * line_height) // 2 + i * line_height,
                          rect.width(), 
                          line_height,
                          QtCore.Qt.AlignCenter, 
                          line)
            
            # Check if we need to load thumbnail
            if printer_data.filename and printer_data.filename != getattr(printer_data, 'last_thumbnail_filename', None):
                printer_data.last_thumbnail_filename = printer_data.filename
                self.load_thumbnail(index, printer_data.ip, printer_data.filename)
    
    def draw_progress_bar(self, p: QtGui.QPainter, y: int, printer_data: PrinterData):
        """Draw progress bar matching the style from PrinterDisplayWidget"""
        progress = int(printer_data.progress)
        bar_width = self.width - 2 * self.padding_h
        bar_height = 18
        bar_rect = QtCore.QRect(self.padding_h, y, bar_width, bar_height)
        
        # Draw background (matching QProgressBar style)
        p.setBrush(QtGui.QColor(255, 255, 255, 30))  # rgba(255,255,255,0.12)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 25)))  # rgba(255,255,255,0.1)
        p.drawRoundedRect(bar_rect, 6, 6)
        
        # Draw progress fill with gradient
        if progress > 0:
            fill_width = max(4, int((bar_width - 4) * progress / 100))
            fill_rect = QtCore.QRect(bar_rect.x() + 2, bar_rect.y() + 2, 
                                   fill_width, bar_height - 4)
            
            # Create gradient matching the original
            gradient = QtGui.QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
            gradient.setColorAt(0, QtGui.QColor(117, 201, 255))  # #75c9ff
            gradient.setColorAt(1, QtGui.QColor(45, 156, 255))   # #2d9cff
            
            p.setBrush(QtGui.QBrush(gradient))
            p.setPen(QtCore.Qt.NoPen)
            p.drawRoundedRect(fill_rect, 6, 6)
        
        # Draw progress text (black text on light background) - ИСПРАВЛЕНО
        p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0)))
        font = p.font()
        font.setBold(True)
        font.setPointSize(9)
        p.setFont(font)
        
        # Используем правильную перегрузку drawText
        p.drawText(bar_rect, QtCore.Qt.AlignCenter, f"{progress}%")
    
    def draw_temperatures(self, p: QtGui.QPainter, y: int, printer_data: PrinterData):
        """Draw temperature and status information matching PrinterDisplayWidget layout"""
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255)))
        font = p.font()
        font.setPointSize(12)
        p.setFont(font)
        
        # Prepare texts
        hotend_text = f"Hotend: {printer_data.hotend_temp[0]:.1f}°C" if printer_data.hotend_temp[0] is not None else "Hotend: —"
        if printer_data.hotend_temp[1] is not None:
            hotend_text += f" / {printer_data.hotend_temp[1]:.0f}°C"
        
        bed_text = f"Bed: {printer_data.bed_temp[0]:.1f}°C" if printer_data.bed_temp[0] is not None else "Bed: —"
        if printer_data.bed_temp[1] is not None:
            bed_text += f" / {printer_data.bed_temp[1]:.0f}°C"
        
        status_text = f"Status: {printer_data.status}"
        
        # Calculate text widths for proper spacing
        fm = p.fontMetrics()
        hotend_width = fm.horizontalAdvance(hotend_text)
        bed_width = fm.horizontalAdvance(bed_text)
        status_width = fm.horizontalAdvance(status_text)
        
        total_text_width = hotend_width + bed_width + status_width
        available_width = self.width - 2 * self.padding_h
        spacing = (available_width - total_text_width) / 2 if total_text_width < available_width else 10
        
        # Draw texts with proper spacing (matching the QHBoxLayout with stretch)
        x = self.padding_h
        text_height = 20
        
        # Hotend
        hotend_rect = QtCore.QRect(x, y, hotend_width, text_height)
        p.drawText(hotend_rect, QtCore.Qt.AlignLeft, hotend_text)
        
        # Bed (centered)
        x += hotend_width + spacing
        bed_rect = QtCore.QRect(x, y, bed_width, text_height)
        p.drawText(bed_rect, QtCore.Qt.AlignLeft, bed_text)
        
        # Status
        x += bed_width + spacing
        status_rect = QtCore.QRect(x, y, status_width, text_height)
        p.drawText(status_rect, QtCore.Qt.AlignLeft, status_text)
    
    def draw_footer(self, p: QtGui.QPainter):
        """Draw footer with instructions"""
        footer_rect = QtCore.QRect(0, self.height() - self.footer_height, 
                                 self.width, self.footer_height)
        
        # Draw footer background (matching the block color)
        p.setBrush(QtGui.QColor(30, 35, 45, 180))
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 25)))
        p.drawRect(footer_rect)
        
        # Draw top border
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 25)))
        p.drawLine(0, self.height() - self.footer_height, 
                  self.width, self.height() - self.footer_height)
        
        # Draw footer text - ИСПРАВЛЕНО
        p.setPen(QtGui.QPen(QtGui.QColor(207, 207, 207)))  # #cfcfcf
        font = p.font()
        font.setPointSize(10)
        p.setFont(font)
        
        # Используем правильную перегрузку drawText
        p.drawText(footer_rect, QtCore.Qt.AlignCenter, 
                  "Двойной клик - настройки • Перетащите для перемещения")
    
    def update_footer_height(self, value):
        """Update footer height and trigger repaint"""
        self.footer_height = value
        self.update_total_height()
        self.update()
    
    def update_total_height(self):
        """Update total widget height based on printer count and footer"""
        new_height = (self.printer_height * self.printer_count) + \
                    (self.spacing * (self.printer_count - 1)) + self.footer_height
        self.setFixedSize(self.width, new_height)
    
    def load_thumbnail(self, printer_index: int, ip: str, filename: str):
        """Load thumbnail for a specific printer"""
        def load_and_update():
            pixmap = self.thumbnail_loader.fetch_thumbnail(ip, filename)
            if pixmap and not pixmap.isNull():
                # Scale to match thumbnail size (80x60)
                scaled = pixmap.scaled(80, 60, 
                                     QtCore.Qt.KeepAspectRatio, 
                                     QtCore.Qt.SmoothTransformation)
                QtCore.QMetaObject.invokeMethod(
                    self, "set_thumbnail", 
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(int, printer_index),
                    QtCore.Q_ARG(QtGui.QPixmap, scaled)
                )
        
        self.thumbnail_loader.executor.submit(load_and_update)
    
    @QtCore.pyqtSlot(int, QtGui.QPixmap)
    def set_thumbnail(self, printer_index: int, pixmap: QtGui.QPixmap):
        """Set thumbnail for a specific printer and trigger repaint"""
        if pixmap and not pixmap.isNull():
            self.thumbnails[printer_index] = pixmap
            self.update()
    
    @QtCore.pyqtSlot(object)
    def on_data_updated(self, printer_data):
        """Handle data update from any printer"""
        if updates_paused:
            return
        
        # Find printer index
        try:
            printer_index = self.printers_data.index(printer_data)
            # Trigger thumbnail load if filename changed
            if printer_data.filename and printer_data.filename != getattr(printer_data, 'last_thumbnail_filename', None):
                printer_data.last_thumbnail_filename = printer_data.filename
                self.load_thumbnail(printer_index, printer_data.ip, printer_data.filename)
        except ValueError:
            pass
        
        self.update()
    
    # Mouse event handlers
    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()
            if self.footer_visible:
                self.hide_footer()
            e.accept()
        else:
            super().mousePressEvent(e)
    
    def mouseMoveEvent(self, e):
        # Update hovered printer
        y = e.pos().y()
        self.hovered_printer = y // (self.printer_height + self.spacing)
        if self.hovered_printer >= self.printer_count:
            self.hovered_printer = -1
        
        # Only repaint if hover state changed
        old_hover = getattr(self, '_last_hovered', -1)
        if old_hover != self.hovered_printer:
            self.update()
            self._last_hovered = self.hovered_printer
        
        # Handle dragging
        if self._drag_pos is not None and e.buttons() & QtCore.Qt.LeftButton:
            new_pos = e.globalPos() - self._drag_pos
            self.move(new_pos)
            e.accept()
        else:
            super().mouseMoveEvent(e)
    
    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self._drag_pos = None
            e.accept()
        else:
            super().mouseReleaseEvent(e)
    
    def mouseDoubleClickEvent(self, e):
        if self.on_settings_callback:
            self.on_settings_callback()
        e.accept()
    
    def enterEvent(self, event):
        if self._drag_pos is None:
            self.show_footer()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        if self._drag_pos is None:
            self.hide_footer()
        self.hovered_printer = -1
        self.update()
        super().leaveEvent(event)
    
    def show_footer(self):
        if not self.footer_visible:
            self.footer_visible = True
            self.footer_animation.setStartValue(self.footer_height)
            self.footer_animation.setEndValue(30)
            self.footer_animation.start()
    
    def hide_footer(self):
        if self.footer_visible:
            self.footer_visible = False
            self.footer_animation.setStartValue(self.footer_height)
            self.footer_animation.setEndValue(0)
            self.footer_animation.start()

# ---------------------------
# Single Printer Widget (standalone window) - ИСПРАВЛЕННЫЙ
# ---------------------------
class SinglePrinterWidget(QtWidgets.QWidget):
    """Standalone window for a single printer"""
    def __init__(self, printer_data: PrinterData, config: Config, on_settings_callback: Callable):
        super().__init__()
        self.printer_data = printer_data
        self.config = config
        self.on_settings_callback = on_settings_callback
        self.setup_context_menu()
        self._drag_pos = None
        self.footer_visible = False
        
        self.init_ui()
        self.setup_animations()
        
        # Таймер для отложенного перемещения
        self._move_timer = QtCore.QTimer()
        self._move_timer.setSingleShot(True)
        self._move_timer.setInterval(10)  # 10 мс для плавного перемещения
        self._move_timer.timeout.connect(self._perform_move)
        self._target_pos = None
    def setup_context_menu(self):
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
    
    def show_context_menu(self, pos):
        menu = QtWidgets.QMenu(self)
        close_action = menu.addAction("Закрыть виджет")
        close_action.triggered.connect(self.close_widget)
        menu.exec_(self.mapToGlobal(pos))
    
    def close_widget(self):
        """Закрываем окно виджета и выполняем скрипт закрытия"""
        print(f"[{self.printer_data.name}] Виджет закрыт через контекстное меню")
        global end 
        end = True
        self.close()  # закрывает окно
    def init_ui(self):
        self.setWindowTitle(f"Widget - {self.printer_data.name}")
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        
        width = self.config.config.get("widget_width", 360)
        height = self.config.config.get("widget_height", 150)
        opacity = self.config.config.get("widget_opacity", 0.88)
        
        self.setFixedSize(width, height)
        self.setWindowOpacity(opacity)
        
        # Create main layout
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create embedded display widget
        self.display_widget = PrinterDisplayWidget(self.printer_data, self.config, embedded=False)
        main_layout.addWidget(self.display_widget)
        
        # Footer (скрыт по умолчанию)
        self.footer = QtWidgets.QLabel("Двойной клик - настройки • Перетащите для перемещения")
        self.footer.setStyleSheet("""
            QLabel {
                color: #cfcfcf;
                font-size: 10px;
                background-color: rgba(30, 35, 45, 180);
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                padding: 5px;
            }
        """)
        self.footer.setAlignment(QtCore.Qt.AlignCenter)
        self.footer.setFixedHeight(0)
        main_layout.addWidget(self.footer)
        
        self.setLayout(main_layout)
    
    def setup_animations(self):
        # Анимация появления футера
        self.footer_animation = QtCore.QPropertyAnimation(self.footer, b"maximumHeight")
        self.footer_animation.setDuration(300)
        self.footer_animation.setEasingCurve(QtCore.QEasingCurve.OutCubic)
    
    def _perform_move(self):
        """Выполнить перемещение окна (вызывается таймером)"""
        if self._target_pos is not None and self._drag_pos is not None:
            self.move(self._target_pos - self._drag_pos)
            # Запускаем следующий кадр
            self._move_timer.start()
    
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.rect()
        p.setBrush(QtGui.QColor(18, 20, 25, 220))
        p.setPen(QtCore.Qt.NoPen)
        p.drawRoundedRect(rect, 10, 10)
        super().paintEvent(e)
    
    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()
            self.hide_footer()
            e.accept()
    
    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() & QtCore.Qt.LeftButton:
            # Сохраняем целевую позицию
            self._target_pos = e.globalPos()
            
            # Если таймер не запущен, запускаем его
            if not self._move_timer.isActive():
                self._move_timer.start()
            
            e.accept()
        elif not self.underMouse() and self.footer_visible:
            self.hide_footer()
    
    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self._drag_pos = None
            self._target_pos = None
            self._move_timer.stop()
            pos = self.pos()
            print(f"[{vars(self.printer_data)}] Перемещено в: x={pos.x()}, y={pos.y()}")
            # -------------------------
    
            e.accept()
    
    def mouseDoubleClickEvent(self, e):
        if self.on_settings_callback:
            self.on_settings_callback()
        e.accept()
    
    def enterEvent(self, event):
        if self._drag_pos is None:  # Только если не перетаскиваем
            self.show_footer()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        if self._drag_pos is None:  # Только если не перетаскиваем
            self.hide_footer()
        super().leaveEvent(event)
    
    def show_footer(self):
        if not self.footer_visible:
            self.footer_visible = True
            self.footer_animation.setStartValue(self.footer.height())
            self.footer_animation.setEndValue(30)
            self.footer_animation.start()
    
    def hide_footer(self):
        if self.footer_visible:
            self.footer_visible = False
            self.footer_animation.setStartValue(self.footer.height())
            self.footer_animation.setEndValue(0)
            self.footer_animation.start()


# ---------------------------
# Main Application
# ---------------------------
class KlipperApp(QtCore.QObject):
    """Main application controller"""
    def __init__(self, config_file: str = CONFIG_FILE):
        super().__init__()
        self.config = Config(config_file)
        self.printers_data = {}  # ip -> PrinterData
        self.ws_manager = WebSocketManager()
        self.widgets = []
        
        # Очередь для накопления данных
        self._data_queue = {}
        self._update_timer = QtCore.QTimer()
        self._update_timer.setInterval(500)  # Уменьшили до 50 мс для более плавного обновления
        self._update_timer.timeout.connect(self._process_data_queue)
        
        # Connect WebSocket manager signals
        self.ws_manager.data_received.connect(self.handle_websocket_data)
    
    def initialize(self):
        """Initialize application based on config"""
        # Show settings on first run
        if self.config.config.get("first_run", True):
            dialog = SettingsDialog(self.config)
            if dialog.exec_() != QtWidgets.QDialog.Accepted:
                return False
            
            self.config.mark_first_run_complete()
            self.config.save_config()
        
        # Get enabled printers
        enabled_printers = self.config.get_enabled_printers()
        if not enabled_printers:
            QtWidgets.QMessageBox.warning(None, "Ошибка", "Нет включенных принтеров!")
            return False
        
        # Initialize printer data and start WebSocket connections
        for printer in enabled_printers:
            name = printer.get("name", "Unknown")
            ip = printer.get("ip", "")
            ind = printer.get("index")
            if ip:
                self.printers_data[ip] = PrinterData(name, ip)
                self.ws_manager.start_printer(printer)
        
        # Start update timer
        self._update_timer.start()
        
        return True
    
    def create_widgets(self):
        """Create widgets based on mode"""
        enabled_printers = self.config.get_enabled_printers()
        printer_data_list = [self.printers_data.get(p["ip"]) for p in enabled_printers if p["ip"] in self.printers_data]
        
        if not printer_data_list:
            return False
        
        multiple_widgets = self.config.config.get("multiple_widgets", False)
        
        if multiple_widgets:
            # Create separate widget for each printer
            x, y = 80, 80
            for printer_data in printer_data_list:
                widget = SinglePrinterWidget(printer_data, self.config, self.open_settings)
                widget.move(x, y)
                widget.show()
                self.widgets.append(widget)
                y += widget.height() + 20  # Stagger windows with gap
        else:
            # Create single widget with all printers
            widget = MultiPrinterWidget(printer_data_list, self.config, self.open_settings)
            widget.move(80, 80)
            widget.show()
            self.widgets.append(widget)
        
        return True
    
    @QtCore.pyqtSlot(dict)
    def handle_websocket_data(self, msg: Dict):
        """Handle incoming WebSocket data (called from any thread)"""
        if msg.get("type") == "ws_message":
            printer_ip = msg.get("printer_ip")
            if printer_ip not in self.printers_data:
                return
            
            parsed = parse_moonraker_message(msg.get("raw"))
            if parsed:
                # Сохраняем данные в очередь вместо немедленного обновления
                self._data_queue[printer_ip] = parsed
    
    @QtCore.pyqtSlot()
    def _process_data_queue(self):
        """Process queued data from WebSocket (called in main thread)"""
        for ip, parsed in self._data_queue.items():
            if ip in self.printers_data:
                self.printers_data[ip].update_from_parsed(parsed)
        self._data_queue.clear()
        
        # Принудительно обрабатываем события очереди для более плавного обновления
        QtWidgets.QApplication.processEvents()
    
    def open_settings(self):
        """Open settings dialog and restart application if needed"""
        dialog = SettingsDialog(self.config, parent=self.widgets[0] if self.widgets else None)
        
        # Сохраняем текущее состояние перед открытием диалога
        old_widgets = self.widgets.copy()
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Закрываем только старые виджеты при подтверждении изменений
            for widget in old_widgets:
                widget.close()
            
            # Stop all WebSocket connections
            self.ws_manager.stop_all()
            self._update_timer.stop()
            
            # Clear old data
            self.printers_data.clear()
            self._data_queue.clear()
            self.widgets.clear()
            
            # Reinitialize
            if self.initialize():
                self.create_widgets()
        else:
            # При отмене НЕ закрываем виджеты
            # Просто активируем существующие окна
            for widget in self.widgets:
                widget.raise_()
                widget.activateWindow()
    
    def shutdown(self):
        """Shutdown application"""
        self._update_timer.stop()
        self.ws_manager.stop_all()


# ---------------------------
# Main runner
# ---------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Floating Klipper gadget")
    parser.add_argument("--config", default=CONFIG_FILE, help="Config file path")
    args = parser.parse_args()
    
    app = QtWidgets.QApplication(sys.argv)
    
    # Create and initialize application
    klipper_app = KlipperApp(args.config)
    if not klipper_app.initialize():
        sys.exit(1)
    
    if not klipper_app.create_widgets():
        QtWidgets.QMessageBox.warning(None, "Ошибка", "Не удалось создать виджеты!")
        sys.exit(1)
    
    try:
        exit_code = app.exec_()
    finally:
        klipper_app.shutdown()
    
    sys.exit(exit_code)


if __name__ == "__main__":

    main()

