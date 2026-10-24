package io.github.lohanlilson.lumenpdf

import org.junit.Assert.assertEquals
import org.junit.Test

class CompareTest {
    private fun w(s: String, page: Int = 0) = s.split(" ").filter { it.isNotEmpty() }.map { PWord(it, page, FracRect(0f, 0f, 0f, 0f)) }

    private fun run(a: String, b: String) = Compare.changes(w(a), w(b)).map { Triple(it.kind, it.textA, it.textB) }

    @Test fun igual() = assertEquals(emptyList<Any>(), run("a b c", "a b c"))
    @Test fun alterado() = assertEquals(listOf(Triple("alterado", "10.000,00", "12.500,00")),
        run("O preço é R$ 10.000,00 à vista", "O preço é R$ 12.500,00 à vista"))
    @Test fun inserido() = assertEquals(listOf(Triple("inserido", "", "e quinhentos")), run("doze mil reais", "doze mil e quinhentos reais"))
    @Test fun removido() = assertEquals(listOf(Triple("removido", "Foro de Goiânia.", "")), run("Prazo de 30 dias. Foro de Goiânia.", "Prazo de 30 dias."))
    @Test fun varias() {
        val r = run("a b c d e f g", "a X c d e Y Z g")
        assertEquals(listOf(Triple("alterado", "b", "X"), Triple("alterado", "f", "Y Z")), r)
    }
    @Test fun inicioEFim() {
        assertEquals(listOf(Triple("inserido", "", "novo"), Triple("removido", "fim", "")), run("a b fim", "novo a b"))
    }
    @Test fun vazio() {
        assertEquals(listOf(Triple("inserido", "", "a b")), run("", "a b"))
        assertEquals(listOf(Triple("removido", "a b", "")), run("a b", ""))
    }
}
