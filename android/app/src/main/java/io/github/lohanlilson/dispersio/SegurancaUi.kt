package io.github.lohanlilson.dispersio

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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

private val RED = Color(0xFFD7373F)
private val RED_BG = Color(0xFFFDE8E9)
private val AMBER = Color(0xFFC77700)
private val AMBER_BG = Color(0xFFFFF4E0)

private val REMOVABLE = listOf("Contém JavaScript", "Tenta abrir", "Executa uma ação", "Abre um site sozinho", "Tem um programa", "Tem um arquivo compactado")

/** Faixa no topo quando o documento tem algo típico de golpe. */
@Composable
fun SecurityBanner(vm: AppVm, d: ViewerDoc) {
    val list = d.threats
    if (list.isEmpty() || d.threatsHidden) return
    var details by remember { mutableStateOf(false) }
    val top = list.first()
    val danger = top.level >= Seguranca.DANGER
    val fg = if (danger) RED else AMBER
    Surface(color = if (danger) RED_BG else AMBER_BG, modifier = Modifier.fillMaxWidth().clickable { details = true }) {
        Row(Modifier.padding(start = 14.dp, end = 4.dp, top = 6.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Warning, null, tint = fg)
            Column(Modifier.padding(start = 8.dp).weight(1f)) {
                Text(if (danger) "Este documento pode ser golpe" else "Atenção a este documento", color = fg,
                    fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                Text(top.title + if (list.size > 1) " (+${list.size - 1})" else "", color = Color(0xFF222222),
                    style = MaterialTheme.typography.bodySmall, maxLines = 2)
            }
            TextButton({ details = true }) { Text("Detalhes") }
            IconButton({ d.threatsHidden = true }) { Icon(Icons.Filled.Close, "Fechar", tint = Color(0xFF555555)) }
        }
    }
    if (details) {
        val canClean = list.any { t -> REMOVABLE.any { t.title.startsWith(it) } }
        AlertDialog(onDismissRequest = { details = false },
            icon = { Icon(Icons.Filled.Warning, null, tint = fg) },
            title = { Text("Segurança do documento") },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    list.forEach { t ->
                        Text((if (t.level >= Seguranca.DANGER) "⚠ " else "• ") + t.title, fontWeight = FontWeight.SemiBold)
                        if (t.detail.isNotEmpty()) Text(t.detail, style = MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.height(8.dp))
                    }
                    Text("O Dispersio PDF não executa código do documento nem abre sites sem perguntar. Se não esperava este arquivo, " +
                        "não digite senhas, não pague e confirme com quem mandou por outro meio.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            },
            confirmButton = { TextButton({ details = false }) { Text("Ok") } },
            dismissButton = if (canClean) ({ TextButton({ details = false; vm.removeDanger(d) }) { Text("Remover o perigo") } }) else null)
    }
}

/** Confirmação antes de abrir um site a partir do documento. */
@Composable
fun LinkDialog(vm: AppVm, chk: Seguranca.LinkCheck, onOpen: () -> Unit, onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    val lvl = chk.level
    val danger = lvl >= Seguranca.DANGER
    val fg = if (danger) RED else if (lvl >= Seguranca.WARN) AMBER else MaterialTheme.colorScheme.primary
    var trust by remember { mutableStateOf(false) }
    AlertDialog(onDismissRequest = onDismiss,
        icon = if (lvl >= Seguranca.WARN) ({ Icon(Icons.Filled.Warning, null, tint = fg) }) else null,
        title = {
            Text(when {
                danger -> "Cuidado: este link parece golpe"
                lvl >= Seguranca.WARN -> "Atenção antes de abrir"
                else -> "Abrir este site?"
            }, color = if (lvl >= Seguranca.WARN) fg else Color.Unspecified)
        },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text("Site: " + chk.domain.ifEmpty { chk.url }, fontWeight = FontWeight.SemiBold)
                Text(if (chk.url.length > 220) chk.url.take(220) + "…" else chk.url, style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (chk.risks.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Surface(shape = RoundedCornerShape(8.dp), border = BorderStroke(1.dp, fg),
                        color = if (danger) RED_BG else if (lvl >= Seguranca.WARN) AMBER_BG else MaterialTheme.colorScheme.surface) {
                        Column(Modifier.padding(10.dp)) {
                            chk.risks.sortedByDescending { it.level }.forEach {
                                Text((if (it.level >= Seguranca.DANGER) "⚠ " else "• ") + it.text, color = Color(0xFF222222),
                                    style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
                if (danger) {
                    Spacer(Modifier.height(8.dp))
                    Text("Na dúvida, não abra. Entre no site digitando o endereço oficial, ou confirme com quem mandou por outro meio (telefone, aplicativo do banco).",
                        style = MaterialTheme.typography.bodySmall)
                }
                if (lvl < Seguranca.WARN && chk.domain.isNotEmpty()) Row(verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.clickable { trust = !trust }) {
                    Checkbox(trust, { trust = it })
                    Text("Abrir links de ${chk.domain} sem perguntar", style = MaterialTheme.typography.bodySmall)
                }
                TextButton({ copyText(ctx, "Endereço", chk.url); vm.toast = "Endereço copiado" }) { Text("Copiar endereço") }
            }
        },
        confirmButton = {
            TextButton({
                if (trust) vm.prefs.trustedSites = vm.prefs.trustedSites + chk.domain.lowercase()
                onOpen()
            }) { Text(if (danger) "Abrir mesmo assim" else "Abrir", color = if (danger) RED else Color.Unspecified) }
        },
        dismissButton = { TextButton(onDismiss) { Text("Não abrir") } })
}

/** true = pode abrir direto, sem perguntar. */
fun linkOpensDirectly(prefs: Prefs, chk: Seguranca.LinkCheck): Boolean =
    chk.level < Seguranca.WARN && (!prefs.confirmLinks || chk.domain.lowercase() in prefs.trustedSites)
