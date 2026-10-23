package io.github.lohanlilson.lumenpdf

import android.app.Application

class LumenApp : Application() {
    lateinit var engine: PdfEngine
        private set
    lateinit var recents: Recents
        private set

    override fun onCreate() {
        super.onCreate()
        engine = PdfEngine(this)
        recents = Recents(this)
    }
}
