"""Leitura em voz alta acompanhando a palavra: lê página após página a partir de onde você está (ou da seleção),
destaca a palavra que está sendo falada e rola a tela junto. Barra com pausar, parar e velocidade.

Usa a voz do Windows (Qt TextToSpeech). Quando a voz não informa a palavra atual, o destaque é estimado pelo tempo.
"""
import re

from PySide6.QtCore import QTimer, QElapsedTimer, QPoint
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QLabel, QComboBox

SPEEDS = [("0,75×", -0.25), ("1×", 0.0), ("1,25×", 0.25), ("1,5×", 0.5), ("2×", 0.9)]


class ReadAloud(QFrame):
    def __init__(self, win, tab, tts):
        super().__init__(win)
        self.win, self.tab, self.tts = win, tab, tts
        self.v = tab.view
        self.page = 0
        self.words = []        # [(início no texto falado, fim, índice da palavra na página)]
        self.text = ""
        self.paused = False
        self.stopped = False
        self._est = QTimer(self)
        self._est.timeout.connect(self._estimate)
        self._clock = QElapsedTimer()
        self.setObjectName("ReadBar")
        self.setStyleSheet("QFrame#ReadBar{background:rgba(30,30,34,225); border-radius:10px;}"
                           "QFrame#ReadBar QPushButton{color:#eee; background:transparent; border:none; padding:5px 10px; font-size:14px;}"
                           "QFrame#ReadBar QPushButton:hover{background:rgba(255,255,255,40); border-radius:6px;}"
                           "QFrame#ReadBar QLabel{color:#ccc;} QFrame#ReadBar QComboBox{color:#eee; background:#333;}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        self.play = QPushButton("⏸")
        self.play.setToolTip("Pausar / continuar")
        self.play.clicked.connect(self.toggle)
        stop = QPushButton("⏹")
        stop.setToolTip("Parar")
        stop.clicked.connect(self.stop)
        self.info = QLabel()
        self.speed = QComboBox()
        for label, _r in SPEEDS:
            self.speed.addItem(label)
        from .config import cfg
        self.speed.setCurrentIndex(int(cfg.qs.value("voz/velocidade", 1) or 1))
        self.speed.currentIndexChanged.connect(self._rate)
        for w in (self.play, stop, QLabel("🔊"), self.info, self.speed):
            lay.addWidget(w)
        from PySide6.QtTextToSpeech import QTextToSpeech
        self.QTTS = QTextToSpeech
        self.word_signal = bool(tts.engineCapabilities() & QTextToSpeech.Capability.WordByWordProgress) \
            if hasattr(QTextToSpeech, "Capability") else False
        tts.sayingWord.connect(self._word) if self.word_signal else None
        tts.stateChanged.connect(self._state)
        self._rate()

    # -------------------------------------------------------------- texto da página
    def _prepare(self, page, start_word=0):
        ws = self.v.words(page)
        parts, self.words, pos = [], [], 0
        for k in range(start_word, len(ws)):
            t = ws[k][1]
            if pos:
                parts.append(" ")
                pos += 1
            parts.append(t)
            self.words.append((pos, pos + len(t), k))
            pos += len(t)
        self.text = "".join(parts)
        self.page = page

    def start(self, page, start_word=0):
        self.stopped = False
        n = self.tab.doc.page_count
        while page < n:
            self._prepare(page, start_word)
            if re.search(r"\w", self.text):
                break
            page, start_word = page + 1, 0
        else:
            self.stop()
            return
        self.info.setText(f"Página {self.page + 1}")
        self._wi = 0
        self.tts.say(self.text)
        self._clock.start()
        if not self.word_signal:
            self._est.start(60)
        self.show()
        self.place()

    def _rate(self):
        from .config import cfg
        i = self.speed.currentIndex()
        cfg.qs.setValue("voz/velocidade", i)
        self.tts.setRate(SPEEDS[i][1])

    # -------------------------------------------------------------- destaque
    def _highlight(self, idx):
        if not (0 <= idx < len(self.words)):
            return
        k = self.words[idx][2]
        r = self.v.words(self.page)[k][0]
        self.v.speak_rect = (self.page, r)
        self.v.ensure_rect_visible(self.page, r)
        self.v.viewport().update()

    def _word(self, word, _id, start, length):
        """Sinal da voz: posição exata da palavra no texto falado."""
        lo, hi = 0, len(self.words) - 1
        while lo < hi:                         # última palavra que começa até 'start'
            mid = (lo + hi + 1) // 2
            if self.words[mid][0] <= start:
                lo = mid
            else:
                hi = mid - 1
        self._highlight(lo)

    def _estimate(self):
        """Sem o sinal da voz: estima pela velocidade (≈ 14 caracteres por segundo em 1×)."""
        if self.paused or not self.words:
            return
        cps = 14.0 * (1 + SPEEDS[self.speed.currentIndex()][1] * 1.4)
        pos = self._clock.elapsed() / 1000.0 * cps
        idx = self._wi
        while idx + 1 < len(self.words) and self.words[idx + 1][0] <= pos:
            idx += 1
        if idx != self._wi or getattr(self.v, "speak_rect", None) is None:
            self._wi = idx
            self._highlight(idx)

    def _state(self, st):
        if st == self.QTTS.State.Ready and not self.stopped and not self.paused:
            self._est.stop()
            if self.page + 1 < self.tab.doc.page_count:
                QTimer.singleShot(150, lambda: self.start(self.page + 1))
            else:
                self.stop()

    # -------------------------------------------------------------- controles
    def toggle(self):
        if self.paused:
            self.paused = False
            self.tts.resume()
            self.play.setText("⏸")
        else:
            self.paused = True
            self.tts.pause()
            self.play.setText("▶")

    def stop(self):
        self.stopped = True
        self._est.stop()
        try:
            self.tts.stateChanged.disconnect(self._state)
            if self.word_signal:
                self.tts.sayingWord.disconnect(self._word)
        except (RuntimeError, TypeError):
            pass
        self.tts.stop()
        self.v.speak_rect = None
        self.v.viewport().update()
        self.hide()
        self.deleteLater()
        if getattr(self.win, "_reader", None) is self:
            self.win._reader = None

    def place(self):
        o = self.v.mapTo(self.win, QPoint(0, 0))
        self.adjustSize()
        self.move(o.x() + (self.v.width() - self.width()) // 2, o.y() + 12)
        self.raise_()
