package io.github.lohanlilson.dispersio

/** Reconstrói tabelas pela posição do texto (igual ao do computador): seleção de linha inteira e exportação para Excel.
 *  Coordenadas em fração da página (0..1). */
object Tabela {
    const val CELL_MAX = 0.35f

    class Seg(val a: Int, val b: Int, val x0: Float, val y0: Float, val x1: Float, val y1: Float, val text: String) {
        val h get() = maxOf(y1 - y0, 0.001f)
        val cy get() = (y0 + y1) / 2
    }

    /** Trechos contínuos de linha (um espaço grande separa colunas). Devolve (trechos, trecho de cada caractere). */
    fun segments(text: String, frac: Array<FracRect?>): Pair<List<Seg>, IntArray> {
        val of = IntArray(frac.size) { -1 }
        val out = ArrayList<Seg>()
        var run = ArrayList<Int>()
        fun flush() {
            if (run.isEmpty()) return
            val fs = run.map { frac[it]!! }
            val a = run.first(); val b = run.last()
            val s = Seg(a, b, fs.minOf { it.l }, fs.minOf { it.t }, fs.maxOf { it.r }, fs.maxOf { it.b },
                text.substring(a, minOf(b + 1, text.length)).replace(Regex("\\s+"), " ").trim())
            for (k in a..b) of[k] = out.size
            out += s
            run = ArrayList()
        }
        for (k in frac.indices) {
            val f = frac[k] ?: continue
            val last = run.lastOrNull()?.let { frac[it] }
            if (last != null) {
                val h = maxOf(f.b - f.t, last.b - last.t)
                val same = kotlin.math.abs((f.t + f.b) / 2 - (last.t + last.b) / 2) < h * 0.6f
                if (!same || f.l < last.l - h || f.l - last.r > 2.5f * h) flush()
            }
            run += k
        }
        flush()
        return out to of
    }

    private fun xover(a: Seg, b: Seg, tol: Float = 0.002f) = a.x0 - tol <= b.x1 && b.x0 - tol <= a.x1

    private fun <T> cluster(items: List<T>, lo: (T) -> Float, hi: (T) -> Float): List<List<T>> {
        val out = ArrayList<ArrayList<T>>()
        var top = 0f
        for (it in items.sortedBy(lo)) {
            if (out.isNotEmpty() && lo(it) <= top) { out.last() += it; top = maxOf(top, hi(it)) }
            else { out += arrayListOf(it); top = hi(it) }
        }
        return out
    }

    fun grid(segs: List<Seg>): List<List<String>> {
        if (segs.isEmpty()) return emptyList()
        val cols = cluster(segs, { it.x0 }, { it.x1 })
        val cells = ArrayList<Pair<Int, List<Seg>>>()
        cols.forEachIndexed { ci, c0 ->
            val c = c0.sortedWith(compareBy({ it.y0 }, { it.x0 }))
            var cur = arrayListOf(c[0])
            for (s in c.drop(1)) {
                val p = cur.last()
                val sameLine = kotlin.math.abs(s.cy - p.cy) <= 0.3f * p.h
                if (sameLine || s.y0 - p.y1 < 0.7f * minOf(s.h, p.h)) cur += s
                else { cells += ci to cur; cur = arrayListOf(s) }
            }
            cells += ci to cur
        }
        data class Span(val y0: Float, val y1: Float, val ci: Int, val cs: List<Seg>)
        val spans = cells.map { (ci, cs) -> Span(cs.minOf { it.y0 }, cs.maxOf { it.y1 }, ci, cs) }
        val rows = cluster(spans, { it.y0 + 0.15f * (it.y1 - it.y0) }, { it.y1 - 0.15f * (it.y1 - it.y0) })
        val table = rows.map { row ->
            val line = Array(cols.size) { "" }
            for (sp in row.sortedBy { it.y0 }) {
                val t = sp.cs.sortedWith(compareBy({ Math.round(it.cy * 1000) }, { it.x0 })).joinToString(" ") { it.text }
                line[sp.ci] = if (line[sp.ci].isEmpty()) t else line[sp.ci] + " " + t
            }
            line.toList()
        }
        val keep = cols.indices.filter { j -> table.any { it[j].isNotEmpty() } }
        return table.map { r -> keep.map { r[it] } }
    }

    fun toTsv(t: List<List<String>>) = t.joinToString("\n") { r -> r.joinToString("\t") { it.replace(Regex("[\\t\\r\\n]"), " ") } }

    data class Region(val x0: Float, val y0: Float, val x1: Float, val y1: Float, val grid: List<List<String>>)

    fun pageTables(segs: List<Seg>, minCols: Int = 2, minRows: Int = 2): List<Region> {
        if (segs.isEmpty()) return emptyList()
        val vis = cluster(segs, { it.cy - 0.3f * it.h }, { it.cy + 0.3f * it.h })
        val lines = vis.filter { v -> v.size >= minCols && v.maxOf { it.x1 - it.x0 } < CELL_MAX }.sortedBy { v -> v.minOf { it.y0 } }
        if (lines.isEmpty()) return emptyList()
        val blocks = ArrayList<ArrayList<List<Seg>>>()
        var cur = arrayListOf(lines[0])
        for (v in lines.drop(1)) {
            val prevBot = cur.last().maxOf { it.y1 }
            val h = v.maxOf { it.h }
            if (v.minOf { it.y0 } - prevBot < 3.5f * h) cur += v else { blocks += cur; cur = arrayListOf(v) }
        }
        blocks += cur
        val out = ArrayList<Region>()
        for (blk in blocks) {
            if (blk.size < minRows) continue
            val all = blk.flatten()
            val x0 = all.minOf { it.x0 } - 0.002f; val x1 = all.maxOf { it.x1 } + 0.002f
            var y0 = all.minOf { it.y0 } - 0.002f; var y1 = all.maxOf { it.y1 } + 0.002f
            // células de várias linhas passam do topo/fundo da primeira/última linha alinhada
            var grew = true
            while (grew) {
                grew = false
                for (sg in segs) {
                    if (sg.x0 < x0 || sg.x1 > x1 || sg.cy in y0..y1) continue
                    if (sg.cy < y0 && y0 - sg.y1 < 0.7f * sg.h) { y0 = sg.y0 - 0.002f; grew = true }
                    else if (sg.cy > y1 && sg.y0 - y1 < 0.7f * sg.h) { y1 = sg.y1 + 0.002f; grew = true }
                }
            }
            val inside = segs.filter { it.cy in y0..y1 && it.x0 >= x0 && it.x1 <= x1 }
            val g = grid(inside)
            if (g.size >= minRows && g.maxOf { it.size } >= minCols) out += Region(x0, y0, x1, y1, g)
        }
        return out
    }

    /** Seleção de linha de tabela: (trechos escolhidos) ou null se não for o caso. */
    fun rowSelection(segs: List<Seg>, sa: Seg, sb: Seg, tables: List<Region>): List<Seg>? {
        if (xover(sa, sb)) return null
        if (maxOf(sa.x1 - sa.x0, sb.x1 - sb.x0) > CELL_MAX) return null
        val sameRow = sa.y0 < sb.y1 && sb.y0 < sa.y1
        if (!sameRow) {
            fun inside(s: Seg, r: Region) = r.x0 <= s.x0 && s.x1 <= r.x1 && s.cy in r.y0..r.y1
            if (tables.none { inside(sa, it) && inside(sb, it) }) return null
        }
        val lo = minOf(sa.x0, sb.x0) - 0.002f; val hi = maxOf(sa.x1, sb.x1) + 0.002f
        val top = minOf(sa.y0, sb.y0); val bot = maxOf(sa.y1, sb.y1)
        val cand = segs.filter { it.x1 >= lo && it.x0 <= hi }
        val chosen = cand.filter { it.cy in (top - 0.2f * it.h)..(bot + 0.2f * it.h) }.toMutableList()
        if (chosen.isEmpty()) return null
        var changed = true
        while (changed) {
            changed = false
            for (s in cand) {
                if (s in chosen) continue
                if (chosen.any { c -> xover(s, c) && (s.y0 - c.y1 in 0f..0.7f * minOf(s.h, c.h) || c.y0 - s.y1 in 0f..0.7f * minOf(s.h, c.h)) }) {
                    chosen += s; changed = true
                }
            }
        }
        return chosen
    }
}
