import sys, os
from PyQt5.QtWidgets import QApplication, QLabel, QWidget, QMenu, QAction
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QMovie, QPixmap

class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(Qt.FramelessWindowHint 
                            | Qt.WindowStaysOnTopHint
                            | Qt.WindowDoesNotAcceptFocus
                            | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.label = QLabel(self)
        self.label.setStyleSheet("background: transparent; border: none;")

        gif_path = self.resource_path("mostima.gif")
        self.movie = QMovie(gif_path)
        self.movie.frameChanged.connect(self.update_frame)
        self.movie.start()

        self.resize(100, 100)
        self.label.resize(100, 100)

        self.direction = 1
        self.speed = 1

        self.screen_rect = QApplication.primaryScreen().geometry()
        self.offset = 50
        self.move(100, self.screen_rect.height() - self.height() - self.offset)

        self.timer = QTimer()
        self.timer.timeout.connect(self.move_pet)
        self.timer.start(30)

    def resource_path(self, relative_path):
        if getattr(sys, 'frozen', False):
            base_path = os.path.join(os.environ.get("RESOURCEPATH", ""), "")
        else:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def update_frame(self):
        frame = self.movie.currentImage()
        if frame.isNull():
            return
        if frame.width() > 2 and frame.height() > 2:
            cropped = frame.copy(1, 1, frame.width() - 4, frame.height() - 4)
        else:
            cropped = frame
        scaled = cropped.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pixmap = QPixmap.fromImage(scaled)
        self.label.setPixmap(pixmap)

    def move_pet(self):
        current_pos = self.pos()
        new_x = current_pos.x() + self.speed * self.direction
        if new_x + self.width() >= self.screen_rect.width() or new_x <= 0:
            self.direction *= -1
        self.move(new_x, self.screen_rect.height() - self.height() - self.offset)

    def enterEvent(self, event):
        self.timer.stop()
        self.movie.setPaused(True)

    def leaveEvent(self, event):
        self.timer.start(30)
        self.movie.setPaused(False)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        menu.exec_(event.globalPos())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec_())
