"""Configurações do usuário (com valores padrão e tipos). Guardadas no registro do Windows via QSettings."""
from PySide6.QtCore import QSettings

from . import APP_ID

DEFAULTS = {
    # Geral
    "author": "",                        # vazio = nome do usuário do Windows
    "window_mode": "maximized",          # maximized | last | normal
    "startup": "home",                   # home | last_session
    "recent_max": 20,
    "auto_update": True,
    "confirm_delete_pages": True,
    "default_asked": False,
    # Aparência
    "theme": "light",                    # light | dark | system
    "accent": "#6d3cf0",
    "ui_size": "normal",                 # small | normal | large
    "show_tools_panel": True,
    "show_quick_rail": True,
    "open_side_panel": "none",           # none | thumbs | bookmarks | comments
    "canvas_color": "",                  # vazio = cor do tema
    "show_sig_bar": True,
    # Documentos
    "default_zoom": "Ajustar largura",
    "two_page": False,
    "invert_pages": False,
    "remember_position": True,
    "wheel_zoom": False,                 # roda do mouse dá zoom sem Ctrl
    "page_shadow": True,
    # Comentários
    "color_highlight": "#ffd400",
    "color_underline": "#2d9d78",
    "color_strikeout": "#d7373f",
    "color_note": "#ffd400",
    "color_freetext": "#1473e6",
    "color_ink": "#d7373f",
    "color_shapes": "#d7373f",
    "stroke_width": 2.0,
    "annot_opacity": 100,
    # Assinatura
    "sign_reason": "Concordo com o conteúdo deste documento",
    "sign_location": "Goiânia/GO",
    "sign_tsa": True,
    "sign_tsa_url": "http://timestamp.digicert.com",
    "sign_ltv": True,
    "save_copies": "ask",                # ask | same_folder
    "sign_suffix": "_assinado",
    # Impressão
    "quick_print_mode": "default",       # default | last  (impressão rápida: Outlook / botão direito)
    "quick_print_notify": True,
    # OCR e conversão
    "ocr_lang": "por",
    "ocr_dpi": 300,
    "compress_level": "media",           # baixa | media | alta
    "image_format": "png",
    "image_dpi": 200,
    "tessdata": "",
}

def windows_user_name():
    """Nome de exibição do usuário logado no Windows (ex.: “Lohan Lopes”); senão o login."""
    import os
    import sys
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            fn = ctypes.windll.secur32.GetUserNameExW
            for fmt in (3, 2):  # NameDisplay, NameSamCompatible
                size = wintypes.ULONG(0)
                fn(fmt, None, ctypes.byref(size))
                if size.value:
                    buf = ctypes.create_unicode_buffer(size.value)
                    if fn(fmt, buf, ctypes.byref(size)) and buf.value.strip():
                        name = buf.value.strip()
                        return name.split("\\")[-1] if fmt == 2 else name
        except Exception:
            pass
        try:  # conta Microsoft: nome completo do perfil
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Office\Common\UserInfo") as k:
                name, _ = winreg.QueryValueEx(k, "UserName")
                if name.strip():
                    return name.strip()
        except OSError:
            pass
    for env in ("USERNAME", "USER", "LOGNAME"):
        if os.environ.get(env):
            return os.environ[env]
    return "Usuário"


UI_FONT_PX = {"small": 12, "normal": 13, "large": 15}


class Config:
    def __init__(self):
        self.qs = QSettings(APP_ID, APP_ID)
        if self.qs.value("brand_v2", None) is None:  # nova identidade: troca o azul antigo pelo violeta da marca
            if str(self.qs.value("accent", "")).lower() in ("#1473e6", ""):
                self.qs.remove("accent")
            self.qs.setValue("brand_v2", "true")

    def get(self, key):
        if key == "author":
            v = str(self.qs.value("author", "") or "").strip()
            if not v or v == "Usuário":
                if not hasattr(self, "_win_user"):
                    self._win_user = windows_user_name()
                return self._win_user
            return v
        default = DEFAULTS.get(key)
        raw = self.qs.value(key, None)
        if raw is None:
            return default
        if isinstance(default, bool):
            return str(raw).lower() in ("true", "1", "yes")
        if isinstance(default, int) and not isinstance(default, bool):
            try:
                return int(float(raw))
            except (TypeError, ValueError):
                return default
        if isinstance(default, float):
            try:
                return float(raw)
            except (TypeError, ValueError):
                return default
        return raw

    def set(self, key, value):
        if isinstance(value, bool):
            value = "true" if value else "false"
        self.qs.setValue(key, value)

    def reset(self):
        for k in DEFAULTS:
            if k != "default_asked":
                self.qs.remove(k)

    def export(self, path):
        out = QSettings(path, QSettings.IniFormat)
        for k in DEFAULTS:
            out.setValue(k, self.get(k) if not isinstance(self.get(k), bool) else ("true" if self.get(k) else "false"))
        out.sync()

    def import_(self, path):
        src = QSettings(path, QSettings.IniFormat)
        for k in DEFAULTS:
            if src.contains(k):
                self.qs.setValue(k, src.value(k))

    # posição de leitura por documento
    def doc_state(self, path):
        import hashlib
        key = "docs/" + hashlib.sha1(path.lower().encode("utf-8")).hexdigest()[:16]
        v = self.qs.value(key, "")
        try:
            page, zoom, mode = str(v).split("|")
            return int(page), float(zoom), mode
        except ValueError:
            return None

    def save_doc_state(self, path, page, zoom, mode):
        import hashlib
        key = "docs/" + hashlib.sha1(path.lower().encode("utf-8")).hexdigest()[:16]
        self.qs.setValue(key, f"{page}|{zoom:.4f}|{mode}")


cfg = Config()
