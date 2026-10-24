package io.github.lohanlilson.lumenpdf

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas as ACanvas
import android.graphics.Paint
import android.graphics.Path as APath
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Redo
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Draw
import androidx.compose.material.icons.filled.FormatStrikethrough
import androidx.compose.material.icons.filled.FormatUnderlined
import androidx.compose.material.icons.filled.Gesture
import androidx.compose.material.icons.filled.Highlight
import androidx.compose.material.icons.filled.StickyNote2
import androidx.compose.material.icons.filled.TextFields
import androidx.compose.material.icons.filled.TouchApp
import androidx.compose.material.icons.filled.EditNote
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.OpenWith
import androidx.compose.material.icons.filled.VerifiedUser
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import java.io.File

val INK_COLORS = listOf(0xFFD7373F, 0xFF1473E6, 0xFF1C1B22, 0xFF6D3CF0, 0xFF2D9D78)

@Composable
private fun ToolButton(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, selected: Boolean,
                       enabled: Boolean = true, onClick: () -> Unit) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.width(64.dp)) {
        FilledTonalIconButton(onClick = onClick, enabled = enabled,
            colors = if (selected) IconButtonDefaults.filledTonalIconButtonColors(
                containerColor = MaterialTheme.colorScheme.primary, contentColor = MaterialTheme.colorScheme.onPrimary)
            else IconButtonDefaults.filledTonalIconButtonColors()) { Icon(icon, label) }
        Text(label, style = MaterialTheme.typography.labelSmall, maxLines = 1)
    }
}

/** Barra inferior do modo de edição. */
@Composable
fun EditBar(vm: AppVm, d: ViewerDoc, onSign: () -> Unit) {
    Surface(shadowElevation = 8.dp, color = MaterialTheme.colorScheme.surface) {
        Column(Modifier.navigationBarsPadding()) {
            val hint = when (d.tool) {
                Tool.NONE -> "Toque e segure no texto para destacar · toque num comentário para editar"
                Tool.INK -> "Desenhe com o dedo. Toque em Concluir para gravar."
                Tool.NOTE -> "Toque onde quer colocar a nota"
                Tool.TEXT -> "Toque onde quer escrever"
                Tool.CHECK -> "Toque para marcar ✓"
                Tool.CROSS -> "Toque para marcar ✗"
                Tool.SIGN -> "Toque ou arraste onde quer colocar sua rubrica"
                Tool.CERT -> "Toque ou arraste onde a assinatura digital deve ficar"
                Tool.EDITTEXT -> "Toque numa linha de texto para alterá-la"
            }
            Text(hint, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp))
            if (d.tool == Tool.INK) InkOptions(vm, d)
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 6.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                fun pick(t: Tool) {
                    if (d.tool == Tool.INK && t != Tool.INK) d.strokes.clear()
                    d.placing = null
                    d.selAnnot = null
                    d.tool = if (d.tool == t) Tool.NONE else t
                    d.selection = null
                }
                ToolButton(Icons.Filled.TouchApp, "Selecionar", d.tool == Tool.NONE) { pick(Tool.NONE) }
                ToolButton(Icons.Filled.EditNote, "Editar texto", d.tool == Tool.EDITTEXT) { pick(Tool.EDITTEXT) }
                ToolButton(Icons.Filled.Gesture, "Desenhar", d.tool == Tool.INK) { pick(Tool.INK) }
                ToolButton(Icons.Filled.StickyNote2, "Nota", d.tool == Tool.NOTE) { pick(Tool.NOTE) }
                ToolButton(Icons.Filled.TextFields, "Texto", d.tool == Tool.TEXT) { pick(Tool.TEXT) }
                ToolButton(Icons.Filled.Check, "Marcar ✓", d.tool == Tool.CHECK) { pick(Tool.CHECK) }
                ToolButton(Icons.Filled.Close, "Marcar ✗", d.tool == Tool.CROSS) { pick(Tool.CROSS) }
                ToolButton(Icons.Filled.Draw, "Rubrica", d.tool == Tool.SIGN) { pick(Tool.SIGN); if (d.tool == Tool.SIGN) onSign() }
                ToolButton(Icons.Filled.VerifiedUser, "Certificado", d.tool == Tool.CERT) { pick(Tool.CERT) }
                ToolButton(Icons.AutoMirrored.Filled.Undo, "Desfazer", false, d.canUndo && !d.busy) { vm.undo(d) }
                ToolButton(Icons.AutoMirrored.Filled.Redo, "Refazer", false, d.canRedo && !d.busy) { vm.redo(d) }
            }
        }
    }
}

@Composable
private fun InkOptions(vm: AppVm, d: ViewerDoc) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        INK_COLORS.forEach { c ->
            Box(Modifier.padding(4.dp).size(28.dp).clip(CircleShape).background(Color(c))
                .border(if (d.inkColor == c) 3.dp else 0.dp, MaterialTheme.colorScheme.outline, CircleShape)
                .clickable { d.inkColor = c })
        }
        Slider(d.inkWidth, { d.inkWidth = it }, valueRange = 0.8f..6f, modifier = Modifier.weight(1f).padding(horizontal = 8.dp))
        IconButton({ if (d.strokes.isNotEmpty()) d.strokes.removeAt(d.strokes.lastIndex) }, enabled = d.strokes.isNotEmpty()) {
            Icon(Icons.AutoMirrored.Filled.Undo, "Apagar último traço")
        }
        TextButton(enabled = d.strokes.isNotEmpty() && !d.busy, onClick = { commitInk(vm, d) }) { Text("Concluir") }
    }
}

fun commitInk(vm: AppVm, d: ViewerDoc) {
    val byPage = d.strokes.groupBy({ it.first }, { it.second })
    val color = d.inkColor
    val width = d.inkWidth
    d.strokes.clear()
    vm.viewModelScopeLaunch {
        for ((page, strokes) in byPage) {
            val pdfStrokes = strokes.filter { it.size > 1 }.map { pts -> vm.engine.pdfPoints(d.pdf, page, pts.map { it.x to it.y }) }
            if (pdfStrokes.isNotEmpty()) vm.edit(d, "gravar o desenho") { Editor.ink(it, page, pdfStrokes, color, width) }.join()
        }
    }
}

/** Seleção de texto: ações sobre o trecho selecionado. */
@Composable
fun SelectionBar(vm: AppVm, d: ViewerDoc, onCopy: (String) -> Unit) {
    val sel = d.selection ?: return
    Surface(shadowElevation = 8.dp, shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.surface,
        modifier = Modifier.padding(12.dp).navigationBarsPadding()) {
        Row(Modifier.padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton({ onCopy(sel.text); d.selection = null }) { Icon(Icons.Filled.ContentCopy, "Copiar") }
            listOf(Triple(Markup.HIGHLIGHT, Icons.Filled.Highlight, vm.prefs.highlightColor),
                Triple(Markup.UNDERLINE, Icons.Filled.FormatUnderlined, 0xFF2D9D78),
                Triple(Markup.STRIKEOUT, Icons.Filled.FormatStrikethrough, 0xFFD7373F)).forEach { (kind, icon, color) ->
                IconButton({
                    d.selection = null
                    vm.edit(d, kind.label.lowercase()) { Editor.markup(it, sel.page, sel.pdfRects, kind, color) }
                }) { Icon(icon, kind.label, tint = Color(color)) }
            }
            IconButton({ d.selection = null }) { Icon(Icons.Filled.Close, "Cancelar seleção") }
        }
    }
}

@Composable
fun TextInputDialog(title: String, label: String, initial: String = "", multiline: Boolean = true, withSize: Boolean = false,
                    onDismiss: () -> Unit, onOk: (String, Float) -> Unit) {
    var text by remember { mutableStateOf(initial) }
    var size by remember { mutableFloatStateOf(11f) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column {
                OutlinedTextField(text, { text = it }, label = { Text(label) }, singleLine = !multiline,
                    minLines = if (multiline) 3 else 1,
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                    modifier = Modifier.fillMaxWidth())
                if (withSize) {
                    Text("Tamanho: ${size.toInt()}", style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 8.dp))
                    Slider(size, { size = it }, valueRange = 7f..28f, steps = 20)
                }
            }
        },
        confirmButton = { TextButton({ onOk(text, size) }, enabled = text.isNotBlank()) { Text("OK") } },
        dismissButton = { TextButton(onDismiss) { Text("Cancelar") } },
    )
}

/** Preenchimento de um campo de formulário. */
@Composable
fun FieldDialog(f: FormField, onDismiss: () -> Unit, onOk: (String) -> Unit) {
    var value by remember { mutableStateOf(f.value) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(f.label.ifBlank { f.name }) },
        text = {
            when (f.kind) {
                FormField.Kind.CHOICE, FormField.Kind.RADIO -> Column {
                    val opts = if (f.kind == FormField.Kind.RADIO) listOfNotNull(f.onValue) else f.options
                    opts.forEach { o ->
                        Row(Modifier.fillMaxWidth().selectable(value == o) { value = o }.padding(vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(value == o, { value = o })
                            Text(o)
                        }
                    }
                }
                else -> OutlinedTextField(value, { value = it }, singleLine = false, modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences))
            }
        },
        confirmButton = { TextButton({ onOk(value) }) { Text("OK") } },
        dismissButton = { TextButton(onDismiss) { Text("Cancelar") } },
    )
}

// ------------------------------------------------------------ rubrica (assinatura desenhada)
fun signatureFile(ctx: Context) = File(ctx.filesDir, "rubrica.png")

fun loadSignature(ctx: Context): Bitmap? = signatureFile(ctx).takeIf { it.exists() }?.let { BitmapFactory.decodeFile(it.absolutePath) }

@Composable
fun SignaturePad(ctx: Context, onDismiss: () -> Unit, onSaved: () -> Unit) {
    val strokes = remember { mutableStateListOf<List<Offset>>() }
    var current by remember { mutableStateOf<List<Offset>>(emptyList()) }
    var area by remember { mutableStateOf(IntSize.Zero) }
    var color by remember { mutableStateOf(0xFF1C2A80) }
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxWidth().padding(12.dp), shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.padding(12.dp)) {
                Text("Desenhe sua rubrica", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
                Box(Modifier.fillMaxWidth().height(220.dp).clip(RoundedCornerShape(10.dp)).background(Color.White)
                    .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(10.dp))
                    .onSizeChanged { area = it }
                    .pointerInput(Unit) {
                        detectDragGestures(
                            onDragStart = { current = listOf(it) },
                            onDrag = { ch, _ -> current = current + ch.position; ch.consume() },
                            onDragEnd = { if (current.size > 1) strokes += current; current = emptyList() },
                        )
                    }) {
                    Canvas(Modifier.fillMaxSize()) {
                        (strokes + listOf(current)).forEach { s ->
                            if (s.size > 1) {
                                val p = Path().apply { moveTo(s[0].x, s[0].y); s.drop(1).forEach { lineTo(it.x, it.y) } }
                                drawPath(p, Color(color), style = Stroke(width = 5f, cap = StrokeCap.Round, join = StrokeJoin.Round))
                            }
                        }
                        drawLine(Color(0x33000000), Offset(24f, size.height * 0.78f), Offset(size.width - 24f, size.height * 0.78f), 2f)
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 8.dp)) {
                    listOf(0xFF1C2A80, 0xFF1C1B22, 0xFF1473E6).forEach { c ->
                        Box(Modifier.padding(4.dp).size(26.dp).clip(CircleShape).background(Color(c))
                            .border(if (color == c) 3.dp else 0.dp, MaterialTheme.colorScheme.outline, CircleShape)
                            .clickable { color = c })
                    }
                    Spacer(Modifier.weight(1f))
                    TextButton({ strokes.clear() }) { Text("Limpar") }
                    TextButton(onDismiss) { Text("Cancelar") }
                    TextButton(enabled = strokes.isNotEmpty(), onClick = {
                        saveSignature(ctx, strokes, area, color)
                        onSaved()
                    }) { Text("Salvar") }
                }
            }
        }
    }
}

private fun saveSignature(ctx: Context, strokes: List<List<Offset>>, area: IntSize, color: Long) {
    val all = strokes.flatten()
    val pad = 12f
    val x0 = (all.minOf { it.x } - pad).coerceAtLeast(0f)
    val y0 = (all.minOf { it.y } - pad).coerceAtLeast(0f)
    val x1 = (all.maxOf { it.x } + pad).coerceAtMost(area.width.toFloat())
    val y1 = (all.maxOf { it.y } + pad).coerceAtMost(area.height.toFloat())
    val scale = 2f
    val bmp = Bitmap.createBitmap(((x1 - x0) * scale).toInt().coerceAtLeast(4), ((y1 - y0) * scale).toInt().coerceAtLeast(4),
        Bitmap.Config.ARGB_8888)
    val c = ACanvas(bmp)
    val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        this.color = color.toInt(); style = Paint.Style.STROKE; strokeWidth = 5f * scale
        strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND
    }
    for (s in strokes) {
        val p = APath()
        p.moveTo((s[0].x - x0) * scale, (s[0].y - y0) * scale)
        s.drop(1).forEach { p.lineTo((it.x - x0) * scale, (it.y - y0) * scale) }
        c.drawPath(p, paint)
    }
    signatureFile(ctx).outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
}

/** Confirmação da caixa posicionada (rubrica, assinatura digital ou comentário movido). */
@Composable
fun PlacementBar(d: ViewerDoc, onConfirm: (Placement) -> Unit) {
    val p = d.placing ?: return
    Surface(shadowElevation = 8.dp, shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.surface,
        modifier = Modifier.padding(12.dp).navigationBarsPadding()) {
        Row(Modifier.padding(start = 14.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Arraste para mover · puxe o canto para o tamanho", style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.weight(1f, fill = false))
            TextButton({ d.placing = null }) { Text("Cancelar") }
            TextButton({ d.placing = null; onConfirm(p) }) { Text(if (p.kind == Tool.NONE) "Mover" else "Confirmar") }
        }
    }
}

/** Ações sobre um comentário selecionado. */
@Composable
fun AnnotBar(vm: AppVm, d: ViewerDoc, onEditNote: (Editor.AnnotRef) -> Unit) {
    val a = d.selAnnot ?: return
    val frac = d.annots.firstOrNull { it.first == a }?.second
    Surface(shadowElevation = 8.dp, shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.surface,
        modifier = Modifier.padding(12.dp).navigationBarsPadding()) {
        Column(Modifier.padding(horizontal = 8.dp, vertical = 4.dp)) {
            Text(a.label + if (a.contents.isNotBlank()) ": ${a.contents.take(60)}" else "", style = MaterialTheme.typography.labelMedium,
                modifier = Modifier.padding(start = 6.dp, top = 4.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                (listOf(0xFFFFD400) + INK_COLORS).forEach { c ->
                    Box(Modifier.padding(3.dp).size(24.dp).clip(CircleShape).background(Color(c)).clickable {
                        d.selAnnot = null
                        vm.edit(d, "mudar a cor") { Editor.recolorAnnot(it, a, c) }
                    })
                }
                if (a.subtype == "Text") IconButton({ onEditNote(a) }) { Icon(Icons.Filled.EditNote, "Editar nota") }
                if (a.movable && frac != null) IconButton({
                    d.selAnnot = null
                    d.placing = Placement(Tool.NONE, a.page, frac.l, frac.t, frac.r, frac.b, (frac.r - frac.l) / (frac.b - frac.t).coerceAtLeast(0.001f), a)
                }) { Icon(Icons.Filled.OpenWith, "Mover") }
                IconButton({ d.selAnnot = null; vm.edit(d, "excluir o comentário") { Editor.deleteAnnot(it, a) } }) {
                    Icon(Icons.Filled.Delete, "Excluir comentário", tint = Color(0xFFD7373F))
                }
                IconButton({ d.selAnnot = null }) { Icon(Icons.Filled.Close, "Fechar") }
            }
        }
    }
}
