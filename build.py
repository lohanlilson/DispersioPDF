"""Gera o executável, o instalador e (opcionalmente) o patch de atualização do Dispersio PDF.

  python build.py                       executável + instalador completo
  python build.py --patch-from 1.0.0    também gera o patch da 1.0.0 para a versão atual
  python build.py --sem-instalador      só o executável

A versão vem de dispersio/__init__.py (__version__). Cada build fica guardado em releases/<versão>
para servir de base aos patches seguintes.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist", "DispersioPDF")
BUILD = os.path.join(ROOT, "build")
RELEASES = os.path.join(ROOT, "releases")


def version():
    return meta()["__version__"]


def meta():
    src = open(os.path.join(ROOT, "dispersio", "__init__.py"), encoding="utf-8").read()
    return {k: v for k, v in re.findall(r'^(\w+)\s*=\s*"([^"]*)"', src, re.M)}


def step(msg):
    print(f"\n=== {msg} ===", flush=True)


def version_file(ver):
    m = meta()
    nums = [int(x) for x in re.findall(r"\d+", ver)[:4]] + [0] * 4
    t = tuple(nums[:4])
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('041604B0', [
    StringStruct('CompanyName', '{m["AUTHOR"]}'),
    StringStruct('LegalCopyright', '© 2026 {m["AUTHOR"]} - {m["EMAIL"]}'),
    StringStruct('FileDescription', 'Dispersio PDF - leitor e editor de PDF'),
    StringStruct('FileVersion', '{ver}'),
    StringStruct('InternalName', 'DispersioPDF'),
    StringStruct('OriginalFilename', 'DispersioPDF.exe'),
    StringStruct('ProductName', 'Dispersio PDF'),
    StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [0x0416, 1200])])]
)"""
    os.makedirs(BUILD, exist_ok=True)
    path = os.path.join(BUILD, "version_info.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def pyinstaller(ver):
    step(f"Gerando executável (versão {ver})")
    sep = ";" if os.name == "nt" else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
           "--name", "DispersioPDF", "--icon", os.path.join("assets", "dispersio.ico"),
           "--version-file", version_file(ver),
           "--add-data", f"assets{sep}assets",
           "--distpath", "dist", "--workpath", os.path.join("build", "pyi"), "--specpath", "build",
           "--collect-all", "pdf2docx", "--collect-all", "pyhanko", "--collect-all", "pyhanko_certvalidator",
           "--collect-all", "ctranslate2", "--collect-all", "sentencepiece", "--collect-binaries", "zxingcpp",
           "--exclude-module", "PySide6.QtWebEngineCore", "--exclude-module", "PySide6.QtWebEngineWidgets",
           "--exclude-module", "tkinter", "--exclude-module", "matplotlib", "--exclude-module", "pandas",
           "--exclude-module", "scipy", "--exclude-module", "onnxruntime", "--exclude-module", "IPython", os.path.join(ROOT, "main.py")]
    # caminhos relativos ao specpath: usa absolutos
    cmd[cmd.index("--icon") + 1] = os.path.join(ROOT, "assets", "dispersio.ico")
    cmd[cmd.index("--add-data") + 1] = f"{os.path.join(ROOT, 'assets')}{sep}assets"
    subprocess.run(cmd, cwd=ROOT, check=True)


def shellext():
    """Compila a DispersioShell.dll (miniaturas e painel de visualização do Explorador) e copia para dist.
    Precisa do Visual Studio Build Tools (C++). Sem ele, o programa é gerado sem essa integração."""
    if os.name != "nt":
        return
    step("Compilando a extensão do Explorador (miniaturas e visualização de PDF)")
    bat = os.path.join(ROOT, "shellext", "build.bat")
    if shutil.which("cl"):
        cmd = f'"{bat}"'
    else:
        vswhere = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                               "Microsoft Visual Studio", "Installer", "vswhere.exe")
        vs = ""
        if os.path.exists(vswhere):
            vs = subprocess.run([vswhere, "-latest", "-products", "*", "-requires",
                                 "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                                capture_output=True, text=True).stdout.strip()
        vcvars = os.path.join(vs, "VC", "Auxiliary", "Build", "vcvars64.bat") if vs else ""
        if not vcvars or not os.path.exists(vcvars):
            msg = "Visual Studio Build Tools (C++) não encontrado — sem miniaturas de PDF no Explorador."
            if os.environ.get("DISPERSIO_REQUIRE_SHELLEXT"):
                sys.exit("ERRO: " + msg)
            print("AVISO: " + msg)
            return
        cmd = f'call "{vcvars}" >nul && "{bat}"'
    r = subprocess.run(cmd, shell=True, cwd=ROOT)
    dll = os.path.join(BUILD, "shellext", "DispersioShell.dll")
    if r.returncode != 0 or not os.path.exists(dll):
        if os.environ.get("DISPERSIO_REQUIRE_SHELLEXT"):
            sys.exit("ERRO: falha ao compilar a DispersioShell.dll")
        print("AVISO: falha ao compilar a extensão do Explorador — gerado sem ela.")
        return
    shutil.copy2(dll, os.path.join(DIST, "DispersioShell.dll"))


def manifest(folder):
    out = {}
    for base, _, files in os.walk(folder):
        for fn in files:
            p = os.path.join(base, fn)
            rel = os.path.relpath(p, folder).replace("\\", "/")
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            out[rel] = h.hexdigest()
    return out


def snapshot(ver):
    step(f"Guardando cópia da versão em releases/{ver}")
    dst = os.path.join(RELEASES, ver)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(DIST, os.path.join(dst, "DispersioPDF"))
    with open(os.path.join(dst, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest(DIST), f, indent=0)


def find_iscc(install=True):
    cands = [shutil.which("ISCC"), shutil.which("iscc")]
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands += [os.path.join(base, "Inno Setup 6", "ISCC.exe"), os.path.join(base, "Programs", "Inno Setup 6", "ISCC.exe")]
    for c in cands:
        if c and os.path.exists(c):
            return c
    if install and shutil.which("winget"):
        step("Inno Setup não encontrado — instalando via winget")
        subprocess.run(["winget", "install", "--id", "JRSoftware.InnoSetup", "-e", "--silent",
                        "--accept-package-agreements", "--accept-source-agreements"])
        return find_iscc(install=False)
    return None


def iscc(script, **defines):
    exe = find_iscc()
    if not exe:
        sys.exit("\nERRO: Inno Setup 6 não encontrado. Instale em https://jrsoftware.org/isdl.php e rode de novo.")
    args = [exe] + [f"/D{k}={v}" for k, v in defines.items()] + [os.path.join(ROOT, "installer", script)]
    subprocess.run(args, cwd=os.path.join(ROOT, "installer"), check=True)


def make_patch(from_ver, ver):
    step(f"Gerando patch {from_ver} -> {ver}")
    base = os.path.join(RELEASES, from_ver, "manifest.json")
    if not os.path.exists(base):
        sys.exit(f"ERRO: releases/{from_ver} não existe. Os patches precisam do build da versão anterior.")
    old = json.load(open(base, encoding="utf-8"))
    new = manifest(DIST)
    changed = [p for p, h in new.items() if old.get(p) != h]
    removed = [p for p in old if p not in new]
    pdir = os.path.join(BUILD, "patch")
    if os.path.exists(pdir):
        shutil.rmtree(pdir)
    os.makedirs(os.path.join(pdir, "files"))
    for rel in changed:
        dst = os.path.join(pdir, "files", rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(DIST, rel), dst)
    with open(os.path.join(pdir, "delete.iss"), "w", encoding="utf-8") as f:
        f.write("[InstallDelete]\n")
        for rel in removed:
            f.write(f'Type: files; Name: "{{app}}\\{rel.replace("/", chr(92))}"\n')
    size = sum(os.path.getsize(os.path.join(DIST, r)) for r in changed) / 1024 / 1024
    print(f"{len(changed)} arquivo(s) alterado(s)/novo(s) ({size:.1f} MB), {len(removed)} removido(s)")
    if not changed and not removed:
        print("Nenhuma diferença — patch não gerado.")
        return
    m = meta()
    iscc("patch.iss", AppVersion=ver, FromVersion=from_ver, SourceDir=DIST, AppPublisher=m["AUTHOR"], AppEmail=m["EMAIL"])


def release_notes(ver):
    """Texto da seção '## <versão>' do CHANGELOG.md."""
    path = os.path.join(ROOT, "CHANGELOG.md")
    if not os.path.exists(path):
        return "Melhorias e correções."
    txt = open(path, encoding="utf-8").read()
    m = re.search(rf"^##\s*\[?{re.escape(ver)}\]?.*?$(.*?)(?=^##\s|\Z)", txt, re.M | re.S)
    return (m.group(1).strip() if m else "") or "Melhorias e correções."


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def publish_files(ver, from_ver):
    """Gera versao.json (lido pelo programa), NOTAS.md e manifest.json na pasta Saida."""
    step("Gerando arquivos de publicação")
    out = os.path.join(ROOT, "Saida")
    # repositório onde a Release está sendo criada (no GitHub Actions); fora dele, o do __init__.py
    repo = os.environ.get("GITHUB_REPOSITORY") or meta()["UPDATE_REPO"]
    base = f"https://github.com/{repo}/releases/download/v{ver}/"

    def entry(fn):
        p = os.path.join(out, fn)
        return {"url": base + fn, "sha256": sha256(p), "tamanho": os.path.getsize(p)}
    setup = f"DispersioPDF-Setup-{ver}.exe"
    info = {"versao": ver, "data": __import__("datetime").date.today().isoformat(),
            "novidades": release_notes(ver), "instalador": entry(setup), "patches": {}}
    patch = f"DispersioPDF-Atualizacao-{from_ver}-para-{ver}.exe" if from_ver else None
    if patch and os.path.exists(os.path.join(out, patch)):
        info["patches"][from_ver] = entry(patch)
    with open(os.path.join(out, "versao.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out, "NOTAS.md"), "w", encoding="utf-8") as f:
        f.write(info["novidades"] + "\n\n**Instalação nova:** baixe `" + setup + "`. "
                "Quem já tem o programa recebe o aviso de atualização automaticamente.\n")
    shutil.copy2(os.path.join(RELEASES, ver, "manifest.json"), os.path.join(out, "manifest.json"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patch-from", help="versão instalada que o patch vai atualizar (ex.: 1.0.0)")
    ap.add_argument("--sem-instalador", action="store_true")
    ap.add_argument("--publicar", action="store_true", help="gera versao.json/NOTAS.md/manifest.json para a Release")
    a = ap.parse_args()
    ver = version()
    if a.patch_from == ver:
        sys.exit(f"ERRO: aumente __version__ em dispersio/__init__.py (atual {ver}) antes de gerar o patch.")
    saida = os.path.join(ROOT, "Saida")
    if os.path.isdir(saida):
        shutil.rmtree(saida)
    pyinstaller(ver)
    shellext()
    snapshot(ver)
    if not a.sem_instalador:
        step("Gerando instalador")
        m = meta()
        iscc("dispersio.iss", AppVersion=ver, SourceDir=DIST, AppPublisher=m["AUTHOR"], AppEmail=m["EMAIL"])
    if a.patch_from:
        make_patch(a.patch_from, ver)
    if a.publicar:
        publish_files(ver, a.patch_from)
    step("Concluído")
    print(f"Executável:  dist\\DispersioPDF\\DispersioPDF.exe")
    if os.path.isdir(os.path.join(ROOT, "Saida")):
        for f in sorted(os.listdir(os.path.join(ROOT, "Saida"))):
            print(f"Saída:       Saida\\{f}")


if __name__ == "__main__":
    main()
