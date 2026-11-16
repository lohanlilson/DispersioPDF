"""Leitura em voz alta: lê da seleção em diante, destaca a palavra falada e passa para a próxima página."""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
from PySide6.QtTextToSpeech import QTextToSpeech
from dispersio.mainwindow import MainWindow
from dispersio.doctab import DocTab


class FakeTTS(QObject):
    """Voz de mentira: guarda o que mandaram falar e avisa a palavra quando o teste pede."""
    sayingWord = Signal(str, int, int, int)
    stateChanged = Signal(object)

    def __init__(self):
        super().__init__()
        self.said = []
    def engineCapabilities(self): return QTextToSpeech.Capability.WordByWordProgress
    def say(self, t): self.said.append(t)
    def setRate(self, r): pass
    def stop(self): pass
    def pause(self): pass
    def resume(self): pass


QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
w = MainWindow(); w.resize(1200, 800); w.show()
d = pymupdf.open()
d.new_page().insert_text((72, 100), "Primeira página com algumas palavras para ler.", fontsize=14)
d.new_page().insert_text((72, 100), "Segunda página continua a leitura.", fontsize=14)
t = DocTab(d.tobytes(), None, None, w.settings); w.add_tab(t)
for _ in range(10): app.processEvents()
w.tts = FakeTTS()
v = t.view
k = next(n for n, wd in enumerate(v.words(0)) if wd[1] == "algumas")
v.set_selection(0, k, k + 1)
r = w.tool_read_aloud(t)
assert w.tts.said[-1].startswith("algumas palavras"), w.tts.said
start = w.tts.said[-1].index("ler")
w.tts.sayingWord.emit("ler", 0, start, 3)
assert v.speak_rect[0] == 0 and abs(v.speak_rect[1].x0 - v.words(0)[k + 3][0].x0) < 0.1, "destaca a palavra falada"
w.tts.stateChanged.emit(QTextToSpeech.State.Ready)          # terminou a página
for _ in range(30):
    app.processEvents()
    import time; time.sleep(0.01)
assert w.tts.said[-1].startswith("Segunda página"), w.tts.said
r.stop()
assert getattr(v, "speak_rect", None) is None and w._reader is None
while len(w.tab_widgets) > 1:
    w.close_tab(len(w.tab_widgets) - 1)
print("voz ok")
