package io.github.lohanlilson.lumenpdf

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/** Todos os comentários do documento, com busca; tocar leva até o comentário. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CommentsSheet(d: ViewerDoc, onDismiss: () -> Unit, onPick: (Editor.AnnotRef) -> Unit) {
    var q by remember { mutableStateOf("") }
    val all = d.annots.map { it.first }.filter { it.subtype != "Popup" }
    val shown = all.filter { q.isBlank() || it.contents.contains(q, true) || it.label.contains(q, true) }
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.padding(horizontal = 16.dp)) {
            Text("Comentários (${all.size})", style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(q, { q = it }, label = { Text("Pesquisar comentários") }, singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp))
        }
        if (shown.isEmpty()) Text(if (all.isEmpty()) "Este documento não tem comentários." else "Nada encontrado.",
            modifier = Modifier.padding(16.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
        LazyColumn(contentPadding = PaddingValues(bottom = 32.dp)) {
            items(shown) { a ->
                Column(Modifier.fillMaxWidth().clickable { onPick(a) }.padding(horizontal = 16.dp, vertical = 10.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(a.label, style = MaterialTheme.typography.labelLarge, modifier = Modifier.weight(1f))
                        Text("pág. ${a.page + 1}", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    if (a.contents.isNotBlank()) Text(a.contents.take(160), style = MaterialTheme.typography.bodyMedium)
                }
                HorizontalDivider()
            }
        }
    }
}

@Composable
fun ReplaceDialog(onDismiss: () -> Unit, onOk: (find: String, repl: String, matchCase: Boolean, wholeWord: Boolean) -> Unit) {
    var f by remember { mutableStateOf("") }
    var r by remember { mutableStateOf("") }
    var c by remember { mutableStateOf(false) }
    var w by remember { mutableStateOf(false) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Localizar e substituir") },
        text = {
            Column {
                OutlinedTextField(f, { f = it }, label = { Text("Localizar") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(r, { r = it }, label = { Text("Substituir por") }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(top = 6.dp))
                Row(Modifier.clickable { c = !c }, verticalAlignment = Alignment.CenterVertically) { Checkbox(c, { c = it }); Text("Diferenciar maiúsculas e minúsculas") }
                Row(Modifier.clickable { w = !w }, verticalAlignment = Alignment.CenterVertically) { Checkbox(w, { w = it }); Text("Somente palavra inteira") }
                Text("Mantém a fonte, o tamanho e a cor de cada trecho.", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        },
        confirmButton = { TextButton({ onOk(f, r, c, w) }, enabled = f.isNotEmpty()) { Text("Substituir tudo") } },
        dismissButton = { TextButton(onDismiss) { Text("Cancelar") } })
}
