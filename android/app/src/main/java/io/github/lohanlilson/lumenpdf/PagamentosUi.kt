package io.github.lohanlilson.lumenpdf

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.QrCode2
import androidx.compose.material.icons.filled.ScreenRotation
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

private val OK = Color(0xFF2D9D78)
private val BAD = Color(0xFFD7373F)
private val INFO = Color(0xFF1473E6)

fun copyText(ctx: Context, label: String, text: String) {
    (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText(label, text))
}

/** Faixa no topo: o boleto/Pix/nota encontrado, com botão de copiar (ou o aviso, se algo não confere). */
@Composable
fun PaymentsBanner(d: ViewerDoc, onCopied: (String) -> Unit, onOpen: () -> Unit) {
    val items = d.payments ?: return
    if (items.isEmpty() || d.paymentsHidden) return
    val ctx = LocalContext.current
    val main = items.firstOrNull { !it.ok } ?: items.first()
    val bad = !main.ok
    Surface(color = if (bad) Color(0xFFFDE8E9) else Color(0xFFEEF3FC), modifier = Modifier.fillMaxWidth().clickable(onClick = onOpen)) {
        Row(Modifier.padding(start = 14.dp, end = 4.dp, top = 6.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(if (bad) Icons.Filled.Warning else Icons.Filled.QrCode2, null, tint = if (bad) BAD else INFO)
            Column(Modifier.padding(start = 8.dp).weight(1f)) {
                Text(main.title + (if (main.summary.isNotEmpty()) " · " + main.summary else ""), color = Color(0xFF222222),
                    style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, maxLines = 2)
                if (bad) Text(main.problem, color = Color(0xFFB0262E), style = MaterialTheme.typography.bodySmall)
                else if (main.source == "texto e código") Text(if (main.kind == "pix") "✔ confere com o QR Code" else "✔ confere com o código de barras",
                    color = OK, style = MaterialTheme.typography.bodySmall)
                if (items.size > 1) Text("Ver todos (${items.size})", color = INFO, style = MaterialTheme.typography.labelMedium)
            }
            if (!bad) TextButton({ copyText(ctx, main.title, main.copy); onCopied(main.copyLabel.replace("Copiar", "Copiado:")) }) {
                Text(if (main.kind == "pix") "Copiar Pix" else if (main.kind == "nfe") "Copiar chave" else "Copiar linha")
            }
            IconButton({ d.paymentsHidden = true }) { Icon(Icons.Filled.Close, "Fechar", tint = Color(0xFF555555)) }
        }
    }
}

/** Lista com tudo o que foi encontrado. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PaymentsSheet(d: ViewerDoc, onGoto: (Int) -> Unit, onDismiss: () -> Unit) {
    val items = d.payments ?: emptyList()
    val ctx = LocalContext.current
    ModalBottomSheet(onDismissRequest = onDismiss) {
        val bad = items.count { !it.ok }
        Text("Boletos, Pix e notas fiscais", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 20.dp))
        Text(if (items.isEmpty()) "Nada encontrado neste documento." else "${items.size} encontrado(s)" + (if (bad > 0) " — $bad com problema" else ""),
            color = if (bad > 0) BAD else MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp))
        LazyColumn(contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 40.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(items) { it -> PaymentCard(it, onCopy = { copyText(ctx, it.title, it.copy) }, onGoto = { onGoto(it.page) }) }
        }
    }
}

@Composable
private fun PaymentCard(it: PayItem, onCopy: () -> Unit, onGoto: () -> Unit) {
    val fg = if (it.ok) OK else BAD
    var copied by remember { mutableStateOf(false) }
    Surface(shape = RoundedCornerShape(10.dp), border = BorderStroke(1.dp, fg), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(if (it.ok) Icons.Filled.CheckCircle else Icons.Filled.Warning, null, tint = fg)
                Text(it.title, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 6.dp).weight(1f))
                Text("pág. ${it.page + 1}", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelMedium)
            }
            if (!it.ok) Text(it.problem, color = BAD, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 4.dp))
            else if (it.source == "texto e código") Text("Texto impresso confere com o " + (if (it.kind == "pix") "QR Code" else "código de barras"),
                color = OK, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 4.dp))
            SelectionContainer {
                Column(Modifier.padding(top = 6.dp)) {
                    it.details.forEach { (k, v) ->
                        Row(Modifier.padding(vertical = 1.dp)) {
                            Text("$k:", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall, modifier = Modifier.width(104.dp))
                            Text(v, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
            Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (it.ok) OutlinedButton({ onCopy(); copied = true }) { Text(if (copied) "Copiado ✔" else it.copyLabel) }
                TextButton(onGoto) { Text("Ir para a página") }
            }
        }
    }
}

/** Aviso: páginas de lado ou de cabeça para baixo. */
@Composable
fun OrientBanner(d: ViewerDoc, onFix: () -> Unit) {
    val f = d.orientFixes
    if (f.isEmpty()) return
    val pages = f.keys.sorted()
    val lst = pages.take(10).joinToString(", ") { "${it + 1}" } + if (pages.size > 10) "…" else ""
    Surface(color = Color(0xFFFFF6DD), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(start = 14.dp, end = 4.dp, top = 4.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.ScreenRotation, null, tint = Color(0xFFC58A00))
            Text((if (pages.size == 1) "A página $lst está" else "As páginas $lst estão") + " de lado ou de cabeça para baixo",
                color = Color(0xFF222222), style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(start = 8.dp).weight(1f))
            TextButton(onFix) { Text("Endireitar") }
            IconButton({ d.orientFixes = emptyMap() }) { Icon(Icons.Filled.Close, "Fechar", tint = Color(0xFF555555)) }
        }
    }
}
