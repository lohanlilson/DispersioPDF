package io.github.lohanlilson.dispersio

import org.junit.Assert.assertEquals
import org.junit.Test

class AutofillTest {
    @Test
    fun rotulos() {
        val casos = mapOf(
            "Nome completo" to "nome", "NOME:" to "nome", "Nome do Requerente" to "nome", "Nome da Mãe" to null, "Nome do pai" to null,
            "Nome fantasia" to null, "Razão Social" to "empresa", "Nome da empresa" to "empresa", "CPF/MF" to "cpf", "C.P.F." to "cpf",
            "RG" to "rg", "Carteira de Identidade" to "rg", "Órgão Emissor" to "orgao", "Data de Nascimento" to "nascimento",
            "Data" to "hoje", "Data de emissão" to null, "E-mail" to "email", "Email" to "email", "Telefone" to "telefone",
            "Celular/WhatsApp" to "telefone", "Endereço" to "endereco", "Bairro" to "bairro", "Município" to "cidade",
            "Estado civil" to "estadocivil", "Estado" to "uf", "UF" to "uf", "CEP" to "cep", "CNPJ" to "cnpj", "Profissão" to "profissao",
            "Nacionalidade" to "nacionalidade", "Observações" to null, "Valor" to null,
        )
        val erros = casos.mapNotNull { (l, k) -> Autofill.match(l, "").let { if (it != k) "$l → $it (esperado $k)" else null } }
        assertEquals(emptyList<String>(), erros)
    }

    @Test
    fun nomeInterno() {
        assertEquals("cpf", Autofill.match("", "form1.dados.cpf_titular"))
        assertEquals("email", Autofill.match("", "emailContato"))
        assertEquals("nascimento", Autofill.match("", "dataNascimento"))
    }
}
