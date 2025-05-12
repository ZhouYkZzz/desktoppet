import sys, os, json
import requests
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QLabel, QWidget,
                             QMenu, QMessageBox, QInputDialog)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QMovie, QPixmap

CONFIG_PATH = Path.home() / ".desktop_pet_config.json"

# ---------- 高德 API 端点 ----------
GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"

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
            # 1) 城市名 → adcode
            geo = requests.get(
                GEOCODE_URL,
                params={
                    "address": self.city,
                    "output": "JSON",
                    "key": self.api_key,
                },
                timeout=(5, 10),
            )
            geo.raise_for_status()
            gdata = geo.json()["geocodes"]
            if not gdata:
                raise ValueError(f"找不到城市“{self.city}”")
            adcode = gdata[0]["adcode"]

            # 2) 高德天气（实况+未来 3 天）
            w = requests.get(
                WEATHER_URL,
                params={
                    "city": adcode,
                    "extensions": "all",   # all = 预报 + 实况
                    "output": "JSON",
                    "key": self.api_key,
                },
                timeout=(5, 15),
            )
            w.raise_for_status()
            fcasts = w.json()["forecasts"][0]["casts"]
            today, tomorrow = fcasts[0], fcasts[1]
            self.finished.emit({"today": today, "tomorrow": tomorrow})

        except requests.ReadTimeout:
            self.error.emit("读取超时，网络可能暂时不稳定，请稍后再试~")
        except requests.ConnectTimeout:
            self.error.emit("连接超时，检查网络或代理设置")
        except requests.HTTPError as e:
            try:
                msg = e.response.json().get("info", "")
                self.error.emit(f"{e.response.status_code} {msg or str(e)}")
            except Exception:
                self.error.emit(str(e))
        except Exception as e:
            self.error.emit(str(e))


class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()

        # —— 窗口 & 透明 —— #
        self.setWindowFlags(Qt.FramelessWindowHint
                            | Qt.WindowStaysOnTopHint
                            | Qt.WindowDoesNotAcceptFocus
                            | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # —— Label & GIF —— #
        self.label = QLabel(self)
        self.label.setStyleSheet("background: transparent; border: none;")
        self.resize(100, 100)
        self.label.resize(100, 100)

        self.movie_main  = QMovie(self.resource_path("mostima.gif"))
        self.movie_relax = QMovie(self.resource_path("relax.gif"))
        self.movie_main.frameChanged.connect(self.update_frame)
        self.movie_relax.frameChanged.connect(self.update_frame)
        self.movie = self.movie_main
        self.movie.start()

        # —— 状态 —— #
        self.menu_open = False
        self.dragging  = False

        # —— 运动 —— #
        self.direction   = 1
        self.speed       = 1
        self.screen_rect = QApplication.primaryScreen().geometry()
        self.offset      = 50
        self.base_y      = self.screen_rect.height() - self.height() - self.offset
        self.move(100, self.base_y)

        self.timer = QTimer(self, timeout=self.move_pet)
        self.timer.start(30)

        # —— 城市 & 天气 —— #
        self.city     = self.load_city()
        self.w_thread = None
        self.fetch_weather()

    # ---------- 城市持久化 ----------
    def load_city(self) -> str:
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text())
                return data.get("city", "杭州")
            except Exception:
                pass
        return "杭州"

    def save_city(self):
        try:
            CONFIG_PATH.write_text(json.dumps({"city": self.city}))
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"无法保存城市：{e}")

    # ---------- 启动天气线程 ----------
    def fetch_weather(self):
        key = os.getenv("pet_weather_key")
        if not key:
            QMessageBox.warning(self, "天气提醒", "未设置环境变量 pet_weather_key")
            return

        if self.w_thread and self.w_thread.isRunning():
            self.w_thread.quit()
            self.w_thread.wait()

        self.w_thread = WeatherThread(key, self.city, self)
        self.w_thread.finished.connect(self.show_weather_popup)
        self.w_thread.error.connect(self.show_weather_error)
        self.w_thread.start()

    # ---------- 弹窗 ----------
    def show_weather_popup(self, payload):
        def fmt(day):
            main = day["dayweather"].lower()      # “小雨”
            desc = f'{day["dayweather"]}/{day["nightweather"]}'
            tmin = int(day["nighttemp"])
            tmax = int(day["daytemp"])
            return main, f"{desc} {tmin}°C ~ {tmax}°C"

        main_today, info_today = fmt(payload["today"])
        main_tom,   info_tom   = fmt(payload["tomorrow"])
        need_umbrella = any(k in (main_today, main_tom)
                            for k in ("雨", "雷"))

        msg =  (f"{self.city} 今天：{info_today}\n"
                f"{self.city} 明天：{info_tom}")
        if need_umbrella:
            msg += "\n\n🌧 记得带伞！"
        QMessageBox.information(self, "天气提醒", msg)

    def show_weather_error(self, err):
        QMessageBox.warning(self, "天气提醒",
                            f"城市：{self.city}\n天气信息获取失败：{err}")

    # ---------- 右键菜单 ----------
    def contextMenuEvent(self, e):
        self.menu_open = True
        was_running = self.timer.isActive()
        self.timer.stop()
        self.movie.setPaused(True)

        menu    = QMenu(self)
        loc_act = menu.addAction("位置…")
        quit_act= menu.addAction("退出")
        chosen  = menu.exec_(e.globalPos())

        if chosen == loc_act:
            self.change_city()
        elif chosen == quit_act:
            QApplication.quit()

        self.menu_open = False
        if was_running:
            self.timer.start(30)
        self.movie.setPaused(False)

    # ---------- 修改城市 ----------
    def change_city(self):
        text, ok = QInputDialog.getText(
            self, "设置位置", "请输入城市名（中文/拼音/英文皆可）：", text=self.city)
        if ok and text.strip():
            self.city = text.strip()
            self.save_city()
            self.fetch_weather()

    # ---------- 其余：动画 & 交互 ----------
    def resource_path(self, rel):
        if getattr(sys, 'frozen', False):
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
        pix = QPixmap.fromImage(
            frame.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
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
            new_x = max(0, min(new_pos.x(), self.screen_rect.width() - self.width()))
            new_y = max(0, min(new_pos.y(), self.screen_rect.height() - self.height()))
            self.move(new_x, new_y)
            e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self.base_y  = self.y()
            inside = self.rect().contains(self.mapFromGlobal(e.globalPos()))
            if not inside:
                self.switch_movie(self.movie_main)
                self.timer.start(30)
            e.accept()


# ---------- 入口 ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec_())
