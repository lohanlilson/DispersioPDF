package io.github.lohanlilson.dispersio

import android.graphics.Bitmap
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Sessão de leitura: o capítulo aberto e, se veio da biblioteca, os outros capítulos da série. */
class ComicSession(
    val book: Comic.Book,
    val ratios: List<Float>,
    val chapters: List<Library.Chapter>,
    val index: Int,
    val series: String,
    val defaultMode: String,
)

private val MODES = listOf("webtoon" to "Webtoon", "pagina" to "Página", "manga" to "Mangá")

@Composable
private fun PageImage(book: Comic.Book, i: Int, cache: PageCache, ratio: Float, maxW: Int, modifier: Modifier = Modifier) {
    val bmp by produceState<Bitmap?>(cache.get(i), book, i) {
        if (value == null) value = withContext(Dispatchers.IO) { book.bitmap(i, maxW)?.also { cache.put(i, it) } }
    }
    val b = bmp
    if (b == null) {
        Box(modifier.fillMaxWidth().aspectRatio(1f / ratio.coerceIn(0.2f, 6f)).background(Color(0xFF1A1A1A)), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(Modifier.width(28.dp), color = Color.Gray)
        }
    } else {
        Image(b.asImageBitmap(), null, modifier.fillMaxWidth().aspectRatio(b.width.toFloat() / b.height), contentScale = ContentScale.FillWidth)
    }
}

/** Página com zoom (pinça e toque duplo) para os modos Página e Mangá. */
@Composable
private fun ZoomPage(book: Comic.Book, i: Int, cache: PageCache, ratio: Float, maxW: Int, onTap: () -> Unit) {
    var scale by remember { mutableFloatStateOf(1f) }
    var off by remember { mutableStateOf(Offset.Zero) }
    Box(Modifier.fillMaxSize().pointerInput(i) {
        detectTapGestures(onTap = { onTap() }, onDoubleTap = { scale = if (scale > 1.2f) 1f else 2.5f; off = Offset.Zero })
    }.pointerInput(i) {
        detectTransformGestures(panZoomLock = true) { _, pan, zoom, _ ->
            scale = (scale * zoom).coerceIn(1f, 5f)
            off = if (scale > 1f) off + pan else Offset.Zero
        }
    }, contentAlignment = Alignment.Center) {
        PageImage(book, i, cache, ratio, maxW, Modifier.graphicsLayer(scaleX = scale, scaleY = scale, translationX = off.x, translationY = off.y))
    }
}

@Composable
fun ComicScreen(vm: AppVm, s: ComicSession) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val book = s.book
    val total = book.pages.size
    val cache = remember(book) { PageCache() }
    val maxW = with(LocalDensity.current) { (LocalConfiguration.current.screenWidthDp.dp.toPx() * 1.5f).toInt() }
    var mode by remember(book) { mutableStateOf(Comic.mode(ctx, s.series, s.defaultMode)) }
    var bars by remember { mutableStateOf(false) }
    val start = remember(book) { Comic.savedPage(ctx, book.key).coerceIn(0, total - 1) }
    var page by remember(book) { mutableStateOf(start) }
    val next = s.chapters.getOrNull(s.index + 1)
    val prev = s.chapters.getOrNull(s.index - 1)
    BackHandler { vm.closeComic() }
    LaunchedEffect(page) { Comic.savePage(ctx, book.key, page, total) }

    Box(Modifier.fillMaxSize().background(Color.Black)) {
        when (mode) {
            "webtoon" -> {
                val list = rememberLazyListState(initialFirstVisibleItemIndex = start)
                LaunchedEffect(list) { snapshotFlow { list.firstVisibleItemIndex }.collect { if (it < total) page = it } }
                LaunchedEffect(mode) { if (list.firstVisibleItemIndex != page) list.scrollToItem(page) }
                LazyColumn(Modifier.fillMaxSize().pointerInput(Unit) { detectTapGestures(onTap = { bars = !bars }) }, state = list) {
                    items(total, key = { it }) { i -> PageImage(book, i, cache, s.ratios.getOrElse(i) { 1.4f }, maxW) }
                    item { EndCard(next, total) { vm.comicChapter(1) } }
                }
            }
            else -> {
                val pager = rememberPagerState(initialPage = page) { total + 1 }
                LaunchedEffect(pager) { snapshotFlow { pager.currentPage }.collect { if (it < total) page = it } }
                LaunchedEffect(mode) { if (pager.currentPage != page) pager.scrollToPage(page) }
                HorizontalPager(pager, Modifier.fillMaxSize(), reverseLayout = mode == "manga", beyondViewportPageCount = 1) { i ->
                    if (i < total) ZoomPage(book, i, cache, s.ratios.getOrElse(i) { 1.4f }, maxW) { bars = !bars }
                    else Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { EndCard(next, total) { vm.comicChapter(1) } }
                }
            }
        }

        AnimatedVisibility(bars, Modifier.align(Alignment.TopCenter)) {
            Row(Modifier.fillMaxWidth().background(Color(0xE6202024)).statusBarsPadding().padding(4.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton({ vm.closeComic() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Voltar", tint = Color.White) }
                Column(Modifier.weight(1f)) {
                    Text(book.name.substringBeforeLast('.'), color = Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("Página ${page + 1} de $total", color = Color(0xFFBBBBBB), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        AnimatedVisibility(bars, Modifier.align(Alignment.BottomCenter)) {
            Column(Modifier.fillMaxWidth().background(Color(0xE6202024)).navigationBarsPadding().padding(horizontal = 12.dp, vertical = 6.dp)) {
                Slider(page.toFloat(), { v -> page = v.toInt().coerceIn(0, total - 1) }, valueRange = 0f..(total - 1).coerceAtLeast(1).toFloat(),
                    colors = SliderDefaults.colors(thumbColor = Color.White, activeTrackColor = Color(0xFF1473E6)))
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    TextButton({ vm.comicChapter(-1) }, enabled = prev != null) { Text("‹ Cap.", color = if (prev != null) Color.White else Color.Gray) }
                    Spacer(Modifier.weight(1f))
                    MODES.forEach { (k, label) ->
                        FilterChip(mode == k, { mode = k; Comic.saveMode(ctx, s.series, k) }, label = { Text(label) })
                    }
                    Spacer(Modifier.weight(1f))
                    TextButton({ vm.comicChapter(1) }, enabled = next != null) { Text("Cap. ›", color = if (next != null) Color.White else Color.Gray) }
                }
            }
        }
    }
}

@Composable
private fun EndCard(next: Library.Chapter?, total: Int, onNext: () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(vertical = 48.dp, horizontal = 24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text("Fim do capítulo ($total páginas)", color = Color.White)
        Spacer(Modifier.height(14.dp))
        if (next != null) Button(onNext) { Text("Próximo: ${next.name.substringBeforeLast('.')}", maxLines = 1, overflow = TextOverflow.Ellipsis) }
        else Text("Este é o último capítulo da série.", color = Color.Gray)
    }
}
