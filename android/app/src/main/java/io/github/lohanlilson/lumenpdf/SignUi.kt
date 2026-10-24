package io.github.lohanlilson.lumenpdf

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.security.KeyChain
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

fun Context.findActivity(): Activity? {
    var c: Context? = this
    while (c is ContextWrapper) {
        if (c is Activity) return c
        c = c.baseContext
    }
    return null
}

/** Escolha do certificado e dados da assinatura. */
@Composable
fun CertSignDialog(vm: AppVm, fieldName: String?, onDismiss: () -> Unit,
                   onSign: (cert: suspend () -> SigningCert, reason: String, location: String, tsa: Boolean) -> Unit) {
    val ctx = LocalContext.current
    val prefs = remember { ctx.getSharedPreferences("prefs", 0) }
    var useAndroid by remember { mutableStateOf(prefs.getString("cert_src", "pfx") == "android") }
    var alias by remember { mutableStateOf(prefs.getString("cert_alias", null)) }
    var pfxList by remember { mutableStateOf(Certs.storedPfx(ctx)) }
    var pfx by remember { mutableStateOf(pfxList.firstOrNull { it.name == prefs.getString("cert_pfx", "") } ?: pfxList.firstOrNull()) }
    var pwd by remember { mutableStateOf("") }
    var reason by remember { mutableStateOf(prefs.getString("sign_reason", "") ?: "") }
    var location by remember { mutableStateOf(prefs.getString("sign_location", "") ?: "") }
    var tsa by remember { mutableStateOf(prefs.getBoolean("sign_tsa", true)) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { u ->
        if (u != null) vm.importPfx(u)?.let { f -> pfxList = Certs.storedPfx(ctx); pfx = f; useAndroid = false }
    }
    val ready = if (useAndroid) alias != null else pfx != null && pwd.isNotEmpty()
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (fieldName != null) "Assinar “$fieldName”" else "Assinar com certificado digital") },
        text = {
            Column(Modifier.heightIn(max = 520.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(Modifier.fillMaxWidth().selectable(!useAndroid) { useAndroid = false }, verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(!useAndroid, { useAndroid = false }); Text("Arquivo de certificado (.pfx / .p12)")
                }
                if (!useAndroid) Column(Modifier.padding(start = 12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    pfxList.forEach { f ->
                        Row(Modifier.fillMaxWidth().selectable(pfx == f) { pfx = f }, verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(pfx == f, { pfx = f }); Text(f.name, style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                    OutlinedButton({ picker.launch(arrayOf("application/x-pkcs12", "application/octet-stream", "*/*")) }) {
                        Text("Importar arquivo .pfx…")
                    }
                    if (pfx != null) OutlinedTextField(pwd, { pwd = it }, label = { Text("Senha do certificado") }, singleLine = true,
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), modifier = Modifier.fillMaxWidth())
                }
                Row(Modifier.fillMaxWidth().selectable(useAndroid) { useAndroid = true }, verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(useAndroid, { useAndroid = true }); Text("Certificado instalado no Android")
                }
                if (useAndroid) Column(Modifier.padding(start = 12.dp)) {
                    Text(alias?.let { "Selecionado: $it" } ?: "Nenhum selecionado", style = MaterialTheme.typography.bodySmall)
                    OutlinedButton({
                        val act = ctx.findActivity() ?: return@OutlinedButton
                        KeyChain.choosePrivateKeyAlias(act, { a -> if (a != null) alias = a }, arrayOf("RSA", "EC"), null, null, -1, alias)
                    }) { Text("Escolher certificado…") }
                    Text("Para instalar: Configurações › Segurança › Criptografia e credenciais › Instalar certificado.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                HorizontalDivider(Modifier.padding(vertical = 4.dp))
                OutlinedTextField(reason, { reason = it }, label = { Text("Motivo (opcional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(location, { location = it }, label = { Text("Local (opcional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Row(Modifier.fillMaxWidth().clickable { tsa = !tsa }, verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(tsa, { tsa = it }); Text("Carimbo de tempo (precisa de internet)")
                }
            }
        },
        confirmButton = {
            TextButton(enabled = ready, onClick = {
                prefs.edit().putString("cert_src", if (useAndroid) "android" else "pfx").putString("cert_alias", alias)
                    .putString("cert_pfx", pfx?.name).putString("sign_reason", reason).putString("sign_location", location)
                    .putBoolean("sign_tsa", tsa).apply()
                val a = alias
                val f = pfx
                val p = pwd
                onSign(if (useAndroid) ({ Certs.fromKeyChain(ctx, a!!) }) else ({ Certs.fromPfx(f!!, p) }), reason, location, tsa)
            }) { Text("Assinar") }
        },
        dismissButton = { TextButton(onDismiss) { Text("Cancelar") } },
    )
}

private val fmt = SimpleDateFormat("dd/MM/yyyy HH:mm", Locale("pt", "BR"))

/** Faixa no topo quando o documento tem assinaturas. */
@Composable
fun SignatureBanner(d: ViewerDoc, onOpen: () -> Unit) {
    val sigs = d.signatures
    if (sigs.isEmpty()) return
    val bad = sigs.any { !it.ok }
    val later = !bad && sigs.any { !it.coversWhole } && d.dirty.not() && sigs.last().coversWhole.not()
    val (bg, fg, icon) = when {
        bad -> Triple(Color(0xFFFDE8E9), Color(0xFFD7373F), Icons.Filled.Error)
        later -> Triple(Color(0xFFFFF6DD), Color(0xFFC58A00), Icons.Filled.Warning)
        else -> Triple(Color(0xFFE7F6EE), Color(0xFF2D9D78), Icons.Filled.CheckCircle)
    }
    val msg = when {
        bad -> "Pelo menos uma assinatura é inválida"
        sigs.size == 1 -> "Assinado por ${sigs[0].signer} — assinatura íntegra"
        else -> "${sigs.size} assinaturas — todas íntegras"
    }
    Surface(color = bg, modifier = Modifier.fillMaxWidth().clickable(onClick = onOpen)) {
        Row(Modifier.padding(horizontal = 14.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, tint = fg)
            Text(msg, color = Color(0xFF222222), style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(start = 8.dp).weight(1f))
            Text("Detalhes", color = fg, style = MaterialTheme.typography.labelLarge)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SignaturesSheet(d: ViewerDoc, onChanges: (SigInfo) -> Unit = {}, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Text("Assinaturas digitais", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 6.dp))
        LazyColumn(contentPadding = PaddingValues(start = 20.dp, end = 20.dp, bottom = 40.dp)) {
            items(d.signatures) { s ->
                Column(Modifier.padding(vertical = 10.dp)) {
                    val color = if (s.ok) Color(0xFF2D9D78) else Color(0xFFD7373F)
                    Text((if (s.ok) "✔ " else "✖ ") + s.signer, color = color, fontWeight = FontWeight.SemiBold)
                    s.document?.let { Text("CPF/CNPJ: $it", style = MaterialTheme.typography.bodySmall) }
                    Text("Data: " + ((s.tsaDate ?: s.date)?.let { fmt.format(it) } ?: "—") +
                        (if (s.tsaDate != null) " (carimbo de tempo)" else " (relógio do signatário)"), style = MaterialTheme.typography.bodySmall)
                    Text(when {
                        s.error != null -> "Assinatura inválida: ${s.error}"
                        !s.intact -> "O conteúdo assinado foi alterado"
                        s.coversWhole -> "O documento não foi alterado desde a assinatura"
                        else -> "Houve acréscimos depois desta assinatura (outras assinaturas, campos ou comentários)"
                    }, style = MaterialTheme.typography.bodySmall)
                    if (s.issuer.isNotBlank()) Text("Emitido por: ${s.issuer}" + (s.validUntil?.let { " · válido até ${fmt.format(it).take(10)}" } ?: ""),
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    s.reason?.let { Text("Motivo: $it", style = MaterialTheme.typography.bodySmall) }
                    s.location?.let { Text("Local: $it", style = MaterialTheme.typography.bodySmall) }
                    if (!s.coversWhole && s.ok && s.revisionEnd > 0) TextButton({ onChanges(s) }) { Text("O que mudou depois desta assinatura") }
                    Text("A identidade (cadeia ICP-Brasil) é conferida no Lumen PDF do computador.",
                        style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                HorizontalDivider()
            }
        }
    }
}
