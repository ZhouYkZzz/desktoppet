from setuptools import setup

APP = ['app.py']

# ① 两张 GIF 都要打进 Resources
DATA_FILES = ['mostima.gif', 'relax.gif']

OPTIONS = {
    'argv_emulation': False,
    'plist': {
        'CFBundleName': 'DesktopPet',
        'CFBundleShortVersionString': '1.0',
        'CFBundleVersion': '1.0',
        'CFBundleIdentifier': 'com.example.desktoppet',
        'LSUIElement': True,          # 菜单栏不显示图标
    },
    'packages': ['PyQt5'],            # PyQt5 已含 sip
    'includes': [                     # 显式列出用到的模块
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
    ],
    # ② imageformats = qgif / qjpeg / qico … → 显示 GIF 必备
    'qt_plugins': ['platforms', 'imageformats'],
}

setup(
    app=APP,
    data_files=DATA_FILES,            # 资源进 Resources/
    options={'py2app': OPTIONS},
    setup_requires=['py2app>=0.28'],  # 新版 py2app 兼容 PyQt5.15+
)
