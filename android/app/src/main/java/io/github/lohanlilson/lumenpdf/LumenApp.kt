package io.github.lohanlilson.lumenpdf

import android.app.Application

class LumenApp : Application() {
    lateinit var engine: PdfEngine
        private set
    lateinit var recents: Recents
        private set
    lateinit var prefs: Prefs
        private set

    override fun onCreate() {
        super.onCreate()
        com.tom_roush.pdfbox.android.PDFBoxResourceLoader.init(applicationContext)
        engine = PdfEngine(this)
        recents = Recents(this)
        prefs = Prefs(this)
        Thread { runCatching { IcpTrust.init(this) } }.start()
    }
}
