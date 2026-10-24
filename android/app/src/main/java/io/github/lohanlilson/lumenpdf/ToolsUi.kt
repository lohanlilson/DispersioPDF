package io.github.lohanlilson.lumenpdf

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp

@Composable
private fun Choice(label: String, selected: Boolean, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().selectable(selected, onClick = onClick), verticalAlignment = Alignment.CenterVertically) {
        RadioButton(selected, onClick); Text(label)
    }
}

/** (lado máximo das imagens em pixels, qualidade JPEG) */
@Composable
fun CompressDialog(sizeKb: Long, onDismiss: () -> Unit, onOk: (Int, Float) -> Unit) {
    var level by remember { mutableIntStateOf(1) }
    val levels = listOf(Triple("Leve (melhor qualidade)", 2200, 0.8f), Triple("Média (recomendado)", 1500, 0.65f),
        Triple("Forte (menor arquivo)", 1000, 0.5f))
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Comprimir PDF") },
        text = {
            Column {
                if (sizeKb > 0) Text("Tamanho atual: %.1f MB".format(sizeKb / 1024.0), style = MaterialTheme.typography.bodySmall)
                levels.forEachIndexed { i, (l, _, _) -> Choice(l, level == i) { level = i } }
                Text("Reduz as imagens do documento. O texto continua nítido.", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        },
        confirmButton = { TextButton({ val (_, px, q) = levels[level]; onOk(px, q) }) { Text("Comprimir") } },
        dismissButton = { TextButton(onDismiss) { Text("Cancelar") } })
}

@Composable
fun ProtectDialog(protected: Boolean, onDismiss: () -> Unit, onRemove: () -> Unit,
                  onOk: (user: String, owner: String, print: Boolean, copy: Boolean, edit: Boolean) -> Unit) {
    var pwd by remember { mutableStateOf("") }
    var pwd2 by remember { mutableStateOf("") }
    var owner by remember { mutableStateOf("") }
    var print by remember { mutableStateOf(true) }
    var copy by remember { mutableStateOf(false) }
    var edit by remember { mutableStateOf(false) }
    val ok = pwd.length >= 3 && pwd == pwd2
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Proteger com senha") },
        text = {
            Column {
                if (protected) {
                    Text("Este documento já tem senha.", style = MaterialTheme.typography.bodySmall)
                    TextButton(onRemove) { Text("Remover a senha") }
                }
                OutlinedTextField(pwd, { pwd = it }, label = { Text("Senha para abrir") }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
                OutlinedTextField(pwd2, { pwd2 = it }, label = { Text("Repita a senha") }, singleLine = true,
                    isError = pwd2.isNotEmpty() && pwd != pwd2,
                    visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
                OutlinedTextField(owner, { owner = it }, label = { Text("Senha de permissões (opcional)") }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
                Row(Modifier.clickable { print = !print }, verticalAlignment = Alignment.CenterVertically) { Checkbox(print, { print = it }); Text("Permitir imprimir") }
                Row(Modifier.clickable { copy = !copy }, verticalAlignment = Alignment.CenterVertically) { Checkbox(copy, { copy = it }); Text("Permitir copiar texto") }
                Row(Modifier.clickable { edit = !edit }, verticalAlignment = Alignment.CenterVertically) { Checkbox(edit, { edit = it }); Text("Permitir editar") }
            }
        },
        confirmButton = { TextButton({ onOk(pwd, owner, print, copy, edit) }, enabled = ok) { Text("Proteger") } },
        dismissButton = { TextButton(onDismiss) { Text("Cancelar") } })
}

@Composable
fun WatermarkDialog(onDismiss: () -> Unit, onOk: (String, Float) -> Unit) {
    var text by remember { mutableStateOf("CONFIDENCIAL") }
    var opacity by remember { mutableFloatStateOf(0.18f) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Marca d'água") },
        text = {
            Column {
                OutlinedTextField(text, { text = it }, label = { Text("Texto") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Text("Transparência: ${(opacity * 100).toInt()}%", style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 8.dp))
                Slider(opacity, { opacity = it }, valueRange = 0.05f..0.6f)
            }
        },
        confirmButton = { TextButton({ onOk(text, opacity) }, enabled = text.isNotBlank()) { Text("Aplicar") } },
        dismissButton = { TextButton(onDismiss) { Text("Cancelar") } })
}

@Composable
fun PageNumbersDialog(onDismiss: () -> Unit, onOk: (String) -> Unit) {
    val formats = listOf("{n}", "{n} de {total}", "Página {n} de {total}", "Pág. {n}")
    var f by remember { mutableIntStateOf(2) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Numerar páginas") },
        text = {
            Column {
                formats.forEachIndexed { i, fm -> Choice(fm.replace("{n}", "1").replace("{total}", "10"), f == i) { f = i } }
                Text("Os números ficam no rodapé, centralizados.", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        },
        confirmButton = { TextButton({ onOk(formats[f]) }) { Text("Numerar") } },
        dismissButton = { TextButton(onDismiss) { Text("Cancelar") } })
}
