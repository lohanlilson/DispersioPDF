package io.github.lohanlilson.dispersio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class PagamentosTest {
    private val hoje = LocalDate.of(2026, 10, 27)
    private val LD_BB = "00190500954014481606906809350314337370000000100"
    private val BC_BB = "00193373700000001000500940144816060680935031"
    private val PIX = "00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR" +
        "5913Fulano de Tal6008BRASILIA62070503***63041D3D"

    private fun boleto(banco: String, venc: LocalDate, cents: Long, livre: String): String {
        val fator = 1000 + java.time.temporal.ChronoUnit.DAYS.between(LocalDate.of(2025, 2, 22), venc)
        val sem = banco + "9" + "%04d".format(fator) + "%010d".format(cents) + livre
        return sem.substring(0, 4) + Pagamentos.mod11Boleto(sem) + sem.substring(4)
    }

    @Test fun exemplosPublicos() {
        assertEquals("", Pagamentos.checkBoletoLine(LD_BB))
        assertEquals(BC_BB, Pagamentos.lineToBarcode(LD_BB))
        assertEquals(LD_BB, Pagamentos.barcodeToLine(BC_BB))
        assertTrue(Pagamentos.pixItem(0, PIX)!!.ok)
        assertFalse(Pagamentos.pixItem(0, PIX.replace("Fulano", "Fulana"))!!.ok)
        assertTrue(Pagamentos.checkBoletoLine(LD_BB.substring(0, 12) + "9" + LD_BB.substring(13)).contains("2º campo"))
    }

    @Test fun boletoValorEVencimento() {
        val bc = boleto("237", LocalDate.of(2026, 11, 10), 123456, "0123456789012345678901234")
        val it = Pagamentos.boletoItem(0, Pagamentos.barcodeToLine(bc), hoje)
        val d = it.details.toMap()
        assertTrue(it.ok); assertEquals("Boleto Bradesco", it.title)
        assertEquals("R$ 1.234,56", d["Valor"]); assertEquals("10/11/2026", d["Vencimento"])
    }

    @Test fun chaveEArrecadacao() {
        val base = "52" + "2610" + "53176704000186" + "55" + "001" + "000012345" + "1" + "12345678"
        val ch = base + Pagamentos.mod11Zero(base)
        val it = Pagamentos.chaveItem(0, ch)
        assertTrue(it.ok); assertEquals("NF-e nº 12345", it.title)
        assertTrue(it.details.toMap()["Emitente"]!!.contains("53.176.704/0001-86"))
        val base2 = "35" + "2609" + "12ABC34501DE35" + "55" + "001" + "000000777" + "1" + "87654321"
        assertTrue(Pagamentos.chaveOk(base2 + Pagamentos.mod11Zero(base2)))
        val sem = ("836" + "00000012345" + "0055" + "1234567890123456789012345").substring(0, 43)
        val bc = sem.substring(0, 3) + Pagamentos.mod10(sem) + sem.substring(3)
        assertTrue(Pagamentos.arrecBarcodeOk(bc))
        val a = Pagamentos.arrecItem(0, Pagamentos.arrecBarcodeToLine(bc))
        assertTrue(a.ok); assertEquals("R$ 123,45", a.details.toMap()["Valor"])
    }

    @Test fun texto() {
        val bc = boleto("237", LocalDate.of(2026, 11, 10), 123456, "0123456789012345678901234")
        val ld = Pagamentos.barcodeToLine(bc)
        val txt = "Banco Bradesco 237-2\n${Pagamentos.fmtBoleto(ld)}\nPix copia e cola:\n${PIX.substring(0, 70)}\n${PIX.substring(70)}\n" +
            "Telefone 62 3333-4444 CPF 123.456.789-09 " + "1".repeat(60)
        val items = Pagamentos.findInText(txt, 0, hoje)
        assertEquals(listOf("boleto", "pix"), items.map { it.kind })
        assertTrue(items.all { it.ok })
        val errado = Pagamentos.findInText(Pagamentos.fmtBoleto(LD_BB.substring(0, 12) + "9" + LD_BB.substring(13)), 0, hoje)
        assertEquals(1, errado.size); assertFalse(errado[0].ok)
        assertEquals(emptyList<PayItem>(), Pagamentos.findInText("Pedido " + "0".repeat(46) + " e 62 99999-0000", 0, hoje))
    }

    @Test fun adulterado() {
        val bc = boleto("237", LocalDate.of(2026, 11, 10), 123456, "0123456789012345678901234")
        val outro = boleto("237", LocalDate.of(2026, 11, 10), 923456, "9993456789012345678901234")
        val texto = Pagamentos.findInText(Pagamentos.fmtBoleto(Pagamentos.barcodeToLine(outro)), 0, hoje)
        val codigo = listOfNotNull(Pagamentos.fromBarcode(com.google.zxing.BarcodeFormat.ITF, bc, 0, hoje))
        val m = Pagamentos.merge(texto, codigo)
        assertFalse(m.first { it.source == "texto" }.ok)
        assertTrue(m.first { it.source == "texto" }.problem.contains("NÃO confere"))
    }

    @Test fun palavras() {
        assertTrue(Orientation.goodWords("Cláusula primeira. A cedente transfere os créditos") >= 4)
        assertTrue(Orientation.goodWords("joApBonau! o eus|d opôeynb 1oo") <= 1)
    }
}
