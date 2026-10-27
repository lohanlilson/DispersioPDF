package io.github.lohanlilson.dispersio

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.DarkMode
import androidx.compose.material.icons.filled.TextDecrease
import androidx.compose.material.icons.filled.TextIncrease
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties

/** Junta as linhas de cada parágrafo (o PDF quebra as linhas pela largura da página). */
fun reflow(text: String): List<String> {
    val lines = text.replace("\r\n", "\n").replace('\r', '\n').split('\n').map { it.trim() }
    val out = ArrayList<String>()
    val cur = StringBuilder()
    fun flush() { if (cur.isNotBlank()) out += cur.toString().trim(); cur.clear() }
    for ((i, l) in lines.withIndex()) {
        if (l.isEmpty()) { flush(); continue }
        val prev = cur.toString()
        val listItem = Regex("^([•\\-–·]|\\(?[0-9ivxIVX]{1,4}[.)]|[a-zA-Z][.)])\\s").containsMatchIn(l)
        val endsSentence = prev.trimEnd().lastOrNull()?.let { it in ".:;!?" } == true
        val title = l.length < 60 && l == l.uppercase() && l.any { it.isLetter() }
        if (cur.isNotEmpty() && (listItem || title || (endsSentence && l.first().isUpperCase() && lines.getOrNull(i - 1).orEmpty().length < 45))) flush()
        if (cur.isNotEmpty()) {
            if (cur.endsWith("-") && l.first().isLowerCase()) cur.setLength(cur.length - 1) else cur.append(' ')
        }
        cur.append(l)
        if (title) flush()
    }
    flush()
    return out
}

/** Modo leitura: o texto das páginas em letra ajustável, sem precisar de zoom. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReadingMode(vm: AppVm, d: ViewerDoc, onClose: () -> Unit) {
    val sp0 = remember { vm.getApplication<android.app.Application>().getSharedPreferences("prefs", 0) }
    var size by remember { mutableStateOf(sp0.getFloat("leitura_tamanho", 19f)) }
    var dark by remember { mutableStateOf(d.night) }
    val bg = if (dark) Color(0xFF15151A) else Color(0xFFFBF8F1)
    val fg = if (dark) Color(0xFFE6E2D8) else Color(0xFF1E1C18)
    val state = rememberLazyListState(initialFirstVisibleItemIndex = d.page)
    LaunchedEffect(size) { sp0.edit().putFloat("leitura_tamanho", size).apply() }
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Scaffold(containerColor = bg, topBar = {
            TopAppBar(title = { Text("Modo leitura", color = fg) },
                navigationIcon = { IconButton(onClose) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Voltar", tint = fg) } },
                actions = {
                    IconButton({ size = (size - 2f).coerceAtLeast(12f) }) { Icon(Icons.Filled.TextDecrease, "Diminuir letra", tint = fg) }
                    IconButton({ size = (size + 2f).coerceAtMost(40f) }) { Icon(Icons.Filled.TextIncrease, "Aumentar letra", tint = fg) }
                    IconButton({ dark = !dark }) { Icon(Icons.Filled.DarkMode, "Modo noturno", tint = fg) }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = bg))
        }) { pad ->
            LazyColumn(state = state, modifier = Modifier.fillMaxSize().background(bg).padding(pad),
                contentPadding = PaddingValues(horizontal = 20.dp, vertical = 12.dp)) {
                items(d.pageCount) { i ->
                    val paras by produceState<List<String>?>(null, d.pdf, i) { value = reflow(vm.engine.pageText(d.pdf, i)) }
                    Column(Modifier.fillMaxWidth().padding(bottom = 18.dp), verticalArrangement = Arrangement.spacedBy((size * 0.6f).dp)) {
                        Row { Text("Página ${i + 1}", color = fg.copy(alpha = 0.55f), style = MaterialTheme.typography.labelMedium) }
                        val p = paras
                        when {
                            p == null -> Text("…", color = fg)
                            p.isEmpty() -> Text("(página sem texto: é uma imagem. Use “Reconhecer texto (OCR)” para ler aqui.)",
                                color = fg.copy(alpha = 0.6f), fontSize = (size * 0.8f).sp)
                            else -> SelectionContainer {
                                Column(verticalArrangement = Arrangement.spacedBy((size * 0.6f).dp)) {
                                    p.forEach { Text(it, color = fg, fontSize = size.sp, lineHeight = (size * 1.45f).sp) }
                                }
                            }
                        }
                        HorizontalDivider(color = fg.copy(alpha = 0.12f))
                    }
                }
            }
        }
    }
}
