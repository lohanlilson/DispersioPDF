package io.github.lohanlilson.lumenpdf

import android.graphics.Path
import android.graphics.PointF
import android.graphics.RectF
import com.tom_roush.pdfbox.contentstream.PDFGraphicsStreamEngine
import com.tom_roush.pdfbox.cos.COSDictionary
import com.tom_roush.pdfbox.cos.COSName
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPage
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream
import com.tom_roush.pdfbox.pdmodel.PDResources
import com.tom_roush.pdfbox.pdmodel.common.PDRectangle
import com.tom_roush.pdfbox.pdmodel.font.PDType1Font
import com.tom_roush.pdfbox.pdmodel.graphics.image.PDImage
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAppearanceDictionary
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAppearanceEntry
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAppearanceStream
import com.tom_roush.pdfbox.pdmodel.interactive.form.PDAcroForm
import com.tom_roush.pdfbox.pdmodel.interactive.form.PDCheckBox
import com.tom_roush.pdfbox.pdmodel.interactive.form.PDSignatureField
import com.tom_roush.pdfbox.pdmodel.interactive.form.PDTextField
import kotlin.math.abs

/** Campo encontrado: tipo (text | check | signature), área em coordenadas do PDF e rótulo. */
data class Found(val kind: String, val rect: RectF, val label: String)

/** Detecção automática de campos (como no Lumen do computador). */
object FieldDetect {
    private val SIG = Regex("assinatura|cedente|cession[aá]ri|contratante|contratad|testemunha|devedor|credor|avalista|fiador|" +
        "locador|locat[aá]ri|comprador|vendedor|outorgante|outorgad|promitente|signat[aá]ri|respons[aá]vel|representante|" +
        "declarante|requerente|interveniente|anuente|emitente|s[oó]cio", RegexOption.IGNORE_CASE)
    private val FILL = Regex("_{3,}|\\.{6,}|…{2,}")
    private val BOX = Regex("[(\\[]\\s{0,3}[)\\]]|[☐□❑❒▢]")

    private class Line(val text: String, val boxes: List<RectF?>)
    private class Word(val text: String, val r: RectF)

    private fun union(rs: List<RectF?>): RectF? {
        val v = rs.filterNotNull()
        if (v.isEmpty()) return null
        return RectF(v.minOf { it.left }, v.maxOf { it.top }, v.maxOf { it.right }, v.minOf { it.bottom })
    }

    /** Linhas e palavras a partir dos caracteres do PDFium (y cresce para cima; top > bottom). */
    private fun build(chars: List<Pair<Char, RectF?>>): Pair<List<Line>, List<Word>> {
        val lines = ArrayList<Line>()
        val words = ArrayList<Word>()
        var t = StringBuilder(); var b = ArrayList<RectF?>()
        var wt = StringBuilder(); var wb = ArrayList<RectF?>()
        fun flushWord() { union(wb)?.let { if (wt.isNotBlank()) words += Word(wt.toString(), it) }; wt = StringBuilder(); wb = ArrayList() }
        fun flushLine() { flushWord(); if (t.isNotEmpty()) lines += Line(t.toString(), b); t = StringBuilder(); b = ArrayList() }
        var lastMid: Float? = null
        for ((c, r) in chars) {
            if (c == '\n' || c == '\r') { flushLine(); lastMid = null; continue }
            if (r != null) {
                val mid = (r.top + r.bottom) / 2
                if (lastMid != null && abs(mid - lastMid) > abs(r.top - r.bottom).coerceAtLeast(4f)) flushLine()
                lastMid = mid
            }
            t.append(c); b += r
            if (c.isWhitespace()) flushWord() else { wt.append(c); wb += r }
        }
        flushLine()
        return lines to words
    }

    private fun labelLeft(words: List<Word>, r: RectF): String {
        val cy = (r.top + r.bottom) / 2
        val same = words.filter { it.r.right <= r.left + 1 && abs((it.r.top + it.r.bottom) / 2 - cy) < maxOf(8f, abs(r.top - r.bottom)) }
            .sortedBy { it.r.left }
        val lab = ArrayList<String>()
        for (w in same.reversed()) {
            if (lab.isNotEmpty() && FILL.containsMatchIn(w.text)) break
            lab.add(0, w.text)
            if (lab.size >= 5 || (lab.size > 1 && w.text.endsWith(".") )) break
        }
        return FILL.replace(lab.joinToString(" "), "").trim().trimEnd(':', ' ').trim(' ', '.', '_', '-')
    }

    private fun labelRight(words: List<Word>, r: RectF): String {
        val cy = (r.top + r.bottom) / 2
        val nxt = words.filter { it.r.left >= r.right - 1 && abs((it.r.top + it.r.bottom) / 2 - cy) < 8f }.sortedBy { it.r.left }
        val lab = ArrayList<String>()
        var lastX = r.right
        for (w in nxt) {
            if (lab.size >= 5 || w.r.left - lastX > (if (lab.isEmpty()) 40f else 12f) || BOX.containsMatchIn(w.text) || w.text in setOf("(", ")", "[", "]")) break
            lab += w.text; lastX = w.r.right
        }
        return lab.joinToString(" ")
    }

    private fun labelAbove(words: List<Word>, r: RectF): String =
        words.filter { it.r.bottom >= r.top - 1 && it.r.bottom <= r.top + 18 && it.r.left < r.left + (r.right - r.left) / 2 && it.r.right > r.left - 4 }
            .sortedWith(compareBy({ -it.r.top }, { it.r.left })).take(5).joinToString(" ") { it.text }.trimEnd(':', ' ')

    private fun labelBelow(words: List<Word>, r: RectF): String =
        words.filter { it.r.top <= r.bottom + 1 && it.r.top >= r.bottom - 16 && it.r.left < r.right && it.r.right > r.left }
            .sortedWith(compareBy({ -it.r.top }, { it.r.left })).take(6).joinToString(" ") { it.text }

    /** Linhas e caixas desenhadas na página (coordenadas do PDF). */
    private class Shapes(page: PDPage) : PDFGraphicsStreamEngine(page) {
        val lines = ArrayList<RectF>()   // horizontais: left, y, right, y
        val rects = ArrayList<RectF>()
        private var cur = PointF()
        private var start = PointF()
        private val segs = ArrayList<Pair<PointF, PointF>>()
        private val pending = ArrayList<RectF>()

        override fun appendRectangle(p0: PointF, p1: PointF, p2: PointF, p3: PointF) {
            val xs = listOf(p0.x, p1.x, p2.x, p3.x); val ys = listOf(p0.y, p1.y, p2.y, p3.y)
            pending += RectF(xs.min(), ys.max(), xs.max(), ys.min())
        }
        override fun moveTo(x: Float, y: Float) { cur = PointF(x, y); start = cur }
        override fun lineTo(x: Float, y: Float) { segs += cur to PointF(x, y); cur = PointF(x, y) }
        override fun curveTo(x1: Float, y1: Float, x2: Float, y2: Float, x3: Float, y3: Float) { cur = PointF(x3, y3) }
        override fun getCurrentPoint(): PointF = cur
        override fun closePath() { segs += cur to start; cur = start }
        override fun endPath() { segs.clear(); pending.clear() }
        private fun take() {
            for ((a, b) in segs) if (abs(a.y - b.y) < 0.8f && abs(a.x - b.x) >= 36f) lines += RectF(minOf(a.x, b.x), a.y, maxOf(a.x, b.x), a.y)
            for (r in pending) {
                val h = abs(r.top - r.bottom); val w = r.right - r.left
                if (h <= 1.6f && w >= 36f) lines += RectF(r.left, r.bottom, r.right, r.bottom) else rects += r
            }
            segs.clear(); pending.clear()
        }
        override fun strokePath() = take()
        override fun fillPath(windingRule: Path.FillType?) = take()
        override fun fillAndStrokePath(windingRule: Path.FillType?) = take()
        override fun clip(windingRule: Path.FillType?) {}
        override fun drawImage(pdImage: PDImage?) {}
        override fun shadingFill(shadingName: COSName?) {}
        fun run() { processPage(page) }
    }

    fun detect(doc: PDDocument, pageIndex: Int, chars: List<Pair<Char, RectF?>>): List<Found> {
        val page = doc.getPage(pageIndex)
        val (lines, words) = build(chars)
        val found = ArrayList<Found>()
        fun hasText(r: RectF) = words.any { w -> w.r.left < r.right && w.r.right > r.left && w.r.bottom < r.top && w.r.top > r.bottom && !FILL.matches(w.text) }
        fun add(kind: String, r: RectF, label: String) {
            if (r.right - r.left < 4) return
            for (f in found) {
                val ix = minOf(r.right, f.rect.right) - maxOf(r.left, f.rect.left)
                val iy = minOf(r.top, f.rect.top) - maxOf(r.bottom, f.rect.bottom)
                if (ix > 0 && iy > 0 && ix * iy > 0.4f * minOf((r.right - r.left) * (r.top - r.bottom), (f.rect.right - f.rect.left) * (f.rect.top - f.rect.bottom))) return
            }
            found += Found(kind, r, label)
        }
        for (ln in lines) {
            for (m in FILL.findAll(ln.text)) {
                val r = union(ln.boxes.subList(m.range.first, m.range.last + 1)) ?: continue
                val hh = maxOf(abs(r.top - r.bottom) * 1.3f, 11f)
                val below = labelBelow(words, r)
                if (SIG.containsMatchIn(below) && r.right - r.left > 90) add("signature", RectF(r.left, r.bottom + 34, r.right, r.bottom), below)
                else { val fr = RectF(r.left, r.bottom + hh, r.right, r.bottom - 1); add("text", fr, labelLeft(words, fr)) }
            }
            for (m in BOX.findAll(ln.text)) {
                val r = union(ln.boxes.subList(m.range.first, m.range.last + 1)) ?: continue
                val side = maxOf(minOf(abs(r.top - r.bottom), 12f) * 0.8f, 7f)
                val cx = (r.left + r.right) / 2; val cy = (r.top + r.bottom) / 2
                add("check", RectF(cx - side / 2, cy + side / 2, cx + side / 2, cy - side / 2), labelRight(words, r))
            }
        }
        val shapes = Shapes(page).apply { runCatching { run() } }
        val pw = page.cropBox.width
        for (ln in shapes.lines) {
            if (ln.right - ln.left > pw * 0.8f) continue
            if (hasText(RectF(ln.left + 1, ln.top + 13, ln.right - 1, ln.top + 0.8f))) continue
            val below = labelBelow(words, ln)
            if (SIG.containsMatchIn(below) && ln.right - ln.left > 90) add("signature", RectF(ln.left, ln.top + 34, ln.right, ln.top), below)
            else { val fr = RectF(ln.left, ln.top + 14, ln.right, ln.top - 1); add("text", fr, labelLeft(words, fr)) }
        }
        for (r in shapes.rects) {
            val w = r.right - r.left; val h = r.top - r.bottom
            if (w in 5.5f..18f && h in 5.5f..18f && abs(w - h) < 2.5f) add("check", r, labelRight(words, r))
            else if (w >= 40 && h in 12f..60f) {
                val inner = RectF(r.left + 1.5f, r.top - 1.5f, r.right - 1.5f, r.bottom + 1.5f)
                if (!hasText(inner)) add("text", inner, labelLeft(words, r).ifBlank { labelAbove(words, r) })
            }
        }
        val existing = page.annotations.filter { it.subtype == "Widget" }.mapNotNull { it.rectangle }
        return found.filter { f ->
            existing.none { e ->
                val ix = minOf(f.rect.right, e.upperRightX) - maxOf(f.rect.left, e.lowerLeftX)
                val iy = minOf(f.rect.top, e.upperRightY) - maxOf(f.rect.bottom, e.lowerLeftY)
                ix > 0 && iy > 0 && ix * iy > 0.3f * (f.rect.right - f.rect.left) * (f.rect.top - f.rect.bottom)
            }
        }
    }

    private fun checkAppearance(doc: PDDocument, w: Float, h: Float, on: Boolean): PDAppearanceStream {
        val s = PDAppearanceStream(doc)
        s.bBox = PDRectangle(w, h)
        s.resources = PDResources()
        PDPageContentStream(doc, s).use { cs ->
            if (on) {
                cs.setStrokingColor(0.1f, 0.1f, 0.12f)
                cs.setLineWidth(minOf(w, h) * 0.12f)
                cs.setLineCapStyle(1)
                cs.moveTo(w * 0.18f, h * 0.52f); cs.lineTo(w * 0.42f, h * 0.25f); cs.lineTo(w * 0.85f, h * 0.8f)
                cs.stroke()
            }
        }
        return s
    }

    /** Cria os campos encontrados (sem borda e sem fundo). Devolve a contagem por tipo. */
    fun create(doc: PDDocument, found: Map<Int, List<Found>>): Map<String, Int> {
        val form = doc.documentCatalog.acroForm ?: PDAcroForm(doc).also { doc.documentCatalog.acroForm = it }
        if (form.defaultResources == null) form.defaultResources = PDResources()
        form.defaultResources.put(COSName.getPDFName("Helv"), PDType1Font.HELVETICA)
        if (form.defaultAppearance.isNullOrBlank()) form.defaultAppearance = "/Helv 0 Tf 0 g"
        val used = form.fieldTree.map { it.fullyQualifiedName }.toMutableSet()
        fun name(label: String, kind: String, page: Int): String {
            var base = label.replace(Regex("[^\\p{L}\\p{N}\\s/º°ª-]"), "").replace(Regex("\\s+"), " ").trim().take(40)
            if (base.isEmpty()) base = mapOf("text" to "Campo", "check" to "Opção", "signature" to "Assinatura")[kind] + " pág ${page + 1}"
            else if (kind == "signature" && !base.lowercase().startsWith("assinatura")) base = "Assinatura $base"
            var n = base; var k = 2
            while (n in used) n = "$base ${k++}"
            used += n
            return n
        }
        val count = mutableMapOf("text" to 0, "check" to 0, "signature" to 0)
        for ((pi, list) in found) {
            val page = doc.getPage(pi)
            for (f in list) {
                val rect = PDRectangle(f.rect.left, f.rect.bottom, f.rect.right - f.rect.left, f.rect.top - f.rect.bottom)
                val field = when (f.kind) {
                    "check" -> PDCheckBox(form)
                    "signature" -> PDSignatureField(form)
                    else -> PDTextField(form).apply { defaultAppearance = "/Helv 0 Tf 0 g" }
                }
                field.partialName = name(f.label, f.kind, pi)
                if (f.label.isNotBlank()) field.alternateFieldName = f.label
                val widget = field.widgets[0]
                widget.rectangle = rect
                widget.page = page
                widget.isPrinted = true
                if (field is PDCheckBox) {
                    val ap = PDAppearanceDictionary()
                    val normal = COSDictionary()
                    normal.setItem(COSName.getPDFName("Yes"), checkAppearance(doc, rect.width, rect.height, true))
                    normal.setItem(COSName.Off, checkAppearance(doc, rect.width, rect.height, false))
                    ap.setNormalAppearance(PDAppearanceEntry(normal))
                    widget.appearance = ap
                    widget.cosObject.setName(COSName.AS, "Off")
                    field.cosObject.setName(COSName.V, "Off")
                }
                val annots = page.annotations
                annots.add(widget)
                page.annotations = annots
                form.fields.add(field)
                count[f.kind] = (count[f.kind] ?: 0) + 1
            }
        }
        return count
    }
}
