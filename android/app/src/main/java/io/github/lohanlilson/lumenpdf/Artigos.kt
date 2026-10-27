package io.github.lohanlilson.lumenpdf

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.time.LocalDate

/** Artigo científico de acesso aberto (OpenAlex; Europe PMC como reserva). Mesmas regras de lumenpdf/artigos.py. */
data class Article(
    val title: String, val authors: List<String> = emptyList(), val year: Int? = null, val venue: String = "",
    val citations: Int? = null, val language: String = "", val doi: String = "", val pdfUrls: List<String> = emptyList(),
    val pageUrl: String = "", val volume: String = "", val issue: String = "", val pages: String = "", val source: String = "OpenAlex",
) {
    val authorsShort get() = if (authors.isEmpty()) "" else authors.take(3).joinToString(", ") + if (authors.size > 3) " et al." else ""

    fun abnt(today: LocalDate = LocalDate.now()): String {
        fun autor(n: String): String {
            val p = n.replace(",", " ").split(Regex("\\s+")).filter { it.isNotEmpty() }
            if (p.size < 2) return n.uppercase()
            if (Regex("[A-Z]{1,3}").matches(p.last())) return "${p.dropLast(1).joinToString(" ").uppercase()}, ${p.last().toList().joinToString(". ")}."
            return "${p.last().uppercase()}, ${p.dropLast(1).joinToString(" ")}"
        }
        val aut = if (authors.size > 3) autor(authors[0]) + " et al." else authors.joinToString("; ") { autor(it) }
        val sb = StringBuilder()
        if (aut.isNotEmpty()) sb.append(aut.trimEnd('.')).append(". ")
        sb.append(title.trimEnd('.')).append(". ")
        if (venue.isNotEmpty()) {
            sb.append(venue)
            if (volume.isNotEmpty()) sb.append(", v. $volume")
            if (issue.isNotEmpty()) sb.append(", n. $issue")
            if (pages.isNotEmpty()) sb.append(", p. $pages")
            sb.append(", ")
        }
        sb.append(year?.toString() ?: "s.d.").append(".")
        if (doi.isNotEmpty()) sb.append(" DOI: ${doi.removePrefix("https://doi.org/")}.")
        val link = pageUrl.ifEmpty { pdfUrls.firstOrNull() ?: "" }
        if (link.isNotEmpty()) {
            val meses = listOf("jan.", "fev.", "mar.", "abr.", "maio", "jun.", "jul.", "ago.", "set.", "out.", "nov.", "dez.")
            sb.append(" Disponível em: $link. Acesso em: ${today.dayOfMonth} ${meses[today.monthValue - 1]} ${today.year}.")
        }
        return sb.toString()
    }
}

object Artigos {
    private const val UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36 LumenPDF"
    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")

    private fun getJson(url: String): JSONObject {
        val c = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 15000; readTimeout = 25000; setRequestProperty("User-Agent", UA); setRequestProperty("Accept", "application/json")
        }
        try {
            if (c.responseCode !in 200..299) throw java.io.IOException("HTTP ${c.responseCode}")
            return JSONObject(c.inputStream.bufferedReader().readText())
        } finally { c.disconnect() }
    }

    fun parseOpenAlex(data: JSONObject): Pair<List<Article>, Int> {
        val out = ArrayList<Article>()
        val res = data.optJSONArray("results") ?: return out to 0
        for (i in 0 until res.length()) {
            val w = res.getJSONObject(i)
            val best = w.optJSONObject("best_oa_location") ?: JSONObject()
            val pdfs = LinkedHashSet<String>()
            best.optString("pdf_url").takeIf { it.isNotEmpty() && it != "null" }?.let { pdfs += it }
            w.optJSONArray("locations")?.let { l -> for (k in 0 until l.length()) l.optJSONObject(k)?.let { loc ->
                if (loc.optBoolean("is_oa", true)) loc.optString("pdf_url").takeIf { it.isNotEmpty() && it != "null" }?.let { pdfs += it } } }
            if (pdfs.isEmpty()) continue
            val venue = w.optJSONObject("primary_location")?.optJSONObject("source")?.optString("display_name")?.takeIf { it.isNotEmpty() && it != "null" }
                ?: best.optJSONObject("source")?.optString("display_name") ?: ""
            val b = w.optJSONObject("biblio") ?: JSONObject()
            fun s(o: JSONObject, k: String) = o.optString(k).takeIf { it.isNotEmpty() && it != "null" } ?: ""
            val pages = listOf(s(b, "first_page"), s(b, "last_page")).filter { it.isNotEmpty() }.joinToString("-")
            val authors = w.optJSONArray("authorships")?.let { a -> (0 until a.length()).mapNotNull { a.optJSONObject(it)?.optJSONObject("author")?.optString("display_name") } } ?: emptyList()
            out += Article(
                title = s(w, "display_name").replace(Regex("<[^>]+>"), "").ifEmpty { "(sem título)" }, authors = authors,
                year = w.optInt("publication_year").takeIf { it > 0 }, venue = venue,
                citations = if (w.has("cited_by_count")) w.optInt("cited_by_count") else null, language = s(w, "language"),
                doi = s(w, "doi"), pdfUrls = pdfs.toList(), pageUrl = s(best, "landing_page_url").ifEmpty { s(w, "doi") },
                volume = s(b, "volume"), issue = s(b, "issue"), pages = pages)
        }
        return out to (data.optJSONObject("meta")?.optInt("count") ?: out.size)
    }

    fun parseEuropePmc(data: JSONObject): Pair<List<Article>, Int> {
        val out = ArrayList<Article>()
        val res = data.optJSONObject("resultList")?.optJSONArray("result") ?: return out to 0
        for (i in 0 until res.length()) {
            val r = res.getJSONObject(i)
            val pdfs = LinkedHashSet<String>()
            r.optJSONObject("fullTextUrlList")?.optJSONArray("fullTextUrl")?.let { l -> for (k in 0 until l.length()) l.optJSONObject(k)?.let { u ->
                if (u.optString("documentStyle") == "pdf" && u.optString("availabilityCode") in setOf("OA", "F")) pdfs += u.optString("url") } }
            r.optString("pmcid").takeIf { it.isNotEmpty() }?.let { pdfs += "https://europepmc.org/articles/$it?pdf=render" }
            if (pdfs.isEmpty()) continue
            val authors = r.optJSONObject("authorList")?.optJSONArray("author")?.let { a -> (0 until a.length()).map { a.getJSONObject(it).optString("fullName") } } ?: emptyList()
            val ji = r.optJSONObject("journalInfo") ?: JSONObject()
            out += Article(
                title = r.optString("title").trimEnd('.'), authors = authors, year = r.optString("pubYear").toIntOrNull(),
                venue = ji.optJSONObject("journal")?.optString("title") ?: "", citations = if (r.has("citedByCount")) r.optInt("citedByCount") else null,
                language = r.optString("language").take(2), doi = r.optString("doi").takeIf { it.isNotEmpty() }?.let { "https://doi.org/$it" } ?: "",
                pdfUrls = pdfs.toList(), pageUrl = "https://europepmc.org/article/${r.optString("source", "MED")}/${r.optString("id")}",
                volume = ji.optString("volume"), issue = ji.optString("issue"), pages = r.optString("pageInfo"), source = "Europe PMC")
        }
        return out to data.optInt("hitCount", out.size)
    }

    /** (artigos, total). OpenAlex; se recusar (limite diário) ou falhar, Europe PMC. */
    fun search(query: String, yearFrom: Int? = null, sort: String = "relevance", page: Int = 1): Pair<List<Article>, Int> {
        val q = query.trim()
        if (q.isEmpty()) return emptyList<Article>() to 0
        val first = runCatching {
            val flt = mutableListOf("is_oa:true", "has_pdf_url:true", "type:article|review|preprint")
            if (yearFrom != null) flt += "publication_year:>${yearFrom - 1}"
            var url = "https://api.openalex.org/works?search=${enc(q)}&filter=${enc(flt.joinToString(","))}&per_page=25&page=$page" +
                "&select=${enc("id,display_name,publication_year,authorships,primary_location,best_oa_location,locations,cited_by_count,language,doi,biblio")}"
            if (sort == "citations") url += "&sort=cited_by_count:desc" else if (sort == "recent") url += "&sort=publication_date:desc"
            return parseOpenAlex(getJson(url))
        }.exceptionOrNull()
        return runCatching {
            var qq = "($q) AND OPEN_ACCESS:Y AND HAS_PDF:Y"
            if (yearFrom != null) qq += " AND PUB_YEAR:[$yearFrom TO 3000]"
            var url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=${enc(qq)}&format=json&resultType=core&pageSize=25&page=$page"
            if (sort == "citations") url += "&sort=${enc("CITED desc")}" else if (sort == "recent") url += "&sort=${enc("P_PDATE_D desc")}"
            parseEuropePmc(getJson(url))
        }.getOrElse { throw java.io.IOException("Não foi possível pesquisar agora (${first?.message}; ${it.message}). Verifique a internet.") }
    }

    fun safeName(title: String) = title.replace(Regex("[\\\\/:*?\"<>|\\r\\n\\t]+"), " ").replace(Regex("\\s+"), " ").trim()
        .take(90).trimEnd(' ', '.').ifEmpty { "Artigo" } + ".pdf"

    /** Baixa o primeiro link que entrega mesmo um PDF; null se a revista não liberar o download direto. */
    fun download(a: Article, dir: File): File? {
        dir.mkdirs()
        val out = File(dir, safeName(a.title))
        for (u in a.pdfUrls) {
            runCatching {
                var url = URL(u)
                var c: HttpURLConnection
                var hops = 0
                while (true) {   // segue redirecionamentos (inclusive http → https)
                    c = (url.openConnection() as HttpURLConnection).apply {
                        connectTimeout = 15000; readTimeout = 40000; instanceFollowRedirects = false
                        setRequestProperty("User-Agent", UA); setRequestProperty("Accept", "application/pdf,*/*")
                    }
                    if (c.responseCode in 300..399 && hops++ < 6) { url = URL(url, c.getHeaderField("Location")); c.disconnect(); continue }
                    break
                }
                try {
                    if (c.responseCode !in 200..299) return@runCatching
                    c.inputStream.use { inp ->
                        val head = ByteArray(1024); var n = 0
                        while (n < head.size) { val r = inp.read(head, n, head.size - n); if (r < 0) break; n += r }
                        if (!String(head, 0, n, Charsets.ISO_8859_1).contains("%PDF")) return@runCatching
                        out.outputStream().use { o -> o.write(head, 0, n); inp.copyTo(o) }
                    }
                } finally { c.disconnect() }
                if (out.length() > 1024) return out
            }
        }
        return null
    }
}

// ------------------------------------------------------------------ tela de pesquisa
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ArticlesScreen(vm: AppVm, onClose: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var q by remember { mutableStateOf("") }
    var english by remember { mutableStateOf(vm.prefs.articlesEnglish) }
    var sort by remember { mutableStateOf("relevance") }
    var sortMenu by remember { mutableStateOf(false) }
    val results = remember { mutableStateListOf<Article>() }
    var total by remember { mutableStateOf(0) }
    var page by remember { mutableStateOf(1) }
    var busy by remember { mutableStateOf<String?>(null) }
    var msg by remember { mutableStateOf<String?>(null) }

    fun run(more: Boolean) {
        val text = q.trim()
        if (text.isEmpty()) return
        vm.prefs.articlesEnglish = english
        if (!more) { results.clear(); page = 1; total = 0 } else page++
        busy = "Pesquisando…"; msg = null
        scope.launch {
            try {
                val queries = mutableListOf(text)
                if (english) Traducao.toEnglishIfReady(text)?.let { if (!it.equals(text, true)) queries += it }
                val seen = results.map { it.doi.ifEmpty { it.title } }.toMutableSet()
                var t = 0
                for (qq in queries) {
                    val (arts, n) = withContext(Dispatchers.IO) { Artigos.search(qq, null, sort, page) }
                    t += n
                    arts.forEach { a -> if (seen.add(a.doi.ifEmpty { a.title })) results += a }
                }
                total = maxOf(total, t)
                if (results.isEmpty()) msg = "Nada encontrado com PDF gratuito. Tente outras palavras" + if (!english) " ou marque “também em inglês”." else "."
            } catch (e: Exception) { msg = e.message } finally { busy = null }
        }
    }

    fun open(a: Article) {
        busy = "Baixando o artigo…"
        scope.launch {
            val f = withContext(Dispatchers.IO) { Artigos.download(a, File(ctx.filesDir, "recebidos")) }
            busy = null
            if (f != null) { onClose(); vm.open(Uri.fromFile(f), fromPicker = false) }
            else {
                msg = "A revista não liberou o PDF para download direto; abrindo no navegador."
                runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(a.pdfUrls.first()))) }
            }
        }
    }

    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Scaffold(topBar = {
            TopAppBar(title = { Text("Artigos científicos") }, navigationIcon = { IconButton(onClose) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Voltar") } })
        }) { pad ->
            Column(Modifier.fillMaxSize().padding(pad)) {
                OutlinedTextField(q, { q = it }, Modifier.fillMaxWidth().padding(horizontal = 14.dp),
                    placeholder = { Text("Ex.: maus-tratos animais medicina veterinária") }, singleLine = true,
                    trailingIcon = { IconButton({ run(false) }) { Icon(Icons.Filled.Search, "Pesquisar") } },
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search), keyboardActions = KeyboardActions(onSearch = { run(false) }))
                Row(Modifier.fillMaxWidth().padding(horizontal = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(english, { english = it }); Text("Também em inglês", Modifier.clickable { english = !english }.weight(1f))
                    Column {
                        TextButton({ sortMenu = true }) { Text(mapOf("relevance" to "Relevantes", "citations" to "Mais citados", "recent" to "Recentes")[sort]!!) }
                        DropdownMenu(sortMenu, { sortMenu = false }) {
                            listOf("relevance" to "Mais relevantes", "citations" to "Mais citados", "recent" to "Mais recentes").forEach { (k, l) ->
                                DropdownMenuItem(text = { Text(l) }, onClick = { sortMenu = false; sort = k; if (results.isNotEmpty()) run(false) })
                            }
                        }
                    }
                }
                if (busy != null) { LinearProgressIndicator(Modifier.fillMaxWidth()); Text(busy!!, Modifier.padding(horizontal = 16.dp), style = MaterialTheme.typography.bodySmall) }
                msg?.let { Text(it, Modifier.padding(horizontal = 16.dp, vertical = 4.dp), color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                if (results.isNotEmpty()) Text("${results.size} de $total com PDF gratuito · fonte: ${results.map { it.source }.distinct().joinToString()}",
                    Modifier.padding(horizontal = 16.dp, vertical = 4.dp), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (results.isEmpty() && busy == null && msg == null) Text("Artigos de acesso aberto (PDF gratuito e legal) de revistas e repositórios do mundo todo. " +
                    "Os em outro idioma podem ser traduzidos ao abrir, sem internet.", Modifier.padding(16.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
                LazyColumn(contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(results) { a -> ArticleCard(a, onOpen = { open(a) }, onRef = { copyText(ctx, "Referência", a.abnt()); vm.toast = "Referência ABNT copiada" },
                        onWeb = { runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(a.pageUrl.ifEmpty { a.pdfUrls.first() }))) } }) }
                    if (results.isNotEmpty() && results.size < total) item { TextButton({ run(true) }, Modifier.fillMaxWidth()) { Text("Carregar mais") } }
                }
            }
        }
    }
}

@Composable
private fun ArticleCard(a: Article, onOpen: () -> Unit, onRef: () -> Unit, onWeb: () -> Unit) {
    Surface(shape = RoundedCornerShape(10.dp), border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.clickable(onClick = onOpen).padding(12.dp)) {
            Text(a.title, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyLarge)
            val meta = listOf(a.authorsShort, a.venue, a.year?.toString() ?: "", a.citations?.let { "$it citações" } ?: "",
                "idioma: " + (Traducao.NAMES[a.language] ?: a.language.ifEmpty { "?" })).filter { it.isNotEmpty() }.joinToString(" · ")
            Text(meta, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 4.dp))
            Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onOpen) { Text("Abrir PDF") }
                TextButton(onRef) { Text("ABNT") }
                TextButton(onWeb) { Text("Página", color = Color(0xFF1473E6)) }
            }
        }
    }
}
