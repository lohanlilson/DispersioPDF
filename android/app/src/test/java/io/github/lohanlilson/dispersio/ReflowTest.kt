package io.github.lohanlilson.dispersio

import org.junit.Assert.assertEquals
import org.junit.Test

class ReflowTest {
    @Test
    fun paragrafos() {
        val t = """
            CONTRATO DE CESSÃO
            Cláusula 1. O cedente transfere ao cessio-
            nário os créditos descritos no anexo, com
            todos os direitos.
            Cláusula 2. O preço é de R$ 10.000,00.
            a) à vista;
            b) em parcelas.
        """.trimIndent()
        val p = reflow(t)
        assertEquals("CONTRATO DE CESSÃO", p[0])
        assertEquals("Cláusula 1. O cedente transfere ao cessionário os créditos descritos no anexo, com todos os direitos.", p[1])
        assertEquals("Cláusula 2. O preço é de R$ 10.000,00.", p[2])
        assertEquals(listOf("a) à vista;", "b) em parcelas."), p.drop(3))
    }
}
