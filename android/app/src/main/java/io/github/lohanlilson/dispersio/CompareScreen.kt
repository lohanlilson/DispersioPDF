package io.github.lohanlilson.dispersio

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlin.math.roundToInt

private val RED = Color(0x66D7373F)
private val GREEN = Color(0x662D9D78)

/** Comparação: abas Original | Revisada, alterações destacadas e navegação entre elas. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CompareScreen(vm: AppVm, c: CompareState, onClose: () -> Unit) {
    var tab by remember { mutableIntStateOf(1) }
    var cur by remember { mutableIntStateOf(if (c.changes.isEmpty()) -1 else 0) }
    val listA = rememberLazyListState()
    val listB = rememberLazyListState()
    LaunchedEffect(cur, tab) {
        val ch = c.changes.getOrNull(cur) ?: return@LaunchedEffect
        if (tab == 0) listA.animateScrollToItem((ch.rectsA.firstOrNull()?.first ?: ch.anchorA?.first ?: ch.pageA))
        else listB.animateScrollToItem((ch.rectsB.firstOrNull()?.first ?: ch.anchorB?.first ?: ch.pageB))
    }
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Scaffold(
            topBar = {
                Column {
                    TopAppBar(title = { Text(c.title) }, navigationIcon = { IconButton(onClose) { Icon(Icons.Filled.Close, "Fechar") } })
                    if (c.intro.isNotBlank()) Text(c.intro, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(horizontal = 16.dp))
                    TabRow(tab) {
                        Tab(tab == 0, { tab = 0 }, text = { Text(c.nameA, maxLines = 1, overflow = TextOverflow.Ellipsis) })
                        Tab(tab == 1, { tab = 1 }, text = { Text(c.nameB, maxLines = 1, overflow = TextOverflow.Ellipsis) })
                    }
                }
            },
            bottomBar = {
                Surface(shadowElevation = 8.dp) {
                    Row(Modifier.fillMaxWidth().navigationBarsPadding().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        IconButton({ if (c.changes.isNotEmpty()) cur = (cur - 1 + c.changes.size) % c.changes.size }, enabled = c.changes.isNotEmpty()) {
                            Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, "Alteração anterior")
                        }
                        Column(Modifier.weight(1f)) {
                            val ch = c.changes.getOrNull(cur)
                            if (ch == null) Text("Nenhuma diferença de texto encontrada", style = MaterialTheme.typography.bodyMedium)
                            else {
                                Text("${cur + 1} de ${c.changes.size} · texto ${ch.kind}", style = MaterialTheme.typography.labelLarge)
                                if (ch.textA.isNotEmpty()) Text("− ${ch.textA}", color = Color(0xFFB0282F), maxLines = 2, overflow = TextOverflow.Ellipsis,
                                    style = MaterialTheme.typography.bodySmall)
                                if (ch.textB.isNotEmpty()) Text("+ ${ch.textB}", color = Color(0xFF1F7A5C), maxLines = 2, overflow = TextOverflow.Ellipsis,
                                    style = MaterialTheme.typography.bodySmall)
                            }
                        }
                        IconButton({ if (c.changes.isNotEmpty()) cur = (cur + 1) % c.changes.size }, enabled = c.changes.isNotEmpty()) {
                            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, "Próxima alteração")
                        }
                    }
                }
            },
        ) { pad ->
            BoxWithConstraints(Modifier.fillMaxSize().padding(pad).background(MaterialTheme.colorScheme.surfaceVariant)) {
                val pageW = constraints.maxWidth - with(LocalDensity.current) { 16.dp.roundToPx() }
                val pdf = if (tab == 0) c.a else c.b
                LazyColumn(state = if (tab == 0) listA else listB, contentPadding = PaddingValues(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(pdf.sizes.size) { i ->
                        val sz = pdf.sizes[i]
                        val bmp by produceState<ImageBitmap?>(null, pdf, i) { value = vm.engine.render(pdf, i, minOf(pageW, 1600)).asImageBitmap() }
                        val dens = LocalDensity.current
                        Box(Modifier.size(with(dens) { pageW.toDp() }, with(dens) { (pageW * sz.ratio).roundToInt().toDp() })
                            .shadow(2.dp).background(Color.White)) {
                            bmp?.let { Image(it, "Página ${i + 1}", Modifier.fillMaxSize(), contentScale = ContentScale.FillBounds) }
                            Canvas(Modifier.fillMaxSize()) {
                                val w = size.width
                                c.changes.forEachIndexed { k, ch ->
                                    val strong = k == cur
                                    val rects = if (tab == 0) ch.rectsA else ch.rectsB
                                    val col = if (tab == 0) RED else GREEN
                                    rects.filter { it.first == i }.forEach { (_, r) ->
                                        drawRect(if (strong) col.copy(alpha = 0.75f) else col, Offset(r.l * w - 1, r.t * w - 1),
                                            Size((r.r - r.l) * w + 2, (r.b - r.t) * w + 2))
                                    }
                                    val anchor = if (tab == 0) ch.anchorA else ch.anchorB
                                    anchor?.takeIf { it.first == i }?.second?.let { r ->
                                        drawLine(if (tab == 0) Color(0xFF2D9D78) else Color(0xFFD7373F), Offset(r.r * w + 2, r.t * w - 2),
                                            Offset(r.r * w + 2, r.b * w + 2), if (strong) 5f else 3f)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
