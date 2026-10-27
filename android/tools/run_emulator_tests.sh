#!/usr/bin/env bash
# Roda os testes do app no emulador e copia as capturas de tela (chamado pelo workflow android.yml).
set -u
APK=android/app/build/outputs/apk
adb install -r "$APK/debug/app-debug.apk"
adb install -r "$APK/androidTest/debug/app-debug-androidTest.apk"
adb logcat -G 16M || true
adb logcat -c || true
sleep 8
adb shell am broadcast -a android.intent.action.CLOSE_SYSTEM_DIALOGS || true
adb shell am instrument -w -r io.github.lohanlilson.lumenpdf.test/androidx.test.runner.AndroidJUnitRunner | tee instr.txt
adb logcat -d | grep -E "DispersioTest|DispersioPdf" | grep -v "printToLog\|Node #\||" | tail -80
adb logcat -d | grep "DESEMPENHO" || true
mkdir -p capturas
adb pull /sdcard/Android/data/io.github.lohanlilson.lumenpdf/files/capturas/. capturas/ || true
# APK de publicação (código otimizado pelo R8): abre e confere que não fecha sozinho
adb uninstall io.github.lohanlilson.lumenpdf >/dev/null 2>&1 || true
adb install -r "$APK/release/app-release.apk"
adb logcat -c || true
adb shell am start -W -n io.github.lohanlilson.lumenpdf/io.github.lohanlilson.dispersio.MainActivity
sleep 6
adb exec-out screencap -p > capturas/05_publicacao.png || true
RELEASE_OK=1
adb shell pidof io.github.lohanlilson.lumenpdf >/dev/null || RELEASE_OK=0
adb logcat -d | grep -q "FATAL EXCEPTION" && RELEASE_OK=0
ls -la capturas || true
if [ "$RELEASE_OK" != 1 ]; then
  echo "APK de publicação fechou sozinho"
  adb logcat -d | grep -E -A30 "FATAL EXCEPTION" | head -80
  exit 1
fi
if grep -qE "FAILURES!!!|INSTRUMENTATION_FAILED|Process crashed|shortMsg" instr.txt || ! grep -q "^OK (" instr.txt; then
  echo "---- logcat ----"
  adb logcat -d | grep -E "AndroidRuntime|lumenpdf|TestRunner|FATAL|DispersioTest|pdfium" | tail -200
  exit 1
fi
