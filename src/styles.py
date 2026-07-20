"""
Centralized visual design system - enterprise / Tier-1 SaaS grade.

Holds the shared design tokens (colour palette, type scale, spacing,
radii) reused across every hand-styled widget and by the Gantt/Milestone
status colours in charts.py, plus a single global QSS stylesheet applied
once at the QApplication level in app.py, so every default Qt widget -
text inputs, combo boxes, trees, scrollbars, tabs, dialogs - shares one
calm, dense, professional look modeled on the visual language of tools
like Asana, Linear, and Claude.ai: cool neutrals, a single restrained
accent, tight radii, near-flat elevation, and no decorative flourish.

No emoji appear anywhere in the app. All iconography comes from
icons.py, which renders vector glyphs (Font Awesome / Material Design,
bundled offline via the `qtawesome` package) instead of relying on the
OS's emoji font.

Design decisions vs. the previous palette, made in response to a client
review calling the app "childish" (3/10 UX score):
  - Accent moved from a bright periwinkle (#5B5FEF) to a restrained,
    desaturated enterprise blue - present in every major B2B product,
    reads as "tool" rather than "app".
  - Background moved from a warm cream to a cool neutral gray - warm
    off-whites skew consumer/lifestyle; cool grays skew productivity
    software.
  - Radii cut roughly in half across the board (16/12/8 -> 10/8/6).
    Heavy rounding is the single biggest "friendly app" signal; tighter
    corners read as precise and considered.
  - Shadows flattened significantly (lower blur, lower opacity, smaller
    offset) - enterprise UI uses elevation as a whisper, not a glow.
  - Heading weight dropped from 700 to 600 and sizes tightened - bold,
    oversized headings belong on marketing pages, not inside a working
    tool used for hours at a time.
"""

# --- Palette ---------------------------------------------------------------
# A cool, low-chroma neutral base with a single restrained, desaturated
# accent. Every semantic colour is pulled a step toward gray relative to
# the previous palette - saturated colour reads as playful; muted colour
# reads as considered.
INK = "#1A1D24"            # primary text / headings
MUTED = "#5B6270"          # secondary / muted text
SUBTLE = "#8A90A0"         # placeholders, disabled, faint captions
ACCENT = "#2F5FD6"         # primary actions, links, active/selected states
ACCENT_DARK = "#24499E"    # hover/pressed state for the accent
ACCENT_SOFT = "#EAEFFB"    # tinted backgrounds behind the accent
SUCCESS = "#1B7A4E"        # constructive actions (create, save, export)
SUCCESS_SOFT = "#E6F3EC"
DANGER = "#C4302B"         # destructive actions (delete)
DANGER_SOFT = "#FBEAE9"
WARNING = "#B4720A"        # warnings / on-hold status
WARNING_SOFT = "#FBF0DD"
BORDER = "#E1E3E8"
SURFACE = "#FFFFFF"
BACKGROUND = "#F5F6F8"
BACKGROUND_ALT = "#ECEDF1"

# --- Backwards-compatible aliases ------------------------------------------
# The rest of the codebase (app.py, views.py, dialogs.py, charts.py)
# imports these historical names; keep them pointed at the new palette so
# every call site picks up the redesign without a churn-y rename pass.
NAVY = INK
SLATE = MUTED
BLUE = ACCENT
BLUE_DARK = ACCENT_DARK
GREEN = SUCCESS
RED = DANGER
AMBER = WARNING

# --- Type --------------------------------------------------------------
# A humanist, screen-native stack: Inter first where installed (same
# family used by Linear, Vercel, and other dense B2B tools), falling
# back gracefully to each OS's own modern system font.
FONT_FAMILY = ("'Inter', 'Segoe UI Variable', 'Segoe UI', 'SF Pro Text', "
              "-apple-system, BlinkMacSystemFont, 'Helvetica Neue', "
              "'Ubuntu', sans-serif")

# --- Spacing & radii ---------------------------------------------------
# Radii pulled in noticeably from the previous scale (was 8/12/16). Tight
# corners are one of the clearest "professional tool, not consumer app"
# signals available in a QSS-only design system.
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 20
SPACE_XL = 32

RADIUS_SM = 6
RADIUS_MD = 8
RADIUS_LG = 10


def button_style(bg: str, fg: str = "white", padding: str = "8px 16px",
                 radius: int = RADIUS_SM) -> str:
    """Shared recipe for the app's accent-coloured call-to-action buttons."""
    return (f"background-color: {bg}; color: {fg}; padding: {padding}; "
            f"font-weight: 600; font-size: 12.5px; border: none; "
            f"border-radius: {radius}px;")


def ghost_button_style(color: str = ACCENT, padding: str = "8px 16px") -> str:
    """A quieter, outline-only button for secondary actions."""
    return (f"background-color: transparent; color: {color}; "
            f"padding: {padding}; font-weight: 600; font-size: 12.5px; "
            f"border: 1px solid {BORDER}; border-radius: {RADIUS_SM}px;")


def hint_style() -> str:
    """Shared recipe for the small 'how this screen works' hint labels
    sprinkled across tabs, so first-time users always have a plain-
    language explainer without hunting for a manual."""
    return (f"color: {MUTED}; font-size: 12px; "
            f"padding: 2px 2px 6px 2px; background: transparent;")


def badge_style(fg: str, bg: str, radius: int = RADIUS_SM) -> str:
    """A soft pill/badge used for status or priority chips."""
    return (f"color: {fg}; background-color: {bg}; padding: 2px 9px; "
            f"border-radius: {radius}px; font-weight: 600; font-size: 11px;")


def card_style(radius: int = RADIUS_MD) -> str:
    """Shared recipe for a raised, breathable panel/card surface."""
    return (f"background-color: {SURFACE}; border: 1px solid {BORDER}; "
            f"border-radius: {radius}px;")


def apply_shadow(widget, blur: int = 14, x_offset: int = 0, y_offset: int = 2,
                 alpha: int = 18):
    """
    Attaches a soft drop shadow to give a widget a gentle sense of
    elevation (cards, dialogs, the top bar). Tuned much flatter than a
    typical consumer-app shadow - enterprise UI treats elevation as a
    near-invisible cue, not a glow.
    """
    from PyQt6.QtWidgets import QGraphicsDropShadowEffect
    from PyQt6.QtGui import QColor

    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(x_offset, y_offset)
    effect.setColor(QColor(21, 23, 28, alpha))
    widget.setGraphicsEffect(effect)
    return effect


ENTERPRISE_STYLESHEET = f"""
* {{
    font-family: {FONT_FAMILY};
}}
QMainWindow, QWidget {{
    background-color: {BACKGROUND};
    color: {INK};
    font-size: 12.5px;
}}
QDialog {{
    background-color: {SURFACE};
}}
QLabel {{
    color: {INK};
}}
QLabel[role="heading"] {{
    font-size: 16px;
    font-weight: 600;
    letter-spacing: -0.1px;
}}
QLabel[role="caption"] {{
    color: {MUTED};
    font-size: 12px;
}}
QPushButton {{
    background-color: {SURFACE};
    color: {INK};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 7px 14px;
    font-weight: 600;
    font-size: 12.5px;
}}
QPushButton:hover {{
    background-color: {BACKGROUND_ALT};
    border-color: #C9CCD3;
}}
QPushButton:pressed {{
    background-color: {BORDER};
}}
QPushButton:disabled {{
    color: {SUBTLE};
    background-color: {BACKGROUND_ALT};
    border-color: {BORDER};
}}
QLineEdit, QTextEdit, QComboBox, QDateEdit, QSpinBox {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 6px 9px;
    selection-background-color: {ACCENT};
    selection-color: white;
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QSpinBox:hover {{
    border-color: #C9CCD3;
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {INK};
    outline: 0;
    padding: 4px;
}}
QTreeWidget, QListWidget, QTableWidget {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD}px;
    alternate-background-color: {BACKGROUND};
    outline: 0;
    padding: 2px;
}}
QHeaderView::section {{
    background-color: {BACKGROUND_ALT};
    color: {MUTED};
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.2px;
    padding: 7px 6px;
    border: none;
    border-bottom: 1px solid {BORDER};
}}
QTreeWidget::item, QListWidget::item {{
    padding: 5px 4px;
    border-radius: {RADIUS_SM}px;
}}
QTreeWidget::item:selected, QListWidget::item:selected {{
    background-color: {ACCENT_SOFT};
    color: {INK};
}}
QTreeWidget::item:hover, QListWidget::item:hover {{
    background-color: {BACKGROUND_ALT};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: {SUBTLE};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 5px;
    min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {SUBTLE};
}}
QMessageBox {{
    background-color: {SURFACE};
}}
QTabWidget::pane {{
    border: 0;
    background-color: {SURFACE};
    border-radius: {RADIUS_MD}px;
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 10px 18px;
    margin-right: 2px;
    border-top-left-radius: {RADIUS_SM}px;
    border-top-right-radius: {RADIUS_SM}px;
    font-size: 12px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background: {SURFACE};
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    background: {BACKGROUND_ALT};
    color: {INK};
}}
QToolTip {{
    background-color: {INK};
    color: white;
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: 6px 9px;
    font-size: 11.5px;
}}
QMenu {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD}px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 12px;
    border-radius: {RADIUS_SM}px;
    color: {INK};
}}
QMenu::item:selected {{
    background-color: {ACCENT_SOFT};
    color: {ACCENT_DARK};
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 3px;
    border: 1.5px solid {BORDER};
    background: {SURFACE};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
"""
