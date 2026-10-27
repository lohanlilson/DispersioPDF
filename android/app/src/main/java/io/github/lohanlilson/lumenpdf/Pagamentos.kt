package io.github.lohanlilson.lumenpdf

import android.graphics.Bitmap
import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.MultiFormatReader
import com.google.zxing.RGBLuminanceSource
import com.google.zxing.common.HybridBinarizer
import com.google.zxing.multi.GenericMultipleBarcodeReader
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Locale

/**
 * Boletos, Pix e chaves de NF-e/CT-e encontrados no documento: conferidos e prontos para copiar.
 * Mesmas regras do programa do computador (lumenpdf/pagamentos.py).
 */
data class PayItem(
    val kind: String,              // boleto | arrecadacao | pix | nfe
    val page: Int,
    val copy: String,
    val title: String,
    val details: List<Pair<String, String>>,
    var ok: Boolean = true,
    var problem: String = "",
    var source: String = "texto",  // texto | código | texto e código
    val key: String = "",
) {
    val copyLabel get() = when (kind) {
        "pix" -> "Copiar Pix copia e cola"
        "nfe" -> "Copiar chave de acesso"
        else -> "Copiar linha digitável"
    }
    val summary get() = details.toMap().let { d -> listOfNotNull(d["Valor"], d["Vencimento"], d["Recebedor"], d["Emitente"]).joinToString(" · ") }
}

object Pagamentos {
    val BANCOS = mapOf(
        "001" to "Banco do Brasil", "003" to "Banco da Amazônia", "004" to "Banco do Nordeste", "021" to "Banestes",
        "033" to "Santander", "037" to "Banpará", "041" to "Banrisul", "047" to "Banese", "070" to "BRB", "077" to "Inter",
        "084" to "Uniprime Norte do Paraná", "085" to "Ailos", "097" to "Credisis", "104" to "Caixa Econômica Federal",
        "133" to "Cresol", "136" to "Unicred", "197" to "Stone", "208" to "BTG Pactual", "212" to "Banco Original",
        "218" to "BS2", "237" to "Bradesco", "260" to "Nubank", "290" to "PagBank", "323" to "Mercado Pago",
        "336" to "C6 Bank", "341" to "Itaú", "380" to "PicPay", "389" to "Mercantil do Brasil", "403" to "Cora",
        "422" to "Safra", "633" to "Rendimento", "655" to "Votorantim", "707" to "Daycoval", "741" to "Ribeirão Preto",
        "745" to "Citibank", "746" to "Modal", "748" to "Sicredi", "756" to "Sicoob",
    )
    private val SEGMENTOS = mapOf('1' to "Prefeitura", '2' to "Saneamento", '3' to "Energia elétrica e gás",
        '4' to "Telecomunicações", '5' to "Órgão governamental", '6' to "Carnê ou assemelhado", '7' to "Multa de trânsito",
        '9' to "Uso do banco")
    private val UFS = mapOf("11" to "RO", "12" to "AC", "13" to "AM", "14" to "RR", "15" to "PA", "16" to "AP", "17" to "TO",
        "21" to "MA", "22" to "PI", "23" to "CE", "24" to "RN", "25" to "PB", "26" to "PE", "27" to "AL", "28" to "SE",
        "29" to "BA", "31" to "MG", "32" to "ES", "33" to "RJ", "35" to "SP", "41" to "PR", "42" to "SC", "43" to "RS",
        "50" to "MS", "51" to "MT", "52" to "GO", "53" to "DF")
    private val MODELOS = mapOf("55" to "NF-e", "65" to "NFC-e", "57" to "CT-e", "67" to "CT-e OS", "58" to "MDF-e",
        "62" to "NFCom", "66" to "NF3e")

    // ------------------------------------------------------------------ dígitos verificadores
    fun mod10(num: String): Int {
        var s = 0; var w = 2
        for (c in num.reversed()) { val p = (c - '0') * w; s += p / 10 + p % 10; w = 3 - w }
        return (10 - s % 10) % 10
    }

    fun mod11Boleto(num: String): Int {
        var s = 0; var w = 2
        for (c in num.reversed()) { s += (c - '0') * w; w = if (w == 9) 2 else w + 1 }
        val dv = 11 - s % 11
        return if (dv == 0 || dv == 10 || dv == 11) 1 else dv
    }

    /** Resto 0 ou 1 vira 0 (arrecadação e chave de acesso). Aceita letras (CNPJ alfanumérico): valor = código ASCII − 48. */
    fun mod11Zero(num: String): Int {
        var s = 0; var w = 2
        for (c in num.reversed()) { s += (c.code - 48) * w; w = if (w == 9) 2 else w + 1 }
        val r = s % 11
        return if (r == 0 || r == 1) 0 else 11 - r
    }

    fun crc16(data: String): String {
        var crc = 0xFFFF
        for (b in data.toByteArray(Charsets.UTF_8)) {
            crc = crc xor ((b.toInt() and 0xFF) shl 8)
            repeat(8) { crc = if (crc and 0x8000 != 0) (crc shl 1) xor 0x1021 else crc shl 1; crc = crc and 0xFFFF }
        }
        return "%04X".format(crc)
    }

    fun money(cents: Long): String {
        val s = "%,.2f".format(Locale.US, cents / 100.0)
        return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")
    }

    private fun fmtCnpj(s: String) = if (s.length == 14) "${s.substring(0, 2)}.${s.substring(2, 5)}.${s.substring(5, 8)}/${s.substring(8, 12)}-${s.substring(12)}" else s

    /** Fator de vencimento: dias desde 07/10/1997; em 22/02/2025 voltou a 1000 (base nova 29/05/2022). */
    fun dueDate(fator: Int, today: LocalDate = LocalDate.now()): LocalDate? {
        if (fator == 0) return null
        val c = listOf(LocalDate.of(1997, 10, 7).plusDays(fator.toLong()), LocalDate.of(2022, 5, 29).plusDays(fator.toLong()))
        return c.minBy { kotlin.math.abs(ChronoUnit.DAYS.between(today, it)) }
    }

    private val DATE = DateTimeFormatter.ofPattern("dd/MM/yyyy")
    private fun String.isDigits() = isNotEmpty() && all { it in '0'..'9' }

    // ------------------------------------------------------------------ boleto bancário
    fun boletoBarcodeOk(bc: String) = bc.length == 44 && bc.isDigits() && bc[0] != '8' &&
        (bc[4] - '0') == mod11Boleto(bc.substring(0, 4) + bc.substring(5))

    fun lineToBarcode(ld: String) = ld.substring(0, 4) + ld[32] + ld.substring(33, 47) + ld.substring(4, 9) + ld.substring(10, 20) + ld.substring(21, 31)

    fun barcodeToLine(bc: String): String {
        val livre = bc.substring(19)
        val c1 = bc.substring(0, 4) + livre.substring(0, 5)
        val c2 = livre.substring(5, 15)
        val c3 = livre.substring(15, 25)
        return c1 + mod10(c1) + c2 + mod10(c2) + c3 + mod10(c3) + bc[4] + bc.substring(5, 19)
    }

    fun fmtBoleto(ld: String) = "${ld.substring(0, 5)}.${ld.substring(5, 10)} ${ld.substring(10, 15)}.${ld.substring(15, 21)} " +
        "${ld.substring(21, 26)}.${ld.substring(26, 32)} ${ld[32]} ${ld.substring(33, 47)}"

    fun checkBoletoLine(ld: String): String {
        val bad = listOf(0 to 9, 10 to 20, 21 to 31).mapIndexedNotNull { n, (a, b) -> if (mod10(ld.substring(a, b)) != ld[b] - '0') n + 1 else null }
        if (bad.isNotEmpty()) return "Dígito errado no " + bad.joinToString(" e ") { "${it}º" } + " campo da linha digitável"
        if (!boletoBarcodeOk(lineToBarcode(ld))) return "O dígito verificador geral não confere (o número foi alterado ou digitado errado)"
        return ""
    }

    fun boletoItem(page: Int, ld: String, today: LocalDate = LocalDate.now()): PayItem {
        val bc = lineToBarcode(ld)
        val banco = BANCOS[ld.substring(0, 3)]
        val det = ArrayList<Pair<String, String>>()
        det += "Banco" to (if (banco != null) "${ld.substring(0, 3)} – $banco" else ld.substring(0, 3))
        val valor = bc.substring(9, 19).toLong()
        det += "Valor" to (if (valor > 0) money(valor) else "não informado (preencher na hora de pagar)")
        dueDate(bc.substring(5, 9).toInt(), today)?.let { det += "Vencimento" to it.format(DATE) }
        det += "Linha digitável" to fmtBoleto(ld)
        val problem = checkBoletoLine(ld)
        return PayItem("boleto", page, ld, if (banco != null) "Boleto $banco" else "Boleto", det, problem.isEmpty(), problem, key = bc)
    }

    // ------------------------------------------------------------------ arrecadação
    private fun arrecMod(c: Char): (String) -> Int = if (c == '6' || c == '7') ::mod10 else ::mod11Zero

    fun arrecBarcodeOk(bc: String) = bc.length == 44 && bc.isDigits() && bc[0] == '8' && bc[2] in "6789" &&
        (bc[3] - '0') == arrecMod(bc[2])(bc.substring(0, 3) + bc.substring(4))

    fun arrecLineToBarcode(ld: String) = (0 until 4).joinToString("") { ld.substring(it * 12, it * 12 + 11) }
    fun arrecBarcodeToLine(bc: String): String {
        val m = arrecMod(bc[2])
        return (0 until 4).joinToString("") { val b = bc.substring(it * 11, (it + 1) * 11); b + m(b) }
    }
    fun fmtArrec(ld: String) = (0 until 4).joinToString(" ") { "${ld.substring(it * 12, it * 12 + 11)}-${ld[it * 12 + 11]}" }

    fun checkArrecLine(ld: String): String {
        if (ld[0] != '8' || ld[2] !in "6789") return "não é arrecadação"
        val m = arrecMod(ld[2])
        val bad = (0 until 4).filter { m(ld.substring(it * 12, it * 12 + 11)) != ld[it * 12 + 11] - '0' }.map { it + 1 }
        if (bad.isNotEmpty()) return "Dígito errado no " + bad.joinToString(" e ") { "${it}º" } + " bloco da linha digitável"
        if (!arrecBarcodeOk(arrecLineToBarcode(ld))) return "O dígito verificador geral não confere (o número foi alterado ou digitado errado)"
        return ""
    }

    fun arrecItem(page: Int, ld: String): PayItem {
        val bc = arrecLineToBarcode(ld)
        val seg = SEGMENTOS[bc[1]] ?: "Arrecadação"
        val det = ArrayList<Pair<String, String>>()
        det += "Tipo" to seg
        if (bc[2] == '6' || bc[2] == '8') bc.substring(4, 15).toLong().let { det += "Valor" to (if (it > 0) money(it) else "não informado") }
        det += "Linha digitável" to fmtArrec(ld)
        val problem = checkArrecLine(ld)
        return PayItem("arrecadacao", page, ld, "Conta / tributo – $seg", det, problem.isEmpty(), problem, key = bc)
    }

    // ------------------------------------------------------------------ chave de acesso
    private val CHAVE_RE = Regex("^\\d{6}[0-9A-Z]{12}\\d{2}\\d{2}\\d{3}\\d{9}\\d\\d{8}\\d$")

    fun chaveOk(ch: String): Boolean = ch.length == 44 && CHAVE_RE.matches(ch) && ch.substring(0, 2) in UFS &&
        ch.substring(4, 6).toInt() in 1..12 && ch.substring(20, 22) in MODELOS && (ch[43] - '0') == mod11Zero(ch.substring(0, 43))

    fun chaveItem(page: Int, ch: String): PayItem {
        val mod = MODELOS[ch.substring(20, 22)] ?: "Nota"
        val numero = ch.substring(25, 34).toLong(); val serie = ch.substring(22, 25).toInt()
        val doc = ch.substring(6, 20)
        val emit = if (doc.startsWith("000") && doc.isDigits()) "CPF ${doc.substring(3, 6)}.${doc.substring(6, 9)}.${doc.substring(9, 12)}-${doc.substring(12)}"
            else "CNPJ ${fmtCnpj(doc)}"
        val det = listOf("Emitente" to emit, "Número / série" to "$numero / $serie",
            "Emissão" to "${ch.substring(4, 6)}/20${ch.substring(2, 4)} – ${UFS[ch.substring(0, 2)]}",
            "Chave de acesso" to ch.chunked(4).joinToString(" "))
        val ok = chaveOk(ch)
        return PayItem("nfe", page, ch, "$mod nº $numero", det, ok, if (ok) "" else "O dígito verificador da chave não confere", key = ch)
    }

    // ------------------------------------------------------------------ Pix (BR Code)
    fun parseTlv(s: String): Map<String, String>? {
        val out = LinkedHashMap<String, String>(); var i = 0
        while (i < s.length) {
            if (i + 4 > s.length || !s.substring(i, i + 4).isDigits()) return null
            val tag = s.substring(i, i + 2); val n = s.substring(i + 2, i + 4).toInt()
            if (i + 4 + n > s.length) return null
            out[tag] = s.substring(i + 4, i + 4 + n); i += 4 + n
        }
        return out
    }

    fun pixExtract(text: String): String? {
        var i = 0
        while (i < text.length) {
            if (i + 4 > text.length) return null
            val tag = text.substring(i, i + 2); val n = text.substring(i + 2, i + 4)
            if (!tag.isDigits() || !n.isDigits()) return null
            i += 4 + n.toInt()
            if (i > text.length) return null
            if (tag == "63") return text.substring(0, i)
        }
        return null
    }

    fun pixItem(page: Int, code: String): PayItem? {
        val top = parseTlv(code) ?: return null
        if (top["00"] != "01" || "63" !in top) return null
        val acc = (26..51).firstNotNullOfOrNull { t -> top["%02d".format(t)]?.let { parseTlv(it) }?.takeIf { it["00"]?.lowercase() == "br.gov.bcb.pix" } } ?: return null
        val det = ArrayList<Pair<String, String>>()
        top["59"]?.let { det += "Recebedor" to it.trim() }
        top["60"]?.let { det += "Cidade" to it.trim() }
        val v = top["54"]
        if (v != null) v.toDoubleOrNull()?.let { det += "Valor" to money(Math.round(it * 100)) } else det += "Valor" to "livre (definido na hora de pagar)"
        when {
            acc["01"] != null -> det += "Chave Pix" to acc["01"]!!
            acc["25"] != null -> det += "Cobrança" to "Pix dinâmico (QR do banco)"
        }
        acc["02"]?.let { det += "Mensagem" to it }
        parseTlv(top["62"] ?: "")?.get("05")?.takeIf { it != "***" }?.let { det += "Identificador" to it }
        val ok = crc16(code.dropLast(4)) == code.takeLast(4).uppercase()
        return PayItem("pix", page, code, "Pix", det, ok, if (ok) "" else "O código Pix está incompleto ou foi alterado (CRC não confere)", key = code)
    }

    // ------------------------------------------------------------------ texto
    private val LINE47 = Regex("(?<!\\d)\\d{5}[.\\s]?\\d{5}\\s*\\d{5}[.\\s]?\\d{6}\\s*\\d{5}[.\\s]?\\d{6}\\s*\\d\\s*\\d{14}(?!\\d)")
    private val LINE48 = Regex("(?<!\\d)8\\d{10}[\\s\\-]?\\d\\s*\\d{11}[\\s\\-]?\\d\\s*\\d{11}[\\s\\-]?\\d\\s*\\d{11}[\\s\\-]?\\d(?!\\d)")
    private val DIGITS = Regex("(?<![\\d.\\-])\\d(?:\\d|[ .\\-](?=\\d)){43,60}(?!\\d)")
    private val RUN = Regex("[0-9A-Z](?:[0-9A-Z]|[ .\\-/](?=[0-9A-Z])){43,70}")

    fun findInText(text: String, page: Int = 0, today: LocalDate = LocalDate.now()): List<PayItem> {
        val items = ArrayList<PayItem>(); val used = HashSet<String>()
        fun add(it: PayItem?) {
            if (it == null || it.copy.toSet().size <= 2 || !used.add(it.key)) return
            items += it
        }
        val t = text.replace('\u0000', ' ').replace('\r', '\n')
        LINE48.findAll(t).forEach { m -> val ld = m.value.filter { it.isDigit() }; if (ld.length == 48 && ld[2] in "6789") add(arrecItem(page, ld)) }
        LINE47.findAll(t).forEach { m -> val ld = m.value.filter { it.isDigit() }; if (ld.length == 47) add(boletoItem(page, ld, today)) }
        DIGITS.findAll(t).forEach { m ->
            val s = m.value.filter { it.isDigit() }
            when {
                s.length == 44 && s[3] == '9' && boletoBarcodeOk(s) -> add(boletoItem(page, barcodeToLine(s), today))
                s.length == 44 && arrecBarcodeOk(s) -> add(arrecItem(page, arrecBarcodeToLine(s)))
                s.length == 47 && s[3] == '9' && checkBoletoLine(s).isEmpty() -> add(boletoItem(page, s, today))
                s.length == 48 && s[0] == '8' && checkArrecLine(s).isEmpty() -> add(arrecItem(page, s))
            }
        }
        RUN.findAll(t.uppercase()).forEach { m ->
            val run = m.value.filter { it != ' ' && it != '.' && it != '-' && it != '/' }
            for (a in 0..run.length - 44) run.substring(a, a + 44).let { if (chaveOk(it)) add(chaveItem(page, it)) }
        }
        val flat = t.replace(Regex("\\s*\\n\\s*"), "")
        for (src in listOf(flat, t)) {
            var i = src.indexOf("000201")
            while (i >= 0) {
                pixExtract(src.substring(i))?.let { add(pixItem(page, it)) }
                i = src.indexOf("000201", i + 1)
            }
        }
        return items
    }

    // ------------------------------------------------------------------ códigos desenhados
    fun fromBarcode(format: BarcodeFormat, payload: String, page: Int, today: LocalDate = LocalDate.now()): PayItem? {
        val p = payload.trim()
        if (p.startsWith("000201")) return pixItem(page, p)
        if (p.length == 44 && p.isDigits()) {
            if (format != BarcodeFormat.CODE_128 && boletoBarcodeOk(p)) return boletoItem(page, barcodeToLine(p), today)
            if (format != BarcodeFormat.CODE_128 && arrecBarcodeOk(p)) return arrecItem(page, arrecBarcodeToLine(p))
            if (chaveOk(p)) return chaveItem(page, p)
        }
        return null
    }

    fun decode(bmp: Bitmap): List<Pair<BarcodeFormat, String>> {
        val w = bmp.width; val h = bmp.height
        val px = IntArray(w * h)
        bmp.getPixels(px, 0, w, 0, 0, w, h)
        val hints = mapOf(
            DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE, BarcodeFormat.ITF, BarcodeFormat.CODE_128),
            DecodeHintType.ALLOWED_LENGTHS to intArrayOf(44),
            DecodeHintType.TRY_HARDER to true,
        )
        val reader = GenericMultipleBarcodeReader(MultiFormatReader().apply { setHints(hints) })
        return runCatching {
            reader.decodeMultiple(BinaryBitmap(HybridBinarizer(RGBLuminanceSource(w, h, px))), hints).map { it.barcodeFormat to it.text }
        }.getOrDefault(emptyList())
    }

    /** Junta texto e códigos da página: confirma o que bate e avisa quando a linha digitável difere do código de barras. */
    fun merge(textItems: List<PayItem>, codes: List<PayItem>): List<PayItem> {
        val items = textItems.toMutableList()
        for (it in codes) {
            it.source = "código"
            val twin = items.firstOrNull { x -> x.kind == it.kind && x.key == it.key }
            if (twin != null) { twin.source = "texto e código"; continue }
            if (it.kind == "boleto" || it.kind == "arrecadacao") items.filter { x -> x.kind == it.kind && x.source == "texto" && x.key != it.key }.forEach { x ->
                x.ok = false
                x.problem = "A linha digitável impressa NÃO confere com o código de barras (possível adulteração). Confira com quem emitiu antes de pagar."
            }
            items += it
        }
        return items
    }

    const val IMAGE_PAGES = 10

    suspend fun scan(engine: PdfEngine, pdf: OpenPdf, pages: Int, today: LocalDate = LocalDate.now()): List<PayItem> {
        val out = ArrayList<PayItem>()
        for (p in 0 until pages) {
            kotlinx.coroutines.yield()
            val text = runCatching { engine.pageText(pdf, p) }.getOrDefault("")
            val ti = findInText(text, p, today)
            val codes = if (p < IMAGE_PAGES) {
                val bmp = engine.renderFresh(pdf, p, 1700)
                val found = decode(bmp).mapNotNull { (f, s) -> fromBarcode(f, s, p, today) }
                bmp.recycle()
                found
            } else emptyList()
            out += merge(ti, codes)
        }
        return out
    }
}
