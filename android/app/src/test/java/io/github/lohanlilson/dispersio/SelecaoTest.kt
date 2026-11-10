package io.github.lohanlilson.dispersio

import org.junit.Assert.assertEquals
import org.junit.Test

/** Seleção em tabela: arrastar dentro de uma coluna pega só a coluna. */
class SelecaoTest {
    /** Monta os caracteres na ordem em que o PDF costuma guardar: linha 1 do nome, data, linha 2, CNPJ, linha 3. */
    private fun page(): Pair<PageChars, Map<String, Int>> {
        val sb = StringBuilder(); val fr = ArrayList<FracRect?>(); val at = HashMap<String, Int>()
        val cw = 0.008f; val h = 0.02f
        fun put(s: String, x: Float, y: Float) {
            at.putIfAbsent(s.substringBefore(' '), sb.length)
            s.forEachIndexed { i, c ->
                sb.append(c)
                fr += if (c == ' ') null else FracRect(x + i * cw, y, x + (i + 1) * cw, y + h)
            }
            at[s.substringAfterLast(' ') + "#fim"] = sb.length - 1
            sb.append('\n'); fr += null
        }
        put("COOPERATIVA CENTRAL DE CREDITO", 0.35f, 0.30f)
        put("26/08/2026", 0.04f, 0.33f)
        put("E ECONOMIA COM INTERACAO", 0.35f, 0.33f)
        put("07202627000174", 0.67f, 0.33f)
        put("SOLIDARIA CRESOL CENTRAL BRASIL", 0.35f, 0.36f)
        return PageChars(0, sb.toString(), fr.toTypedArray(), arrayOfNulls(fr.size)) to at
    }

    @Test fun soAColuna() {
        val (pc, at) = page()
        val sel = pc.selection(at["COOPERATIVA"]!!, at["BRASIL#fim"]!!)
        assertEquals("COOPERATIVA CENTRAL DE CREDITO\nE ECONOMIA COM INTERACAO\nSOLIDARIA CRESOL CENTRAL BRASIL", sel.text)
    }

    @Test fun textoCorridoNaoMuda() {
        val sb = StringBuilder(); val fr = ArrayList<FracRect?>()
        listOf("Primeira linha do paragrafo", "segunda linha do paragrafo", "terceira").forEachIndexed { l, s ->
            s.forEachIndexed { i, c -> sb.append(c); fr += if (c == ' ') null else FracRect(0.1f + i * 0.01f, 0.1f + l * 0.03f, 0.11f + i * 0.01f, 0.12f + l * 0.03f) }
            sb.append('\n'); fr += null
        }
        val pc = PageChars(0, sb.toString(), fr.toTypedArray(), arrayOfNulls(fr.size))
        assertEquals("linha do paragrafo\nsegunda linha do paragrafo\nterc", pc.selection(9, sb.indexOf("terc") + 3).text)
    }
}
