# PDFium (métodos nativos chamados por JNI)
-keep class io.legere.pdfiumandroid.** { *; }
-keepclasseswithmembernames class * { native <methods>; }

# PDFBox / BouncyCastle (carregam classes por reflexão)
-keep class com.tom_roush.** { *; }
-keep class org.bouncycastle.** { *; }
-dontwarn com.tom_roush.**
-dontwarn org.bouncycastle.**
-dontwarn com.gemalto.jp2.**
