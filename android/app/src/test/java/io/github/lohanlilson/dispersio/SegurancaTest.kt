package io.github.lohanlilson.dispersio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class SegurancaTest {
    private fun lvl(u: String, t: String = "") = Seguranca.linkRisk(u, t).level

    @Test fun links() {
        assertTrue(lvl("https://www.bradesco.com.br/x") < Seguranca.WARN)
        assertEquals(Seguranca.DANGER, lvl("https://bradesco-seguro.top/login"))
        assertEquals(Seguranca.DANGER, lvl("https://evil.com/x", "Acesse www.itau.com.br"))
        assertTrue(lvl("https://www.itau.com.br", "www.itau.com.br") < Seguranca.WARN)
        assertEquals(Seguranca.DANGER, lvl("http://192.168.0.10/boleto"))
        assertEquals(Seguranca.WARN, lvl("https://bit.ly/x"))
        assertEquals(Seguranca.DANGER, lvl("https://xn--bradsco-6ya.com"))
        assertEquals(Seguranca.DANGER, lvl("https://arquivos.com/nota-fiscal.exe"))
        assertEquals(Seguranca.DANGER, lvl("https://gov-br.online/cpf"))
        assertTrue(lvl("https://www.gov.br/receita") < Seguranca.WARN)
        assertTrue(lvl("https://satcm.gov.cn/x") < Seguranca.WARN)
        assertTrue(lvl("https://receitasdebolo.com") < Seguranca.WARN)
        assertEquals(Seguranca.DANGER, lvl("javascript:alert(1)"))
        assertEquals(Seguranca.DANGER, lvl("https://www.google.com@phish.ru/x"))
        assertEquals(Seguranca.INFO, lvl("mailto:a@b.com"))
    }

    @Test fun pixQuebradoEmLinhas() {
        val pix = "00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR" +
            "5913Fulano de\nTal6008BRASILIA62070503***63041D3D"
        val items = Pagamentos.findInText("Pague com Pix:\n$pix", 0)
        assertTrue(items.any { it.kind == "pix" && it.ok })
    }

    @Test fun recebedorForaDoDocumento() {
        val pix = "00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR" +
            "5913Fulano de Tal6008BRASILIA62070503***63041D3D"
        val texto = "NACIONAL SECURITIZADORA S.A. — Cobrança referente ao contrato 123. ".repeat(5) + "\n" + pix
        val items = Pagamentos.findInText(texto, 0)
        Pagamentos.checkPixPayee(items, listOf(texto))
        assertTrue(items.first { it.kind == "pix" }.alert.contains("não aparece"))
        val ok = Pagamentos.findInText(texto.replace("NACIONAL SECURITIZADORA S.A.", "FULANO DE TAL"), 0)
        Pagamentos.checkPixPayee(ok, listOf(texto.replace("NACIONAL SECURITIZADORA S.A.", "FULANO DE TAL")))
        assertEquals("", ok.first { it.kind == "pix" }.alert)
    }

    @Test fun bancoTrocado() {
        val venc = LocalDate.of(2026, 11, 10)
        val fator = 1000 + java.time.temporal.ChronoUnit.DAYS.between(LocalDate.of(2025, 2, 22), venc)
        val sem = "341" + "9" + "%04d".format(fator) + "%010d".format(5000L) + "0123456789012345678901234"
        val bc = sem.substring(0, 4) + Pagamentos.mod11Boleto(sem) + sem.substring(4)
        val ld = Pagamentos.barcodeToLine(bc)
        val b = Pagamentos.findInText("Banco Bradesco 237-2\n$ld\nBeneficiário: Loja", 0, venc).first { it.kind == "boleto" }
        assertTrue(b.alert, b.alert.contains("Itaú") && b.alert.contains("Bradesco"))
        val c = Pagamentos.findInText("Itaú 341-7  CPF 123.456.789-01\n$ld", 0, venc).first { it.kind == "boleto" }
        assertEquals("", c.alert)
    }
}
