package io.github.lohanlilson.dispersio

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
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.runtime.snapshotFlow
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.material3.FilterChip
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

/** Artigo científico de acesso aberto (OpenAlex; Europe PMC como reserva). Mesmas regras de dispersio/artigos.py. */
data class Article(
    val title: String, val authors: List<String> = emptyList(), val year: Int? = null, val venue: String = "",
    val citations: Int? = null, val language: String = "", val doi: String = "", val pdfUrls: List<String> = emptyList(),
    val pageUrl: String = "", val volume: String = "", val issue: String = "", val pages: String = "", val source: String = "OpenAlex",
    val abstract: String = "", val id: String = "", val kind: String = "", val related: List<String> = emptyList(), val refs: List<String> = emptyList(),
) {
    val hasPdf get() = pdfUrls.isNotEmpty()
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
    private const val UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36 DispersioPDF"
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

    private val Y = LocalDate.now().year
    /** filtros rápidos: chave → (rótulo, filtro do OpenAlex, trecho da consulta do Europe PMC) */
    val FILTERS = linkedMapOf(
        "pdf" to Triple("Só PDF grátis", "is_oa:true,has_pdf_url:true", " AND OPEN_ACCESS:Y AND HAS_PDF:Y"),
        "recent" to Triple("Últimos 5 anos", "publication_year:>${Y - 6}", " AND PUB_YEAR:[${Y - 5} TO 3000]"),
        "review" to Triple("Revisões", "type:review", " AND PUB_TYPE:\"review\""),
        "br" to Triple("Brasil", "authorships.countries:BR", " AND AFF:\"Brazil\""),
        "pt" to Triple("Em português", "language:pt", " AND LANG:\"por\""),
        "abstract" to Triple("Com resumo", "has_abstract:true", " AND HAS_ABSTRACT:Y"),
    )
    private const val SELECT = "id,display_name,publication_year,authorships,primary_location,best_oa_location,locations,cited_by_count," +
        "language,doi,biblio,type,abstract_inverted_index,related_works,referenced_works"

    private fun shortId(u: String?) = (u ?: "").substringAfterLast('/')

    fun abstractText(inv: JSONObject?): String {
        if (inv == null) return ""
        val pos = java.util.TreeMap<Int, String>()
        for (w in inv.keys()) inv.optJSONArray(w)?.let { a -> for (k in 0 until a.length()) pos[a.getInt(k)] = w }
        return pos.values.joinToString(" ")
    }

    fun parseWork(w: JSONObject): Article {
        val best = w.optJSONObject("best_oa_location") ?: JSONObject()
        val pdfs = LinkedHashSet<String>()
        best.optString("pdf_url").takeIf { it.isNotEmpty() && it != "null" }?.let { pdfs += it }
        w.optJSONArray("locations")?.let { l -> for (k in 0 until l.length()) l.optJSONObject(k)?.let { loc ->
            if (loc.optBoolean("is_oa", true)) loc.optString("pdf_url").takeIf { it.isNotEmpty() && it != "null" }?.let { pdfs += it } } }
        val venue = w.optJSONObject("primary_location")?.optJSONObject("source")?.optString("display_name")?.takeIf { it.isNotEmpty() && it != "null" }
            ?: best.optJSONObject("source")?.optString("display_name") ?: ""
        val b = w.optJSONObject("biblio") ?: JSONObject()
        fun s(o: JSONObject, k: String) = o.optString(k).takeIf { it.isNotEmpty() && it != "null" } ?: ""
        val pages = listOf(s(b, "first_page"), s(b, "last_page")).filter { it.isNotEmpty() }.joinToString("-")
        val authors = w.optJSONArray("authorships")?.let { a -> (0 until a.length()).mapNotNull { a.optJSONObject(it)?.optJSONObject("author")?.optString("display_name") } } ?: emptyList()
        fun ids(k: String) = w.optJSONArray(k)?.let { a -> (0 until a.length()).map { shortId(a.optString(it)) } } ?: emptyList()
        return Article(
            title = s(w, "display_name").replace(Regex("<[^>]+>"), "").ifEmpty { "(sem título)" }, authors = authors,
            year = w.optInt("publication_year").takeIf { it > 0 }, venue = venue,
            citations = if (w.has("cited_by_count")) w.optInt("cited_by_count") else null, language = s(w, "language"),
            doi = s(w, "doi"), pdfUrls = pdfs.toList(),
            pageUrl = s(best, "landing_page_url").ifEmpty { w.optJSONObject("primary_location")?.let { s(it, "landing_page_url") } ?: "" }.ifEmpty { s(w, "doi") },
            volume = s(b, "volume"), issue = s(b, "issue"), pages = pages, abstract = abstractText(w.optJSONObject("abstract_inverted_index")),
            id = shortId(w.optString("id")), kind = s(w, "type"), related = ids("related_works"), refs = ids("referenced_works"))
    }

    fun parseOpenAlex(data: JSONObject, onlyPdf: Boolean = true): Pair<List<Article>, Int> {
        val res = data.optJSONArray("results") ?: return emptyList<Article>() to 0
        val out = (0 until res.length()).map { parseWork(res.getJSONObject(it)) }.filter { !onlyPdf || it.hasPdf }
        return out to (data.optJSONObject("meta")?.optInt("count") ?: out.size)
    }

    private fun flt(filters: Set<String>, extra: List<String> = emptyList()): String {
        val f = ArrayList<String>()
        if ("review" !in filters) f += "type:article|review|preprint"
        filters.mapNotNullTo(f) { FILTERS[it]?.second }
        f += extra
        return f.joinToString(",")
    }

    private fun sortParam(sort: String) = when (sort) { "citations" -> "&sort=cited_by_count:desc"; "recent" -> "&sort=publication_date:desc"; else -> "" }

    /** Trabalhos pelo id do OpenAlex (parecidos, referências), na ordem pedida. */
    fun byIds(ids: List<String>): List<Article> {
        val out = ArrayList<Article>()
        for (chunk in ids.filter { it.isNotEmpty() }.take(100).chunked(50)) {
            val (arts, _) = parseOpenAlex(getJson("https://api.openalex.org/works?filter=${enc("openalex_id:" + chunk.joinToString("|"))}&per_page=50&select=${enc(SELECT)}"), false)
            out += arts.sortedBy { chunk.indexOf(it.id).let { i -> if (i < 0) 999 else i } }
        }
        return out
    }

    /** Quem citou este trabalho. */
    fun citing(id: String, page: Int, filters: Set<String>, sort: String): Pair<List<Article>, Int> =
        parseOpenAlex(getJson("https://api.openalex.org/works?filter=${enc(flt(filters - "pdf", listOf("cites:$id")))}&per_page=25&page=$page&select=${enc(SELECT)}" + sortParam(sort)), false)

    private val DOI_RE = Regex("\\b(10\\.\\d{4,9}/[^\\s\"<>]+)", RegexOption.IGNORE_CASE)
    private val ARXIV_RE = Regex("arxiv\\.org/(?:abs|pdf)/(\\d{4}\\.\\d{4,5})(?:v\\d+)?", RegexOption.IGNORE_CASE)
    private val OAID_RE = Regex("\\b(W\\d{5,})\\b")

    /** DOI, link de revista com DOI, arXiv ou id do OpenAlex colado na pesquisa. */
    fun parseLink(text: String): String? {
        val t = text.trim()
        ARXIV_RE.find(t)?.let { return "doi:10.48550/arXiv.${it.groupValues[1]}" }
        DOI_RE.find(t)?.let { return "doi:" + it.groupValues[1].trimEnd('.', ',', ';', ')').removeSuffix(".pdf") }
        OAID_RE.find(t)?.let { if (' ' !in t || "openalex" in t) return it.groupValues[1] }
        return null
    }

    fun byKey(key: String): Article = parseWork(getJson("https://api.openalex.org/works/${key}?select=${enc(SELECT)}"))

    /** Sugestões enquanto digita: (tipo, rótulo, id). Gratuito no OpenAlex. */
    fun autocomplete(text: String): List<Triple<String, String, String>> {
        val out = ArrayList<Triple<String, String, String>>()
        for ((kind, path, n) in listOf(Triple("tema", "keywords", 6), Triple("artigo", "works", 5))) {
            runCatching { getJson("https://api.openalex.org/autocomplete/$path?q=${enc(text.trim())}") }.getOrNull()?.optJSONArray("results")?.let { r ->
                for (i in 0 until minOf(n, r.length())) r.getJSONObject(i).let { out += Triple(kind, it.optString("display_name"), shortId(it.optString("id"))) }
            }
        }
        return out
    }

    /** Pesquisa para "artigos sobre este documento": título (metadados ou a maior letra da 1ª página) ou termos frequentes. */
    fun queryFromDocument(doc: com.tom_roush.pdfbox.pdmodel.PDDocument): String {
        var title = doc.documentInformation?.title ?: ""
        if (title.split(' ').size < 3 || Regex("(?i)microsoft word|untitled|\\.docx?$|\\.pdf$").containsMatchIn(title)) {
            val blocks = DocAnalysis.rawBlocks(doc, 0).filter { it.shown.length > 12 && it.rect.top < 500 }
            title = blocks.maxByOrNull { it.size }?.shown ?: ""
        }
        title = title.split(Regex("\\s+")).take(14).joinToString(" ")
        if (title.split(' ').size >= 3) return title
        val st = com.tom_roush.pdfbox.text.PDFTextStripper().apply { startPage = 1; endPage = minOf(3, doc.numberOfPages) }
        val stop = setOf("para", "como", "sobre", "with", "from", "that", "this", "were", "which", "their", "also", "entre", "pelo", "pela")
        return Regex("[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\\-]{3,}").findAll(runCatching { st.getText(doc) }.getOrDefault("")).map { it.value.lowercase() }
            .filter { it !in stop }.groupingBy { it }.eachCount().entries.sortedByDescending { it.value }.take(5).joinToString(" ") { it.key }
    }

    fun parseEuropePmc(data: JSONObject, onlyPdf: Boolean = true): Pair<List<Article>, Int> {
        val out = ArrayList<Article>()
        val res = data.optJSONObject("resultList")?.optJSONArray("result") ?: return out to 0
        for (i in 0 until res.length()) {
            val r = res.getJSONObject(i)
            val pdfs = LinkedHashSet<String>()
            r.optJSONObject("fullTextUrlList")?.optJSONArray("fullTextUrl")?.let { l -> for (k in 0 until l.length()) l.optJSONObject(k)?.let { u ->
                if (u.optString("documentStyle") == "pdf" && u.optString("availabilityCode") in setOf("OA", "F")) pdfs += u.optString("url") } }
            r.optString("pmcid").takeIf { it.isNotEmpty() }?.let { pdfs += "https://europepmc.org/articles/$it?pdf=render" }
            if (pdfs.isEmpty() && onlyPdf) continue
            val authors = r.optJSONObject("authorList")?.optJSONArray("author")?.let { a -> (0 until a.length()).map { a.getJSONObject(it).optString("fullName") } } ?: emptyList()
            val ji = r.optJSONObject("journalInfo") ?: JSONObject()
            out += Article(
                title = r.optString("title").trimEnd('.'), authors = authors, year = r.optString("pubYear").toIntOrNull(),
                venue = ji.optJSONObject("journal")?.optString("title") ?: "", citations = if (r.has("citedByCount")) r.optInt("citedByCount") else null,
                language = r.optString("language").take(2), doi = r.optString("doi").takeIf { it.isNotEmpty() }?.let { "https://doi.org/$it" } ?: "",
                pdfUrls = pdfs.toList(), pageUrl = "https://europepmc.org/article/${r.optString("source", "MED")}/${r.optString("id")}",
                volume = ji.optString("volume"), issue = ji.optString("issue"), pages = r.optString("pageInfo"), source = "Europe PMC",
                abstract = r.optString("abstractText").replace(Regex("<[^>]+>"), ""),
                kind = if (r.optString("pubTypeList").contains("review", true)) "review" else "article")
        }
        return out to data.optInt("hitCount", out.size)
    }

    /** (artigos, total). OpenAlex; se recusar (limite diário) ou falhar, Europe PMC. */
    fun search(query: String, yearFrom: Int? = null, sort: String = "relevance", page: Int = 1, filters: Set<String> = setOf("pdf")): Pair<List<Article>, Int> {
        val q = query.trim()
        if (q.isEmpty()) return emptyList<Article>() to 0
        val first = runCatching {
            val extra = if (yearFrom != null) listOf("publication_year:>${yearFrom - 1}") else emptyList()
            val url = "https://api.openalex.org/works?search=${enc(q)}&filter=${enc(flt(filters, extra))}&per_page=25&page=$page&select=${enc(SELECT)}" + sortParam(sort)
            return parseOpenAlex(getJson(url), "pdf" in filters)
        }.exceptionOrNull()
        return runCatching {
            var qq = "($q)" + filters.joinToString("") { FILTERS[it]?.third ?: "" }
            if (yearFrom != null) qq += " AND PUB_YEAR:[$yearFrom TO 3000]"
            var url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=${enc(qq)}&format=json&resultType=core&pageSize=25&page=$page"
            if (sort == "citations") url += "&sort=${enc("CITED desc")}" else if (sort == "recent") url += "&sort=${enc("P_PDATE_D desc")}"
            parseEuropePmc(getJson(url), "pdf" in filters)
        }.getOrElse { throw java.io.IOException("Não foi possível pesquisar agora (${first?.message}; ${it.message}). Verifique a internet.") }
    }

    fun stripAccents(s: String) = java.text.Normalizer.normalize(s, java.text.Normalizer.Form.NFD).replace(Regex("\\p{Mn}+"), "")

    private var acc: Map<String, String>? = null
    fun loadAccents(ctx: android.content.Context) {
        if (acc != null) return
        acc = runCatching {
            ctx.assets.open("dados/acentos.txt").bufferedReader().readLines().filter { "=" in it && !it.startsWith("#") }
                .associate { it.substringBefore("=").trim() to it.substringAfter("=").trim() }
        }.getOrDefault(emptyMap())
    }

    /** Recoloca acentos em palavras comuns digitadas sem eles (caes → cães). */
    fun restoreAccents(q: String, table: Map<String, String>? = acc): String = Regex("[A-Za-z]+").replace(q) { m ->
        val w = m.value
        val b = table?.get(w.lowercase()) ?: return@replace w
        when {
            w.length > 1 && w.all { it.isUpperCase() } -> b.uppercase()
            w[0].isUpperCase() -> b.replaceFirstChar { it.uppercase() }
            else -> b
        }
    }

    /** A pesquisa digitada e uma versão corrigida (com os acentos que faltaram ou, se já tinha, sem acentos e hífens). */
    fun variants(q: String, table: Map<String, String>? = acc): List<String> {
        val fixed = restoreAccents(q, table)
        val out = ArrayList<String>()
        for (v in listOf(q, if (fixed != q) fixed else stripAccents(q).replace("-", " "))) {
            val n = v.split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
            if (n.isNotEmpty() && out.none { it.equals(n, true) }) out += n
        }
        return out
    }

    fun key(a: Article) = a.doi.lowercase().ifEmpty { stripAccents(a.title).lowercase().replace(Regex("[^a-z0-9]+"), " ").trim() }

    /** Pesquisa várias versões e intercala os resultados (os em inglês aparecem junto dos em português), sem repetir. */
    fun searchMany(queries: List<String>, yearFrom: Int?, sort: String, page: Int, seen: MutableSet<String>, filters: Set<String> = setOf("pdf")): Pair<List<Article>, Int> {
        val lists = ArrayList<List<Article>>(); var total = 0; var err: Exception? = null
        for (q in queries) runCatching { search(q, yearFrom, sort, page, filters) }.onSuccess { (a, n) -> lists += a; total = maxOf(total, n) }.onFailure { err = it as? Exception }
        if (lists.isEmpty() && err != null) throw err!!
        val out = ArrayList<Article>()
        for (i in 0 until (lists.maxOfOrNull { it.size } ?: 0)) for (l in lists) if (i < l.size && seen.add(key(l[i]))) out += l[i]
        return out to total
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
private data class NavState(val mode: String, val about: Article?, val results: List<Article>, val total: Int, val page: Int)

/** Pesquisa de artigos: sugestões enquanto digita, filtros em botões, resumo traduzido, parecidos / quem citou /
 *  referências (com voltar), rolagem contínua, DOI ou link colado e artigos sobre o documento aberto. */
@OptIn(ExperimentalMaterial3Api::class, androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun ArticlesScreen(vm: AppVm, initialQuery: String = "", onClose: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val sp = remember { ctx.getSharedPreferences("prefs", 0) }
    var q by remember { mutableStateOf(initialQuery) }
    var english by remember { mutableStateOf(vm.prefs.articlesEnglish) }
    var sort by remember { mutableStateOf("relevance") }
    var filters by remember { mutableStateOf((sp.getString("artigos_filtros", "pdf") ?: "pdf").split(",").filter { it.isNotEmpty() }.toSet()) }
    val results = remember { mutableStateListOf<Article>() }
    var total by remember { mutableStateOf(0) }
    var page by remember { mutableStateOf(1) }
    var busy by remember { mutableStateOf<String?>(null) }
    var msg by remember { mutableStateOf<String?>(null) }
    var mode by remember { mutableStateOf("search") }       // search | related | citing | refs | one
    var about by remember { mutableStateOf<Article?>(null) }
    val stack = remember { mutableStateListOf<NavState>() }
    var suggestions by remember { mutableStateOf<List<Triple<String, String, String>>>(emptyList()) }
    var typed by remember { mutableStateOf(false) }
    val listState = rememberLazyListState()
    val dst = Traducao.target(vm.prefs)

    fun load(more: Boolean, block: suspend () -> Pair<List<Article>, Int>) {
        if (!more) { results.clear(); page = 1; total = 0 }
        msg = null
        scope.launch {
            try {
                val (arts, t) = block()
                val seen = results.map { Artigos.key(it) }.toMutableSet()
                arts.forEach { if (seen.add(Artigos.key(it))) results += it }
                total = if (more) maxOf(total, t) else t
                if (results.isEmpty()) msg = "Nada encontrado. Tente outras palavras, desligue algum filtro ou marque “também em inglês”."
            } catch (e: Exception) { msg = e.message } finally { busy = null }
        }
    }

    fun openKey(key: String) {
        mode = "one"; stack.clear(); busy = "Buscando o artigo…"
        load(false) { withContext(Dispatchers.IO) { listOf(Artigos.byKey(key)) to 1 } }
    }

    fun run(more: Boolean = false) {
        val text = q.trim()
        if (text.isEmpty()) return
        suggestions = emptyList(); typed = false
        if (!more) Artigos.parseLink(text)?.let { openKey(it); return }
        vm.prefs.articlesEnglish = english
        if (!more) {
            mode = "search"; stack.clear()
            val h = (sp.getString("artigos_historico", "") ?: "").split("\n").filter { it.isNotBlank() && it != text }
            sp.edit().putString("artigos_historico", (listOf(text) + h).take(30).joinToString("\n")).apply()
        } else page++
        busy = "Pesquisando…"
        val pg = page; val srt = sort; val flt = filters
        load(more) {
            Artigos.loadAccents(ctx)
            val queries = Artigos.variants(text).toMutableList()
            if (english && Traducao.detect("$text ".repeat(12)) != "en") {
                if (Traducao.missing("pt", "en").isNotEmpty()) {
                    busy = "Preparando a pesquisa em inglês (download único, cerca de 30 MB)…"
                    runCatching { Traducao.download("pt", "en") }
                }
                runCatching { Traducao.translate("pt", "en", Artigos.restoreAccents(text)) }.getOrNull()
                    ?.trim()?.trimEnd('.')?.takeIf { it.isNotEmpty() && queries.none { x -> x.equals(it, true) } }
                    ?.let { queries += it; busy = "Pesquisando também em inglês (“$it”)…" }
            }
            val seen = if (more) results.map { Artigos.key(it) }.toMutableSet() else mutableSetOf()
            withContext(Dispatchers.IO) { Artigos.searchMany(queries, null, srt, pg, seen, flt) }
        }
    }

    fun navigate(kind: String, a: Article) {
        stack += NavState(mode, about, results.toList(), total, page)
        mode = kind; about = a
        busy = mapOf("related" to "Buscando artigos parecidos…", "citing" to "Buscando quem citou…", "refs" to "Buscando as referências…")[kind]
        val srt = sort; val flt = filters
        load(false) {
            withContext(Dispatchers.IO) {
                when (kind) {
                    "related" -> Artigos.byIds(a.related) to a.related.size
                    "refs" -> Artigos.byIds(a.refs) to a.refs.size
                    else -> Artigos.citing(a.id, 1, flt, srt)
                }
            }
        }
    }

    fun back() {
        val s0 = stack.removeLastOrNull() ?: return
        mode = s0.mode; about = s0.about; total = s0.total; page = s0.page
        results.clear(); results += s0.results
    }

    fun refilter() {
        sp.edit().putString("artigos_filtros", filters.joinToString(",")).apply()
        when (mode) {
            "search" -> if (q.isNotBlank()) run()
            "citing" -> about?.let { a ->
                busy = "Buscando quem citou…"; val srt = sort; val flt = filters
                load(false) { withContext(Dispatchers.IO) { Artigos.citing(a.id, 1, flt, srt) } }
            }
        }
    }

    // sugestões enquanto digita (só depois de parar de digitar)
    LaunchedEffect(q, typed) {
        if (!typed || q.trim().length < 3 || Artigos.parseLink(q) != null) { suggestions = emptyList(); return@LaunchedEffect }
        kotlinx.coroutines.delay(450)
        val text = q.trim()
        val hist = (sp.getString("artigos_historico", "") ?: "").split("\n").filter { it.isNotBlank() && it.contains(text, true) }.take(3)
            .map { Triple("hist", it, "") }
        val en = if (Traducao.detect("$text ".repeat(12)) != "en" && Traducao.missing("pt", "en").isEmpty())
            runCatching { Traducao.translate("pt", "en", Artigos.restoreAccents(text)) }.getOrNull() else null
        val auto = withContext(Dispatchers.IO) { (listOfNotNull(text, en?.takeIf { !it.equals(text, true) })).flatMap { runCatching { Artigos.autocomplete(it) }.getOrDefault(emptyList()) } }
        if (q.trim() == text) suggestions = (hist + auto).distinctBy { it.second.lowercase() }.take(10)
    }

    // rolagem contínua
    LaunchedEffect(listState, results.size, total, busy) {
        snapshotFlow { listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }.collect { last ->
            if (busy == null && results.isNotEmpty() && results.size < total && last >= results.size - 3) {
                if (mode == "search") run(more = true)
                else if (mode == "citing") about?.let { a -> page++; busy = "Carregando…"; val pg = page; val flt = filters; val srt = sort
                    load(true) { withContext(Dispatchers.IO) { Artigos.citing(a.id, pg, flt, srt) } } }
            }
        }
    }

    LaunchedEffect(Unit) { if (initialQuery.isNotBlank()) { english = true; run() } }

    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Scaffold(topBar = {
            TopAppBar(title = { Text(if (mode == "search" || mode == "one") "Artigos científicos" else
                    mapOf("related" to "Parecidos", "citing" to "Quem citou", "refs" to "Referências")[mode]!!) },
                navigationIcon = { IconButton({ if (stack.isNotEmpty()) back() else onClose() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Voltar") } })
        }) { pad ->
            Column(Modifier.fillMaxSize().padding(pad)) {
                OutlinedTextField(q, { q = it; typed = true }, Modifier.fillMaxWidth().padding(horizontal = 14.dp),
                    placeholder = { Text("Tema, DOI ou link do artigo") }, singleLine = true,
                    trailingIcon = { IconButton({ run() }) { Icon(Icons.Filled.Search, "Pesquisar") } },
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search), keyboardActions = KeyboardActions(onSearch = { run() }))
                if (suggestions.isNotEmpty()) Surface(shadowElevation = 6.dp, shape = RoundedCornerShape(10.dp),
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 2.dp)) {
                    Column {
                        suggestions.forEach { (kind, label, id) ->
                            Row(Modifier.fillMaxWidth().clickable {
                                suggestions = emptyList(); typed = false; q = label
                                if (kind == "artigo" && id.isNotEmpty()) openKey(id) else run()
                            }.padding(horizontal = 12.dp, vertical = 9.dp), verticalAlignment = Alignment.CenterVertically) {
                                Text(when (kind) { "tema" -> "🔎"; "artigo" -> "📄"; else -> "🕘" }, Modifier.padding(end = 8.dp))
                                Text(label, maxLines = 2, style = MaterialTheme.typography.bodyMedium)
                            }
                        }
                    }
                }
                androidx.compose.foundation.layout.FlowRow(Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Artigos.FILTERS.forEach { (k, f) ->
                        FilterChip(selected = k in filters, onClick = { filters = if (k in filters) filters - k else filters + k; refilter() }, label = { Text(f.first) })
                    }
                    listOf("relevance" to "Relevância", "citations" to "Mais citados", "recent" to "Recentes").forEach { (k, l) ->
                        FilterChip(selected = sort == k, onClick = { sort = k; refilter() }, label = { Text(l) })
                    }
                    FilterChip(selected = english, onClick = { english = !english }, label = { Text("Também em inglês") })
                }
                if (busy != null) { LinearProgressIndicator(Modifier.fillMaxWidth()); Text(busy!!, Modifier.padding(horizontal = 16.dp), style = MaterialTheme.typography.bodySmall) }
                msg?.let { Text(it, Modifier.padding(horizontal = 16.dp, vertical = 4.dp), color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                if (results.isNotEmpty()) Text((about?.let { "“${it.title.take(70)}” — " } ?: "") + "${results.size}" + (if (total > results.size) " de $total" else "") +
                    " · fonte: ${results.map { it.source }.distinct().joinToString()}",
                    Modifier.padding(horizontal = 16.dp, vertical = 2.dp), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (results.isEmpty() && busy == null && msg == null) Text("Artigos de revistas e repositórios do mundo todo. Os em outro idioma podem ser traduzidos " +
                    "ao abrir, sem internet. Dica: cole um DOI ou link de artigo para ir direto a ele.", Modifier.padding(16.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
                LazyColumn(state = listState, contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(results, key = { Artigos.key(it) + it.id }) { a ->
                        ArticleCard(a, dst,
                            onOpen = {
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
                            },
                            onRef = { copyText(ctx, "Referência", a.abnt()); vm.toast = "Referência ABNT copiada" },
                            onWeb = { runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(a.pageUrl.ifEmpty { a.pdfUrls.firstOrNull() ?: a.doi }))) } },
                            onNav = { kind -> navigate(kind, a) })
                    }
                }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun ArticleCard(a: Article, dst: String, onOpen: () -> Unit, onRef: () -> Unit, onWeb: () -> Unit, onNav: (String) -> Unit) {
    var showAbs by remember { mutableStateOf(false) }
    var translated by remember { mutableStateOf<String?>(null) }
    var ask by remember { mutableStateOf(false) }
    val src = a.language.ifEmpty { Traducao.detect(a.abstract) ?: "en" }
    Surface(shape = RoundedCornerShape(10.dp), border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text(a.title, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyLarge)
            Text(listOf(a.authorsShort, a.venue, a.year?.toString() ?: "").filter { it.isNotEmpty() }.joinToString(" · "),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 3.dp))
            androidx.compose.foundation.layout.FlowRow(Modifier.padding(top = 5.dp), horizontalArrangement = Arrangement.spacedBy(5.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                if (a.hasPdf) Badge("PDF grátis", Color(0xFFE7F6EE), Color(0xFF1F7A5A)) else Badge("sem PDF gratuito", Color(0xFFFDE8E9), Color(0xFFB0262E))
                if (a.language.isNotEmpty()) Badge(Traducao.NAMES[a.language] ?: a.language, Color(0xFFEEF3FC), Color(0xFF1D5FBF))
                if (a.kind == "review") Badge("revisão", Color(0xFFFFF6DD), Color(0xFF8A6100))
                if (a.kind == "preprint") Badge("preprint", Color(0xFFFFF6DD), Color(0xFF8A6100))
                if ((a.citations ?: 0) > 0) Badge("${a.citations} citações", Color(0xFFF1ECFE), Color(0xFF5B2BB5))
            }
            if (showAbs) {
                LaunchedEffect(Unit) {
                    if (translated == null && src != dst && Traducao.supported(src)) {
                        if (Traducao.missing(src, dst).isEmpty()) translated = runCatching { Citacoes.translate(a.abstract) { Traducao.translate(src, dst, it) } }.getOrNull()
                        else ask = true
                    }
                }
                Text(if (translated != null) "Resumo (tradução automática)" else "Resumo", fontWeight = FontWeight.SemiBold,
                    style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(top = 8.dp))
                androidx.compose.foundation.text.selection.SelectionContainer { Text(translated ?: a.abstract, style = MaterialTheme.typography.bodySmall) }
            }
            if (ask) ModelGate(src, dst, onCancel = { ask = false }) {
                ask = false; translated = null; showAbs = false; showAbs = true
            }
            androidx.compose.foundation.layout.FlowRow(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                TextButton(onOpen, enabled = a.hasPdf) { Text("Abrir PDF") }
                TextButton({ showAbs = !showAbs }, enabled = a.abstract.isNotEmpty()) { Text(if (showAbs) "Fechar resumo" else "Resumo") }
                if (a.id.isNotEmpty()) {
                    TextButton({ onNav("related") }, enabled = a.related.isNotEmpty()) { Text("Parecidos") }
                    TextButton({ onNav("citing") }, enabled = (a.citations ?: 0) > 0) { Text("Citado por (${a.citations ?: 0})") }
                    TextButton({ onNav("refs") }, enabled = a.refs.isNotEmpty()) { Text("Referências (${a.refs.size})") }
                }
                TextButton(onRef) { Text("ABNT") }
                TextButton(onWeb) { Text("Página", color = Color(0xFF1473E6)) }
            }
        }
    }
}

@Composable
private fun Badge(text: String, bg: Color, fg: Color) {
    Surface(color = bg, shape = RoundedCornerShape(8.dp)) {
        Text(text, color = fg, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(horizontal = 7.dp, vertical = 2.dp))
    }
}
