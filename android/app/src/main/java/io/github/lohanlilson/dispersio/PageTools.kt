package io.github.lohanlilson.dispersio

import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.os.Build
import android.provider.MediaStore
import com.tom_roush.pdfbox.cos.COSArray
import com.tom_roush.pdfbox.cos.COSBase
import com.tom_roush.pdfbox.cos.COSDictionary
import com.tom_roush.pdfbox.cos.COSInteger
import com.tom_roush.pdfbox.cos.COSName
import com.tom_roush.pdfbox.cos.COSObject
import com.tom_roush.pdfbox.cos.COSStream
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream
import com.tom_roush.pdfbox.pdmodel.PDResources
import com.tom_roush.pdfbox.pdmodel.common.PDMetadata
import com.tom_roush.pdfbox.pdmodel.common.PDRectangle
import com.tom_roush.pdfbox.pdmodel.graphics.color.PDOutputIntent
import com.tom_roush.pdfbox.pdmodel.graphics.form.PDFormXObject
import com.tom_roush.pdfbox.pdmodel.graphics.image.PDImageXObject
import com.tom_roush.pdfbox.util.Matrix
import java.io.File
import java.util.Calendar
import java.util.UUID
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin

/** Análise das páginas pela imagem renderizada: em branco, inclinação e margens. */
object PageAnalysis {
    private fun gray(bmp: Bitmap): Triple<Int, Int, IntArray> {
        val w = bmp.width; val h = bmp.height
        val px = IntArray(w * h)
        bmp.getPixels(px, 0, w, 0, 0, w, h)
        for (i in px.indices) {
            val c = px[i]
            px[i] = (((c shr 16) and 0xFF) * 299 + ((c shr 8) and 0xFF) * 587 + (c and 0xFF) * 114) / 1000
        }
        return Triple(w, h, px)
    }

    private fun percentile(v: IntArray, p: Double): Int {
        val hist = IntArray(256)
        v.forEach { hist[it]++ }
        val target = (v.size * p).toLong()
        var acc = 0L
        for (i in 0..255) { acc += hist[i]; if (acc >= target) return i }
        return 255
    }

    /** Página sem conteúdo visível (sem texto, comentários ou manchas além de ruído de digitalização). */
    suspend fun isBlank(engine: PdfEngine, pdf: OpenPdf, page: Int, hasAnnots: Boolean): Boolean {
        if (hasAnnots) return false
        if (engine.pageChars(pdf, page).text.any { !it.isWhitespace() && it != '\u0000' }) return false
        val (w, h, g) = gray(engine.render(pdf, page, 330))
        val mx = (w * 0.06).toInt(); val my = (h * 0.06).toInt()
        val inner = ArrayList<Int>(w * h)
        for (y in my until h - my) for (x in mx until w - mx) inner += g[y * w + x]
        val arr = inner.toIntArray()
        val bg = percentile(arr, 0.9)
        val dark = arr.count { it < bg - 60 }
        return dark.toDouble() / arr.size.coerceAtLeast(1) < 0.0012
    }

    /** Inclinação do texto em graus (positivo = linhas descendo para a direita na tela). */
    suspend fun skew(engine: PdfEngine, pdf: OpenPdf, page: Int, maxDeg: Double = 6.0): Double {
        val (w, h, g) = gray(engine.render(pdf, page, 900))
        val bg = percentile(g, 0.9)
        var xs = ArrayList<Double>(); var ys = ArrayList<Double>()
        for (y in 0 until h) for (x in 0 until w) if (g[y * w + x] < bg - 80) { xs += x - w / 2.0; ys += y - h / 2.0 }
        if (xs.size < 200) return 0.0
        if (xs.size > 50_000) {
            val step = xs.size / 50_000.0
            val nx = ArrayList<Double>(); val ny = ArrayList<Double>()
            var k = 0.0
            while (k < xs.size) { nx += xs[k.toInt()]; ny += ys[k.toInt()]; k += step }
            xs = nx; ys = ny
        }
        val diag = kotlin.math.hypot(w.toDouble(), h.toDouble()).toInt() + 2
        val hist = IntArray(diag * 2)
        fun score(deg: Double): Double {
            val t = Math.toRadians(deg); val c = cos(t); val s = sin(t)
            java.util.Arrays.fill(hist, 0)
            for (i in xs.indices) hist[(ys[i] * c - xs[i] * s).toInt() + diag]++
            var sum = 0.0
            for (v in hist) sum += v.toDouble() * v
            return sum
        }
        var best = 0.0; var bs = -1.0
        var d = -maxDeg
        while (d <= maxDeg + 1e-9) { val sc = score(d); if (sc > bs) { bs = sc; best = d }; d += 0.25 }
        var fine = best - 0.25
        val end = best + 0.25
        while (fine <= end + 1e-9) { val sc = score(fine); if (sc > bs) { bs = sc; best = fine }; fine += 0.05 }
        return Math.round(best * 100) / 100.0
    }

    /** Área com conteúdo (frações da largura, como no visualizador), ignorando bordas brancas ou pretas. */
    suspend fun contentBox(engine: PdfEngine, pdf: OpenPdf, page: Int): FracRect? {
        val bmp = engine.render(pdf, page, 600)
        val (w, h, g) = gray(bmp)
        val bg = percentile(g, 0.6)
        fun ink(v: Int) = abs(v - bg) > 60
        // linhas/colunas quase totalmente escuras nas bordas (sombra do escâner) não contam
        fun rowInk(y: Int): Int { var n = 0; for (x in 0 until w) if (ink(g[y * w + x])) n++; return n }
        fun colInk(x: Int): Int { var n = 0; for (y in 0 until h) if (ink(g[y * w + x])) n++; return n }
        val rows = IntArray(h) { rowInk(it) }; val cols = IntArray(w) { colInk(it) }
        fun useful(n: Int, len: Int) = n > len * 0.002 && n < len * 0.85
        val top = rows.indexOfFirst { useful(it, w) }; val bottom = rows.indexOfLast { useful(it, w) }
        val left = cols.indexOfFirst { useful(it, h) }; val right = cols.indexOfLast { useful(it, h) }
        if (top < 0 || left < 0 || bottom <= top || right <= left) return null
        val pad = w * 0.02f
        val l = ((left - pad) / w).coerceAtLeast(0f); val r = ((right + pad) / w).coerceAtMost(1f)
        val t = ((top - pad) / w).coerceAtLeast(0f); val b = ((bottom + pad) / w).coerceAtMost(h.toFloat() / w)
        return FracRect(l, t, r, b)
    }
}

/** Alterações de página com o PDFBox. */
object PageEdit {
    /** Gira o conteúdo da página em torno do centro (graus, anti-horário na tela). */
    fun rotateContent(doc: PDDocument, pageIndex: Int, degrees: Double): List<COSDictionary> {
        val page = doc.getPage(pageIndex)
        val box = page.cropBox
        val cx = box.lowerLeftX + box.width / 2; val cy = box.lowerLeftY + box.height / 2
        val m = Matrix.getTranslateInstance(cx, cy)
        m.concatenate(Matrix.getRotateInstance(Math.toRadians(degrees), 0f, 0f))
        m.concatenate(Matrix.getTranslateInstance(-cx, -cy))
        PDPageContentStream(doc, page, PDPageContentStream.AppendMode.PREPEND, true).use { cs ->
            cs.saveGraphicsState()
            cs.transform(m)
        }
        PDPageContentStream(doc, page, PDPageContentStream.AppendMode.APPEND, true).use { it.restoreGraphicsState() }
        (page.cosObject.getDictionaryObject(COSName.CONTENTS) as? COSArray)?.isNeedToBeUpdated = true
        return listOf(page.cosObject)
    }

    /** Recorta a página (pdfRect em coordenadas do PDF). */
    fun crop(doc: PDDocument, pageIndex: Int, l: Float, b: Float, r: Float, t: Float) {
        val page = doc.getPage(pageIndex)
        val mb = page.mediaBox
        val x0 = maxOf(minOf(l, r), mb.lowerLeftX); val x1 = minOf(maxOf(l, r), mb.upperRightX)
        val y0 = maxOf(minOf(b, t), mb.lowerLeftY); val y1 = minOf(maxOf(b, t), mb.upperRightY)
        if (x1 - x0 < 20 || y1 - y0 < 20) return
        page.cropBox = PDRectangle(x0, y0, x1 - x0, y1 - y0)
    }

    /** Salva as imagens embutidas na galeria (JPEG original quando possível). Devolve quantas. */
    fun extractImages(ctx: Context, src: File, password: String?, base: String): Int {
        var n = 0
        val seen = HashSet<COSBase>()
        PDDocument.load(src, password ?: "").use { doc ->
            fun walk(res: PDResources?, pageNo: Int, depth: Int) {
                if (res == null || depth > 6) return
                for (name in res.xObjectNames) {
                    val cos = res.cosObject.getCOSDictionary(COSName.XOBJECT)?.getItem(name)
                    val key = (cos as? COSObject)?.`object` ?: cos ?: continue
                    if (!seen.add(key)) continue
                    val xo = runCatching { res.getXObject(name) }.getOrNull() ?: continue
                    when (xo) {
                        is PDFormXObject -> walk(xo.resources, pageNo, depth + 1)
                        is PDImageXObject -> {
                            if (xo.width < 16 || xo.height < 16) continue
                            val jpeg = xo.cosObject.getDictionaryObject(COSName.FILTER).let {
                                it == COSName.DCT_DECODE || (it as? COSArray)?.let { a -> a.size() == 1 && a.getObject(0) == COSName.DCT_DECODE } == true
                            } && xo.colorSpace?.numberOfComponents != 4
                            n++
                            val fname = "%s_pag%03d_%d.%s".format(base, pageNo + 1, n, if (jpeg) "jpg" else "png")
                            val values = ContentValues().apply {
                                put(MediaStore.Images.Media.DISPLAY_NAME, fname)
                                put(MediaStore.Images.Media.MIME_TYPE, if (jpeg) "image/jpeg" else "image/png")
                                if (Build.VERSION.SDK_INT >= 29) put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/Dispersio PDF")
                            }
                            val uri = ctx.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: continue
                            ctx.contentResolver.openOutputStream(uri)?.use { o ->
                                if (jpeg) xo.cosObject.createRawInputStream().use { it.copyTo(o) }
                                else xo.image.compress(Bitmap.CompressFormat.PNG, 100, o)
                            }
                        }
                    }
                }
            }
            for (i in 0 until doc.numberOfPages) walk(doc.getPage(i).resources, i, 0)
        }
        return n
    }
}

/** PDF/A-2b (arquivamento de longo prazo). Mesmas regras do Dispersio PDF do computador. */
object PdfA {
    private val families = listOf(
        listOf("courier", "mono", "consolas") to "LiberationMono",
        listOf("calibri", "carlito") to "Carlito",
        listOf("times", "georgia", "garamond", "cambria", "serif", "roman", "bookman", "palatino") to "LiberationSerif",
        listOf("helvetica", "arial", "verdana", "tahoma", "sans", "segoe") to "LiberationSans",
    )

    private fun substitute(baseFont: String): String? {
        val n = baseFont.substringAfter('+').lowercase()
        if (listOf("symbol", "dingbat", "wingding").any { it in n }) return null
        val fam = families.firstOrNull { (keys, _) -> keys.any { it in n } }?.second ?: "LiberationSans"
        val bold = listOf("bold", "black", "heavy", "semibold", "demi").any { it in n }
        val italic = "italic" in n || "oblique" in n
        val style = when { bold && italic -> "BoldItalic"; bold -> "Bold"; italic -> "Italic"; else -> "Regular" }
        return "fontes/$fam-$style.ttf"
    }

    private fun cp1252(code: Int): Char? = runCatching {
        val s = String(byteArrayOf(code.toByte()), charset("windows-1252"))
        s.singleOrNull()?.takeIf { it != '�' }
    }.getOrNull()

    /** Todas as fontes (diretas e indiretas) alcançáveis a partir do catálogo. */
    private fun fonts(doc: PDDocument): List<COSDictionary> {
        val out = ArrayList<COSDictionary>()
        val seen = java.util.IdentityHashMap<COSBase, Boolean>()
        val stack = ArrayDeque<COSBase>()
        stack.add(doc.document.trailer)
        while (stack.isNotEmpty()) {
            var b = stack.removeLast()
            if (b is COSObject) b = b.`object` ?: continue
            if (seen.put(b, true) != null) continue
            when (b) {
                is COSDictionary -> {
                    if (b.getCOSName(COSName.TYPE) == COSName.FONT) out += b
                    for (k in b.keySet()) {
                        if (k == COSName.PARENT || k == COSName.P) continue
                        b.getItem(k)?.let { stack.add(it) }
                    }
                }
                is COSArray -> for (i in 0 until b.size()) b.get(i)?.let { stack.add(it) }
            }
        }
        return out
    }

    private fun embedded(fd: COSDictionary?) = fd != null &&
        (fd.containsKey(COSName.FONT_FILE) || fd.containsKey(COSName.FONT_FILE2) || fd.containsKey(COSName.FONT_FILE3))

    private fun embed(ctx: Context, doc: PDDocument, f: COSDictionary, problems: MutableList<String>) {
        val sub = f.getCOSName(COSName.SUBTYPE)
        val base = f.getNameAsString(COSName.BASE_FONT) ?: "?"
        if (sub != COSName.TYPE1 && sub != COSName.TRUE_TYPE && sub != COSName.MM_TYPE1) {
            problems += "fonte “$base” não está no arquivo e não pôde ser embutida"; return
        }
        val path = substitute(base) ?: run { problems += "fonte de símbolos “$base” não está no arquivo e não tem equivalente"; return }
        val data = ctx.assets.open(path).use { it.readBytes() }
        val ttf = com.tom_roush.fontbox.ttf.TTFParser().parse(java.io.ByteArrayInputStream(data))
        val upm = ttf.header.unitsPerEm.toFloat()
        val enc = f.getDictionaryObject(COSName.ENCODING)
        if (enc == null || enc == COSName.STANDARD_ENCODING) f.setItem(COSName.ENCODING, COSName.WIN_ANSI_ENCODING)
        if (!f.containsKey(COSName.WIDTHS)) {
            val cmap = ttf.unicodeCmapLookup
            val ws = COSArray()
            for (c in 32..255) {
                val ch = cp1252(c)
                val gid = if (ch != null) cmap.getGlyphId(ch.code) else 0
                ws.add(COSInteger.get(if (gid > 0) Math.round(ttf.getAdvanceWidth(gid) * 1000f / upm).toLong() else 0L))
            }
            f.setInt(COSName.FIRST_CHAR, 32); f.setInt(COSName.LAST_CHAR, 255)
            f.setItem(COSName.WIDTHS, ws)
        }
        val ff: COSStream = doc.document.createCOSStream()
        ff.createOutputStream(COSName.FLATE_DECODE).use { it.write(data) }
        ff.setInt(COSName.LENGTH1, data.size)
        var fd = f.getCOSDictionary(COSName.FONT_DESC)
        if (fd == null) {
            val bb = ttf.header
            fd = COSDictionary().apply {
                setItem(COSName.TYPE, COSName.FONT_DESC)
                setName(COSName.FONT_NAME, base.substringAfter('+'))
                setInt(COSName.FLAGS, 32)
                setItem(COSName.FONT_BBOX, COSArray().apply {
                    listOf(bb.xMin, bb.yMin, bb.xMax, bb.yMax).forEach { add(COSInteger.get(Math.round(it * 1000f / upm).toLong())) }
                })
                setInt(COSName.ITALIC_ANGLE, 0)
                setInt(COSName.ASCENT, Math.round(ttf.horizontalHeader.ascender * 1000f / upm))
                setInt(COSName.DESCENT, Math.round(ttf.horizontalHeader.descender * 1000f / upm))
                setInt(COSName.CAP_HEIGHT, 700); setInt(COSName.STEM_V, 80)
            }
            f.setItem(COSName.FONT_DESC, fd)
        }
        fd.removeItem(COSName.FONT_FILE); fd.removeItem(COSName.FONT_FILE3)
        fd.setItem(COSName.FONT_FILE2, ff)
        fd.setInt(COSName.FLAGS, (fd.getInt(COSName.FLAGS, 32) and 4.inv()) or 32)
        f.setItem(COSName.SUBTYPE, COSName.TRUE_TYPE)
    }

    private fun iso(c: Calendar): String {
        val f = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", java.util.Locale.US)
        f.timeZone = c.timeZone
        return f.format(c.time)
    }

    private fun esc(s: String) = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    /** Converte src em PDF/A-2b gravado em dst. Devolve os avisos (lista vazia = tudo certo). */
    fun convert(ctx: Context, src: File, password: String?, dst: File, title: String): List<String> {
        val problems = ArrayList<String>()
        PDDocument.load(src, password ?: "").use { doc ->
            if (doc.isEncrypted) doc.isAllSecurityToBeRemoved = true
            val cat = doc.documentCatalog
            val names = cat.cosObject.getCOSDictionary(COSName.NAMES)
            if (names?.containsKey(COSName.EMBEDDED_FILES) == true) {
                names.removeItem(COSName.EMBEDDED_FILES)
                problems += "os arquivos anexados foram removidos (não são permitidos no PDF/A-2b)"
            }
            names?.removeItem(COSName.JAVA_SCRIPT)
            cat.cosObject.removeItem(COSName.AA)
            (cat.cosObject.getDictionaryObject(COSName.OPEN_ACTION) as? COSDictionary)?.let {
                if (it.getCOSName(COSName.S) == COSName.JAVA_SCRIPT) cat.cosObject.removeItem(COSName.OPEN_ACTION)
            }
            cat.acroForm?.let { af ->
                runCatching { if (af.needAppearances) af.refreshAppearances() }
                af.cosObject.removeItem(COSName.NEED_APPEARANCES)
            }
            // comentários: com aparência e marcados para impressão
            for (page in doc.pages) for (a in page.annotations) {
                runCatching {
                    a.isPrinted = true; a.isHidden = false; a.isInvisible = false; a.isNoView = false
                    if (a.appearance == null && a.subtype != "Popup" && a.subtype != "Link") a.constructAppearances(doc)
                }
            }
            // fontes
            for (f in fonts(doc)) {
                val sub = f.getCOSName(COSName.SUBTYPE)
                if (sub == COSName.CID_FONT_TYPE2 && !f.containsKey(COSName.CID_TO_GID_MAP)) f.setItem(COSName.CID_TO_GID_MAP, COSName.IDENTITY)
                if (sub == COSName.TYPE0 || sub == COSName.TYPE3 || sub == COSName.CID_FONT_TYPE0 || sub == COSName.CID_FONT_TYPE2) continue
                if (!embedded(f.getCOSDictionary(COSName.FONT_DESC))) embed(ctx, doc, f, problems)
            }
            // LZW não é permitido: regrava em Flate
            for (o in doc.document.objects) {
                val s = o.`object` as? COSStream ?: continue
                val filter = s.getDictionaryObject(COSName.FILTER)
                val lzw = filter == COSName.LZW_DECODE || (filter as? COSArray)?.any { it == COSName.LZW_DECODE } == true
                if (lzw) {
                    val data = s.createInputStream().use { it.readBytes() }
                    s.removeItem(COSName.DECODE_PARMS)
                    s.createOutputStream(COSName.FLATE_DECODE).use { it.write(data) }
                }
            }
            // intenção de saída sRGB + metadados
            val oi = ctx.assets.open("pdfa/sRGB.icc").use { PDOutputIntent(doc, it) }
            oi.info = "sRGB IEC61966-2.1"; oi.outputCondition = "sRGB IEC61966-2.1"
            oi.outputConditionIdentifier = "sRGB IEC61966-2.1"; oi.registryName = "http://www.color.org"
            cat.cosObject.removeItem(COSName.getPDFName("OutputIntents"))
            cat.addOutputIntent(oi)
            val now = Calendar.getInstance()
            now.set(Calendar.MILLISECOND, 0)
            val info = doc.documentInformation
            val author = info.author.orEmpty()
            info.title = title.ifBlank { null }
            info.author = author.ifBlank { null }
            info.subject = null; info.keywords = null; info.trapped = null
            info.creator = "Dispersio PDF"; info.producer = "Dispersio PDF"
            info.creationDate = now; info.modificationDate = now
            val d = iso(now)
            val xmp = buildString {
                append("<?xpacket begin=\"﻿\" id=\"W5M0MpCehiHzreSzNTczkc9d\"?>\n<x:xmpmeta xmlns:x=\"adobe:ns:meta/\">\n")
                append(" <rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\">\n  <rdf:Description rdf:about=\"\"")
                append(" xmlns:pdfaid=\"http://www.aiim.org/pdfa/ns/id/\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\"")
                append(" xmlns:xmp=\"http://ns.adobe.com/xap/1.0/\" xmlns:pdf=\"http://ns.adobe.com/pdf/1.3/\" xmlns:xmpMM=\"http://ns.adobe.com/xap/1.0/mm/\">\n")
                append("   <pdfaid:part>2</pdfaid:part>\n   <pdfaid:conformance>B</pdfaid:conformance>\n   <dc:format>application/pdf</dc:format>\n")
                if (title.isNotBlank()) append("   <dc:title><rdf:Alt><rdf:li xml:lang=\"x-default\">${esc(title)}</rdf:li></rdf:Alt></dc:title>\n")
                if (author.isNotBlank()) append("   <dc:creator><rdf:Seq><rdf:li>${esc(author)}</rdf:li></rdf:Seq></dc:creator>\n")
                append("   <xmp:CreateDate>$d</xmp:CreateDate>\n   <xmp:ModifyDate>$d</xmp:ModifyDate>\n   <xmp:MetadataDate>$d</xmp:MetadataDate>\n")
                append("   <xmp:CreatorTool>Dispersio PDF</xmp:CreatorTool>\n   <pdf:Producer>Dispersio PDF</pdf:Producer>\n")
                append("   <xmpMM:DocumentID>uuid:${UUID.randomUUID()}</xmpMM:DocumentID>\n")
                append("  </rdf:Description>\n </rdf:RDF>\n</x:xmpmeta>\n<?xpacket end=\"w\"?>")
            }
            val md = PDMetadata(doc)
            md.importXMPMetadata(xmp.toByteArray(Charsets.UTF_8))
            cat.metadata = md
            Editor.subsetFonts(doc)
            if (doc.version < 1.7f) doc.version = 1.7f
            dst.outputStream().buffered().use { doc.save(it) }
        }
        return problems
    }
}

/** Páginas de lado ou de cabeça para baixo: descobre a rotação certa (texto digital pela direção das letras; digitalizada por OCR). */
object Orientation {
    private val recognizer by lazy {
        com.google.mlkit.vision.text.TextRecognition.getClient(com.google.mlkit.vision.text.latin.TextRecognizerOptions.DEFAULT_OPTIONS)
    }
    private val WORD = Regex("^[A-Za-zÀ-ÿ]{4,}$")

    fun goodWords(text: String) = text.split(Regex("\\s+")).count { w ->
        val t = w.trim('.', ',', ';', ':', '(', ')', '"', '\'', '-')
        WORD.matches(t) && t.lowercase().any { it in "aeiouáéíóúâêôãõ" }
    }

    /** Quanto girar (horário) a página como está exibida, pela direção das letras; null se não há texto suficiente. */
    fun textTurn(pc: PageChars): Int? {
        val votes = IntArray(4)
        var total = 0
        for (k in 0 until pc.size - 1) {
            val a = pc.frac[k] ?: continue
            val b = pc.frac[k + 1] ?: continue
            if (pc.text[k].isWhitespace() || pc.text[k + 1].isWhitespace()) continue
            val dx = (b.l + b.r - a.l - a.r) / 2; val dy = (b.t + b.b - a.t - a.b) / 2
            if (abs(dx) + abs(dy) > 0.06f || abs(dx) + abs(dy) < 1e-5f) continue      // quebra de linha
            val v = when {
                abs(dx) > 2 * abs(dy) -> if (dx > 0) 0 else 2
                abs(dy) > 2 * abs(dx) -> if (dy < 0) 1 else 3   // subindo: girar 90° horário; descendo: 270°
                else -> continue
            }
            votes[v]++; total++
        }
        if (total < 40) return null
        val best = votes.indices.maxBy { votes[it] }
        return if (votes[best] >= total * 0.7) best * 90 else null
    }

    private fun inkProfileHorizontal(bmp: Bitmap): Boolean? {
        val w = bmp.width; val h = bmp.height
        val px = IntArray(w * h); bmp.getPixels(px, 0, w, 0, 0, w, h)
        val g = IntArray(px.size) { val c = px[it]; (((c shr 16) and 0xFF) * 299 + ((c shr 8) and 0xFF) * 587 + (c and 0xFF) * 114) / 1000 }
        val hist = IntArray(256); g.forEach { hist[it]++ }
        var acc = 0L; var p92 = 255
        for (i in 0..255) { acc += hist[i]; if (acc >= g.size * 0.92) { p92 = i; break } }
        val thr = p92 - 70
        val rows = DoubleArray(h); val cols = DoubleArray(w); var ink = 0
        for (y in 0 until h) for (x in 0 until w) if (g[y * w + x] < thr) { rows[y]++; cols[x]++; ink++ }
        if (ink < g.size * 0.004) return null
        fun v(a: DoubleArray, n: Int): Double { val m = a.average(); return a.sumOf { (it - m) * (it - m) } / a.size / (n.toDouble() * n) }
        return v(rows, w) >= v(cols, h)
    }

    private fun ocrScore(bmp: Bitmap, turn: Int): Int {
        val m = android.graphics.Matrix().apply { postRotate(turn.toFloat()) }
        val r = Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, m, true)
        val crop = Bitmap.createBitmap(r, (r.width * 0.08).toInt(), (r.height * 0.15).toInt(), (r.width * 0.84).toInt(), (r.height * 0.45).toInt())
        return try {
            goodWords(com.google.android.gms.tasks.Tasks.await(recognizer.process(com.google.mlkit.vision.common.InputImage.fromBitmap(crop, 0))).text)
        } finally {
            if (r !== bmp) r.recycle()
            crop.recycle()
        }
    }

    /** Quanto girar (horário) uma página digitalizada; null se não tiver certeza. */
    suspend fun scanTurn(engine: PdfEngine, pdf: OpenPdf, page: Int): Int? {
        val bmp = engine.renderFresh(pdf, page, 1000)
        try {
            val horiz = inkProfileHorizontal(bmp) ?: return null
            val cands = if (horiz) listOf(0, 180) else listOf(90, 270)
            val scores = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Default) { cands.associateWith { ocrScore(bmp, it) } }
            val best = scores.maxBy { it.value }
            val other = scores.values.min()
            if (best.value < 6 || best.value < 2 * other + 3) return null
            return best.key
        } finally {
            bmp.recycle()
        }
    }

    /** Rotação (absoluta) que deixa o texto digital de pé, pela direção das letras no PDF (0, 90, 180, 270); null sem texto. */
    fun textRotation(doc: PDDocument, page: Int): Int? {
        val votes = IntArray(4)
        var total = 0
        val st = object : com.tom_roush.pdfbox.text.PDFTextStripper() {
            override fun processTextPosition(t: com.tom_roush.pdfbox.text.TextPosition) {
                if (t.unicode.isNullOrBlank()) return
                val k = ((Math.round(t.dir / 90f) % 4) + 4) % 4
                votes[k]++; total++
            }
        }
        st.startPage = page + 1; st.endPage = page + 1
        runCatching { st.getText(doc) }
        if (total < 40) return null
        val best = votes.indices.maxBy { votes[it] }
        return if (votes[best] >= total * 0.7) best * 90 else null
    }

    /** {página: rotação nova (graus)} para as páginas que estão de lado ou de cabeça para baixo.
     *  textRot: rotação certa pela camada de texto (PDFBox), quando houver. */
    suspend fun fixes(engine: PdfEngine, pdf: OpenPdf, pages: Iterable<Int>, onPage: (Int) -> Unit = {},
                      textRot: suspend (Int) -> Int? = { null }): Map<Int, Int> {
        val out = LinkedHashMap<Int, Int>()
        for (p in pages) {
            kotlinx.coroutines.yield()
            onPage(p)
            val pc = engine.pageChars(pdf, p)
            val cur = engine.pageRotation(pdf, p)
            val textChars = pc.text.count { !it.isWhitespace() && it != '\u0000' }
            if (textChars > 15) {
                val r = runCatching { textRot(p) }.getOrNull()
                if (r != null) { if (r != cur) out[p] = r; continue }
                val turn = textTurn(pc)
                if (turn != null && turn != 0) out[p] = (cur + turn) % 360
            } else {
                val turn = runCatching { scanTurn(engine, pdf, p) }.getOrNull()
                if (turn != null && turn != 0) out[p] = (cur + turn) % 360
            }
        }
        return out
    }
}
