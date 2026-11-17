package io.github.lohanlilson.dispersio

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.text.Normalizer

/** e-CNPJ: confere se o responsável pelo certificado consta no quadro de sócios e administradores da Receita
 *  (dados públicos pela BrasilAPI; se falhar, CNPJ.ws). Só o CNPJ é enviado. Guardado por 7 dias. Igual ao computador. */
object Socios {
    data class Socio(val nome: String, val doc: String, val qualificacao: String, val representante: String, val docRep: String)
    data class Dados(val razao: String, val situacao: String, val socios: List<Socio>, val fonte: String)
    /** nivel: ok | warn | bad | info */
    data class Resultado(val nivel: String, val texto: String, val dados: Dados? = null)

    private const val VALIDADE = 7L * 24 * 3600 * 1000

    fun norm(s: String): String {
        val t = Normalizer.normalize(s, Normalizer.Form.NFD).replace(Regex("\\p{M}"), "").uppercase().replace(Regex("[^A-Z ]"), " ")
        return t.split(Regex("\\s+")).filter { it.isNotEmpty() && it !in setOf("DE", "DA", "DO", "DAS", "DOS", "E") }.joinToString(" ")
    }

    private fun digits(s: String?) = s.orEmpty().filter { it.isDigit() }

    private fun get(url: String): String? {
        repeat(3) { attempt ->
            val c = (URL(url).openConnection() as HttpURLConnection).apply {
                connectTimeout = 10000; readTimeout = 12000
                setRequestProperty("User-Agent", "DispersioPDF-Android/1.0 (https://github.com/lohanlilson/DispersioPDF)")
                setRequestProperty("Accept", "application/json")
            }
            try {
                when (c.responseCode) {
                    200 -> return c.inputStream.bufferedReader().readText()
                    404 -> throw NoSuchElementException("CNPJ não encontrado na Receita Federal")
                    429, 503 -> Thread.sleep(2000L * (attempt + 1))
                    else -> return null
                }
            } catch (e: NoSuchElementException) { throw e
            } catch (_: Exception) { if (attempt >= 1) return null
            } finally { c.disconnect() }
        }
        return null
    }

    private fun brasilApi(cnpj: String): Dados? {
        val j = JSONObject(get("https://brasilapi.com.br/api/cnpj/v1/$cnpj") ?: return null)
        val q = j.optJSONArray("qsa") ?: JSONArray()
        val socios = (0 until q.length()).map { q.getJSONObject(it) }.map {
            Socio(it.optString("nome_socio"), it.optString("cnpj_cpf_do_socio"), it.optString("qualificacao_socio"),
                it.optString("nome_representante_legal"), it.optString("cpf_representante_legal"))
        }
        return Dados(j.optString("razao_social"), j.optString("descricao_situacao_cadastral"), socios, "Receita Federal (BrasilAPI)")
    }

    private fun cnpjWs(cnpj: String): Dados? {
        val j = JSONObject(get("https://publica.cnpj.ws/cnpj/$cnpj") ?: return null)
        val q = j.optJSONArray("socios") ?: JSONArray()
        val socios = (0 until q.length()).map { q.getJSONObject(it) }.map {
            Socio(it.optString("nome"), it.optString("cpf_cnpj_socio"), it.optJSONObject("qualificacao_socio")?.optString("descricao").orEmpty(),
                it.optString("nome_representante"), it.optString("cpf_representante_legal"))
        }
        return Dados(j.optString("razao_social"), j.optJSONObject("estabelecimento")?.optString("situacao_cadastral").orEmpty(), socios, "Receita Federal (CNPJ.ws)")
    }

    private fun toJson(d: Dados) = JSONObject().put("r", d.razao).put("s", d.situacao).put("f", d.fonte).put("q",
        JSONArray(d.socios.map { JSONArray(listOf(it.nome, it.doc, it.qualificacao, it.representante, it.docRep)) }))

    private fun fromJson(j: JSONObject): Dados {
        val q = j.getJSONArray("q")
        return Dados(j.getString("r"), j.getString("s"), (0 until q.length()).map { q.getJSONArray(it) }.map {
            Socio(it.getString(0), it.getString(1), it.getString(2), it.getString(3), it.getString(4))
        }, j.getString("f"))
    }

    private fun cacheFile(ctx: Context) = File(ctx.filesDir, "socios.json")

    fun consultar(ctx: Context, cnpj0: String): Dados {
        val cnpj = digits(cnpj0)
        require(cnpj.length == 14) { "CNPJ inválido" }
        val cache = runCatching { JSONObject(cacheFile(ctx).readText()) }.getOrDefault(JSONObject())
        val old = cache.optJSONObject(cnpj)
        if (old != null && System.currentTimeMillis() - old.optLong("em") < VALIDADE) return fromJson(old)
        val d = runCatching { brasilApi(cnpj) }.getOrElse { if (it is NoSuchElementException) throw it else null }
            ?: runCatching { cnpjWs(cnpj) }.getOrElse { if (it is NoSuchElementException) throw it else null }
        if (d != null) {
            runCatching { cache.put(cnpj, toJson(d).put("em", System.currentTimeMillis())); cacheFile(ctx).writeText(cache.toString()) }
            return d
        }
        if (old != null) return fromJson(old)            // sem internet: último resultado
        throw java.io.IOException("não foi possível consultar a Receita Federal")
    }

    private fun cpfConfere(mascarado: String, cpf: String?): Boolean? {
        val m = digits(mascarado); val c = digits(cpf)
        if (c.length != 11 || m.length != 6 || m == "000000") return null
        return c.substring(3, 9) == m
    }

    fun conferir(responsavel: String?, cpf: String?, d: Dados): Resultado {
        val sit = d.situacao.uppercase()
        val avisoSit = if (sit.isEmpty() || sit == "ATIVA") "" else " Atenção: a situação do CNPJ na Receita é $sit."
        if (responsavel.isNullOrBlank())
            return Resultado("warn", "O certificado não informa o responsável, então não dá para conferir no quadro de sócios.$avisoSit", d)
        val achados = ArrayList<Pair<String, Boolean?>>()
        for (s in d.socios) {
            for ((nome, doc, papel) in listOf(Triple(s.nome, s.doc, s.qualificacao), Triple(s.representante, s.docRep, "representante legal de ${s.nome}"))) {
                if (nome.isBlank()) continue
                val ok = cpfConfere(doc, cpf)
                if (norm(nome) == norm(responsavel)) achados += papel to ok
                else if (ok == true && norm(nome).split(" ").firstOrNull() == norm(responsavel).split(" ").firstOrNull()) achados += papel to true
            }
        }
        if (achados.isNotEmpty()) {
            val (papel, ok) = achados.firstOrNull { it.second == true } ?: achados[0]
            if (ok == false) return Resultado("warn", "Há um sócio com o mesmo nome ($papel), mas o CPF não confere com o do certificado.$avisoSit", d)
            return Resultado(if (avisoSit.isNotEmpty()) "bad" else "ok", "$responsavel consta no quadro de sócios e administradores como $papel.$avisoSit", d)
        }
        if (d.socios.isEmpty()) {
            if (norm(responsavel).isNotEmpty() && norm(d.razao).contains(norm(responsavel)))
                return Resultado(if (avisoSit.isNotEmpty()) "bad" else "ok", "Empresa individual em nome de $responsavel.$avisoSit", d)
            return Resultado("info", "A Receita não lista sócios para este tipo de empresa; confira o responsável pelo contrato social ou ato constitutivo.$avisoSit", d)
        }
        return Resultado(if (avisoSit.isNotEmpty()) "bad" else "warn",
            "$responsavel NÃO consta no quadro de sócios e administradores. Pode ser um procurador: peça a procuração e confira se ela dá poderes para assinar este documento.$avisoSit", d)
    }

    suspend fun verificar(ctx: Context, s: SigInfo): Resultado? = withContext(Dispatchers.IO) {
        if (s.icp.type != "e-CNPJ") return@withContext null
        val cnpj = s.icp.cnpj ?: s.document ?: return@withContext null
        try {
            conferir(s.icp.responsible, s.icp.responsibleCpf, consultar(ctx, cnpj))
        } catch (e: Exception) {
            Resultado("info", "Não foi possível conferir o quadro de sócios: ${e.message ?: "sem internet"}")
        }
    }
}
