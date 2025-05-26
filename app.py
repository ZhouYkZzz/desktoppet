#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Desktop-Pet with user-customisable themes (macOS).
"""
import sys, os, json, subprocess, shutil
from pathlib import Path
from datetime import datetime, timedelta
import requests
from typing import Optional, Dict, List

from PyQt5.QtWidgets import (
    QApplication, QLabel, QWidget, QMenu, QMessageBox,
    QInputDialog, QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QDateEdit, QTimeEdit, QLineEdit, QLabel as QtLabel,
    QFileDialog
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QDate, QTime
from PyQt5.QtGui import QMovie, QPixmap

# ----------------- 全局常量 -----------------
CONFIG_PATH  = Path.home() / ".desktop_pet_config.json"
THEMES_DIR   = Path.home() / ".desktop_pet_themes"        # 每个主题两张 GIF
THEMES_DIR.mkdir(exist_ok=True)
DEFAULT_THEME_NAME  = "主题一"
DEFAULT_CITY        = "杭州"
DEFAULT_MAIN_GIF    = "mostima.gif"   # 日常
DEFAULT_RELAX_GIF   = "relax.gif"     # 悬停

# ---------- 高德 API 端点 ----------
GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"

# ---------- 在此填入你的高德 Web API Key ----------
API_KEY = ""   # ← 换成自己的 Key
# ------------------------------------------------------

# ----------- 天气后台线程 -----------
class WeatherThread(QThread):
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(self, api_key: str, city: str, parent=None):
        super().__init__(parent)
        self.api_key = api_key
        self.city    = city

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

        today      = QDate.currentDate()
        next_hour  = (datetime.now() + timedelta(hours=1)).time().replace(second=0, microsecond=0)

        self.date_edit     = QDateEdit(today, self)
        self.date_edit.setCalendarPopup(True)

        self.time_edit     = QTimeEdit(QTime(next_hour.hour, next_hour.minute), self)
        self.time_edit.setDisplayFormat("HH:mm")

        self.duration_edit = QTimeEdit(QTime(1, 0), self)   # 默认 1 小时
        self.duration_edit.setDisplayFormat("HH:mm")

        self.title_edit    = QLineEdit(self)
        self.title_edit.setPlaceholderText("事件标题…")

        ok_btn     = QPushButton("创建", self)
        cancel_btn = QPushButton("取消", self)
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        vbox = QVBoxLayout(self)
        for lbl, w in [("选择日期：", self.date_edit),
                       ("选择时间：", self.time_edit),
                       ("持续时长：", self.duration_edit),
                       ("事件标题：", self.title_edit)]:
            vbox.addWidget(QtLabel(lbl))
            vbox.addWidget(w)

        hbtn = QHBoxLayout()
        hbtn.addStretch()
        hbtn.addWidget(ok_btn)
        hbtn.addWidget(cancel_btn)
        vbox.addLayout(hbtn)

    @staticmethod
    def get_event(parent=None):
        dlg = EventDialog(parent)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.date_edit.date().toPyDate()
            t = dlg.time_edit.time().toPyTime()
            start_dt = datetime.combine(d, t)

            dur_qt  = dlg.duration_edit.time()
            duration = timedelta(hours=dur_qt.hour(), minutes=dur_qt.minute())

            title = dlg.title_edit.text().strip() or "提醒"
            return start_dt, duration, title
        return None, None, None


# ----------- 桌面宠物 -----------
class DesktopPet(QWidget):

    # ---------- 配置文件处理 ----------
    def load_config(self) -> Dict:
        """读取/初始化配置文件，返回 dict 并写回硬盘"""
        cfg: Dict = {}
        if CONFIG_PATH.exists():
            try:
                cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}

        # 城市
        if "city" not in cfg:
            cfg["city"] = DEFAULT_CITY

        # 主题
        if "themes" not in cfg:
            cfg["themes"] = {}
        if DEFAULT_THEME_NAME not in cfg["themes"]:
            cfg["themes"][DEFAULT_THEME_NAME] = [
                self.resource_path(DEFAULT_MAIN_GIF),
                self.resource_path(DEFAULT_RELAX_GIF),
            ]

        # 当前主题
        if "current_theme" not in cfg:
            cfg["current_theme"] = DEFAULT_THEME_NAME

        # 保存（确保结构完整）
        self._write_config(cfg)
        return cfg

    def _write_config(self, cfg: Dict):
        try:
            CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"无法保存配置：{e}")

    # ---------- 构造函数 ----------
    def __init__(self):
        super().__init__()

        # —— 配置 —— #
        self.config        = self.load_config()
        self.city          = self.config["city"]
        self.themes: Dict[str, List[str]] = self.config["themes"]
        self.current_theme = self.config["current_theme"]

        # —— 窗口 & 透明 —— #
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
            Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # —— Label —— #
        self.label = QLabel(self)
        self.label.setStyleSheet("background: transparent; border: none;")
        self.resize(200, 200)
        self.label.resize(200, 200)

        # —— 动画 —— #
        self.movie_main  = None    # 会在 set_theme 中创建
        self.movie_relax = None
        self.movie       = None
        self.set_theme(self.current_theme)   # 初始主题

        # —— 状态 —— #
        self.menu_open = False
        self.dragging  = False

        # —— 运动 —— #
        self.direction    = 1
        self.speed        = 1
        self.screen_rect  = QApplication.primaryScreen().geometry()
        self.offset       = 10
        self.base_y       = self.screen_rect.height() - self.height() - self.offset
        self.move(100, self.base_y)

        self.timer = QTimer(self, timeout=self.move_pet)
        self.timer.start(30)

        # —— 城市 & 天气 —— #
        self.w_thread = None
        self.fetch_weather()

        # —— 天气信息控件 —— #
        self.weather_label = QLabel(self)
        self.weather_label.setAlignment(Qt.AlignCenter)
        self.weather_label.setStyleSheet("font-size: 12px; color: white; background: transparent;")
        self.weather_label.setGeometry(0, 20, self.width(), self.height())

        # —— 5秒后隐藏天气 —— #
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_label)

    # ---------- 资源路径 ----------
    @staticmethod
    def resource_path(rel):
        if getattr(sys, "frozen", False):
            return os.path.join(os.environ.get("RESOURCEPATH", ""), rel)
        return os.path.join(os.path.abspath("."), rel)

    # ---------- 主题相关 ----------
    def set_theme(self, theme_name: str):
        """根据 theme_name 切换主题"""
        if theme_name not in self.themes:
            QMessageBox.warning(self, "切换主题失败", f"找不到主题「{theme_name}」")
            return

        main_path, relax_path = self.themes[theme_name]

        # 停止旧动画
        if self.movie_main:  self.movie_main.stop()
        if self.movie_relax: self.movie_relax.stop()

        # 创建新动画
        self.movie_main  = QMovie(main_path)
        self.movie_relax = QMovie(relax_path)
        self.movie_main.frameChanged.connect(self.update_frame)
        self.movie_relax.frameChanged.connect(self.update_frame)

        # 切到主动画
        self.switch_movie(self.movie_main)

        # 更新状态
        self.current_theme           = theme_name
        self.config["current_theme"] = theme_name
        self._write_config(self.config)

    # ---------- 主题：新增 ----------
    def add_theme(self):
        """新增主题：先选『日常行走』再选『悬停静止』，完毕后确认顺序并命名"""
        QMessageBox.information(
            self, "新增主题向导",
            "将依次选择两张 GIF：\n1⃣  日常行走（主动画）\n2⃣  悬停静止（鼠标悬浮）"
        )

        main_path, _ = QFileDialog.getOpenFileName(
            self, "选择【日常行走】GIF", "", "GIF Files (*.gif)"
        )
        if not main_path:
            return

        relax_path, _ = QFileDialog.getOpenFileName(
            self, "选择【悬停静止】GIF", "", "GIF Files (*.gif)"
        )
        if not relax_path:
            return

        # —— 让用户确认顺序是否选对 —— #
        chk = QMessageBox.question(
            self, "确认 GIF 顺序",
            f"👉  日常行走：{Path(main_path).name}\n👉  悬停静止：{Path(relax_path).name}\n\n确认无误？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if chk != QMessageBox.Yes:
            return

        # —— 命名 —— #
        name, ok = QInputDialog.getText(self, "主题名称", "输入主题名称：")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self.themes:
            QMessageBox.warning(self, "新增主题", "该主题名称已存在！")
            return

        # —— 复制到私有目录 —— #
        dest_main  = THEMES_DIR / f"{name}_main.gif"
        dest_relax = THEMES_DIR / f"{name}_relax.gif"
        try:
            shutil.copy(main_path, dest_main)
            shutil.copy(relax_path, dest_relax)
        except Exception as e:
            QMessageBox.warning(self, "新增主题失败", f"复制文件失败：{e}")
            return

        # —— 更新内存 & 配置 —— #
        self.themes[name] = [str(dest_main), str(dest_relax)]
        self.config["themes"] = self.themes
        self._write_config(self.config)

        # —— 切换到新主题 —— #
        self.set_theme(name)
        QMessageBox.information(self, "新增主题", f"「{name}」已添加并启用")

    # ---------- 主题：删除 ----------
    def delete_current_theme(self):
        name = self.current_theme
        if name == DEFAULT_THEME_NAME:
            QMessageBox.information(self, "删除主题", "默认主题无法删除")
            return
        yes = QMessageBox.question(
            self, "删除确认",
            f"确定永久删除主题「{name}」？\n文件将移至系统废纸篓。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if yes != QMessageBox.Yes:
            return

        # —— 删除磁盘文件 —— #
        for p in self.themes.get(name, []):
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass

        # —— 从字典里移除并写配置 —— #
        self.themes.pop(name, None)
        self.config["themes"] = self.themes
        # 若删除的是当前主题才切回默认
        if self.current_theme == name:
            self.set_theme(DEFAULT_THEME_NAME)
        self._write_config(self.config)

        QMessageBox.information(self, "删除完成", f"主题「{name}」已删除")

    # ---------- 主题：重命名 ----------
    def rename_current_theme(self):
        old = self.current_theme
        if old == DEFAULT_THEME_NAME:
            QMessageBox.information(self, "重命名", "默认主题无法重命名")
            return
        new, ok = QInputDialog.getText(self, "重命名主题", "新的主题名称：", text=old)
        new = new.strip() if ok else ""
        if not new or new == old:
            return
        if new in self.themes:
            QMessageBox.warning(self, "重命名主题", "该名称已存在")
            return

        # 改文件名，保持磁盘整洁
        old_main, old_relax = map(Path, self.themes[old])
        new_main  = old_main.with_name(f"{new}_main.gif")
        new_relax = old_relax.with_name(f"{new}_relax.gif")
        try:
            old_main.rename(new_main)
            old_relax.rename(new_relax)
        except Exception:
            # 如果重命名失败就保留原文件名
            new_main, new_relax = old_main, old_relax

        self.themes[new] = [str(new_main), str(new_relax)]
        self.themes.pop(old)
        self.current_theme           = new
        self.config["themes"]        = self.themes
        self.config["current_theme"] = new
        self._write_config(self.config)
        QMessageBox.information(self, "重命名成功", f"已将主题「{old}」重命名为「{new}」")

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

        self.weather_label.setText(msg)
        self.weather_label.adjustSize()
        self.hide_timer.start(5000)

    def show_weather_error(self, err):
        self.weather_label.setText(f"获取天气信息失败：{err}")

    def hide_label(self):
        self.weather_label.setText("")
        self.weather_label.adjustSize()
        old_x, old_y = self.x(), self.y()
        self.resize(100, 200)
        self.label.resize(100, 200)
        self.move(old_x, old_y)

    # ---------- 右键菜单 ----------
    def contextMenuEvent(self, e):
        self.menu_open = True
        running = self.timer.isActive()
        self.timer.stop()
        if self.movie:
            self.movie.setPaused(True)

        menu      = QMenu(self)
        loc_act   = menu.addAction("位置…")
        theme_act = menu.addAction("更换主题…")
        sched_act = menu.addAction("新建日程…")
        quit_act  = menu.addAction("退出")
        chosen    = menu.exec_(e.globalPos())

        if chosen == loc_act:
            self.change_city()
        elif chosen == sched_act:
            self.create_calendar_event()
        elif chosen == theme_act:
            self.change_theme_dialog()
        elif chosen == quit_act:
            QApplication.quit()

        self.menu_open = False
        if running:
            self.timer.start(30)
        if self.movie:
            self.movie.setPaused(False)

    # ---------- 右键菜单里的主题对话框 ----------
    def change_theme_dialog(self):
        while True:
            items = list(self.themes.keys()) + [
                "——", "新增主题", "重命名当前主题", "删除当前主题", "取消"
            ]
            # 让 QInputDialog 默认选中当前主题
            cur_idx = items.index(self.current_theme) if self.current_theme in self.themes else 0
            choice, ok = QInputDialog.getItem(
                self, "更换主题", "选择操作：", items, current=cur_idx, editable=False
            )
            if not ok or choice == "取消" or not choice:
                return
            if choice == "新增主题":
                self.add_theme()
                continue
            if choice == "重命名当前主题":
                self.rename_current_theme()
                continue
            if choice == "删除当前主题":
                self.delete_current_theme()
                continue
            if choice == "——":
                continue
            # —— 切换主题 —— #
            self.set_theme(choice)
            return
    # ---------- 修改城市 ----------
    def change_city(self):
        text, ok = QInputDialog.getText(self, "设置位置", "请输入城市名：", text=self.city)
        if ok and text.strip():
            self.city = text.strip()
            self.config["city"] = self.city
            self._write_config(self.config)
            self.fetch_weather()

    # ---------- 新建日程 ----------
    def create_calendar_event(self):
        start_dt, duration, title = EventDialog.get_event(self)
        if not start_dt:
            return

        end_dt = start_dt + duration
        try:
            self._add_event_to_calendar(start_dt, end_dt, title, cal_name="个人")
            dh, dm = divmod(duration.seconds // 60, 60)
            QMessageBox.information(
                self, "已创建",
                f"已在 {start_dt.strftime('%m-%d %H:%M')} 创建「{title}」，持续 {dh}h{dm:02d}m"
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
        try_names = ["日历", "Calendar"] if cal_name is None else [cal_name]

        sy, sM, sd = start_dt.year,  start_dt.month,  start_dt.day
        sh, sm     = start_dt.hour,  start_dt.minute
        ey, eM, ed = end_dt.year,    end_dt.month,    end_dt.day
        eh, em     = end_dt.hour,    end_dt.minute

        success, last_err = False, ""
        for name in try_names:
            applescript_code = f'''
            try
                tell application "Calendar"
                    tell calendar "{name}"
                        set eventStart to (current date)
                        set year of eventStart   to {sy}
                        set month of eventStart  to {sM}
                        set day of eventStart    to {sd}
                        set hours of eventStart  to {sh}
                        set minutes of eventStart to {sm}
                        set seconds of eventStart to 0
                        set eventEnd to (current date)
                        set year of eventEnd   to {ey}
                        set month of eventEnd  to {eM}
                        set day of eventEnd    to {ed}
                        set hours of eventEnd  to {eh}
                        set minutes of eventEnd to {em}
                        set seconds of eventEnd to 0
                        make new event with properties {{summary:"{title}", start date:eventStart, end date:eventEnd, description:"{notes}"}}
                        return ""
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
    def switch_movie(self, new_movie: QMovie):
        if self.movie is new_movie:
            return
        if self.movie:
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
                max(0, min(new_pos.x(), self.screen_rect.width()  - self.width())),
                max(0, min(new_pos.y(), self.screen_rect.height() - self.height()))
            )
            e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self.base_y   = self.y()
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
