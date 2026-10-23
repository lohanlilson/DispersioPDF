package io.github.lohanlilson.lumenpdf

import android.graphics.Bitmap
import android.graphics.RectF
import com.tom_roush.pdfbox.cos.COSArray
import com.tom_roush.pdfbox.cos.COSDictionary
import com.tom_roush.pdfbox.cos.COSName
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPage
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream
import com.tom_roush.pdfbox.pdmodel.common.PDRectangle
import com.tom_roush.pdfbox.pdmodel.font.PDFont
import com.tom_roush.pdfbox.pdmodel.font.PDType0Font
import com.tom_roush.pdfbox.pdmodel.font.PDType1Font
import com.tom_roush.pdfbox.pdmodel.graphics.color.PDColor
import com.tom_roush.pdfbox.pdmodel.graphics.color.PDDeviceRGB
import com.tom_roush.pdfbox.pdmodel.graphics.image.LosslessFactory
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotation
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationMarkup
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationText
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationTextMarkup
import com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDBorderStyleDictionary
import com.tom_roush.pdfbox.pdmodel.interactive.form.PDCheckBox
import com.tom_roush.pdfbox.pdmodel.interactive.form.PDChoice
import com.tom_roush.pdfbox.pdmodel.interactive.form.PDRadioButton
import com.tom_roush.pdfbox.pdmodel.interactive.form.PDSignatureField
import com.tom_roush.pdfbox.pdmodel.interactive.form.PDTerminalField
import com.tom_roush.pdfbox.pdmodel.interactive.form.PDTextField
import com.tom_roush.pdfbox.util.Matrix
import java.io.File
import java.util.Calendar

/** Marcação de texto (destacar, sublinhar, tachar). */
enum class Markup(val subtype: String, val label: String) {
    HIGHLIGHT(PDAnnotationTextMarkup.SUB_TYPE_HIGHLIGHT, "Destacar"),
    UNDERLINE(PDAnnotationTextMarkup.SUB_TYPE_UNDERLINE, "Sublinhar"),
    STRIKEOUT(PDAnnotationTextMarkup.SUB_TYPE_STRIKEOUT, "Tachar"),
}

/** Campo de formulário encontrado no documento. rect = coordenadas do PDF (sem rotação). */
data class FormField(
    val name: String, val label: String, val kind: Kind, val page: Int, val rect: RectF,
    val value: String, val options: List<String>, val onValue: String?, val readOnly: Boolean,
) {
    enum class Kind { TEXT, CHECK, RADIO, CHOICE, SIGNATURE, OTHER }
}

fun argb(c: Long) = floatArrayOf(((c shr 16) and 0xFF) / 255f, ((c shr 8) and 0xFF) / 255f, (c and 0xFF) / 255f)

/**
 * Edição com o PDFBox. Cada operação gera uma nova versão do arquivo de trabalho.
 * Em documentos assinados a gravação é incremental (só acrescenta), então as assinaturas continuam válidas.
 */
object Editor {
    var author: String = "Lumen PDF"

    private fun signed(doc: PDDocument): Boolean =
        doc.documentCatalog.acroForm?.fieldTree?.any { it is PDSignatureField && it.signature != null } == true

    /** Abre [src], aplica [block] e grava em [dst]. block devolve os objetos alterados (para a gravação incremental). */
    fun apply(src: File, dst: File, password: String?, block: (PDDocument) -> Collection<COSDictionary>) {
        PDDocument.load(src, password ?: "").use { doc ->
            val changed = block(doc)
            dst.outputStream().buffered().use { out ->
                if (signed(doc)) {
                    val set = HashSet<COSDictionary>()
                    changed.forEach { d -> set += d; d.isNeedToBeUpdated = true }
                    doc.documentCatalog.cosObject.isNeedToBeUpdated = true
                    doc.saveIncremental(out, set)
                } else {
                    doc.save(out)
                }
            }
        }
    }

    private fun addAnnot(page: PDPage, a: PDAnnotation): List<COSDictionary> {
        val annots = page.annotations
        annots.add(a)
        page.annotations = annots
        val out = mutableListOf(page.cosObject, a.cosObject)
        (page.cosObject.getDictionaryObject(COSName.ANNOTS) as? COSArray)?.let { it.isNeedToBeUpdated = true }
        return out
    }

    private fun stamp(a: PDAnnotationMarkup, color: Long) {
        a.color = PDColor(argb(color), PDDeviceRGB.INSTANCE)
        a.titlePopup = author
        a.creationDate = Calendar.getInstance()
        a.setModifiedDate(Calendar.getInstance())
        a.isPrinted = true
        a.annotationName = "lumen-" + System.nanoTime()
    }

    /** rects = retângulos do texto em coordenadas do PDF. */
    fun markup(doc: PDDocument, pageIndex: Int, rects: List<RectF>, kind: Markup, color: Long, note: String? = null): List<COSDictionary> {
        val page = doc.getPage(pageIndex)
        val a = PDAnnotationTextMarkup(kind.subtype)
        val quads = FloatArray(rects.size * 8)
        var x0 = Float.MAX_VALUE; var y0 = Float.MAX_VALUE; var x1 = -Float.MAX_VALUE; var y1 = -Float.MAX_VALUE
        rects.forEachIndexed { i, r ->
            val l = minOf(r.left, r.right); val rr = maxOf(r.left, r.right)
            val b = minOf(r.top, r.bottom); val t = maxOf(r.top, r.bottom)
            floatArrayOf(l, t, rr, t, l, b, rr, b).copyInto(quads, i * 8)
            x0 = minOf(x0, l); y0 = minOf(y0, b); x1 = maxOf(x1, rr); y1 = maxOf(y1, t)
        }
        a.rectangle = PDRectangle(x0 - 1, y0 - 1, x1 - x0 + 2, y1 - y0 + 2)
        a.quadPoints = quads
        stamp(a, color)
        if (kind == Markup.HIGHLIGHT) a.constantOpacity = 1f
        if (!note.isNullOrBlank()) a.contents = note
        a.constructAppearances(doc)
        return addAnnot(page, a)
    }

    /** strokes = lista de traços, cada um com pontos em coordenadas do PDF (x,y,x,y…). */
    fun ink(doc: PDDocument, pageIndex: Int, strokes: List<FloatArray>, color: Long, width: Float): List<COSDictionary> {
        val page = doc.getPage(pageIndex)
        val a = PDAnnotationMarkup()
        a.cosObject.setName(COSName.SUBTYPE, "Ink")
        var x0 = Float.MAX_VALUE; var y0 = Float.MAX_VALUE; var x1 = -Float.MAX_VALUE; var y1 = -Float.MAX_VALUE
        for (s in strokes) for (i in s.indices step 2) {
            x0 = minOf(x0, s[i]); x1 = maxOf(x1, s[i]); y0 = minOf(y0, s[i + 1]); y1 = maxOf(y1, s[i + 1])
        }
        val pad = width * 2
        a.rectangle = PDRectangle(x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)
        a.inkList = strokes.toTypedArray()
        a.borderStyle = PDBorderStyleDictionary().apply { this.width = width }
        stamp(a, color)
        a.constructAppearances(doc)
        return addAnnot(page, a)
    }

    fun note(doc: PDDocument, pageIndex: Int, x: Float, y: Float, text: String, color: Long): List<COSDictionary> {
        val page = doc.getPage(pageIndex)
        val a = PDAnnotationText()
        a.rectangle = PDRectangle(x, y - 22, 22f, 22f)
        a.contents = text
        a.name = PDAnnotationText.NAME_COMMENT
        stamp(a, color)
        a.constructAppearances(doc)
        return addAnnot(page, a)
    }

    private fun loadFont(doc: PDDocument): PDFont {
        val cands = listOf("/system/fonts/Roboto-Regular.ttf", "/system/fonts/NotoSans-Regular.ttf", "/system/fonts/DroidSans.ttf")
        for (c in cands) {
            val f = File(c)
            if (f.exists()) runCatching { return PDType0Font.load(doc, f) }
        }
        return PDType1Font.HELVETICA
    }

    /** Escreve no conteúdo da página (como o "Preencher e assinar" do Acrobat): sai igual em qualquer leitor. */
    private fun withContent(doc: PDDocument, page: PDPage, block: (PDPageContentStream) -> Unit): List<COSDictionary> {
        PDPageContentStream(doc, page, PDPageContentStream.AppendMode.APPEND, true, true).use(block)
        val out = mutableListOf(page.cosObject)
        (page.cosObject.getDictionaryObject(COSName.CONTENTS) as? COSArray)?.let { it.isNeedToBeUpdated = true }
        page.cosObject.getDictionaryObject(COSName.RESOURCES)?.let { (it as? COSDictionary)?.let { r -> out += r; markDeep(r) } }
        return out
    }

    private fun markDeep(d: COSDictionary) {
        d.isNeedToBeUpdated = true
        for (k in d.keySet()) (d.getDictionaryObject(k) as? COSDictionary)?.isNeedToBeUpdated = true
    }

    /** Matriz que deixa o conteúdo "em pé" mesmo em páginas giradas. (x,y) = canto inferior esquerdo visual. */
    private fun upright(page: PDPage, x: Float, y: Float): Matrix {
        val rot = ((page.rotation % 360) + 360) % 360
        return Matrix.getRotateInstance(Math.toRadians(rot.toDouble()), x, y)
    }

    fun text(doc: PDDocument, pageIndex: Int, x: Float, y: Float, text: String, size: Float, color: Long): List<COSDictionary> {
        val page = doc.getPage(pageIndex)
        return withContent(doc, page) { cs ->
            val font = loadFont(doc)
            cs.beginText()
            cs.setNonStrokingColor(PDColor(argb(color), PDDeviceRGB.INSTANCE))
            cs.setFont(font, size)
            val lines = text.split("\n")
            lines.forEachIndexed { i, line ->
                cs.setTextMatrix(upright(page, x, y).also { it.translate(0f, -i * size * 1.2f) })
                cs.showText(line)
            }
            cs.endText()
        }
    }

    /** ✓ ou ✗ desenhado em vetor. (x,y) = centro. */
    fun mark(doc: PDDocument, pageIndex: Int, x: Float, y: Float, check: Boolean, size: Float, color: Long): List<COSDictionary> {
        val page = doc.getPage(pageIndex)
        return withContent(doc, page) { cs ->
            cs.saveGraphicsState()
            cs.transform(upright(page, x, y))
            cs.setStrokingColor(PDColor(argb(color), PDDeviceRGB.INSTANCE))
            cs.setLineWidth(size * 0.12f)
            cs.setLineCapStyle(1)
            cs.setLineJoinStyle(1)
            val h = size / 2
            if (check) {
                cs.moveTo(-h, 0f); cs.lineTo(-h * 0.25f, -h * 0.7f); cs.lineTo(h, h * 0.8f)
            } else {
                cs.moveTo(-h * 0.8f, -h * 0.8f); cs.lineTo(h * 0.8f, h * 0.8f)
                cs.moveTo(-h * 0.8f, h * 0.8f); cs.lineTo(h * 0.8f, -h * 0.8f)
            }
            cs.stroke()
            cs.restoreGraphicsState()
        }
    }

    /** Imagem (rubrica) com o canto inferior esquerdo visual em (x,y). */
    fun image(doc: PDDocument, pageIndex: Int, bmp: Bitmap, x: Float, y: Float, w: Float, h: Float): List<COSDictionary> {
        val page = doc.getPage(pageIndex)
        return withContent(doc, page) { cs ->
            val img = LosslessFactory.createFromImage(doc, bmp)
            cs.saveGraphicsState()
            cs.transform(upright(page, x, y))
            cs.drawImage(img, 0f, 0f, w, h)
            cs.restoreGraphicsState()
        }
    }

    // ------------------------------------------------------------ formulários
    fun fields(doc: PDDocument): List<FormField> {
        val form = doc.documentCatalog.acroForm ?: return emptyList()
        val pages = doc.pages
        val out = ArrayList<FormField>()
        for (f in form.fieldTree) {
            if (f !is PDTerminalField) continue
            val kind = when (f) {
                is PDTextField -> FormField.Kind.TEXT
                is PDCheckBox -> FormField.Kind.CHECK
                is PDRadioButton -> FormField.Kind.RADIO
                is PDChoice -> FormField.Kind.CHOICE
                is PDSignatureField -> FormField.Kind.SIGNATURE
                else -> FormField.Kind.OTHER
            }
            val opts = (f as? PDChoice)?.optionsDisplayValues ?: emptyList()
            for (w in f.widgets) {
                val r = w.rectangle ?: continue
                val pageIdx = w.page?.let { pages.indexOf(it) }?.takeIf { it >= 0 }
                    ?: (0 until doc.numberOfPages).firstOrNull { i -> doc.getPage(i).annotations.any { it.cosObject == w.cosObject } }
                    ?: continue
                val on = when (f) {
                    is PDCheckBox -> f.onValue
                    is PDRadioButton -> w.appearance?.normalAppearance?.subDictionary?.keys?.firstOrNull { it.name != "Off" }?.name
                    else -> null
                }
                out += FormField(
                    f.fullyQualifiedName, f.alternateFieldName ?: f.partialName ?: f.fullyQualifiedName, kind, pageIdx,
                    RectF(r.lowerLeftX, r.upperRightY, r.upperRightX, r.lowerLeftY),
                    when (f) {
                        is PDSignatureField -> if (f.signature != null) "assinado" else ""
                        else -> f.valueAsString ?: ""
                    },
                    opts, on, f.isReadOnly,
                )
            }
        }
        return out
    }

    fun setField(doc: PDDocument, name: String, value: String): List<COSDictionary> {
        val form = doc.documentCatalog.acroForm ?: return emptyList()
        val f = form.getField(name) ?: return emptyList()
        runCatching {
            when (f) {
                is PDCheckBox -> if (value.isNotEmpty() && value != "Off") f.check() else f.unCheck()
                is PDRadioButton -> f.setValue(value)
                is PDChoice -> f.setValue(value)
                else -> f.setValue(value)
            }
        }.onFailure {
            // fonte do campo sem os caracteres: pede para o leitor redesenhar o campo
            form.needAppearances = true
            f.cosObject.setString(COSName.V, value)
        }
        val out = mutableListOf(f.cosObject, form.cosObject)
        (f as? PDTerminalField)?.widgets?.forEach { w ->
            out += w.cosObject
            w.appearance?.cosObject?.let { out += it; markDeep(it) }
        }
        return out
    }

    // ------------------------------------------------------------ páginas (alteram a estrutura: gravação completa)
    /** Abre, aplica e grava o documento inteiro (mudanças de páginas). */
    fun applyFull(src: File, dst: File, password: String?, block: (PDDocument, MutableList<PDDocument>) -> Unit) {
        val keep = mutableListOf<PDDocument>()   // documentos de origem: ficam abertos até gravar
        try {
            PDDocument.load(src, password ?: "").use { doc ->
                block(doc, keep)
                dst.outputStream().buffered().use { doc.save(it) }
            }
        } finally {
            keep.forEach { runCatching { it.close() } }
        }
    }

    fun isSigned(src: File, password: String?): Boolean =
        runCatching { PDDocument.load(src, password ?: "").use { signed(it) } }.getOrDefault(false)

    fun rotate(doc: PDDocument, pages: Collection<Int>, angle: Int) {
        for (i in pages) doc.getPage(i).let { it.rotation = ((it.rotation + angle) % 360 + 360) % 360 }
    }

    fun delete(doc: PDDocument, pages: Collection<Int>) {
        for (i in pages.sortedDescending()) doc.removePage(i)
    }

    /** Reordena: order[k] = índice antigo da página que fica na posição k. */
    fun reorder(doc: PDDocument, order: List<Int>) {
        val pages = (0 until doc.numberOfPages).map { doc.getPage(it) }
        for (p in pages) doc.pages.remove(p)
        for (i in order) doc.pages.add(pages[i])
    }

    /** Insere as páginas de outro PDF na posição [at]. */
    fun insertPdf(doc: PDDocument, other: File, at: Int, keep: MutableList<PDDocument>) {
        val o = PDDocument.load(other)
        keep += o
        val total = doc.numberOfPages
        val added = (0 until o.numberOfPages).map { doc.importPage(o.getPage(it)) }
        val order = (0 until total).toMutableList()
        order.addAll(at.coerceIn(0, total), (total until total + added.size).toList())
        reorder(doc, order)
    }

    fun insertBlank(doc: PDDocument, at: Int) {
        val ref = doc.getPage((at - 1).coerceAtLeast(0).coerceAtMost(doc.numberOfPages - 1))
        val page = PDPage(ref.mediaBox)
        doc.addPage(page)
        val total = doc.numberOfPages
        val order = (0 until total - 1).toMutableList()
        order.add(at.coerceIn(0, total - 1), total - 1)
        reorder(doc, order)
    }

    fun extract(src: File, password: String?, pages: List<Int>, dst: File) {
        PDDocument.load(src, password ?: "").use { doc ->
            PDDocument().use { out ->
                for (i in pages) out.importPage(doc.getPage(i))
                dst.outputStream().buffered().use { out.save(it) }
            }
        }
    }

    fun merge(files: List<File>, dst: File) {
        PDDocument().use { out ->
            val opened = files.map { PDDocument.load(it) }
            try {
                for (d in opened) for (i in 0 until d.numberOfPages) out.importPage(d.getPage(i))
                dst.outputStream().buffered().use { out.save(it) }
            } finally {
                opened.forEach { it.close() }
            }
        }
    }
}
