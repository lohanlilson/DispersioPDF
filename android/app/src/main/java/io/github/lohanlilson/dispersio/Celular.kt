package io.github.lohanlilson.dispersio

import android.content.Context
import android.net.Uri
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import kotlin.coroutines.resume

/** Continuar do computador / enviar para o computador: lê o QR que o Dispersio PDF do computador mostra e
 *  conversa com ele pela rede Wi-Fi (sem nuvem). */
object Celular {
    /** Abre o leitor de QR do Google Play (não pede permissão de câmera). null = cancelou. */
    suspend fun scan(ctx: Context): String? = suspendCancellableCoroutine { cont ->
        val opts = GmsBarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
        GmsBarcodeScanning.getClient(ctx, opts).startScan()
            .addOnSuccessListener { if (cont.isActive) cont.resume(it.rawValue) }
            .addOnCanceledListener { if (cont.isActive) cont.resume(null) }
            .addOnFailureListener { if (cont.isActive) cont.resume(null) }
    }

    /** O QR é do Dispersio PDF do computador? (http://IP:porta/código) */
    fun isLink(s: String?) = s != null && Regex("^http://[\\d.]+:\\d+/[A-Za-z0-9_-]{8,}/?$").matches(s.trim())

    private fun conn(url: String, method: String = "GET"): HttpURLConnection =
        (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = method; connectTimeout = 6000; readTimeout = 60000
        }

    data class Info(val name: String, val page: Int, val hasDoc: Boolean)

    suspend fun info(base: String): Info = withContext(Dispatchers.IO) {
        val c = conn(base.trimEnd('/') + "/info")
        try {
            val j = JSONObject(c.inputStream.bufferedReader().readText())
            Info(j.optString("name", "Documento.pdf"), j.optInt("page", 0), j.optBoolean("has_doc", false))
        } finally { c.disconnect() }
    }

    /** Baixa o documento oferecido pelo computador para a pasta do app. */
    suspend fun download(ctx: Context, base: String, name: String, onProgress: (Float) -> Unit = {}): File = withContext(Dispatchers.IO) {
        val c = conn(base.trimEnd('/') + "/doc.pdf")
        try {
            val total = c.contentLengthLong
            val safe = name.replace(Regex("[\\\\/:*?\"<>|]"), "_").ifBlank { "Documento.pdf" }.let { if (it.lowercase().endsWith(".pdf")) it else "$it.pdf" }
            val out = File(File(ctx.filesDir, "recebidos").apply { mkdirs() }, safe)
            c.inputStream.use { i ->
                out.outputStream().use { o ->
                    val buf = ByteArray(64 * 1024); var n: Int; var got = 0L
                    while (i.read(buf).also { n = it } > 0) { o.write(buf, 0, n); got += n; if (total > 0) onProgress(got.toFloat() / total) }
                }
            }
            out
        } finally { c.disconnect() }
    }

    /** Manda um PDF para o computador, que abre na página indicada. */
    suspend fun upload(base: String, file: File, name: String, page: Int) = withContext(Dispatchers.IO) {
        val c = conn(base.trimEnd('/') + "/upload?name=" + Uri.encode(name) + "&page=$page", "POST")
        try {
            c.doOutput = true
            c.setFixedLengthStreamingMode(file.length())
            c.setRequestProperty("Content-Type", "application/pdf")
            file.inputStream().use { i -> c.outputStream.use { i.copyTo(it) } }
            if (c.responseCode != 200) throw IllegalStateException("o computador respondeu ${c.responseCode}")
        } finally { c.disconnect() }
    }
}
