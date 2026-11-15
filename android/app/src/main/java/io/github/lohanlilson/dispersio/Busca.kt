package io.github.lohanlilson.dispersio

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.Normalizer

/** Busca em vários PDFs: ignora acentos e maiúsculas; CPF/CNPJ com ou sem pontuação. */
object Busca {
    const val MAX_PER_FILE = 50

    /** Minúsculas e sem acento, com o mesmo tamanho (para recortar o trecho original). */
    fun fold(t: String): String {
        val sb = StringBuilder(t.length)
        for (c in t) {
            if (c.code < 128) { sb.append(c.lowercaseChar()); continue }
            val d = Normalizer.normalize(c.toString(), Normalizer.Form.NFD).replace(Regex("\\p{Mn}+"), "")
            sb.append((d.firstOrNull() ?: c).lowercaseChar())
        }
        return sb.toString()
    }

    fun pattern(query: String): Regex? {
        val q = fold(query.trim())
        if (q.isEmpty()) return null
        val digits = q.filter { it.isDigit() }
        if (digits.length >= 6 && Regex("^[\\d.\\-/\\s]+$").matches(q))
            return Regex("(?<!\\d)" + digits.map { Regex.escape(it.toString()) }.joinToString("[.\\-/\\s]?") + "(?!\\d)")
        return Regex(q.split(Regex("\\s+")).joinToString("\\s+") { Regex.escape(it) })
    }

    data class Hit(val page: Int, val snippet: String, val match: String)
    data class FileHits(val uri: Uri, val name: String, val hits: List<Hit>)

    fun searchText(pages: List<String>, re: Regex): List<Hit> {
        val out = ArrayList<Hit>()
        for ((p, text) in pages.withIndex()) {
            for (m in re.findAll(fold(text))) {
                val a = m.range.first; val b = m.range.last + 1
                val s0 = maxOf(0, a - 60); val s1 = minOf(text.length, b + 60)
                out += Hit(p, (if (s0 > 0) "…" else "") + text.substring(s0, s1).replace(Regex("\\s+"), " ").trim() + (if (s1 < text.length) "…" else ""),
                    text.substring(a, b))
                if (out.size >= MAX_PER_FILE) return out
            }
        }
        return out
    }

    /** PDFs dentro de uma pasta escolhida (e subpastas). */
    fun listTree(ctx: Context, tree: Uri): List<Pair<Uri, String>> {
        val out = ArrayList<Pair<Uri, String>>()
        fun walk(docId: String, depth: Int) {
            if (depth > 6 || out.size > 2000) return
            val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, docId)
            ctx.contentResolver.query(children, arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_DISPLAY_NAME, DocumentsContract.Document.COLUMN_MIME_TYPE), null, null, null)?.use { c ->
                while (c.moveToNext()) {
                    val id = c.getString(0); val name = c.getString(1) ?: ""; val mime = c.getString(2) ?: ""
                    if (mime == DocumentsContract.Document.MIME_TYPE_DIR) walk(id, depth + 1)
                    else if (mime == "application/pdf" || name.lowercase().endsWith(".pdf"))
                        out += DocumentsContract.buildDocumentUriUsingTree(tree, id) to name
                }
            }
        }
        runCatching { walk(DocumentsContract.getTreeDocumentId(tree), 0) }
        return out.sortedBy { it.second.lowercase() }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SearchAllScreen(vm: AppVm, onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val sp = remember { ctx.getSharedPreferences("busca", Context.MODE_PRIVATE) }
    var query by remember { mutableStateOf("") }
    var tree by remember { mutableStateOf(sp.getString("pasta", null)?.let { Uri.parse(it) }) }
    var useFolder by remember { mutableStateOf(tree != null) }
    val results = remember { mutableStateListOf<Busca.FileHits>() }
    var status by remember { mutableStateOf("Acentos e maiúsculas não importam. CPF e CNPJ com ou sem pontos.") }
    var progress by remember { mutableStateOf<Float?>(null) }
    var job by remember { mutableStateOf<Job?>(null) }
    val pickFolder = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        if (uri != null) {
            runCatching { ctx.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION) }
            sp.edit().putString("pasta", uri.toString()).apply()
            tree = uri; useFolder = true
        }
    }

    fun run() {
        val re = Busca.pattern(query) ?: return
        job?.cancel()
        results.clear()
        job = scope.launch {
            val files: List<Pair<Uri, String>> = withContext(Dispatchers.IO) {
                if (useFolder && tree != null) Busca.listTree(ctx, tree!!)
                else vm.recentList.map { Uri.parse(it.uri) to it.name }
            }
            var unread = 0
            for ((i, f) in files.withIndex()) {
                status = "Procurando… ${i + 1} de ${files.size}: ${f.second}"
                progress = (i + 1f) / maxOf(1, files.size)
                val pages = withContext(Dispatchers.IO) {
                    runCatching {
                        val pdf = vm.engine.open(ctx, f.first)
                        try { (0 until pdf.sizes.size).map { vm.engine.pageText(pdf, it) } } finally { vm.engine.close(pdf) }
                    }.getOrNull()
                }
                if (pages == null) { unread++; continue }
                val hits = withContext(Dispatchers.Default) { Busca.searchText(pages, re) }
                if (hits.isNotEmpty()) results += Busca.FileHits(f.first, f.second, hits)
            }
            progress = null
            val n = results.sumOf { it.hits.size }
            status = (if (n > 0) "$n resultado(s) em ${results.size} arquivo(s)." else "Nada encontrado em ${files.size} arquivo(s).") +
                (if (unread > 0) " $unread não puderam ser lidos (protegidos ou danificados)." else "")
        }
    }

    Dialog(onDismissRequest = { job?.cancel(); onDismiss() }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Scaffold(topBar = {
            TopAppBar(title = { Text("Buscar em vários PDFs") },
                navigationIcon = { IconButton({ job?.cancel(); onDismiss() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Voltar") } })
        }) { pad ->
            Column(Modifier.fillMaxSize().padding(pad).padding(horizontal = 14.dp)) {
                OutlinedTextField(query, { query = it }, Modifier.fillMaxWidth(), singleLine = true,
                    placeholder = { Text("Nome, CPF, CNPJ, contrato…") },
                    trailingIcon = { IconButton({ run() }) { Icon(Icons.Filled.Search, "Buscar") } },
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search), keyboardActions = KeyboardActions(onSearch = { run() }))
                Row(Modifier.padding(vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    FilterChip(!useFolder, { useFolder = false }, label = { Text("Recentes") })
                    FilterChip(useFolder && tree != null, { if (tree == null) pickFolder.launch(null) else useFolder = true },
                        label = { Text(tree?.let { "Pasta: " + (it.lastPathSegment?.substringAfterLast(':') ?: "") } ?: "Escolher pasta…") })
                    if (tree != null) TextButton({ pickFolder.launch(tree) }) { Text("Trocar") }
                }
                progress?.let { LinearProgressIndicator({ it }, Modifier.fillMaxWidth()) }
                Text(status, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(vertical = 6.dp))
                LazyColumn(Modifier.fillMaxSize()) {
                    results.forEach { f ->
                        item(key = "f" + f.uri) {
                            Text("${f.name}  (${f.hits.size}${if (f.hits.size >= Busca.MAX_PER_FILE) "+" else ""})", fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.padding(top = 10.dp, bottom = 2.dp))
                        }
                        items(f.hits, key = { h -> "${f.uri}#${h.page}#${h.snippet.hashCode()}" }) { h ->
                            Column(Modifier.fillMaxWidth().clickable { vm.openAt(f.uri, f.name, h.page, h.match); onDismiss() }.padding(vertical = 6.dp)) {
                                Text("Página ${h.page + 1}", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                                Text(h.snippet, style = MaterialTheme.typography.bodySmall, maxLines = 3, overflow = TextOverflow.Ellipsis)
                            }
                            HorizontalDivider()
                        }
                    }
                }
            }
        }
    }
}
