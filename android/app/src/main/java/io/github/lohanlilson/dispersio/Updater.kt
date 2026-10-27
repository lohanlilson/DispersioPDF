package io.github.lohanlilson.dispersio

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

data class UpdateInfo(val version: String, val notes: String, val apkUrl: String, val size: Long)

/** Atualização automática: as versões do app ficam nas Releases "android-vX.Y.Z" do GitHub. */
object Updater {
    // o nome antigo fica como reserva enquanto o repositório não é renomeado (depois o GitHub redireciona)
    private val REPOS = listOf("lohanlilson/DispersioPDF", "lohanlilson/LumenPDF")

    private fun parts(v: String) = Regex("\\d+").findAll(v).map { it.value.toInt() }.toList()

    fun newer(a: String, b: String): Boolean {
        val x = parts(a)
        val y = parts(b)
        for (i in 0 until maxOf(x.size, y.size)) {
            val p = x.getOrElse(i) { 0 }
            val q = y.getOrElse(i) { 0 }
            if (p != q) return p > q
        }
        return false
    }

    private fun get(url: String): HttpURLConnection =
        (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 15000
            readTimeout = 30000
            instanceFollowRedirects = true
            setRequestProperty("User-Agent", "DispersioPDF-Android/${BuildConfig.VERSION_NAME}")
            setRequestProperty("Accept", "application/vnd.github+json")
        }

    suspend fun check(): UpdateInfo? = withContext(Dispatchers.IO) {
        var arr: JSONArray? = null
        for (repo in REPOS) {
            val c = get("https://api.github.com/repos/$repo/releases?per_page=30")
            if (c.responseCode == 404) { c.disconnect(); continue }
            arr = c.inputStream.use { JSONArray(it.bufferedReader().readText()) }
            break
        }
        if (arr == null) return@withContext null
        for (i in 0 until arr.length()) {
            val r = arr.getJSONObject(i)
            val tag = r.optString("tag_name")
            if (!tag.startsWith("android-v") || r.optBoolean("draft") || r.optBoolean("prerelease")) continue
            val ver = tag.removePrefix("android-v")
            if (!newer(ver, BuildConfig.VERSION_NAME)) return@withContext null
            val assets = r.getJSONArray("assets")
            for (k in 0 until assets.length()) {
                val a = assets.getJSONObject(k)
                if (a.optString("name").endsWith(".apk")) {
                    return@withContext UpdateInfo(ver, r.optString("body"), a.getString("browser_download_url"), a.optLong("size"))
                }
            }
            return@withContext null
        }
        null
    }

    suspend fun download(context: Context, info: UpdateInfo, progress: (Float) -> Unit): File = withContext(Dispatchers.IO) {
        val dir = File(context.cacheDir, "atualizacao").apply { deleteRecursively(); mkdirs() }
        val out = File(dir, "DispersioPDF-${info.version}.apk")
        val c = get(info.apkUrl)
        val total = c.contentLengthLong.takeIf { it > 0 } ?: info.size
        c.inputStream.use { inp ->
            out.outputStream().use { o ->
                val buf = ByteArray(64 * 1024)
                var got = 0L
                while (true) {
                    val n = inp.read(buf)
                    if (n < 0) break
                    o.write(buf, 0, n)
                    got += n
                    if (total > 0) progress(got.toFloat() / total)
                }
            }
        }
        out
    }

    /** true se o Android já permite que o Dispersio instale a atualização. */
    fun canInstall(context: Context) =
        Build.VERSION.SDK_INT < 26 || context.packageManager.canRequestPackageInstalls()

    fun askInstallPermission(context: Context) {
        context.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    fun install(context: Context, apk: File) {
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", apk)
        context.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
