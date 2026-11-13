"""PyInstaller 桌面版入口。

打包命令（在项目根目录执行）：

    pyinstaller --noconfirm --clean --onefile --windowed \
        --name WebLinkCrawler \
        --collect-all ttkbootstrap \
        packaging/pyinstaller_desktop.py
"""

from weblinkcrawler.app import main

if __name__ == "__main__":
    main()
