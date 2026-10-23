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
                    .pointerInput(d) {
                        detectTapGestures(
                            onDoubleTap = { p -> commitZoom(if (d.zoom > 1.2f) 1f else 2.5f, p) },
                            onTap = { p ->
                                scope.launch {
                                    val hit = pageAt(d, g, p)
                                    val field = hit?.let { (pg, fx, fy) ->
                                        d.fields.firstOrNull { (f, r) -> f.page == pg && fx in r.l..r.r && fy in r.t..r.b && !f.readOnly }?.first
                                    }
                                    when {
                                        hit != null && d.editing && d.tool in setOf(Tool.CHECK, Tool.CROSS, Tool.SIGN) ->
                                            placeNow(ctx, vm, d, d.tool, hit.first, Offset(hit.second, hit.third)) { signPad = true }
                                        hit != null && d.editing && d.tool in setOf(Tool.NOTE, Tool.TEXT) ->
                                            pendingTap = Triple(d.tool, hit.first, Offset(hit.second, hit.third))
                                        field != null && field.kind == FormField.Kind.CHECK ->
                                            vm.edit(d, "marcar o campo") { Editor.setField(it, field.name, if (field.value.isEmpty() || field.value == "Off") "on" else "") }
                                        field != null && field.kind == FormField.Kind.SIGNATURE ->
                                            Toast.makeText(ctx, if (field.value.isEmpty()) "Campo de assinatura: a assinatura com certificado chega na próxima versão."
                                                else "Este campo já está assinado.", Toast.LENGTH_LONG).show()
                                        field != null -> editField = field
                                        handleLinkTap(ctx, vm, d, g, p) -> Unit
                                        d.selection != null -> d.selection = null
                                        else -> bars = !bars
                                    }
                                }
                            },
                        )
                    }
                    .horizontalScroll(hs, enabled = d.zoom > 1.01f)
            ) {
                LazyColumn(
                    state = list,
                    userScrollEnabled = d.tool != Tool.INK,
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
                        PageView(vm, d, i, sz, g.pageWidth(d.zoom))
                    }
                }
            }
            if (d.selection != null) Box(Modifier.align(Alignment.BottomCenter)) {
                SelectionBar(vm, d) { copyText(ctx, it) }
            }
            if (d.busy) LinearProgressIndicator(Modifier.fillMaxWidth().align(Alignment.TopCenter))
            // indicador de página
            Surface(
                onClick = { gotoDialog = true },
                shape = RoundedCornerShape(50),
                color = Color(0xCC1C1B22),
                modifier = Modifier.align(Alignment.BottomCenter).then(if (d.editing) Modifier else Modifier.navigationBarsPadding())
                    .padding(bottom = if (d.selection != null) 84.dp else 14.dp),
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
private fun PageView(vm: AppVm, d: ViewerDoc, i: Int, sz: PageSize, pageW: Int) {
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
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        Box(
            Modifier.size(with(density) { pageW.toDp() }, with(density) { pageH.toDp() })
                .shadow(3.dp)
                .background(if (d.night) Color.Black else Color.White)
                .pointerInput(d, d.tool, pageW) {
                    if (d.tool == Tool.INK) {
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
            val fields = d.fields.filter { it.first.page == i }
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
private suspend fun handleLinkTap(ctx: Context, vm: AppVm, d: ViewerDoc, g: ViewerGeom, p: Offset): Boolean {
    val item = g.list.layoutInfo.visibleItemsInfo.firstOrNull { p.y >= it.offset && p.y <= it.offset + it.size } ?: return false
    val pw = g.pageWidth(d.zoom)
    val x = (p.x + g.hs.value - g.sidePx) / pw
    val y = (p.y - item.offset) / pw
    val link = vm.engine.links(d.pdf, item.index).firstOrNull { x in it.area.l..it.area.r && y in it.area.t..it.area.b }
        ?: return false
    val target = link.page
    val uri = link.uri
    when {
        target != null && target >= 0 -> g.list.animateScrollToItem(target)
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
        val i = Intent(Intent.ACTION_SEND).setType("application/pdf")
            .putExtra(Intent.EXTRA_STREAM, shareUri(ctx, d.uri))
            .putExtra(Intent.EXTRA_SUBJECT, d.name)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        ctx.startActivity(Intent.createChooser(i, "Compartilhar PDF"))
    }.onFailure { Toast.makeText(ctx, "Não foi possível compartilhar: ${it.message}", Toast.LENGTH_LONG).show() }
}
