package io.github.lohanlilson.dispersio

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

data class RecentDoc(val uri: String, val name: String, val page: Int, val openedAt: Long) {
    val key: String get() = sha1(uri)
}

fun sha1(s: String): String =
    MessageDigest.getInstance("SHA-1").digest(s.toByteArray()).joinToString("") { "%02x".format(it) }.take(20)

/** Arquivos abertos recentemente (com a última página lida). */
class Recents(private val context: Context) {
    private val prefs = context.getSharedPreferences("recentes", Context.MODE_PRIVATE)

    fun list(): List<RecentDoc> {
        val arr = runCatching { JSONArray(prefs.getString("lista", "[]")) }.getOrElse { JSONArray() }
        return (0 until arr.length()).map {
            val o = arr.getJSONObject(it)
            RecentDoc(o.getString("uri"), o.getString("name"), o.optInt("page"), o.optLong("at"))
        }
    }

    private fun save(items: List<RecentDoc>) {
        val arr = JSONArray()
        items.take(40).forEach {
            arr.put(JSONObject().put("uri", it.uri).put("name", it.name).put("page", it.page).put("at", it.openedAt))
        }
        prefs.edit().putString("lista", arr.toString()).apply()
    }

    fun touch(uri: String, name: String, page: Int? = null) {
        val old = list()
        val prev = old.firstOrNull { it.uri == uri }
        save(listOf(RecentDoc(uri, name, page ?: prev?.page ?: 0, System.currentTimeMillis())) + old.filter { it.uri != uri })
    }

    fun setPage(uri: String, page: Int) {
        save(list().map { if (it.uri == uri) it.copy(page = page) else it })
    }

    fun remove(uri: String) {
        save(list().filter { it.uri != uri })
        thumbFile(uri).delete()
    }

    fun thumbFile(uri: String) = File(context.cacheDir, "miniaturas/${sha1(uri)}.png")
}

fun displayName(context: Context, uri: Uri): String {
    if (uri.scheme == "file") return File(uri.path ?: "documento.pdf").name
    return runCatching {
        context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        }
    }.getOrNull() ?: uri.lastPathSegment?.substringAfterLast('/') ?: "documento.pdf"
}

/**
 * Prepara um arquivo para abrir. Arquivos escolhidos pelo seletor do Android ficam com permissão permanente
 * (dá para reabrir pelos recentes e salvar no mesmo lugar). Os recebidos de outros apps (WhatsApp, e-mail…)
 * só podem ser lidos agora, então são copiados para a pasta do app.
 */
fun prepareUri(context: Context, uri: Uri, fromPicker: Boolean): Uri {
    if (uri.scheme == "file") return uri
    if (fromPicker) {
        runCatching {
            context.contentResolver.takePersistableUriPermission(
                uri, Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        }.onFailure {
            runCatching { context.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION) }
        }
        return uri
    }
    val name = displayName(context, uri).let { if (it.lowercase().endsWith(".pdf")) it else "$it.pdf" }
    val dir = File(context.filesDir, "recebidos").apply { mkdirs() }
    var dest = File(dir, name)
    if (dest.exists()) {
        // mesmo arquivo recebido de novo: reaproveita; nome igual e conteúdo diferente: numera
        val len = runCatching { context.contentResolver.openFileDescriptor(uri, "r")?.use { it.statSize } }.getOrNull()
        if (len == null || len != dest.length()) {
            var n = 2
            val base = name.removeSuffix(".pdf").removeSuffix(".PDF")
            while (dest.exists()) dest = File(dir, "$base ($n).pdf").also { n++ }
        } else {
            return Uri.fromFile(dest)
        }
    }
    context.contentResolver.openInputStream(uri)?.use { inp -> dest.outputStream().use { inp.copyTo(it) } }
        ?: error("Não foi possível ler o arquivo recebido")
    return Uri.fromFile(dest)
}
