"""Salvamento automático: salva sozinho depois de alterar e ao fechar; dá para desligar nas Preferências."""
import os, sys, tempfile, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
app.setApplicationName("DispersioPDF-teste")
from dispersio import backups
from dispersio.config import cfg
from dispersio.doctab import DocTab
from dispersio.mainwindow import MainWindow

DocTab.AUTOSAVE_MS = 200
perguntas = []
QMessageBox.question = staticmethod(lambda *a, **k: (perguntas.append(a[2] if len(a) > 2 else ""), QMessageBox.Discard)[1])


def wait(ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def novo(nome):
    fn = os.path.join(tmp, nome)
    d = pymupdf.open(); d.new_page().insert_text((72, 72), "ORIGINAL"); d.save(fn)
    return fn


def texto(fn):
    with pymupdf.open(fn) as d:
        return d[0].get_text()


def altera(t, s):
    t.checkpoint(); t.doc[0].insert_text((72, 100 + 14 * len(t.undo_stack)), s); t.changed([0])


tmp = tempfile.mkdtemp()
cfg.set("autosave", True)
w = MainWindow(); w.show()

# 1. salva sozinho pouco depois da alteração; só uma versão anterior por sessão
fn = novo("a.pdf")
w.open_path(fn); wait(100)
t = w.cur()
assert t.can_autosave()
altera(t, "PRIMEIRA")
assert t.modified and "PRIMEIRA" not in texto(fn)
wait(600)
assert not t.modified, "deveria ter salvo sozinho"
assert "PRIMEIRA" in texto(fn)
assert "Salvo automaticamente" in w.statusBar().currentMessage(), w.statusBar().currentMessage()
for k in range(3):
    altera(t, f"MAIS{k}"); wait(500)
assert "MAIS2" in texto(fn) and not t.modified
vs = backups.versions(fn)
assert len(vs) == 1 and "PRIMEIRA" not in texto(vs[0][0]), "a versão guardada é a de antes das alterações"
# desfazer continua funcionando depois de salvar sozinho
t.undo(); assert "MAIS2" not in t.doc[0].get_text(); wait(500)
assert "MAIS2" not in texto(fn)

# 2. não salva no meio da edição seguida: espera parar de alterar
altera(t, "RAPIDO1"); wait(120); altera(t, "RAPIDO2"); wait(120)
assert t.modified and "RAPIDO1" not in texto(fn)
wait(500); assert "RAPIDO2" in texto(fn)

# 3. fechar com alteração pendente: salva sem perguntar
altera(t, "AO FECHAR")
assert w.close_tab(w.tabbar.currentIndex())
assert "AO FECHAR" in texto(fn) and not perguntas

# 4. desligado: não salva sozinho e pergunta ao fechar
cfg.set("autosave", False)
fn2 = novo("b.pdf")
w.open_path(fn2); wait(100)
t = w.cur()
altera(t, "SEM AUTO"); wait(600)
assert t.modified and "SEM AUTO" not in texto(fn2)
assert w.close_tab(w.tabbar.currentIndex())
assert len(perguntas) == 1 and "SEM AUTO" not in texto(fn2)
cfg.set("autosave", True)

# 5. arquivo travado (aberto em outro programa): avisa, não trava, e pergunta ao fechar
fn3 = novo("c.pdf")
w.open_path(fn3); wait(100)
t = w.cur()
orig = os.replace
os.replace = lambda *a: (_ for _ in ()).throw(PermissionError("em uso"))
altera(t, "TRAVADO"); wait(600)
os.replace = orig
assert t.modified and t._autosave_error and "TRAVADO" not in texto(fn3)
assert "Não foi possível salvar automaticamente" in w.statusBar().currentMessage()
assert not os.path.exists(fn3 + ".tmp")
perguntas.clear()
assert w.close_tab(w.tabbar.currentIndex())
assert len(perguntas) == 1, "com falha, volta a perguntar"

# 6. documento assinado e documento novo (sem arquivo): não salvam sozinhos
fn4 = novo("d.pdf")
w.open_path(fn4); wait(100)
t = w.cur(); t.has_signatures = True
altera(t, "ASSINADO"); wait(600)
assert t.modified and "ASSINADO" not in texto(fn4)
perguntas.clear(); w.close_tab(w.tabbar.currentIndex()); assert len(perguntas) == 1
d = pymupdf.open(); d.new_page()
w.open_bytes(d.tobytes(), "Novo.pdf"); wait(100)
t = w.cur()
assert not t.can_autosave()
altera(t, "NOVO"); wait(600)
assert t.modified
perguntas.clear(); w.close_tab(w.tabbar.currentIndex()); assert len(perguntas) == 1
print("salvamento automático ok")
