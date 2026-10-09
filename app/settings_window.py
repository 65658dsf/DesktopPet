"""Settings panel: AI access, pet appearance, behaviour, about."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
                               QScrollArea, QSlider, QSpinBox, QTabWidget, QTextEdit,
                               QVBoxLayout, QWidget)

from ai.client import test_connection
from config import data_dir
from petpack import STATE_ROWS, STATE_FRAMES

DARK = "#141013"
CARD = "#1e181c"
ACCENT = "#c2444f"
TEXT = "#f2e7ea"
MUTED = "#a08e95"

PRESETS = [
    ("OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    ("DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
    ("Moonshot", "https://api.moonshot.cn/v1", "moonshot-v1-8k"),
    ("Ollama 本地", "http://localhost:11434/v1", "qwen2.5:7b"),
]

STATE_LABELS = {
    "auto": "自动（待机 + 随机小动作）",
    "idle": "待机 idle",
    "running-right": "右移 running-right",
    "running-left": "左移 running-left",
    "waving": "挥手 waving",
    "jumping": "跳跃 jumping",
    "failed": "故障 failed",
    "waiting": "等待 waiting",
    "running": "忙碌 running",
    "review": "查看 review",
}


class _Tester(QObject):
    result = Signal(bool, str)

    def start(self, cfg: dict) -> None:
        threading.Thread(target=self._run, args=(cfg,), daemon=True).start()

    def _run(self, cfg: dict) -> None:
        ok, message = test_connection(cfg)
        self.result.emit(ok, message)


class SettingsWindow(QWidget):
    apply_requested = Signal(dict)
    open_folder_requested = Signal()
    reset_position_requested = Signal()
    state_preview_requested = Signal(str)

    def __init__(self, config, packages) -> None:
        super().__init__(None)
        self.setWindowTitle("秦彻 · 设置")
        self.resize(620, 720)
        self.config = config
        self.packages = packages
        self.setStyleSheet(f"""
            QWidget {{ background: {DARK}; color: {TEXT}; font-size: 12px; }}
            QTabWidget::pane {{ border: 1px solid #33262c; border-radius: 8px; }}
            QTabBar::tab {{ background: #1c161a; color: {MUTED}; padding: 8px 18px;
                            border-top-left-radius: 8px; border-top-right-radius: 8px; }}
            QTabBar::tab:selected {{ background: {CARD}; color: {TEXT}; }}
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {{
                background: {CARD}; border: 1px solid #43313a; border-radius: 8px;
                padding: 5px 8px; color: {TEXT}; }}
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border-color: {ACCENT}; }}
            QPushButton {{ background: #2a2228; border: 1px solid #43313a; border-radius: 8px;
                           padding: 6px 14px; color: {TEXT}; }}
            QPushButton:hover {{ border-color: {ACCENT}; background: #35282f; }}
            QCheckBox::indicator {{ width: 15px; height: 15px; border-radius: 4px;
                                    border: 1px solid #5a4048; background: {CARD}; }}
            QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
            QSlider::groove:horizontal {{ height: 5px; background: #3a2a31; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {ACCENT}; width: 13px; margin: -5px 0;
                                          border-radius: 6px; }}
            QLabel {{ background: transparent; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        tabs = QTabWidget()
        tabs.addTab(self._build_ai_tab(), "AI 接入")
        tabs.addTab(self._build_look_tab(), "桌宠外观")
        tabs.addTab(self._build_behaviour_tab(), "行为")
        tabs.addTab(self._build_about_tab(), "关于")
        root.addWidget(tabs, 1)

        footer = QHBoxLayout()
        self.hint = QLabel("")
        self.hint.setStyleSheet(f"color: {MUTED};")
        footer.addWidget(self.hint, 1)
        save = QPushButton("保存并应用")
        save.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: #1a1114; border: none;"
            "border-radius: 8px; padding: 8px 22px; font-weight: bold; }}"
            "QPushButton:hover { background: #d5545f; }")
        save.clicked.connect(self._apply)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.hide)
        footer.addWidget(close_button)
        footer.addWidget(save)
        root.addLayout(footer)

        self.reload()

    # ------------------------------------------------------------------ #
    def _build_ai_tab(self) -> QWidget:
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet("QScrollArea { border: none; }")
        host = QWidget()
        page.setWidget(host)
        layout = QVBoxLayout(host)
        layout.setSpacing(10)

        self.radio_local = QRadioButton("本地离线模式（内置回复，完全不联网）")
        self.radio_online = QRadioButton("在线 AI（OpenAI 兼容接口 / 本地大模型服务）")
        layout.addWidget(self.radio_local)
        layout.addWidget(self.radio_online)

        presets = QHBoxLayout()
        presets.addWidget(QLabel("快速预设："))
        for name, url, model in PRESETS:
            button = QPushButton(name)
            button.clicked.connect(lambda _=False, u=url, m=model: self._set_preset(u, m))
            presets.addWidget(button)
        presets.addStretch(1)
        layout.addLayout(presets)

        form = QFormLayout()
        form.setSpacing(8)
        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("https://api.openai.com/v1")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("sk-...（本地模型可留空）")
        key_row = QHBoxLayout()
        key_row.addWidget(self.api_key, 1)
        show_key = QCheckBox("显示")
        show_key.toggled.connect(lambda on: self.api_key.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        key_row.addWidget(show_key)
        key_host = QWidget()
        key_host.setLayout(key_row)

        self.model = QLineEdit()
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(16, 8192)
        self.max_tokens.setSingleStep(64)
        self.stream = QCheckBox("流式输出（逐字显示）")

        form.addRow("接口地址", self.base_url)
        form.addRow("API Key", key_host)
        form.addRow("模型", self.model)
        form.addRow("温度", self.temperature)
        form.addRow("最大回复 tokens", self.max_tokens)
        form.addRow("", self.stream)
        layout.addLayout(form)

        layout.addWidget(QLabel("角色人设（system prompt）"))
        self.system_prompt = QTextEdit()
        self.system_prompt.setMinimumHeight(180)
        self.system_prompt.setFont(QFont("Microsoft YaHei UI", 10))
        layout.addWidget(self.system_prompt)

        test_row = QHBoxLayout()
        self.test_button = QPushButton("测试连接")
        self.test_button.clicked.connect(self._test)
        self.test_result = QLabel("")
        self.test_result.setWordWrap(True)
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.test_result, 1)
        layout.addLayout(test_row)
        layout.addStretch(1)

        self._tester = _Tester()
        self._tester.result.connect(self._on_test_result)
        return page

    def _build_look_tab(self) -> QWidget:
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        self.package_box = QComboBox()
        for package in self.packages:
            self.package_box.addItem(f"{package.display_name}（{package.id}）", package.id)
        form.addRow("宠物包", self.package_box)

        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(60, 400)
        self.scale_label = QLabel("100%")
        size_row = QHBoxLayout()
        size_row.addWidget(self.scale_slider, 1)
        size_row.addWidget(self.scale_label)
        size_host = QWidget()
        size_host.setLayout(size_row)
        form.addRow("显示尺寸", size_host)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(96, 768)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(104, 832)
        self.keep_ratio = QCheckBox("保持比例（192:208）")
        wh_row = QHBoxLayout()
        wh_row.addWidget(QLabel("宽"))
        wh_row.addWidget(self.width_spin)
        wh_row.addWidget(QLabel("高"))
        wh_row.addWidget(self.height_spin)
        wh_row.addWidget(self.keep_ratio)
        wh_row.addStretch(1)
        wh_host = QWidget()
        wh_host.setLayout(wh_row)
        form.addRow("像素尺寸", wh_host)

        self.pixelated = QCheckBox("像素化渲染（image-rendering: pixelated）")
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(50, 200)
        self.speed_label = QLabel("1.00x")
        speed_row = QHBoxLayout()
        speed_row.addWidget(self.speed_slider, 1)
        speed_row.addWidget(self.speed_label)
        speed_host = QWidget()
        speed_host.setLayout(speed_row)
        self.reduced_motion = QCheckBox("减弱动效（停用循环动画）")
        form.addRow("动画速度", speed_host)
        form.addRow("", self.pixelated)
        form.addRow("", self.reduced_motion)
        layout.addLayout(form)

        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel("手动状态："))
        self.state_box = QComboBox()
        for key, label in STATE_LABELS.items():
            self.state_box.addItem(label, key)
        preview_row.addWidget(self.state_box, 1)
        preview_button = QPushButton("立即预览")
        preview_button.clicked.connect(
            lambda: self.state_preview_requested.emit(self.state_box.currentData()))
        preview_row.addWidget(preview_button)
        layout.addLayout(preview_row)
        layout.addStretch(1)

        self.scale_slider.valueChanged.connect(self._on_scale_changed)
        self.width_spin.valueChanged.connect(self._on_width_changed)
        self.height_spin.valueChanged.connect(self._on_height_changed)
        return host

    def _build_behaviour_tab(self) -> QWidget:
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setSpacing(9)
        self.always_on_top = QCheckBox("窗口总在最前")
        self.drag_enabled = QCheckBox("允许拖拽移动")
        self.locked = QCheckBox("锁定位置（禁止拖动）")
        self.click_through = QCheckBox("忽略鼠标（点击穿透到桌面）")
        self.idle_variety = QCheckBox("待机时随机做点小动作")
        self.autostart = QCheckBox("开机自动启动")
        self.show_on_startup = QCheckBox("启动后显示桌宠")
        for box in (self.always_on_top, self.drag_enabled, self.locked, self.click_through,
                    self.idle_variety, self.autostart, self.show_on_startup):
            layout.addWidget(box)

        buttons = QHBoxLayout()
        reset = QPushButton("桌宠回到右下角")
        reset.clicked.connect(self.reset_position_requested.emit)
        folder = QPushButton("打开配置目录")
        folder.clicked.connect(self.open_folder_requested.emit)
        buttons.addWidget(reset)
        buttons.addWidget(folder)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)
        return host

    def _build_about_tab(self) -> QWidget:
        host = QWidget()
        layout = QVBoxLayout(host)
        text = QLabel(
            "秦彻 · 桌面宠物  v1.0\n\n"
            "• 宠物包：Desktop Pet Launcher 契约兼容（8 列 × 9 行图集，192×208 单元格，"
            "1x / 2x / 4x 三档）\n"
            "• 离线运行：全部核心功能（动画、交互、托盘、设置、内置回复）不依赖网络\n"
            "• AI 交互：可接入任意 OpenAI 兼容接口（含 Ollama 等本地模型服务）\n"
            "• 扫描目录：%USERPROFILE%\\.codex\\pets、%APPDATA%\\top.nether.pet\\pets、程序目录 pets\n\n"
            "交互：单击有反应 · 双击打开对话 · 拖拽移动（按方向切换动画）· 右键菜单\n\n"
            "素材：基于用户提供的秦彻 Q 版立绘进行抠图与程序化动画合成，"
            "为同人二次创作，仅供个人欣赏使用。角色版权归《恋与深空》权利方所有。")
        text.setWordWrap(True)
        text.setStyleSheet(f"color: {MUTED}; line-height: 20px;")
        layout.addWidget(text)
        layout.addStretch(1)
        return host

    # ------------------------------------------------------------------ #
    def _set_preset(self, url: str, model: str) -> None:
        self.base_url.setText(url)
        self.model.setText(model)
        self.radio_online.setChecked(True)

    def reload(self) -> None:
        ai = self.config.ai
        online = ai.get("mode") == "online"
        self.radio_online.setChecked(online)
        self.radio_local.setChecked(not online)
        self.base_url.setText(str(ai.get("baseUrl", "")))
        self.api_key.setText(str(ai.get("apiKey", "")))
        self.model.setText(str(ai.get("model", "")))
        self.temperature.setValue(float(ai.get("temperature", 0.8)))
        self.max_tokens.setValue(int(ai.get("maxTokens", 512)))
        self.stream.setChecked(bool(ai.get("stream", True)))
        self.system_prompt.setPlainText(str(ai.get("systemPrompt", "")))

        active = str(self.config.get("activePetId", ""))
        index = self.package_box.findData(active)
        self.package_box.setCurrentIndex(index if index >= 0 else 0)

        width = int(self.config.get("width", 192))
        percent = max(60, min(400, round(width / 192 * 100)))
        self.scale_slider.setValue(percent)
        self.scale_label.setText(f"{percent}%")
        self.width_spin.setValue(width)
        self.height_spin.setValue(int(self.config.get("height", 208)))
        self.keep_ratio.setChecked(bool(self.config.get("keepAspectRatio", True)))
        self.pixelated.setChecked(bool(self.config.get("pixelated", False)))
        speed = float(self.config.get("animationSpeed", 1.0))
        self.speed_slider.setValue(int(speed * 100))
        self.speed_label.setText(f"{speed:.2f}x")
        self.reduced_motion.setChecked(bool(self.config.get("reducedMotion", False)))
        state = str(self.config.get("manualState", "auto"))
        state_index = self.state_box.findData(state)
        self.state_box.setCurrentIndex(max(0, state_index))

        self.always_on_top.setChecked(bool(self.config.get("alwaysOnTop", True)))
        self.drag_enabled.setChecked(bool(self.config.get("dragEnabled", True)))
        self.locked.setChecked(bool(self.config.get("locked", False)))
        self.click_through.setChecked(bool(self.config.get("clickThrough", False)))
        self.idle_variety.setChecked(bool(self.config.get("idleVariety", True)))
        self.autostart.setChecked(bool(self.config.get("autostart", False)))
        self.show_on_startup.setChecked(bool(self.config.get("showOnStartup", True)))

    def _on_scale_changed(self, percent: int) -> None:
        self.scale_label.setText(f"{percent}%")
        self.width_spin.blockSignals(True)
        self.height_spin.blockSignals(True)
        self.width_spin.setValue(round(192 * percent / 100))
        self.height_spin.setValue(round(208 * percent / 100))
        self.width_spin.blockSignals(False)
        self.height_spin.blockSignals(False)

    def _on_width_changed(self, width: int) -> None:
        if self.keep_ratio.isChecked():
            self.height_spin.blockSignals(True)
            self.height_spin.setValue(round(width * 208 / 192))
            self.height_spin.blockSignals(False)

    def _on_height_changed(self, height: int) -> None:
        if self.keep_ratio.isChecked():
            self.width_spin.blockSignals(True)
            self.width_spin.setValue(round(height * 192 / 208))
            self.width_spin.blockSignals(False)

    def _test(self) -> None:
        self.test_result.setText("测试中……")
        self.test_result.setStyleSheet(f"color: {MUTED};")
        self._tester.start(self._ai_values())

    def _on_test_result(self, ok: bool, message: str) -> None:
        self.test_result.setText(message)
        self.test_result.setStyleSheet(f"color: {'#8fd18a' if ok else ACCENT};")

    def _ai_values(self) -> dict:
        return {
            "mode": "online" if self.radio_online.isChecked() else "local",
            "baseUrl": self.base_url.text().strip(),
            "apiKey": self.api_key.text().strip(),
            "model": self.model.text().strip(),
            "temperature": self.temperature.value(),
            "maxTokens": self.max_tokens.value(),
            "stream": self.stream.isChecked(),
            "systemPrompt": self.system_prompt.toPlainText(),
        }

    def _apply(self) -> None:
        ai = self._ai_values()
        values = {
            "activePetId": self.package_box.currentData(),
            "width": self.width_spin.value(),
            "height": self.height_spin.value(),
            "keepAspectRatio": self.keep_ratio.isChecked(),
            "pixelated": self.pixelated.isChecked(),
            "animationSpeed": self.speed_slider.value() / 100.0,
            "reducedMotion": self.reduced_motion.isChecked(),
            "manualState": self.state_box.currentData(),
            "alwaysOnTop": self.always_on_top.isChecked(),
            "dragEnabled": self.drag_enabled.isChecked(),
            "locked": self.locked.isChecked(),
            "clickThrough": self.click_through.isChecked(),
            "idleVariety": self.idle_variety.isChecked(),
            "autostart": self.autostart.isChecked(),
            "showOnStartup": self.show_on_startup.isChecked(),
            "ai": ai,
        }
        self.apply_requested.emit(values)
        self.hint.setText("已保存")
        self.hint.setStyleSheet(f"color: #8fd18a;")

    def closeEvent(self, event) -> None:                          # noqa: N802
        event.ignore()
        self.hide()
