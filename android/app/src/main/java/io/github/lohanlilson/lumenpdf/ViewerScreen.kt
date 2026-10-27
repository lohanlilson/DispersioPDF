package io.github.lohanlilson.lumenpdf

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculateCentroid
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.EditOff
import androidx.compose.material.icons.filled.Save
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.DarkMode
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.graphics.nativeCanvas
import androidx.core.content.FileProvider
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.android.awaitFrame
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch
import java.io.File
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

private const val MAX_ZOOM = 5f
private const val MAX_RENDER_PX = 2600
private val PAGE_GAP = 10.dp
private val SIDE = 8.dp

private val INVERT = ColorFilter.colorMatrix(ColorMatrix(floatArrayOf(
    -1f, 0f, 0f, 0f, 255f, 0f, -1f, 0f, 0f, 255f, 0f, 0f, -1f, 0f, 255f, 0f, 0f, 0f, 1f, 0f)))

/** Posições de rolagem e helpers compartilhados entre gestos, busca e navegação. */
private class ViewerGeom(
    val list: LazyListState,
    val hs: ScrollState,
    val viewportW: Int,
    val viewportH: Int,
    val sidePx: Int,
    val gapPx: Int,
) {
    fun pageWidth(zoom: Float) = (viewportW * zoom).roundToInt() - 2 * sidePx
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ViewerScreen(vm: AppVm, d: ViewerDoc) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var bars by remember { mutableStateOf(true) }
    var searchMode by remember { mutableStateOf(false) }
    var showToc by remember { mutableStateOf(false) }
    var gotoDialog by remember { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    val list = rememberLazyListState()
    val hs = rememberScrollState()
    var geom by remember { mutableStateOf<ViewerGeom?>(null) }
    var saveMenu by remember { mutableStateOf(false) }
    var pendingTap by remember { mutableStateOf<Triple<Tool, Int, Offset>?>(null) }   // ferramenta, página, ponto (frações)
    var editField by remember { mutableStateOf<FormField?>(null) }
    var signPad by remember { mutableStateOf(false) }
    var nameDialog by remember { mutableStateOf(false) }
    var certSign by remember { mutableStateOf<Triple<Int, android.graphics.RectF, String?>?>(null) }  // página, área (PDF), campo
    var sigSheet by remember { mutableStateOf(false) }
    var organize by remember { mutableStateOf(false) }
    var editLine by remember { mutableStateOf<TextLine?>(null) }
    var editRun by remember { mutableStateOf<TextRun?>(null) }
    var editPt by remember { mutableStateOf(android.graphics.PointF()) }
    var dlg by remember { mutableStateOf("") }
    var splitReq by remember { mutableStateOf<Pair<String, String>?>(null) }
    var reading by remember { mutableStateOf(false) }
    var showComments by remember { mutableStateOf(false) }
    var payList by remember { mutableStateOf(false) }
    var translating by remember { mutableStateOf(false) }
    var pickLang by remember { mutableStateOf(false) }
    var replaceDlg by remember { mutableStateOf(false) }
    val fdfOut = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/vnd.fdf")) { u -> if (u != null) vm.exportComments(d, u) }
    val fdfIn = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { u -> if (u != null) vm.importComments(d, u) }
    val pickReplacement = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { u -> if (u != null) vm.replaceImage(d, u) }
    var blankList by remember { mutableStateOf<List<Int>?>(null) }
    val pdfaTarget = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/pdf")) { u ->
        if (u != null) vm.saveAsPdfA(d, u)
    }
    val pickFolder = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { tree ->
        val r = splitReq
        splitReq = null
        if (tree != null && r != null) vm.split(d, r.first, r.second, tree)
    }           // comprimir | senha | marca | numeros | prefs
    var confirmSigned by remember { mutableStateOf<(() -> Unit)?>(null) }
    val pickCompare = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { u -> if (u != null) vm.compareWith(d, u) }
    var convertKind by remember { mutableStateOf("") }
    val convertTarget = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("*/*")) { u ->
        if (u != null) vm.convert(d, convertKind, u)
    }
    var reader by remember { mutableStateOf<Reader?>(null) }
    fun guarded(a: () -> Unit) { if (d.signatures.isNotEmpty()) confirmSigned = a else a() }
    androidx.compose.runtime.DisposableEffect(Unit) { onDispose { reader?.release() } }
    val view = androidx.compose.ui.platform.LocalView.current
    androidx.compose.runtime.DisposableEffect(vm.prefs.keepScreenOn) {
        view.keepScreenOn = vm.prefs.keepScreenOn
        onDispose { view.keepScreenOn = false }
    }
    var editNote by remember { mutableStateOf<Editor.AnnotRef?>(null) }
    val saveAs = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/pdf")) { u ->
        if (u != null) vm.saveAs(d, u)
    }
    fun doSave() = vm.save(d) { saveAs.launch(d.name) }
    // "Editar texto": deixa o documento aberto para leitura antes do primeiro toque
    LaunchedEffect(d.tool, d.pdf, d.page) {
        if (d.editing && d.tool == Tool.EDITTEXT) { kotlinx.coroutines.delay(400); vm.prewarmRead(d, d.page) }
    }
    LaunchedEffect(vm.toast) {
        vm.toast?.let { Toast.makeText(ctx, it, Toast.LENGTH_SHORT).show(); vm.toast = null }
    }

    LaunchedEffect(d) {
        if (d.startPage > 0) list.scrollToItem(d.startPage)
        // página atual = a que ocupa o meio da tela
        snapshotFlow {
            val info = list.layoutInfo
            val mid = (info.viewportStartOffset + info.viewportEndOffset) / 2
            info.visibleItemsInfo.firstOrNull { mid >= it.offset && mid <= it.offset + it.size + 40 }?.index
                ?: list.firstVisibleItemIndex
        }.distinctUntilChanged().collect { d.page = it }
    }

    fun goToHit(i: Int) {
        if (i !in d.hits.indices) return
        d.hitIndex = i
        val g = geom ?: return
        val h = d.hits[i]
        val r = h.rects.first()
        scope.launch {
            val pw = g.pageWidth(d.zoom)
            list.scrollToItem(h.page)
            list.scrollBy(r.t * pw - g.viewportH / 3f)
            if (d.zoom > 1.01f) g.hs.scrollTo((r.l * pw + g.sidePx - g.viewportW / 3f).roundToInt().coerceAtLeast(0))
        }
    }

    LaunchedEffect(d.hits.size, d.searching) {
        if (!d.searching && d.hitIndex >= 0) goToHit(d.hitIndex)
    }

    androidx.compose.material3.Scaffold(
        topBar = {
            AnimatedVisibility(bars || searchMode, enter = fadeIn(), exit = fadeOut()) {
                if (searchMode) {
                    SearchBar(vm, d, onClose = { searchMode = false; d.hits.clear(); d.hitIndex = -1; d.query = "" },
                        onNav = { step ->
                            if (d.hits.isNotEmpty()) goToHit(((d.hitIndex + step) % d.hits.size + d.hits.size) % d.hits.size)
                        })
                } else {
                    TopAppBar(
                        title = { Text(d.name, maxLines = 1, style = MaterialTheme.typography.titleMedium) },
                        navigationIcon = { IconButton({ vm.requestClose() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Voltar") } },
                        actions = {
                            if (d.dirty) Box {
                                IconButton({ saveMenu = true }) { Icon(Icons.Filled.Save, "Salvar", tint = MaterialTheme.colorScheme.primary) }
                                DropdownMenu(saveMenu, { saveMenu = false }) {
                                    DropdownMenuItem(text = { Text("Salvar") }, onClick = { saveMenu = false; doSave() })
                                    DropdownMenuItem(text = { Text("Salvar uma cópia…") }, onClick = { saveMenu = false; saveAs.launch(d.name) })
                                }
                            }
                            IconButton({ d.editing = !d.editing; d.tool = Tool.NONE; d.strokes.clear(); d.selection = null }) {
                                Icon(if (d.editing) Icons.Filled.EditOff else Icons.Filled.Edit, if (d.editing) "Sair da edição" else "Editar")
                            }
                            IconButton({ searchMode = true }) { Icon(Icons.Filled.Search, "Localizar") }
                            IconButton({ showToc = true }) { Icon(Icons.AutoMirrored.Filled.List, "Sumário") }
                            IconButton({ share(ctx, d) }) { Icon(Icons.Filled.Share, "Compartilhar") }
                            Box {
                                IconButton({ menu = true }) { Icon(Icons.Filled.MoreVert, "Mais") }
                                DropdownMenu(menu, { menu = false }) {
                                    DropdownMenuItem(text = { Text(if (d.night) "Modo claro" else "Modo noturno") },
                                        leadingIcon = { Icon(Icons.Filled.DarkMode, null) },
                                        onClick = { menu = false; d.night = !d.night })
                                    DropdownMenuItem(text = { Text("Organizar páginas…") }, onClick = { menu = false; organize = true })
                                    DropdownMenuItem(text = { Text("Imprimir…") }, onClick = {
                                        menu = false
                                        scope.launch { printPdf(ctx, vm.currentFile(d), d.name) }
                                    })
                                    DropdownMenuItem(text = { Text("Ler em voz alta") }, onClick = {
                                        menu = false
                                        reader?.release()
                                        reader = Reader(ctx, { pg -> vm.engine.pageText(d.pdf, pg) }, d.pageCount) { pg ->
                                            scope.launch { list.animateScrollToItem(pg) }
                                        }.also { r -> scope.launch { while (!r.ready) kotlinx.coroutines.delay(100); r.start(d.page) } }
                                    })
                                    DropdownMenuItem(text = { Text("Reconhecer texto (OCR)") }, onClick = { menu = false; vm.ocr(d) })
                                    DropdownMenuItem(text = { Text("Converter…") }, onClick = { menu = false; dlg = "converter" })
                                    DropdownMenuItem(text = { Text("Preencher com meus dados") }, onClick = {
                                        menu = false
                                        dlg = if (Autofill.hasAny(ctx)) "autofill" else "meusdados"
                                    })
                                    DropdownMenuItem(text = { Text("Detectar campos de formulário") }, onClick = { menu = false; guarded { vm.detectFields(d) } })
                                    DropdownMenuItem(text = { Text("Comparar com outro PDF…") }, onClick = { menu = false; pickCompare.launch(arrayOf("application/pdf")) })
                                    DropdownMenuItem(text = { Text("Modo leitura") }, onClick = { menu = false; reading = true })
                                    DropdownMenuItem(text = { Text("Localizar e substituir…") }, onClick = { menu = false; replaceDlg = true })
                                    DropdownMenuItem(text = { Text("Comentários…") }, onClick = { menu = false; showComments = true })
                                    DropdownMenuItem(text = { Text("Boletos, Pix e notas…") }, onClick = { menu = false; vm.paymentsNow(d); payList = true })
                                    DropdownMenuItem(text = { Text("Traduzir…") }, onClick = { menu = false; if (d.language != null) translating = true else pickLang = true })
                                    DropdownMenuItem(text = { Text("Criar links de sites e e-mails") }, onClick = { menu = false; vm.autolink(d) })
                                    DropdownMenuItem(text = { Text("Exportar comentários (FDF)…") }, onClick = {
                                        menu = false; fdfOut.launch(d.name.removeSuffix(".pdf").removeSuffix(".PDF") + "_comentarios.fdf")
                                    })
                                    DropdownMenuItem(text = { Text("Importar comentários (FDF)…") }, onClick = { menu = false; fdfIn.launch(arrayOf("*/*")) })
                                    DropdownMenuItem(text = { Text("Dividir…") }, onClick = { menu = false; dlg = "dividir" })
                                    DropdownMenuItem(text = { Text("Recortar margens…") }, onClick = { menu = false; dlg = "recortar" })
                                    DropdownMenuItem(text = { Text("Remover páginas em branco") }, onClick = {
                                        menu = false
                                        scope.launch {
                                            val l = vm.findBlank(d)
                                            if (l.isEmpty()) vm.toast = "Nenhuma página em branco encontrada."
                                            else if (l.size == d.pageCount) vm.toast = "Todas as páginas parecem em branco; nada foi removido."
                                            else blankList = l
                                        }
                                    })
                                    DropdownMenuItem(text = { Text("Endireitar páginas") }, onClick = { menu = false; vm.deskew(d) })
                                    DropdownMenuItem(text = { Text("Extrair imagens") }, onClick = { menu = false; vm.extractImages(d) })
                                    DropdownMenuItem(text = { Text("Salvar como PDF/A…") }, onClick = {
                                        menu = false
                                        pdfaTarget.launch(d.name.removeSuffix(".pdf").removeSuffix(".PDF") + "_PDFA.pdf")
                                    })
                                    DropdownMenuItem(text = { Text("Comprimir…") }, onClick = { menu = false; dlg = "comprimir" })
                                    DropdownMenuItem(text = { Text("Proteger com senha…") }, onClick = { menu = false; dlg = "senha" })
                                    DropdownMenuItem(text = { Text("Marca d'água…") }, onClick = { menu = false; dlg = "marca" })
                                    DropdownMenuItem(text = { Text("Numerar páginas…") }, onClick = { menu = false; dlg = "numeros" })
                                    DropdownMenuItem(text = { Text("Preferências…") }, onClick = { menu = false; dlg = "prefs" })
                                    DropdownMenuItem(text = { Text("Ir para a página…") }, onClick = { menu = false; gotoDialog = true })
                                    DropdownMenuItem(text = { Text("Salvar uma cópia…") }, onClick = { menu = false; saveAs.launch(d.name) })
                                    DropdownMenuItem(text = { Text("Versões anteriores…") }, onClick = { menu = false; dlg = "versoes" })
                                    DropdownMenuItem(text = { Text("Seu nome nos comentários…") }, onClick = { menu = false; nameDialog = true })
                                    DropdownMenuItem(text = { Text("Redesenhar rubrica…") }, onClick = { menu = false; signPad = true })
                                    DropdownMenuItem(text = { Text("Copiar texto da página") },
                                        leadingIcon = { Icon(Icons.Filled.ContentCopy, null) },
                                        onClick = {
                                            menu = false
                                            scope.launch { copyText(ctx, vm.engine.pageText(d.pdf, d.page)) }
                                        })
                                }
                            }
                        },
                        colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
                    )
                }
            }
        },
        bottomBar = {
            if (d.editing) EditBar(vm, d, onSign = { if (loadSignature(ctx) == null) signPad = true })
        },
    ) { pad ->
        BoxWithConstraints(
            Modifier.fillMaxSize().padding(top = pad.calculateTopPadding(), bottom = pad.calculateBottomPadding())
                .background(if (d.night) Color(0xFF101014) else MaterialTheme.colorScheme.surfaceVariant)
        ) {
            val density = LocalDensity.current
            val vw = constraints.maxWidth
            val vh = constraints.maxHeight
            val side = with(density) { SIDE.roundToPx() }
            val gap = with(density) { PAGE_GAP.roundToPx() }
            val g = remember(vw, vh) { ViewerGeom(list, hs, vw, vh, side, gap) }
            geom = g
            var gesture by remember { mutableFloatStateOf(1f) }
            var pivot by remember { mutableStateOf(Offset.Zero) }

            fun commitZoom(newZoom: Float, at: Offset) {
                val z = newZoom.coerceIn(1f, MAX_ZOOM)
                val factor = z / d.zoom
                gesture = 1f
                if (factor == 1f) return
                val idx = list.firstVisibleItemIndex
                val off = list.firstVisibleItemScrollOffset
                val hx = hs.value
                d.zoom = z
                scope.launch {
                    awaitFrame()
                    list.scrollToItem(idx)
                    list.scrollBy((off + at.y) * factor - at.y)
                    hs.scrollTo(((hx + at.x) * factor - at.x).roundToInt().coerceAtLeast(0))
                }
            }


            fun onPageTap(pg: Int, fx: Float, fy: Float) {
                scope.launch {
                    val hit = Triple(pg, fx, fy)
                    android.util.Log.i("LumenPdf", "toque $hit ferramenta=${d.tool} edição=${d.editing}")
                    val field = d.fields.firstOrNull { (f, r) -> f.page == pg && fx in r.l..r.r && fy in r.t..r.b && !f.readOnly }?.first
                    val annot = if (d.editing && d.tool == Tool.NONE) d.annots.filter { (a, r) ->
                        a.page == pg && fx in r.l - 0.01f..r.r + 0.01f && fy in r.t - 0.01f..r.b + 0.01f
                    }.minByOrNull { (_, r) -> (r.r - r.l) * (r.b - r.t) }?.first else null
                    when {
                        d.placing != null -> Unit
                        d.editing && d.tool == Tool.CERT -> {
                            val sz = d.pdf.sizes[pg]
                            val w = 190f / sz.w
                            val h = 56f / sz.w
                            d.placing = Placement(Tool.CERT, pg, fx - w / 2, fy - h / 2, fx + w / 2, fy + h / 2)
                        }
                        d.editing && d.tool == Tool.SIGN -> {
                            val bmp = loadSignature(ctx)
                            if (bmp == null) signPad = true else {
                                val sz = d.pdf.sizes[pg]
                                val aspect = bmp.width.toFloat() / bmp.height
                                val w = 120f / sz.w
                                val h = w / aspect
                                d.placing = Placement(Tool.SIGN, pg, fx - w / 2, fy - h / 2, fx + w / 2, fy + h / 2, aspect)
                            }
                        }
                        d.editing && d.tool == Tool.IMAGE -> vm.pickImage(d, pg, fx, fy)
                        d.editing && d.tool == Tool.MEASURE && d.measureKind == "area" -> {
                            val cur = d.areaPts
                            d.areaPts = if (cur == null || cur.first != pg) pg to listOf(Offset(fx, fy)) else pg to (cur.second + Offset(fx, fy))
                        }
                        d.editing && d.tool == Tool.HIGHLIGHT -> {
                            val pc = vm.engine.pageChars(d.pdf, pg)
                            val k = pc.charAt(fx, fy)
                            if (k < 0) Toast.makeText(ctx, "Nenhum texto neste ponto", Toast.LENGTH_SHORT).show()
                            else {
                                val (a, b) = pc.word(k)
                                vm.markup(d, pc.selection(a, b), Markup.HIGHLIGHT, vm.prefs.highlightColor)
                            }
                        }
                        d.editing && d.tool == Tool.EDITTEXT -> {
                            val line = vm.engine.lineAt(d.pdf, pg, fx, fy)
                            if (line == null || line.text.isBlank()) Toast.makeText(ctx, "Nenhum texto neste ponto", Toast.LENGTH_SHORT).show()
                            else {
                                val pt = vm.engine.pdfPoint(d.pdf, pg, fx, fy)
                                editPt = pt
                                editRun = vm.analyzeRun(d, line, pt.x, pt.y)
                                editLine = line
                            }
                        }
                        annot != null -> d.selAnnot = annot
                        d.editing && d.tool in setOf(Tool.CHECK, Tool.CROSS) ->
                            placeNow(ctx, vm, d, d.tool, pg, Offset(fx, fy)) { signPad = true }
                        d.editing && d.tool in setOf(Tool.NOTE, Tool.TEXT) -> pendingTap = Triple(d.tool, pg, Offset(fx, fy))
                        field != null && field.kind == FormField.Kind.CHECK ->
                            vm.edit(d, "marcar o campo") { Editor.setField(it, field.name, if (field.value.isEmpty() || field.value == "Off") "on" else "") }
                        field != null && field.kind == FormField.Kind.SIGNATURE ->
                            if (field.value.isEmpty()) certSign = Triple(field.page, field.rect, field.name) else sigSheet = true
                        field != null -> editField = field
                        handleLinkTap(ctx, vm, d, pg, fx, fy, list) -> Unit
                        d.selection != null -> d.selection = null
                        else -> bars = !bars
                    }
                }
            }

            fun onPageDoubleTap(pg: Int, fx: Float, fy: Float) {
                val item = list.layoutInfo.visibleItemsInfo.firstOrNull { it.index == pg } ?: return
                val pw = g.pageWidth(d.zoom)
                commitZoom(if (d.zoom > 1.2f) 1f else 2.5f, Offset(fx * pw + side - hs.value, item.offset + fy * pw))
            }
            val contentW = (vw * d.zoom).roundToInt()
            Box(
                Modifier.fillMaxSize()
                    // pinça com dois dedos: zoom (um dedo continua rolando normalmente)
                    .pointerInput(d) {
                        awaitEachGesture {
                            awaitFirstDown(requireUnconsumed = false)
                            var scale = 1f
                            var lastPivot = Offset.Zero
                            do {
                                val ev = awaitPointerEvent(PointerEventPass.Initial)
                                if (ev.changes.count { it.pressed } >= 2) {
                                    scale *= ev.calculateZoom()
                                    val target = (d.zoom * scale).coerceIn(1f, MAX_ZOOM)
                                    gesture = target / d.zoom
                                    lastPivot = ev.calculateCentroid()
                                    pivot = lastPivot
                                    ev.changes.forEach { it.consume() }
                                }
                            } while (ev.changes.any { it.pressed })
                            if (scale != 1f) commitZoom(d.zoom * gesture, lastPivot)
                        }
                    }
                    .horizontalScroll(hs, enabled = d.zoom > 1.01f)
            ) {
                LazyColumn(
                    state = list,
                    userScrollEnabled = d.tool != Tool.INK && d.tool != Tool.SHAPE && d.tool != Tool.REDACT && d.tool != Tool.CROP && d.tool != Tool.SNAP && !(d.tool == Tool.MEASURE && d.measureKind != "area") && !(d.editing && d.tool == Tool.HIGHLIGHT) && d.placing == null,
                    modifier = Modifier.width(with(density) { contentW.toDp() }).fillMaxHeight()
                        .graphicsLayer {
                            scaleX = gesture
                            scaleY = gesture
                            transformOrigin = TransformOrigin(
                                ((pivot.x + hs.value) / contentW.coerceAtLeast(1)).coerceIn(0f, 1f),
                                (pivot.y / vh.coerceAtLeast(1)).coerceIn(0f, 1f))
                        },
                    contentPadding = PaddingValues(top = PAGE_GAP, bottom = 80.dp),
                    verticalArrangement = Arrangement.spacedBy(PAGE_GAP),
                ) {
                    itemsIndexed(d.pdf.sizes, key = { i, _ -> i }) { i, sz ->
                        PageView(vm, d, i, sz, g.pageWidth(d.zoom), ::onPageTap, ::onPageDoubleTap)
                    }
                }
            }
            if (d.selection != null) Box(Modifier.align(Alignment.BottomCenter)) {
                SelectionBar(vm, d) { copyText(ctx, it) }
            }
            reader?.let { r ->
                Surface(shape = RoundedCornerShape(50), color = MaterialTheme.colorScheme.primaryContainer, shadowElevation = 6.dp,
                    modifier = Modifier.align(Alignment.TopCenter).padding(top = 56.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(horizontal = 6.dp)) {
                        Text("Lendo pág. ${r.page + 1}", style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(start = 10.dp))
                        IconButton({ if (r.playing) r.pause() else r.resume() }) {
                            Icon(if (r.playing) Icons.Filled.Pause else Icons.Filled.PlayArrow, if (r.playing) "Pausar" else "Continuar")
                        }
                        IconButton({ r.release(); reader = null }) { Icon(Icons.Filled.Stop, "Parar leitura") }
                    }
                }
            }
            d.areaPts?.let { (_, pts) ->
                Box(Modifier.align(Alignment.BottomCenter)) {
                    androidx.compose.material3.Surface(shadowElevation = 8.dp, shape = RoundedCornerShape(16.dp),
                        modifier = Modifier.padding(12.dp).navigationBarsPadding()) {
                        Row(Modifier.padding(horizontal = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text("${pts.size} ponto(s)", modifier = Modifier.padding(horizontal = 8.dp))
                            TextButton({ d.areaPts = d.areaPts?.let { (p, l) -> if (l.size > 1) p to l.dropLast(1) else null } }) { Text("Desfazer ponto") }
                            TextButton({ vm.addMeasureArea(d) }, enabled = pts.size >= 3) { Text("Concluir área") }
                        }
                    }
                }
            }
            d.snapFile?.let { f ->
                Box(Modifier.align(Alignment.BottomCenter)) {
                    androidx.compose.material3.Surface(shadowElevation = 8.dp, shape = RoundedCornerShape(16.dp),
                        modifier = Modifier.padding(12.dp).navigationBarsPadding()) {
                        Row(Modifier.padding(horizontal = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text("Área capturada", modifier = Modifier.padding(horizontal = 8.dp))
                            TextButton({ vm.saveToGallery(f); d.snapFile = null }) { Text("Salvar na galeria") }
                            TextButton({
                                val u = androidx.core.content.FileProvider.getUriForFile(ctx, ctx.packageName + ".files", f)
                                ctx.startActivity(android.content.Intent.createChooser(android.content.Intent(android.content.Intent.ACTION_SEND)
                                    .setType("image/png").putExtra(android.content.Intent.EXTRA_STREAM, u)
                                    .addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION), "Compartilhar imagem"))
                                d.snapFile = null
                            }) { Text("Compartilhar") }
                            TextButton({ d.snapFile = null }) { Text("Fechar") }
                        }
                    }
                }
            }
            d.placing?.takeIf { it.kind == Tool.IMAGE }?.let { pl ->
                Box(Modifier.align(Alignment.BottomCenter)) {
                    androidx.compose.material3.Surface(shadowElevation = 8.dp, shape = RoundedCornerShape(16.dp),
                        modifier = Modifier.padding(12.dp).navigationBarsPadding()) {
                        Row(Modifier.padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                            TextButton({ d.placing = null; vm.moveImage(d, pl) }) { Text("Aplicar") }
                            TextButton({ pickReplacement.launch("image/*") }) { Text("Trocar") }
                            TextButton({ vm.deleteImage(d) }) { Text("Excluir") }
                            TextButton({ d.placing = null; d.selImage = null }) { Text("Cancelar") }
                        }
                    }
                }
            }
            d.cropDraft?.let { (pg, r) ->
                Box(Modifier.align(Alignment.BottomCenter)) {
                    androidx.compose.material3.Surface(shadowElevation = 8.dp, shape = RoundedCornerShape(16.dp),
                        modifier = Modifier.padding(12.dp).navigationBarsPadding()) {
                        Row(Modifier.padding(horizontal = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                            TextButton({ d.cropDraft = null; d.tool = Tool.NONE; guarded { vm.crop(d, listOf(pg), r) } }) { Text("Recortar esta página") }
                            TextButton({ d.cropDraft = null; d.tool = Tool.NONE; guarded { vm.crop(d, (0 until d.pageCount).toList(), r) } }) { Text("Todas") }
                            TextButton({ d.cropDraft = null }) { Text("Cancelar") }
                        }
                    }
                }
            }
            if (d.placing != null) Box(Modifier.align(Alignment.BottomCenter)) {
                PlacementBar(d) { p -> scope.launch { confirmPlacement(ctx, vm, d, p) { certSign = it } } }
            }
            if (d.selAnnot != null) Box(Modifier.align(Alignment.BottomCenter)) {
                AnnotBar(vm, d) { editNote = it }
            }
            if (d.busy) LinearProgressIndicator(Modifier.fillMaxWidth().align(Alignment.TopCenter))
            Column(Modifier.align(Alignment.TopCenter)) {
                if (bars || d.signatures.any { !it.ok }) SignatureBanner(d) { sigSheet = true }
                if (bars || d.payments?.any { !it.ok } == true) PaymentsBanner(d, onCopied = { vm.toast = it }) { payList = true }
                if (bars) OrientBanner(d) { vm.straighten(d, d.orientFixes) }
                if (bars) TranslateBanner(d, Traducao.target(vm.prefs)) { translating = true }
            }
            // indicador de página
            Surface(
                onClick = { gotoDialog = true },
                shape = RoundedCornerShape(50),
                color = Color(0xCC1C1B22),
                modifier = Modifier.align(Alignment.BottomCenter).then(if (d.editing) Modifier else Modifier.navigationBarsPadding())
                    .padding(bottom = if (d.selection != null || d.placing != null || d.selAnnot != null) 96.dp else 14.dp),
            ) {
                Text("${d.page + 1} / ${d.pageCount}", color = Color.White,
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp), style = MaterialTheme.typography.labelLarge)
            }
        }
    }

    if (showToc) TocSheet(vm, d, onDismiss = { showToc = false }) { p ->
        showToc = false
        scope.launch { list.scrollToItem(p) }
    }
    pendingTap?.let { (tool, page, at) ->
        val sz = d.pdf.sizes[page]
        when (tool) {
            Tool.NOTE -> TextInputDialog("Nova nota", "Comentário", onDismiss = { pendingTap = null }) { text, _ ->
                pendingTap = null
                scope.launch {
                    val pt = vm.engine.pdfPoint(d.pdf, page, at.x, at.y)
                    vm.edit(d, "adicionar a nota") { Editor.note(it, page, pt.x, pt.y, text, 0xFFFFD400) }
                }
            }
            Tool.TEXT -> TextInputDialog("Adicionar texto", "Texto", withSize = true, onDismiss = { pendingTap = null }) { text, size ->
                pendingTap = null
                scope.launch {
                    val pt = vm.engine.pdfPoint(d.pdf, page, at.x, at.y + size * 0.35f / sz.w)
                    vm.edit(d, "adicionar o texto") { Editor.text(it, page, pt.x, pt.y, text, size, 0xFF1C1B22) }
                }
            }
            else -> pendingTap = null
        }
    }
    editField?.let { f ->
        FieldDialog(f, onDismiss = { editField = null }) { v ->
            editField = null
            vm.edit(d, "preencher o campo") { Editor.setField(it, f.name, v) }
        }
    }
    if (signPad) SignaturePad(ctx, onDismiss = { signPad = false }) {
        signPad = false
        d.tool = Tool.SIGN
        Toast.makeText(ctx, "Rubrica salva. Toque na página onde quer colocá-la.", Toast.LENGTH_LONG).show()
    }
    certSign?.let { (pg, rect, fieldName) ->
        CertSignDialog(vm, fieldName, onDismiss = { certSign = null }) { cert, reason, location, tsa ->
            certSign = null
            vm.signWithCert(d, cert, pg, rect, fieldName, reason, location, tsa)
        }
    }
    if (sigSheet) SignaturesSheet(d, onChanges = { sig -> sigSheet = false; vm.changesAfter(d, sig) }) { sigSheet = false }
    vm.compare?.let { c -> CompareScreen(vm, c) { vm.closeCompare() } }
    vm.progress?.let { msg ->
        AlertDialog(onDismissRequest = {}, confirmButton = {}, text = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                androidx.compose.material3.CircularProgressIndicator(Modifier.size(28.dp))
                Text(msg, Modifier.padding(start = 16.dp))
            }
        })
    }
    when (dlg) {
        "comprimir" -> CompressDialog((d.work?.length() ?: Uri.parse(d.uri).path?.let { File(it).length() } ?: 0L) / 1024,
            onDismiss = { dlg = "" }) { px, q ->
            dlg = ""
            guarded {
                vm.pages(d, "comprimir", done = { a, b ->
                    vm.toast = "Comprimido: %.1f MB → %.1f MB".format(a / 1048576.0, b / 1048576.0)
                }) { doc, _ -> Editor.compress(doc, px, q) }
            }
        }
        "senha" -> ProtectDialog(d.password != null, onDismiss = { dlg = "" }, onRemove = {
            dlg = ""
            vm.pages(d, "remover a senha", newPassword = null) { doc, _ -> Editor.unprotect(doc) }
        }) { user, owner, pr, cp, ed ->
            dlg = ""
            guarded { vm.pages(d, "proteger", newPassword = user) { doc, _ -> Editor.protect(doc, user, owner, pr, cp, ed) } }
        }
        "marca" -> WatermarkDialog(onDismiss = { dlg = "" }) { t, op ->
            dlg = ""
            guarded { vm.pages(d, "aplicar a marca d'água") { doc, _ -> Editor.watermark(doc, t, op, 0xFFD7373F) } }
        }
        "numeros" -> PageNumbersDialog(onDismiss = { dlg = "" }) { f ->
            dlg = ""
            guarded { vm.pages(d, "numerar as páginas") { doc, _ -> Editor.pageNumbers(doc, f) } }
        }
        "prefs" -> SettingsScreen(vm) { dlg = "" }
        "recortar" -> AlertDialog(onDismissRequest = { dlg = "" }, title = { Text("Recortar margens") },
            text = {
                Column {
                    TextButton({ dlg = ""; guarded { vm.crop(d, (0 until d.pageCount).toList(), null) } }, modifier = Modifier.fillMaxWidth()) {
                        Text("Automático em todas as páginas (bordas brancas ou pretas)", Modifier.fillMaxWidth())
                    }
                    TextButton({ dlg = ""; guarded { vm.crop(d, listOf(d.page), null) } }, modifier = Modifier.fillMaxWidth()) {
                        Text("Automático só nesta página", Modifier.fillMaxWidth())
                    }
                    TextButton({ dlg = ""; d.editing = true; d.tool = Tool.CROP; d.cropDraft = null }, modifier = Modifier.fillMaxWidth()) {
                        Text("Desenhar a área a manter…", Modifier.fillMaxWidth())
                    }
                }
            },
            confirmButton = {}, dismissButton = { TextButton({ dlg = "" }) { Text("Cancelar") } })
        "versoes" -> VersionsDialog(d, onDismiss = { dlg = "" }) { f -> dlg = ""; vm.restoreVersion(d, f) }
        "dividir" -> SplitDialog(d.pageCount, onDismiss = { dlg = "" }) { m, v ->
            dlg = ""
            splitReq = m to v
            pickFolder.launch(null)
        }
        "meusdados" -> MyDataDialog { dlg = if (Autofill.hasAny(ctx)) "autofill" else "" }
        "autofill" -> AutofillDialog(remember(d.fields) { Autofill.plan(d.fields.map { it.first }, Autofill.load(ctx)) },
            onEditData = { dlg = "meusdados" }, onDismiss = { dlg = "" }) { fills ->
            dlg = ""
            vm.edit(d, "preencher os campos") { doc -> fills.flatMap { Editor.setField(doc, it.field.name, it.value) } }
            vm.toast = "${fills.size} campo(s) preenchido(s). Confira e toque em Salvar."
        }
        "converter" -> AlertDialog(onDismissRequest = { dlg = "" }, title = { Text("Converter para") },
            text = {
                Column {
                    val base = d.name.removeSuffix(".pdf").removeSuffix(".PDF")
                    listOf(Triple("word", "Word (.docx)", "$base.docx"), Triple("excel", "Excel (.xlsx)", "$base.xlsx"),
                        Triple("texto", "Texto (.txt)", "$base.txt"), Triple("imagens", "Imagens JPG (galeria)", "")).forEach { (k, l, fname) ->
                        TextButton({
                            dlg = ""
                            convertKind = k
                            if (k == "imagens") vm.convert(d, k, null) else convertTarget.launch(fname)
                        }, modifier = Modifier.fillMaxWidth()) { Text(l, Modifier.fillMaxWidth()) }
                    }
                }
            },
            confirmButton = {}, dismissButton = { TextButton({ dlg = "" }) { Text("Cancelar") } })
    }
    blankList?.let { l ->
        AlertDialog(onDismissRequest = { blankList = null }, title = { Text("Páginas em branco") },
            text = { Text("Encontradas: páginas " + l.joinToString(", ") { (it + 1).toString() } + ".\n\nRemover? Dá para desfazer.") },
            confirmButton = {
                TextButton({
                    blankList = null
                    guarded { vm.pages(d, "remover as páginas em branco") { doc, _ -> l.sortedDescending().forEach { doc.removePage(it) } } }
                }) { Text("Remover") }
            },
            dismissButton = { TextButton({ blankList = null }) { Text("Cancelar") } })
    }
    if (reading) ReadingMode(vm, d) { reading = false }
    if (translating) {
        val dst = Traducao.target(vm.prefs)
        val src = d.language
        if (src == null || src == dst || !Traducao.supported(src)) {
            translating = false
            if (src == dst) vm.toast = "O documento já está em ${Traducao.NAMES[dst]}." else pickLang = true
        } else TranslatedReading(vm, d, src, dst) { translating = false; d.translateHidden = true }
    }
    if (pickLang) AlertDialog(onDismissRequest = { pickLang = false }, title = { Text("Em que idioma está o documento?") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Traducao.NAMES.filter { it.key != Traducao.target(vm.prefs) && Traducao.supported(it.key) }.forEach { (k, n) ->
                    Text(n.replaceFirstChar { it.uppercase() }, Modifier.fillMaxWidth().clickable { pickLang = false; d.language = k; translating = true }.padding(vertical = 10.dp))
                }
            }
        }, confirmButton = { TextButton({ pickLang = false }) { Text("Cancelar") } })
    if (payList && d.payments != null) PaymentsSheet(d, onGoto = { p -> payList = false; scope.launch { list.animateScrollToItem(p) } }) { payList = false }
    if (showComments) CommentsSheet(d, onDismiss = { showComments = false }) { a ->
        showComments = false
        d.editing = true; d.tool = Tool.NONE; d.selAnnot = a
        scope.launch { list.animateScrollToItem(a.page) }
    }
    if (replaceDlg) ReplaceDialog(onDismiss = { replaceDlg = false }) { f, r, c, w ->
        replaceDlg = false
        guarded { vm.replaceAll(d, f, r, c, w) }
    }
    d.calLen?.let { len ->
        TextInputDialog("Calibrar escala", "Medida real dessa linha (ex.: 3,5 m)", "", multiline = false,
            onDismiss = { d.calLen = null }) { t, _ ->
            d.calLen = null
            val m = Regex("""\s*([\d.,]+)\s*(km|m|cm|mm)?\s*""").matchEntire(t.lowercase())
            val v = m?.groupValues?.get(1)?.let { if (',' in it) it.replace(".", "").replace(',', '.') else it }?.toDoubleOrNull()
            if (m == null || v == null || v <= 0) vm.toast = "Não entendi a medida. Use, por exemplo: 3,5 m"
            else {
                val unit = m.groupValues[2].ifEmpty { "m" }
                vm.setScale(d, MeasureScale(v / len, unit, "calibrada (${t.trim()})"))
                d.measureKind = "dist"
                vm.toast = "Escala calibrada. Agora é só medir."
            }
        }
    }
    confirmSigned?.let { act ->
        AlertDialog(onDismissRequest = { confirmSigned = null }, title = { Text("Documento assinado") },
            text = { Text("Esta alteração regrava o documento inteiro e invalida as assinaturas digitais. Continuar?") },
            confirmButton = { TextButton({ confirmSigned = null; act() }) { Text("Continuar") } },
            dismissButton = { TextButton({ confirmSigned = null }) { Text("Cancelar") } })
    }
    editLine?.let { line ->
        val run = editRun
        TextInputDialog("Editar texto", "Texto da linha", run?.text ?: line.text, multiline = false,
            note = run?.style?.let { "Mantém o estilo: ${it.description}" }, onDismiss = { editLine = null; editRun = null }) { t, _ ->
            editLine = null
            editRun = null
            vm.replaceText(d, line, editPt.x, editPt.y, t)
        }
    }
    editNote?.let { a ->
        TextInputDialog("Editar nota", "Comentário", a.contents, onDismiss = { editNote = null }) { t, _ ->
            editNote = null
            vm.edit(d, "editar a nota") { Editor.editNote(it, a, t) }
        }
    }
    if (organize) OrganizeScreen(vm, d) { organize = false }
    if (nameDialog) TextInputDialog("Seu nome", "Aparece como autor dos comentários", vm.authorName(), multiline = false,
        onDismiss = { nameDialog = false }) { n, _ -> nameDialog = false; vm.setAuthorName(n) }
    if (vm.confirmClose) AlertDialog(
        onDismissRequest = { vm.confirmClose = false },
        title = { Text("Salvar alterações?") },
        text = { Text("“${d.name}” tem alterações que ainda não foram salvas.") },
        confirmButton = { TextButton({ vm.confirmClose = false; vm.save(d) { saveAs.launch(d.name) }; vm.closeAfterSave = true }) { Text("Salvar") } },
        dismissButton = {
            Row {
                TextButton({ vm.confirmClose = false; vm.closeDoc() }) { Text("Descartar") }
                TextButton({ vm.confirmClose = false }) { Text("Cancelar") }
            }
        },
    )
    if (gotoDialog) GotoDialog(d, onDismiss = { gotoDialog = false }) { p ->
        gotoDialog = false
        scope.launch { list.scrollToItem(p) }
    }
}

@Composable
private fun PageView(vm: AppVm, d: ViewerDoc, i: Int, sz: PageSize, pageW: Int,
                     onTap: (Int, Float, Float) -> Unit, onDoubleTap: (Int, Float, Float) -> Unit) {
    val density = LocalDensity.current
    val pageH = (pageW * sz.ratio).roundToInt()
    val renderW = min(pageW, MAX_RENDER_PX)
    // mostra a última imagem desta página (zoom anterior ou versão antes da edição) enquanto a nova é gerada
    var shown by remember(d, i) { mutableStateOf(d.lastBitmaps.get(i)) }
    // caracteres da página em memória (carregados logo depois da imagem; a seleção não espera o PDFium)
    var chars by remember(d.pdf, i) { mutableStateOf(d.pdf.chars[i]) }
    LaunchedEffect(d.pdf, i) {
        if (chars == null) {
            kotlinx.coroutines.delay(250)
            chars = runCatching { vm.engine.pageChars(d.pdf, i) }.getOrNull()
        }
    }
    val pdf = d.pdf
    LaunchedEffect(pdf, i, renderW) {
        val b = vm.engine.render(pdf, i, renderW).asImageBitmap()
        shown = b
        d.lastBitmaps.put(i, b)
    }
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current
    val signBmp = remember(d.tool, d.placing?.kind) { if (d.tool == Tool.SIGN || d.placing?.kind == Tool.SIGN) loadSignature(ctx) else null }
    val signImg = remember(signBmp) { signBmp?.asImageBitmap() }
    val signAspect = signBmp?.let { it.width.toFloat() / it.height }
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        Box(
            Modifier.size(with(density) { pageW.toDp() }, with(density) { pageH.toDp() })
                .shadow(3.dp)
                .background(if (d.night) Color.Black else Color.White)
                .pointerInput(d, pageW) {
                    detectTapGestures(
                        onTap = { o -> onTap(i, o.x / pageW, o.y / pageW) },
                        onDoubleTap = { o -> onDoubleTap(i, o.x / pageW, o.y / pageW) },
                        onLongPress = { },
                    )
                }
                .pointerInput(d, d.tool, d.placing != null, pageW) {
                    if (d.placing != null || (d.editing && d.tool in setOf(Tool.SIGN, Tool.CERT))) {
                        // caixa de assinatura/rubrica: arrastar move, o canto redimensiona, arrastar fora cria uma nova
                        var mode = 0
                        val minW = 30f / pageW
                        fun resized(p: Placement, r0: Float, b0: Float): Placement {
                            val r = maxOf(p.l + minW, r0)
                            val b = if (p.aspect != null) p.t + (r - p.l) / p.aspect else maxOf(p.t + minW * 0.5f, b0)
                            return p.copy(r = r, b = b)
                        }
                        detectDragGestures(
                            onDragStart = { o ->
                                val fx = o.x / pageW
                                val fy = o.y / pageW
                                val p = d.placing
                                val tol = 48f / pageW
                                mode = when {
                                    p != null && p.page == i && p.kind != Tool.NONE && kotlin.math.abs(fx - p.r) < tol && kotlin.math.abs(fy - p.b) < tol -> 2
                                    p != null && p.page == i && fx in p.l..p.r && fy in p.t..p.b -> 1
                                    d.tool in setOf(Tool.SIGN, Tool.CERT) && p?.kind != Tool.NONE -> {
                                        val aspect = if (d.tool == Tool.SIGN) signAspect else null
                                        if (d.tool == Tool.SIGN && signAspect == null) 0 else {
                                            d.placing = Placement(d.tool, i, fx, fy, fx + minW, fy + minW / (aspect ?: 2f), aspect)
                                            3
                                        }
                                    }
                                    else -> 0
                                }
                            },
                            onDrag = { ch, drag ->
                                if (mode != 0) {
                                    ch.consume()
                                    val p = d.placing
                                    if (p != null) {
                                        val dx = drag.x / pageW
                                        val dy = drag.y / pageW
                                        d.placing = when (mode) {
                                            1 -> p.copy(l = p.l + dx, t = p.t + dy, r = p.r + dx, b = p.b + dy)
                                            else -> resized(p, p.r + dx, p.b + dy)
                                        }
                                    }
                                }
                            },
                        )
                    } else if (d.tool == Tool.REDACT) {
                        // tarja: arrastar desenha o retângulo
                        var start = Offset.Zero
                        detectDragGestures(
                            onDragStart = { o -> start = o; d.redactions += i to FracRect(o.x / pageW, o.y / pageW, o.x / pageW, o.y / pageW) },
                            onDrag = { ch, _ ->
                                ch.consume()
                                val p = ch.position
                                if (d.redactions.isNotEmpty()) d.redactions[d.redactions.lastIndex] = i to FracRect(
                                    minOf(start.x, p.x) / pageW, minOf(start.y, p.y) / pageW, maxOf(start.x, p.x) / pageW, maxOf(start.y, p.y) / pageW)
                            },
                            onDragEnd = {
                                val last = d.redactions.lastOrNull()
                                if (last != null && (last.second.r - last.second.l) * pageW < 8) d.redactions.removeAt(d.redactions.lastIndex)
                            },
                        )
                    } else if (d.editing && d.tool == Tool.MEASURE && d.measureKind != "area") {
                        // medir distância (ou calibrar): arrastar de um ponto ao outro
                        detectDragGestures(
                            onDragStart = { o -> val p = Offset(o.x / pageW, o.y / pageW); d.measureDraft = Triple(i, p, p) },
                            onDrag = { ch, _ ->
                                ch.consume()
                                d.measureDraft?.let { (pg, a, _) -> d.measureDraft = Triple(pg, a, Offset(ch.position.x / pageW, ch.position.y / pageW)) }
                            },
                            onDragEnd = {
                                val m = d.measureDraft
                                if (m == null || (m.third - m.second).getDistance() * pageW < 12f) d.measureDraft = null
                                else if (d.measureKind == "cal") scope.launch {
                                    val p = vm.measurePts(d, m.first, listOf(m.second, m.third))
                                    d.calLen = distPts(p[0], p[1], p[2], p[3])
                                    d.measureDraft = null
                                } else vm.addMeasureLine(d, m.first, m.second, m.third)
                            },
                            onDragCancel = { d.measureDraft = null },
                        )
                    } else if (d.editing && d.tool == Tool.SNAP) {
                        var start = Offset.Zero
                        detectDragGestures(
                            onDragStart = { o -> start = Offset(o.x / pageW, o.y / pageW); d.snapDraft = i to FracRect(start.x, start.y, start.x, start.y) },
                            onDrag = { ch, _ ->
                                ch.consume()
                                val p = Offset(ch.position.x / pageW, ch.position.y / pageW)
                                d.snapDraft = i to FracRect(minOf(start.x, p.x), minOf(start.y, p.y), maxOf(start.x, p.x), maxOf(start.y, p.y))
                            },
                            onDragEnd = {
                                val sd = d.snapDraft
                                d.snapDraft = null
                                if (sd != null && (sd.second.r - sd.second.l) * pageW > 20 && (sd.second.b - sd.second.t) * pageW > 20) vm.snapshot(d, sd.first, sd.second)
                            },
                        )
                    } else if (d.tool == Tool.CROP) {
                        // recortar: arrastar desenha a área que fica
                        var start = Offset.Zero
                        detectDragGestures(
                            onDragStart = { o -> start = Offset(o.x / pageW, o.y / pageW); d.cropDraft = i to FracRect(start.x, start.y, start.x, start.y) },
                            onDrag = { ch, _ ->
                                ch.consume()
                                val p = Offset(ch.position.x / pageW, ch.position.y / pageW)
                                d.cropDraft = i to FracRect(minOf(start.x, p.x), minOf(start.y, p.y), maxOf(start.x, p.x), maxOf(start.y, p.y))
                            },
                            onDragEnd = { d.cropDraft?.let { (_, r) -> if ((r.r - r.l) * pageW < 30 || (r.b - r.t) * pageW < 30) d.cropDraft = null } },
                        )
                    } else if (d.editing && d.tool == Tool.SHAPE) {
                        // formas: arrastar do início ao fim; ao soltar, grava
                        detectDragGestures(
                            onDragStart = { o -> val p = Offset(o.x / pageW, o.y / pageW); d.shapeDraft = Triple(i, p, p) },
                            onDrag = { ch, _ ->
                                ch.consume()
                                d.shapeDraft?.let { (pg, a, _) -> d.shapeDraft = Triple(pg, a, Offset(ch.position.x / pageW, ch.position.y / pageW)) }
                            },
                            onDragEnd = {
                                val sd = d.shapeDraft
                                if (sd != null && (sd.third - sd.second).getDistance() * pageW > 12f) vm.addShape(d, sd.first, sd.second, sd.third)
                                else d.shapeDraft = null
                            },
                            onDragCancel = { d.shapeDraft = null },
                        )
                    } else if (d.tool == Tool.INK) {
                        // desenho à mão livre
                        var cur = mutableListOf<Offset>()
                        detectDragGestures(
                            onDragStart = { o -> cur = mutableListOf(Offset(o.x / pageW, o.y / pageW)); d.strokes += i to cur.toList() },
                            onDrag = { ch, _ ->
                                ch.consume()
                                cur.add(Offset(ch.position.x / pageW, ch.position.y / pageW))
                                if (d.strokes.isNotEmpty()) d.strokes[d.strokes.lastIndex] = i to cur.toList()
                            },
                        )
                    } else if (d.editing && d.tool == Tool.HIGHLIGHT) {
                        // marca-texto: arrastar sobre o texto já destaca (sem precisar segurar antes)
                        var anchor = -1
                        detectDragGestures(
                            onDragStart = { o ->
                                val pc = chars
                                anchor = pc?.charAt(o.x / pageW, o.y / pageW) ?: -1
                                if (pc != null && anchor >= 0) d.selection = pc.wordSelection(anchor, anchor)
                                else if (pc == null) scope.launch {
                                    val c = vm.engine.pageChars(d.pdf, i)
                                    chars = c
                                    anchor = c.charAt(o.x / pageW, o.y / pageW)
                                    if (anchor >= 0) d.selection = c.wordSelection(anchor, anchor)
                                }
                            },
                            onDrag = { ch, _ ->
                                ch.consume()
                                val pc = chars
                                if (pc != null && anchor >= 0) {
                                    val c = pc.charAt(ch.position.x / pageW, ch.position.y / pageW, strict = false)
                                    if (c >= 0) d.selection = pc.wordSelection(anchor, c)
                                }
                            },
                            onDragEnd = {
                                val sel = d.selection
                                d.selection = null
                                if (sel != null && sel.page == i && anchor >= 0) vm.markup(d, sel, Markup.HIGHLIGHT, vm.prefs.highlightColor)
                                anchor = -1
                            },
                            onDragCancel = { d.selection = null; anchor = -1 },
                        )
                    } else {
                        // tocar e segurar no texto: seleciona a palavra; arrastar estende a seleção
                        var anchor = -1
                        detectDragGesturesAfterLongPress(
                            onDragStart = { o ->
                                scope.launch {
                                    val pc = chars ?: vm.engine.pageChars(d.pdf, i).also { chars = it }
                                    val k = pc.charAt(o.x / pageW, o.y / pageW)
                                    if (k >= 0) {
                                        val (a, b) = pc.word(k)
                                        anchor = a
                                        d.selection = pc.selection(a, b)
                                    }
                                }
                            },
                            onDrag = { ch, _ ->
                                ch.consume()
                                val pc = chars
                                if (pc != null && anchor >= 0) {
                                    val c = pc.charAt(ch.position.x / pageW, ch.position.y / pageW, strict = false)
                                    if (c >= 0) d.selection = pc.wordSelection(anchor, c)
                                }
                            },
                        )
                    }
                }
        ) {
            shown?.let {
                Image(it, "Página ${i + 1}", Modifier.fillMaxSize(), contentScale = ContentScale.FillBounds,
                    colorFilter = if (d.night) INVERT else null)
            }
            val reds = d.redactions.filter { it.first == i }
            if (reds.isNotEmpty()) Canvas(Modifier.fillMaxSize()) {
                val w = size.width
                reds.forEach { (_, r) ->
                    drawRect(Color(0xAA000000), Offset(r.l * w, r.t * w), Size((r.r - r.l) * w, (r.b - r.t) * w))
                    drawRect(Color(0xFFD7373F), Offset(r.l * w, r.t * w), Size((r.r - r.l) * w, (r.b - r.t) * w), style = Stroke(2f))
                }
            }
            val place = d.placing?.takeIf { it.page == i }
            val selA = d.selAnnot?.let { a -> d.annots.firstOrNull { it.first == a && a.page == i }?.second }
            if (place != null || selA != null) {
                Canvas(Modifier.fillMaxSize()) {
                    val w = size.width
                    selA?.let { r ->
                        drawRect(Color(0xFF6D3CF0), Offset(r.l * w - 4, r.t * w - 4), Size((r.r - r.l) * w + 8, (r.b - r.t) * w + 8),
                            style = Stroke(3f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 6f))))
                    }
                    place?.let { p ->
                        val tl = Offset(p.l * w, p.t * w)
                        val sz2 = Size(p.w * w, p.h * w)
                        drawRect(Color(0x226D3CF0), tl, sz2)
                        if (p.kind == Tool.SIGN && signImg != null) {
                            drawImage(signImg, dstOffset = androidx.compose.ui.unit.IntOffset(tl.x.toInt(), tl.y.toInt()),
                                dstSize = androidx.compose.ui.unit.IntSize(sz2.width.toInt().coerceAtLeast(1), sz2.height.toInt().coerceAtLeast(1)))
                        }
                        if (p.kind == Tool.CERT) drawContext.canvas.nativeCanvas.drawText("Assinatura digital",
                            tl.x + 10f, tl.y + sz2.height / 2 + 10f,
                            android.graphics.Paint().apply { color = 0xFF6D3CF0.toInt(); textSize = (sz2.height * 0.28f).coerceIn(14f, 48f); isAntiAlias = true })
                        drawRect(Color(0xFF6D3CF0), tl, sz2, style = Stroke(3f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(14f, 8f))))
                        drawCircle(Color(0xFF6D3CF0), 18f, Offset(tl.x + sz2.width, tl.y + sz2.height))
                        drawCircle(Color.White, 8f, Offset(tl.x + sz2.width, tl.y + sz2.height))
                    }
                }
            }
            val fields = if (vm.prefs.highlightFields) d.fields.filter { it.first.page == i } else emptyList()
            val sel = d.selection?.takeIf { it.page == i }
            val strokes = d.strokes.filter { it.first == i }
            val marks = d.pendingMarks.filter { it.first == i }
            d.cropDraft?.takeIf { it.first == i }?.let { (_, r) ->
                Canvas(Modifier.fillMaxSize()) {
                    val w = size.width; val h = size.height
                    val dim = Color(0x88000000)
                    drawRect(dim, Offset.Zero, Size(w, r.t * w))
                    drawRect(dim, Offset(0f, r.b * w), Size(w, h - r.b * w))
                    drawRect(dim, Offset(0f, r.t * w), Size(r.l * w, (r.b - r.t) * w))
                    drawRect(dim, Offset(r.r * w, r.t * w), Size(w - r.r * w, (r.b - r.t) * w))
                    drawRect(Color(0xFF6D3CF0), Offset(r.l * w, r.t * w), Size((r.r - r.l) * w, (r.b - r.t) * w), style = Stroke(3f))
                }
            }
            val md = d.measureDraft?.takeIf { it.first == i }
            val ap = d.areaPts?.takeIf { it.first == i }
            val sn = d.snapDraft?.takeIf { it.first == i }
            if (md != null || ap != null || sn != null) Canvas(Modifier.fillMaxSize()) {
                val w = size.width
                val blue = Color(0xFF1473E6)
                md?.let { (_, a, b) ->
                    drawLine(blue, a * w, b * w, 3f, StrokeCap.Round)
                    drawCircle(blue, 6f, a * w); drawCircle(blue, 6f, b * w)
                }
                ap?.second?.let { pts ->
                    if (pts.size >= 2) {
                        val path = Path().apply { moveTo(pts[0].x * w, pts[0].y * w); pts.drop(1).forEach { lineTo(it.x * w, it.y * w) }; close() }
                        drawPath(path, blue.copy(alpha = 0.18f))
                        drawPath(path, blue, style = Stroke(3f))
                    }
                    pts.forEach { drawCircle(blue, 7f, it * w) }
                }
                sn?.second?.let { r ->
                    drawRect(Color(0x226D3CF0), Offset(r.l * w, r.t * w), Size((r.r - r.l) * w, (r.b - r.t) * w))
                    drawRect(Color(0xFF6D3CF0), Offset(r.l * w, r.t * w), Size((r.r - r.l) * w, (r.b - r.t) * w), style = Stroke(3f))
                }
            }
            val shp = d.shapeDraft?.takeIf { it.first == i }
            if (shp != null) Canvas(Modifier.fillMaxSize()) {
                val w = size.width
                val a = shp.second * w; val b = shp.third * w
                val tl = Offset(minOf(a.x, b.x), minOf(a.y, b.y))
                val sz2 = Size(kotlin.math.abs(b.x - a.x), kotlin.math.abs(b.y - a.y))
                val st = Stroke(d.inkWidth * w / sz.w, cap = StrokeCap.Round)
                when (d.shapeKind) {
                    "Circle" -> drawOval(Color(d.inkColor), tl, sz2, style = st)
                    "Arrow" -> {
                        drawLine(Color(d.inkColor), a, b, st.width, StrokeCap.Round)
                        val ang = kotlin.math.atan2(b.y - a.y, b.x - a.x)
                        val len = 14f * w / sz.w + st.width * 2
                        for (s2 in listOf(-0.5f, 0.5f)) drawLine(Color(d.inkColor), b,
                            Offset(b.x - len * kotlin.math.cos(ang + s2), b.y - len * kotlin.math.sin(ang + s2)), st.width, StrokeCap.Round)
                    }
                    else -> drawRect(Color(d.inkColor), tl, sz2, style = st)
                }
            }
            if (fields.isNotEmpty() || sel != null || strokes.isNotEmpty() || marks.isNotEmpty()) {
                Canvas(Modifier.fillMaxSize()) {
                    val w = size.width
                    for ((f, r) in fields) {
                        val tl = Offset(r.l * w, r.t * w)
                        val sz2 = Size((r.r - r.l) * w, (r.b - r.t) * w)
                        if (f.kind == FormField.Kind.SIGNATURE) {
                            if (f.value.isEmpty()) {
                                drawRect(Color(0x186D3CF0), tl, sz2)
                                drawRect(Color(0xFF6D3CF0), tl, sz2, style = Stroke(2f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(12f, 8f))))
                            }
                        } else if (!f.readOnly) drawRect(Color(0x40CCD7FF), tl, sz2)
                    }
                    val selColor = if (d.editing && d.tool == Tool.HIGHLIGHT) Color(vm.prefs.highlightColor).copy(alpha = 0.45f) else Color(0x553D7BFF)
                    sel?.rects?.forEach { r -> drawRect(selColor, Offset(r.l * w, r.t * w), Size((r.r - r.l) * w, (r.b - r.t) * w),
                        blendMode = androidx.compose.ui.graphics.BlendMode.Multiply) }
                    for ((pg, rs, c) in marks) if (pg == i) rs.forEach { r ->
                        drawRect(Color(c).copy(alpha = 0.55f), Offset(r.l * w, r.t * w), Size((r.r - r.l) * w, (r.b - r.t) * w),
                            blendMode = androidx.compose.ui.graphics.BlendMode.Multiply)
                    }
                    val px = d.inkWidth * w / sz.w
                    for ((_, pts) in strokes) {
                        if (pts.size < 2) continue
                        val path = Path().apply { moveTo(pts[0].x * w, pts[0].y * w); pts.drop(1).forEach { lineTo(it.x * w, it.y * w) } }
                        drawPath(path, Color(d.inkColor), style = Stroke(px, cap = StrokeCap.Round, join = StrokeJoin.Round))
                    }
                }
            }
            val hits = d.hits
            if (hits.isNotEmpty()) {
                Canvas(Modifier.fillMaxSize()) {
                    hits.forEachIndexed { k, h ->
                        if (h.page != i) return@forEachIndexed
                        val cur = k == d.hitIndex
                        for (r in h.rects) {
                            drawRect(
                                if (cur) Color(0x99FF8C00) else Color(0x66FFD400),
                                topLeft = Offset(r.l * size.width, r.t * size.width),
                                size = Size((r.r - r.l) * size.width, (r.b - r.t) * size.width),
                            )
                        }
                    }
                }
            }
        }
    }
}

/** ✓, ✗ e rubrica: colocados direto no ponto tocado (centralizados). */
private suspend fun placeNow(ctx: Context, vm: AppVm, d: ViewerDoc, tool: Tool, page: Int, at: Offset, needPad: () -> Unit) {
    val sz = d.pdf.sizes[page]
    when (tool) {
        Tool.CHECK, Tool.CROSS -> {
            val pt = vm.engine.pdfPoint(d.pdf, page, at.x, at.y)
            vm.edit(d, "marcar") { Editor.mark(it, page, pt.x, pt.y, tool == Tool.CHECK, 14f, 0xFF1C1B22) }
        }
        Tool.SIGN -> {
            val bmp = loadSignature(ctx) ?: return needPad()
            val w = 120f
            val h = w * bmp.height / bmp.width
            // canto inferior esquerdo visual da rubrica centralizada no toque
            val pt = vm.engine.pdfPoint(d.pdf, page, at.x - w / 2 / sz.w, at.y + h / 2 / sz.w)
            vm.edit(d, "colocar a rubrica") { Editor.image(it, page, bmp, pt.x, pt.y, w, h) }
        }
        else -> Unit
    }
}

/** Grava a caixa posicionada: rubrica (imagem), assinatura digital (abre o diálogo) ou comentário movido. */
private suspend fun confirmPlacement(ctx: Context, vm: AppVm, d: ViewerDoc, p: Placement,
                                     openCert: (Triple<Int, android.graphics.RectF, String?>) -> Unit) {
    val sz = d.pdf.sizes[p.page]
    when (p.kind) {
        Tool.SIGN -> {
            val bmp = loadSignature(ctx) ?: return
            val pt = vm.engine.pdfPoint(d.pdf, p.page, p.l, p.b)   // canto inferior esquerdo visual
            val w = p.w * sz.w
            val h = p.h * sz.w
            vm.edit(d, "colocar a rubrica") { Editor.image(it, p.page, bmp, pt.x, pt.y, w, h) }
        }
        Tool.CERT -> {
            val pts = vm.engine.pdfPoints(d.pdf, p.page, listOf(p.l to p.t, p.r to p.b))
            openCert(Triple(p.page, android.graphics.RectF(minOf(pts[0], pts[2]), maxOf(pts[1], pts[3]),
                maxOf(pts[0], pts[2]), minOf(pts[1], pts[3])), null))
        }
        Tool.NONE -> {
            val a = p.annot ?: return
            val old = d.annots.firstOrNull { it.first == a }?.second ?: return
            val pts = vm.engine.pdfPoints(d.pdf, p.page, listOf(old.l to old.t, p.l to p.t))
            val dx = pts[2] - pts[0]
            val dy = pts[3] - pts[1]
            vm.edit(d, "mover o comentário") { Editor.moveAnnot(it, a, dx, dy) }
        }
        else -> Unit
    }
}

/** Página e posição (frações da largura da página) sob um ponto da tela. */
private fun pageAt(d: ViewerDoc, g: ViewerGeom, p: Offset): Triple<Int, Float, Float>? {
    val item = g.list.layoutInfo.visibleItemsInfo.firstOrNull { p.y >= it.offset && p.y <= it.offset + it.size } ?: return null
    val pw = g.pageWidth(d.zoom)
    val x = (p.x + g.hs.value - g.sidePx) / pw
    val y = (p.y - item.offset) / pw
    if (x < 0f || x > 1f || y < 0f || y > d.pdf.sizes[item.index].ratio) return null
    return Triple(item.index, x, y)
}

/** Toque num link: vai para a página de destino ou abre o endereço. */
private suspend fun handleLinkTap(ctx: Context, vm: AppVm, d: ViewerDoc, page: Int, x: Float, y: Float, list: LazyListState): Boolean {
    val link = vm.engine.links(d.pdf, page).firstOrNull { x in it.area.l..it.area.r && y in it.area.t..it.area.b } ?: return false
    val target = link.page
    val uri = link.uri
    when {
        target != null && target >= 0 -> list.animateScrollToItem(target)
        !uri.isNullOrBlank() -> runCatching {
            ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(uri)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }.onFailure { Toast.makeText(ctx, "Não foi possível abrir o link", Toast.LENGTH_SHORT).show() }
    }
    return true
}

@Composable
private fun SearchBar(vm: AppVm, d: ViewerDoc, onClose: () -> Unit, onNav: (Int) -> Unit) {
    val focus = remember { FocusRequester() }
    var text by remember { mutableStateOf(d.query) }
    LaunchedEffect(Unit) { focus.requestFocus() }
    Surface(color = MaterialTheme.colorScheme.surface, shadowElevation = 3.dp) {
        Column(Modifier.padding(top = with(LocalDensity.current) { 0.dp })) {
            Row(Modifier.fillMaxWidth().padding(top = 28.dp, start = 4.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClose) { Icon(Icons.Filled.Close, "Fechar busca") }
                TextField(
                    text, { text = it },
                    modifier = Modifier.weight(1f).focusRequester(focus),
                    placeholder = { Text("Localizar no documento") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    keyboardActions = KeyboardActions(onSearch = { vm.search(d, text) }),
                    colors = TextFieldDefaults.colors(focusedContainerColor = Color.Transparent,
                        unfocusedContainerColor = Color.Transparent),
                )
                val label = when {
                    d.searching -> "pág. ${d.searchPage + 1}"
                    d.query.isNotEmpty() && d.hits.isEmpty() -> "0"
                    d.hits.isNotEmpty() -> "${d.hitIndex + 1}/${d.hits.size}"
                    else -> ""
                }
                Text(label, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(horizontal = 4.dp))
                IconButton({ onNav(-1) }, enabled = d.hits.isNotEmpty()) { Icon(Icons.Filled.KeyboardArrowUp, "Anterior") }
                IconButton({ onNav(1) }, enabled = d.hits.isNotEmpty()) { Icon(Icons.Filled.KeyboardArrowDown, "Próximo") }
            }
            if (d.searching) {
                LinearProgressIndicator(progress = { (d.searchPage + 1f) / d.pageCount }, modifier = Modifier.fillMaxWidth())
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TocSheet(vm: AppVm, d: ViewerDoc, onDismiss: () -> Unit, onGo: (Int) -> Unit) {
    val toc by produceState<List<TocItem>?>(null, d) { value = vm.engine.toc(d.pdf) }
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Text("Sumário", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp))
        val items = toc
        when {
            items == null -> LinearProgressIndicator(Modifier.fillMaxWidth().padding(20.dp))
            items.isEmpty() -> Text("Este documento não tem sumário (marcadores).", modifier = Modifier.padding(20.dp),
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            else -> LazyColumn(contentPadding = PaddingValues(bottom = 40.dp)) {
                itemsIndexed(items) { _, t ->
                    Row(Modifier.fillMaxWidth().clickable { onGo(t.page.coerceIn(0, d.pageCount - 1)) }
                        .padding(start = (20 + t.level * 16).dp, end = 20.dp, top = 12.dp, bottom = 12.dp)) {
                        Text(t.title, Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
                        Text("${t.page + 1}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun GotoDialog(d: ViewerDoc, onDismiss: () -> Unit, onGo: (Int) -> Unit) {
    var text by remember { mutableStateOf("${d.page + 1}") }
    val n = text.toIntOrNull()
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Ir para a página") },
        text = {
            OutlinedTextField(text, { text = it.filter(Char::isDigit) }, singleLine = true,
                label = { Text("Página (1 a ${d.pageCount})") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Go),
                keyboardActions = KeyboardActions(onGo = { if (n != null && n in 1..d.pageCount) onGo(n - 1) }))
        },
        confirmButton = { TextButton({ onGo(n!! - 1) }, enabled = n != null && n in 1..d.pageCount) { Text("Ir") } },
        dismissButton = { TextButton(onDismiss) { Text("Cancelar") } },
    )
}

private fun copyText(ctx: Context, text: String) {
    val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    cm.setPrimaryClip(ClipData.newPlainText("Lumen PDF", text))
    Toast.makeText(ctx, if (text.isBlank()) "Esta página não tem texto (talvez seja uma imagem escaneada)." else "Texto copiado",
        Toast.LENGTH_SHORT).show()
}

fun shareUri(ctx: Context, uriStr: String): Uri {
    val uri = Uri.parse(uriStr)
    return if (uri.scheme == "file") FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", File(uri.path!!)) else uri
}

private fun share(ctx: Context, d: ViewerDoc) {
    runCatching {
        // com alterações não salvas, compartilha a versão editada (com o nome original)
        val uri = d.work?.takeIf { d.dirty }?.let { w ->
            val f = File(ctx.cacheDir, "compartilhar/${d.name}").apply { parentFile?.mkdirs() }
            w.copyTo(f, overwrite = true)
            FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
        } ?: shareUri(ctx, d.uri)
        val i = Intent(Intent.ACTION_SEND).setType("application/pdf")
            .putExtra(Intent.EXTRA_STREAM, uri)
            .putExtra(Intent.EXTRA_SUBJECT, d.name)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        ctx.startActivity(Intent.createChooser(i, "Compartilhar PDF"))
    }.onFailure { Toast.makeText(ctx, "Não foi possível compartilhar: ${it.message}", Toast.LENGTH_LONG).show() }
}
