# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""支持 ``python -m weblinkcrawler`` 启动入口。

与 console script ``weblinkcrawler`` 等价，共用 ``weblinkcrawler.cli:main``：
无参数启动 GUI，``--version`` / ``-h`` 应答版本与帮助。main() 的返回值
作为进程退出码上抛。配置与数据库按当前工作目录读写，建议从项目根目录
启动，以保持配置和数据库位置稳定。
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
