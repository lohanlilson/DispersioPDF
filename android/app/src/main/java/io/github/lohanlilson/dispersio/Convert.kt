package io.github.lohanlilson.dispersio

import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.os.Build
import android.provider.MediaStore
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.io.OutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/** OCR com o reconhecimento de texto do Google (no aparelho). */
object Ocr {
    private val recognizer by lazy { TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS) }

    /** Reconhece as palavras de uma página. Devolve posições em frações da largura exibida (l, t, r, b). */
    suspend fun page(engine: PdfEngine, pdf: OpenPdf, i: Int): List<Pair<String, FracRect>> {
        val w = 2000
        val bmp = engine.render(pdf, i, w)
        val res = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            Tasks.await(recognizer.process(InputImage.fromBitmap(bmp, 0)))
        }
        val out = ArrayList<Pair<String, FracRect>>()
        for (b in res.textBlocks) for (l in b.lines) for (e in l.elements) {
            val r = e.boundingBox ?: continue
            out += e.text to FracRect(r.left / w.toFloat(), r.top / w.toFloat(), r.right / w.toFloat(), r.bottom / w.toFloat())
        }
        return out
    }
}

/** Conversões: texto, Word (.docx), Excel (.xlsx) e imagens. */
object Convert {
    private fun esc(s: String) = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace(Regex("[\\u0000-\\u0008\\u000B\\u000C\\u000E-\\u001F]"), "")

    private fun zip(out: OutputStream, files: Map<String, String>) {
        ZipOutputStream(out).use { z ->
            for ((name, content) in files) {
                z.putNextEntry(ZipEntry(name))
                z.write(content.toByteArray(Charsets.UTF_8))
                z.closeEntry()
            }
        }
    }

    /** Word: um parágrafo por linha, quebra de página entre as páginas do PDF. */
    fun docx(pages: List<String>, out: OutputStream) {
        val body = StringBuilder()
        pages.forEachIndexed { i, p ->
            p.split("\n").forEach { line ->
                body.append("<w:p><w:r><w:t xml:space=\"preserve\">").append(esc(line.trimEnd('\r'))).append("</w:t></w:r></w:p>")
            }
            if (i < pages.size - 1) body.append("<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>")
        }
        zip(out, mapOf(
            "[Content_Types].xml" to """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>""",
            "_rels/.rels" to """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>""",
            "word/document.xml" to """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>$body<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="0" w:footer="0" w:gutter="0"/></w:sectPr></w:body></w:document>""",
        ))
    }

    private fun colName(i: Int): String {
        var n = i + 1
        val sb = StringBuilder()
        while (n > 0) { val r = (n - 1) % 26; sb.insert(0, ('A' + r)); n = (n - 1) / 26 }
        return sb.toString()
    }

    /** Número no formato brasileiro (1.234,56 / R$ 10,00 / 15%) -> Double. */
    fun brNumber(s: String): Double? {
        val t = s.trim().removePrefix("R$").trim().removeSuffix("%").trim()
        if (!Regex("^-?\\d{1,3}(\\.\\d{3})*(,\\d+)?$|^-?\\d+(,\\d+)?$").matches(t)) return null
        return t.replace(".", "").replace(",", ".").toDoubleOrNull()
    }

    /** Excel: uma planilha por página; colunas separadas por 2+ espaços ou tabulação; números viram números. */
    fun xlsx(pages: List<String>, out: OutputStream) =
        xlsxTables(pages.mapIndexed { i, p ->
            "Página ${i + 1}" to p.split("\n").map { it.trimEnd('\r') }.filter { it.isNotBlank() }.map { it.trim().split(Regex("\\t|\\s{2,}")) }
        }, out, header = false)

    /** Valor de célula do Excel: (xml da célula sem a referência, estilo). Datas viram datas, R$ e % viram números;
     *  CPF, CNPJ, códigos, telefones e números com zero à esquerda continuam texto. */
    fun cell(ref: String, raw: String, header: Boolean = false): String {
        val v = raw.trim()
        fun text(st: Int = 0) = "<c r=\"$ref\" t=\"inlineStr\"${if (st > 0) " s=\"$st\"" else ""}><is><t xml:space=\"preserve\">${esc(v)}</t></is></c>"
        if (header) return text(5)
        if (v.isEmpty()) return ""
        Regex("^(\\d{1,2})/(\\d{1,2})/(\\d{4}|\\d{2})$").find(v)?.let { m ->
            val (d, mo, y0) = m.destructured
            val y = y0.toInt().let { if (it < 100) it + 2000 else it }
            val date = runCatching { java.time.LocalDate.of(y, mo.toInt(), d.toInt()) }.getOrNull() ?: return text()
            val serial = java.time.temporal.ChronoUnit.DAYS.between(java.time.LocalDate.of(1899, 12, 30), date)
            return "<c r=\"$ref\" s=\"1\"><v>$serial</v></c>"
        }
        val digits = v.filter { it.isDigit() }
        val codeLike = Regex("^[\\d.\\-/() ]+$").matches(v) && ((v.startsWith("0") && digits.length > 1) || digits.length >= 11 ||
            (Regex("\\d[.\\-/]\\d{3}[.\\-/]|\\d-\\d").containsMatchIn(v) && !Regex("^-?\\d{1,3}(\\.\\d{3})+(,\\d+)?$").matches(v)))
        if (codeLike) return text()
        Regex("^(-)?\\s*R\\$\\s*(-)?\\s*([\\d.]+(,\\d+)?)$").find(v)?.let { m ->
            brNumber(m.groupValues[3])?.let { n -> return "<c r=\"$ref\" s=\"2\"><v>${if (m.groupValues[1].isNotEmpty() || m.groupValues[2].isNotEmpty()) -n else n}</v></c>" }
        }
        if (v.endsWith("%")) brNumber(v)?.let { return "<c r=\"$ref\" s=\"3\"><v>${it / 100}</v></c>" }
        brNumber(v)?.let { return "<c r=\"$ref\"${if (',' in v) " s=\"4\"" else ""}><v>$it</v></c>" }
        return text()
    }

    private const val STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="2"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/><numFmt numFmtId="165" formatCode="&quot;R$&quot; #,##0.00"/></numFmts><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFDCE6F2"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="6"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="10" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>"""

    /** Excel a partir de tabelas: uma aba por tabela, primeira linha em negrito, larguras ajustadas. */
    fun xlsxTables(tables: List<Pair<String, List<List<String>>>>, out: OutputStream, header: Boolean = true) {
        val sheets = tables.mapIndexed { si, (_, grid) ->
            val rows = StringBuilder()
            val widths = HashMap<Int, Int>()
            grid.forEachIndexed { ri, line ->
                rows.append("<row r=\"${ri + 1}\">")
                line.forEachIndexed { ci, c ->
                    rows.append(cell("${colName(ci)}${ri + 1}", c, header && ri == 0 && grid.size > 1))
                    widths[ci] = maxOf(widths[ci] ?: 0, minOf(c.length, 60))
                }
                rows.append("</row>")
            }
            val cols = if (widths.isEmpty()) "" else "<cols>" + widths.toSortedMap().entries.joinToString("") { (c, w) ->
                "<col min=\"${c + 1}\" max=\"${c + 1}\" width=\"${maxOf(8, w + 2)}\" customWidth=\"1\"/>" } + "</cols>"
            val pane = if (header && grid.size > 1) "<sheetViews><sheetView workbookViewId=\"0\"><pane ySplit=\"1\" topLeftCell=\"A2\" activePane=\"bottomLeft\" state=\"frozen\"/></sheetView></sheetViews>" else ""
            "xl/worksheets/sheet${si + 1}.xml" to """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">$pane$cols<sheetData>$rows</sheetData></worksheet>"""
        }
        val n = sheets.size
        val ct = (1..n).joinToString("") { """<Override PartName="/xl/worksheets/sheet$it.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>""" }
        val wbSheets = tables.mapIndexed { i, (name, _) -> """<sheet name="${esc(name.take(31).replace(Regex("[\\\\/?*\\[\\]:]"), " "))}" sheetId="${i + 1}" r:id="rId${i + 1}"/>""" }.joinToString("")
        val wbRels = (1..n).joinToString("") { """<Relationship Id="rId$it" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet$it.xml"/>""" } +
            """<Relationship Id="rId${n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>"""
        zip(out, mapOf(
            "[Content_Types].xml" to """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>$ct</Types>""",
            "_rels/.rels" to """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>""",
            "xl/workbook.xml" to """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>$wbSheets</sheets></workbook>""",
            "xl/_rels/workbook.xml.rels" to """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">$wbRels</Relationships>""",
            "xl/styles.xml" to STYLES,
        ) + sheets.toMap())
    }

    /** Salva as páginas como JPG em Imagens/Dispersio PDF (aparecem na galeria). Devolve quantas foram salvas. */
    suspend fun images(ctx: Context, engine: PdfEngine, pdf: OpenPdf, baseName: String, onPage: (Int) -> Unit): Int {
        var n = 0
        for (i in 0 until pdf.sizes.size) {
            onPage(i)
            val bmp = engine.render(pdf, i, 1654)
            val values = ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, "${baseName}_pagina${i + 1}.jpg")
                put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                if (Build.VERSION.SDK_INT >= 29) put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/Dispersio PDF")
            }
            val uri = ctx.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: continue
            ctx.contentResolver.openOutputStream(uri)?.use { bmp.compress(Bitmap.CompressFormat.JPEG, 90, it) }
            n++
        }
        return n
    }
}
