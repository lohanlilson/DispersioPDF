package io.github.lohanlilson.dispersio

import android.annotation.SuppressLint
import android.content.Context
import android.net.Uri
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import java.io.ByteArrayInputStream
import java.io.File
import java.util.zip.ZipFile

/** Livros EPUB: o livro é descompactado na pasta do app e cada capítulo aparece numa página de rolagem,
 *  com tamanho da letra e tema (claro, sépia, escuro). Lembra capítulo e posição. Sem acesso à internet. */
object Epub {
    class Book(val key: String, val title: String, val dir: File, val chapters: List<File>)

    fun isEpubName(name: String) = name.lowercase().endsWith(".epub")

    fun open(ctx: Context, uri: Uri, name: String): Book {
        val key = Comic.key(uri)
        val dir = File(ctx.filesDir, "epub/$key")
        if (!File(dir, ".pronto").exists()) {
            dir.deleteRecursively(); dir.mkdirs()
            val tmp = File.createTempFile("epub-", ".zip", ctx.cacheDir)
            ctx.contentResolver.openInputStream(uri)!!.use { i -> tmp.outputStream().use { i.copyTo(it) } }
            ZipFile(tmp).use { z ->
                for (e in z.entries()) {
                    if (e.isDirectory) continue
                    val out = File(dir, e.name)
                    if (!out.canonicalPath.startsWith(dir.canonicalPath + File.separator)) continue   // nome malicioso (../)
                    out.parentFile?.mkdirs()
                    z.getInputStream(e).use { i -> out.outputStream().use { i.copyTo(it) } }
                }
            }
            tmp.delete()
            File(dir, ".pronto").writeText("ok")
        }
        val container = File(dir, "META-INF/container.xml").takeIf { it.exists() }?.readText()
            ?: throw IllegalStateException("EPUB inválido (falta o META-INF/container.xml).")
        val opfPath = Regex("full-path=\"([^\"]+)\"").find(container)?.groupValues?.get(1) ?: throw IllegalStateException("EPUB inválido.")
        val opf = File(dir, opfPath)
        val xml = opf.readText()
        val items = Regex("<(?:\\w+:)?item\\b[^>]*>").findAll(xml).associate { m ->
            val t = m.value
            (Regex("\\bid=\"([^\"]+)\"").find(t)?.groupValues?.get(1) ?: "") to (Regex("\\bhref=\"([^\"]+)\"").find(t)?.groupValues?.get(1) ?: "")
        }
        val spine = Regex("<(?:\\w+:)?itemref\\b[^>]*\\bidref=\"([^\"]+)\"").findAll(xml).mapNotNull { items[it.groupValues[1]] }
            .map { File(opf.parentFile, Uri.decode(it.substringBefore('#'))) }.filter { it.exists() }.toList()
        if (spine.isEmpty()) throw IllegalStateException("Este EPUB não tem capítulos legíveis.")
        val title = Regex("<dc:title[^>]*>([^<]+)</dc:title>").find(xml)?.groupValues?.get(1)?.trim() ?: name.substringBeforeLast('.')
        return Book(key, title, dir, spine)
    }

    private fun sp(ctx: Context) = ctx.getSharedPreferences("livros", Context.MODE_PRIVATE)
    fun pos(ctx: Context, key: String) = sp(ctx).getInt("cap_$key", 0) to sp(ctx).getFloat("rol_$key", 0f)
    fun savePos(ctx: Context, key: String, ch: Int, frac: Float) = sp(ctx).edit().putInt("cap_$key", ch).putFloat("rol_$key", frac).apply()
    fun fontSize(ctx: Context) = sp(ctx).getInt("fonte", 110)
    fun setFontSize(ctx: Context, v: Int) = sp(ctx).edit().putInt("fonte", v).apply()
    fun theme(ctx: Context) = sp(ctx).getString("tema", "claro")!!
    fun setTheme(ctx: Context, v: String) = sp(ctx).edit().putString("tema", v).apply()

    fun css(size: Int, theme: String): String {
        val (bg, fg) = when (theme) { "sepia" -> "#f4ecd8" to "#3b2f1e"; "escuro" -> "#121212" to "#d8d8d8"; else -> "#ffffff" to "#1a1a1a" }
        return "html,body{background:$bg !important;color:$fg !important;}" +
            "body{font-size:$size% !important;line-height:1.6 !important;margin:0 !important;padding:16px 18px 80px !important;" +
            "max-width:46em;margin:auto !important;word-wrap:break-word;}" +
            "img,svg{max-width:100% !important;height:auto !important;} a{color:inherit;}"
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun EpubScreen(vm: AppVm, book: Epub.Book) {
    val ctx = LocalContext.current
    val start = remember(book) { Epub.pos(ctx, book.key) }
    var ch by remember(book) { mutableIntStateOf(start.first.coerceIn(0, book.chapters.size - 1)) }
    var size by remember { mutableIntStateOf(Epub.fontSize(ctx)) }
    var theme by remember { mutableStateOf(Epub.theme(ctx)) }
    var restore by remember(book) { mutableStateOf(start.second) }
    var web by remember { mutableStateOf<WebView?>(null) }
    fun style() = web?.evaluateJavascript(
        "(function(){var s=document.getElementById('dispersio-css');if(!s){s=document.createElement('style');s.id='dispersio-css';" +
            "document.head.appendChild(s);}s.textContent=${org.json.JSONObject.quote(Epub.css(size, theme))};})()", null)
    fun saveScroll() = web?.evaluateJavascript("(window.scrollY/Math.max(1,document.body.scrollHeight-window.innerHeight))") { v ->
        Epub.savePos(ctx, book.key, ch, v?.toFloatOrNull() ?: 0f)
    }
    BackHandler { saveScroll(); vm.closeEpub() }
    val bg = when (theme) { "sepia" -> Color(0xFFF4ECD8); "escuro" -> Color(0xFF121212); else -> Color.White }
    val fg = if (theme == "escuro") Color(0xFFD8D8D8) else Color(0xFF1A1A1A)
    Column(Modifier.fillMaxSize().background(bg)) {
        Row(Modifier.fillMaxWidth().statusBarsPadding().padding(4.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton({ saveScroll(); vm.closeEpub() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Voltar", tint = fg) }
            Text(book.title, Modifier.weight(1f), color = fg, maxLines = 1, overflow = TextOverflow.Ellipsis)
            TextButton({ size = (size - 10).coerceAtLeast(70); Epub.setFontSize(ctx, size); style() }) { Text("A−", color = fg) }
            TextButton({ size = (size + 10).coerceAtMost(220); Epub.setFontSize(ctx, size); style() }) { Text("A+", color = fg) }
        }
        AndroidView(factory = { c ->
            WebView(c).apply {
                settings.javaScriptEnabled = true
                settings.allowFileAccess = true
                settings.allowContentAccess = false
                settings.blockNetworkLoads = true
                webViewClient = object : WebViewClient() {
                    override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                        val s = request.url.scheme
                        return if (s == "file") null else WebResourceResponse("text/plain", "utf-8", ByteArrayInputStream(ByteArray(0)))
                    }
                    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                        val u = request.url
                        if (u.scheme == "file") {
                            val f = File(u.path ?: "")
                            val i = book.chapters.indexOfFirst { it.canonicalPath == f.canonicalPath }
                            if (i >= 0) { ch = i; restore = 0f }
                            return i < 0
                        }
                        return true          // links externos não abrem dentro do livro
                    }
                    override fun onPageFinished(view: WebView, url: String) {
                        style()
                        val r = restore
                        if (r > 0f) view.postDelayed({ view.evaluateJavascript("window.scrollTo(0,(document.body.scrollHeight-window.innerHeight)*$r)", null) }, 150)
                        restore = 0f
                    }
                }
                web = this
            }
        }, update = { w ->
            val target = Uri.fromFile(book.chapters[ch]).toString()
            if (w.url != target) w.loadUrl(target)
        }, modifier = Modifier.weight(1f).fillMaxWidth())
        Row(Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 8.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton({ if (ch > 0) { saveScroll(); ch--; restore = 0f; Epub.savePos(ctx, book.key, ch, 0f) } }, enabled = ch > 0) { Text("‹ Anterior", color = fg) }
            Spacer(Modifier.weight(1f))
            listOf("claro" to "Claro", "sepia" to "Sépia", "escuro" to "Escuro").forEach { (k, l) ->
                FilterChip(theme == k, { theme = k; Epub.setTheme(ctx, k); style() }, label = { Text(l, style = MaterialTheme.typography.labelSmall) })
            }
            Spacer(Modifier.weight(1f))
            Text("${ch + 1}/${book.chapters.size}", color = fg, style = MaterialTheme.typography.labelSmall)
            TextButton({ if (ch < book.chapters.size - 1) { ch++; restore = 0f; Epub.savePos(ctx, book.key, ch, 0f) } },
                enabled = ch < book.chapters.size - 1) { Text("Próximo ›", color = fg) }
        }
    }
}
