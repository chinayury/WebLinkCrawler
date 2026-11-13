# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later
"""生成 PyInstaller Windows 版本资源文件。

从 ``weblinkcrawler.APP_VERSION`` / ``APP_VENDOR`` / ``APP_COPYRIGHT`` 等常量生成
``packaging/version_info.txt``，供 PyInstaller ``--version-file`` 使用。版本号只
维护在包元数据中，本文件不保存版本号，避免多处漂移。

用法（项目根目录）：

    python packaging/make_version_info.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import weblinkcrawler as w  # noqa: E402


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    """把 ``0.1.0`` 之类的版本号转成 4 段整数元组。"""
    parts: list[int] = []
    for chunk in version.split(".")[:4]:
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    padded = (parts + [0, 0, 0, 0])[:4]
    return padded[0], padded[1], padded[2], padded[3]


def _quote(value: str) -> str:
    """转义为 version_info 文件中的单引号字符串字面量。"""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def build_version_info() -> str:
    """按包常量生成 PyInstaller 版本资源文本。"""
    filevers = _version_tuple(w.APP_VERSION)
    version_text = ".".join(str(n) for n in filevers)
    fields = [
        ("CompanyName", w.APP_VENDOR),
        ("FileDescription", w.APP_NAME),
        ("FileVersion", version_text),
        ("InternalName", w.APP_NAME_EN),
        ("LegalCopyright", w.APP_COPYRIGHT),
        ("OriginalFilename", f"{w.APP_NAME_EN}.exe"),
        ("ProductName", w.APP_NAME),
        ("ProductVersion", version_text),
    ]
    strings = ",\n".join(
        f"            StringStruct({_quote(key)}, {_quote(value)})"
        for key, value in fields
    )
    return f"""# 由 packaging/make_version_info.py 生成，请勿手动编辑。
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={filevers},
    prodvers={filevers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404b0',
        [
{strings}
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


def main() -> None:
    out = ROOT / "packaging" / "version_info.txt"
    out.write_text(build_version_info(), encoding="utf-8", newline="\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
