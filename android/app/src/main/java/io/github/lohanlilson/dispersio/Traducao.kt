package io.github.lohanlilson.dispersio

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Translate
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.common.model.DownloadConditions
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateLanguage
import com.google.mlkit.nl.translate.TranslateRemoteModel
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.Translator
import com.google.mlkit.nl.translate.TranslatorOptions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Locale

/** Tradução offline e gratuita (tradutor do Google que roda no aparelho; o pacote do idioma é baixado uma vez). */
object Traducao {
    val NAMES = linkedMapOf("pt" to "português", "en" to "inglês", "es" to "espanhol", "fr" to "francês", "de" to "alemão",
        "it" to "italiano", "zh" to "chinês", "ja" to "japonês", "ru" to "russo", "nl" to "holandês", "pl" to "polonês",
        "ko" to "coreano", "ar" to "árabe", "tr" to "turco", "sv" to "sueco", "uk" to "ucraniano", "ca" to "catalão")

    private val STOP = mapOf(
        "en" to "the of and to in is that for with as are was on by this be from which an or were at have has not but",
        "pt" to "de que e o a os as do da dos das em para com não uma um por se no na é ao como mais foi são",
        "es" to "de la que el en y los las del se por un una para con no es al lo como más fue son",
        "fr" to "de la le et les des en un une du est que pour dans qui par sur pas au avec sont ce",
        "de" to "der die und in den von zu das mit sich des auf für ist im dem nicht ein eine als auch",
        "it" to "di e il la che in per un una del della le non con è sono si da al gli",
    ).mapValues { it.value.split(" ").toSet() }

    /** Idioma do texto pelas palavras mais comuns; null se não der para saber. */
    fun detect(text: String): String? {
        if (Regex("[\\u4e00-\\u9fff]").findAll(text).count() > 30) return "zh"
        val words = Regex("[a-zà-ÿ]+").findAll(text.lowercase()).map { it.value }.toList()
        if (words.size < 12) return null
        val score = STOP.mapValues { (_, s) -> words.count { it in s } }
        val best = score.maxBy { it.value }
        val second = score.values.sortedDescending()[1]
        return if (best.value >= maxOf(3.0, words.size * 0.08) && best.value > second * 1.3) best.key else null
    }

    fun deviceLanguage(): String = Locale.getDefault().language.takeIf { it in NAMES } ?: "pt"
    fun target(prefs: Prefs) = prefs.translateTo.ifEmpty { deviceLanguage() }
    fun supported(code: String) = TranslateLanguage.fromLanguageTag(code) != null

    private val translators = HashMap<String, Translator>()
    fun translator(src: String, dst: String): Translator = synchronized(translators) {
        translators.getOrPut("$src>$dst") {
            Translation.getClient(TranslatorOptions.Builder()
                .setSourceLanguage(TranslateLanguage.fromLanguageTag(src)!!).setTargetLanguage(TranslateLanguage.fromLanguageTag(dst)!!).build())
        }
    }

    /** Pacotes que faltam baixar para src → dst. */
    suspend fun missing(src: String, dst: String): List<String> = withContext(Dispatchers.IO) {
        val have = Tasks.await(RemoteModelManager.getInstance().getDownloadedModels(TranslateRemoteModel::class.java)).map { it.language }
        listOf(src, dst).filter { it != "en" && TranslateLanguage.fromLanguageTag(it) !in have }
    }

    suspend fun download(src: String, dst: String) = withContext(Dispatchers.IO) {
        Tasks.await(translator(src, dst).downloadModelIfNeeded(DownloadConditions.Builder().build()))
    }

    suspend fun translate(src: String, dst: String, text: String): String = withContext(Dispatchers.IO) {
        if (text.isBlank() || Regex("^[\\d\\s.,;:()\\[\\]%±×=<>+\\-–/·*]+$").matches(text)) return@withContext text
        Tasks.await(translator(src, dst).translate(text))
    }

}

/** Faixa no topo: oferece traduzir; depois mostra o andamento e alterna Original / Tradução no próprio documento. */
@Composable
fun TranslateBanner(vm: AppVm, d: ViewerDoc, target: String, onTranslate: () -> Unit, onReading: () -> Unit) {
    val st = vm.tr
    val mine = st != null && (st.original === d || st.translated === d)
    if (!mine) {
        val src = d.language ?: return
        if (src == target || d.translateHidden || !Traducao.supported(src) || d.readOnly) return
    }
    Surface(color = Color(0xFFF1ECFE), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(start = 12.dp, end = 2.dp, top = 2.dp, bottom = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Translate, null, tint = Color(0xFF7C3AED))
            if (!mine) {
                Text("Documento em ${Traducao.NAMES[d.language] ?: d.language}", color = Color(0xFF222222), style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(start = 8.dp).weight(1f))
                TextButton(onTranslate) { Text("Traduzir") }
                IconButton({ d.translateHidden = true }) { Icon(Icons.Filled.Close, "Fechar", tint = Color(0xFF555555)) }
            } else {
                st!!
                Text(when {
                    st.error != null -> "Erro: ${st.error}"
                    st.running -> "Traduzindo… ${st.pages.size} de ${st.total}"
                    else -> "Traduzido"
                }, color = Color(0xFF222222), style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(start = 6.dp).weight(1f), maxLines = 1)
                val showing = vm.doc === st.translated && st.translated != null
                SegChip("Original", !showing) { vm.showTranslated(false) }
                SegChip("Tradução", showing, enabled = st.translated != null) { vm.showTranslated(true) }
                TextButton(onReading) { Text("Leitura") }
            }
        }
    }
}

@Composable
private fun SegChip(label: String, on: Boolean, enabled: Boolean = true, onClick: () -> Unit) {
    Surface(onClick = onClick, enabled = enabled, shape = RoundedCornerShape(50),
        color = if (on) Color(0xFF7C3AED) else Color.Transparent, border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFF7C3AED)),
        modifier = Modifier.padding(horizontal = 2.dp)) {
        Text(label, color = if (on) Color.White else if (enabled) Color(0xFF5B2BB5) else Color(0xFF9A93B0),
            style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp))
    }
}

/** Pede para baixar o pacote de idioma (uma vez) e então chama onReady. */
@Composable
fun ModelGate(src: String, dst: String, onCancel: () -> Unit, onReady: () -> Unit) {
    val scope = rememberCoroutineScope()
    var missing by remember { mutableStateOf<List<String>?>(null) }
    var downloading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(src, dst) {
        val m = runCatching { Traducao.missing(src, dst) }.getOrElse { error = it.message; return@LaunchedEffect }
        if (m.isEmpty()) onReady() else missing = m
    }
    val m = missing ?: return
    AlertDialog(onDismissRequest = { if (!downloading) onCancel() },
        title = { Text(if (downloading) "Baixando o pacote de idioma…" else "Baixar pacote de idioma?") },
        text = {
            Column {
                Text("Para traduzir sem internet, o app baixa uma vez o pacote de " + m.joinToString(" e ") { Traducao.NAMES[it] ?: it } +
                    " (cerca de ${30 * m.size} MB). Melhor no Wi-Fi.")
                if (downloading) LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 12.dp))
                error?.let { Text("Não foi possível baixar: $it", color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = { if (!downloading) TextButton({
            downloading = true; error = null
            scope.launch {
                runCatching { Traducao.download(src, dst) }.onSuccess { downloading = false; onReady() }.onFailure { error = it.message; downloading = false }
            }
        }) { Text("Baixar") } },
        dismissButton = { if (!downloading) TextButton(onCancel) { Text("Agora não") } })
}

/** Leitura traduzida: só a tradução, o original ou os dois intercalados (bilíngue). Mostra as páginas conforme ficam prontas.
 *  Referências, números e citações ficam como no original; cabeçalhos e números de página não aparecem. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TranslatedReading(vm: AppVm, st: TrState, onClose: () -> Unit) {
    val sp = remember { vm.getApplication<android.app.Application>().getSharedPreferences("prefs", 0) }
    var mode by remember { mutableStateOf(sp.getInt("leitura_traducao", 0)) }
    val state = rememberLazyListState(initialFirstVisibleItemIndex = st.original.page.coerceAtMost(maxOf(0, st.total - 1)))
    val bg = Color(0xFFFBF8F1); val fg = Color(0xFF1E1C18)
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Scaffold(containerColor = bg, topBar = {
            TopAppBar(title = { Text("Leitura traduzida") }, navigationIcon = { IconButton(onClose) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Voltar") } })
        }) { pad ->
            Column(Modifier.fillMaxSize().background(bg).padding(pad)) {
                Row(Modifier.padding(horizontal = 14.dp, vertical = 4.dp)) {
                    listOf("Tradução", "Original", "Intercalado").forEachIndexed { i, l -> SegChip(l, mode == i) { mode = i; sp.edit().putInt("leitura_traducao", i).apply() } }
                }
                if (st.running) { LinearProgressIndicator(Modifier.fillMaxWidth()); Text("Traduzindo… ${st.pages.size} de ${st.total} páginas", Modifier.padding(horizontal = 20.dp), style = MaterialTheme.typography.bodySmall) }
                Text("Tradução automática gratuita, feita no próprio aparelho. Citações, referências e números ficam como no original.",
                    Modifier.padding(horizontal = 20.dp, vertical = 6.dp), style = MaterialTheme.typography.bodySmall, color = fg.copy(alpha = 0.6f))
                LazyColumn(state = state, contentPadding = PaddingValues(horizontal = 20.dp, vertical = 8.dp)) {
                    items(st.total) { i ->
                        val items = st.pages[i]
                        Column(Modifier.fillMaxWidth().padding(bottom = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text("Página ${i + 1}", color = fg.copy(alpha = 0.55f), style = MaterialTheme.typography.labelMedium)
                            if (items == null) Text(if (st.running) "Traduzindo…" else "—", color = fg.copy(alpha = 0.6f))
                            else SelectionContainer { Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                for ((b, t) in items) {
                                    if (b.keep && (b.why == "cabeçalho/rodapé" || b.why == "número da página")) continue
                                    val o = b.shown
                                    val big = b.bold || b.size >= 13f
                                    val w = if (big) FontWeight.SemiBold else FontWeight.Normal
                                    when {
                                        b.keep -> Text(o, color = fg.copy(alpha = 0.55f), fontSize = 14.sp, lineHeight = 20.sp)
                                        mode == 1 -> Text(o, color = fg, fontSize = 17.sp, lineHeight = 25.sp, fontWeight = w)
                                        mode == 0 -> Text(t ?: o, color = fg, fontSize = 17.sp, lineHeight = 25.sp, fontWeight = w)
                                        else -> Column {
                                            Text(t ?: o, color = fg, fontSize = 17.sp, lineHeight = 25.sp, fontWeight = w)
                                            Text(o, color = fg.copy(alpha = 0.55f), fontSize = 14.sp, lineHeight = 20.sp)
                                        }
                                    }
                                }
                            } }
                            HorizontalDivider(color = fg.copy(alpha = 0.12f))
                        }
                    }
                }
            }
        }
    }
}

/** Tradução de um trecho selecionado (balão). */
@Composable
fun SnippetTranslation(text: String, src: String, dst: String, onDismiss: () -> Unit) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    var ready by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<String?>(null) }
    if (!ready) ModelGate(src, dst, onCancel = onDismiss) { ready = true }
    LaunchedEffect(ready) {
        if (ready) result = runCatching { Citacoes.translate(text.replace(Regex("\\s+"), " ")) { Traducao.translate(src, dst, it) } }
            .getOrElse { "Não foi possível traduzir: ${it.message}" }
    }
    if (ready) AlertDialog(onDismissRequest = onDismiss,
        title = { Text("Tradução (${Traducao.NAMES[src] ?: src} → ${Traducao.NAMES[dst] ?: dst})") },
        text = { SelectionContainer { Text(result ?: "Traduzindo…") } },
        confirmButton = { TextButton({ result?.let { copyText(ctx, "Tradução", it) }; onDismiss() }) { Text("Copiar") } },
        dismissButton = { TextButton(onDismiss) { Text("Fechar") } })
}
