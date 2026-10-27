package io.github.lohanlilson.lumenpdf

import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CitacoesTest {
    @Test fun separaEDevolve() {
        val (clean, cites) = Citacoes.split("Animal cruelty predicts violence [12, 15] and abuse (Arkow et al., 2011; Ascione 1993).")
        assertEquals("Animal cruelty predicts violence and abuse.", clean)
        assertEquals(listOf("[12, 15]", "(Arkow et al., 2011; Ascione 1993)"), cites)
        assertEquals("A crueldade prediz violência e abuso [12, 15] (Arkow et al., 2011; Ascione 1993).",
            Citacoes.join("A crueldade prediz violência e abuso.", cites))
        val sup = "Dogs were examined${Citacoes.SUP}12,14${Citacoes.SUP_END} in 2019."
        val t = runBlocking { Citacoes.translate(sup) { "Os cães foram examinados em 2019." } }
        assertEquals("Os cães foram examinados em 2019¹²˒¹⁴.", t)
        assertEquals(listOf("See Fig. 2 for details.", "The dogs, e.g. Labradors, improved."), Citacoes.sentences("See Fig. 2 for details. The dogs, e.g. Labradors, improved."))
        assertEquals("12.5 ± 3.1", runBlocking { Citacoes.translate("12.5 ± 3.1") { "x" } })
    }

    @Test fun divideProporcional() {
        assertEquals(listOf("um dois tres", "quatro cinco seis sete oito nove dez"),
            DocAnalysis.splitLike("um dois tres quatro cinco seis sete oito nove dez", listOf("abc def ghi", "jkl mno pqr stu vwx yz")))
    }

    @Test fun links() {
        assertEquals("doi:10.1177/0886260508319362", Artigos.parseLink("https://doi.org/10.1177/0886260508319362"))
        assertEquals("doi:10.3390/ani16172675", Artigos.parseLink("veja 10.3390/ani16172675."))
        assertEquals("doi:10.48550/arXiv.2301.12345", Artigos.parseLink("https://arxiv.org/abs/2301.12345v2"))
        assertEquals(null, Artigos.parseLink("maus tratos"))
    }

    @Test fun obraCompleta() {
        val w = JSONObject("""{"id":"https://openalex.org/W1","display_name":"X","type":"review","abstract_inverted_index":{"Animal":[0],"cruelty":[1],"matters":[2]},
            "related_works":["https://openalex.org/W2","https://openalex.org/W3"],"referenced_works":["https://openalex.org/W9"],"cited_by_count":4}""")
        val a = Artigos.parseWork(w)
        assertEquals("Animal cruelty matters", a.abstract)
        assertEquals("W1", a.id); assertEquals("review", a.kind)
        assertEquals(listOf("W2", "W3"), a.related); assertEquals(listOf("W9"), a.refs)
        assertTrue(!a.hasPdf)
    }
}
