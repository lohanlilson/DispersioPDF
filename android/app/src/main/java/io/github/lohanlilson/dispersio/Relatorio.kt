package io.github.lohanlilson.dispersio

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Relatório de erro: guarda quando o app fecha com erro e oferece enviar (e-mail, Gmail ou GitHub) na próxima vez. */
object Relatorio {
    const val EMAIL = "lohanlilson@gmail.com"
    private const val REPO = "lohanlilson/DispersioPDF"

    private fun file(ctx: Context) = File(ctx.filesDir, "ultimo_erro.txt")
    private fun log(ctx: Context) = File(ctx.filesDir, "erros.log")

    fun info() = "Dispersio PDF para Android ${BuildConfig.VERSION_NAME}\n" +
        "Aparelho: ${Build.MANUFACTURER} ${Build.MODEL} — Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})"

    /** Liga a gravação de erros que fecham o app. */
    fun install(ctx: Context) {
        val app = ctx.applicationContext
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            runCatching {
                val txt = "Data: ${SimpleDateFormat("dd/MM/yyyy HH:mm:ss", Locale("pt", "BR")).format(Date())}\n${info()}\n" +
                    "Linha de execução: ${t.name}\n\n${e.stackTraceToString().take(12000)}"
                file(app).writeText(txt)
                log(app).appendText("=".repeat(60) + "\n" + txt + "\n")
                if (log(app).length() > 1_000_000) log(app).writeText(log(app).readText().takeLast(500_000))
            }
            previous?.uncaughtException(t, e)
        }
    }

    fun pending(ctx: Context): String? = file(ctx).takeIf { it.exists() }?.readText()
    fun clear(ctx: Context) { file(ctx).delete() }
    fun lastErrors(ctx: Context): String = log(ctx).takeIf { it.exists() }?.readText()?.split("=".repeat(60))
        ?.map { it.trim() }?.filter { it.isNotEmpty() }?.takeLast(3)?.joinToString("\n\n----\n\n") ?: ""

    private fun subject(what: String) = "Dispersio PDF Android ${BuildConfig.VERSION_NAME} — $what"

    /** Abre o app de e-mail (ou a lista de apps para compartilhar) com o relatório preenchido. */
    fun sendEmail(ctx: Context, body: String, what: String = "relatório de erro") {
        val i = Intent(Intent.ACTION_SEND).apply {
            type = "message/rfc822"
            putExtra(Intent.EXTRA_EMAIL, arrayOf(EMAIL))
            putExtra(Intent.EXTRA_SUBJECT, subject(what))
            putExtra(Intent.EXTRA_TEXT, body)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        try { ctx.startActivity(Intent.createChooser(i, "Enviar relatório").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
        catch (_: ActivityNotFoundException) { copyText(ctx, "Relatório", body) }
    }

    fun openGithub(ctx: Context, body: String, what: String = "relatório de erro") {
        val url = "https://github.com/$REPO/issues/new?title=" + Uri.encode(subject(what)) +
            "&body=" + Uri.encode("```\n" + body.take(5000) + "\n```")
        runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
    }
}

/** Na abertura: o app fechou com erro da última vez? */
@Composable
fun CrashReportDialog(report: String, onDone: () -> Unit) {
    val ctx = LocalContext.current
    AlertDialog(
        onDismissRequest = { Relatorio.clear(ctx); onDone() },
        title = { Text("O app fechou com um erro") },
        text = {
            Column(Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState())) {
                Text("Quer enviar o relatório ao desenvolvedor para corrigir? Nenhum documento é enviado, só os dados técnicos abaixo.")
                Text(report.take(1500), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.heightIn(min = 0.dp))
            }
        },
        confirmButton = {
            TextButton({ Relatorio.sendEmail(ctx, report); Relatorio.clear(ctx); onDone() }) { Text("Enviar") }
        },
        dismissButton = {
            Column {
                TextButton({ Relatorio.openGithub(ctx, report); Relatorio.clear(ctx); onDone() }) { Text("Pelo GitHub") }
                TextButton({ Relatorio.clear(ctx); onDone() }) { Text("Agora não") }
            }
        },
    )
}
