package io.github.lohanlilson.dispersio

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class ArtigosTest {
    private val hoje = LocalDate.of(2026, 10, 27)

    @Test fun openAlex() {
        val js = JSONObject("""{"meta":{"count":2},"results":[
          {"display_name":"Veterinary forensics: animal cruelty","publication_year":2021,"language":"en","cited_by_count":12,
           "doi":"https://doi.org/10.1/abc","authorships":[{"author":{"display_name":"Melissa J. Behr"}},{"author":{"display_name":"Ana Souza"}}],
           "primary_location":{"source":{"display_name":"Veterinary Pathology"}},
           "best_oa_location":{"is_oa":true,"pdf_url":"https://x.org/a.pdf","landing_page_url":"https://x.org/a"},
           "locations":[{"is_oa":true,"pdf_url":"https://repo.org/a.pdf"}],"biblio":{"volume":"58","issue":"2","first_page":"10","last_page":"20"}},
          {"display_name":"Sem PDF","best_oa_location":{"pdf_url":null},"locations":[]}]}""")
        val (arts, n) = Artigos.parseOpenAlex(js)
        assertEquals(2, n); assertEquals(1, arts.size)
        assertEquals(listOf("https://x.org/a.pdf", "https://repo.org/a.pdf"), arts[0].pdfUrls)
        assertTrue(arts[0].abnt(hoje), arts[0].abnt(hoje).startswith(
            "BEHR, Melissa J.; SOUZA, Ana. Veterinary forensics: animal cruelty. Veterinary Pathology, v. 58, n. 2, p. 10-20, 2021. DOI: 10.1/abc."))
        assertTrue(arts[0].abnt(hoje).endsWith("Acesso em: 27 out. 2026."))
    }

    private fun String.startswith(p: String) = startsWith(p)

    @Test fun europePmc() {
        val js = JSONObject("""{"hitCount":1,"resultList":{"result":[{"title":"Dog bite injuries.","authorList":{"author":[{"fullName":"Long K"}]},
            "pubYear":"2024","journalInfo":{"journal":{"title":"Animals"},"volume":"14"},"pmcid":"PMC1","source":"MED","id":"9"}]}}""")
        val (arts, _) = Artigos.parseEuropePmc(js)
        assertEquals("Europe PMC", arts[0].source)
        assertTrue(arts[0].abnt(hoje).startsWith("LONG, K. Dog bite injuries. Animals, v. 14, 2024."))
    }

    @Test fun nomes() {
        assertEquals("Cães maus-tratos abuso.pdf", Artigos.safeName("Cães: \"maus-tratos\"/abuso?"))
        assertEquals("LONG, K. et al. X. Y, 2026.", Article("X", listOf("Long K", "A B", "C D", "E F"), 2026, "Y").abnt(hoje))
    }

    @Test fun idioma() {
        assertEquals("en", Traducao.detect("The results of this study show that the animals were in poor condition and that it was not possible to treat them in the clinic."))
        assertEquals("pt", Traducao.detect("Os resultados deste estudo mostram que os animais estavam em más condições e que não foi possível tratá-los na clínica nas primeiras semanas do ano."))
        assertNull(Traducao.detect("Tabela 1"))
    }
}

class AcentosTest {
    private val t = java.io.File("src/main/assets/dados/acentos.txt").readLines().filter { "=" in it && !it.startsWith("#") }
        .associate { it.substringBefore("=") to it.substringAfter("=") }

    @org.junit.Test fun acentos() {
        org.junit.Assert.assertEquals("maus tratos em cães", Artigos.restoreAccents("maus tratos em caes", t))
        org.junit.Assert.assertEquals("Toxicidade em CÃES", Artigos.restoreAccents("Toxicidade em CAES", t))
        org.junit.Assert.assertEquals(listOf("maus tratos em caes", "maus tratos em cães"), Artigos.variants("maus tratos em caes", t))
        org.junit.Assert.assertEquals(listOf("maus-tratos em cães", "maus tratos em caes"), Artigos.variants("maus-tratos em cães", t))
    }
}
