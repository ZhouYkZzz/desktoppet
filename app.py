import sys
from PyQt5.QtWidgets import QApplication, QLabel, QWidget
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QMovie, QPixmap

class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()

        # 设置窗口标志：无边框、始终顶层、不接受焦点；去除可能的投影
        self.setWindowFlags(Qt.FramelessWindowHint 
                            | Qt.WindowStaysOnTopHint
                            | Qt.WindowDoesNotAcceptFocus
                            | Qt.NoDropShadowWindowHint)
        # 设置透明背景
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # 准备一个 QLabel 来显示裁剪/缩放后的帧
        self.label = QLabel(self)
        self.label.setStyleSheet("background: transparent; border: none;")

        # 不直接 self.label.setMovie()，而是由我们手动更新帧
        self.movie = QMovie("mostima.gif")
        # 连接帧更新信号
        self.movie.frameChanged.connect(self.update_frame)
        self.movie.start()

        # 初始大小（与裁剪+缩放后的大小一致），假设最终想显示 100×100
        self.resize(100, 100)
        self.label.resize(100, 100)

        # 方向与速度
        self.direction = 1  # 1 向右，-1 向左
        self.speed = 1

        # 获取屏幕大小
        self.screen_rect = QApplication.primaryScreen().geometry()

        # 定义向上的偏移量，避免被底部栏或Dock挡住
        self.offset = 50
        self.move(100, self.screen_rect.height() - self.height() - self.offset)

        # 定时器移动
        self.timer = QTimer()
        self.timer.timeout.connect(self.move_pet)
        self.timer.start(30)

    def update_frame(self):
        """
        获取当前帧，裁剪外围 1 像素，再缩放到 (100×100)，然后赋给 label
        你可以根据需要调整裁剪和缩放方式。
        """
        frame = self.movie.currentImage()  # QImage
        if frame.isNull():
            return  # 当前帧可能无效，直接返回

        # 假设我们要去掉外面 1 像素的区域
        # 先确保宽高 > 2，再做 copy
        if frame.width() > 2 and frame.height() > 2:
            cropped = frame.copy(1, 1, frame.width() - 4, frame.height() - 4)
        else:
            # 无法安全裁剪时，就用原图
            cropped = frame

        # 进一步缩放到 100×100（保持比例或强制填满都可以）
        scaled = cropped.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        # 将处理后的帧设置到 label
        pixmap = QPixmap.fromImage(scaled)
        self.label.setPixmap(pixmap)

    def move_pet(self):
        current_pos = self.pos()
        new_x = current_pos.x() + self.speed * self.direction

        # 到达屏幕边缘时反向
        if new_x + self.width() >= self.screen_rect.width() or new_x <= 0:
            self.direction *= -1

        # 始终在屏幕底部（减去 offset）
        self.move(new_x, self.screen_rect.height() - self.height() - self.offset)

    def enterEvent(self, event):
        # 鼠标进入宠物区域，停止移动，并暂停动画
        self.timer.stop()
        self.movie.setPaused(True)

    def leaveEvent(self, event):
        # 鼠标离开宠物区域，继续移动，并恢复动画
        self.timer.start(30)
        self.movie.setPaused(False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec_())
