package io.github.lohanlilson.dispersio

import android.graphics.Bitmap
import android.graphics.RectF
import com.tom_roush.pdfbox.cos.COSArray
import com.tom_roush.pdfbox.cos.COSBase
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
    var author: String = "Dispersio PDF"

    private fun signed(doc: PDDocument): Boolean =
        doc.documentCatalog.acroForm?.fieldTree?.any { it is PDSignatureField && it.signature != null } == true

    /** Abre [src], aplica [block] e grava em [dst]. block devolve os objetos alterados (para a gravação incremental). */
    fun apply(src: File, dst: File, password: String?, block: (PDDocument) -> Collection<COSDictionary>) =
        apply(src, dst, password, block) {}

    /** after = roda com o documento ainda aberto, já com a alteração (ex.: ler campos e comentários sem reabrir). */
    fun apply(src: File, dst: File, password: String?, block: (PDDocument) -> Collection<COSDictionary>, after: (PDDocument) -> Unit) {
        PDDocument.load(src, password ?: "").use { doc ->
            val changed = block(doc)
            // gravação incremental: só acrescenta o que mudou (mais rápido e mantém as assinaturas válidas).
            // Documento protegido por senha: grava o arquivo inteiro.
            val incremental = signed(doc) || !doc.isEncrypted
            var ok = false
            if (incremental) {
                ok = runCatching {
                    dst.outputStream().buffered().use { out ->
                        val set = HashSet<COSDictionary>()
                        changed.forEach { d -> set += d; d.isNeedToBeUpdated = true }
                        doc.documentCatalog.cosObject.isNeedToBeUpdated = true
                        subsetFonts(doc)
                        doc.saveIncremental(out, set)
                    }
                    true
                }.getOrElse { e ->
                    if (signed(doc)) throw e
                    android.util.Log.w("DispersioPdf", "gravação incremental falhou; gravando completo", e)
                    false
                }
            }
            if (!ok) dst.outputStream().buffered().use { doc.save(it) }
            after(doc)
        }
    }

    /**
     * Fontes embutidas como subconjunto só recebem as letras no save() completo; a gravação incremental
     * do PDFBox pula essa etapa e a fonte ficaria vazia (texto invisível na tela). Faz aqui.
     */
    fun subsetFonts(doc: PDDocument) {
        val f = PDDocument::class.java.getDeclaredField("fontsToSubset").apply { isAccessible = true }
        @Suppress("UNCHECKED_CAST")
        val fonts = f.get(doc) as MutableSet<com.tom_roush.pdfbox.pdmodel.font.PDFont>
        for (font in fonts.toList()) runCatching { font.subset() }.onFailure { android.util.Log.w("DispersioPdf", "subconjunto da fonte", it) }
        fonts.clear()
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
        a.annotationName = "dispersio-" + System.nanoTime()
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

    /**
     * Forma: "Square" (retângulo), "Circle" (círculo/elipse) ou "Arrow" (seta).
     * x0,y0 → x1,y1 em coordenadas do PDF (na seta, do início para a ponta).
     */
    fun shape(doc: PDDocument, pageIndex: Int, kind: String, x0: Float, y0: Float, x1: Float, y1: Float,
              color: Long, width: Float): List<COSDictionary> {
        val page = doc.getPage(pageIndex)
        val pad = width * 2 + 2
        val l = minOf(x0, x1); val r = maxOf(x0, x1); val b = minOf(y0, y1); val t = maxOf(y0, y1)
        val border = PDBorderStyleDictionary().apply { this.width = width }
        val a: PDAnnotationMarkup = if (kind == "Arrow") {
            com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationLine().apply {
                line = floatArrayOf(x0, y0, x1, y1)
                endPointEndingStyle = com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationLine.LE_OPEN_ARROW
                rectangle = PDRectangle(l - pad * 3, b - pad * 3, r - l + pad * 6, t - b + pad * 6)
                borderStyle = border
            }
        } else {
            com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationSquareCircle(
                if (kind == "Circle") com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationSquareCircle.SUB_TYPE_CIRCLE
                else com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationSquareCircle.SUB_TYPE_SQUARE).apply {
                rectangle = PDRectangle(l - width / 2, b - width / 2, r - l + width, t - b + width)
                borderStyle = border
            }
        }
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

    /** Grupos de páginas para dividir: mode = every (a cada N) | ranges ("1-3; 4-10") | bookmarks | size (MB). */
    fun splitGroups(src: File, password: String?, mode: String, value: String): List<List<Int>> =
        PDDocument.load(src, password ?: "").use { doc ->
            val n = doc.numberOfPages
            when (mode) {
                "every" -> { val k = value.trim().toIntOrNull()?.coerceAtLeast(1) ?: 1; (0 until n step k).map { (it until minOf(it + k, n)).toList() } }
                "ranges" -> value.split(';').map { parseRanges(it, n) }.filter { it.isNotEmpty() }
                "bookmarks" -> {
                    val starts = sortedSetOf(0)
                    var item = doc.documentCatalog.documentOutline?.firstChild
                    while (item != null) {
                        runCatching { item!!.findDestinationPage(doc)?.let { pg -> doc.pages.indexOf(pg).takeIf { it >= 0 }?.let { starts += it } } }
                        item = item.nextSibling
                    }
                    val st = starts.toList() + n
                    st.zipWithNext().filter { (a, b) -> b > a }.map { (a, b) -> (a until b).toList() }
                }
                else -> {   // size: tamanho de cada página sozinha (estimativa por cima) e agrupa até o limite
                    val limit = ((value.replace(',', '.').trim().toDoubleOrNull() ?: 5.0) * 1024 * 1024).toLong()
                    val groups = ArrayList<List<Int>>()
                    var cur = ArrayList<Int>(); var acc = 0L
                    for (i in 0 until n) {
                        val sz = PDDocument().use { one ->
                            one.importPage(doc.getPage(i))
                            val o = java.io.ByteArrayOutputStream(); one.save(o); o.size().toLong()
                        }
                        if (cur.isNotEmpty() && acc + sz > limit) { groups += cur; cur = ArrayList(); acc = 0 }
                        cur += i; acc += sz
                    }
                    if (cur.isNotEmpty()) groups += cur
                    groups
                }
            }
        }

    /** "1-3, 5, 8-" → páginas (base 0); partes inválidas são ignoradas. */
    fun parseRanges(text: String, n: Int): List<Int> {
        val out = ArrayList<Int>()
        for (part in text.split(',')) {
            val p = part.trim()
            if (p.isEmpty()) continue
            runCatching {
                if ('-' in p) {
                    val (a, b) = p.split('-', limit = 2).map { it.trim() }
                    val x = a.toIntOrNull() ?: 1; val y = b.toIntOrNull() ?: n
                    if (x <= y) out += (x - 1 until y) else out += (x - 1 downTo y - 1)
                } else out += p.toInt() - 1
            }
        }
        return out.filter { it in 0 until n }
    }

    /** Salva cada grupo de páginas num arquivo. */
    fun split(src: File, password: String?, groups: List<List<Int>>, dir: File, base: String): List<File> {
        dir.mkdirs()
        return groups.mapIndexed { k, pages ->
            val f = File(dir, "%s_parte%02d.pdf".format(base, k + 1))
            extract(src, password, pages, f)
            f
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

    // ------------------------------------------------------------ comentários existentes
    data class AnnotRef(val page: Int, val index: Int, val subtype: String, val rect: RectF, val contents: String) {
        val movable get() = subtype in setOf("Text", "Ink", "FreeText", "Square", "Circle", "Line", "Stamp")
        val label get() = when (subtype) {
            "Highlight" -> "Destaque"; "Underline" -> "Sublinhado"; "StrikeOut" -> "Tachado"; "Text" -> "Nota"
            "Ink" -> "Desenho"; "FreeText" -> "Caixa de texto"; "Square" -> "Retângulo"; "Circle" -> "Elipse"
            else -> subtype
        }
    }

    private val SKIP = setOf("Widget", "Link", "Popup")

    fun annotations(doc: PDDocument): List<AnnotRef> {
        val out = ArrayList<AnnotRef>()
        for (p in 0 until doc.numberOfPages) {
            doc.getPage(p).annotations.forEachIndexed { i, a ->
                if (a.subtype in SKIP) return@forEachIndexed
                val r = a.rectangle ?: return@forEachIndexed
                out += AnnotRef(p, i, a.subtype, RectF(r.lowerLeftX, r.upperRightY, r.upperRightX, r.lowerLeftY), a.contents ?: "")
            }
        }
        return out
    }

    private fun annotAt(doc: PDDocument, ref: AnnotRef): Pair<PDPage, PDAnnotation> {
        val page = doc.getPage(ref.page)
        val a = page.annotations.getOrNull(ref.index)
        require(a != null && a.subtype == ref.subtype) { "comentário não encontrado" }
        return page to a
    }

    fun deleteAnnot(doc: PDDocument, ref: AnnotRef): List<COSDictionary> {
        val (page, a) = annotAt(doc, ref)
        val popup = (a as? PDAnnotationMarkup)?.popup?.cosObject
        // remove direto do array /Annots (a lista do PDFBox não repassa remoções)
        val arr = page.cosObject.getDictionaryObject(COSName.ANNOTS) as? COSArray ?: return emptyList()
        for (k in arr.size() - 1 downTo 0) {
            val o = arr.getObject(k)
            if (o == a.cosObject || (popup != null && o == popup)) arr.remove(k)
        }
        arr.isNeedToBeUpdated = true
        page.cosObject.setItem(COSName.ANNOTS, arr)
        return listOf(page.cosObject)
    }

    fun recolorAnnot(doc: PDDocument, ref: AnnotRef, color: Long): List<COSDictionary> {
        val (page, a) = annotAt(doc, ref)
        a.color = PDColor(argb(color), PDDeviceRGB.INSTANCE)
        a.setModifiedDate(Calendar.getInstance())
        a.cosObject.removeItem(COSName.AP)
        a.constructAppearances(doc)
        return listOf(page.cosObject, a.cosObject)
    }

    fun editNote(doc: PDDocument, ref: AnnotRef, text: String): List<COSDictionary> {
        val (page, a) = annotAt(doc, ref)
        a.contents = text
        a.setModifiedDate(Calendar.getInstance())
        return listOf(page.cosObject, a.cosObject)
    }

    /** Desloca o comentário (dx, dy em coordenadas do PDF). */
    fun moveAnnot(doc: PDDocument, ref: AnnotRef, dx: Float, dy: Float): List<COSDictionary> {
        val (page, a) = annotAt(doc, ref)
        val r = a.rectangle
        a.rectangle = PDRectangle(r.lowerLeftX + dx, r.lowerLeftY + dy, r.width, r.height)
        if (a is PDAnnotationMarkup) {
            a.inkList?.let { list -> a.inkList = list.map { s -> FloatArray(s.size) { k -> s[k] + if (k % 2 == 0) dx else dy } }.toTypedArray() }
        }
        (a as? PDAnnotationTextMarkup)?.quadPoints?.let { q -> a.quadPoints = FloatArray(q.size) { k -> q[k] + if (k % 2 == 0) dx else dy } }
        (a as? com.tom_roush.pdfbox.pdmodel.interactive.annotation.PDAnnotationLine)?.line?.let { q ->
            a.line = FloatArray(q.size) { k -> q[k] + if (k % 2 == 0) dx else dy }
        }
        a.setModifiedDate(Calendar.getInstance())
        a.cosObject.removeItem(COSName.AP)
        a.constructAppearances(doc)
        return listOf(page.cosObject, a.cosObject)
    }

    // ------------------------------------------------------------ editar texto existente
    /**
     * Troca uma linha de texto: cobre o trecho original com um retângulo da cor do fundo e escreve o novo texto
     * na mesma posição e tamanho. rect = área do texto original (coordenadas do PDF).
     */
    fun replaceText(doc: PDDocument, pageIndex: Int, rect: RectF, x: Float, y: Float, text: String, size: Float,
                    color: Long, bg: Long = 0xFFFFFFFF): List<COSDictionary> {
        val page = doc.getPage(pageIndex)
        return withContent(doc, page) { cs ->
            val l = minOf(rect.left, rect.right); val b = minOf(rect.top, rect.bottom)
            val w = kotlin.math.abs(rect.right - rect.left); val h = kotlin.math.abs(rect.top - rect.bottom)
            cs.setNonStrokingColor(PDColor(argb(bg), PDDeviceRGB.INSTANCE))
            cs.addRect(l - 1, b - 1, w + 2, h + 2)
            cs.fill()
            if (text.isNotEmpty()) {
                val font = loadFont(doc)
                cs.beginText()
                cs.setNonStrokingColor(PDColor(argb(color), PDDeviceRGB.INSTANCE))
                cs.setFont(font, size)
                cs.setTextMatrix(upright(page, x, y))
                cs.showText(text)
                cs.endText()
            }
        }
    }

    // ------------------------------------------------------------ marca d'água e numeração
    fun watermark(doc: PDDocument, text: String, opacity: Float, color: Long) {
        val font = loadFont(doc)
        for (page in doc.pages) {
            PDPageContentStream(doc, page, PDPageContentStream.AppendMode.APPEND, true, true).use { cs ->
                val box = page.cropBox
                val gs = com.tom_roush.pdfbox.pdmodel.graphics.state.PDExtendedGraphicsState()
                gs.nonStrokingAlphaConstant = opacity
                cs.setGraphicsStateParameters(gs)
                cs.setNonStrokingColor(PDColor(argb(color), PDDeviceRGB.INSTANCE))
                val diag = kotlin.math.hypot(box.width, box.height)
                var size = diag / 12f
                val tw = font.getStringWidth(text) / 1000 * size
                if (tw > diag * 0.8f) size *= diag * 0.8f / tw
                val w = font.getStringWidth(text) / 1000 * size
                val ang = Math.atan2(box.height.toDouble(), box.width.toDouble())
                cs.beginText()
                cs.setFont(font, size)
                val m = Matrix.getRotateInstance(ang, box.lowerLeftX + box.width / 2, box.lowerLeftY + box.height / 2)
                m.translate(-w / 2, -size / 3)
                cs.setTextMatrix(m)
                cs.showText(text)
                cs.endText()
            }
        }
    }

    /** formato: "{n}", "{n} de {total}", "Página {n} de {total}". */
    fun pageNumbers(doc: PDDocument, format: String, size: Float = 10f) {
        val font = loadFont(doc)
        val total = doc.numberOfPages
        doc.pages.forEachIndexed { i, page ->
            val text = format.replace("{n}", "${i + 1}").replace("{total}", "$total")
            PDPageContentStream(doc, page, PDPageContentStream.AppendMode.APPEND, true, true).use { cs ->
                val box = page.cropBox
                val rot = ((page.rotation % 360) + 360) % 360
                val w = font.getStringWidth(text) / 1000 * size
                // centro do rodapé visual
                val (vw, _) = if (rot % 180 == 0) box.width to box.height else box.height to box.width
                val m = when (rot) {
                    90 -> Matrix(0f, 1f, -1f, 0f, box.lowerLeftX + box.width - 24f, box.lowerLeftY + vw / 2 - w / 2)
                    180 -> Matrix(-1f, 0f, 0f, -1f, box.lowerLeftX + vw / 2 + w / 2, box.lowerLeftY + box.height - 24f)
                    270 -> Matrix(0f, -1f, 1f, 0f, box.lowerLeftX + 24f, box.lowerLeftY + vw / 2 + w / 2)
                    else -> Matrix(1f, 0f, 0f, 1f, box.lowerLeftX + vw / 2 - w / 2, box.lowerLeftY + 20f)
                }
                cs.beginText()
                cs.setFont(font, size)
                cs.setNonStrokingColor(0.25f, 0.25f, 0.28f)
                cs.setTextMatrix(m)
                cs.showText(text)
                cs.endText()
            }
        }
    }

    // ------------------------------------------------------------ comprimir, senha, fotos
    /** Reduz as imagens (lado maior até maxPx, JPEG). Devolve quantas imagens foram recomprimidas. */
    fun compress(doc: PDDocument, maxPx: Int, quality: Float): Int {
        var n = 0
        val seen = HashSet<COSBase>()
        for (page in doc.pages) {
            val res = page.resources ?: continue
            for (name in res.xObjectNames) {
                val xo = runCatching { res.getXObject(name) }.getOrNull() as? com.tom_roush.pdfbox.pdmodel.graphics.image.PDImageXObject ?: continue
                if (!seen.add(xo.cosObject)) continue
                val big = maxOf(xo.width, xo.height)
                if (big <= maxPx && xo.cosObject.getDictionaryObject(COSName.FILTER)?.toString()?.contains("DCT") == true) continue
                val bmp = runCatching { xo.image }.getOrNull() ?: continue
                val scale = if (big > maxPx) maxPx.toFloat() / big else 1f
                val small = if (scale < 1f) Bitmap.createScaledBitmap(bmp, maxOf(1, (bmp.width * scale).toInt()), maxOf(1, (bmp.height * scale).toInt()), true) else bmp
                val opaque = if (small.hasAlpha()) small.copy(Bitmap.Config.RGB_565, false) else small
                val jpg = com.tom_roush.pdfbox.pdmodel.graphics.image.JPEGFactory.createFromImage(doc, opaque, quality)
                res.put(name, jpg)
                n++
            }
        }
        return n
    }

    fun protect(doc: PDDocument, userPwd: String, ownerPwd: String, allowPrint: Boolean, allowCopy: Boolean, allowEdit: Boolean) {
        val ap = com.tom_roush.pdfbox.pdmodel.encryption.AccessPermission()
        ap.setCanPrint(allowPrint)
        ap.setCanExtractContent(allowCopy)
        ap.setCanModify(allowEdit)
        val policy = com.tom_roush.pdfbox.pdmodel.encryption.StandardProtectionPolicy(ownerPwd.ifEmpty { userPwd + "_dispersio" }, userPwd, ap)
        policy.encryptionKeyLength = 256
        doc.protect(policy)
    }

    fun unprotect(doc: PDDocument) {
        doc.isAllSecurityToBeRemoved = true
    }

    /** Fotos para PDF: uma página por imagem, no tamanho A4 (retrato ou paisagem conforme a foto). */
    fun imagesToPdf(images: List<Bitmap>, dst: File) {
        PDDocument().use { doc ->
            for (bmp in images) {
                val land = bmp.width > bmp.height
                val pw = if (land) 842f else 595f
                val ph = if (land) 595f else 842f
                val page = PDPage(PDRectangle(pw, ph))
                doc.addPage(page)
                val img = com.tom_roush.pdfbox.pdmodel.graphics.image.JPEGFactory.createFromImage(doc, bmp, 0.85f)
                val margin = 18f
                val s = minOf((pw - 2 * margin) / bmp.width, (ph - 2 * margin) / bmp.height)
                val w = bmp.width * s
                val h = bmp.height * s
                PDPageContentStream(doc, page).use { it.drawImage(img, (pw - w) / 2, (ph - h) / 2, w, h) }
            }
            dst.outputStream().buffered().use { doc.save(it) }
        }
    }

    // ------------------------------------------------------------ OCR
    /** Palavra reconhecida: canto inferior esquerdo visual (x,y) em coordenadas do PDF e tamanho visual em pontos. */
    data class OcrWord(val text: String, val x: Float, val y: Float, val w: Float, val h: Float)

    /** Camada de texto invisível sobre a imagem (o PDF passa a ser pesquisável e o texto pode ser copiado). */
    fun ocrLayer(doc: PDDocument, pageIndex: Int, words: List<OcrWord>): List<COSDictionary> {
        if (words.isEmpty()) return emptyList()
        val page = doc.getPage(pageIndex)
        return withContent(doc, page) { cs ->
            val font = loadFont(doc)
            cs.beginText()
            cs.setRenderingMode(com.tom_roush.pdfbox.pdmodel.graphics.state.RenderingMode.NEITHER)
            for (wd in words) {
                val size = (wd.h * 0.85f).coerceAtLeast(2f)
                val natural = runCatching { font.getStringWidth(wd.text) / 1000 * size }.getOrNull() ?: continue
                if (natural <= 0f) continue
                cs.setFont(font, size)
                cs.setHorizontalScaling((100f * wd.w / natural).coerceIn(20f, 400f))
                cs.setTextMatrix(upright(page, wd.x, wd.y + wd.h * 0.18f))
                runCatching { cs.showText(wd.text) }
            }
            cs.endText()
        }
    }

    // ------------------------------------------------------------ tarja definitiva
    /**
     * Substitui o conteúdo da página por uma imagem dela já com as tarjas pretas: o que estava embaixo
     * deixa de existir no arquivo. [image] = página renderizada (orientação de exibição) com as tarjas.
     * Remove os comentários que ficavam sob as tarjas (pdfRects = tarjas em coordenadas do PDF).
     */
    fun redactPage(doc: PDDocument, pageIndex: Int, image: Bitmap, pdfRects: List<RectF>) {
        val page = doc.getPage(pageIndex)
        val box = page.cropBox
        val rot = ((page.rotation % 360) + 360) % 360
        val img = com.tom_roush.pdfbox.pdmodel.graphics.image.JPEGFactory.createFromImage(doc, image, 0.9f)
        page.resources = com.tom_roush.pdfbox.pdmodel.PDResources()
        PDPageContentStream(doc, page, PDPageContentStream.AppendMode.OVERWRITE, true, true).use { cs ->
            val (vw, vh) = if (rot % 180 == 0) box.width to box.height else box.height to box.width
            val m = when (rot) {
                90 -> Matrix(0f, 1f, -1f, 0f, box.upperRightX, box.lowerLeftY)
                180 -> Matrix(-1f, 0f, 0f, -1f, box.upperRightX, box.upperRightY)
                270 -> Matrix(0f, -1f, 1f, 0f, box.lowerLeftX, box.upperRightY)
                else -> Matrix(1f, 0f, 0f, 1f, box.lowerLeftX, box.lowerLeftY)
            }
            cs.transform(m)
            cs.drawImage(img, 0f, 0f, vw, vh)
        }
        // comentários e campos sob as tarjas
        val arr = page.cosObject.getDictionaryObject(COSName.ANNOTS) as? COSArray
        if (arr != null) {
            for (k in arr.size() - 1 downTo 0) {
                val d = arr.getObject(k) as? COSDictionary ?: continue
                val r = (d.getDictionaryObject(COSName.RECT) as? COSArray)?.toFloatArray() ?: continue
                val ar = RectF(minOf(r[0], r[2]), maxOf(r[1], r[3]), maxOf(r[0], r[2]), minOf(r[1], r[3]))
                if (pdfRects.any { t -> minOf(t.right, ar.right) > maxOf(t.left, ar.left) && minOf(t.top, ar.top) > maxOf(t.bottom, ar.bottom) }) arr.remove(k)
            }
        }
    }
}
