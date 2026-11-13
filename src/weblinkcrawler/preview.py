"""WebLinkCrawler独立网页预览进程（PyQt5 + QtWebEngine）。

本模块刻意与 Tk主程序分进程运行，避免 Tk与 Qt两套事件循环互相干扰：

    python preview.py --url URL --result PATH

窗口功能：
-刷新页面；
-「选择元素」（快捷键 Ctrl+Shift+C）：注入本模块内置的 JavaScript，拦截下一次
点击并计算稳定的 CSS选择器（唯一 id优先，否则 tag:nth-of-type路径，最多6层）；
-「打开 DevTools」（F12，若当前 Qt构建支持）；
-状态标签。

结果约定：
-用户确认后把 {"css_selector": "...", "url": "..."}原子写入 --result，退出0；
-在确认框中取消则继续选择；
-直接关闭窗口而未选择时写入 {"css_selector": "", "cancelled": true}，退出0；
-缺少 PyQt5 / QtWebEngine时向 stderr输出 QT_UNAVAILABLE并以2退出。

约束：只用标准库与 PyQt5/QtWebEngine，不引入新依赖；只执行本模块内置的固定
JavaScript常量，绝不 eval页面返回的任意字符串。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

EXIT_OK =0
EXIT_QT_UNAVAILABLE =2

#选择模式注入脚本：监听器只安装一次，重复进入选择模式仅重置状态。
_SELECT_JS = r"""
(function () {
    function cssEscape(value) {
        var text = String(value == null ? "" : value);
        if (window.CSS && typeof window.CSS.escape === "function") {
            return window.CSS.escape(text);
        }
        return text.replace(/[^a-zA-Z0-9_\u00a0-\uffff-]/g, function (ch) {
            return "\\" + ch;
        });
    }

    function isUnique(selector, element) {
        try {
            var found = document.querySelectorAll(selector);
            return found.length ===1 && found[0] === element;
        } catch (err) {
            return false;
        }
    }

    function buildPath(element) {
        var parts = [];
        var node = element;
        var depth =0;
        while (node && node.nodeType ===1 && depth <6) {
            var tag = node.tagName ? node.tagName.toLowerCase() : "";
            if (!tag) {
                break;
            }
            if (node.id) {
                var idSelector = "#" + cssEscape(node.id);
                if (isUnique(idSelector, node)) {
                    parts.unshift(idSelector);
                    return parts.join(" > ");
                }
            }
            var index =1;
            var sibling = node;
            while (sibling && (sibling = sibling.previousElementSibling)) {
                if (sibling.tagName === node.tagName) {
                    index +=1;
                }
            }
            parts.unshift(tag + ":nth-of-type(" + index + ")");
            node = node.parentElement;
            depth +=1;
        }
        return parts.join(" > ");
    }

    function onClick(event) {
        if (!window.__wlcArmed) {
            return;
        }
        window.__wlcArmed = false;
        try {
            event.preventDefault();
            event.stopPropagation();
            if (event.stopImmediatePropagation) {
                event.stopImmediatePropagation();
            }
        } catch (err) {}
        var element = event.target;
        if (!element || element.nodeType !==1) {
            element = document.documentElement;
        }
        var selector = buildPath(element);
        var text = String(element.innerText || element.textContent || "")
            .replace(/\s+/g, " ")
            .trim();
        if (text.length >80) {
            text = text.slice(0,80) + "…";
        }
        try {
            if (document.body) {
                document.body.style.cursor = window.__wlcPrevCursor || "";
            }
        } catch (err) {}
        try {
            element.style.outline = "2px solid #2A5BD7";
            setTimeout(function () {
                try {
                    element.style.outline = "";
                } catch (err) {}
            },800);
        } catch (err) {}
        window.__wlcPick = {
            selector: selector,
            tag: element.tagName ? element.tagName.toLowerCase() : "",
            id: element.id || "",
            classes: (element.className && typeof element.className === "string")
                ? element.className : "",
            text: text,
            url: location.href
        };
        return false;
    }

    function onMouseDown(event) {
        if (!window.__wlcArmed) {
            return;
        }
        try {
            event.preventDefault();
            event.stopPropagation();
        } catch (err) {}
    }

    if (!window.__wlcHandlersInstalled) {
        document.addEventListener("click", onClick, true);
        document.addEventListener("mousedown", onMouseDown, true);
        window.__wlcHandlersInstalled = true;
    }
    window.__wlcPick = null;
    window.__wlcArmed = true;
    try {
        if (document.body) {
            window.__wlcPrevCursor = document.body.style.cursor || "";
            document.body.style.cursor = "crosshair";
        }
    } catch (err) {}
    return "armed";
})();
"""

#读取选择结果：只读取注入脚本设置的窗口变量。
_PICK_JS = "window.__wlcPick ? JSON.stringify(window.__wlcPick) : ''"


def _write_result(result_path, payload): # indent-probe
    """把结果原子写入目标路径（同目录临时文件 + os.replace，utf-8）。"""
    target = os.path.abspath(result_path)
    directory = os.path.dirname(target) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".wlc_preview_", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ----可选依赖：缺失时只置标记，交给 main()输出 QT_UNAVAILABLE --------------
try: # pragma: no cover -依赖可选
    from PyQt5.QtCore import QTimer, QUrl # noqa: F401
    from PyQt5.QtGui import QKeySequence # noqa: F401
    from PyQt5.QtWidgets import ( # noqa: F401
        QApplication,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QPushButton,
        QShortcut,
        QVBoxLayout,
        QWidget,
    )
    from PyQt5.QtWebEngineWidgets import QWebEngineView # noqa: F401

    QT_AVAILABLE = True
except Exception: # ImportError / DLL加载失败等
    QT_AVAILABLE = False


if QT_AVAILABLE: # pragma: no cover -需要 PyQt5 + QtWebEngine +图形界面

    class PreviewWindow(QWidget):
        """预览窗口：刷新、选择元素、DevTools与结果回写。"""

        def __init__(self, url, result_path):
            super().__init__()
            self._url = url
            self._result_path = result_path
            self._finished = False
            self._selecting = False
            self._devtools = None

            self.setWindowTitle("网页预览 -选择页面元素")
            self.resize(1200,820)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(8,8,8,8)
            layout.setSpacing(6)

            toolbar = QHBoxLayout()
            self._reload_button = QPushButton("刷新", self)
            self._reload_button.clicked.connect(self._reload)
            toolbar.addWidget(self._reload_button)

            self._select_button = QPushButton("选择元素 (Ctrl+Shift+C)", self)
            self._select_button.clicked.connect(self._start_selection)
            toolbar.addWidget(self._select_button)

            self._devtools_button = QPushButton("DevTools (F12)", self)
            self._devtools_button.clicked.connect(self._toggle_devtools)
            toolbar.addWidget(self._devtools_button)

            toolbar.addStretch(1)
            self._status = QLabel("正在加载页面…", self)
            toolbar.addWidget(self._status)
            layout.addLayout(toolbar)

            self._view = QWebEngineView(self)
            layout.addWidget(self._view,1)
            self._view.loadFinished.connect(self._on_load_finished)
            self._view.setUrl(QUrl(self._url))

            self._timer = QTimer(self)
            self._timer.setInterval(250)
            self._timer.timeout.connect(self._poll_pick)

            #快捷键对象必须保留引用，避免被 Python回收
            self._shortcut_select = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
            self._shortcut_select.activated.connect(self._start_selection)
            self._shortcut_devtools = QShortcut(QKeySequence("F12"), self)
            self._shortcut_devtools.activated.connect(self._toggle_devtools)

        # ----工具栏动作 ----
        def _reload(self):
            try:
                self._view.reload()
                self._status.setText("正在刷新页面…")
            except Exception as exc:
                self._status.setText(f"刷新失败: {exc}")

        def _toggle_devtools(self):
            try:
                if self._devtools is None:
                    self._devtools = QWebEngineView()
                    self._devtools.setWindowTitle("DevTools")
                    self._devtools.resize(1000,700)
                    try:
                        self._devtools.page().setInspectedPage(self._view.page())
                    except Exception:
                        self._view.page().setDevToolsPage(self._devtools.page())
                self._devtools.show()
                self._devtools.raise_()
                self._status.setText("DevTools已打开")
            except Exception as exc:
                self._status.setText(f"DevTools不可用: {exc}")

        def _on_load_finished(self, ok):
            if ok:
                self._status.setText("页面已加载，可点击「选择元素」")
                if self._selecting:
                    #页面跳转后 JS上下文被重置，需要重新注入
                    try:
                        self._view.page().runJavaScript(_SELECT_JS)
                        self._timer.start()
                    except Exception:
                        pass
            else:
                self._status.setText("页面加载失败，请检查 URL或网络")

        # ----元素选择 ----
        def _start_selection(self):
            try:
                self._selecting = True
                self._view.page().runJavaScript(_SELECT_JS)
                self._timer.start()
                self._status.setText("选择模式：请在页面中点击目标元素")
            except Exception as exc:
                self._selecting = False
                self._status.setText(f"无法进入选择模式: {exc}")

        def _poll_pick(self):
            if not self._selecting:
                return
            try:
                self._view.page().runJavaScript(_PICK_JS, self._on_pick_result)
            except Exception:
                pass

        def _on_pick_result(self, result):
            if not self._selecting or not result:
                return
            try:
                info = json.loads(result) if isinstance(result, str) else None
            except Exception:
                info = None
            if not isinstance(info, dict):
                return
            selector = str(info.get("selector") or "").strip()
            if not selector:
                self._selecting = False
                self._timer.stop()
                self._status.setText("未能生成 CSS选择器，请重试")
                return

            self._selecting = False
            self._timer.stop()
            tag = str(info.get("tag") or "").strip()
            label = f"标签: {tag or '未知'}\n选择器: {selector}"
            if len(label) >400:
                label = label[:400] + "…"
            answer = QMessageBox.question(
                self,
                "确认 CSS选择器",
                f"{label}\n\n是否使用该选择器抓取链接？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Yes:
                self._accept_selection(selector)
            else:
                self._status.setText("已取消，继续点击页面元素即可重新选择")
                self._start_selection()

        def _accept_selection(self, selector):
            try:
                _write_result(self._result_path, {"css_selector": selector, "url": self._url})
            except Exception as exc:
                self._status.setText(f"写入结果失败: {exc}")
                print(f"RESULT_WRITE_FAILED: {exc}", file=sys.stderr)
                return
            self._finished = True
            self._status.setText(f"已选择: {selector[:80]}")
            self.close()
            app = QApplication.instance()
            if app is not None:
                QTimer.singleShot(0, app.quit)

        # ----关闭 ----
        def closeEvent(self, event):
            try:
                self._timer.stop()
            except Exception:
                pass
            if not self._finished:
                self._finished = True
                try:
                    _write_result(
                        self._result_path,
                        {"css_selector": "", "cancelled": True},
                    )
                except Exception as exc:
                    print(f"RESULT_WRITE_FAILED: {exc}", file=sys.stderr)
            try:
                super().closeEvent(event)
            except Exception:
                pass
            app = QApplication.instance()
            if app is not None:
                QTimer.singleShot(0, app.quit)

else: # pragma: no cover -缺少 PyQt5时的占位
    PreviewWindow = None


def run_preview(url, result_path):
    """创建并运行预览窗口；成功返回 EXIT_OK。"""
    if not QT_AVAILABLE:
        print("QT_UNAVAILABLE", file=sys.stderr)
        return EXIT_QT_UNAVAILABLE
    try:
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv[:1])
        window = PreviewWindow(url, result_path)
        window.show()
        app.exec_()
        return EXIT_OK
    except Exception as exc:
        print("QT_UNAVAILABLE", file=sys.stderr)
        print(f"QT_INIT_FAILED: {exc}", file=sys.stderr)
        return EXIT_QT_UNAVAILABLE


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="WebLinkCrawler网页预览选元素（独立进程）",
    )
    parser.add_argument("--url", required=True, help="要预览的网页 URL")
    parser.add_argument("--result", required=True, help="选择结果 JSON的输出路径")
    args = parser.parse_args(argv)
    return run_preview(args.url, args.result)


if __name__ == "__main__":
    sys.exit(main())
