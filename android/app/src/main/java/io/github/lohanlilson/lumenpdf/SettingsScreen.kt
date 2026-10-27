package io.github.lohanlilson.lumenpdf

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(vm: AppVm, onClose: () -> Unit) {
    val ctx = LocalContext.current
    val p = vm.prefs
    var name by remember { mutableStateOf(vm.authorName().takeIf { it != "Dispersio PDF" } ?: "") }
    var pads by remember { mutableStateOf(0) }
    var certs by remember { mutableStateOf(Certs.storedPfx(ctx)) }
    var signPad by remember { mutableStateOf(false) }
    var myData by remember { mutableStateOf(false) }
    Dialog(onDismissRequest = { vm.setAuthorName(name); onClose() },
        properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Scaffold(topBar = {
            TopAppBar(title = { Text("Preferências") },
                navigationIcon = { IconButton({ vm.setAuthorName(name); onClose() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Voltar") } })
        }) { pad ->
            Column(Modifier.fillMaxSize().padding(pad).verticalScroll(rememberScrollState()).padding(horizontal = 18.dp)) {
                Section("Geral")
                OutlinedTextField(name, { name = it }, label = { Text("Seu nome (autor dos comentários)") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth())
                Text("Tema do app", style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(top = 12.dp))
                listOf("sistema" to "Igual ao celular", "claro" to "Claro", "escuro" to "Escuro").forEach { (k, l) ->
                    Row(Modifier.fillMaxWidth().clickable { p.theme = k }, verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(p.theme == k, { p.theme = k }); Text(l)
                    }
                }
                Toggle("Salvar automaticamente as alterações", p.autosave) { p.autosave = it }
                Text("Salva o documento alguns segundos depois de editar, ao sair do app e ao fechar. A versão de antes fica em " +
                    "⋮ › Versões anteriores. Documentos assinados continuam pedindo para salvar.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Toggle("Mostrar boletos, Pix e notas fiscais encontrados", p.detectPayments) { p.detectPayments = it }
                Toggle("Avisar quando houver páginas de lado ou de cabeça para baixo", p.detectOrientation) { p.detectOrientation = it }
                Toggle("Oferecer tradução quando o documento estiver em outro idioma", p.offerTranslation) { p.offerTranslation = it }
                Text("Traduzir para", style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(top = 8.dp))
                listOf("" to "Idioma do celular (${Traducao.NAMES[Traducao.deviceLanguage()]})", "pt" to "Português", "en" to "Inglês", "es" to "Espanhol").forEach { (k, l) ->
                    Row(Modifier.fillMaxWidth().clickable { p.translateTo = k }, verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(p.translateTo == k, { p.translateTo = k }); Text(l)
                    }
                }
                Toggle("Verificar atualizações automaticamente", p.autoUpdate) { p.autoUpdate = it }

                Section("Formulários")
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(if (Autofill.hasAny(ctx)) "Meus dados salvos" else "Nenhum dado salvo", Modifier.weight(1f))
                    TextButton({ myData = true }) { Text("Editar meus dados") }
                }

                Section("Leitura")
                Toggle("Abrir documentos no modo noturno", p.nightPages) { p.nightPages = it }
                Toggle("Reabrir na última página lida", p.rememberPage) { p.rememberPage = it }
                Toggle("Manter a tela ligada enquanto leio", p.keepScreenOn) { p.keepScreenOn = it }
                Toggle("Destacar campos de formulário", p.highlightFields) { p.highlightFields = it }

                Section("Comentários")
                Text("Cor do destaque", style = MaterialTheme.typography.bodyLarge)
                Row(Modifier.padding(vertical = 6.dp)) {
                    listOf(0xFFFFD400, 0xFF7CE07C, 0xFF7FD3FF, 0xFFFF9ECF, 0xFFFFB347).forEach { c ->
                        Box(Modifier.padding(4.dp).size(32.dp).clip(CircleShape).background(Color(c))
                            .border(if (p.highlightColor == c) 3.dp else 0.dp, MaterialTheme.colorScheme.outline, CircleShape)
                            .clickable { p.highlightColor = c })
                    }
                }

                Section("Assinatura")
                Toggle("Carimbo de tempo por padrão", p.tsaDefault) { p.tsaDefault = it; pads++ }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(if (signatureFile(ctx).exists()) "Rubrica salva" else "Nenhuma rubrica salva", Modifier.weight(1f))
                    TextButton({ signPad = true }) { Text("Desenhar") }
                    if (signatureFile(ctx).exists()) TextButton({ signatureFile(ctx).delete(); pads++ }) { Text("Apagar") }
                }
                Text("Certificados importados (.pfx)", style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(top = 8.dp))
                if (certs.isEmpty()) Text("Nenhum. Importe na hora de assinar.", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                certs.forEach { f ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(f.name, style = MaterialTheme.typography.bodyMedium)
                            if (PasswordVault.has(ctx, f.name)) Text("Senha guardada com a digital", style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        IconButton({ PasswordVault.forget(ctx, f.name); f.delete(); certs = Certs.storedPfx(ctx) }) { Icon(Icons.Filled.Delete, "Remover ${f.name}") }
                    }
                }

                Section("Sobre")
                Text("Dispersio PDF para Android ${BuildConfig.VERSION_NAME}")
                Text("Desenvolvido por Lohan Lilson S. Lopes", style = MaterialTheme.typography.bodySmall)
                Text("lohanlilson@gmail.com", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(bottom = 40.dp))
                if (pads < 0) Text("")
            }
        }
    }
    if (myData) MyDataDialog { myData = false; pads++ }
    if (signPad) SignaturePad(ctx, onDismiss = { signPad = false }) { signPad = false; pads++ }
}

@Composable
private fun Section(title: String) {
    HorizontalDivider(Modifier.padding(top = 16.dp))
    Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold,
        color = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(top = 12.dp, bottom = 6.dp))
}

@Composable
private fun Toggle(label: String, value: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().clickable { onChange(!value) }.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, Modifier.weight(1f))
        Switch(value, onChange)
    }
}
