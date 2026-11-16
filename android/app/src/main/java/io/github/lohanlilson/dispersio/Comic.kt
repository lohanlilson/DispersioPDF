package io.github.lohanlilson.dispersio

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.util.LruCache
import com.github.junrar.Archive
import com.github.junrar.rarfile.FileHeader
import java.io.ByteArrayOutputStream
import java.io.File
import java.security.MessageDigest
import java.util.zip.ZipFile

/** Tipos aceitos em “Abrir”: PDF, livros e quadrinhos (muitos .cbz/.cbr chegam como “octet-stream”). */
val OPEN_TYPES = arrayOf("application/pdf", "application/epub+zip", "application/vnd.comicbook+zip", "application/vnd.comicbook-rar",
    "application/x-cbz", "application/x-cbr", "application/zip", "application/x-rar-compressed", "application/vnd.rar", "application/octet-stream")

/** Quadrinhos e mangás (.cbz/.zip, .cbr/.rar): lê as imagens direto do arquivo, sem converter para PDF. */
object Comic {
    val IMG = setOf("jpg", "jpeg", "png", "webp", "gif", "bmp", "avif", "heic", "heif")
    val COMIC_EXT = setOf("cbz", "cbr", "zip", "rar", "cb7")

    fun isComicName(name: String) = name.substringAfterLast('.', "").lowercase() in COMIC_EXT

    fun naturalKey(s: String): List<Comparable<*>> =
        Regex("(\\d+)|(\\D+)").findAll(s.lowercase()).map { m -> m.groupValues[1].toBigIntegerOrNull() ?: m.value }.toList()

    val naturalOrder = Comparator<String> { a, b ->
        val ka = naturalKey(a); val kb = naturalKey(b)
        for (i in 0 until minOf(ka.size, kb.size)) {
            val x = ka[i]; val y = kb[i]
            val c = if (x is java.math.BigInteger && y is java.math.BigInteger) x.compareTo(y) else x.toString().compareTo(y.toString())
            if (c != 0) return@Comparator c
        }
        ka.size - kb.size
    }

    private fun junk(n: String) = n.startsWith("__MACOSX/") || n.substringAfterLast('/').startsWith(".") ||
        n.substringAfterLast('/').lowercase() in setOf("thumbs.db", "desktop.ini")

    /** Livro aberto: o arquivo local e a lista de páginas em ordem de leitura. */
    class Book(val file: File, val key: String, val name: String, val pages: List<String>, val rtl: Boolean, private val rar: Boolean) {
        private var zip: ZipFile? = null
        private var archive: Archive? = null
        private var headers: Map<String, FileHeader> = emptyMap()

        @Synchronized fun bytes(i: Int): ByteArray {
            val n = pages[i]
            return if (rar) {
                val a = archive ?: Archive(file).also { ar -> archive = ar; headers = ar.fileHeaders.associateBy { it.fileName.replace('\\', '/') } }
                ByteArrayOutputStream().also { a.extractFile(headers[n], it) }.toByteArray()
            } else {
                val z = zip ?: ZipFile(file).also { zip = it }
                z.getInputStream(z.getEntry(n)).use { it.readBytes() }
            }
        }

        /** Página decodificada com no máximo maxW de largura (economiza memória). */
        fun bitmap(i: Int, maxW: Int): Bitmap? {
            val b = runCatching { bytes(i) }.getOrNull() ?: return null
            val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(b, 0, b.size, o)
            var sample = 1
            while (o.outWidth / (sample * 2) >= maxW) sample *= 2
            return BitmapFactory.decodeByteArray(b, 0, b.size, BitmapFactory.Options().apply { inSampleSize = sample })
        }

        /** Proporção (altura/largura) de cada página, sem decodificar as imagens. */
        fun ratio(i: Int): Float {
            val b = runCatching { bytes(i) }.getOrNull() ?: return 1.4f
            val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(b, 0, b.size, o)
            return if (o.outWidth > 0) o.outHeight.toFloat() / o.outWidth else 1.4f
        }

        fun close() { runCatching { zip?.close() }; runCatching { archive?.close() } }
    }

    fun key(uri: Uri) = MessageDigest.getInstance("SHA-1").digest(uri.toString().toByteArray()).joinToString("") { "%02x".format(it) }.take(20)

    /** Copia para a pasta do app (o leitor precisa de acesso aleatório) e lista as páginas. */
    fun open(ctx: Context, uri: Uri, name: String): Book {
        val key = key(uri)
        val dir = File(ctx.cacheDir, "hq").apply { mkdirs() }
        val f = File(dir, key + "." + name.substringAfterLast('.', "cbz").lowercase())
        if (!f.exists() || f.length() == 0L) {
            // guarda só os últimos capítulos abertos
            dir.listFiles()?.sortedByDescending { it.lastModified() }?.drop(6)?.forEach { it.delete() }
            ctx.contentResolver.openInputStream(uri)!!.use { i -> f.outputStream().use { i.copyTo(it) } }
        }
        f.setLastModified(System.currentTimeMillis())
        val magic = f.inputStream().use { val b = ByteArray(4); it.read(b); b }
        val isZip = magic[0] == 'P'.code.toByte() && magic[1] == 'K'.code.toByte()
        val isRar = magic[0] == 'R'.code.toByte() && magic[1] == 'a'.code.toByte() && magic[2] == 'r'.code.toByte()
        var info: String? = null
        val pages: List<String> = when {
            isZip -> ZipFile(f).use { z ->
                z.getEntry("ComicInfo.xml")?.let { e -> info = z.getInputStream(e).use { it.readBytes().decodeToString() } }
                z.entries().toList().map { it.name }.filter { !it.endsWith("/") && !junk(it) && it.substringAfterLast('.', "").lowercase() in IMG }
            }
            isRar -> try {
                Archive(f).use { a ->
                    a.fileHeaders.filter { !it.isDirectory }.map { it.fileName.replace('\\', '/') }.also { names ->
                        a.fileHeaders.firstOrNull { it.fileName.endsWith("ComicInfo.xml") }?.let { h ->
                            info = ByteArrayOutputStream().also { a.extractFile(h, it) }.toString("UTF-8")
                        }
                    }.filter { !junk(it) && it.substringAfterLast('.', "").lowercase() in IMG }
                }
            } catch (e: com.github.junrar.exception.UnsupportedRarV5Exception) {
                throw IllegalStateException("Este .cbr usa o formato RAR5, que o celular ainda não abre. No computador ele abre normalmente; lá dá para salvar como PDF.")
            }
            else -> throw IllegalStateException("Formato não reconhecido. Use .cbz (ZIP) ou .cbr (RAR).")
        }.sortedWith(naturalOrder)
        if (pages.isEmpty()) throw IllegalStateException("Nenhuma imagem encontrada neste arquivo.")
        val rtl = info?.let { Regex("<Manga>\\s*YesAndRightToLeft\\s*</Manga>", RegexOption.IGNORE_CASE).containsMatchIn(it) } ?: false
        return Book(f, key, name, pages, rtl, isRar)
    }

    // ------------------------------------------------------------ progresso e modo
    private fun sp(ctx: Context) = ctx.getSharedPreferences("quadrinhos", Context.MODE_PRIVATE)
    fun savedPage(ctx: Context, key: String) = sp(ctx).getInt("pag_$key", 0)
    fun savePage(ctx: Context, key: String, page: Int, total: Int) =
        sp(ctx).edit().putInt("pag_$key", page).putInt("tot_$key", total).putLong("quando_$key", System.currentTimeMillis()).apply()
    /** 0..1 (lido até o fim = 1), ou null se nunca abriu. */
    fun progress(ctx: Context, key: String): Float? {
        val t = sp(ctx).getInt("tot_$key", 0)
        if (t == 0) return null
        return ((sp(ctx).getInt("pag_$key", 0) + 1f) / t).coerceIn(0f, 1f)
    }
    fun lastRead(ctx: Context, key: String) = sp(ctx).getLong("quando_$key", 0)
    fun mode(ctx: Context, series: String, default: String) = sp(ctx).getString("modo_$series", null) ?: default
    fun saveMode(ctx: Context, series: String, mode: String) = sp(ctx).edit().putString("modo_$series", mode).apply()
}

/** Cache de páginas decodificadas (limite pela memória disponível). */
class PageCache : LruCache<Int, Bitmap>((Runtime.getRuntime().maxMemory() / 6).toInt()) {
    override fun sizeOf(key: Int, value: Bitmap) = value.allocationByteCount
}
