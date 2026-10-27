package io.github.lohanlilson.dispersio

import android.graphics.RectF

/** Palavra com a página e a posição na tela (frações da largura da página). */
data class PWord(val text: String, val page: Int, val frac: FracRect)

/** Alteração entre duas versões. */
data class Change(val kind: String, val textA: String, val textB: String, val pageA: Int, val pageB: Int,
                  val rectsA: List<Pair<Int, FracRect>>, val rectsB: List<Pair<Int, FracRect>>,
                  val anchorA: Pair<Int, FracRect>?, val anchorB: Pair<Int, FracRect>?)

object Compare {
    /** Palavras do documento em ordem de leitura. */
    suspend fun words(engine: PdfEngine, pdf: OpenPdf): List<PWord> {
        val out = ArrayList<PWord>()
        for (p in 0 until pdf.sizes.size) {
            // caracteres da página já com a posição na tela (uma leitura por página)
            val pc = engine.pageChars(pdf, p)
            var sb = StringBuilder(); var boxes = ArrayList<FracRect>()
            fun flush() {
                if (sb.isNotBlank() && boxes.isNotEmpty()) {
                    out += PWord(sb.toString(), p, FracRect(boxes.minOf { it.l }, boxes.minOf { it.t }, boxes.maxOf { it.r }, boxes.maxOf { it.b }))
                }
                sb = StringBuilder(); boxes = ArrayList()
            }
            for (k in 0 until pc.size) {
                val c = pc.text[k]
                if (c.isWhitespace() || c == '\u0000') flush() else { sb.append(c); pc.frac[k]?.let { boxes += it } }
            }
            flush()
        }
        return out
    }

    /** Diferença de Myers (sequências de palavras). Devolve operações (tipo, a0, a1, b0, b1). */
    private fun diff(a: List<String>, b: List<String>): List<IntArray> {
        val n = a.size; val m = b.size; val max = n + m
        val v = IntArray(2 * max + 2)
        val trace = ArrayList<IntArray>()
        var found = false
        loop@ for (d in 0..max) {
            trace += v.copyOf()
            var k = -d
            while (k <= d) {
                var x = if (k == -d || (k != d && v[k - 1 + max] < v[k + 1 + max])) v[k + 1 + max] else v[k - 1 + max] + 1
                var y = x - k
                while (x < n && y < m && a[x] == b[y]) { x++; y++ }
                v[k + max] = x
                if (x >= n && y >= m) { found = true; break@loop }
                k += 2
            }
            if (d > 20000) break
        }
        if (!found) return listOf(intArrayOf(2, 0, n, 0, m))
        // reconstrói o caminho
        val moves = ArrayList<IntArray>()   // (x0,y0,x1,y1) passos
        var x = n; var y = m
        for (d in trace.size - 1 downTo 1) {
            val vv = trace[d]
            val k = x - y
            val prevK = if (k == -d || (k != d && vv[k - 1 + max] < vv[k + 1 + max])) k + 1 else k - 1
            val prevX = vv[prevK + max]; val prevY = prevX - prevK
            while (x > prevX && y > prevY) { x--; y-- }
            moves += intArrayOf(prevX, prevY, x, y)
            x = prevX; y = prevY
        }
        moves.reverse()
        // agrupa inserções/remoções consecutivas em blocos
        val ops = ArrayList<IntArray>()   // tipo 0 = removido, 1 = inserido, 2 = alterado
        var ca = -1; var cb = -1; var a0 = 0; var a1 = 0; var b0 = 0; var b1 = 0
        fun close() { if (ca >= 0 || cb >= 0) { ops += intArrayOf(if (a1 > a0 && b1 > b0) 2 else if (a1 > a0) 0 else 1, a0, a1, b0, b1) }; ca = -1; cb = -1 }
        for (mv in moves) {
            val (px, py, nx, ny) = mv.toList()
            // passo diagonal antes deste movimento já consumido acima; aqui só 1 passo horizontal ou vertical
            if (nx == px + 1 && ny == py) {
                if (ca < 0 && cb < 0) { a0 = px; b0 = py; a1 = px; b1 = py; ca = 0 }
                if (px != a1 || py != b1) { close(); a0 = px; b0 = py; a1 = px; b1 = py; ca = 0 }
                a1 = nx
            } else if (ny == py + 1 && nx == px) {
                if (ca < 0 && cb < 0) { a0 = px; b0 = py; a1 = px; b1 = py; cb = 0 }
                if (px != a1 || py != b1) { close(); a0 = px; b0 = py; a1 = px; b1 = py; cb = 0 }
                b1 = ny
            }
        }
        close()
        return ops
    }

    fun changes(a: List<PWord>, b: List<PWord>): List<Change> {
        val ops = diff(a.map { it.text }, b.map { it.text })
        return ops.map { (t, a0, a1, b0, b1) ->
            val ra = a.subList(a0, a1); val rb = b.subList(b0, b1)
            Change(
                when (t) { 0 -> "removido"; 1 -> "inserido"; else -> "alterado" },
                ra.joinToString(" ") { it.text }, rb.joinToString(" ") { it.text },
                ra.firstOrNull()?.page ?: a.getOrNull(minOf(a0, a.size - 1))?.page ?: 0,
                rb.firstOrNull()?.page ?: b.getOrNull(minOf(b0, b.size - 1))?.page ?: 0,
                ra.map { it.page to it.frac }, rb.map { it.page to it.frac },
                if (ra.isEmpty()) a.getOrNull(minOf(a0, a.size - 1))?.let { it.page to it.frac } else null,
                if (rb.isEmpty()) b.getOrNull(minOf(b0, b.size - 1))?.let { it.page to it.frac } else null,
            )
        }
    }

    private operator fun IntArray.component5() = this[4]
}
