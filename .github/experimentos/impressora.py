"""Experimento: impressora virtual com o driver "Microsoft Print To PDF" e porta local em named pipe."""
import os, subprocess, sys, threading, time
import win32file, win32pipe, win32print, win32security, pywintypes

PIPE = r"\\.\pipe\DispersioTeste"
PRN = "Dispersio Teste"
OUT = os.path.abspath("saida_exp"); os.makedirs(OUT, exist_ok=True)

def ps(cmd):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
    print(f"PS> {cmd}\n{r.stdout}{r.stderr}rc={r.returncode}", flush=True)
    return r

got = []
def server():
    sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        "D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;OW)(A;;GRGW;;;AU)", win32security.SDDL_REVISION_1)
    sa = pywintypes.SECURITY_ATTRIBUTES(); sa.SECURITY_DESCRIPTOR = sd
    while True:
        h = win32pipe.CreateNamedPipe(PIPE, win32pipe.PIPE_ACCESS_INBOUND, win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_WAIT,
                                      win32pipe.PIPE_UNLIMITED_INSTANCES, 65536, 65536, 0, sa)
        win32pipe.ConnectNamedPipe(h, None)
        title = ""
        try:
            ph = win32print.OpenPrinter(PRN)
            jobs = win32print.EnumJobs(ph, 0, 20, 1); win32print.ClosePrinter(ph)
            title = ";".join(f"{j['pDocument']}|{j['pUserName']}|{j['Status']}" for j in jobs)
        except Exception as e:
            title = f"enumjobs falhou: {e}"
        data = bytearray()
        while True:
            try:
                _, chunk = win32file.ReadFile(h, 65536); data += chunk
            except pywintypes.error:
                break
        win32file.CloseHandle(h)
        fn = os.path.join(OUT, f"job{len(got)+1}.pdf"); open(fn, "wb").write(data)
        print(f"RECEBIDO {len(data)} bytes, início {bytes(data[:8])!r}, jobs: {title}", flush=True)
        got.append(fn)

threading.Thread(target=server, daemon=True).start()
time.sleep(1)
ps("Get-PrinterDriver | Select Name | Format-Table -HideTableHeaders")
ps(f"Add-PrinterPort -Name '{PIPE}'")
ps(f"Add-Printer -Name '{PRN}' -DriverName 'Microsoft Print To PDF' -PortName '{PIPE}'")
ps(f"Get-Printer -Name '{PRN}' | Format-List Name,DriverName,PortName,PrinterStatus")
ps(f"'Olá impressora Dispersio - teste 1' | Out-Printer -Name '{PRN}'")
t0 = time.time()
while len(got) < 1 and time.time() - t0 < 60: time.sleep(0.5)
ps(f"'Segundo documento - teste 2' | Out-Printer -Name '{PRN}'; 'Terceiro - teste 3' | Out-Printer -Name '{PRN}'")
while len(got) < 3 and time.time() - t0 < 120: time.sleep(0.5)
ps(f"Get-PrintJob -PrinterName '{PRN}' | Format-List *")
ok = True
import pymupdf
for f in got:
    try:
        d = pymupdf.open(f); print(f, d.page_count, repr(d[0].get_text()[:80]))
    except Exception as e:
        ok = False; print("PDF inválido", f, e)
print("RESULTADO", "OK" if len(got) == 3 and ok else "FALHOU", len(got))
ps(f"Remove-Printer -Name '{PRN}'; Remove-PrinterPort -Name '{PIPE}'")
sys.exit(0 if len(got) == 3 and ok else 1)
