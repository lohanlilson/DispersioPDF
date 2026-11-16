package io.github.lohanlilson.dispersio

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.Typeface
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.TextRecognizer
import com.google.mlkit.vision.text.japanese.JapaneseTextRecognizerOptions
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlin.math.abs

/** Tradução de quadrinhos nos balões (igual à do computador): reconhece o texto, junta em falas, traduz para o
 *  português do Brasil e escreve por cima, centralizado, no maior tamanho que couber. */
object MangaTrad {
    val LANGS = listOf("en" to "Inglês", "es" to "Espanhol", "ja" to "Japonês")

    private val latin by lazy { TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS) }
    private val japanese by lazy { TextRecognition.getClient(JapaneseTextRecognizerOptions.Builder().build()) }
    private fun recognizer(lang: String): TextRecognizer = if (lang == "ja") japanese else latin

    data class Balloon(val rect: Rect, val text: String)

    private fun letters(t: String) = t.count { it.isLetter() }

    /** Falas da página (blocos de texto próximos viram um balão). */
    fun balloons(bmp: Bitmap, lang: String): List<Balloon> {
        val res = Tasks.await(recognizer(lang).process(InputImage.fromBitmap(bmp, 0)))
        val groups = ArrayList<Pair<Rect, MutableList<Pair<Rect, String>>>>()
        val lineH = res.textBlocks.flatMap { it.lines }.mapNotNull { it.boundingBox?.height() }.sorted().let { if (it.isEmpty()) 20 else it[it.size / 2] }
        for (b in res.textBlocks) {
            for (ln in b.lines) {
                val r = ln.boundingBox ?: continue
                val g = groups.firstOrNull { (gr, _) ->
                    r.left <= gr.right + 1.6 * lineH && r.right >= gr.left - 1.6 * lineH && r.top <= gr.bottom + 0.9 * lineH && r.bottom >= gr.top - 0.5 * lineH
                }
                if (g == null) groups += Rect(r) to mutableListOf(r to ln.text) else { g.first.union(r); g.second += r to ln.text }
            }
        }
        return groups.mapNotNull { (rect, lines) ->
            var t = lines.sortedWith(compareBy({ it.first.top / maxOf(1, (lineH * 0.7).toInt()) }, { it.first.left })).joinToString(if (lang == "ja") "" else " ") { it.second }
            t = t.replace(Regex("(\\w)- (\\w)"), "$1$2").replace(Regex("(^|\\s)[|l1](?=\\s+[A-Z'’])"), "$1I")
            if (letters(t) < 2 || (lines.size == 1 && t.length <= 2)) null else Balloon(rect, t)
        }
    }

    // ------------------------------------------------------------------ “tu” → “você” nas falas
    private val TU_VERBS = mapOf(
        "foste" to "foi", "estás" to "está", "tens" to "tem", "és" to "é", "vais" to "vai", "podes" to "pode", "queres" to "quer",
        "sabes" to "sabe", "fazes" to "faz", "dizes" to "diz", "vens" to "vem", "viste" to "viu", "fizeste" to "fez", "disseste" to "disse",
        "tiveste" to "teve", "estavas" to "estava", "eras" to "era", "tinhas" to "tinha", "precisas" to "precisa", "achas" to "acha",
        "pensas" to "pensa", "gostas" to "gosta", "falas" to "fala", "entendes" to "entende", "lembras" to "lembra", "conheces" to "conhece",
        "acreditas" to "acredita", "deves" to "deve", "ficas" to "fica", "serás" to "será", "terás" to "terá", "chegaste" to "chegou",
        "deixaste" to "deixou", "voltaste" to "voltou", "perdeste" to "perdeu")
    private val TU_SUBJ = mapOf("mintas" to "minta", "faças" to "faça", "digas" to "diga", "vás" to "vá", "sejas" to "seja",
        "tenhas" to "tenha", "estejas" to "esteja", "venhas" to "venha", "morras" to "morra", "fujas" to "fuja", "olhes" to "olhe",
        "chores" to "chore", "desistas" to "desista", "esqueças" to "esqueça", "saias" to "saia", "fales" to "fale")
    private val TU_WORDS = listOf("contigo" to "com você", "teu" to "seu", "tua" to "sua", "teus" to "seus", "tuas" to "suas",
        "a ti" to "a você", "para ti" to "para você", "de ti" to "de você", "por ti" to "por você")

    private fun case(src: String, dst: String) = if (src.firstOrNull()?.isUpperCase() == true) dst.replaceFirstChar { it.uppercase() } else dst

    fun dialogBr(text: String): String {
        var t = Regex("\\b[Tt]u\\b").replace(text) { case(it.value, "você") }
        for ((a, b) in TU_SUBJ) t = Regex("\\b$a\\b", RegexOption.IGNORE_CASE).replace(t) { case(it.value, b) }
        for ((a, b) in TU_VERBS) t = Regex("\\b(você\\s+)?$a\\b", RegexOption.IGNORE_CASE).replace(t) { m ->
            if (m.groupValues[1].isNotEmpty()) m.groupValues[1] + b else case(m.value, "você $b")
        }
        for ((a, b) in TU_WORDS) t = Regex("\\b$a\\b", RegexOption.IGNORE_CASE).replace(t) { case(it.value, b) }
        return t.replace(Regex("\\s+"), " ").trim()
    }

    // ------------------------------------------------------------------ desenho
    private fun bgColor(bmp: Bitmap, r: Rect): Int {
        val pts = ArrayList<Int>()
        val x0 = r.left.coerceIn(0, bmp.width - 1); val x1 = r.right.coerceIn(0, bmp.width - 1)
        val y0 = r.top.coerceIn(0, bmp.height - 1); val y1 = r.bottom.coerceIn(0, bmp.height - 1)
        val sx = maxOf(1, (x1 - x0) / 12); val sy = maxOf(1, (y1 - y0) / 12)
        for (x in x0..x1 step sx) { pts += bmp.getPixel(x, y0); pts += bmp.getPixel(x, y1) }
        for (y in y0..y1 step sy) { pts += bmp.getPixel(x0, y); pts += bmp.getPixel(x1, y) }
        if (pts.isEmpty()) return Color.WHITE
        val bin = pts.groupBy { Color.red(it) / 24 * 10000 + Color.green(it) / 24 * 100 + Color.blue(it) / 24 }.maxBy { it.value.size }.value
        return Color.rgb(bin.map { Color.red(it) }.average().toInt(), bin.map { Color.green(it) }.average().toInt(), bin.map { Color.blue(it) }.average().toInt())
    }

    private fun near(c: Int, bg: Int) = abs(Color.red(c) - Color.red(bg)) + abs(Color.green(c) - Color.green(bg)) + abs(Color.blue(c) - Color.blue(bg)) <= 40

    /** Área livre do balão a partir da área do texto (anda enquanto a cor é a do fundo); 66% disso (balão oval). */
    private fun balloonBox(bmp: Bitmap, r: Rect, bg: Int): Rect {
        val cx = r.centerX(); val cy = r.centerY()
        fun run(x0: Int, y0: Int, dx: Int, dy: Int): Int {
            var x = x0; var y = y0; var n = 0
            while (n < 3000) {
                val nx = x + dx; val ny = y + dy
                if (nx !in 0 until bmp.width || ny !in 0 until bmp.height || !near(bmp.getPixel(nx, ny), bg)) break
                x = nx; y = ny; n++
            }
            return if (dx != 0) x else y
        }
        val l = run(r.left, cy, -1, 0); val rt = run(r.right, cy, 1, 0)
        val t = run(cx, r.top, 0, -1); val b = run(cx, r.bottom, 0, 1)
        val w = ((rt - l) * 0.66f).toInt(); val h = ((b - t) * 0.66f).toInt()
        val mx = (l + rt) / 2; val my = (t + b) / 2
        val box = Rect(mx - w / 2, my - h / 2, mx + w / 2, my + h / 2)
        if (box.width() < r.width() || box.height() < r.height() || box.width() > bmp.width * 0.7) return Rect(r)
        box.union(r)
        return box
    }

    private fun layout(text: String, paint: TextPaint, w: Int) =
        StaticLayout.Builder.obtain(text, 0, text.length, paint, maxOf(1, w)).setAlignment(Layout.Alignment.ALIGN_CENTER).setLineSpacing(0f, 1.1f).build()

    /** Página traduzida: uma cópia da imagem com as falas em português. */
    suspend fun translate(src: Bitmap, lang: String): Bitmap {
        val list = balloons(src, lang)
        val out = src.copy(Bitmap.Config.ARGB_8888, true)
        if (list.isEmpty()) return out
        val c = Canvas(out)
        val fill = Paint().apply { style = Paint.Style.FILL }
        for (b in list) {
            val tr = runCatching { dialogBr(Traducao.translate(lang, "pt", b.text)) }.getOrNull() ?: continue
            if (tr.isBlank() || tr == b.text) continue
            val cover = Rect(b.rect.left - 4, b.rect.top - 3, b.rect.right + 4, b.rect.bottom + 3)
            val bg = bgColor(src, Rect(cover.left - 2, cover.top - 2, cover.right + 2, cover.bottom + 2))
            fill.color = bg
            c.drawRect(cover, fill)
            var box = balloonBox(out, cover, bg)
            if (box.height() > 2.2f * box.width()) {          // texto vertical (japonês): alarga
                val w = minOf(out.width * 0.4f, box.height() * 0.8f).toInt()
                box = Rect(box.centerX() - w / 2, box.top, box.centerX() + w / 2, box.bottom)
            }
            val lum = 0.3 * Color.red(bg) + 0.59 * Color.green(bg) + 0.11 * Color.blue(bg)
            val paint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { typeface = Typeface.DEFAULT_BOLD; color = if (lum > 128) Color.BLACK else Color.WHITE }
            var size = minOf(box.height() / 2f, out.width / 18f)
            var lay = run { paint.textSize = size; layout(tr, paint, box.width()) }
            while ((lay.height > box.height() || (0 until lay.lineCount).any { lay.getLineWidth(it) > box.width() + 1 }) && size > 7f) {
                size *= 0.92f; paint.textSize = size; lay = layout(tr, paint, box.width())
            }
            c.save()
            c.translate(box.left.toFloat(), box.top + (box.height() - lay.height) / 2f)
            lay.draw(c)
            c.restore()
        }
        return out
    }
}
