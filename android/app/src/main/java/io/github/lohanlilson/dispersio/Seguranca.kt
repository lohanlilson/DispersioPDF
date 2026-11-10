package io.github.lohanlilson.dispersio

import com.tom_roush.pdfbox.cos.COSArray
import com.tom_roush.pdfbox.cos.COSDictionary
import com.tom_roush.pdfbox.cos.COSName
import com.tom_roush.pdfbox.cos.COSString
import com.tom_roush.pdfbox.pdmodel.PDDocument
import java.net.IDN
import java.net.URI
import java.net.URLDecoder
import java.text.Normalizer

/** Proteção contra PDFs de golpe: links enganosos e conteúdo perigoso escondido no arquivo (igual ao do computador). */
object Seguranca {
    const val DANGER = 2
    const val WARN = 1
    const val INFO = 0

    data class Risk(val level: Int, val text: String)
    data class LinkCheck(val url: String, val host: String = "", val domain: String = "", val risks: List<Risk> = emptyList()) {
        val level get() = risks.maxOfOrNull { it.level } ?: -1
    }
    data class Threat(val level: Int, val title: String, val detail: String = "", val page: Int = -1)

    private val SHORTENERS = setOf(
        "bit.ly", "bitly.com", "tinyurl.com", "t.co", "goo.gl", "is.gd", "ow.ly", "buff.ly", "cutt.ly", "rb.gy",
        "shorturl.at", "tiny.cc", "rebrand.ly", "s.id", "t.ly", "v.gd", "encurtador.com.br", "abre.ai", "l1nk.dev",
        "short.io", "bl.ink", "lnkd.in", "trib.al", "u.to", "x.gd", "shre.ink", "encurta.net", "migre.me", "qrco.de",
        "linktr.ee", "tinu.be", "1url.com.br", "curt.link", "bit.do", "urlz.fr")

    private val BRANDS = mapOf(
        "bradesco" to listOf("bradesco.com.br"), "itau" to listOf("itau.com.br", "itau-unibanco.com.br"),
        "santander" to listOf("santander.com.br", "santander.com"), "caixa" to listOf("caixa.gov.br"),
        "bancodobrasil" to listOf("bb.com.br"), "nubank" to listOf("nubank.com.br", "nu.com.mx", "nubank.com"),
        "bancointer" to listOf("bancointer.com.br", "inter.co"), "sicoob" to listOf("sicoob.com.br"), "sicredi" to listOf("sicredi.com.br"),
        "mercadopago" to listOf("mercadopago.com.br", "mercadopago.com", "mercadolivre.com.br"),
        "mercadolivre" to listOf("mercadolivre.com.br", "mercadolibre.com"), "picpay" to listOf("picpay.com"),
        "pagseguro" to listOf("pagseguro.uol.com.br", "pagbank.com.br"), "pagbank" to listOf("pagbank.com.br"),
        "c6bank" to listOf("c6bank.com.br"), "serasa" to listOf("serasa.com.br", "serasaexperian.com.br"),
        "receita" to listOf("gov.br", "receita.fazenda.gov.br"), "correios" to listOf("correios.com.br"), "detran" to listOf("gov.br"),
        "paypal" to listOf("paypal.com"), "microsoft" to listOf("microsoft.com", "live.com", "office.com", "microsoftonline.com", "sharepoint.com"),
        "office365" to listOf("office.com", "microsoft.com", "microsoftonline.com"), "outlook" to listOf("outlook.com", "live.com", "office.com"),
        "docusign" to listOf("docusign.com", "docusign.net"), "dropbox" to listOf("dropbox.com"), "netflix" to listOf("netflix.com"),
        "amazon" to listOf("amazon.com", "amazon.com.br"), "apple" to listOf("apple.com", "icloud.com"), "icloud" to listOf("icloud.com", "apple.com"),
        "whatsapp" to listOf("whatsapp.com", "wa.me"), "instagram" to listOf("instagram.com"), "facebook" to listOf("facebook.com", "fb.com"),
        "gov.br" to listOf("gov.br"), "shopee" to listOf("shopee.com.br"), "magalu" to listOf("magazineluiza.com.br", "magalu.com"))

    private val DISTINCT = setOf("bradesco", "santander", "nubank", "bancodobrasil", "bancointer", "mercadopago", "mercadolivre", "picpay",
        "pagseguro", "pagbank", "sicoob", "sicredi", "serasa", "correios", "paypal", "office365", "docusign",
        "netflix", "whatsapp", "instagram", "facebook", "shopee", "c6bank", "icloud", "microsoft")

    val EXEC_EXT = setOf("exe", "scr", "msi", "bat", "cmd", "com", "pif", "js", "jse", "vbs", "vbe", "wsf", "ps1", "hta",
        "jar", "lnk", "reg", "apk", "dll", "cpl", "msc", "iso", "img", "vhd", "docm", "xlsm", "pptm", "appx", "msix")
    val ARCHIVE_EXT = setOf("zip", "rar", "7z", "gz", "tar", "cab", "arj")
    private val SECOND_LEVEL = setOf("com", "net", "org", "gov", "edu", "art", "blog", "eco", "emp", "eng", "ind", "inf", "jus", "leg",
        "med", "mil", "rec", "srv", "tur", "app", "dev", "log", "adv", "arq", "coop", "nom", "co", "ac", "or", "ne", "go")

    private fun plain(s: String) = Normalizer.normalize(s, Normalizer.Form.NFD).replace(Regex("\\p{Mn}+"), "").lowercase()

    fun registeredDomain(host: String): String {
        val h = host.lowercase().trim('.')
        val parts = h.split('.')
        if (parts.size <= 2) return h
        return if (parts.last().length == 2 && parts[parts.size - 2] in SECOND_LEVEL) parts.takeLast(3).joinToString(".")
        else parts.takeLast(2).joinToString(".")
    }

    private val IP = Regex("^\\d{1,3}(\\.\\d{1,3}){3}$|^\\[?[0-9a-f:]+\\]?$", RegexOption.IGNORE_CASE)
    private val DOMAIN_IN_TEXT = Regex("(?:https?://)?((?:[a-z0-9-]+\\.)+(?:com|net|org|gov|br|io|co|me|app|info|biz|online|site|xyz|top|ly|gl|us|pt)(?:\\.[a-z]{2})?)\\b",
        RegexOption.IGNORE_CASE)

    private fun dec(s: String) = runCatching { URLDecoder.decode(s.replace("+", "%2B"), "UTF-8") }.getOrDefault(s)

    fun linkRisk(uri: String, shown: String = ""): LinkCheck {
        val url = uri.trim()
        val r = ArrayList<Risk>()
        val scheme = url.substringBefore(':', "").lowercase()
        when (scheme) {
            "mailto" -> return LinkCheck(url, risks = listOf(Risk(INFO, "Abre o e-mail para escrever a ${dec(url.substringAfter(':').substringBefore('?'))}.")))
            "tel", "sms" -> return LinkCheck(url, risks = listOf(Risk(INFO, "Liga ou manda mensagem para ${dec(url.substringAfter(':'))}.")))
            "http", "https" -> {}
            else -> return LinkCheck(url, risks = listOf(Risk(DANGER, "Não é um site: o link usa “${scheme.ifEmpty { "?" }}:”, que pode abrir arquivos ou aplicativos.")))
        }
        val afterScheme = url.substringAfter("://", "")
        val authority = afterScheme.substringBefore('/').substringBefore('?').substringBefore('#')
        val host = authority.substringAfterLast('@').substringBefore(':').lowercase().removePrefix("[").removeSuffix("]")
        val domain = registeredDomain(host)
        if (host.isEmpty()) return LinkCheck(url, risks = listOf(Risk(DANGER, "O link não tem endereço de site.")))
        if ('@' in authority) r += Risk(DANGER, "O endereço esconde o site verdadeiro: tudo antes do “@” é enfeite; o site é $host.")
        if (IP.matches(host)) r += Risk(DANGER, "O site é só um número (endereço IP), sem nome — empresas de verdade não fazem isso.")
        if ("xn--" in host) {
            val shownHost = runCatching { IDN.toUnicode(host) }.getOrDefault(host)
            r += Risk(DANGER, "O nome do site usa letras de outros alfabetos que imitam letras comuns ($shownHost).")
        }
        if (domain in SHORTENERS || host in SHORTENERS) r += Risk(WARN, "É um link encurtado ($domain): não dá para saber para onde ele leva de verdade.")
        val path = dec(runCatching { URI(url).rawPath ?: "" }.getOrDefault(afterScheme.substringAfter('/', ""))).lowercase()
        if (host.endsWith("wa.me") || "whatsapp" in domain) {
            val num = path.filter { it.isDigit() }
            if (num.isNotEmpty()) r += Risk(INFO, "Abre uma conversa no WhatsApp com o número +$num.")
        }
        val tokens = host.split('.', '-', '_').filter { it.isNotEmpty() }
        val joined = tokens.joinToString("")
        for ((brand, official) in BRANDS) {
            val hit = if (brand == "gov.br") ("govbr" in tokens || tokens.zipWithNext().any { (a, b) -> a == "gov" && b == "br" }) && !host.endsWith(".gov.br")
                else brand in tokens || (brand in DISTINCT && brand in joined)
            if (hit && official.none { host == it || host.endsWith(".$it") }) {
                r += Risk(DANGER, "O endereço usa o nome “$brand”, mas o site é $domain, que não é o oficial.")
                break
            }
        }
        val last = path.substringAfterLast('/')
        val ext = if ('.' in last) last.substringAfterLast('.') else ""
        if (ext in EXEC_EXT) r += Risk(DANGER, "O link baixa um programa (.$ext). Golpes usam isso para instalar vírus.")
        else if (ext in ARCHIVE_EXT) r += Risk(WARN, "O link baixa um arquivo compactado (.$ext), que pode conter programas.")
        if (shown.isNotBlank()) {
            DOMAIN_IN_TEXT.find(plain(shown).replace(" ", ""))?.let { m ->
                val sd = registeredDomain(m.groupValues[1].lowercase())
                if (sd.isNotEmpty() && sd != domain && !host.endsWith(sd))
                    r += Risk(DANGER, "O texto mostra “${m.groupValues[1]}”, mas o link vai para $domain.")
            }
        }
        if (scheme == "http" && r.none { it.level == DANGER })
            r += Risk(WARN, "O site não usa conexão segura (https): não digite senhas nem dados de cartão nele.")
        return LinkCheck(url, host, domain, r)
    }

    /** Texto que está de fato dentro da área do link (caracteres com o centro dentro dela). */
    fun shownText(chars: PageChars, a: FracRect): String {
        val sb = StringBuilder()
        val dx = (a.r - a.l) * 0.01f; val dy = (a.b - a.t) * 0.05f
        for (k in 0 until chars.size) {
            val f = chars.frac[k] ?: continue
            val cx = (f.l + f.r) / 2; val cy = (f.t + f.b) / 2
            if (cx in (a.l - dx)..(a.r + dx) && cy in (a.t - dy)..(a.b + dy)) sb.append(chars.text[k]) else if (sb.isNotEmpty() && sb.last() != ' ') sb.append(' ')
        }
        return sb.toString().trim()
    }

    // ------------------------------------------------------------------ documento
    private val BAD_ACTIONS = setOf("JavaScript", "Launch", "SubmitForm", "ImportData", "GoToE")

    private fun str(d: COSDictionary, key: String): String = when (val v = d.getDictionaryObject(key)) {
        is COSString -> v.string
        is COSDictionary -> (v.getDictionaryObject("F") as? COSString)?.string ?: (v.getDictionaryObject("UF") as? COSString)?.string ?: ""
        else -> ""
    }

    /** Ações, JavaScript e anexos (lendo os objetos do arquivo). */
    fun scanDoc(doc: PDDocument): List<Threat> {
        val out = ArrayList<Threat>()
        var js = 0; var launch = 0; var submit = 0; var auto = false
        val launchFiles = ArrayList<String>(); val submitUrls = ArrayList<String>()
        val attach = LinkedHashSet<String>()
        for (o in runCatching { doc.document.objects }.getOrDefault(emptyList())) {
            val d = o.`object` as? COSDictionary ?: continue
            if (d.containsKey(COSName.getPDFName("JS"))) js++
            when (d.getCOSName(COSName.S)?.name) {
                "JavaScript" -> js++
                "Launch", "GoToE" -> { launch++; str(d, "F").takeIf { it.isNotEmpty() }?.let { launchFiles += it } }
                "SubmitForm" -> { submit++; str(d, "F").takeIf { it.isNotEmpty() }?.let { submitUrls += it } }
            }
            if (d.getCOSName(COSName.TYPE)?.name == "Filespec" || d.containsKey(COSName.EF)) {
                val n = (d.getDictionaryObject(COSName.UF) as? COSString)?.string ?: (d.getDictionaryObject(COSName.F) as? COSString)?.string
                if (!n.isNullOrBlank()) attach += n
            }
        }
        val cat = doc.documentCatalog.cosObject
        val oa = cat.getDictionaryObject(COSName.OPEN_ACTION)
        if (oa is COSDictionary) {
            val s = oa.getCOSName(COSName.S)?.name
            if (s != null && s != "GoTo") auto = true
            if (s == "URI") out += Threat(DANGER, "Abre um site sozinho ao abrir o documento", str(oa, "URI"))
        }
        if (cat.containsKey(COSName.AA)) auto = true
        if (js > 0) out += Threat(if (auto || launch > 0) DANGER else WARN, "Contém JavaScript (código escondido)",
            "O Dispersio PDF não executa esse código, mas outros leitores podem executar. Documentos comuns (boletos, contratos, notas) não precisam disso.")
        if (launch > 0) out += Threat(DANGER, "Tenta abrir um programa ou arquivo do aparelho", launchFiles.take(3).joinToString().ifEmpty { "ação “Launch”" })
        if (submit > 0) {
            val dests = submitUrls.mapNotNull { u -> u.substringAfter("://", "").substringBefore('/').takeIf { it.isNotEmpty() }?.let { registeredDomain(it) } }.distinct()
            out += Threat(WARN, "O formulário envia o que for digitado para a internet", if (dests.isEmpty()) "" else "Destino: " + dests.take(3).joinToString())
        }
        if (auto && js == 0 && launch == 0) out += Threat(WARN, "Executa uma ação sozinho ao ser aberto")
        for (n in attach) {
            val ext = if ('.' in n) n.substringAfterLast('.').lowercase() else ""
            if (ext in EXEC_EXT) out += Threat(DANGER, "Tem um programa anexado: $n", "Não salve nem abra esse anexo.")
            else if (ext in ARCHIVE_EXT) out += Threat(WARN, "Tem um arquivo compactado anexado: $n", "Pode conter programas; só abra se esperava receber.")
        }
        return out
    }

    /** Links suspeitos e o “botão falso” (imagem com um link cobrindo a página). */
    suspend fun scanLinks(engine: PdfEngine, pdf: OpenPdf, pages: Int, maxPages: Int = 300): List<Threat> {
        val bad = ArrayList<Pair<Int, LinkCheck>>()
        var fake: Pair<Int, LinkCheck>? = null
        for (p in 0 until minOf(pages, maxPages)) {
            kotlinx.coroutines.yield()
            val links = runCatching { engine.links(pdf, p) }.getOrDefault(emptyList()).filter { !it.uri.isNullOrBlank() }
            if (links.isEmpty()) continue
            val chars = runCatching { engine.pageChars(pdf, p) }.getOrNull()
            for (ln in links) {
                val chk = linkRisk(ln.uri!!, chars?.let { shownText(it, ln.area) } ?: "")
                if (chk.level >= DANGER) bad += p to chk
                val a = ln.area
                if (fake == null && (a.r - a.l) * (a.b - a.t) > 0.2f && (chars?.text?.trim()?.length ?: 0) < 300) fake = p to chk
            }
        }
        val out = ArrayList<Threat>()
        fake?.let { (p, chk) ->
            out += Threat(DANGER, "Página com “botão” que leva para um site",
                "Quase toda a página ${p + 1} é um link para ${chk.domain.ifEmpty { chk.url }}. Golpes usam uma imagem de documento borrado com “clique para visualizar” para roubar senhas.", p)
        }
        val seen = HashSet<Pair<String, String>>()
        for ((p, chk) in bad) {
            val worst = chk.risks.maxBy { it.level }
            if (!seen.add(chk.domain to (chk.risks.firstOrNull()?.text ?: ""))) continue
            out += Threat(DANGER, "Link suspeito na página ${p + 1}", worst.text, p)
            if (seen.size >= 5) break
        }
        return out
    }

    /** Tira JavaScript, ações automáticas, abrir programas e anexos. Mantém texto, imagens, comentários, campos e links. */
    fun removeActiveContent(doc: PDDocument) {
        val cat = doc.documentCatalog.cosObject
        (cat.getDictionaryObject(COSName.OPEN_ACTION) as? COSDictionary)?.let { oa ->
            if (oa.getCOSName(COSName.S)?.name != "GoTo") cat.removeItem(COSName.OPEN_ACTION)
        }
        cat.removeItem(COSName.AA)
        (cat.getDictionaryObject(COSName.NAMES) as? COSDictionary)?.let { n ->
            n.removeItem(COSName.JAVA_SCRIPT)
            n.removeItem(COSName.EMBEDDED_FILES)
        }
        for (o in runCatching { doc.document.objects }.getOrDefault(emptyList())) {
            val d = o.`object` as? COSDictionary ?: continue
            d.removeItem(COSName.AA)
            val a = d.getDictionaryObject(COSName.A) as? COSDictionary
            if (a != null && a.getCOSName(COSName.S)?.name in BAD_ACTIONS) d.removeItem(COSName.A)
            if (d.getCOSName(COSName.S)?.name in BAD_ACTIONS && !d.containsKey(COSName.SUBTYPE)) {
                for (k in d.keySet().toList()) d.removeItem(k)
            }
        }
        for (page in doc.pages) {
            val annots = page.cosObject.getDictionaryObject(COSName.ANNOTS) as? COSArray ?: continue
            for (k in annots.size() - 1 downTo 0) {
                val an = annots.getObject(k) as? COSDictionary ?: continue
                if (an.getCOSName(COSName.SUBTYPE)?.name == "FileAttachment") annots.remove(k)
            }
        }
    }
}
