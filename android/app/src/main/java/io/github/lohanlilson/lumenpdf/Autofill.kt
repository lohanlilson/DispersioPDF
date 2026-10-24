package io.github.lohanlilson.lumenpdf

import android.content.Context
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import java.text.Normalizer
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** "Meus dados": guardados no aparelho e usados para preencher formulários com um toque. */
object Autofill {
    /** key, rótulo, palavras que identificam o campo (sem acento, minúsculas), teclado */
    data class Item(val key: String, val label: String, val words: List<String>, val keyboard: KeyboardType = KeyboardType.Text)

    val ITEMS = listOf(
        Item("nome", "Nome completo", listOf("nome completo", "nome", "name", "requerente", "contratante", "declarante", "outorgante", "solicitante", "assinante")),
        Item("cpf", "CPF", listOf("cpf", "cpf mf", "c p f"), KeyboardType.Number),
        Item("rg", "RG / Identidade", listOf("rg", "identidade", "carteira de identidade", "documento de identidade")),
        Item("orgao", "Órgão emissor do RG", listOf("orgao emissor", "orgao expedidor", "emissor")),
        Item("nascimento", "Data de nascimento", listOf("data de nascimento", "nascimento", "data nasc", "nasc", "dt nasc"), KeyboardType.Number),
        Item("nacionalidade", "Nacionalidade", listOf("nacionalidade")),
        Item("estadocivil", "Estado civil", listOf("estado civil")),
        Item("profissao", "Profissão", listOf("profissao", "ocupacao", "cargo", "funcao")),
        Item("email", "E-mail", listOf("e mail", "email", "correio eletronico"), KeyboardType.Email),
        Item("telefone", "Telefone / Celular", listOf("telefone", "celular", "fone", "tel", "whatsapp"), KeyboardType.Phone),
        Item("endereco", "Endereço (rua, número, complemento)", listOf("endereco", "endereco completo", "logradouro", "rua", "residencia", "domicilio")),
        Item("bairro", "Bairro", listOf("bairro", "setor")),
        Item("cidade", "Cidade", listOf("cidade", "municipio")),
        Item("uf", "UF", listOf("uf", "estado")),
        Item("cep", "CEP", listOf("cep"), KeyboardType.Number),
        Item("empresa", "Empresa / Razão social", listOf("razao social", "empresa", "nome empresarial")),
        Item("cnpj", "CNPJ", listOf("cnpj"), KeyboardType.Number),
    )

    /** rótulos que parecem "nome", mas são de outra pessoa ou coisa */
    private val NOT_MINE = listOf("mae", "pai", "conjuge", "fantasia", "testemunha", "empresa", "social", "banco", "responsavel", "procurador",
        "filho", "filha", "dependente", "beneficiario", "vendedor", "comprador", "locador", "locatario", "fiador", "avalista")

    fun norm(s: String): String = Normalizer.normalize(s, Normalizer.Form.NFD).replace(Regex("\\p{M}"), "").lowercase()
        .replace(Regex("[^a-z0-9]+"), " ").replace(Regex("\\b(do|da|de|dos|das|n|no|nº|o|a)\\b"), " ")
        .replace(Regex("\\s+"), " ").trim()

    private fun sp(ctx: Context) = ctx.getSharedPreferences("meus_dados", Context.MODE_PRIVATE)
    fun load(ctx: Context): Map<String, String> = ITEMS.associate { it.key to (sp(ctx).getString(it.key, "") ?: "") }
    fun save(ctx: Context, data: Map<String, String>) = sp(ctx).edit().apply { data.forEach { (k, v) -> putString(k, v.trim()) } }.apply()
    fun hasAny(ctx: Context) = load(ctx).values.any { it.isNotBlank() }

    /** Qual dado do perfil serve para o campo (pelo rótulo e pelo nome interno). "hoje" = data de hoje. */
    fun match(label: String, name: String): String? {
        for (raw in listOf(label, name.substringAfterLast('.'))) {
            val n = norm(raw.replace('_', ' ').replace(Regex("([a-z])([A-Z])"), "$1 $2"))
            if (n.isBlank()) continue
            if (n == "data" || n == "data assinatura" || n == "data hoje") return "hoje"
            val words = n.split(" ").toSet()
            // frases mais longas primeiro: "estado civil" antes de "estado", "data de nascimento" antes de "nome"
            val cands = ITEMS.flatMap { it -> it.words.map { w -> it to norm(w) } }.sortedByDescending { it.second.length }
            for ((item, w) in cands) {
                val hit = if (w.contains(' ')) " $n ".contains(" $w ") else w in words
                if (!hit) continue
                if (item.key == "nome" && NOT_MINE.any { it in words }) break
                if (item.key == "uf" && "civil" in words) continue
                return item.key
            }
        }
        return null
    }

    data class Fill(val field: FormField, val key: String, val value: String)

    /** Campos de texto vazios que dá para preencher com os dados salvos. */
    fun plan(fields: List<FormField>, data: Map<String, String>): List<Fill> {
        val today = SimpleDateFormat("dd/MM/yyyy", Locale("pt", "BR")).format(Date())
        return fields.filter { it.kind == FormField.Kind.TEXT && !it.readOnly && it.value.isBlank() }
            .distinctBy { it.name }
            .mapNotNull { f ->
                val key = match(f.label, f.name) ?: return@mapNotNull null
                val v = if (key == "hoje") today else data[key].orEmpty()
                if (v.isBlank()) null else Fill(f, key, v)
            }
    }
}

/** Editor dos "Meus dados". */
@Composable
fun MyDataDialog(onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    val data = remember { mutableStateMapOf<String, String>().apply { putAll(Autofill.load(ctx)) } }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Meus dados") },
        text = {
            Column(Modifier.heightIn(max = 520.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("Ficam só neste celular. Usados em “Preencher com meus dados”.", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Autofill.ITEMS.forEach { it ->
                    OutlinedTextField(data[it.key] ?: "", { v -> data[it.key] = v }, label = { Text(it.label) }, singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = it.keyboard), modifier = Modifier.fillMaxWidth())
                }
            }
        },
        confirmButton = { TextButton({ Autofill.save(ctx, data); onDismiss() }) { Text("Salvar") } },
        dismissButton = { TextButton(onDismiss) { Text("Cancelar") } },
    )
}

/** Mostra o que será preenchido (dá para desmarcar) antes de gravar. */
@Composable
fun AutofillDialog(plan: List<Autofill.Fill>, onEditData: () -> Unit, onDismiss: () -> Unit, onFill: (List<Autofill.Fill>) -> Unit) {
    val on = remember(plan) { mutableStateMapOf<String, Boolean>().apply { plan.forEach { put(it.field.name, true) } } }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Preencher com meus dados") },
        text = {
            Column(Modifier.heightIn(max = 480.dp).verticalScroll(rememberScrollState())) {
                if (plan.isEmpty()) Text("Nenhum campo vazio corresponde aos seus dados salvos. Confira “Meus dados” ou use " +
                    "“Detectar campos de formulário” se o PDF não tiver campos.")
                plan.forEach { p ->
                    Row(Modifier.fillMaxWidth().clickable { on[p.field.name] = !(on[p.field.name] ?: true) }, verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(on[p.field.name] ?: true, { on[p.field.name] = it })
                        Column {
                            Text(p.field.label.ifBlank { p.field.name } + " · pág. ${p.field.page + 1}", style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(p.value, style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
                TextButton(onEditData) { Text("Editar meus dados…") }
            }
        },
        confirmButton = {
            TextButton(enabled = plan.any { on[it.field.name] != false }, onClick = { onFill(plan.filter { on[it.field.name] != false }) }) {
                Text("Preencher")
            }
        },
        dismissButton = { TextButton(onDismiss) { Text("Cancelar") } },
    )
}
