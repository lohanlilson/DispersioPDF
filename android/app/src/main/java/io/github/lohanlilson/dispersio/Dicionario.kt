package io.github.lohanlilson.dispersio

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/** Dicionário (igual ao do computador): português pelo Wikcionário, seguindo a forma básica (“casas” → “casa”);
 *  outras línguas: tradução (offline) + significado do Wiktionary em inglês. O que já foi consultado funciona offline. */
object Dicionario {
    data class Entry(val word: String, val defs: List<Pair<String, String>>, val base: Pair<String, List<Pair<String, String>>>?,
                     val translation: String?, val source: String)

    fun clean(w: String) = w.trim().trim('.', ',', ';', ':', '!', '?', '"', '\'', '“', '”', '‘', '’', '(', ')', '[', ']', '«', '»', '…', '—', '–', '-', '*').trim()

    private fun get(url: String): String? {
        repeat(3) { attempt ->
            val c = (URL(url).openConnection() as HttpURLConnection).apply {
                connectTimeout = 8000; readTimeout = 8000
                setRequestProperty("User-Agent", "DispersioPDF-Android/1.0 (https://github.com/lohanlilson/DispersioPDF)")
            }
            try {
                when (c.responseCode) {
                    200 -> return c.inputStream.bufferedReader().readText()
                    429, 503 -> Thread.sleep(1500L * (attempt + 1))
                    else -> return null
                }
            } catch (_: Exception) {
                if (attempt >= 1) return null
            } finally { c.disconnect() }
        }
        return null
    }

    private fun wikitext(page: String): String? = get("https://pt.wiktionary.org/w/api.php?action=parse&prop=wikitext&format=json&formatversion=2&redirects=1&page=" + Uri.encode(page))
        ?.let { runCatching { JSONObject(it).getJSONObject("parse").getString("wikitext") }.getOrNull() }

    private fun strip(t0: String): String {
        var t = Regex("\\{\\{escopo2?\\|[^|}]*\\|([^}]*)\\}\\}").replace(t0) { "(" + it.groupValues[1].replace("|", ", ") + ") " }
        repeat(3) { t = Regex("\\{\\{[^{}]*\\}\\}").replace(t, "") }
        t = Regex("\\[\\[(?:[^|\\]]*\\|)?([^\\]]*)\\]\\]").replace(t, "$1")
        t = Regex("'''?|<[^>]+>").replace(t, "")
        return t.replace(Regex("\\s+"), " ").trim(' ', ';', ':')
    }

    private val POS = Regex("^==+\\s*([^=]+?)\\s*==+\\s*$")
    private val LEMMA = Regex("(?:plural|feminino|masculino|forma|flexão|conjugação|pretérito|presente|futuro|particípio|gerúndio|infinitivo|imperativo|singular|diminutivo|aumentativo)[^#\\n]*?\\[\\[([^\\]|#]+)", RegexOption.IGNORE_CASE)

    /** (definições da seção de português, forma básica se for flexão) */
    fun ptDefs(wikitext: String): Pair<List<Pair<String, String>>, String?> {
        val sec = Regex("^=\\{\\{-pt-\\}\\}=\\s*$(.*?)(?=^=\\{\\{-[a-z]+-\\}\\}=|\\z)", setOf(RegexOption.MULTILINE, RegexOption.DOT_MATCHES_ALL))
            .find(wikitext)?.groupValues?.get(1) ?: return emptyList<Pair<String, String>>() to null
        var pos = ""; var lemma: String? = null; var flex = 0
        val out = ArrayList<Pair<String, String>>()
        for (line in sec.lines()) {
            POS.matchEntire(line)?.let { if (!it.groupValues[1].startsWith("{{")) { pos = it.groupValues[1] }; return@let }
            if (line.startsWith("#") && !line.startsWith("#*") && !line.startsWith("#:") && !line.startsWith("##")) {
                val raw = line.trimStart('#').trim()
                LEMMA.find(raw)?.let { flex++; if (lemma == null) lemma = it.groupValues[1].trim() }
                val d = strip(raw)
                if (d.isNotEmpty()) out += pos to d
            }
        }
        return out to (if (out.isNotEmpty() && flex * 2 >= out.size) lemma else null)
    }

    private fun english(word: String): List<Pair<String, String>> {
        val j = (get("https://en.wiktionary.org/api/rest_v1/page/definition/" + Uri.encode(word))
            ?: get("https://en.wiktionary.org/api/rest_v1/page/definition/" + Uri.encode(word.lowercase())))?.let { runCatching { JSONObject(it) }.getOrNull() } ?: return emptyList()
        val out = ArrayList<Pair<String, String>>()
        for (lang in j.keys()) {
            val arr = j.optJSONArray(lang) ?: continue
            for (i in 0 until arr.length()) {
                val e = arr.getJSONObject(i)
                val defs = e.optJSONArray("definitions") ?: continue
                for (k in 0 until minOf(3, defs.length())) {
                    val d = android.text.Html.fromHtml(defs.getJSONObject(k).optString("definition"), android.text.Html.FROM_HTML_MODE_LEGACY).toString().trim()
                    if (d.isNotEmpty()) out += e.optString("partOfSpeech") to d
                }
            }
            if (out.isNotEmpty()) break
        }
        return out.take(5)
    }

    private fun cacheFile(ctx: Context) = File(ctx.filesDir, "dicionario.json")

    suspend fun lookup(ctx: Context, word: String, lang: String): Entry? = withContext(Dispatchers.IO) {
        val w = clean(word)
        if (w.isEmpty() || w.length > 60) return@withContext null
        val key = "$lang:${w.lowercase()}"
        val cache = runCatching { JSONObject(cacheFile(ctx).readText()) }.getOrDefault(JSONObject())
        cache.optJSONObject(key)?.let { return@withContext fromJson(it) }
        var res: Entry? = null
        if (lang == "pt") {
            for (page in listOf(w, w.lowercase()).distinct()) {
                val wt = wikitext(page) ?: continue
                val (defs, lemma) = ptDefs(wt)
                if (defs.isEmpty()) continue
                val base = lemma?.takeIf { !it.equals(page, true) }?.let { l -> wikitext(l)?.let { ptDefs(it).first }?.takeIf { it.isNotEmpty() }?.let { l to it } }
                res = Entry(page, defs.take(6), base, null, "Wikcionário")
                break
            }
        }
        if (res == null) {
            val tr = if (lang != "pt" && Traducao.supported(lang)) runCatching {
                if (Traducao.missing(lang, "pt").isEmpty()) Traducao.translate(lang, "pt", w) else null
            }.getOrNull() else null
            val defs = english(w)
            if (defs.isNotEmpty() || tr != null) res = Entry(w, defs, null, tr, if (defs.isNotEmpty()) "Wiktionary (inglês)" else "tradutor offline")
        }
        res?.let { e -> runCatching { cache.put(key, toJson(e)); cacheFile(ctx).writeText(cache.toString()) } }
        res
    }

    private fun toJson(e: Entry) = JSONObject().apply {
        put("w", e.word); put("t", e.translation ?: ""); put("s", e.source)
        put("d", org.json.JSONArray(e.defs.map { org.json.JSONArray(listOf(it.first, it.second)) }))
        e.base?.let { b -> put("bw", b.first); put("bd", org.json.JSONArray(b.second.map { org.json.JSONArray(listOf(it.first, it.second)) })) }
    }

    private fun fromJson(j: JSONObject): Entry {
        fun pairs(a: org.json.JSONArray?) = (0 until (a?.length() ?: 0)).map { a!!.getJSONArray(it).let { p -> p.getString(0) to p.getString(1) } }
        return Entry(j.getString("w"), pairs(j.optJSONArray("d")), j.optString("bw").takeIf { it.isNotEmpty() }?.let { it to pairs(j.optJSONArray("bd")) },
            j.optString("t").takeIf { it.isNotEmpty() }, j.optString("s"))
    }
}

@Composable
fun DictionaryDialog(word: String, lang: String, onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    val res by produceState<Pair<Boolean, Dicionario.Entry?>>(false to null, word) { value = true to Dicionario.lookup(ctx, word, lang) }
    val (done, e) = res
    AlertDialog(onDismissRequest = onDismiss,
        title = { Text(Dicionario.clean(word)) },
        text = {
            Column(Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState())) {
                val x = e
                when {
                    x == null && !done -> LinearProgressIndicator(Modifier.padding(vertical = 12.dp))
                    x == null -> Text("Não encontrei esta palavra. Sem internet, só aparecem as que você já consultou antes.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    else -> {
                        x.translation?.let { Text("Tradução: $it", fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(bottom = 6.dp)) }
                        var last = ""
                        x.defs.forEach { (pos, d) ->
                            if (pos.isNotEmpty() && pos != last) { Text(pos, fontStyle = FontStyle.Italic, color = MaterialTheme.colorScheme.onSurfaceVariant); last = pos }
                            Text("• $d", modifier = Modifier.padding(bottom = 3.dp))
                        }
                        x.base?.let { (bw, bd) ->
                            Text("$bw (forma básica)", fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp))
                            bd.take(4).forEach { (_, d) -> Text("• $d") }
                        }
                        Text("Fonte: ${x.source}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(top = 8.dp))
                    }
                }
            }
        },
        confirmButton = { TextButton(onDismiss) { Text("Fechar") } },
        dismissButton = {
            TextButton({
                val site = if (lang == "pt") "pt" else "en"
                runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://$site.wiktionary.org/wiki/" + Uri.encode(Dicionario.clean(word)))).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
            }) { Text("Ver mais") }
        })
}
