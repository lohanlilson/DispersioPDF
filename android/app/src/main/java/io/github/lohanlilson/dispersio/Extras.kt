package io.github.lohanlilson.dispersio

import android.content.Context
import android.os.Bundle
import android.os.CancellationSignal
import android.os.ParcelFileDescriptor
import android.print.PageRange
import android.print.PrintAttributes
import android.print.PrintDocumentAdapter
import android.print.PrintDocumentInfo
import android.print.PrintManager
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.launch
import java.io.File
import java.io.FileOutputStream
import java.util.Locale

/** Impressão pelo serviço do Android (impressoras Wi-Fi, Salvar como PDF…). */
fun printPdf(ctx: Context, file: File, name: String) {
    val pm = ctx.getSystemService(Context.PRINT_SERVICE) as PrintManager
    pm.print(name, object : PrintDocumentAdapter() {
        override fun onLayout(old: PrintAttributes?, new: PrintAttributes?, cancel: CancellationSignal?,
                              cb: LayoutResultCallback, extras: Bundle?) {
            if (cancel?.isCanceled == true) { cb.onLayoutCancelled(); return }
            cb.onLayoutFinished(PrintDocumentInfo.Builder(name).setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).build(), true)
        }

        override fun onWrite(pages: Array<out PageRange>?, dest: ParcelFileDescriptor, cancel: CancellationSignal?, cb: WriteResultCallback) {
            try {
                file.inputStream().use { i -> FileOutputStream(dest.fileDescriptor).use { i.copyTo(it) } }
                cb.onWriteFinished(arrayOf(PageRange.ALL_PAGES))
            } catch (e: Exception) {
                cb.onWriteFailed(e.message)
            }
        }
    }, null)
}

/** Leitura em voz alta (voz do Android em português), página por página. */
class Reader(ctx: Context, private val text: suspend (Int) -> String, private val pages: Int,
             private val chars: (suspend (Int) -> PageChars?)? = null,
             private val onWord: (Int, FracRect?) -> Unit = { _, _ -> },
             private val onPage: (Int) -> Unit) {
    /** Palavras do trecho falado: posição no texto falado → área na página (para destacar a palavra lida). */
    private class Tok(val at: Int, val end: Int, val rect: FracRect?)
    private var toks: List<List<Tok>> = emptyList()
    var playing by mutableStateOf(false)
        private set
    var page by mutableIntStateOf(0)
        private set
    var ready by mutableStateOf(false)
        private set
    private var chunks: List<String> = emptyList()
    private var idx = 0
    private val scope = kotlinx.coroutines.MainScope()
    private val tts = TextToSpeech(ctx) { st ->
        if (st == TextToSpeech.SUCCESS) {
            ttsReady()
        }
    }

    private fun ttsReady() {
        tts.language = Locale("pt", "BR")
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(id: String?) {}
            override fun onRangeStart(id: String?, start: Int, end: Int, frame: Int) {
                val n = id?.substringAfterLast('-')?.toIntOrNull() ?: return
                val list = toks.getOrNull(n) ?: return
                val t = list.lastOrNull { it.at <= start } ?: return
                val pg = page
                scope.launch(kotlinx.coroutines.Dispatchers.Main) { onWord(pg, t.rect) }
            }
            override fun onError(id: String?) {}
            override fun onDone(id: String?) {
                scope.launch(kotlinx.coroutines.Dispatchers.Main) { next() }
            }
        })
        ready = true
    }

    fun start(from: Int) {
        page = from
        playing = true
        loadPage()
    }

    private fun loadPage() {
        scope.launch(kotlinx.coroutines.Dispatchers.Main) {
            val pc = chars?.let { runCatching { it(page) }.getOrNull() }
            if (pc != null && pc.text.isNotBlank()) {
                // trechos de até ~1500 caracteres, terminando em fim de frase, guardando onde cada palavra está na página
                val words = Regex("\\S+").findAll(pc.text).toList()
                val cs = ArrayList<String>(); val ts = ArrayList<List<Tok>>()
                var sb = StringBuilder(); var cur = ArrayList<Tok>()
                for (m in words) {
                    if (sb.isNotEmpty()) sb.append(' ')
                    var rect: FracRect? = null
                    for (k in m.range) pc.frac.getOrNull(k)?.let { f -> rect = rect?.let { FracRect(minOf(it.l, f.l), minOf(it.t, f.t), maxOf(it.r, f.r), maxOf(it.b, f.b)) } ?: f }
                    cur += Tok(sb.length, sb.length + m.value.length, rect)
                    sb.append(m.value)
                    if (sb.length > 1200 && m.value.last() in ".!?;:") { cs += sb.toString(); ts += cur; sb = StringBuilder(); cur = ArrayList() }
                }
                if (sb.isNotEmpty()) { cs += sb.toString(); ts += cur }
                chunks = cs; toks = ts
            } else {
                val t = text(page).replace(Regex("\\s+"), " ").trim()
                chunks = t.split(Regex("(?<=[.!?;:])\\s+")).fold(mutableListOf<String>()) { acc, s ->
                    if (acc.isNotEmpty() && acc.last().length + s.length < 1500) acc[acc.lastIndex] = acc.last() + " " + s else acc += s
                    acc
                }.filter { it.isNotBlank() }
                toks = emptyList()
            }
            idx = 0
            onPage(page)
            if (chunks.isEmpty()) next() else speak()
        }
    }

    private fun speak() {
        if (!playing) return
        tts.speak(chunks[idx], TextToSpeech.QUEUE_FLUSH, null, "dispersio-$page-$idx")
    }

    private fun next() {
        if (!playing) return
        idx++
        if (idx < chunks.size) speak()
        else if (page + 1 < pages) { page++; loadPage() }
        else stop()
    }

    fun pause() {
        playing = false
        tts.stop()
    }

    fun resume() {
        playing = true
        if (chunks.isEmpty()) loadPage() else speak()
    }

    fun stop() {
        playing = false
        tts.stop()
        onWord(page, null)
    }

    fun release() {
        stop()
        tts.shutdown()
        scope.coroutineContext[kotlinx.coroutines.Job]?.cancel()
    }
}
