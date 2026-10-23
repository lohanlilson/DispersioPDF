package io.github.lohanlilson.lumenpdf

import android.app.Application
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.compose.ui.geometry.Offset
import com.tom_roush.pdfbox.cos.COSDictionary
import com.tom_roush.pdfbox.pdmodel.PDDocument
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

enum class Tool { NONE, INK, NOTE, TEXT, CHECK, CROSS, SIGN, CERT }

/** Documento aberto no visualizador e o estado da tela dele. */
class ViewerDoc(pdf: OpenPdf, uri: String, val name: String, val startPage: Int, val password: String?) {
    var pdf by mutableStateOf(pdf)
    var uri by mutableStateOf(uri)
    var zoom by mutableFloatStateOf(1f)
    var night by mutableStateOf(false)
    var page by mutableIntStateOf(startPage)
    var query by mutableStateOf("")
    val hits = mutableStateListOf<SearchHit>()
    var hitIndex by mutableIntStateOf(-1)
    var searching by mutableStateOf(false)
    var searchPage by mutableIntStateOf(0)
    val pageCount get() = pdf.sizes.size

    // edição
    var tool by mutableStateOf(Tool.NONE)
    var editing by mutableStateOf(false)
    var selection by mutableStateOf<TextSelection?>(null)
    var work: java.io.File? = null
    var version = 0
    val undo = ArrayDeque<java.io.File>()
    val redo = ArrayDeque<java.io.File>()
    var dirty by mutableStateOf(false)
    var canUndo by mutableStateOf(false)
    var canRedo by mutableStateOf(false)
    var fields by mutableStateOf<List<Pair<FormField, FracRect>>>(emptyList())
    var inkColor by mutableStateOf(0xFFD7373F)
    var inkWidth by mutableFloatStateOf(2f)
    val strokes = mutableStateListOf<Pair<Int, List<Offset>>>()   // (página, pontos em frações da largura)
    var busy by mutableStateOf(false)
    var signatures by mutableStateOf<List<SigInfo>>(emptyList())
    /** últimas imagens exibidas por página (marcador enquanto a nova renderização não fica pronta) */
    val lastBitmaps = android.util.LruCache<Int, androidx.compose.ui.graphics.ImageBitmap>(10)
}

data class PendingPassword(val uri: Uri, val name: String, val wrong: Boolean)

class AppVm(app: Application) : AndroidViewModel(app) {
    /** edições em fila: um toque durante outra edição espera a vez em vez de ser descartado */
    private val editLock = kotlinx.coroutines.sync.Mutex()
    private val lumen = app as LumenApp
    val engine get() = lumen.engine
    val recents get() = lumen.recents

    var doc by mutableStateOf<ViewerDoc?>(null)
        private set
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
    var password by mutableStateOf<PendingPassword?>(null)
    var recentList by mutableStateOf(recents.list())
        private set
    var update by mutableStateOf<UpdateInfo?>(null)
    private var checkedUpdate = false

    fun refreshRecents() {
        recentList = recents.list()
    }

    /** fromPicker = escolhido pelo seletor do Android (permissão permanente); senão, recebido de outro app. */
    fun open(uri: Uri, fromPicker: Boolean) = viewModelScope.launch {
        loading = true
        try {
            val name = withContext(Dispatchers.IO) { displayName(getApplication(), uri) }
            val ready = withContext(Dispatchers.IO) { prepareUri(getApplication(), uri, fromPicker) }
            openPrepared(ready, name, null)
        } catch (e: Exception) {
            error = "Não foi possível abrir o arquivo.\n${e.message ?: e.javaClass.simpleName}"
        } finally {
            loading = false
        }
    }

    fun openRecent(r: RecentDoc) = viewModelScope.launch {
        loading = true
        try {
            openPrepared(Uri.parse(r.uri), r.name, null)
        } catch (e: Exception) {
            error = "Não foi possível abrir “${r.name}”. Ele pode ter sido movido ou apagado."
        } finally {
            loading = false
        }
    }

    fun submitPassword(pwd: String) = viewModelScope.launch {
        val p = password ?: return@launch
        password = null
        loading = true
        try {
            openPrepared(p.uri, p.name, pwd)
        } catch (e: Exception) {
            error = "Não foi possível abrir o arquivo.\n${e.message ?: ""}"
        } finally {
            loading = false
        }
    }

    private suspend fun openPrepared(uri: Uri, name: String, pwd: String?) {
        val pdf = try {
            engine.open(getApplication(), uri, pwd)
        } catch (e: PasswordNeeded) {
            password = PendingPassword(uri, name, pwd != null)
            return
        }
        doc?.let { closeDoc() }
        val key = uri.toString()
        val start = recents.list().firstOrNull { it.uri == key }?.page?.coerceIn(0, pdf.sizes.size - 1) ?: 0
        recents.touch(key, name)
        doc = ViewerDoc(pdf, key, name, start, pwd)
        refreshRecents()
        loadFields(doc!!)
    }

    // ------------------------------------------------------------ edição
    private fun editDir(d: ViewerDoc) = File(getApplication<Application>().cacheDir, "edicao/${sha1(d.uri)}")

    /** Aplica uma edição (PDFBox) e reabre a nova versão no visualizador. */
    fun edit(d: ViewerDoc, what: String, block: (PDDocument) -> Collection<COSDictionary>) = viewModelScope.launch {
        editLock.lock()
        d.busy = true
        try {
            val app = getApplication<Application>()
            val src = d.work ?: withContext(Dispatchers.IO) {
                val dir = editDir(d).apply { deleteRecursively(); mkdirs() }
                val f = File(dir, "v0.pdf")
                app.contentResolver.openInputStream(Uri.parse(d.uri))!!.use { i -> f.outputStream().use { i.copyTo(it) } }
                f
            }
            d.version++
            val dst = File(src.parentFile, "v${d.version}.pdf")
            withContext(Dispatchers.IO) {
                Editor.author = authorName()
                Editor.apply(src, dst, d.password, block)
            }
            d.undo.addLast(src)
            d.redo.clear()
            d.work = dst
            d.dirty = true
            reopen(d, dst)
        } catch (e: Exception) {
            error = "Não foi possível $what.\n${e.message ?: e.javaClass.simpleName}"
        } finally {
            d.busy = false
            d.canUndo = d.undo.isNotEmpty()
            d.canRedo = d.redo.isNotEmpty()
            editLock.unlock()
        }
    }

    private suspend fun reopen(d: ViewerDoc, f: File) {
        val newPdf = engine.open(getApplication(), Uri.fromFile(f), d.password)
        android.util.Log.i("LumenPdf", "reaberto: ${newPdf.id} (${f.length()} bytes)")
        val old = d.pdf
        d.pdf = newPdf
        engine.close(old)
        loadFields(d)
    }

    fun undo(d: ViewerDoc) = viewModelScope.launch {
        val prev = d.undo.removeLastOrNull() ?: return@launch
        d.work?.let { d.redo.addLast(it) }
        d.work = prev
        d.dirty = true
        reopen(d, prev)
        d.canUndo = d.undo.isNotEmpty()
        d.canRedo = d.redo.isNotEmpty()
    }

    fun redo(d: ViewerDoc) = viewModelScope.launch {
        val next = d.redo.removeLastOrNull() ?: return@launch
        d.work?.let { d.undo.addLast(it) }
        d.work = next
        d.dirty = true
        reopen(d, next)
        d.canUndo = d.undo.isNotEmpty()
        d.canRedo = d.redo.isNotEmpty()
    }

    fun loadFields(d: ViewerDoc) = viewModelScope.launch {
        val app = getApplication<Application>()
        val list = runCatching {
            withContext(Dispatchers.IO) {
                val f = d.work
                if (f != null) PDDocument.load(f, d.password ?: "").use { Editor.fields(it) }
                else app.contentResolver.openInputStream(Uri.parse(d.uri))!!.use { s ->
                    PDDocument.load(s, d.password ?: "").use { Editor.fields(it) }
                }
            }
        }.getOrDefault(emptyList())
        d.fields = list.filter { it.page < d.pageCount }.map { it to engine.fracOf(d.pdf, it.page, it.rect) }
        d.signatures = if (list.any { it.kind == FormField.Kind.SIGNATURE && it.value.isNotEmpty() }) runCatching {
            withContext(Dispatchers.IO) {
                val bytes = d.work?.readBytes() ?: app.contentResolver.openInputStream(Uri.parse(d.uri))!!.use { it.readBytes() }
                PdfSigner.validate(bytes)
            }
        }.getOrDefault(emptyList()) else emptyList()
    }

    /** Assina com certificado digital (gravação incremental) e abre a versão assinada. */
    fun signWithCert(d: ViewerDoc, cert: suspend () -> SigningCert, page: Int, rect: android.graphics.RectF, field: String?,
                     reason: String, location: String, tsa: Boolean) = viewModelScope.launch {
        editLock.lock()
        d.busy = true
        try {
            val app = getApplication<Application>()
            val sc = withContext(Dispatchers.IO) { cert() }
            val src = d.work ?: withContext(Dispatchers.IO) {
                val dir = editDir(d).apply { deleteRecursively(); mkdirs() }
                File(dir, "v0.pdf").also { f ->
                    app.contentResolver.openInputStream(Uri.parse(d.uri))!!.use { i -> f.outputStream().use { i.copyTo(it) } }
                }
            }
            val res = withContext(Dispatchers.IO) { PdfSigner.sign(src, d.password, sc, page, rect, field, reason, location, tsa) }
            d.version++
            val dst = File(src.parentFile, "v${d.version}.pdf")
            withContext(Dispatchers.IO) { dst.writeBytes(res.bytes) }
            d.undo.addLast(src)
            d.redo.clear()
            d.work = dst
            d.dirty = true
            reopen(d, dst)
            d.tool = Tool.NONE
            toast = "Assinado por ${Certs.splitName(sc.subject).first}" +
                (if (res.timestamp) " com carimbo de tempo" else "") + ". Toque em Salvar ou Compartilhar." +
                (res.problem?.let { "\n($it)" } ?: "")
        } catch (e: Exception) {
            val msg = e.message ?: e.javaClass.simpleName
            error = if (msg.contains("password", true) || msg.contains("mac", true) || msg.contains("pad block", true))
                "Senha do certificado incorreta." else "Não foi possível assinar.\n$msg"
        } finally {
            d.busy = false
            d.canUndo = d.undo.isNotEmpty()
            d.canRedo = d.redo.isNotEmpty()
            editLock.unlock()
        }
    }

    /** Operação de páginas (gravação completa). Em documento assinado, confirma antes (invalida as assinaturas). */
    fun pages(d: ViewerDoc, what: String, block: (PDDocument, MutableList<PDDocument>) -> Unit) = viewModelScope.launch {
        editLock.lock()
        d.busy = true
        try {
            val app = getApplication<Application>()
            val src = d.work ?: withContext(Dispatchers.IO) {
                val dir = editDir(d).apply { deleteRecursively(); mkdirs() }
                File(dir, "v0.pdf").also { f ->
                    app.contentResolver.openInputStream(Uri.parse(d.uri))!!.use { i -> f.outputStream().use { i.copyTo(it) } }
                }
            }
            d.version++
            val dst = File(src.parentFile, "v${d.version}.pdf")
            withContext(Dispatchers.IO) { Editor.applyFull(src, dst, d.password, block) }
            d.undo.addLast(src)
            d.redo.clear()
            d.work = dst
            d.dirty = true
            d.lastBitmaps.evictAll()
            reopen(d, dst)
        } catch (e: Exception) {
            error = "Não foi possível $what.\n${e.message ?: e.javaClass.simpleName}"
        } finally {
            d.busy = false
            d.canUndo = d.undo.isNotEmpty()
            d.canRedo = d.redo.isNotEmpty()
            editLock.unlock()
        }
    }

    /** Salva as páginas escolhidas num PDF novo (pasta do app) e devolve o arquivo. */
    suspend fun extract(d: ViewerDoc, pages: List<Int>): File = withContext(Dispatchers.IO) {
        val app = getApplication<Application>()
        val src = d.work ?: File(app.cacheDir, "extrair-origem.pdf").also { f ->
            app.contentResolver.openInputStream(Uri.parse(d.uri))!!.use { i -> f.outputStream().use { i.copyTo(it) } }
        }
        val base = d.name.removeSuffix(".pdf").removeSuffix(".PDF")
        val out = File(File(app.filesDir, "recebidos").apply { mkdirs() }, "${base}_paginas.pdf")
        Editor.extract(src, d.password, pages, out)
        out
    }

    /** Copia um arquivo escolhido (content://) para o cache e devolve o caminho. */
    suspend fun cacheCopy(u: Uri, name: String = "inserir.pdf"): File = withContext(Dispatchers.IO) {
        val f = File(getApplication<Application>().cacheDir, name)
        getApplication<Application>().contentResolver.openInputStream(u)!!.use { i -> f.outputStream().use { i.copyTo(it) } }
        f
    }

    /** Junta vários PDFs num novo arquivo e abre. */
    fun mergeAndOpen(uris: List<Uri>) = viewModelScope.launch {
        loading = true
        try {
            val app = getApplication<Application>()
            val files = uris.mapIndexed { i, u -> cacheCopy(u, "juntar_$i.pdf") }
            val stamp = java.text.SimpleDateFormat("yyyyMMdd_HHmm", java.util.Locale.US).format(java.util.Date())
            val out = File(File(app.filesDir, "recebidos").apply { mkdirs() }, "Combinado_$stamp.pdf")
            withContext(Dispatchers.IO) { Editor.merge(files, out) }
            openPrepared(Uri.fromFile(out), out.name, null)
        } catch (e: Exception) {
            error = "Não foi possível juntar os arquivos.\n${e.message ?: ""}"
        } finally {
            loading = false
        }
    }

    /** PDF gerado pelo scanner: guarda na pasta do app e abre. */
    fun openScanned(u: Uri) = viewModelScope.launch {
        loading = true
        try {
            val app = getApplication<Application>()
            val stamp = java.text.SimpleDateFormat("yyyyMMdd_HHmm", java.util.Locale.US).format(java.util.Date())
            val out = File(File(app.filesDir, "recebidos").apply { mkdirs() }, "Digitalizacao_$stamp.pdf")
            withContext(Dispatchers.IO) {
                app.contentResolver.openInputStream(u)!!.use { i -> out.outputStream().use { i.copyTo(it) } }
            }
            openPrepared(Uri.fromFile(out), out.name, null)
        } catch (e: Exception) {
            error = "Não foi possível abrir a digitalização.\n${e.message ?: ""}"
        } finally {
            loading = false
        }
    }

    /** Copia um .pfx/.p12 escolhido para a pasta do app (para reutilizar sem procurar de novo). */
    fun importPfx(u: Uri): File? = runCatching {
        val app = getApplication<Application>()
        val name = displayName(app, u)
        val dir = File(app.filesDir, "certificados").apply { mkdirs() }
        val f = File(dir, name)
        app.contentResolver.openInputStream(u)!!.use { i -> f.outputStream().use { i.copyTo(it) } }
        f
    }.getOrNull()

    /** Grava a versão editada no arquivo original. Devolve false se o local não aceita gravação. */
    fun save(d: ViewerDoc, onNeedSaveAs: () -> Unit) = viewModelScope.launch {
        val f = d.work ?: return@launch
        val app = getApplication<Application>()
        val ok = runCatching {
            withContext(Dispatchers.IO) {
                val u = Uri.parse(d.uri)
                if (u.scheme == "file") f.copyTo(File(u.path!!), overwrite = true)
                else app.contentResolver.openOutputStream(u, "wt")!!.use { o -> f.inputStream().use { it.copyTo(o) } }
            }
        }.isSuccess
        if (ok) {
            d.dirty = false
            recents.thumbFile(d.uri).delete()
            toast = "Salvo"
            if (closeAfterSave) { closeAfterSave = false; closeDoc() }
        } else onNeedSaveAs()
    }

    fun saveAs(d: ViewerDoc, target: Uri) = viewModelScope.launch {
        val app = getApplication<Application>()
        val src = d.work
        runCatching {
            withContext(Dispatchers.IO) {
                app.contentResolver.openOutputStream(target, "wt")!!.use { o ->
                    (src?.inputStream() ?: app.contentResolver.openInputStream(Uri.parse(d.uri))!!).use { it.copyTo(o) }
                }
                runCatching {
                    app.contentResolver.takePersistableUriPermission(target,
                        android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION or android.content.Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                }
            }
            val name = displayName(app, target)
            d.uri = target.toString()
            d.dirty = false
            recents.touch(d.uri, name, d.page)
            toast = "Salvo como “$name”"
            if (closeAfterSave) { closeAfterSave = false; closeDoc() }
        }.onFailure { error = "Não foi possível salvar: ${it.message}" }
    }

    var toast by mutableStateOf<String?>(null)
    var confirmClose by mutableStateOf(false)
    var closeAfterSave = false

    fun requestClose() {
        val d = doc ?: return
        if (d.dirty) confirmClose = true else closeDoc()
    }

    fun viewModelScopeLaunch(block: suspend kotlinx.coroutines.CoroutineScope.() -> Unit) = viewModelScope.launch(block = block)

    fun authorName(): String = getApplication<Application>().getSharedPreferences("prefs", 0).getString("autor", null)
        ?.takeIf { it.isNotBlank() } ?: "Lumen PDF"

    fun setAuthorName(n: String) {
        getApplication<Application>().getSharedPreferences("prefs", 0).edit().putString("autor", n.trim()).apply()
    }

    fun closeDoc() {
        val d = doc ?: return
        recents.setPage(d.uri, d.page)
        doc = null
        viewModelScope.launch { engine.close(d.pdf) }
        refreshRecents()
    }

    fun removeRecent(r: RecentDoc) {
        recents.remove(r.uri)
        refreshRecents()
    }

    fun search(d: ViewerDoc, q: String) = viewModelScope.launch {
        d.query = q
        d.hits.clear()
        d.hitIndex = -1
        if (q.isBlank()) return@launch
        d.searching = true
        try {
            val res = engine.search(d.pdf, q) { p -> d.searchPage = p }
            d.hits.addAll(res)
            d.hitIndex = res.indexOfFirst { it.page >= d.page }.let { if (it < 0 && res.isNotEmpty()) 0 else it }
        } finally {
            d.searching = false
        }
    }

    fun checkUpdate() {
        if (checkedUpdate) return
        checkedUpdate = true
        viewModelScope.launch {
            update = runCatching { Updater.check() }.getOrNull()
        }
    }

    override fun onCleared() {
        doc?.let { d -> recents.setPage(d.uri, d.page) }
        super.onCleared()
    }
}
