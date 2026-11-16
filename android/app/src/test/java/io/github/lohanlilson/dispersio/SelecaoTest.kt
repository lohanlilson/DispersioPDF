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

    @Test fun linhaInteira() {
        val (pc, at) = page()
        val sel = pc.selection(at["26/08/2026"]!!, at["07202627000174#fim"]!!)
        assertEquals("26/08/2026\tCOOPERATIVA CENTRAL DE CREDITO E ECONOMIA COM INTERACAO SOLIDARIA CRESOL CENTRAL BRASIL\t07202627000174", sel.text)
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

class CelulaExcelTest {
    @Test fun tipos() {
        org.junit.Assert.assertTrue(Convert.cell("A1", "07202627000174").contains("inlineStr"))
        org.junit.Assert.assertTrue(Convert.cell("A1", "111.222.333-44").contains("inlineStr"))
        org.junit.Assert.assertTrue(Convert.cell("A1", "26/08/2026").contains("s=\"1\"><v>46260</v>"))
        org.junit.Assert.assertTrue(Convert.cell("A1", "R$ 1.234,56").contains("<v>1234.56</v>"))
        org.junit.Assert.assertTrue(Convert.cell("A1", "12,5%").contains("<v>0.125</v>"))
        org.junit.Assert.assertTrue(Convert.cell("A1", "42").contains("<v>42.0</v>"))
    }
}

class PlanilhaTest {
    @Test fun gera() {
        val f = java.io.File("build/teste_tabela.xlsx")
        f.outputStream().use { Convert.xlsxTables(listOf("Pág 1 - Tabela 1" to listOf(listOf("Data", "Nome", "CNPJ", "Valor"),
            listOf("26/08/2026", "COOPERATIVA <&> X", "07202627000174", "R$ 1.234,56"))), it) }
        java.io.File("build/teste_texto.xlsx").outputStream().use { Convert.xlsx(listOf("a  b\n1  2"), it) }
    }
}

class BuscaTest {
    @Test fun acentoECnpj() {
        val pages = listOf("Contrato de cessão de CRÉDITO", "CNPJ 07.202.627/0001-74 e crédito")
        val h = Busca.searchText(pages, Busca.pattern("credito")!!)
        assertEquals(listOf(0, 1), h.map { it.page })
        assertEquals("CRÉDITO", h[0].match)
        assertEquals("07.202.627/0001-74", Busca.searchText(pages, Busca.pattern("07202627000174")!!).single().match)
    }
}

class CelularTest {
    @Test fun reconheceQr() {
        org.junit.Assert.assertTrue(Celular.isLink("http://192.168.0.12:51234/AbC_d-12345678"))
        org.junit.Assert.assertFalse(Celular.isLink("https://site.com/AbC12345678"))
        org.junit.Assert.assertFalse(Celular.isLink("00020126580014br.gov.bcb.pix"))
    }
}

class DialogoTest {
    @Test fun tuParaVoce() {
        assertEquals("Onde você foi ontem à noite?", MangaTrad.dialogBr("Onde foste ontem à noite?"))
        assertEquals("Não minta para mim!", MangaTrad.dialogBr("Não mintas para mim!"))
        assertEquals("Você está louco? Eu vou com você.", MangaTrad.dialogBr("Tu estás louco? Eu vou contigo."))
    }
}

class DicionarioTest {
    @Test fun leWikcionario() {
        val wt = "={{-pt-}}=\n==Substantivo==\n# [[construção]] que serve de [[moradia]]\n#* ''exemplo''\n# {{escopo|pt|Família}} [[lar]]\n={{-es-}}=\n# não\n"
        val (defs, lemma) = Dicionario.ptDefs(wt)
        assertEquals(listOf("Substantivo" to "construção que serve de moradia", "Substantivo" to "(Família) lar"), defs)
        assertEquals(null, lemma)
        assertEquals("casa", Dicionario.ptDefs("={{-pt-}}=\n==Forma==\n# plural de [[casa]]\n").second)
        assertEquals("Saudade", Dicionario.clean("“Saudade!”"))
    }
}
