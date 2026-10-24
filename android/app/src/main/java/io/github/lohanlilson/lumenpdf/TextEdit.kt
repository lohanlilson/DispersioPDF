package io.github.lohanlilson.lumenpdf

import android.content.res.AssetManager
import android.graphics.RectF
import com.tom_roush.pdfbox.contentstream.operator.Operator
import com.tom_roush.pdfbox.contentstream.operator.color.SetNonStrokingColor
import com.tom_roush.pdfbox.contentstream.operator.color.SetNonStrokingColorN
import com.tom_roush.pdfbox.contentstream.operator.color.SetNonStrokingColorSpace
import com.tom_roush.pdfbox.contentstream.operator.color.SetNonStrokingDeviceCMYKColor
import com.tom_roush.pdfbox.contentstream.operator.color.SetNonStrokingDeviceGrayColor
import com.tom_roush.pdfbox.contentstream.operator.color.SetNonStrokingDeviceRGBColor
import com.tom_roush.pdfbox.contentstream.operator.color.SetStrokingColor
import com.tom_roush.pdfbox.contentstream.operator.color.SetStrokingColorN
import com.tom_roush.pdfbox.contentstream.operator.color.SetStrokingColorSpace
import com.tom_roush.pdfbox.contentstream.operator.color.SetStrokingDeviceCMYKColor
import com.tom_roush.pdfbox.contentstream.operator.color.SetStrokingDeviceGrayColor
import com.tom_roush.pdfbox.contentstream.operator.color.SetStrokingDeviceRGBColor
import com.tom_roush.pdfbox.cos.COSArray
import com.tom_roush.pdfbox.cos.COSBase
import com.tom_roush.pdfbox.cos.COSDictionary
import com.tom_roush.pdfbox.cos.COSFloat
import com.tom_roush.pdfbox.cos.COSName
import com.tom_roush.pdfbox.cos.COSNumber
import com.tom_roush.pdfbox.cos.COSString
import com.tom_roush.pdfbox.pdfparser.PDFStreamParser
import com.tom_roush.pdfbox.pdfwriter.ContentStreamWriter
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPage
import com.tom_roush.pdfbox.pdmodel.common.PDStream
import com.tom_roush.pdfbox.pdmodel.font.PDFont
import com.tom_roush.pdfbox.pdmodel.font.PDType0Font
import com.tom_roush.pdfbox.pdmodel.font.PDType3Font
import com.tom_roush.pdfbox.pdmodel.font.PDVectorFont
import com.tom_roush.pdfbox.pdmodel.graphics.color.PDColor
import com.tom_roush.pdfbox.pdmodel.graphics.color.PDDeviceRGB
import com.tom_roush.pdfbox.pdmodel.graphics.form.PDFormXObject
import com.tom_roush.pdfbox.pdmodel.graphics.form.PDTransparencyGroup
import com.tom_roush.pdfbox.pdmodel.graphics.state.RenderingMode
import com.tom_roush.pdfbox.text.PDFTextStripper
import com.tom_roush.pdfbox.util.Matrix
import com.tom_roush.pdfbox.util.Vector
import java.io.ByteArrayInputStream
import kotlin.math.abs
import kotlin.math.atan2

/** Estilo do trecho de texto que será editado (mostrado na janela e usado para reescrever). */
data class TextStyle(
    val fontName: String, val bold: Boolean, val italic: Boolean, val size: Float, val color: Int,
    val family: String,   // sans | serif | mono | calibri
) {
    val description: String
        get() = buildString {
            append(fontName.substringAfter('+').ifBlank { "fonte" })
            if (bold && !fontName.contains("bold", true)) append(" negrito")
            if (italic && !fontName.contains("italic", true) && !fontName.contains("oblique", true)) append(" itálico")
            append(" · ").append("%.1f".format(size).removeSuffix(",0").removeSuffix(".0")).append(" pt")
        }
}

/** Trecho de mesma fonte/tamanho/cor dentro da linha tocada. */
data class TextRun(val page: Int, val text: String, val rect: RectF, val style: TextStyle)

/**
 * Edição de texto preservando fonte, negrito/itálico, tamanho e cor:
 * 1. localiza os caracteres do trecho tocado (mesmo estilo) e remove-os do conteúdo da página
 *    (o texto antigo some de verdade; o espaço que ocupavam é mantido);
 * 2. escreve o novo texto no mesmo ponto, com a fonte do próprio PDF quando ela tem todas as letras
 *    ou, senão, uma fonte de mesmas medidas (Arial→Liberation Sans, Times→Liberation Serif,
 *    Courier→Liberation Mono, Calibri→Carlito) no mesmo peso e estilo; mesma cor e tamanho.
 */
object TextEdit {
    var assets: AssetManager? = null

    private class Glyph(
        val op: Int, val str: Int, val idx: Int, val font: PDFont, val code: Int, val unicode: String,
        val x: Float, val y: Float, val cx: Float, val cy: Float, val advUser: Float,
        val tfs: Float, val adjust: Float,          // número a usar no TJ para manter o avanço do caractere removido
        val size: Float, val color: Int, val angle: Double, val th: Float, val fakeBold: Boolean,
    ) {
        var styleKey = ""
    }

    /** Lê os caracteres da página com posição, fonte e cor. */
    private class Probe(private val pageIndex: Int) : PDFTextStripper() {
        val glyphs = ArrayList<Glyph>()
        private var depth = 0
        private var op = -1
        private var str = -1
        private var idx = 0

        init {
            listOf(SetStrokingColorSpace(), SetNonStrokingColorSpace(), SetStrokingColor(), SetNonStrokingColor(),
                SetStrokingColorN(), SetNonStrokingColorN(), SetStrokingDeviceGrayColor(), SetNonStrokingDeviceGrayColor(),
                SetStrokingDeviceRGBColor(), SetNonStrokingDeviceRGBColor(), SetStrokingDeviceCMYKColor(),
                SetNonStrokingDeviceCMYKColor()).forEach { addOperator(it) }
            startPage = pageIndex + 1
            endPage = pageIndex + 1
        }

        override fun processOperator(operator: Operator, operands: MutableList<COSBase>) {
            if (depth == 0) {
                op++
                str = -1
            }
            super.processOperator(operator, operands)
        }

        override fun showForm(form: PDFormXObject) {
            depth++
            try { super.showForm(form) } finally { depth-- }
        }

        override fun showTransparencyGroup(form: PDTransparencyGroup) {
            depth++
            try { super.showTransparencyGroup(form) } finally { depth-- }
        }

        override fun showText(string: ByteArray) {
            if (depth == 0) {
                str++
                idx = 0
            }
            super.showText(string)
        }

        override fun showGlyph(trm: Matrix, font: PDFont, code: Int, unicode: String?, displacement: Vector) {
            super.showGlyph(trm, font, code, unicode, displacement)
            if (depth != 0) return
            val gs = graphicsState
            val ts = gs.textState
            val tfs = ts.fontSize
            val wordSp = if (code == 32 && font !is PDType0Font) ts.wordSpacing else 0f
            val adv = displacement.x * tfs + ts.characterSpacing + wordSp
            val a = trm.getValue(0, 0); val b = trm.getValue(0, 1); val c = trm.getValue(1, 0); val d = trm.getValue(1, 1)
            val u = displacement.x / 2; val v = 0.3f
            val mode = ts.renderingMode
            val color = runCatching {
                (if (mode == RenderingMode.STROKE) gs.strokingColor else gs.nonStrokingColor).toRGB()
            }.getOrDefault(0)
            glyphs += Glyph(op, str, idx++, font, code, unicode ?: "",
                trm.translateX, trm.translateY, a * u + c * v + trm.translateX, b * u + d * v + trm.translateY,
                displacement.x * trm.scalingFactorX, tfs, if (tfs != 0f) -adv * 1000f / tfs else 0f,
                trm.scalingFactorY, color, atan2(b.toDouble(), a.toDouble()), ts.horizontalScaling / 100f,
                mode == RenderingMode.FILL_STROKE)
        }

        fun run(doc: PDDocument): List<Glyph> {
            getText(doc)
            return glyphs
        }
    }

    private fun boldOf(f: PDFont, g: Glyph): Boolean {
        val n = f.name?.lowercase() ?: ""
        val fd = f.fontDescriptor
        return g.fakeBold || listOf("bold", "black", "heavy", "semibold", "demi").any { it in n } ||
            fd?.isForceBold == true || (fd?.fontWeight ?: 0f) >= 600f
    }

    private fun italicOf(f: PDFont): Boolean {
        val n = f.name?.lowercase() ?: ""
        val fd = f.fontDescriptor
        return "italic" in n || "oblique" in n || fd?.isItalic == true || abs(fd?.italicAngle ?: 0f) > 3f
    }

    private fun familyOf(f: PDFont): String {
        val n = f.name?.lowercase()?.substringAfter('+') ?: ""
        val fd = f.fontDescriptor
        return when {
            listOf("courier", "mono", "consol", "lucidaconsole").any { it in n } || fd?.isFixedPitch == true -> "mono"
            "calibri" in n || "carlito" in n -> "calibri"
            "sans" !in n && (listOf("times", "georgia", "garamond", "cambria", "book", "serif", "roman", "palatino", "minion").any { it in n } ||
                fd?.isSerif == true) -> "serif"
            else -> "sans"
        }
    }

    private fun styleOf(g: Glyph) = TextStyle(g.font.name ?: "", boldOf(g.font, g), italicOf(g.font), g.size, g.color, familyOf(g.font))

    private fun key(g: Glyph) = "${g.font.name}|${boldOf(g.font, g)}|${(g.size * 2).toInt()}|${g.color}"

    private fun inside(r: RectF, g: Glyph): Boolean {
        val l = minOf(r.left, r.right) - 1; val rr = maxOf(r.left, r.right) + 1
        val b = minOf(r.top, r.bottom) - 1; val t = maxOf(r.top, r.bottom) + 1
        return g.cx in l..rr && g.cy in b..t
    }

    /** Caracteres do trecho tocado: mesma linha (lineRect), mesmo estilo e contíguos ao ponto (px, py). */
    private fun runGlyphs(all: List<Glyph>, lineRect: RectF, px: Float, py: Float): List<Glyph> {
        val found = all.filter { inside(lineRect, it) }
        if (found.isEmpty()) return emptyList()
        // ordem visual na linha (o arquivo pode desenhar os trechos fora de ordem)
        val ang = found.first().angle
        val dx = kotlin.math.cos(ang).toFloat(); val dy = kotlin.math.sin(ang).toFloat()
        val line = found.sortedBy { it.x * dx + it.y * dy }
        line.forEach { it.styleKey = key(it) }
        // espaços herdam o estilo do vizinho (muitos PDFs desenham espaços com outra fonte)
        for (i in line.indices) if (line[i].unicode.isBlank() && i > 0) line[i].styleKey = line[i - 1].styleKey
        val tapped = line.minByOrNull { g ->
            val dx = when { px < g.x -> g.x - px; px > g.x + g.advUser -> px - g.x - g.advUser; else -> 0f }
            dx + abs(g.cy - py) * 0.2f
        }!!
        val i0 = line.indexOf(tapped)
        var a = i0
        while (a > 0 && line[a - 1].styleKey == tapped.styleKey) a--
        var e = i0
        while (e < line.size - 1 && line[e + 1].styleKey == tapped.styleKey) e++
        // não começa nem termina com espaço
        while (a < e && line[a].unicode.isBlank()) a++
        while (e > a && line[e].unicode.isBlank()) e--
        return line.subList(a, e + 1)
    }

    private fun rectOf(gs: List<Glyph>): RectF {
        val h = gs.maxOf { it.size }
        val l = gs.minOf { it.x }
        val r = gs.maxOf { it.x + it.advUser }
        val base = gs.minOf { it.y }
        return RectF(l, base + h * 0.95f, r, base - h * 0.25f)
    }

    /** Trecho sob o dedo, com o estilo detectado. lineRect/px/py em coordenadas do PDF. */
    fun analyze(doc: PDDocument, pageIndex: Int, lineRect: RectF, px: Float, py: Float): TextRun? {
        val gs = runGlyphs(Probe(pageIndex).run(doc), lineRect, px, py)
        if (gs.isEmpty()) return null
        return TextRun(pageIndex, gs.joinToString("") { it.unicode }, rectOf(gs), styleOf(gs.maxByOrNull { it.size }!!))
    }

    // ------------------------------------------------------------ remover do conteúdo

    /** Reescreve o conteúdo da página sem os caracteres indicados (mantém o avanço deles). */
    private fun removeGlyphs(doc: PDDocument, page: PDPage, remove: List<Glyph>): List<COSDictionary> {
        val byOp = remove.groupBy { it.op }
        val parser = PDFStreamParser(page)
        parser.parse()
        val tokens = parser.tokens
        val out = ArrayList<Any>(tokens.size + 16)
        val operands = ArrayList<Any>()
        var op = -1
        for (t in tokens) {
            if (t !is Operator) {
                operands += t
                continue
            }
            op++
            val rm = byOp[op]
            if (rm == null) {
                out.addAll(operands); out.add(t); operands.clear(); continue
            }
            val font = rm.first().font
            val strs = rm.groupBy { it.str }
            fun rewrite(s: COSString, k: Int, arr: COSArray) {
                val gl = strs[k]?.associateBy { it.idx }
                if (gl == null) { arr.add(s); return }
                val bytes = s.bytes
                val inp = ByteArrayInputStream(bytes)
                var pos = 0
                var i = 0
                var chunk = java.io.ByteArrayOutputStream()
                fun flush() {
                    if (chunk.size() > 0) arr.add(COSString(chunk.toByteArray()))
                    chunk = java.io.ByteArrayOutputStream()
                }
                while (inp.available() > 0) {
                    font.readCode(inp)
                    val end = bytes.size - inp.available()
                    val g = gl[i]
                    if (g == null) chunk.write(bytes, pos, end - pos)
                    else { flush(); arr.add(COSFloat(g.adjust)) }
                    pos = end
                    i++
                }
                flush()
            }
            val arr = COSArray()
            when (t.name) {
                "Tj" -> (operands.lastOrNull() as? COSString)?.let { rewrite(it, 0, arr) }
                "'", "\"" -> (operands.lastOrNull() as? COSString)?.let { rewrite(it, 0, arr) }
                "TJ" -> {
                    var k = 0
                    (operands.lastOrNull() as? COSArray)?.forEach { el ->
                        when (el) {
                            is COSString -> rewrite(el, k++, arr)
                            else -> arr.add(el)
                        }
                    }
                }
                else -> { out.addAll(operands); out.add(t); operands.clear(); continue }
            }
            when (t.name) {
                "'" -> out.add(Operator.getOperator("T*"))
                "\"" -> {
                    (operands.getOrNull(0) as? COSNumber)?.let { out.add(it); out.add(Operator.getOperator("Tw")) }
                    (operands.getOrNull(1) as? COSNumber)?.let { out.add(it); out.add(Operator.getOperator("Tc")) }
                    out.add(Operator.getOperator("T*"))
                }
            }
            out.add(arr)
            out.add(Operator.getOperator("TJ"))
            operands.clear()
        }
        out.addAll(operands)
        val stream = PDStream(doc)
        stream.createOutputStream(COSName.FLATE_DECODE).use { ContentStreamWriter(it).writeTokens(out) }
        page.setContents(stream)
        stream.cosObject.isNeedToBeUpdated = true
        return listOf(page.cosObject, stream.cosObject)
    }

    // ------------------------------------------------------------ fonte para o novo texto

    private fun fits(f: PDFont, text: String): Boolean {
        if (f is PDType3Font) return false
        return runCatching {
            text.codePoints().toArray().all { cp ->
                val s = String(Character.toChars(cp))
                if (s.isBlank()) return@all true
                val bytes = f.encode(s)
                val code = f.readCode(ByteArrayInputStream(bytes))
                (f as? PDVectorFont)?.hasGlyph(code) ?: true
            }
        }.getOrDefault(false)
    }

    private val fileOf = mapOf(
        "sans" to "LiberationSans", "serif" to "LiberationSerif", "mono" to "LiberationMono", "calibri" to "Carlito",
    )

    fun fallbackFile(style: TextStyle): String {
        val base = fileOf[style.family] ?: "LiberationSans"
        val v = when {
            style.bold && style.italic -> "BoldItalic"
            style.bold -> "Bold"
            style.italic -> "Italic"
            else -> "Regular"
        }
        return "fontes/$base-$v.ttf"
    }

    /** (fonte, descrição) para escrever [text] com a aparência de [g]. */
    private fun fontFor(doc: PDDocument, g: Glyph, style: TextStyle, text: String): Pair<PDFont, String> {
        if (fits(g.font, text)) return g.font to "fonte original do PDF"
        val am = assets ?: error("fontes indisponíveis")
        val path = fallbackFile(style)
        val f = am.open(path).use { PDType0Font.load(doc, it, true) }
        return f to path.substringAfter('/').removeSuffix(".ttf")
    }

    /** Resultado: objetos alterados (gravação incremental) e a fonte usada. */
    class Result(val changed: List<COSDictionary>, val fontUsed: String, val run: TextRun?)

    /**
     * Troca o trecho tocado por [text]. Devolve null se não achou o texto pelo PDFBox
     * (o chamador usa o método antigo, que cobre com retângulo).
     */
    fun replace(doc: PDDocument, pageIndex: Int, lineRect: RectF, px: Float, py: Float, text: String): Result? {
        val page = doc.getPage(pageIndex)
        val gs = runGlyphs(Probe(pageIndex).run(doc), lineRect, px, py)
        if (gs.isEmpty() || gs.any { it.font.isVertical }) return null
        val first = gs.first()
        val style = styleOf(gs.maxByOrNull { it.size }!!)
        val run = TextRun(pageIndex, gs.joinToString("") { it.unicode }, rectOf(gs), style)
        val changed = ArrayList(removeGlyphs(doc, page, gs))
        var used = "—"
        if (text.isNotEmpty()) {
            val (font, desc) = fontFor(doc, first, style, text)
            used = desc
            com.tom_roush.pdfbox.pdmodel.PDPageContentStream(doc, page,
                com.tom_roush.pdfbox.pdmodel.PDPageContentStream.AppendMode.APPEND, true, true).use { cs ->
                cs.beginText()
                val rgb = style.color
                cs.setNonStrokingColor(PDColor(floatArrayOf(((rgb shr 16) and 0xFF) / 255f, ((rgb shr 8) and 0xFF) / 255f, (rgb and 0xFF) / 255f),
                    PDDeviceRGB.INSTANCE))
                cs.setFont(font, first.size)
                if (abs(first.th - 1f) > 0.01f) cs.setHorizontalScaling(first.th * 100f)
                cs.setTextMatrix(Matrix.getRotateInstance(first.angle, first.x, first.y))
                cs.showText(text)
                cs.endText()
            }
            changed += page.cosObject
            (page.cosObject.getDictionaryObject(COSName.CONTENTS) as? COSArray)?.let { it.isNeedToBeUpdated = true }
            page.cosObject.getDictionaryObject(COSName.RESOURCES)?.let { (it as? COSDictionary)?.let { r -> changed += r; r.isNeedToBeUpdated = true
                (r.getDictionaryObject(COSName.FONT) as? COSDictionary)?.isNeedToBeUpdated = true } }
        }
        return Result(changed, used, run)
    }
}
