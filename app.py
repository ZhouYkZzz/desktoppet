#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Desktop‑Pet with calendar duration selector (macOS).
"""
import sys, os, json, subprocess
from pathlib import Path
from datetime import datetime, timedelta
import requests
from typing import Optional

from PyQt5.QtWidgets import (
    QApplication, QLabel, QWidget, QMenu, QMessageBox,
    QInputDialog, QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QDateEdit, QTimeEdit, QLineEdit, QLabel as QtLabel
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QDate, QTime
from PyQt5.QtGui import QMovie, QPixmap

CONFIG_PATH = Path.home() / ".desktop_pet_config.json"

# ---------- 高德 API 端点 ----------
GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"

# ---------- 在此填入你的高德 Web API Key ----------
API_KEY = "e84310e1f93659655488638257320d47"  # ← 换成自己的 Key
# ------------------------------------------------------

# ----------- 天气后台线程 -----------
class WeatherThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, api_key: str, city: str, parent=None):
        super().__init__(parent)
        self.api_key = api_key
        self.city = city

    def run(self):
        try:
            geo = requests.get(
                GEOCODE_URL,
                params={"address": self.city, "output": "JSON", "key": self.api_key},
                timeout=(5, 10),
            )
            geo.raise_for_status()
            gdata = geo.json()["geocodes"]
            if not gdata:
                raise ValueError(f"找不到城市「{self.city}」")
            adcode = gdata[0]["adcode"]

            w = requests.get(
                WEATHER_URL,
                params={"city": adcode, "extensions": "all", "output": "JSON", "key": self.api_key},
                timeout=(5, 15),
            )
            w.raise_for_status()
            fcasts = w.json()["forecasts"][0]["casts"]
            self.finished.emit({"today": fcasts[0], "tomorrow": fcasts[1]})

        except Exception as e:
            self.error.emit(str(e))


# ----------- 日程对话框 -----------
class EventDialog(QDialog):
    """日期 + 时间 + 持续时长 + 标题 选择对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建日程")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        today = QDate.currentDate()
        next_hour = (datetime.now() + timedelta(hours=1)).time().replace(second=0, microsecond=0)

        # 起始日期
        self.date_edit = QDateEdit(today, self)
        self.date_edit.setCalendarPopup(True)

        # 起始时间
        self.time_edit = QTimeEdit(QTime(next_hour.hour, next_hour.minute), self)
        self.time_edit.setDisplayFormat("HH:mm")

        # ▶ 新增：持续时长（默认 01:00）
        self.duration_edit = QTimeEdit(QTime(1, 0), self)
        self.duration_edit.setDisplayFormat("HH:mm")
        # 如果想要 5 分钟递增，取消下一行注释
        # self.duration_edit.setSingleStep(QTime(0, 5))

        # 事件标题
        self.title_edit = QLineEdit(self)
        self.title_edit.setPlaceholderText("事件标题…")

        # 按钮
        ok_btn = QPushButton("创建", self)
        cancel_btn = QPushButton("取消", self)
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        # 布局
        vbox = QVBoxLayout(self)
        vbox.addWidget(QtLabel("选择日期："))
        vbox.addWidget(self.date_edit)
        vbox.addWidget(QtLabel("选择时间："))
        vbox.addWidget(self.time_edit)
        vbox.addWidget(QtLabel("持续时长："))      # ← 新增
        vbox.addWidget(self.duration_edit)        # ← 新增
        vbox.addWidget(QtLabel("事件标题："))
        vbox.addWidget(self.title_edit)

        hbtn = QHBoxLayout()
        hbtn.addStretch()
        hbtn.addWidget(ok_btn)
        hbtn.addWidget(cancel_btn)
        vbox.addLayout(hbtn)

    # -------- 返回起始时间、持续时长、标题 --------
    @staticmethod
    def get_event(parent=None):
        dlg = EventDialog(parent)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.date_edit.date().toPyDate()
            t = dlg.time_edit.time().toPyTime()
            start_dt = datetime.combine(d, t)

            dur_qt = dlg.duration_edit.time()
            duration = timedelta(hours=dur_qt.hour(), minutes=dur_qt.minute())

            title = dlg.title_edit.text().strip() or "提醒"
            return start_dt, duration, title
        return None, None, None


# ----------- 桌面宠物 -----------
class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()

        # —— 窗口 & 透明 —— #
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
            Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # —— Label & GIF —— #
        self.label = QLabel(self)
        self.label.setStyleSheet("background: transparent; border: none;")
        self.resize(200, 200)
        self.label.resize(200, 200)

        self.movie_main = QMovie(self.resource_path("mostima.gif"))
        self.movie_relax = QMovie(self.resource_path("relax.gif"))
        self.movie_main.frameChanged.connect(self.update_frame)
        self.movie_relax.frameChanged.connect(self.update_frame)
        self.movie = self.movie_main
        self.movie.start()

        # —— 状态 —— #
        self.menu_open = False
        self.dragging = False

        # —— 运动 —— #
        self.direction = 1
        self.speed = 1
        self.screen_rect = QApplication.primaryScreen().geometry()
        self.offset = 0
        self.base_y = self.screen_rect.height() - self.height() - self.offset
        self.move(100, self.base_y)

        self.timer = QTimer(self, timeout=self.move_pet)
        self.timer.start(30)

        # —— 城市 & 天气 —— #
        self.city = self.load_city()
        self.w_thread = None
        self.fetch_weather()

        # —— 新增的天气显示部分 —— #
        self.weather_label = QLabel(self)
        self.weather_label.setAlignment(Qt.AlignCenter)
        self.weather_label.setStyleSheet("font-size: 12px; color: white; background: transparent;")
        self.weather_label.setGeometry(0, 20, self.width(), self.height())

        # —— 新增的5秒后隐藏Label —— #
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)  # 确保只触发一次
        self.hide_timer.timeout.connect(self.hide_label)

    def load_city(self):
        if CONFIG_PATH.exists():
            try:
                return json.loads(CONFIG_PATH.read_text()).get("city", "杭州")
            except Exception:
                pass
        return "杭州"

    def save_city(self):
        try:
            CONFIG_PATH.write_text(json.dumps({"city": self.city}))
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"无法保存城市：{e}")

    # ---------- 天气 ----------
    def fetch_weather(self):
        if not API_KEY or API_KEY == "YOUR_AMAP_API_KEY":
            QMessageBox.warning(self, "天气提醒", "请在源码顶部 API_KEY 处填入你的高德 Key！")
            return
        if self.w_thread and self.w_thread.isRunning():
            self.w_thread.quit()
            self.w_thread.wait()

        self.w_thread = WeatherThread(API_KEY, self.city, self)
        self.w_thread.finished.connect(self.show_weather_label)
        self.w_thread.error.connect(self.show_weather_error)
        self.w_thread.start()

    def show_weather_label(self, data):
        def fmt(day):
            desc = f'{day["dayweather"]}/{day["nightweather"]}'
            tmin, tmax = int(day["nighttemp"]), int(day["daytemp"])
            return desc, f"{tmin}°C~{tmax}°C"

        d1, t1 = fmt(data["today"])
        d2, t2 = fmt(data["tomorrow"])
        msg = f"{self.city} 今天：{d1} {t1}\n{self.city} 明天：{d2} {t2}"

        # 设置天气信息到QLabel
        self.weather_label.setText(msg)
        self.weather_label.adjustSize()  # 调整 QLabel 大小适应内容

        # 启动定时器，5秒后隐藏 label
        self.hide_timer.start(5000)

    def show_weather_error(self, err):
        self.weather_label.setText(f"获取天气信息失败：{err}")

    def hide_label(self):
        self.weather_label.setText("")  # 清空天气信息
        self.weather_label.adjustSize()  # 调整大小
        old_x, old_y = self.x(), self.y()
        self.resize(100,200)  # 调整窗口大小以适应隐藏后的状态
        self.label.resize(100, 200)  # 调整 QLabel 大小
        self.move(old_x, old_y)  # 保持原位置

    # ---------- 右键菜单 ----------
    def contextMenuEvent(self, e):
        self.menu_open = True
        running = self.timer.isActive()
        self.timer.stop()
        self.movie.setPaused(True)

        menu = QMenu(self)
        loc_act = menu.addAction("位置…")
        sched_act = menu.addAction("新建日程…")
        quit_act = menu.addAction("退出")
        chosen = menu.exec_(e.globalPos())

        if chosen == loc_act:
            self.change_city()
        elif chosen == sched_act:
            self.create_calendar_event()
        elif chosen == quit_act:
            QApplication.quit()

        self.menu_open = False
        if running:
            self.timer.start(30)
        self.movie.setPaused(False)

    # ---------- 修改城市 ----------
    def change_city(self):
        text, ok = QInputDialog.getText(self, "设置位置", "请输入城市名：", text=self.city)
        if ok and text.strip():
            self.city = text.strip()
            self.save_city()
            self.fetch_weather()

    # ---------- 新建日程 ----------
    def create_calendar_event(self):
        start_dt, duration, title = EventDialog.get_event(self)
        if not start_dt:
            return  # 用户取消

        end_dt = start_dt + duration
        try:
            self._add_event_to_calendar(start_dt, end_dt, title, cal_name="个人")
            dur_hours = duration.seconds // 3600
            dur_mins = (duration.seconds // 60) % 60
            QMessageBox.information(
                self, "已创建",
                f"已在 {start_dt.strftime('%m-%d %H:%M')} 创建「{title}」，持续 {dur_hours}h{dur_mins:02d}m"
            )
        except Exception as e:
            QMessageBox.warning(self, "创建失败", str(e))

    # ---------- 往 macOS 日历写入事件 ----------
    def _add_event_to_calendar(
        self,
        start_dt: datetime,
        end_dt: datetime,
        title: str,
        notes: str = "",
        cal_name: Optional[str] = None,
    ):
        """
        在 macOS 日历中添加事件。
        start_dt, end_dt: datetime
        title: 事件标题
        notes: 备注
        cal_name: 日历名称，None 时依次尝试“日历”→“Calendar”
        """
        try_names = ["日历", "Calendar"] if cal_name is None else [cal_name]

        sy, sM, sd = start_dt.year, start_dt.month, start_dt.day
        sh, sm = start_dt.hour, start_dt.minute
        ey, eM, ed = end_dt.year, end_dt.month, end_dt.day
        eh, em = end_dt.hour, end_dt.minute

        success, last_err = False, ""
        for name in try_names:
            applescript_code = f'''
            try
                tell application "Calendar"
                    tell calendar "{name}"
                        set eventStart to (current date)
                        set year of eventStart to {sy}
                        set month of eventStart to {sM}
                        set day of eventStart to {sd}
                        set hours of eventStart to {sh}
                        set minutes of eventStart to {sm}
                        set seconds of eventStart to 0
                        set eventEnd to (current date)
                        set year of eventEnd to {ey}
                        set month of eventEnd to {eM}
                        set day of eventEnd to {ed}
                        set hours of eventEnd to {eh}
                        set minutes of eventEnd to {em}
                        set seconds of eventEnd to 0
                        make new event with properties {{summary:"{title}", start date:eventStart, end date:eventEnd, description:"{notes}"}}
                        return "" -- 成功返回空串
                    end tell
                end tell
            on error errMsg
                return errMsg
            end try
            '''
            result = subprocess.run(
                ["osascript", "-e", applescript_code],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip() == "":
                success = True
                break
            last_err = result.stdout or result.stderr

        if not success:
            raise RuntimeError(f"无法写入日历，AppleScript 错误信息：{last_err}")

    # ---------- 其余动画/交互 ----------
    @staticmethod
    def resource_path(rel):
        if getattr(sys, "frozen", False):
            return os.path.join(os.environ.get("RESOURCEPATH", ""), rel)
        return os.path.join(os.path.abspath("."), rel)

    def switch_movie(self, new_movie):
        if self.movie is new_movie:
            return
        self.movie.stop()
        self.movie = new_movie
        self.movie.start()

    def update_frame(self):
        frame = self.movie.currentImage()
        if frame.isNull():
            return
        if frame.width() > 4 and frame.height() > 4:
            frame = frame.copy(1, 1, frame.width() - 4, frame.height() - 4)
        pix = QPixmap.fromImage(frame.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.label.setPixmap(pix)

    def move_pet(self):
        x = self.x() + self.speed * self.direction
        if x + self.width() >= self.screen_rect.width() or x <= 0:
            self.direction *= -1
        self.move(x, self.base_y)

    def enterEvent(self, _):
        if self.menu_open or self.dragging:
            return
        self.timer.stop()
        self.switch_movie(self.movie_relax)

    def leaveEvent(self, _):
        if self.menu_open or self.dragging:
            return
        self.switch_movie(self.movie_main)
        self.timer.start(30)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_pos = e.globalPos() - self.pos()
            self.timer.stop()
            self.switch_movie(self.movie_relax)
            e.accept()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton and self.dragging:
            new_pos = e.globalPos() - self.drag_pos
            self.move(
                max(0, min(new_pos.x(), self.screen_rect.width() - self.width())),
                max(0, min(new_pos.y(), self.screen_rect.height() - self.height()))
            )
            e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self.base_y = self.y()
            if not self.rect().contains(self.mapFromGlobal(e.globalPos())):
                self.switch_movie(self.movie_main)
                self.timer.start(30)
            e.accept()


# ---------- 入口 ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec_())
