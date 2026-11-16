package io.github.lohanlilson.dispersio

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.provider.DocumentsContract
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.StarBorder
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.util.zip.ZipInputStream

/** Biblioteca de quadrinhos/mangás: uma pasta escolhida; cada subpasta é uma série, cada arquivo um capítulo. */
object Library {
    data class Chapter(val uri: Uri, val name: String) { val key get() = Comic.key(uri) }
    data class Series(val id: String, val name: String, val chapters: List<Chapter>)

    val TAGS = listOf("lendo" to "Lendo", "quero" to "Quero ler", "concluido" to "Concluído")

    private fun sp(ctx: Context) = ctx.getSharedPreferences("biblioteca", Context.MODE_PRIVATE)
    fun folder(ctx: Context) = sp(ctx).getString("pasta", null)?.let { Uri.parse(it) }
    fun setFolder(ctx: Context, u: Uri) = sp(ctx).edit().putString("pasta", u.toString()).apply()
    fun manualTag(ctx: Context, id: String) = sp(ctx).getString("tag_$id", null)
    fun setTag(ctx: Context, id: String, tag: String?) = sp(ctx).edit().apply { if (tag == null) remove("tag_$id") else putString("tag_$id", tag) }.apply()
    fun fav(ctx: Context, id: String) = sp(ctx).getBoolean("fav_$id", false)
    fun setFav(ctx: Context, id: String, on: Boolean) = sp(ctx).edit().putBoolean("fav_$id", on).apply()

    /** Fração lida da série (capítulos inteiros contam 1; o atual, a fração das páginas). */
    fun progress(ctx: Context, s: Series): Float =
        if (s.chapters.isEmpty()) 0f else s.chapters.sumOf { (Comic.progress(ctx, it.key) ?: 0f).toDouble() }.toFloat() / s.chapters.size

    fun lastRead(ctx: Context, s: Series) = s.chapters.maxOfOrNull { Comic.lastRead(ctx, it.key) } ?: 0L

    /** Etiqueta escolhida ou automática: lido até o fim = Concluído; começou = Lendo. */
    fun tag(ctx: Context, s: Series): String? {
        manualTag(ctx, s.id)?.let { return it }
        val p = progress(ctx, s)
        return when { p >= 0.995f -> "concluido"; p > 0f -> "lendo"; else -> null }
    }

    /** Primeiro capítulo não terminado (para “Continuar”). */
    fun resume(ctx: Context, s: Series): Int = s.chapters.indexOfFirst { (Comic.progress(ctx, it.key) ?: 0f) < 0.995f }.let { if (it < 0) 0 else it }

    fun scan(ctx: Context, tree: Uri): List<Series> {
        fun children(docId: String): List<Triple<String, String, Boolean>> {
            val out = ArrayList<Triple<String, String, Boolean>>()
            val u = DocumentsContract.buildChildDocumentsUriUsingTree(tree, docId)
            ctx.contentResolver.query(u, arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                DocumentsContract.Document.COLUMN_MIME_TYPE), null, null, null)?.use { c ->
                while (c.moveToNext()) out += Triple(c.getString(0), c.getString(1) ?: "", c.getString(2) == DocumentsContract.Document.MIME_TYPE_DIR)
            }
            return out
        }
        fun chaptersIn(docId: String, depth: Int): List<Chapter> = children(docId).flatMap { (id, name, dir) ->
            when {
                dir && depth < 2 -> chaptersIn(id, depth + 1)
                !dir && Comic.isComicName(name) -> listOf(Chapter(DocumentsContract.buildDocumentUriUsingTree(tree, id), name))
                else -> emptyList()
            }
        }.sortedWith(compareBy(Comic.naturalOrder) { it.name })
        val root = DocumentsContract.getTreeDocumentId(tree)
        val top = children(root)
        val series = top.filter { it.third }.mapNotNull { (id, name, _) ->
            chaptersIn(id, 1).takeIf { it.isNotEmpty() }?.let { Series(Comic.key(Uri.parse(tree.toString() + "/" + id)), name, it) }
        }.toMutableList()
        // arquivos soltos na pasta raiz: cada um vira uma “série” de um capítulo
        top.filter { !it.third && Comic.isComicName(it.second) }.forEach { (id, name, _) ->
            val ch = Chapter(DocumentsContract.buildDocumentUriUsingTree(tree, id), name)
            series += Series(ch.key, name.substringBeforeLast('.'), listOf(ch))
        }
        return series.sortedWith(compareBy(Comic.naturalOrder) { it.name })
    }

    /** Capa: a primeira imagem do primeiro capítulo, guardada pequena. (Lê só o começo do arquivo.) */
    fun cover(ctx: Context, s: Series): Bitmap? {
        val f = File(File(ctx.filesDir, "capas").apply { mkdirs() }, s.id + ".jpg")
        if (f.exists()) return BitmapFactory.decodeFile(f.path)
        val ch = s.chapters.firstOrNull() ?: return null
        val bytes = runCatching {
            ctx.contentResolver.openInputStream(ch.uri)!!.use { raw ->
                val zin = ZipInputStream(raw.buffered())
                var best: Pair<String, ByteArray>? = null
                var seen = 0
                while (true) {
                    val e = zin.nextEntry ?: break
                    if (e.isDirectory || e.name.substringAfterLast('.', "").lowercase() !in Comic.IMG || e.name.startsWith("__MACOSX")) continue
                    val b = zin.readBytes()
                    if (best == null || Comic.naturalOrder.compare(e.name, best.first) < 0) best = e.name to b
                    if (++seen >= 4) break           // as primeiras imagens bastam (a capa costuma ser a primeira)
                }
                best?.second
            }
        }.getOrNull()
        val big = bytes?.let { b ->
            val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(b, 0, b.size, o)
            var sample = 1
            while (o.outWidth / (sample * 2) >= 300) sample *= 2
            BitmapFactory.decodeByteArray(b, 0, b.size, BitmapFactory.Options().apply { inSampleSize = sample })
        } ?: return null
        runCatching { f.outputStream().use { big.compress(Bitmap.CompressFormat.JPEG, 85, it) } }
        return big
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LibraryScreen(vm: AppVm, onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    var tree by remember { mutableStateOf(Library.folder(ctx)) }
    var series by remember { mutableStateOf<List<Library.Series>?>(null) }
    var filter by remember { mutableStateOf("todos") }
    var open by remember { mutableStateOf<Library.Series?>(null) }
    var tick by remember { mutableIntStateOf(0) }      // atualiza progresso/etiquetas ao voltar
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { u ->
        if (u != null) {
            runCatching { ctx.contentResolver.takePersistableUriPermission(u, Intent.FLAG_GRANT_READ_URI_PERMISSION) }
            Library.setFolder(ctx, u); tree = u; series = null
        }
    }
    LaunchedEffect(tree) { tree?.let { t -> series = withContext(Dispatchers.IO) { runCatching { Library.scan(ctx, t) }.getOrDefault(emptyList()) } } }
    LaunchedEffect(vm.comic) { if (vm.comic == null) tick++ }

    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        val sel = open
        if (sel != null) { SeriesScreen(vm, sel, tick) { open = null; tick++ }; return@Dialog }
        Scaffold(topBar = {
            TopAppBar(title = { Text("Quadrinhos e mangás") },
                navigationIcon = { IconButton(onDismiss) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Voltar") } },
                actions = { IconButton({ pick.launch(tree) }) { Icon(Icons.Filled.Folder, "Escolher pasta") } })
        }) { pad ->
            Column(Modifier.fillMaxSize().padding(pad)) {
                if (tree == null) {
                    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("Escolha a pasta onde ficam seus quadrinhos e mangás. Cada subpasta vira uma série; os arquivos .cbz/.cbr dentro dela são os capítulos.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Button({ pick.launch(null) }, Modifier.padding(top = 16.dp)) { Text("Escolher pasta") }
                    }
                    return@Column
                }
                val all = series
                if (all == null) { LinearProgressIndicator(Modifier.fillMaxWidth()); return@Column }
                val tabs = listOf("todos" to "Todos", "lendo" to "Lendo", "quero" to "Quero ler", "concluido" to "Concluídos", "fav" to "Favoritos")
                LazyRow(Modifier.padding(horizontal = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    items(tabs) { (k, label) -> FilterChip(filter == k, { filter = k }, label = { Text(label) }) }
                }
                @Suppress("UNUSED_EXPRESSION") tick
                val shown = all.filter { s ->
                    when (filter) { "todos" -> true; "fav" -> Library.fav(ctx, s.id); else -> Library.tag(ctx, s) == filter }
                }.sortedByDescending { Library.lastRead(ctx, it) }
                if (shown.isEmpty()) Text(if (all.isEmpty()) "Nenhum .cbz ou .cbr nesta pasta." else "Nada aqui ainda.",
                    Modifier.padding(24.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
                LazyVerticalGrid(GridCells.Adaptive(110.dp), Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(10.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    items(shown, key = { it.id }) { s -> SeriesCard(s, tick) { open = s } }
                }
            }
        }
    }
}

@Composable
private fun SeriesCard(s: Library.Series, tick: Int, onClick: () -> Unit) {
    val ctx = LocalContext.current
    val cover by produceState<Bitmap?>(null, s.id) { value = withContext(Dispatchers.IO) { Library.cover(ctx, s) } }
    val p = remember(s.id, tick) { Library.progress(ctx, s) }
    Column(Modifier.clickable(onClick = onClick)) {
        Box(Modifier.fillMaxWidth().aspectRatio(0.68f).clip(RoundedCornerShape(8.dp)).background(Color(0xFF2A2A2E)), contentAlignment = Alignment.Center) {
            val c = cover
            if (c != null) Image(c.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
            else Text(s.name.take(1).uppercase(), color = Color.White, style = MaterialTheme.typography.headlineMedium)
            if (Library.fav(ctx, s.id)) Icon(Icons.Filled.Star, null, Modifier.align(Alignment.TopEnd).padding(4.dp), tint = Color(0xFFFFC107))
        }
        if (p > 0f) LinearProgressIndicator({ p }, Modifier.fillMaxWidth().padding(top = 3.dp))
        Text(s.name, maxLines = 2, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium)
        Text("${s.chapters.size} cap. · ${(p * 100).toInt()}%", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SeriesScreen(vm: AppVm, s: Library.Series, tick: Int, onBack: () -> Unit) {
    val ctx = LocalContext.current
    var ver by remember { mutableIntStateOf(0) }
    var tag by remember(s.id, tick) { mutableStateOf(Library.tag(ctx, s)) }
    var fav by remember(s.id) { mutableStateOf(Library.fav(ctx, s.id)) }
    Scaffold(topBar = {
        TopAppBar(title = { Text(s.name, maxLines = 1, overflow = TextOverflow.Ellipsis) },
            navigationIcon = { IconButton(onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Voltar") } },
            actions = {
                IconButton({ fav = !fav; Library.setFav(ctx, s.id, fav) }) {
                    Icon(if (fav) Icons.Filled.Star else Icons.Filled.StarBorder, "Favorito", tint = if (fav) Color(0xFFFFC107) else MaterialTheme.colorScheme.onSurface)
                }
            })
    }) { pad ->
        Column(Modifier.fillMaxSize().padding(pad)) {
            LazyRow(Modifier.padding(horizontal = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                items(Library.TAGS) { (k, label) ->
                    FilterChip(tag == k, { tag = if (tag == k) null else k; Library.setTag(ctx, s.id, tag) }, label = { Text(label) })
                }
            }
            val r = remember(s.id, tick, ver) { Library.resume(ctx, s) }
            Button({ vm.openComicFromLibrary(s, r) }, Modifier.fillMaxWidth().padding(12.dp)) {
                Text(if (Comic.progress(ctx, s.chapters[r].key) != null) "Continuar: ${s.chapters[r].name.substringBeforeLast('.')}" else "Começar a ler",
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            LazyColumn(Modifier.fillMaxSize()) {
                items(s.chapters.size) { i ->
                    val ch = s.chapters[i]
                    val p = remember(ch.key, tick, ver) { Comic.progress(ctx, ch.key) }
                    Row(Modifier.fillMaxWidth().clickable { vm.openComicFromLibrary(s, i) }.padding(horizontal = 16.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(ch.name.substringBeforeLast('.'), maxLines = 1, overflow = TextOverflow.Ellipsis,
                                color = if (p != null && p >= 0.995f) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface)
                            if (p != null && p < 0.995f) LinearProgressIndicator({ p }, Modifier.fillMaxWidth().padding(top = 4.dp))
                        }
                        if (p != null && p >= 0.995f) Icon(Icons.Filled.CheckCircle, "Lido", tint = MaterialTheme.colorScheme.primary)
                        else TextButton({ Comic.savePage(ctx, ch.key, 0, 1); ver++; tag = Library.tag(ctx, s) }) { Text("Marcar lido") }
                    }
                    HorizontalDivider()
                }
            }
        }
    }
}
