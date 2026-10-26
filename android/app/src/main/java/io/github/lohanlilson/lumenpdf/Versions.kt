package io.github.lohanlilson.lumenpdf

import android.content.Context
import android.net.Uri
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Cópia de segurança ao salvar por cima: a versão anterior fica guardada (últimas 10, até 30 dias). */
object Versions {
    const val KEEP = 10
    private const val DAYS = 30L

    private fun dir(ctx: Context, uri: String) = File(ctx.filesDir, "versoes/${sha1(uri)}")

    /** Guarda o conteúdo atual do arquivo antes de ser substituído. */
    fun backup(ctx: Context, uri: String): File? {
        val u = Uri.parse(uri)
        val d = dir(ctx, uri).apply { mkdirs() }
        val f = File(d, SimpleDateFormat("yyyyMMdd-HHmmss-SSS", Locale.US).format(Date()) + ".pdf")
        val ok = runCatching {
            (if (u.scheme == "file") File(u.path!!).inputStream() else ctx.contentResolver.openInputStream(u)!!).use { i ->
                f.outputStream().use { i.copyTo(it) }
            }
        }.isSuccess
        if (!ok || f.length() == 0L) { f.delete(); return null }
        prune(d)
        return f
    }

    private fun prune(d: File) {
        val files = d.listFiles { f -> f.name.endsWith(".pdf") }?.sortedByDescending { it.name } ?: return
        val limit = System.currentTimeMillis() - DAYS * 86_400_000L
        files.forEachIndexed { i, f -> if (i >= KEEP || (i > 0 && f.lastModified() < limit)) f.delete() }
    }

    fun list(ctx: Context, uri: String): List<File> =
        dir(ctx, uri).listFiles { f -> f.name.endsWith(".pdf") }?.sortedByDescending { it.name } ?: emptyList()

    fun date(f: File): Date = runCatching { SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).parse(f.name.take(15)) }.getOrNull()
        ?: Date(f.lastModified())
}

@Composable
fun VersionsDialog(d: ViewerDoc, onDismiss: () -> Unit, onRestore: (File) -> Unit) {
    val ctx = LocalContext.current
    val list = remember(d.uri) { Versions.list(ctx, d.uri) }
    val fmt = remember { SimpleDateFormat("dd/MM/yyyy HH:mm:ss", Locale("pt", "BR")) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Versões anteriores") },
        text = {
            Column(Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState())) {
                if (list.isEmpty()) Text("Ainda não há versões anteriores deste arquivo.\n\nCada vez que você salva por cima, " +
                    "a versão anterior fica guardada aqui por até 30 dias.")
                else Text("Toque numa versão para restaurá-la:", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                list.forEach { f ->
                    Column(Modifier.fillMaxWidth().clickable { onRestore(f) }.padding(vertical = 10.dp)) {
                        Text("Salva por cima em ${fmt.format(Versions.date(f))}", style = MaterialTheme.typography.bodyMedium)
                        Text("%.2f MB".format(f.length() / 1048576.0), style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    HorizontalDivider()
                }
            }
        },
        confirmButton = { TextButton(onDismiss) { Text("Fechar") } })
}
