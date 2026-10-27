package io.github.lohanlilson.lumenpdf

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

@Composable
fun LumenRoot(vm: AppVm) {
    val d = vm.doc
    // atalhos do ícone do app
    val scan = rememberScanner { vm.openScanned(it) }
    val pick = androidx.activity.compose.rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.OpenDocument()) { u -> if (u != null) vm.open(u, fromPicker = true) }
    LaunchedEffect(vm.pendingAction) {
        when (vm.pendingAction) {
            "scan" -> scan()
            "open" -> pick.launch(arrayOf("application/pdf"))
        }
        vm.pendingAction = null
    }
    if (d == null) {
        HomeScreen(vm)
    } else {
        BackHandler { if (d.editing && d.tool != Tool.NONE) d.tool = Tool.NONE else vm.requestClose() }
        ViewerScreen(vm, d)
    }
    if (vm.loading) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
    }
    vm.error?.let { msg ->
        AlertDialog(onDismissRequest = { vm.error = null }, confirmButton = { TextButton({ vm.error = null }) { Text("OK") } },
            title = { Text("Dispersio PDF") }, text = { Text(msg) })
    }
    vm.password?.let { p -> PasswordDialog(p, onCancel = { vm.password = null }, onOk = { vm.submitPassword(it) }) }
    vm.update?.let { u -> UpdateDialog(u, onDismiss = { vm.update = null }) }
}

@Composable
private fun PasswordDialog(p: PendingPassword, onCancel: () -> Unit, onOk: (String) -> Unit) {
    var pwd by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Documento protegido") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(if (p.wrong) "Senha incorreta. Tente de novo." else "“${p.name}” está protegido por senha.")
                OutlinedTextField(pwd, { pwd = it }, label = { Text("Senha") }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
            }
        },
        confirmButton = { TextButton({ onOk(pwd) }, enabled = pwd.isNotEmpty()) { Text("Abrir") } },
        dismissButton = { TextButton(onCancel) { Text("Cancelar") } },
    )
}

@Composable
private fun UpdateDialog(u: UpdateInfo, onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var progress by remember { mutableStateOf<Float?>(null) }
    var err by remember { mutableStateOf<String?>(null) }
    var file by remember { mutableStateOf<java.io.File?>(null) }
    LaunchedEffect(file) {
        // depois de baixar, instala assim que o Android permitir
        file?.let { if (Updater.canInstall(ctx)) Updater.install(ctx, it) }
    }
    AlertDialog(
        onDismissRequest = { if (progress == null) onDismiss() },
        title = { Text("Nova versão: ${u.version}") },
        text = {
            Column(Modifier.heightIn(max = 380.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Você está usando a versão ${BuildConfig.VERSION_NAME}.", style = MaterialTheme.typography.bodySmall)
                if (u.notes.isNotBlank()) Text(u.notes.replace("**", ""), style = MaterialTheme.typography.bodyMedium)
                progress?.let { LinearProgressIndicator(progress = { it }, modifier = Modifier.fillMaxWidth()) }
                if (file != null && !Updater.canInstall(ctx)) {
                    Text("Permita que o Dispersio PDF instale atualizações e toque em Instalar.", color = MaterialTheme.colorScheme.primary)
                }
                err?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            val f = file
            if (f != null) {
                TextButton({
                    if (Updater.canInstall(ctx)) Updater.install(ctx, f) else Updater.askInstallPermission(ctx)
                }) { Text(if (Updater.canInstall(ctx)) "Instalar" else "Permitir") }
            } else {
                TextButton(enabled = progress == null, onClick = {
                    progress = 0f
                    err = null
                    scope.launch {
                        try {
                            file = Updater.download(ctx, u) { progress = it }
                        } catch (e: Exception) {
                            err = "Não foi possível baixar: ${e.message}"
                        }
                        progress = null
                    }
                }) { Text("Atualizar") }
            }
        },
        dismissButton = { TextButton(onDismiss, enabled = progress == null) { Text("Depois") } },
    )
}
