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
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

enum class Tool { NONE, HIGHLIGHT, INK, SHAPE, MEASURE, NOTE, TEXT, CHECK, CROSS, SIGN, CERT, EDITTEXT, REDACT, CROP, SNAP, IMAGE }

/** Comparação aberta: as duas versões e a lista de alterações. */
class CompareState(val a: OpenPdf, val b: OpenPdf, val nameA: String, val nameB: String, val changes: List<Change>,
                   val title: String, val intro: String = "")

/** Caixa sendo posicionada (rubrica, assinatura digital ou comentário a mover), em frações da largura da página. */
data class Placement(val kind: Tool, val page: Int, val l: Float, val t: Float, val r: Float, val b: Float,
                     val aspect: Float? = null, val annot: Editor.AnnotRef? = null) {
    val w get() = r - l
    val h get() = b - t
}

/** Documento aberto no visualizador e o estado da tela dele. */
class ViewerDoc(pdf: OpenPdf, uri: String, val name: String, val startPage: Int, password: String?) {
    var password: String? = password
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
    val strokes = mutableStateListOf<Pair<Int, List<Offset>>>()
    /** forma escolhida: Square | Circle | Arrow; e a que está sendo desenhada (página, início, fim em frações) */
    var shapeKind by mutableStateOf("Square")
    var shapeDraft by mutableStateOf<Triple<Int, Offset, Offset>?>(null)
    /** área desenhada com a ferramenta Recortar (página, retângulo em frações) */
    var cropDraft by mutableStateOf<Pair<Int, FracRect>?>(null)
    /** captura de área (página, retângulo) e o arquivo gerado */
    var snapDraft by mutableStateOf<Pair<Int, FracRect>?>(null)
    var snapFile by mutableStateOf<java.io.File?>(null)
    /** medidas: "dist" | "area" | "cal"; linha em andamento; pontos da área */
    var measureKind by mutableStateOf("dist")
    var measureDraft by mutableStateOf<Triple<Int, Offset, Offset>?>(null)
    var areaPts by mutableStateOf<Pair<Int, List<Offset>>?>(null)
    var scale by mutableStateOf(MeasureScale.PAPER)
    /** comprimento (pontos do PDF) da linha desenhada para calibrar a escala */
    var calLen by mutableStateOf<Double?>(null)
    /** imagem selecionada (ferramenta Imagens) */
    var selImage by mutableStateOf<PageImage?>(null)   // (página, pontos em frações da largura)
    var busy by mutableStateOf(false)
    var signatures by mutableStateOf<List<SigInfo>>(emptyList())
    var placing by mutableStateOf<Placement?>(null)
    var annots by mutableStateOf<List<Pair<Editor.AnnotRef, FracRect>>>(emptyList())
    var selAnnot by mutableStateOf<Editor.AnnotRef?>(null)
    val redactions = mutableStateListOf<Pair<Int, FracRect>>()
    /** destaques já pedidos, mostrados na hora enquanto o arquivo é gravado */
    val pendingMarks = mutableStateListOf<Triple<Int, List<FracRect>, Long>>()
    /** últimas imagens exibidas por página (marcador enquanto a nova renderização não fica pronta) */
    val lastBitmaps = android.util.LruCache<Int, androidx.compose.ui.graphics.ImageBitmap>(10)
    /** tamanhos das páginas de cada versão (reabrir sem medir de novo) */
    val sizesOf = HashMap<String, List<PageSize>>()
}

const val KEEP_PASSWORD = "\u0000manter"

/** Campos e comentários lidos do documento logo depois da edição (evita reabrir o arquivo). */
class Parsed(val fields: List<FormField>, val annots: List<Editor.AnnotRef>)

data class PendingPassword(val uri: Uri, val name: String, val wrong: Boolean)

class AppVm(app: Application) : AndroidViewModel(app) {
    /** edições em fila: um toque durante outra edição espera a vez em vez de ser descartado */
    private val editLock = kotlinx.coroutines.sync.Mutex()
    private val lumen = app as LumenApp
    val engine get() = lumen.engine
    val recents get() = lumen.recents
    val prefs get() = lumen.prefs

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

    /** pedido vindo de um atalho do ícone: "scan" | "open" */
    var pendingAction by mutableStateOf<String?>(null)

    fun refreshRecents() {
        recentList = recents.list()
        Shortcuts.updateRecents(getApplication(), recentList)
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
        val start = if (!prefs.rememberPage) 0 else recents.list().firstOrNull { it.uri == key }?.page?.coerceIn(0, pdf.sizes.size - 1) ?: 0
        recents.touch(key, name)
        doc = ViewerDoc(pdf, key, name, start, pwd).also { it.night = prefs.nightPages }
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
            val cur = currentSizes(d)
            cur?.let { d.sizesOf[src.path] = it }
            var parsed: Parsed? = null
            withContext(Dispatchers.IO) {
                Editor.author = authorName()
                Editor.apply(src, dst, d.password, block) { doc ->
                    parsed = runCatching { Parsed(Editor.fields(doc), Editor.annotations(doc)) }.getOrNull()
                }
            }
            d.undo.addLast(src)
            d.redo.clear()
            d.work = dst
            d.dirty = true
            reopen(d, dst, cur, parsed)
        } catch (e: Exception) {
            error = "Não foi possível $what.\n${e.message ?: e.javaClass.simpleName}"
        } finally {
            d.busy = false
            d.canUndo = d.undo.isNotEmpty()
            d.canRedo = d.redo.isNotEmpty()
            editLock.unlock()
        }
    }

    private fun currentSizes(d: ViewerDoc): List<PageSize>? = if (d.pdf.measured.all { it }) d.pdf.sizes.toList() else null

    /** known = tamanhos das páginas (edições que não mexem nas páginas); parsed = campos e comentários já lidos. */
    private suspend fun reopen(d: ViewerDoc, f: File, known: List<PageSize>? = null, parsed: Parsed? = null) {
        val t0 = System.currentTimeMillis()
        val newPdf = engine.open(getApplication(), Uri.fromFile(f), d.password, known)
        android.util.Log.i("LumenPdf", "reaberto: ${newPdf.id} (${f.length()} bytes) em ${System.currentTimeMillis() - t0} ms")
        known?.let { d.sizesOf[f.path] = it }
        val old = d.pdf
        d.pdf = newPdf
        engine.close(old)
        loadFields(d, parsed)
    }

    /** Grava a forma desenhada (pontos em frações da largura da página). */
    fun addShape(d: ViewerDoc, page: Int, a: Offset, b: Offset) = viewModelScope.launch {
        val pts = engine.pdfPoints(d.pdf, page, listOf(a.x to a.y, b.x to b.y))
        val kind = d.shapeKind
        val color = d.inkColor
        val width = d.inkWidth
        edit(d, "desenhar a forma") { Editor.shape(it, page, kind, pts[0], pts[1], pts[2], pts[3], color, width) }.join()
        d.shapeDraft = null
    }

    /** Destaque/sublinhado/tachado do trecho selecionado. Aparece na hora; o arquivo é gravado em seguida. */
    fun markup(d: ViewerDoc, sel: TextSelection, kind: Markup, color: Long) {
        if (sel.pdfRects.isEmpty()) return
        val mark = Triple(sel.page, sel.rects, if (kind == Markup.HIGHLIGHT) color else 0L)
        if (kind == Markup.HIGHLIGHT) d.pendingMarks += mark
        edit(d, kind.label.lowercase()) { Editor.markup(it, sel.page, sel.pdfRects, kind, color) }
            .invokeOnCompletion { d.pendingMarks.remove(mark) }
    }

    /** Documento aberto no PDFBox só para leitura (editar texto), mantido até a versão mudar. */
    private val readLock = kotlinx.coroutines.sync.Mutex()
    private var readDoc: Pair<String, PDDocument>? = null

    private suspend fun <T> withReadDoc(d: ViewerDoc, block: (PDDocument) -> T): T = readLock.withLock {
        withContext(Dispatchers.IO) {
            val key = (d.work?.path ?: d.uri) + "|" + (d.password ?: "")
            val cur = readDoc
            val doc = if (cur != null && cur.first == key) cur.second else {
                cur?.second?.let { runCatching { it.close() } }
                readDoc = null
                val app = getApplication<Application>()
                val f = d.work
                val nd = if (f != null) PDDocument.load(f, d.password ?: "")
                    else app.contentResolver.openInputStream(Uri.parse(d.uri))!!.use { PDDocument.load(it, d.password ?: "") }
                readDoc = key to nd
                nd
            }
            block(doc)
        }
    }

    /** Abre o documento para leitura com antecedência (ao escolher a ferramenta "Editar texto"). */
    fun prewarmRead(d: ViewerDoc, page: Int = d.page) = viewModelScope.launch {
        // processa a página uma vez (carrega as fontes): o primeiro toque já sai rápido
        runCatching { withReadDoc(d) { TextEdit.analyze(it, page, android.graphics.RectF(0f, 0f, 0f, 0f), 0f, 0f) } }
    }

    private fun dropReadDoc() {
        val cur = readDoc ?: return
        viewModelScope.launch { readLock.withLock { if (readDoc === cur) { runCatching { cur.second.close() }; readDoc = null } } }
    }

    /** Trecho de texto (mesmo estilo) sob o dedo, para a ferramenta "Editar texto". */
    suspend fun analyzeRun(d: ViewerDoc, line: TextLine, px: Float, py: Float): TextRun? =
        runCatching { withReadDoc(d) { TextEdit.analyze(it, line.page, line.rect, px, py) } }
            .onFailure { android.util.Log.w("LumenPdf", "analisar texto", it) }.getOrNull()

    /** Troca o texto mantendo fonte, negrito/itálico, tamanho e cor. */
    fun replaceText(d: ViewerDoc, line: TextLine, px: Float, py: Float, text: String) {
        var used: String? = null
        edit(d, "editar o texto") { doc ->
            val r = runCatching { TextEdit.replace(doc, line.page, line.rect, px, py, text) }
                .onFailure { android.util.Log.w("LumenPdf", "editar texto", it) }.getOrNull()
            if (r != null) { used = r.fontUsed; r.changed }
            else Editor.replaceText(doc, line.page, line.rect, line.x, line.baseline, text, line.size, 0xFF1C1B22)
        }.invokeOnCompletion {
            val u = used
            if (u != null && u != "fonte original do PDF" && u != "—")
                toast = "A fonte original não tem todas as letras do novo texto; usei $u (mesmas medidas e estilo)."
        }
    }

    fun undo(d: ViewerDoc) = viewModelScope.launch {
        val prev = d.undo.removeLastOrNull() ?: return@launch
        d.work?.let { w -> d.redo.addLast(w); currentSizes(d)?.let { d.sizesOf[w.path] = it } }
        d.work = prev
        d.dirty = true
        reopen(d, prev, d.sizesOf[prev.path])
        d.canUndo = d.undo.isNotEmpty()
        d.canRedo = d.redo.isNotEmpty()
    }

    fun redo(d: ViewerDoc) = viewModelScope.launch {
        val next = d.redo.removeLastOrNull() ?: return@launch
        d.work?.let { w -> d.undo.addLast(w); currentSizes(d)?.let { d.sizesOf[w.path] = it } }
        d.work = next
        d.dirty = true
        reopen(d, next, d.sizesOf[next.path])
        d.canUndo = d.undo.isNotEmpty()
        d.canRedo = d.redo.isNotEmpty()
    }

    fun loadFields(d: ViewerDoc, parsed: Parsed? = null) = viewModelScope.launch {
        val app = getApplication<Application>()
        // uma leitura só do arquivo para campos e comentários (ou nenhuma, se a edição já trouxe)
        val p = parsed ?: runCatching {
            withContext(Dispatchers.IO) {
                val f = d.work
                val doc = if (f != null) PDDocument.load(f, d.password ?: "")
                    else app.contentResolver.openInputStream(Uri.parse(d.uri))!!.use { s -> PDDocument.load(s, d.password ?: "") }
                doc.use { Parsed(Editor.fields(it), Editor.annotations(it)) }
            }
        }.getOrDefault(Parsed(emptyList(), emptyList()))
        val list = p.fields
        val pdfNow0 = d.pdf
        val fl = list.filter { it.page < d.pageCount }
        val al = p.annots.filter { it.page < d.pageCount }
        val fr = engine.fracOfAll(pdfNow0, fl.map { it.page to it.rect } + al.map { it.page to it.rect })
        d.fields = fl.mapIndexed { k, f -> f to fr[k] }
        d.annots = al.mapIndexed { k, a -> a to fr[fl.size + k] }
        d.selAnnot = null
        val signed = list.any { it.kind == FormField.Kind.SIGNATURE && it.value.isNotEmpty() }
        val pdfNow = d.pdf
        val bytes = if (signed) runCatching {
            withContext(Dispatchers.IO) { d.work?.readBytes() ?: app.contentResolver.openInputStream(Uri.parse(d.uri))!!.use { it.readBytes() } }
        }.getOrNull() else null
        d.signatures = bytes?.let { b ->
            runCatching { withContext(Dispatchers.IO) { IcpTrust.init(app); PdfSigner.validate(b) } }.getOrNull()
        } ?: emptyList()
        // depois, com internet: listas de revogação (pode demorar; a tela já mostra o resultado sem elas)
        if (bytes != null && d.signatures.any { it.identity?.status == IcpTrust.Status.NO_REVOCATION_CHECK }) {
            val online = runCatching { withContext(Dispatchers.IO) { PdfSigner.validate(bytes, online = true) } }.getOrNull()
            if (online != null && d.pdf === pdfNow) d.signatures = online
        }
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
            val cur = currentSizes(d)
            cur?.let { d.sizesOf[src.path] = it }
            d.undo.addLast(src)
            d.redo.clear()
            d.work = dst
            d.dirty = true
            reopen(d, dst, cur)
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
    fun pages(d: ViewerDoc, what: String, newPassword: String? = KEEP_PASSWORD, done: (Long, Long) -> Unit = { _, _ -> },
              block: (PDDocument, MutableList<PDDocument>) -> Unit) = viewModelScope.launch {
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
            currentSizes(d)?.let { d.sizesOf[src.path] = it }
            withContext(Dispatchers.IO) { Editor.applyFull(src, dst, d.password, block) }
            if (newPassword != KEEP_PASSWORD) d.password = newPassword
            done(src.length(), dst.length())
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

    /** Divide o documento e grava as partes na pasta escolhida (árvore do Android). */
    fun split(d: ViewerDoc, mode: String, value: String, tree: Uri) = viewModelScope.launch {
        val app = getApplication<Application>()
        try {
            progress = "Dividindo…"
            val files = withContext(Dispatchers.IO) {
                val src = d.work ?: File(app.cacheDir, "dividir-origem.pdf").also { f ->
                    app.contentResolver.openInputStream(Uri.parse(d.uri))!!.use { i -> f.outputStream().use { i.copyTo(it) } }
                }
                val groups = Editor.splitGroups(src, d.password, mode, value)
                if (groups.size < 2) return@withContext emptyList()
                val tmp = File(app.cacheDir, "dividir").apply { deleteRecursively() }
                val parts = Editor.split(src, d.password, groups, tmp, d.name.removeSuffix(".pdf").removeSuffix(".PDF"))
                val r = app.contentResolver
                val parent = android.provider.DocumentsContract.buildDocumentUriUsingTree(tree,
                    android.provider.DocumentsContract.getTreeDocumentId(tree))
                parts.map { f ->
                    val u = android.provider.DocumentsContract.createDocument(r, parent, "application/pdf", f.name)
                        ?: error("Não foi possível criar ${f.name} na pasta")
                    r.openOutputStream(u)!!.use { o -> f.inputStream().use { it.copyTo(o) } }
                    f.length()
                }
            }
            toast = if (files.isEmpty()) "Nada a dividir: o resultado seria um arquivo só."
                else "${files.size} arquivos salvos na pasta escolhida (maior: %.1f MB)".format(files.max() / 1048576.0)
        } catch (e: Exception) {
            error = "Não foi possível dividir.\n${e.message ?: e.javaClass.simpleName}"
        } finally {
            progress = null
        }
    }

    /** Volta o documento para uma versão anterior guardada (vira uma edição: dá para desfazer; salve para manter). */
    fun restoreVersion(d: ViewerDoc, backup: File) = viewModelScope.launch {
        editLock.lock()
        d.busy = true
        try {
            val app = getApplication<Application>()
            val src = d.work ?: withContext(Dispatchers.IO) {
                val dir = editDir(d).apply { deleteRecursively(); mkdirs() }
                File(dir, "v0.pdf").also { f -> app.contentResolver.openInputStream(Uri.parse(d.uri))!!.use { i -> f.outputStream().use { i.copyTo(it) } } }
            }
            currentSizes(d)?.let { d.sizesOf[src.path] = it }
            d.version++
            val dst = File(src.parentFile, "v${d.version}.pdf")
            withContext(Dispatchers.IO) { backup.copyTo(dst, overwrite = true) }
            d.undo.addLast(src)
            d.redo.clear()
            d.work = dst
            d.dirty = true
            d.lastBitmaps.evictAll()
            reopen(d, dst)
            toast = "Versão anterior restaurada. Toque em Salvar para mantê-la (ou Desfazer)."
        } catch (e: Exception) {
            error = "Não foi possível restaurar.\n${e.message ?: e.javaClass.simpleName}"
        } finally {
            d.busy = false
            d.canUndo = d.undo.isNotEmpty()
            d.canRedo = d.redo.isNotEmpty()
            editLock.unlock()
        }
    }

    private suspend fun workFile(d: ViewerDoc, name: String): File = d.work ?: withContext(Dispatchers.IO) {
        val app = getApplication<Application>()
        File(app.cacheDir, name).also { f -> app.contentResolver.openInputStream(Uri.parse(d.uri))!!.use { i -> f.outputStream().use { i.copyTo(it) } } }
    }

    /** Páginas em branco (sem texto, comentários nem conteúdo visível). */
    suspend fun findBlank(d: ViewerDoc): List<Int> {
        progress = "Procurando páginas em branco…"
        try {
            val withAnnots = d.annots.map { it.first.page }.toSet() + d.fields.map { it.first.page }.toSet()
            return (0 until d.pageCount).filter { p ->
                progress = "Procurando páginas em branco… ${p + 1} de ${d.pageCount}"
                PageAnalysis.isBlank(engine, d.pdf, p, p in withAnnots)
            }
        } finally {
            progress = null
        }
    }

    /** Endireita as páginas digitalizadas tortas. */
    fun deskew(d: ViewerDoc) = viewModelScope.launch {
        try {
            val fixes = ArrayList<Pair<Int, Double>>()
            for (p in 0 until d.pageCount) {
                progress = "Verificando inclinação… página ${p + 1} de ${d.pageCount}"
                val chars = engine.pageChars(d.pdf, p).text.count { !it.isWhitespace() && it != '\u0000' }
                if (chars > 15) continue   // página com texto digital: não é digitalização
                val a = PageAnalysis.skew(engine, d.pdf, p)
                if (kotlin.math.abs(a) >= 0.3) fixes += p to a
            }
            progress = null
            if (fixes.isEmpty()) { toast = "Nenhuma página digitalizada torta encontrada."; return@launch }
            edit(d, "endireitar as páginas") { doc -> fixes.flatMap { (p, a) -> PageEdit.rotateContent(doc, p, a) } }.join()
            d.lastBitmaps.evictAll()
            toast = "Endireitadas: " + fixes.joinToString(", ") { (p, a) -> "pág. ${p + 1} (%+.1f°)".format(a) } + ". Dá para desfazer."
        } catch (e: Exception) {
            error = "Não foi possível endireitar.\n${e.message ?: e.javaClass.simpleName}"
        } finally {
            progress = null
        }
    }

    /** Recorta páginas: rects = página → retângulo em frações (null = automático, pelas bordas do conteúdo). */
    fun crop(d: ViewerDoc, pages: List<Int>, area: FracRect?) = viewModelScope.launch {
        try {
            val boxes = HashMap<Int, FloatArray>()
            for ((k, p) in pages.withIndex()) {
                progress = "Analisando margens… ${k + 1} de ${pages.size}"
                val r = area ?: PageAnalysis.contentBox(engine, d.pdf, p) ?: continue
                boxes[p] = engine.pdfPoints(d.pdf, p, listOf(r.l to r.t, r.r to r.b))
            }
            progress = null
            if (boxes.isEmpty()) { toast = "Nada para recortar."; return@launch }
            pages(d, "recortar") { doc, _ -> boxes.forEach { (p, b) -> PageEdit.crop(doc, p, b[0], b[1], b[2], b[3]) } }.join()
            toast = "${boxes.size} página(s) recortada(s). Dá para desfazer."
        } catch (e: Exception) {
            error = "Não foi possível recortar.\n${e.message ?: e.javaClass.simpleName}"
        } finally {
            progress = null
        }
    }

    fun extractImages(d: ViewerDoc) = viewModelScope.launch {
        try {
            progress = "Extraindo imagens…"
            val app = getApplication<Application>()
            val src = workFile(d, "imagens-origem.pdf")
            val n = withContext(Dispatchers.IO) { PageEdit.extractImages(app, src, d.password, d.name.removeSuffix(".pdf").removeSuffix(".PDF")) }
            toast = if (n == 0) "Este documento não tem imagens." else "$n imagem(ns) salvas na galeria (Imagens › Lumen PDF)"
        } catch (e: Exception) {
            error = "Não foi possível extrair as imagens.\n${e.message ?: e.javaClass.simpleName}"
        } finally {
            progress = null
        }
    }

    fun saveAsPdfA(d: ViewerDoc, target: Uri) = viewModelScope.launch {
        try {
            progress = "Convertendo para PDF/A…"
            val app = getApplication<Application>()
            val src = workFile(d, "pdfa-origem.pdf")
            val problems = withContext(Dispatchers.IO) {
                val out = File(app.cacheDir, "pdfa-saida.pdf")
                val title = d.name.removeSuffix(".pdf").removeSuffix(".PDF")
                val pr = PdfA.convert(app, src, d.password, out, title)
                app.contentResolver.openOutputStream(target, "wt")!!.use { o -> out.inputStream().use { it.copyTo(o) } }
                pr
            }
            if (problems.isEmpty()) toast = "Salvo como PDF/A-2b."
            else error = "Salvo como PDF/A-2b, com avisos:\n• " + problems.joinToString("\n• ")
        } catch (e: Exception) {
            error = "Não foi possível converter para PDF/A.\n${e.message ?: e.javaClass.simpleName}"
        } finally {
            progress = null
        }
    }

    // ------------------------------------------------------------ links, substituir, comentários, medidas, imagens
    private val urlRx = Regex("""(?:https?://|www\.)[^\s<>()"']+[^\s<>()"'.,;:!?)]""", RegexOption.IGNORE_CASE)
    private val mailRx = Regex("""[\w.+-]+@[\w-]+(?:\.[\w-]+)+""")

    fun autolink(d: ViewerDoc) = viewModelScope.launch {
        try {
            val items = HashMap<Int, MutableList<Pair<String, List<android.graphics.RectF>>>>()
            for (p in 0 until d.pageCount) {
                progress = "Procurando endereços… página ${p + 1} de ${d.pageCount}"
                val pc = engine.pageChars(d.pdf, p)
                for (m in urlRx.findAll(pc.text) + mailRx.findAll(pc.text)) {
                    val u = m.value
                    val uri = when { '@' in u && !u.contains("://") -> "mailto:$u"; u.startsWith("http", true) -> u; else -> "https://$u" }
                    items.getOrPut(p) { ArrayList() } += uri to pc.selection(m.range.first, m.range.last).pdfRects
                }
            }
            progress = null
            val n = items.values.sumOf { l -> l.sumOf { it.second.size } }
            if (n == 0) { toast = "Nenhum endereço de site ou e-mail encontrado."; return@launch }
            edit(d, "criar os links") { doc -> items.flatMap { (p, l) -> MoreEdit.links(doc, p, l) } }.join()
            toast = "Links criados para ${items.values.sumOf { it.size }} endereço(s). Dá para desfazer."
        } finally {
            progress = null
        }
    }

    fun replaceAll(d: ViewerDoc, find: String, repl: String, matchCase: Boolean, wholeWord: Boolean) = viewModelScope.launch {
        if (find.isEmpty()) return@launch
        var pat = Regex.escape(find)
        if (wholeWord) pat = "(?<![\\p{L}\\p{N}_])$pat(?![\\p{L}\\p{N}_])"
        val rx = if (matchCase) Regex(pat) else Regex(pat, RegexOption.IGNORE_CASE)
        val norm = { x: String -> x.replace(Regex("\\s+"), "") }
        val pages = (0 until d.pageCount).filter { p ->
            val t = engine.pageChars(d.pdf, p).text
            if (matchCase) norm(t).contains(norm(find)) else norm(t).contains(norm(find), ignoreCase = true)
        }
        if (pages.isEmpty()) { toast = "“$find” não foi encontrado."; return@launch }
        var count = 0
        progress = "Substituindo…"
        try {
            edit(d, "substituir o texto") { doc ->
                pages.flatMap { p -> TextEdit.replaceInPage(doc, p, rx, repl).let { (ch, n) -> count += n; ch } }
            }.join()
        } finally {
            progress = null
        }
        toast = if (count == 0) "“$find” não foi encontrado no texto editável." else "$count substituição(ões). Dá para desfazer."
    }

    fun exportComments(d: ViewerDoc, target: Uri) = viewModelScope.launch {
        try {
            val app = getApplication<Application>()
            val src = workFile(d, "fdf-origem.pdf")
            val n = withContext(Dispatchers.IO) {
                PDDocument.load(src, d.password ?: "").use { doc ->
                    app.contentResolver.openOutputStream(target, "wt")!!.use { MoreEdit.exportFdf(doc, d.name, it) }
                }
            }
            toast = if (n == 0) "O documento não tem comentários (o arquivo ficou vazio)." else "$n comentário(s) exportado(s)."
        } catch (e: Exception) {
            error = "Não foi possível exportar.\n${e.message ?: e.javaClass.simpleName}"
        }
    }

    fun importComments(d: ViewerDoc, src: Uri) = viewModelScope.launch {
        try {
            val bytes = withContext(Dispatchers.IO) { getApplication<Application>().contentResolver.openInputStream(src)!!.use { it.readBytes() } }
            var n = 0
            edit(d, "importar os comentários") { doc -> MoreEdit.importFdf(doc, java.io.ByteArrayInputStream(bytes)).let { (ch, k) -> n = k; ch } }.join()
            toast = if (n == 0) "Nenhum comentário encontrado nesse arquivo." else "$n comentário(s) importado(s). Dá para desfazer."
        } catch (e: Exception) {
            error = "Não foi possível importar.\n${e.message ?: e.javaClass.simpleName}"
        }
    }

    /** Recorta a área da página como imagem (alta resolução). */
    fun snapshot(d: ViewerDoc, page: Int, r: FracRect) = viewModelScope.launch {
        try {
            val full = engine.render(d.pdf, page, 2400)
            val w = full.width
            val x = (r.l * w).toInt().coerceIn(0, w - 1); val y = (r.t * w).toInt().coerceIn(0, full.height - 1)
            val cw = ((r.r - r.l) * w).toInt().coerceIn(1, w - x); val ch = ((r.b - r.t) * w).toInt().coerceIn(1, full.height - y)
            val bmp = android.graphics.Bitmap.createBitmap(full, x, y, cw, ch)
            val f = withContext(Dispatchers.IO) {
                File(File(getApplication<Application>().cacheDir, "capturas").apply { mkdirs() },
                    "${d.name.removeSuffix(".pdf").removeSuffix(".PDF")}_pag${page + 1}.png").also { out ->
                    out.outputStream().use { bmp.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
                }
            }
            d.snapFile = f
        } catch (e: Exception) {
            error = "Não foi possível capturar.\n${e.message ?: e.javaClass.simpleName}"
        }
    }

    fun saveToGallery(f: File) = viewModelScope.launch(Dispatchers.IO) {
        val app = getApplication<Application>()
        val values = android.content.ContentValues().apply {
            put(android.provider.MediaStore.Images.Media.DISPLAY_NAME, f.name)
            put(android.provider.MediaStore.Images.Media.MIME_TYPE, "image/png")
            if (android.os.Build.VERSION.SDK_INT >= 29) put(android.provider.MediaStore.Images.Media.RELATIVE_PATH, "Pictures/Lumen PDF")
        }
        val uri = app.contentResolver.insert(android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
        if (uri != null) app.contentResolver.openOutputStream(uri)?.use { o -> f.inputStream().use { it.copyTo(o) } }
        withContext(Dispatchers.Main) { toast = "Imagem salva na galeria (Imagens › Lumen PDF)" }
    }

    fun loadScale(d: ViewerDoc) {
        d.scale = MeasureScale.parse(getApplication<Application>().getSharedPreferences("escalas", 0).getString(d.uri, null)) ?: MeasureScale.PAPER
    }

    fun setScale(d: ViewerDoc, s: MeasureScale) {
        d.scale = s
        getApplication<Application>().getSharedPreferences("escalas", 0).edit().putString(d.uri, s.store()).apply()
    }

    /** Linha de medida (ou calibração) entre dois pontos em frações. Devolve o comprimento em pontos do PDF. */
    suspend fun measurePts(d: ViewerDoc, page: Int, pts: List<Offset>): FloatArray = engine.pdfPoints(d.pdf, page, pts.map { it.x to it.y })

    fun addMeasureLine(d: ViewerDoc, page: Int, a: Offset, b: Offset) = viewModelScope.launch {
        val p = measurePts(d, page, listOf(a, b))
        val len = distPts(p[0], p[1], p[2], p[3]) * d.scale.factor
        val text = MoreEdit.fmtMeasure(len, d.scale.unit)
        edit(d, "medir") { MoreEdit.measureLine(it, page, p[0], p[1], p[2], p[3], text, 0xFF1473E6) }.join()
        d.measureDraft = null
        toast = "Distância: $text (escala ${d.scale.label})"
    }

    fun addMeasureArea(d: ViewerDoc) = viewModelScope.launch {
        val (page, pts) = d.areaPts ?: return@launch
        if (pts.size < 3) return@launch
        val p = measurePts(d, page, pts)
        val pp = (pts.indices).map { p[it * 2] to p[it * 2 + 1] }
        val area = MoreEdit.polygonArea(pp) * d.scale.factor * d.scale.factor
        val text = MoreEdit.fmtMeasure(area, d.scale.unit, area = true)
        edit(d, "medir a área") { MoreEdit.measureArea(it, page, pp, text, 0xFF1473E6) }.join()
        d.areaPts = null
        toast = "Área: $text (escala ${d.scale.label})"
    }

    /** Imagem sob o dedo (ferramenta Imagens): seleciona e abre a caixa de mover/redimensionar. */
    fun pickImage(d: ViewerDoc, page: Int, fx: Float, fy: Float) = viewModelScope.launch {
        val imgs = runCatching { withReadDoc(d) { PageImages.list(it, page) } }.getOrDefault(emptyList())
        if (imgs.isEmpty()) { toast = "Nenhuma imagem nesta página."; return@launch }
        val fr = engine.fracOfAll(d.pdf, imgs.map { page to it.rect })
        val k = fr.indices.lastOrNull { fx in fr[it].l..fr[it].r && fy in fr[it].t..fr[it].b }
        if (k == null) { toast = "Toque em cima de uma imagem."; return@launch }
        val r = fr[k]
        d.selImage = imgs[k]
        d.placing = Placement(Tool.IMAGE, page, r.l, r.t, r.r, r.b, (r.r - r.l) / (r.b - r.t).coerceAtLeast(0.001f))
    }

    fun moveImage(d: ViewerDoc, p: Placement) = viewModelScope.launch {
        val img = d.selImage ?: return@launch
        val pts = engine.pdfPoints(d.pdf, p.page, listOf(p.l to p.b, p.r to p.t))
        edit(d, "mover a imagem") { PageImages.move(it, img, minOf(pts[0], pts[2]), minOf(pts[1], pts[3]), maxOf(pts[0], pts[2]), maxOf(pts[1], pts[3])) }.join()
        d.selImage = null
    }

    fun deleteImage(d: ViewerDoc) = viewModelScope.launch {
        val img = d.selImage ?: return@launch
        d.placing = null
        edit(d, "excluir a imagem") { PageImages.delete(it, img) }.join()
        d.selImage = null
    }

    fun replaceImage(d: ViewerDoc, u: Uri) = viewModelScope.launch {
        val img = d.selImage ?: return@launch
        val bmp = withContext(Dispatchers.IO) {
            getApplication<Application>().contentResolver.openInputStream(u)!!.use { android.graphics.BitmapFactory.decodeStream(it) }
        } ?: run { error = "Não foi possível ler a imagem."; return@launch }
        d.placing = null
        edit(d, "trocar a imagem") { PageImages.replace(it, img, bmp) }.join()
        d.selImage = null
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
                runCatching { Versions.backup(app, d.uri) }   // versão anterior guardada (menu › Versões anteriores)
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
    var showSettings by mutableStateOf(false)
    var progress by mutableStateOf<String?>(null)
    var compare by mutableStateOf<CompareState?>(null)
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
        dropReadDoc()
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
        if (checkedUpdate || !prefs.autoUpdate) return
        checkedUpdate = true
        viewModelScope.launch {
            update = runCatching { Updater.check() }.getOrNull()
        }
    }

    override fun onCleared() {
        doc?.let { d -> recents.setPage(d.uri, d.page) }
        super.onCleared()
    }

    /** Arquivo atual (versão editada, se houver) para imprimir. */
    suspend fun currentFile(d: ViewerDoc): File = withContext(Dispatchers.IO) {
        d.work ?: Uri.parse(d.uri).let { u ->
            if (u.scheme == "file") File(u.path!!)
            else File(getApplication<Application>().cacheDir, "imprimir.pdf").also { f ->
                getApplication<Application>().contentResolver.openInputStream(u)!!.use { i -> f.outputStream().use { i.copyTo(it) } }
            }
        }
    }

    /** Fotos da galeria para PDF (uma página por foto). */
    fun imagesToPdf(uris: List<Uri>) = viewModelScope.launch {
        loading = true
        try {
            val app = getApplication<Application>()
            val stamp = java.text.SimpleDateFormat("yyyyMMdd_HHmm", java.util.Locale.US).format(java.util.Date())
            val out = File(File(app.filesDir, "recebidos").apply { mkdirs() }, "Fotos_$stamp.pdf")
            withContext(Dispatchers.IO) {
                val bmps = uris.mapNotNull { u -> runCatching { decodeImage(app, u, 2000) }.getOrNull() }
                require(bmps.isNotEmpty()) { "Nenhuma imagem pôde ser lida" }
                Editor.imagesToPdf(bmps, out)
            }
            openPrepared(Uri.fromFile(out), out.name, null)
        } catch (e: Exception) {
            error = "Não foi possível criar o PDF.\n${e.message ?: ""}"
        } finally {
            loading = false
        }
    }

    // ------------------------------------------------------------ leva 2
    /** OCR nas páginas sem texto: cria a camada de texto invisível (pesquisável e copiável). */
    fun ocr(d: ViewerDoc) = viewModelScope.launch {
        try {
            val todo = (0 until d.pageCount).filter { engine.chars(d.pdf, it).count { c -> !c.first.isWhitespace() } < 15 }
            if (todo.isEmpty()) { toast = "Todas as páginas já têm texto"; return@launch }
            val words = HashMap<Int, List<Editor.OcrWord>>()
            for ((k, p) in todo.withIndex()) {
                progress = "Reconhecendo texto… página ${k + 1} de ${todo.size}"
                val sz = d.pdf.sizes[p]
                val ws = Ocr.page(engine, d.pdf, p)
                if (ws.isEmpty()) continue
                val pts = engine.pdfPoints(d.pdf, p, ws.map { it.second.l to it.second.b })
                words[p] = ws.mapIndexed { i, (t, r) -> Editor.OcrWord(t, pts[i * 2], pts[i * 2 + 1], (r.r - r.l) * sz.w, (r.b - r.t) * sz.w) }
            }
            progress = null
            if (words.isEmpty()) { toast = "Nenhum texto reconhecido"; return@launch }
            edit(d, "aplicar o OCR") { doc -> words.flatMap { (p, ws) -> Editor.ocrLayer(doc, p, ws) } }.join()
            toast = "Texto reconhecido em ${words.size} página(s). Agora dá para buscar e copiar."
        } catch (e: Exception) {
            error = "Não foi possível reconhecer o texto.\n${e.message ?: ""}"
        } finally {
            progress = null
        }
    }

    /** Texto de todas as páginas (para Word, Excel e .txt). */
    suspend fun allText(d: ViewerDoc): List<String> = (0 until d.pageCount).map { engine.pageText(d.pdf, it) }

    fun convert(d: ViewerDoc, kind: String, target: Uri?) = viewModelScope.launch {
        val app = getApplication<Application>()
        try {
            progress = "Convertendo…"
            if (kind == "imagens") {
                val n = Convert.images(app, engine, d.pdf, d.name.removeSuffix(".pdf").removeSuffix(".PDF")) { progress = "Salvando página ${it + 1}…" }
                toast = "$n imagem(ns) salvas na galeria (Imagens › Lumen PDF)"
                return@launch
            }
            val pages = allText(d)
            if (pages.all { it.isBlank() }) { error = "Este PDF não tem texto (é imagem). Use \"Reconhecer texto (OCR)\" antes."; return@launch }
            withContext(Dispatchers.IO) {
                app.contentResolver.openOutputStream(target!!, "wt")!!.use { o ->
                    when (kind) {
                        "word" -> Convert.docx(pages, o)
                        "excel" -> Convert.xlsx(pages, o)
                        else -> o.write(pages.joinToString("\n\n\u000C").toByteArray())
                    }
                }
            }
            toast = "Convertido: ${displayName(app, target!!)}"
        } catch (e: Exception) {
            error = "Não foi possível converter.\n${e.message ?: ""}"
        } finally {
            progress = null
        }
    }

    fun detectFields(d: ViewerDoc) = viewModelScope.launch {
        progress = "Procurando campos…"
        val chars = (0 until d.pageCount).associateWith { engine.chars(d.pdf, it) }
        var count: Map<String, Int> = emptyMap()
        pages(d, "criar os campos", done = { _, _ -> }) { doc, _ ->
            val found = chars.mapValues { (p, c) -> FieldDetect.detect(doc, p, c) }.filterValues { it.isNotEmpty() }
            count = FieldDetect.create(doc, found)
        }.join()
        progress = null
        val total = count.values.sum()
        toast = if (total == 0) "Nenhum campo novo encontrado" else
            "$total campo(s): ${count["text"]} de texto, ${count["check"]} caixa(s), ${count["signature"]} de assinatura"
    }

    /** Tarjas de padrões (CPF, CNPJ, e-mail, telefone) encontradas no texto. */
    suspend fun findPatterns(d: ViewerDoc, kinds: Set<String>): List<Pair<Int, FracRect>> {
        val re = mapOf(
            "cpf" to "\\d{3}\\.?\\d{3}\\.?\\d{3}-?\\d{2}",
            "cnpj" to "\\d{2}\\.?\\d{3}\\.?\\d{3}/?\\d{4}-?\\d{2}",
            "email" to "[\\w.+-]+@[\\w-]+\\.[\\w.-]+",
            "telefone" to "\\(?\\d{2}\\)?\\s?9?\\d{4}-?\\d{4}",
        ).filterKeys { it in kinds }.values.joinToString("|").toRegex()
        val out = ArrayList<Pair<Int, FracRect>>()
        for (p in 0 until d.pageCount) {
            val pc = engine.pageChars(d.pdf, p)
            for (m in re.findAll(pc.text)) {
                val boxes = (m.range.first..m.range.last).mapNotNull { pc.frac.getOrNull(it) }
                if (boxes.isEmpty()) continue
                out += p to FracRect(boxes.minOf { it.l }, boxes.minOf { it.t }, boxes.maxOf { it.r }, boxes.maxOf { it.b })
            }
        }
        return out
    }

    /** Aplica as tarjas: as páginas atingidas são regravadas como imagem, sem o conteúdo coberto. */
    fun applyRedactions(d: ViewerDoc) = viewModelScope.launch {
        val items = d.redactions.toList()
        if (items.isEmpty()) return@launch
        progress = "Aplicando tarjas…"
        try {
            val byPage = items.groupBy({ it.first }, { it.second })
            val images = HashMap<Int, android.graphics.Bitmap>()
            val pdfRects = HashMap<Int, List<android.graphics.RectF>>()
            for ((p, rects) in byPage) {
                val sz = d.pdf.sizes[p]
                val w = (sz.w * 200 / 72).toInt()
                val bmp = engine.render(d.pdf, p, w).copy(android.graphics.Bitmap.Config.ARGB_8888, true)
                val c = android.graphics.Canvas(bmp)
                val black = android.graphics.Paint().apply { color = android.graphics.Color.BLACK }
                rects.forEach { r -> c.drawRect(r.l * w - 2, r.t * w - 2, r.r * w + 2, r.b * w + 2, black) }
                images[p] = bmp
                pdfRects[p] = rects.map { r ->
                    val pts = engine.pdfPoints(d.pdf, p, listOf(r.l to r.t, r.r to r.b))
                    android.graphics.RectF(minOf(pts[0], pts[2]), maxOf(pts[1], pts[3]), maxOf(pts[0], pts[2]), minOf(pts[1], pts[3]))
                }
            }
            d.redactions.clear()
            pages(d, "aplicar as tarjas") { doc, _ -> images.forEach { (p, img) -> Editor.redactPage(doc, p, img, pdfRects[p]!!) } }.join()
            toast = "Tarjas aplicadas em ${images.size} página(s)"
        } finally {
            progress = null
        }
    }

    // ------------------------------------------------------------ comparar
    private suspend fun runCompare(a: OpenPdf, b: OpenPdf, nameA: String, nameB: String, title: String, intro: String) {
        progress = "Comparando…"
        try {
            val wa = Compare.words(engine, a)
            val wb = Compare.words(engine, b)
            val ch = withContext(Dispatchers.Default) { Compare.changes(wa, wb) }
            compare = CompareState(a, b, nameA, nameB, ch, title, intro)
        } finally {
            progress = null
        }
    }

    fun compareWith(d: ViewerDoc, other: Uri) = viewModelScope.launch {
        try {
            val app = getApplication<Application>()
            val fa = currentFile(d).let { f -> File(app.cacheDir, "comparar_a.pdf").also { f.copyTo(it, true) } }
            val fb = cacheCopy(other, "comparar_b.pdf")
            val a = engine.open(app, Uri.fromFile(fa), d.password)
            val b = engine.open(app, Uri.fromFile(fb))
            runCompare(a, b, d.name, displayName(app, other), "Comparar documentos", "")
        } catch (e: Exception) {
            error = "Não foi possível comparar.\n${e.message ?: ""}"
        }
    }

    /** Versão assinada × versão atual. */
    fun changesAfter(d: ViewerDoc, sig: SigInfo) = viewModelScope.launch {
        try {
            val app = getApplication<Application>()
            val cur = currentFile(d)
            val bytes = withContext(Dispatchers.IO) { cur.readBytes() }
            val fa = File(app.cacheDir, "versao_assinada.pdf").apply { writeBytes(bytes.copyOfRange(0, sig.revisionEnd.coerceAtMost(bytes.size))) }
            val fb = File(app.cacheDir, "versao_atual.pdf").apply { writeBytes(bytes) }
            val a = engine.open(app, Uri.fromFile(fa), d.password)
            val b = engine.open(app, Uri.fromFile(fb), d.password)
            val later = d.signatures.filter { it.revisionEnd > sig.revisionEnd }.joinToString { it.signer }
            runCompare(a, b, "Versão assinada", "Versão atual", "Alterações após a assinatura",
                "Depois da assinatura de ${sig.signer}" + (if (later.isNotEmpty()) " · assinaturas posteriores: $later" else ""))
        } catch (e: Exception) {
            error = "Não foi possível comparar.\n${e.message ?: ""}"
        }
    }

    fun closeCompare() {
        val c = compare ?: return
        compare = null
        viewModelScope.launch { engine.close(c.a); engine.close(c.b) }
    }
}

/** Lê uma imagem já girada conforme a foto e reduzida (lado maior até maxPx). */
fun decodeImage(ctx: android.content.Context, u: Uri, maxPx: Int): android.graphics.Bitmap {
    return if (android.os.Build.VERSION.SDK_INT >= 28) {
        android.graphics.ImageDecoder.decodeBitmap(android.graphics.ImageDecoder.createSource(ctx.contentResolver, u)) { dec, info, _ ->
            val big = maxOf(info.size.width, info.size.height)
            if (big > maxPx) dec.setTargetSize(info.size.width * maxPx / big, info.size.height * maxPx / big)
            dec.allocator = android.graphics.ImageDecoder.ALLOCATOR_SOFTWARE
        }
    } else {
        val o = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
        ctx.contentResolver.openInputStream(u)!!.use { android.graphics.BitmapFactory.decodeStream(it, null, o) }
        var sample = 1
        while (maxOf(o.outWidth, o.outHeight) / sample > maxPx * 2) sample *= 2
        ctx.contentResolver.openInputStream(u)!!.use {
            android.graphics.BitmapFactory.decodeStream(it, null, android.graphics.BitmapFactory.Options().apply { inSampleSize = sample })!!
        }
    }
}