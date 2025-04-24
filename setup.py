from setuptools import setup

APP = ['app.py']
DATA_FILES = ['mostima.gif']  # 确保这里包含了GIF文件
OPTIONS = {
    'argv_emulation': False,  # 确认关闭
    'plist': {
        'CFBundleName': 'DesktopPet',
        'CFBundleShortVersionString': '1.0',
        'CFBundleVersion': '1.0',
        'CFBundleIdentifier': 'com.example.desktoppet',
        'LSUIElement': True,
    },
    'packages': ['PyQt5'],
    'includes': ['PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'PyQt5.sip'],
    'qt_plugins': ['platforms'],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
