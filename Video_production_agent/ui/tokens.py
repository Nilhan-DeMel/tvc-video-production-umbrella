from __future__ import annotations

import os
from typing import Dict

from PyQt6.QtGui import QFont, QFontDatabase

from .paths import APP_ROOT


MOTION_TOKENS = {
    "micro_ms": 150,
    "panel_ms": 260,
    "toast_ms": 2200,
}


THEMES: Dict[str, Dict[str, str]] = {
    "aurora_graphite": {
        "bg_start": "#060b14",
        "bg_mid": "#0a1322",
        "bg_end": "#040814",
        "bg_glow_a": "rgba(54, 116, 255, 0.16)",
        "bg_glow_b": "rgba(38, 193, 255, 0.08)",
        "shell": "rgba(12, 20, 38, 0.95)",
        "shell_edge": "#203155",
        "panel": "#10192a",
        "panel_soft": "#12203a",
        "panel_alt": "#162642",
        "panel_glass": "rgba(17, 28, 49, 0.92)",
        "panel_hero": "rgba(18, 34, 61, 0.95)",
        "panel_command": "rgba(16, 33, 60, 0.97)",
        "panel_archive": "rgba(15, 24, 41, 0.93)",
        "panel_utility": "rgba(12, 20, 33, 0.90)",
        "border": "#263a60",
        "border_soft": "#355585",
        "border_strong": "#4a7cff",
        "text": "#edf3ff",
        "text_soft": "#cbd8f3",
        "muted": "#8ea7d0",
        "accent": "#4b7dff",
        "accent_2": "#2ad2ff",
        "accent_3": "#8be7ff",
        "accent_soft": "rgba(75, 125, 255, 0.22)",
        "accent_live_soft": "rgba(42, 210, 255, 0.16)",
        "success": "#2ed39a",
        "warning": "#ffbc45",
        "danger": "#ff7187",
        "focus": "#79aaff",
    },
    "obsidian_contrast": {
        "bg_start": "#010101",
        "bg_mid": "#0b0d12",
        "bg_end": "#020203",
        "bg_glow_a": "rgba(89, 166, 255, 0.12)",
        "bg_glow_b": "rgba(123, 242, 255, 0.08)",
        "shell": "rgba(8, 10, 14, 0.98)",
        "shell_edge": "#454b58",
        "panel": "#0b0f15",
        "panel_soft": "#121824",
        "panel_alt": "#172131",
        "panel_glass": "rgba(10, 14, 20, 0.96)",
        "panel_hero": "rgba(15, 22, 31, 0.97)",
        "panel_command": "rgba(15, 22, 32, 0.99)",
        "panel_archive": "rgba(13, 18, 26, 0.98)",
        "panel_utility": "rgba(11, 15, 22, 0.96)",
        "border": "#4d5565",
        "border_soft": "#6f7b90",
        "border_strong": "#89b8ff",
        "text": "#ffffff",
        "text_soft": "#dde5f7",
        "muted": "#b8c2d8",
        "accent": "#67a8ff",
        "accent_2": "#7bf2ff",
        "accent_3": "#cdf7ff",
        "accent_soft": "rgba(103, 168, 255, 0.22)",
        "accent_live_soft": "rgba(123, 242, 255, 0.16)",
        "success": "#63ffbd",
        "warning": "#ffd166",
        "danger": "#ff7b8f",
        "focus": "#9bc6ff",
    },
}


def _font_candidates() -> Dict[str, list]:
    base = os.path.join(APP_ROOT, "assets", "fonts")
    return {
        "Sora": [os.path.join(base, "Sora-VariableFont_wght.ttf"), os.path.join(base, "Sora-Regular.ttf")],
        "Manrope": [os.path.join(base, "Manrope-VariableFont_wght.ttf"), os.path.join(base, "Manrope-Regular.ttf")],
        "JetBrains Mono": [
            os.path.join(base, "JetBrainsMono-VariableFont_wght.ttf"),
            os.path.join(base, "JetBrainsMono-Regular.ttf"),
        ],
    }


def load_premium_fonts():
    for candidates in _font_candidates().values():
        for path in candidates:
            if os.path.exists(path):
                QFontDatabase.addApplicationFont(path)
                break


def app_font(density: str = "cozy") -> QFont:
    size = 10 if density == "compact" else 11
    for family in ("Manrope", "Segoe UI", "Arial"):
        font = QFont(family, size)
        if font.exactMatch():
            return font
    return QFont("Segoe UI", size)


def mono_font(size: int = 10) -> QFont:
    for family in ("JetBrains Mono", "Consolas", "Courier New"):
        font = QFont(family, size)
        if font.exactMatch():
            return font
    return QFont("Consolas", size)


def headline_font(size: int = 11) -> QFont:
    for family in ("Sora", "Bahnschrift SemiBold", "Segoe UI Semibold", "Segoe UI"):
        font = QFont(family, size)
        if font.exactMatch():
            return font
    return QFont("Segoe UI Semibold", size)


def build_stylesheet(theme_id: str = "aurora_graphite", density: str = "cozy") -> str:
    t = THEMES.get(theme_id, THEMES["aurora_graphite"])
    base_pad = "8px" if density == "compact" else "10px"
    field_pad = "8px" if density == "compact" else "10px"
    body_px = "12px" if density == "compact" else "13px"
    card_radius = "16px" if density == "compact" else "18px"
    rail_radius = "18px"
    return f"""
    QMainWindow#StudioWindow {{
        background: qradialgradient(
            cx:0.18, cy:0.08, radius:1.35, fx:0.18, fy:0.08,
            stop:0 {t["bg_glow_a"]},
            stop:0.18 {t["bg_glow_b"]},
            stop:0.42 {t["bg_mid"]},
            stop:1 {t["bg_end"]}
        );
        color: {t["text"]};
    }}
    QWidget {{
        color: {t["text"]};
        font-size: {body_px};
        background: transparent;
    }}
    QLabel[role="shellTitle"] {{
        color: {t["text"]};
        font-size: {"22px" if density == "compact" else "24px"};
        font-weight: 800;
        letter-spacing: 0.04em;
    }}
    QLabel[role="shellSubtitle"] {{
        color: {t["text_soft"]};
        font-size: 12px;
    }}
    QLabel[role="eyebrow"] {{
        color: {t["accent_2"]};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }}
    QLabel[role="pageTitle"] {{
        color: {t["text"]};
        font-size: {"24px" if density == "compact" else "28px"};
        font-weight: 800;
    }}
    QLabel[role="pageSubtitle"] {{
        color: {t["muted"]};
        font-size: 13px;
        padding-bottom: 4px;
    }}
    QLabel[role="cardTitle"] {{
        color: {t["text"]};
        font-size: {"16px" if density == "compact" else "18px"};
        font-weight: 800;
    }}
    QLabel[role="cardSubtitle"] {{
        color: {t["muted"]};
        font-size: 12px;
    }}
    QLabel[role="title"] {{
        color: {t["text"]};
        font-size: 18px;
        font-weight: 800;
    }}
    QLabel[role="heroStateLabel"] {{
        color: {t["accent_2"]};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }}
    QLabel[role="heroStateTitle"] {{
        color: {t["text"]};
        font-size: {"27px" if density == "compact" else "31px"};
        font-weight: 850;
        letter-spacing: 0.01em;
    }}
    QLabel[role="heroStateTitle"][scale="tight"] {{
        font-size: {"23px" if density == "compact" else "26px"};
    }}
    QLabel[role="heroStateBody"] {{
        color: {t["text_soft"]};
        font-size: {"13px" if density == "compact" else "14px"};
        line-height: 1.35em;
    }}
    QLabel[role="heroStateBody"][scale="tight"] {{
        font-size: 12px;
    }}
    QLabel[role="heroMeta"] {{
        color: {t["muted"]};
        font-size: 12px;
        font-weight: 600;
    }}
    QLabel[role="sectionLabel"] {{
        color: {t["accent_3"]};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }}
    QLabel[role="hudLabel"] {{
        color: {t["muted"]};
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
    }}
    QLabel[role="hudValue"] {{
        color: {t["text"]};
        font-size: 16px;
        font-weight: 800;
    }}
    QLabel[role="muted"] {{
        color: {t["muted"]};
    }}
    QLabel[role="metricLabel"] {{
        color: {t["muted"]};
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
    }}
    QLabel[role="metricValue"] {{
        color: {t["text"]};
        font-size: 20px;
        font-weight: 800;
    }}
    QFrame#ShellTopBar {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t["shell"]}, stop:0.65 {t["panel_utility"]}, stop:1 rgba(9,16,27,0.94));
        border: 1px solid {t["shell_edge"]};
        border-radius: 20px;
    }}
    QFrame#LeftRailFrame {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {t["panel_utility"]}, stop:1 rgba(9,16,27,0.92));
        border: 1px solid {t["border"]};
        border-radius: {rail_radius};
    }}
    QFrame#InspectorPanel {{
        background: {t["panel_utility"]};
        border: 1px solid {t["border"]};
        border-radius: 18px;
    }}
    QFrame#GlassCard {{
        background: {t["panel_glass"]};
        border: 1px solid {t["border"]};
        border-radius: {card_radius};
    }}
    QFrame#GlassCard[variant="hero"] {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["panel_hero"]}, stop:1 rgba(10, 24, 44, 0.98));
        border: 1px solid {t["border_strong"]};
    }}
    QFrame#GlassCard[variant="command"] {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["panel_command"]}, stop:1 rgba(10, 22, 40, 0.98));
        border: 1px solid {t["accent_2"]};
    }}
    QFrame#GlassCard[variant="subtle"] {{
        background: {t["panel_utility"]};
        border: 1px solid {t["border_soft"]};
    }}
    QFrame#GlassCard[variant="archive"] {{
        background: {t["panel_archive"]};
        border: 1px solid {t["border_soft"]};
    }}
    QFrame#GlassCard[variant="nav"] {{
        background: rgba(9, 16, 28, 0.88);
        border: 1px solid {t["shell_edge"]};
    }}
    QFrame#MetricTile {{
        background: rgba(21, 34, 56, 0.96);
        border: 1px solid {t["border"]};
        border-radius: 14px;
    }}
    QFrame#MetricTile[density="compact"] {{
        border-radius: 12px;
    }}
    QFrame#MetricTile[narrow="true"] QLabel[role="metricValue"] {{
        font-size: {"17px" if density == "compact" else "18px"};
    }}
    QFrame#MetricTile[density="compact"] QLabel[role="metricLabel"] {{
        font-size: 10px;
    }}
    QFrame#MetricTile[density="compact"] QLabel[role="metricValue"] {{
        font-size: 18px;
    }}
    QFrame#MetricTile[tone="live"] {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(23, 42, 70, 0.98), stop:1 rgba(17, 31, 52, 0.98));
        border: 1px solid {t["accent_2"]};
    }}
    QFrame#MetricTile[tone="success"] {{
        border: 1px solid {t["success"]};
    }}
    QFrame#MetricTile[tone="warning"] {{
        border: 1px solid {t["warning"]};
    }}
    QFrame#HeroNarrativeWell {{
        background: rgba(255, 255, 255, 0.028);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 16px;
    }}
    QFrame#HeroFacetWell {{
        background: rgba(10, 18, 30, 0.46);
        border: 1px solid rgba(255, 255, 255, 0.04);
        border-radius: 16px;
    }}
    QFrame#Toast {{
        background: rgba(10, 17, 29, 0.97);
        border: 1px solid {t["border_soft"]};
        border-radius: 12px;
    }}
    QFrame#Toast[tone="info"] {{
        border: 1px solid {t["accent"]};
    }}
    QFrame#Toast[tone="success"] {{
        border: 1px solid {t["success"]};
    }}
    QFrame#Toast[tone="warning"] {{
        border: 1px solid {t["warning"]};
    }}
    QFrame#Toast[tone="error"] {{
        border: 1px solid {t["danger"]};
    }}
    QLabel#StatusPill {{
        border-radius: 14px;
        padding: 5px 12px;
        font-weight: 700;
        min-height: 18px;
        max-height: 28px;
        background: rgba(255, 255, 255, 0.045);
    }}
    QLabel#StatusPill[density="compact"] {{
        border-radius: 12px;
        padding: 4px 10px;
        min-height: 16px;
        max-height: 26px;
        font-size: 11px;
    }}
    QLabel#StatusPill[tone="success"] {{
        border: 1px solid {t["success"]};
        color: {t["success"]};
    }}
    QLabel#StatusPill[tone="warning"] {{
        border: 1px solid {t["warning"]};
        color: {t["warning"]};
    }}
    QLabel#StatusPill[tone="danger"] {{
        border: 1px solid {t["danger"]};
        color: {t["danger"]};
    }}
    QLabel#StatusPill[tone="info"] {{
        border: 1px solid {t["accent_2"]};
        color: {t["accent_2"]};
    }}
    QLabel#StatusPill[tone="live"] {{
        border: 1px solid {t["accent_3"]};
        color: {t["accent_3"]};
        background: {t["accent_live_soft"]};
    }}
    QLabel#StatusPill[tone="muted"] {{
        border: 1px solid {t["border_soft"]};
        color: {t["muted"]};
    }}
    QLabel#RunThumb {{
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid {t["border_soft"]};
        border-radius: 14px;
    }}
    QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget {{
        background-color: {t["panel_soft"]};
        border: 1px solid {t["border"]};
        border-radius: 10px;
        padding: {field_pad};
        selection-background-color: {t["accent"]};
        selection-color: #ffffff;
    }}
    QPlainTextEdit[role="editor"], QTextBrowser[role="console"] {{
        background-color: rgba(11, 20, 36, 0.94);
        border: 1px solid {t["border_soft"]};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus, QComboBox:focus, QListWidget:focus {{
        border: 1px solid {t["focus"]};
    }}
    QPushButton {{
        background-color: {t["panel_alt"]};
        border: 1px solid {t["border_soft"]};
        border-radius: 10px;
        padding: 9px 13px;
        font-weight: 700;
    }}
    QPushButton:hover {{
        background-color: rgba(255, 255, 255, 0.06);
        border: 1px solid {t["border_strong"]};
    }}
    QPushButton:pressed {{
        background-color: rgba(255, 255, 255, 0.04);
    }}
    QPushButton[accent="true"] {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["accent"]}, stop:1 {t["accent_2"]});
        border: 1px solid {t["accent_2"]};
        color: #ffffff;
        padding: 10px 16px;
    }}
    QPushButton[accent="true"][accentKind="ghost"] {{
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid {t["border_strong"]};
        color: {t["text"]};
    }}
    QPushButton[accent="true"][accentKind="success"] {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t["success"]}, stop:1 {t["accent_2"]});
        border: 1px solid {t["success"]};
        color: #031313;
    }}
    QPushButton[segment="true"] {{
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid {t["border_soft"]};
        border-radius: 10px;
        padding: 8px 12px;
        color: {t["text_soft"]};
    }}
    QPushButton[segment="true"][active="true"] {{
        background: {t["accent_soft"]};
        border: 1px solid {t["border_strong"]};
        color: {t["text"]};
    }}
    QPushButton[accent="true"]:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #5a88ff, stop:1 #4be0ff);
        border: 1px solid #82e8ff;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox::down-arrow {{
        width: 10px;
        height: 10px;
    }}
    QListWidget#LeftRail {{
        background: transparent;
        border: none;
        outline: none;
        padding: 6px;
    }}
    QListWidget#LeftRail::item {{
        padding: 14px 14px;
        margin: 4px 2px;
        border-radius: 14px;
        color: {t["text_soft"]};
        border: 1px solid transparent;
    }}
    QListWidget#LeftRail::item:hover {{
        background: rgba(255, 255, 255, 0.045);
        color: {t["text"]};
    }}
    QListWidget#LeftRail::item:selected {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t["accent_soft"]}, stop:1 rgba(42, 210, 255, 0.12));
        border: 1px solid {t["border_strong"]};
        color: #ffffff;
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QSplitter::handle {{
        background: rgba(255, 255, 255, 0.05);
        width: 4px;
        margin: 6px 0;
        border-radius: 2px;
    }}
    QCheckBox {{
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 5px;
        border: 1px solid {t["border_soft"]};
        background: {t["panel_soft"]};
    }}
    QCheckBox::indicator:checked {{
        background: {t["accent"]};
        border: 1px solid {t["accent_2"]};
    }}
    QToolTip {{
        background-color: {t["panel"]};
        color: {t["text"]};
        border: 1px solid {t["border_soft"]};
        padding: 6px;
    }}
    """
