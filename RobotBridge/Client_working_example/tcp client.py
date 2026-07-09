# python
import sys
import socket
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QSpinBox, QPushButton,
                             QGridLayout, QDialog, QLineEdit)
from PyQt5.QtCore import Qt, pyqtSignal, QEvent, QTimer
# pyinstaller --onefile --windowed --name "Saad" '.\tcp client.py'
# Configuration
ROBOT_IP = "192.168.201.1"
ROBOT_PORT = 6001

# Parameters and valid ranges
PARAMS = [
    ("J_SPEED", 1, 100), ("L_SPEED", 1, 100),
    ("WAX_SPEED", 0, 100), ("WATER_SPEED", 0, 100),
    ("REPEATS", 1, 10),
    ("START_WAIT", 10, 10000), ("WATER_WAIT", 10, 10000),
    ("WAX_WAIT_TIME_IN", 0, 10000), ("WAX_WAIT_TIME_OUT", 10, 10000),
    ("STAND_WAIT", 10, 10000), ("END_WAIT", 10, 10000)
]

# 1. DEFINE THIS CLASS FIRST TO AVOID NAME ERROR
class ClickableSpinBox(QSpinBox):
    """Custom SpinBox that detects taps and prevents default focus."""
    clicked = pyqtSignal()
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.NoFocus)
        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            self.clicked.emit()
            return True
        return super().eventFilter(obj, event)


class NumericKeypad(QDialog):
    """Pop-up touchscreen numpad with keyboard support."""
    def __init__(self, current_val, min_v, max_v, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setFixedSize(380, 550)
        self.setStyleSheet("background-color: #2c3e50; border: 4px solid #3498db; border-radius: 20px;")

        layout = QVBoxLayout(self)
        self.display = QLineEdit(str(current_val))
        self.display.setReadOnly(False)
        self.display.setAlignment(Qt.AlignCenter)
        self.display.setStyleSheet("font-size: 50px; padding: 15px; background: white; color: black; border-radius: 10px;")
        self.display.setFocus()
        layout.addWidget(self.display)

        grid = QGridLayout()
        grid.setSpacing(10)
        buttons = ['7', '8', '9', '4', '5', '6', '1', '2', '3', '0', 'CLR', 'OK']
        for i, b in enumerate(buttons):
            btn = QPushButton(b)
            btn.setFixedSize(100, 90)
            color = "#27ae60" if b == 'OK' else "#c0392b" if b == 'CLR' else "#34495e"
            btn.setStyleSheet(f"font-size: 28px; font-weight: bold; background: {color}; color: white; border-radius: 15px;")
            btn.clicked.connect(lambda checked, val=b: self.on_click(val))
            grid.addWidget(btn, i // 3, i % 3)
        layout.addLayout(grid)

        self.result_value = current_val
        self.min_v = min_v
        self.max_v = max_v

    def keyPressEvent(self, event):
        """Handle keyboard input for digits, backspace, and enter"""
        key = event.text()
        if key.isdigit():
            # Append digit to display
            self.display.setText(self.display.text() + key)
        elif event.key() == Qt.Key_Backspace:
            # Clear on backspace
            self.display.clear()
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            # Accept on enter
            self.on_click('OK')
        else:
            super().keyPressEvent(event)

    def on_click(self, label):
        if label == 'OK':
            try:
                val = int(self.display.text() if self.display.text() != "" else 0)
                self.result_value = max(self.min_v, min(val, self.max_v))
                self.accept()
            except ValueError: self.reject()
        elif label == 'CLR':
            self.display.clear()
        else:
            self.display.setText(self.display.text() + label)


class DobotControlUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setFixedSize(1000, 900)
        self.setStyleSheet("background-color: #1a1a1a; color: white; font-family: Arial;")
        self.inputs = {}

        # Persistent socket management
        self.socket = None
        self.reconnect_timer = QTimer()
        self.reconnect_timer.timeout.connect(self.try_reconnect)
        self.reconnect_timer.setInterval(5000)  # Try reconnect every 5 seconds if disconnected
        self.status_led = None

        # Status check timer - probe connection once a second
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.check_connection)
        self.status_timer.setInterval(1000)  # 1 second

        self.init_ui()
        # Start periodic status checks
        self.status_timer.start()
        self.connect_to_robot()

    def init_ui(self):
        self.setWindowTitle(f"SAAD ROBOT PARAMETER CONTROL — {ROBOT_IP}:{ROBOT_PORT}")
        self.center_window()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        # Reduced top/bottom margins to allow rows to spread out more
        layout.setContentsMargins(20, 10, 20, 10)


        self.status_led = QLabel("OFFLINE")
        self.status_led.setFixedSize(80, 80)                      # square for perfect circle
        self.status_led.setAlignment(Qt.AlignCenter)
        self.status_led.setStyleSheet( "font-weight: bold; color: white; border-radius: 40px; background-color: #c0392b;")

        new_bulb_btn = QPushButton("New Bulb")
        new_bulb_btn.setFixedSize(150, 80)
        new_bulb_btn.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold; border-radius: 10px;")
        new_bulb_btn.clicked.connect(lambda: self.send_to_robot("New_Bulb", 1))

        header_layout = QGridLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setHorizontalSpacing(0)
        header_layout.setVerticalSpacing(0)
        # left and right stretches keep the center column centered
        header_layout.setColumnStretch(0, 1)
        header_layout.setColumnStretch(1, 0)
        header_layout.setColumnStretch(2, 1)

        # add widgets: status_led on left, new_bulb_btn centered
        header_layout.addWidget(self.status_led, 0, 0, Qt.AlignLeft | Qt.AlignTop)
        header_layout.addWidget(new_bulb_btn, 0, 1, Qt.AlignHCenter | Qt.AlignTop)

        # header_layout.addWidget(new_bulb_btn)
        # header_layout.addWidget(self.status_led)
        layout.addLayout(header_layout)

        # --- RE-SPACED GRID SYSTEM ---
        grid = QGridLayout()
        # INCREASED vertical spacing to reduce "crowded" feel
        grid.setVerticalSpacing(20)
        grid.setHorizontalSpacing(15)

        grid.setColumnStretch(0, 1) # Left spacer
        grid.setColumnStretch(1, 0) # Labels
        grid.setColumnStretch(2, 0) # Controls
        grid.setColumnStretch(3, 1) # Right spacer

        for i, (name, vmin, vmax) in enumerate(PARAMS):
            # Parameter Labels
            param_label = QLabel(f"{name}\n({vmin}-{vmax})")
            param_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            # Slightly smaller label font to match thinner rows
            param_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #bdc3c7; padding-right: 20px;")
            grid.addWidget(param_label, i, 1)

            container = QWidget()
            h_layout = QHBoxLayout(container)
            h_layout.setContentsMargins(0, 0, 0, 0)
            h_layout.setSpacing(10)

            step_val = 100 if "WAIT" in name else 1
            row_height = 55

            m_btn = QPushButton("-")
            m_btn.setFixedSize(80, row_height)
            m_btn.setStyleSheet("font-size: 28px; background: #c0392b; border-radius: 10px; font-weight: bold;")

            spin = ClickableSpinBox()
            spin.setRange(vmin, vmax)
            # WIDER but THINNER numeric display
            spin.setFixedSize(500, row_height)
            spin.setButtonSymbols(QSpinBox.NoButtons)
            spin.setAlignment(Qt.AlignCenter)
            spin.setReadOnly(True)
            # Smaller font for the thinner bar
            spin.setStyleSheet(f"QSpinBox {{ font-size: 32px; background: #34495e; color: #2ecc71; border-radius: 12px; }}")

            key_btn = QPushButton("KEYPAD")
            key_btn.setFixedSize(120, row_height)
            key_btn.setStyleSheet("font-size: 16px; background: #3498db; border-radius: 10px; font-weight: bold;")

            p_btn = QPushButton("+")
            p_btn.setFixedSize(80, row_height)
            p_btn.setStyleSheet("font-size: 28px; background: #27ae60; border-radius: 10px; font-weight: bold;")

            # Logic connections
            # key_btn.clicked.connect(lambda _, n=name, s=spin, mi=vmin, ma=vmax: self.open_numpad(n, s, mi, ma))
            # spin.clicked.connect(lambda n=name, s=spin, mi=vmin, ma=vmax: self.open_numpad(n, s, mi, ma))
            spin.editingFinished.connect(lambda n=name, s=spin: self.send_to_robot(n, s.value()))
            m_btn.clicked.connect(lambda _, s=spin, sv=step_val: self.quick_adjust(s, -sv))
            p_btn.clicked.connect(lambda _, s=spin, sv=step_val: self.quick_adjust(s, sv))

            h_layout.addWidget(m_btn)
            h_layout.addWidget(spin)
            # h_layout.addWidget(key_btn)
            h_layout.addWidget(p_btn)

            grid.addWidget(container, i, 2)
            self.inputs[name] = spin

        layout.addLayout(grid)
        layout.addStretch(1)

    def update_status(self, online):
        radius = 40  # must match half of setFixedSize()
        if online:
            self.status_led.setText("ONLINE")
            self.status_led.setStyleSheet( f"background-color: #27ae60; color: white; border-radius: {radius}px; font-weight: bold;" )
        else:
            self.status_led.setText("OFFLINE")
            self.status_led.setStyleSheet( f"background-color: #c0392b; color: white; border-radius: {radius}px; font-weight: bold;" )

    def open_numpad(self, name, spin, vmin, vmax):
        dialog = NumericKeypad(spin.value(), vmin, vmax, self)
        if dialog.exec_():
            spin.setValue(dialog.result_value)
            self.send_to_robot(name, dialog.result_value)

    def quick_adjust(self, spin, delta):
        spin.setValue(spin.value() + delta)
        spin.editingFinished.emit()

    def connect_to_robot(self):
        """Establish persistent TCP connection to robot"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(2)
            self.socket.connect((ROBOT_IP, ROBOT_PORT))
            self.update_status(True)
            self.reconnect_timer.stop()
            # Request sync after connection established
            self.request_sync_from_robot()
        except Exception:
            self.update_status(False)
            self.socket = None
            self.reconnect_timer.start()

    def try_reconnect(self):
        """Attempt to reconnect if connection is lost"""
        if self.socket is None:
            self.connect_to_robot()

    def disconnect_from_robot(self):
        """Close persistent TCP connection"""
        try:
            if self.socket:
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()
        except:
            pass
        finally:
            self.socket = None
            self.reconnect_timer.stop()

    def send_to_robot(self, name, val):
        """Send command via persistent TCP connection"""
        try:
            if self.socket is None:
                raise Exception("Not connected")
            self.socket.sendall(f"{name}:{val}".encode('utf-8'))
            self.socket.recv(1024)
            self.update_status(True)
        except Exception:
            self.update_status(False)
            self.disconnect_from_robot()
            self.reconnect_timer.start()

    def check_connection(self):
        """Probe the TCP connection once a second and update the status LED.

        Sends a lightweight heartbeat and expects any response. On failure,
        it marks offline and kicks off reconnection attempts.
        """
        # If no socket, mark offline and let reconnect timer handle reconnection
        if self.socket is None:
            self.update_status(False)
            return

        try:
            # Send a lightweight probe; server should reply or at least not raise
            try:
                self.socket.sendall(b"HEARTBEAT")
                # Try to read any immediate response (non-blocking due to short timeout)
                _ = self.socket.recv(1024)
                self.update_status(True)
            except Exception:
                # If probe fails, consider connection lost
                raise
        except Exception:
            self.update_status(False)
            # Clean-up and schedule reconnects
            try:
                self.disconnect_from_robot()
            except Exception:
                pass
            self.reconnect_timer.start()

    def request_sync_from_robot(self):
        """Request parameter sync from robot via persistent connection"""
        try:
            if self.socket is None:
                raise Exception("Not connected")
            self.socket.sendall("GET_SYNC".encode('utf-8'))
            data = self.socket.recv(1024).decode('utf-8')
            if data.startswith("SYNC:"):
                self.update_status(True)
                for part in data[5:].split(","):
                    v_name, v_val = part.split("=")
                    if v_name in self.inputs:
                        self.inputs[v_name].setValue(int(v_val))
        except Exception:
            self.update_status(False)
            self.disconnect_from_robot()
            self.reconnect_timer.start()

    def closeEvent(self, event):
        """Cleanup: disconnect from robot on application shutdown"""
        self.disconnect_from_robot()
        event.accept()

    def center_window(self):
        """Move window to the center of the primary screen."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        screen_geo = screen.availableGeometry()
        x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
        y = screen_geo.y() + (screen_geo.height() - self.height()) // 2
        self.move(x, y)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DobotControlUI()
    window.show()
    sys.exit(app.exec())
