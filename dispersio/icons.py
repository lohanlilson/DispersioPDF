"""Conjunto de ícones vetoriais próprios (traço 24x24), coloridos conforme o tema."""
from PySide6.QtCore import QByteArray, Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

_P = {
    "open": '<path d="M3 6h6l2 2h10v11H3z"/>',
    "save": '<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v5h8V3"/><path d="M8 21v-7h8v7"/>',
    "saveas": '<path d="M5 3h11l3 3v7"/><path d="M5 3v18h7"/><path d="M8 3v5h8V3"/><path d="M15 21l6-6-2-2-6 6v2z"/>',
    "print": '<path d="M6 9V3h12v6"/><path d="M6 18H4v-8h16v8h-2"/><path d="M6 14h12v7H6z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5"/>',
    "zoom_in": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5M8 11h6M11 8v6"/>',
    "zoom_out": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5M8 11h6"/>',
    "select": '<path d="M5 3l14 8-6.5 1.8L9.5 19z"/>',
    "hand": '<path d="M7 12V6a1.6 1.6 0 013.2 0v5"/><path d="M10.2 11V4.5a1.6 1.6 0 013.2 0V11"/><path d="M13.4 11V6a1.6 1.6 0 013.2 0v6"/><path d="M16.6 12V9a1.6 1.6 0 013.2 0v5a7 7 0 01-7 7h-1a7 7 0 01-6-3.5L3.6 13a1.6 1.6 0 012.6-1.8L7 12"/>',
    "highlight": '<path d="M14 3l7 7-8 8-7-7z"/><path d="M6 11l-3 6 2 2 6-3"/><path d="M2 22h9" stroke-width="3"/>',
    "underline": '<path d="M7 4v7a5 5 0 0010 0V4"/><path d="M5 20h14"/>',
    "strike": '<path d="M4 12h16"/><path d="M16.5 7A4.5 3.5 0 0012 4.5c-2.5 0-4.5 1.3-4.5 3.2 0 1.5 1 2.3 2.5 3"/><path d="M7.5 16.5c.5 1.7 2.3 3 4.5 3 2.5 0 4.5-1.3 4.5-3.2 0-1-.4-1.7-1.2-2.3"/>',
    "squiggly": '<path d="M5 4v6a7 7 0 0014 0V4"/><path d="M3 20l2-2 2 2 2-2 2 2 2-2 2 2 2-2 2 2"/>',
    "note": '<path d="M4 4h16v12H9l-5 4z"/><path d="M8 8h8M8 12h5"/>',
    "freetext": '<path d="M4 4h16v16H4z"/><path d="M8 8h8M12 8v9"/>',
    "addtext": '<path d="M5 6V4h14v2"/><path d="M12 4v16M9 20h6"/>',
    "ink": '<path d="M3 17c2-3 4-3 5-1s2 3 4 0 3-8 6-8 2 4 0 7"/><path d="M15 3l3 3"/>',
    "rect": '<rect x="4" y="5" width="16" height="14" rx="1"/>',
    "ellipse": '<ellipse cx="12" cy="12" rx="9" ry="7"/>',
    "line": '<path d="M5 19L19 5"/>',
    "translate": '<path d="M4 5h9M8.5 3v2M6 5c0 4 3 7 6 8M11 5c0 4-3 7-7 8"/><path d="M13 21l4-10 4 10M14.5 17.5h5"/>',
    "barcode": '<path d="M4 6v12M7 6v12M10 6v9M13 6v9M16 6v12M20 6v12"/><path d="M9.5 18h4"/>',
    "arrow": '<path d="M5 19L19 5"/><path d="M10 5h9v9"/>',
    "stamp": '<path d="M4 21h16"/><path d="M5 17h14v-4H5z"/><path d="M10 13V9.5a3 3 0 114 0V13"/>',
    "sign": '<path d="M3 17c3-5 5-1 7-4s2-7 4.5-5.5S13 15 16 15s3-3 5-2"/><path d="M3 21h18"/>',
    "certificate": '<path d="M4 4h16v11H4z"/><path d="M8 8h8M8 11h5"/><circle cx="16" cy="17" r="3"/><path d="M14.5 19.5L14 23l2-1 2 1-.5-3.5"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "edittext": '<path d="M4 7V5h10v2M9 5v12M7 17h4"/><path d="M14 20h3l5-5-3-3-5 5z"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="1"/><circle cx="9" cy="10" r="2"/><path d="M21 17l-6-6-8 9"/>',
    "link": '<path d="M10 14a4 4 0 006 0l3-3a4 4 0 00-6-6l-1 1"/><path d="M14 10a4 4 0 00-6 0l-3 3a4 4 0 006 6l1-1"/>',
    "merge": '<path d="M4 3h7v8H4zM13 13h7v8h-7z"/><path d="M11 7h5v4M16 11l-2-2M16 11l2-2"/>',
    "split": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.5 8L20 18M8.5 16L20 6"/>',
    "rotate_cw": '<path d="M20 12a8 8 0 11-2.4-5.7"/><path d="M20 4v5h-5"/>',
    "rotate_ccw": '<path d="M4 12a8 8 0 102.4-5.7"/><path d="M4 4v5h5"/>',
    "trash": '<path d="M4 7h16M10 7V4h4v3"/><path d="M6 7l1 14h10l1-14"/><path d="M10 11v6M14 11v6"/>',
    "compress": '<path d="M4 14h6v6M20 10h-6V4"/><path d="M14 10l7-7M3 21l7-7"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="1"/><path d="M8 11V7a4 4 0 018 0v4"/>',
    "unlock": '<rect x="5" y="11" width="14" height="10" rx="1"/><path d="M8 11V7a4 4 0 017.5-2"/>',
    "redact": '<path d="M3 5h18v5H3z" fill="currentColor"/><path d="M3 14h12v5H3z" fill="currentColor"/>',
    "ocr": '<path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4"/><path d="M8 9h8M8 12h8M8 15h5"/>',
    "convert": '<path d="M4 8h14l-4-4"/><path d="M20 16H6l4 4"/>',
    "word": '<path d="M5 3h10l4 4v14H5z"/><path d="M8 11l1.5 6 2.5-5 2.5 5 1.5-6"/>',
    "excel": '<path d="M5 3h10l4 4v14H5z"/><path d="M8 11l7 7M15 11l-7 7"/>',
    "imagefile": '<path d="M5 3h10l4 4v14H5z"/><circle cx="10" cy="11" r="1.5"/><path d="M19 18l-5-5-7 7"/>',
    "textfile": '<path d="M5 3h10l4 4v14H5z"/><path d="M8 10h8M8 13h8M8 16h5"/>',
    "createpdf": '<path d="M5 3h10l4 4v14H5z"/><path d="M12 10v7M8.5 13.5h7"/>',
    "form": '<rect x="3" y="3" width="18" height="18" rx="1"/><path d="M7 8h10M7 12h4"/><rect x="13" y="11" width="4" height="4"/><path d="M7 17h10"/>',
    "textfield": '<rect x="3" y="7" width="18" height="10" rx="1"/><path d="M7 10v4"/>',
    "checkbox": '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 12l3 3 5-6"/>',
    "split": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/><path d="M6 9h3M6 12h3M15 9h3M15 12h3"/>',
    "compare": '<path d="M3 4h7v16H3zM14 4h7v16h-7z"/><path d="M5 8h3M5 11h3M16 8h3M16 11h3M16 14h3"/>',
    "watermark": '<path d="M12 3s6 7 6 11a6 6 0 01-12 0c0-4 6-11 6-11z"/>',
    "pagenum": '<path d="M5 3h10l4 4v14H5z"/><path d="M10 10l-1 8M14 10l-1 8M8 12.5h7.5M7.5 15.5h7.5"/>',
    "crop": '<path d="M6 2v16h16"/><path d="M2 6h16v16"/>',
    "insertpage": '<path d="M5 3h10l4 4v14H5z"/><path d="M12 10v7M8.5 13.5h7"/>',
    "extract": '<path d="M13 3H5v18h14V9"/><path d="M13 3l6 6"/><path d="M12 11v7M9 15l3 3 3-3"/>',
    "organize": '<rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="9"/><rect x="3" y="15" width="7" height="6"/><rect x="14" y="15" width="7" height="6"/>',
    "thumbs": '<rect x="4" y="3" width="6" height="8"/><rect x="14" y="3" width="6" height="8"/><rect x="4" y="13" width="6" height="8"/><rect x="14" y="13" width="6" height="8"/>',
    "bookmark": '<path d="M6 3h12v18l-6-4-6 4z"/>',
    "comments": '<path d="M4 4h16v12H9l-5 4z"/>',
    "attach": '<path d="M20 11l-8.5 8.5a5 5 0 01-7-7L13 4a3.3 3.3 0 014.7 4.7L9.2 17.2a1.6 1.6 0 01-2.3-2.3L15 7"/>',
    "tools": '<rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><path d="M17 14v6M14 17h6"/>',
    "home": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h5v-6h4v6h5V10"/>',
    "fit_width": '<path d="M3 12h18M7 8l-4 4 4 4M17 8l4 4-4 4"/>',
    "fit_page": '<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M9 9l-2-2M15 9l2-2M9 15l-2 2M15 15l2 2"/>',
    "prev": '<path d="M15 18l-6-6 6-6"/>',
    "next": '<path d="M9 18l6-6-6-6"/>',
    "up": '<path d="M6 15l6-6 6 6"/>',
    "down": '<path d="M6 9l6 6 6-6"/>',
    "undo": '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 010 10h-3"/>',
    "redo": '<path d="M15 14l5-5-5-5"/><path d="M20 9H9a5 5 0 000 10h3"/>',
    "moon": '<path d="M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "speaker": '<path d="M11 5L6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 010 7M19 5a10 10 0 010 14"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    "readmode": '<path d="M4 4h6a2 2 0 012 2v14a2 2 0 00-2-2H4z"/><path d="M20 4h-6a2 2 0 00-2 2v14a2 2 0 012-2h6z"/>',
    "twopage": '<rect x="3" y="4" width="8" height="16"/><rect x="13" y="4" width="8" height="16"/>',
    "onepage": '<rect x="6" y="3" width="12" height="18"/>',
    "flatten": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "clean": '<path d="M4 20l7-7"/><path d="M14 3l7 7-6 6-7-7z"/><path d="M3 21h6"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="1"/><path d="M16 8V4H4v12h4"/>',
    "blank": '<path d="M5 3h10l4 4v14H5z"/>',
    "star": '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 01-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 010-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 014 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 010 4h-.1a1.7 1.7 0 00-1.5 1z"/>',
    "fullscreen": '<path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/>',
}

_registry = []  # (widget, name, setter)
_color = "#2c2c2c"


def _svg(name, color):
    body = _P.get(name, _P["blank"]).replace("currentColor", color)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


_icon_cache = {}


def icon(name, color=None, size=48):
    color = color or _color
    key = (name, color, size)
    ic = _icon_cache.get(key)
    if ic is None:
        ic = _icon_cache[key] = _make_icon(name, color, size)
    return ic


def _make_icon(name, color, size):
    renderer = QSvgRenderer(QByteArray(_svg(name, color).encode()))
    pm = QPixmap(QSize(size, size))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    return QIcon(pm)


def bind(widget, name):
    """Define o ícone e registra o widget para recolorir na troca de tema."""
    widget.setIcon(icon(name))
    _registry.append((widget, name))
    return widget


def set_color(color):
    global _color
    _color = color
    alive = []
    for w, n in _registry:
        try:
            w.setIcon(icon(n))
            alive.append((w, n))
        except RuntimeError:  # widget destruído
            pass
    _registry[:] = alive


def current_color():
    return _color


_chip_cache = {}


def chip(name, color, size=40, radius=0.28):
    """Ícone branco sobre um quadrado arredondado colorido (estilo dos cartões modernos)."""
    key = (name, color, size)
    if key in _chip_cache:
        return _chip_cache[key]
    from PySide6.QtGui import QColor, QLinearGradient, QBrush
    pm = QPixmap(QSize(size * 2, size * 2))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    g = QLinearGradient(0, 0, size * 2, size * 2)
    g.setColorAt(0, c.lighter(118))
    g.setColorAt(1, c)
    p.setBrush(QBrush(g))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, size * 2, size * 2, size * 2 * radius, size * 2 * radius)
    renderer = QSvgRenderer(QByteArray(_svg(name, "#ffffff").encode()))
    m = int(size * 2 * 0.24)
    from PySide6.QtCore import QRectF
    renderer.render(p, QRectF(m, m, size * 2 - 2 * m, size * 2 - 2 * m))
    p.end()
    pm.setDevicePixelRatio(2)
    ic = QIcon(pm)
    _chip_cache[key] = ic
    return ic


SECTION_COLORS = {
    "Comentar": "#f59e0b", "Editar": "#7c3aed", "Organizar páginas": "#10b981", "Converter e exportar": "#3b82f6",
    "Proteger": "#ef4444", "Assinar": "#ec4899", "Formulários": "#14b8a6", "Mais ferramentas": "#64748b",
}
