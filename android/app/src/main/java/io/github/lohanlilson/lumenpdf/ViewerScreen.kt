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
    var dlg by remember { mutableStateOf("") }           // comprimir | senha | marca | numeros | prefs
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
                                    DropdownMenuItem(text = { Text("Detectar campos de formulário") }, onClick = { menu = false; guarded { vm.detectFields(d) } })
                                    DropdownMenuItem(text = { Text("Comparar com outro PDF…") }, onClick = { menu = false; pickCompare.launch(arrayOf("application/pdf")) })
                                    DropdownMenuItem(text = { Text("Comprimir…") }, onClick = { menu = false; dlg = "comprimir" })
                                    DropdownMenuItem(text = { Text("Proteger com senha…") }, onClick = { menu = false; dlg = "senha" })
                                    DropdownMenuItem(text = { Text("Marca d'água…") }, onClick = { menu = false; dlg = "marca" })
                                    DropdownMenuItem(text = { Text("Numerar páginas…") }, onClick = { menu = false; dlg = "numeros" })
                                    DropdownMenuItem(text = { Text("Preferências…") }, onClick = { menu = false; dlg = "prefs" })
                                    DropdownMenuItem(text = { Text("Ir para a página…") }, onClick = { menu = false; gotoDialog = true })
                                    DropdownMenuItem(text = { Text("Salvar uma cópia…") }, onClick = { menu = false; saveAs.launch(d.name) })
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
                        d.editing && d.tool == Tool.EDITTEXT -> {
                            val line = vm.engine.lineAt(d.pdf, pg, fx, fy)
                            if (line == null || line.text.isBlank()) Toast.makeText(ctx, "Nenhum texto neste ponto", Toast.LENGTH_SHORT).show()
                            else editLine = line
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
                    userScrollEnabled = d.tool != Tool.INK && d.tool != Tool.REDACT && d.placing == null,
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
            if (d.placing != null) Box(Modifier.align(Alignment.BottomCenter)) {
                PlacementBar(d) { p -> scope.launch { confirmPlacement(ctx, vm, d, p) { certSign = it } } }
            }
            if (d.selAnnot != null) Box(Modifier.align(Alignment.BottomCenter)) {
                AnnotBar(vm, d) { editNote = it }
            }
            if (d.busy) LinearProgressIndicator(Modifier.fillMaxWidth().align(Alignment.TopCenter))
            if (bars || d.signatures.any { !it.ok }) Box(Modifier.align(Alignment.TopCenter)) { SignatureBanner(d) { sigSheet = true } }
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
    confirmSigned?.let { act ->
        AlertDialog(onDismissRequest = { confirmSigned = null }, title = { Text("Documento assinado") },
            text = { Text("Esta alteração regrava o documento inteiro e invalida as assinaturas digitais. Continuar?") },
            confirmButton = { TextButton({ confirmSigned = null; act() }) { Text("Continuar") } },
            dismissButton = { TextButton({ confirmSigned = null }) { Text("Cancelar") } })
    }
    editLine?.let { line ->
        TextInputDialog("Editar texto", "Texto da linha", line.text, multiline = false, onDismiss = { editLine = null }) { t, _ ->
            editLine = null
            vm.edit(d, "editar o texto") { Editor.replaceText(it, line.page, line.rect, line.x, line.baseline, t, line.size, 0xFF1C1B22) }
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
                    } else {
                        // tocar e segurar no texto: seleciona; arrastar estende a seleção
                        var anchor = -1
                        detectDragGesturesAfterLongPress(
                            onDragStart = { o ->
                                scope.launch {
                                    anchor = vm.engine.charAt(d.pdf, i, o.x / pageW, o.y / pageW)
                                    if (anchor >= 0) {
                                        // começa pela palavra inteira
                                        val txt = vm.engine.selection(d.pdf, i, maxOf(0, anchor - 40), anchor + 40)
                                        val rel = anchor - txt.start
                                        val t = txt.text
                                        var a = rel; var b = rel
                                        while (a > 0 && t.getOrNull(a - 1)?.isLetterOrDigit() == true) a--
                                        while (b < t.length - 1 && t.getOrNull(b + 1)?.isLetterOrDigit() == true) b++
                                        anchor = txt.start + a
                                        d.selection = vm.engine.selection(d.pdf, i, txt.start + a, txt.start + b)
                                    }
                                }
                            },
                            onDrag = { ch, _ ->
                                ch.consume()
                                val pos = ch.position
                                if (anchor >= 0) scope.launch {
                                    val c = vm.engine.charAt(d.pdf, i, pos.x / pageW, pos.y / pageW)
                                    if (c >= 0) d.selection = vm.engine.selection(d.pdf, i, anchor, c)
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
            if (fields.isNotEmpty() || sel != null || strokes.isNotEmpty()) {
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
                    sel?.rects?.forEach { r -> drawRect(Color(0x553D7BFF), Offset(r.l * w, r.t * w), Size((r.r - r.l) * w, (r.b - r.t) * w)) }
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
