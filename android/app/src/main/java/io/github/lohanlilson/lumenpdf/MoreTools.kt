package io.github.lohanlilson.lumenpdf

import android.graphics.Bitmap
import android.graphics.RectF
import com.tom_roush.pdfbox.contentstream.PDFStreamEngine
import com.tom_roush.pdfbox.contentstream.operator.DrawObject
import com.tom_roush.pdfbox.contentstream.operator.Operator
import com.tom_roush.pdfbox.contentstream.operator.state.Concatenate
import com.tom_roush.pdfbox.contentstream.operator.state.Restore
import com.tom_roush.pdfbox.contentstream.operator.state.Save
import com.tom_roush.pdfbox.contentstream.operator.state.SetGraphicsStateParameters
import com.tom_roush.pdfbox.contentstream.operator.state.SetMatrix
import com.tom_roush.pdfbox.cos.COSArray
import com.tom_roush.pdfbox.cos.COSBase
import com.tom_roush.pdfbox.cos.COSDictionary
import com.tom_roush.pdfbox.cos.COSFloat
import com.tom_roush.pdfbox.cos.COSName
import com.tom_roush.pdfbox.pdfparser.PDFStreamParser
import com.tom_roush.pdfbox.pdfwriter.ContentStreamWriter
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPage
import com.tom_roush.pdfbox.pdmodel.common.PDRectangle
import com.tom_roush.pdfbox.pdmodel.common.PDStream
import com.tom_roush.pdfbox.pdmodel.fdf.FDFAnnotation
import com.tom_roush.pdfbox.pdmodel.fdf.FDFDocument
import com.tom_roush.pdfbox.pdmodel.graphics.color.PDColor
import com.tom_roush.pdfbox.pdmodel.graphics.color.PDDeviceRGB
import com.tom_roush.pdfbox.pdmodel.graphics.image.LosslessFactory
import com.tom_roush.pdfbox.pdmodel.graphics.image.PDImageXObject
import com.tom_roush.pdfbox.pdmodel.interactive.action.PDActionURI
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotation
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationLine
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationLink
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationMarkup
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDBorderStyleDictionary
import com.tom_roush.pdfbox.util.Matrix
import java.io.InputStream
import java.io.OutputStream
import java.util.Calendar
import kotlin.math.abs
import kotlin.math.hypot

/** Imagem desenhada diretamente na página (não dentro de formulários). */
data class PageImage(val page: Int, val opIndex: Int, val name: String, val ctm: FloatArray, val rect: RectF) {
    override fun equals(other: Any?) = other is PageImage && other.page == page && other.opIndex == opIndex
    override fun hashCode() = page * 100_003 + opIndex
}

object PageImages {
    /** Lista as imagens da página com a posição (coordenadas do PDF). */
    fun list(doc: PDDocument, pageIndex: Int): List<PageImage> {
        val page = doc.getPage(pageIndex)
        val out = ArrayList<PageImage>()
        val engine = object : PDFStreamEngine() {
            var op = -1
            var depth = 0
            init {
                addOperator(Concatenate()); addOperator(Save()); addOperator(Restore()); addOperator(SetMatrix())
                addOperator(SetGraphicsStateParameters()); addOperator(DrawObject())
            }
            override fun processOperator(operator: Operator, operands: MutableList<COSBase>) {
                if (depth == 0) op++
                if (depth == 0 && operator.name == "Do") {
                    val name = operands.firstOrNull() as? COSName
                    val xo = name?.let { runCatching { resources.getXObject(it) }.getOrNull() }
                    if (xo is PDImageXObject) {
                        val m = graphicsState.currentTransformationMatrix
                        val pts = listOf(0f to 0f, 1f to 0f, 0f to 1f, 1f to 1f).map { (x, y) -> m.transformPoint(x, y) }
                        out += PageImage(pageIndex, op, name.name, floatArrayOf(m.scaleX, m.shearY, m.shearX, m.scaleY, m.translateX, m.translateY),
                            RectF(pts.minOf { it.x }, pts.maxOf { it.y }, pts.maxOf { it.x }, pts.minOf { it.y }))
                        return
                    }
                }
                super.processOperator(operator, operands)
            }
            override fun showForm(form: com.tom_roush.pdfbox.pdmodel.graphics.form.PDFormXObject) {
                depth++
                try { super.showForm(form) } finally { depth-- }
            }
        }
        engine.processPage(page)
        return out
    }

    /** Reescreve o conteúdo da página trocando o operador "Do" da imagem (op) por [replacement] (vazio = remover). */
    private fun rewrite(doc: PDDocument, page: PDPage, op: Int, replacement: (List<Any>) -> List<Any>): List<COSDictionary> {
        val parser = PDFStreamParser(page)
        parser.parse()
        val out = ArrayList<Any>()
        val operands = ArrayList<Any>()
        var k = -1
        for (t in parser.tokens) {
            if (t !is Operator) { operands += t; continue }
            k++
            if (k == op && t.name == "Do") out.addAll(replacement(operands.toList())) else { out.addAll(operands); out.add(t) }
            operands.clear()
        }
        out.addAll(operands)
        val stream = PDStream(doc)
        stream.createOutputStream(COSName.FLATE_DECODE).use { ContentStreamWriter(it).writeTokens(out) }
        page.setContents(stream)
        stream.cosObject.isNeedToBeUpdated = true
        return listOf(page.cosObject, stream.cosObject)
    }

    private fun inverse(m: FloatArray): FloatArray {
        val (a, b, c, d, e, f) = m
        val det = a * d - b * c
        return floatArrayOf(d / det, -b / det, -c / det, a / det, (c * f - d * e) / det, (b * e - a * f) / det)
    }

    private operator fun FloatArray.component6() = this[5]

    /** A·B no formato [a b c d e f] do PDF (vetor linha: primeiro A, depois B). */
    private fun mul(x: FloatArray, y: FloatArray) = floatArrayOf(
        x[0] * y[0] + x[1] * y[2], x[0] * y[1] + x[1] * y[3],
        x[2] * y[0] + x[3] * y[2], x[2] * y[1] + x[3] * y[3],
        x[4] * y[0] + x[5] * y[2] + y[4], x[4] * y[1] + x[5] * y[3] + y[5])

    /** Move/redimensiona a imagem para o retângulo (coordenadas do PDF). */
    fun move(doc: PDDocument, img: PageImage, l: Float, b: Float, r: Float, t: Float): List<COSDictionary> {
        val target = floatArrayOf(r - l, 0f, 0f, t - b, l, b)
        // depois de "A cm" o CTM vira A × C; queremos A × C = alvo  ⇒  A = alvo × C⁻¹
        val a = mul(target, inverse(img.ctm))
        return rewrite(doc, doc.getPage(img.page), img.opIndex) { ops ->
            listOf<Any>(Operator.getOperator("q")) + a.map { COSFloat(it) } + listOf(Operator.getOperator("cm")) + ops +
                listOf(Operator.getOperator("Do"), Operator.getOperator("Q"))
        }
    }

    fun delete(doc: PDDocument, img: PageImage): List<COSDictionary> = rewrite(doc, doc.getPage(img.page), img.opIndex) { emptyList() }

    /** Troca a imagem por outra (mesma posição e tamanho). */
    fun replace(doc: PDDocument, img: PageImage, bmp: Bitmap): List<COSDictionary> {
        val page = doc.getPage(img.page)
        val x = LosslessFactory.createFromImage(doc, bmp)
        val name = page.resources.add(x)
        val changed = ArrayList(rewrite(doc, page, img.opIndex) { listOf<Any>(name, Operator.getOperator("Do")) })
        changed += page.resources.cosObject
        page.resources.cosObject.isNeedToBeUpdated = true
        (page.resources.cosObject.getDictionaryObject(COSName.XOBJECT) as? COSDictionary)?.isNeedToBeUpdated = true
        return changed
    }
}

object MoreEdit {
    /** Cria links clicáveis. items = (endereço, retângulos em coordenadas do PDF). */
    fun links(doc: PDDocument, pageIndex: Int, items: List<Pair<String, List<RectF>>>): List<COSDictionary> {
        val page = doc.getPage(pageIndex)
        val existing = page.annotations.filterIsInstance<PDAnnotationLink>().map { it.rectangle }
        val annots = page.annotations
        val out = mutableListOf<COSDictionary>(page.cosObject)
        for ((uri, rects) in items) for (r in rects) {
            val pr = PDRectangle(minOf(r.left, r.right), minOf(r.top, r.bottom), abs(r.right - r.left), abs(r.top - r.bottom))
            if (existing.any { e -> e.lowerLeftX < pr.upperRightX && pr.lowerLeftX < e.upperRightX && e.lowerLeftY < pr.upperRightY && pr.lowerLeftY < e.upperRightY }) continue
            val l = PDAnnotationLink()
            l.rectangle = pr
            l.borderStyle = PDBorderStyleDictionary().apply { width = 0f }
            l.action = PDActionURI().apply { this.uri = uri }
            l.page = page
            annots.add(l)
            out += l.cosObject
        }
        page.annotations = annots
        (page.cosObject.getDictionaryObject(COSName.ANNOTS) as? COSArray)?.isNeedToBeUpdated = true
        return out
    }

    private val SKIP = setOf("Popup", "Link", "Widget")

    /** Comentários em FDF (abre no Acrobat, Foxit, PDF-XChange…). Devolve a quantidade. */
    fun exportFdf(doc: PDDocument, pdfName: String, out: OutputStream): Int {
        FDFDocument().use { fdf ->
            val list = ArrayList<FDFAnnotation>()
            for (p in 0 until doc.numberOfPages) for (a in doc.getPage(p).annotations) {
                if (a.subtype in SKIP) continue
                val c = COSDictionary(a.cosObject)
                for (k in listOf(COSName.P, COSName.getPDFName("Popup"), COSName.PARENT, COSName.AP, COSName.getPDFName("IRT"), COSName.STRUCT_PARENT)) c.removeItem(k)
                c.setInt(COSName.PAGE, p)
                list += FDFAnnotation.create(c) ?: continue
            }
            fdf.catalog.fdf.annotations = list
            fdf.catalog.fdf.file = com.tom_roush.pdfbox.pdmodel.common.filespecification.PDSimpleFileSpecification().apply { file = pdfName }
            fdf.save(out)
            return list.size
        }
    }

    /** Acrescenta os comentários de um FDF. Devolve (objetos alterados, quantidade). */
    fun importFdf(doc: PDDocument, input: InputStream): Pair<List<COSDictionary>, Int> {
        val changed = ArrayList<COSDictionary>()
        var n = 0
        FDFDocument.load(input).use { fdf ->
            for (fa in fdf.catalog.fdf.annotations ?: emptyList()) {
                val c = COSDictionary(fa.cosObject)
                val sub = c.getNameAsString(COSName.SUBTYPE) ?: continue
                if (sub in SKIP) continue
                val p = c.getInt(COSName.PAGE, 0)
                if (p !in 0 until doc.numberOfPages) continue
                c.removeItem(COSName.PAGE); c.removeItem(COSName.AP); c.removeItem(COSName.getPDFName("Popup")); c.removeItem(COSName.P)
                val page = doc.getPage(p)
                val a = PDAnnotation.createAnnotation(c)
                a.page = page
                runCatching { a.constructAppearances(doc) }
                val annots = page.annotations
                annots.add(a)
                page.annotations = annots
                (page.cosObject.getDictionaryObject(COSName.ANNOTS) as? COSArray)?.isNeedToBeUpdated = true
                changed += page.cosObject; changed += a.cosObject
                n++
            }
        }
        return changed to n
    }

    fun fmtMeasure(v: Double, unit: String, area: Boolean = false): String {
        val s = String.format(java.util.Locale("pt", "BR"), "%,.2f", v)
        return if (area) "$s $unit²" else "$s $unit"
    }

    fun polygonArea(pts: List<Pair<Float, Float>>): Double {
        var a = 0.0
        for (i in pts.indices) {
            val (x0, y0) = pts[i]; val (x1, y1) = pts[(i + 1) % pts.size]
            a += x0.toDouble() * y1 - x1.toDouble() * y0
        }
        return abs(a) / 2
    }

    private fun label(doc: PDDocument, page: PDPage, text: String, cx: Float, cy: Float, color: Long): PDAnnotation {
        val w = 8f + text.length * 5.2f
        val ft = PDAnnotationMarkup()
        ft.cosObject.setName(COSName.SUBTYPE, "FreeText")
        ft.rectangle = PDRectangle(cx - w / 2, cy - 7f, w, 14f)
        ft.contents = text
        ft.cosObject.setString(COSName.DA, "/Helv 9 Tf %.3f %.3f %.3f rg".format(java.util.Locale.US,
            ((color shr 16) and 0xFF) / 255f, ((color shr 8) and 0xFF) / 255f, (color and 0xFF) / 255f))
        ft.cosObject.setInt(COSName.Q, 1)
        ft.color = PDColor(floatArrayOf(1f, 1f, 1f), PDDeviceRGB.INSTANCE)
        ft.borderStyle = PDBorderStyleDictionary().apply { width = 0f }
        ft.subject = "Medida"
        ft.titlePopup = Editor.author
        ft.page = page
        runCatching { ft.constructAppearances(doc) }
        return ft
    }

    /** Medida de distância (linha com marcas nas pontas e rótulo). x,y em coordenadas do PDF. */
    fun measureLine(doc: PDDocument, pageIndex: Int, x0: Float, y0: Float, x1: Float, y1: Float, text: String, color: Long): List<COSDictionary> {
        val page = doc.getPage(pageIndex)
        val ln = PDAnnotationLine()
        ln.line = floatArrayOf(x0, y0, x1, y1)
        ln.startPointEndingStyle = PDAnnotationLine.LE_BUTT
        ln.endPointEndingStyle = PDAnnotationLine.LE_BUTT
        ln.rectangle = PDRectangle(minOf(x0, x1) - 8, minOf(y0, y1) - 8, abs(x1 - x0) + 16, abs(y1 - y0) + 16)
        ln.borderStyle = PDBorderStyleDictionary().apply { width = 1.2f }
        ln.color = PDColor(argb(color), PDDeviceRGB.INSTANCE)
        ln.contents = "Distância: $text"
        ln.subject = "Medida"
        ln.titlePopup = Editor.author
        ln.setModifiedDate(Calendar.getInstance())
        ln.page = page
        ln.constructAppearances(doc)
        val horizontal = abs(x1 - x0) >= abs(y1 - y0)
        val lab = label(doc, page, text, (x0 + x1) / 2 + if (horizontal) 0f else 8f + text.length * 2.6f, (y0 + y1) / 2 + if (horizontal) 9f else 0f, color)
        val annots = page.annotations
        annots.add(ln); annots.add(lab)
        page.annotations = annots
        (page.cosObject.getDictionaryObject(COSName.ANNOTS) as? COSArray)?.isNeedToBeUpdated = true
        return listOf(page.cosObject, ln.cosObject, lab.cosObject)
    }

    /** Medida de área (polígono preenchido e rótulo no centro). pts em coordenadas do PDF. */
    fun measureArea(doc: PDDocument, pageIndex: Int, pts: List<Pair<Float, Float>>, text: String, color: Long): List<COSDictionary> {
        val page = doc.getPage(pageIndex)
        val pg = PDAnnotationMarkup()
        pg.cosObject.setName(COSName.SUBTYPE, "Polygon")
        pg.cosObject.setItem(COSName.getPDFName("Vertices"), COSArray().apply { pts.forEach { add(COSFloat(it.first)); add(COSFloat(it.second)) } })
        pg.rectangle = PDRectangle(pts.minOf { it.first } - 4, pts.minOf { it.second } - 4,
            pts.maxOf { it.first } - pts.minOf { it.first } + 8, pts.maxOf { it.second } - pts.minOf { it.second } + 8)
        pg.color = PDColor(argb(color), PDDeviceRGB.INSTANCE)
        pg.cosObject.setItem(COSName.IC, COSArray().apply { argb(color).forEach { add(COSFloat(it)) } })
        pg.constantOpacity = 0.25f
        pg.borderStyle = PDBorderStyleDictionary().apply { width = 1.2f }
        pg.contents = "Área: $text"
        pg.subject = "Medida"
        pg.titlePopup = Editor.author
        pg.page = page
        pg.constructAppearances(doc)
        val lab = label(doc, page, text, pts.map { it.first }.average().toFloat(), pts.map { it.second }.average().toFloat(), color)
        val annots = page.annotations
        annots.add(pg); annots.add(lab)
        page.annotations = annots
        (page.cosObject.getDictionaryObject(COSName.ANNOTS) as? COSArray)?.isNeedToBeUpdated = true
        return listOf(page.cosObject, pg.cosObject, lab.cosObject)
    }
}

/** Escala das medidas: unidades reais por ponto do PDF. */
data class MeasureScale(val factor: Double, val unit: String, val label: String) {
    companion object {
        val PAPER = MeasureScale(2.54 / 72, "cm", "tamanho real do papel")
        fun plan(n: Int, unit: String): MeasureScale {
            val perUnit = mapOf("m" to 1.0, "cm" to 100.0, "mm" to 1000.0, "km" to 0.001)[unit] ?: 1.0
            return MeasureScale(0.0254 / 72 * n * perUnit, unit, "1:$n")
        }
        fun parse(s: String?): MeasureScale? = s?.split("|")?.takeIf { it.size == 3 }?.let { (f, u, l) -> f.toDoubleOrNull()?.let { MeasureScale(it, u, l) } }
    }
    fun store() = "$factor|$unit|$label"
}

fun distPts(x0: Float, y0: Float, x1: Float, y1: Float) = hypot((x1 - x0).toDouble(), (y1 - y0).toDouble())
