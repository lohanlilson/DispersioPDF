package io.github.lohanlilson.dispersio

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.ArrowDownward
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.FileProvider
import java.io.File

/** Fila do Dispersio (igual à impressora do computador): o que você compartilha com "Fila do Dispersio" fica aqui
 *  para juntar num PDF só, imprimir tudo, compartilhar ou salvar. */
object Fila {
    fun dir(ctx: Context) = File(ctx.filesDir, "fila").apply { mkdirs() }
    private fun orderFile(ctx: Context) = File(dir(ctx), ".ordem")

    fun list(ctx: Context): List<File> {
        val files = dir(ctx).listFiles { f -> f.isFile && f.name.lowercase().endsWith(".pdf") }?.toList().orEmpty()
        val order = runCatching { orderFile(ctx).readLines() }.getOrDefault(emptyList())
        return files.sortedWith(compareBy({ order.indexOf(it.name).let { i -> if (i < 0) Int.MAX_VALUE else i } }, { it.lastModified() }))
    }

    fun saveOrder(ctx: Context, files: List<File>) = orderFile(ctx).writeText(files.joinToString("\n") { it.name })

    private fun freeName(ctx: Context, name: String): File {
        val base = name.substringBeforeLast('.').ifBlank { "Documento" }.replace(Regex("[\\\\/:*?\"<>|]"), "_")
        var f = File(dir(ctx), "$base.pdf"); var n = 2
        while (f.exists()) f = File(dir(ctx), "$base ($n).pdf").also { n++ }
        return f
    }

    /** Copia para a fila. Imagens viram páginas de PDF. Devolve quantos entraram. */
    fun add(ctx: Context, uris: List<Uri>): Int {
        var n = 0
        val order = list(ctx).toMutableList()
        for (u in uris) {
            runCatching {
                val name = displayName(ctx, u)
                val mime = ctx.contentResolver.getType(u) ?: ""
                val dest = freeName(ctx, name)
                if (mime.startsWith("image/")) {
                    val bmp = decodeImage(ctx, u, 2000)
                    Editor.imagesToPdf(listOf(bmp), dest)
                } else {
                    ctx.contentResolver.openInputStream(u)!!.use { i -> dest.outputStream().use { i.copyTo(it) } }
                }
                order += dest; n++
            }
        }
        saveOrder(ctx, order)
        return n
    }

    fun merge(ctx: Context, files: List<File>): File {
        val stamp = java.text.SimpleDateFormat("yyyyMMdd_HHmm", java.util.Locale.US).format(java.util.Date())
        val out = File(File(ctx.filesDir, "recebidos").apply { mkdirs() }, "Fila_$stamp.pdf")
        if (files.size == 1) files[0].copyTo(out, overwrite = true) else Editor.merge(files, out)
        return out
    }

    fun share(ctx: Context, files: List<File>) {
        val uris = ArrayList(files.map { FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", it) })
        val i = if (uris.size == 1) Intent(Intent.ACTION_SEND).putExtra(Intent.EXTRA_STREAM, uris[0])
        else Intent(Intent.ACTION_SEND_MULTIPLE).putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
        i.type = "application/pdf"
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        ctx.startActivity(Intent.createChooser(i, "Compartilhar").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FilaScreen(vm: AppVm, onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    var files by remember { mutableStateOf(Fila.list(ctx)) }
    var sel by remember { mutableStateOf(files.map { it.name }.toSet()) }
    fun refresh() { files = Fila.list(ctx); sel = sel.intersect(files.map { it.name }.toSet()) }
    val chosen = files.filter { it.name in sel }
    val target = chosen.ifEmpty { files }
    val what = if (chosen.isEmpty() || chosen.size == files.size) "todos" else "${chosen.size} selecionado(s)"

    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Scaffold(topBar = {
            TopAppBar(title = { Text("Fila do Dispersio (${files.size})") },
                navigationIcon = { IconButton(onDismiss) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Voltar") } },
                actions = { if (files.isNotEmpty()) TextButton({ files.forEach { it.delete() }; refresh(); vm.refreshQueue() }) { Text("Limpar") } })
        }) { pad ->
            Column(Modifier.fillMaxSize().padding(pad)) {
                if (files.isEmpty()) {
                    Text("A fila está vazia.\n\nEm qualquer app (WhatsApp, e-mail, Arquivos, Galeria), toque em Compartilhar e escolha " +
                        "“Fila do Dispersio”. Os arquivos ficam aqui para juntar num PDF só, imprimir ou enviar de uma vez.",
                        modifier = Modifier.padding(20.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
                    return@Column
                }
                Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button({ vm.queueMerge(target, open = true); onDismiss() }, Modifier.weight(1f)) { Text("Juntar e abrir") }
                    OutlinedButton({ vm.queuePrint(target) { printPdf(ctx, it, it.name) } }, Modifier.weight(1f)) { Text("Imprimir") }
                }
                Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton({ vm.queueShareMerged(target) }, Modifier.weight(1f)) { Text("Juntar e enviar") }
                    OutlinedButton({ Fila.share(ctx, target) }, Modifier.weight(1f)) { Text("Enviar separados") }
                }
                Text("Ações valem para: $what", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp))
                HorizontalDivider()
                LazyColumn(Modifier.fillMaxSize()) {
                    itemsIndexed(files, key = { _, f -> f.name }) { i, f ->
                        Row(Modifier.fillMaxWidth().clickable { vm.open(Uri.fromFile(f), fromPicker = false); onDismiss() }.padding(start = 4.dp, end = 4.dp),
                            verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(f.name in sel, { on -> sel = if (on) sel + f.name else sel - f.name })
                            Column(Modifier.weight(1f)) {
                                Text(f.name, maxLines = 2, overflow = TextOverflow.Ellipsis)
                                Text("%.1f MB".format(f.length() / 1e6), style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            IconButton({ if (i > 0) { val l = files.toMutableList(); l.add(i - 1, l.removeAt(i)); Fila.saveOrder(ctx, l); refresh() } },
                                enabled = i > 0) { Icon(Icons.Filled.ArrowUpward, "Subir") }
                            IconButton({ if (i < files.size - 1) { val l = files.toMutableList(); l.add(i + 1, l.removeAt(i)); Fila.saveOrder(ctx, l); refresh() } },
                                enabled = i < files.size - 1) { Icon(Icons.Filled.ArrowDownward, "Descer") }
                            IconButton({ f.delete(); refresh(); vm.refreshQueue() }) { Icon(Icons.Filled.Delete, "Remover") }
                            Spacer(Modifier.width(2.dp))
                        }
                        HorizontalDivider()
                    }
                }
            }
        }
    }
}
