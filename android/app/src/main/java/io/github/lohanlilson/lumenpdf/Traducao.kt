package io.github.lohanlilson.lumenpdf

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

    /** Traduz a pesquisa para o inglês só se o pacote já estiver no aparelho (não baixa nada sem perguntar). */
    suspend fun toEnglishIfReady(q: String): String? = runCatching {
        val src = detect(("$q ").repeat(12)) ?: "pt"
        if (src == "en" || missing(src, "en").isNotEmpty()) null else translate(src, "en", q)
    }.getOrNull()
}

/** Faixa no topo: documento em outro idioma, com botão para traduzir. */
@Composable
fun TranslateBanner(d: ViewerDoc, target: String, onTranslate: () -> Unit) {
    val src = d.language ?: return
    if (src == target || d.translateHidden || !Traducao.supported(src)) return
    Surface(color = Color(0xFFF1ECFE), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(start = 14.dp, end = 4.dp, top = 2.dp, bottom = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Translate, null, tint = Color(0xFF7C3AED))
            Text("Documento em ${Traducao.NAMES[src] ?: src}", color = Color(0xFF222222), style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(start = 8.dp).weight(1f))
            TextButton(onTranslate) { Text("Traduzir") }
            IconButton({ d.translateHidden = true }) { Icon(Icons.Filled.Close, "Fechar", tint = Color(0xFF555555)) }
        }
    }
}

/** Leitura traduzida: o texto de cada página traduzido (sem internet), com o original a um toque. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TranslatedReading(vm: AppVm, d: ViewerDoc, src: String, dst: String, onClose: () -> Unit) {
    val scope = rememberCoroutineScope()
    var ready by remember { mutableStateOf(false) }
    var ask by remember { mutableStateOf<List<String>?>(null) }
    var downloading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var original by remember { mutableStateOf(false) }
    val cache = remember { mutableStateMapOf<Int, List<Pair<String, String>>>() }
    LaunchedEffect(Unit) {
        val m = runCatching { Traducao.missing(src, dst) }.getOrElse { error = it.message; return@LaunchedEffect }
        if (m.isEmpty()) ready = true else ask = m
    }
    val state = rememberLazyListState(initialFirstVisibleItemIndex = d.page)
    val bg = Color(0xFFFBF8F1); val fg = Color(0xFF1E1C18)
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Scaffold(containerColor = bg, topBar = {
            TopAppBar(title = { Text(if (original) "Original" else "Tradução (${Traducao.NAMES[dst]})") },
                navigationIcon = { IconButton(onClose) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Voltar") } },
                actions = { TextButton({ original = !original }) { Text(if (original) "Ver tradução" else "Ver original") } })
        }) { pad ->
            Column(Modifier.fillMaxSize().background(bg).padding(pad)) {
                if (downloading) { LinearProgressIndicator(Modifier.fillMaxWidth()); Text("Baixando o pacote de idioma (uma vez só)…", Modifier.padding(16.dp)) }
                error?.let { Text("Não foi possível traduzir: $it", Modifier.padding(16.dp), color = MaterialTheme.colorScheme.error) }
                if (ready) {
                    Text("Tradução automática gratuita, feita no próprio aparelho: boa para entender; confira trechos importantes no original.",
                        Modifier.padding(horizontal = 20.dp, vertical = 6.dp), style = MaterialTheme.typography.bodySmall, color = fg.copy(alpha = 0.6f))
                    LazyColumn(state = state, contentPadding = PaddingValues(horizontal = 20.dp, vertical = 8.dp)) {
                        items(d.pageCount) { i ->
                            val paras = cache[i]
                            LaunchedEffect(i) {
                                if (cache[i] == null) {
                                    val src0 = reflow(vm.engine.pageText(d.pdf, i))
                                    cache[i] = src0.map { it to runCatching { Traducao.translate(src, dst, it) }.getOrDefault(it) }
                                }
                            }
                            Column(Modifier.fillMaxWidth().padding(bottom = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                Text("Página ${i + 1}", color = fg.copy(alpha = 0.55f), style = MaterialTheme.typography.labelMedium)
                                when {
                                    paras == null -> Text("Traduzindo…", color = fg.copy(alpha = 0.6f))
                                    paras.isEmpty() -> Text("(página sem texto: é uma imagem. Use “Reconhecer texto (OCR)” antes.)", color = fg.copy(alpha = 0.6f))
                                    else -> SelectionContainer { Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                        paras.forEach { (o, t) -> Text(if (original) o else t, color = fg, fontSize = 17.sp, lineHeight = 25.sp) }
                                    } }
                                }
                                HorizontalDivider(color = fg.copy(alpha = 0.12f))
                            }
                        }
                    }
                }
            }
        }
        ask?.let { m ->
            AlertDialog(onDismissRequest = onClose,
                title = { Text("Baixar pacote de idioma?") },
                text = { Text("Para traduzir sem internet, o app baixa uma vez o pacote de " + m.joinToString(" e ") { Traducao.NAMES[it] ?: it } +
                    " (cerca de ${30 * m.size} MB). Melhor no Wi-Fi.") },
                confirmButton = { TextButton({
                    ask = null; downloading = true
                    scope.launch {
                        runCatching { Traducao.download(src, dst) }.onSuccess { ready = true }.onFailure { error = it.message }
                        downloading = false
                    }
                }) { Text("Baixar") } },
                dismissButton = { TextButton(onClose) { Text("Agora não") } })
        }
    }
}
