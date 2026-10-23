package io.github.lohanlilson.lumenpdf

import android.app.Application
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Documento aberto no visualizador e o estado da tela dele. */
class ViewerDoc(val pdf: OpenPdf, val uri: String, val name: String, val startPage: Int) {
    var zoom by mutableFloatStateOf(1f)
    var night by mutableStateOf(false)
    var page by mutableIntStateOf(startPage)
    var query by mutableStateOf("")
    val hits = mutableStateListOf<SearchHit>()
    var hitIndex by mutableIntStateOf(-1)
    var searching by mutableStateOf(false)
    var searchPage by mutableIntStateOf(0)
    val pageCount get() = pdf.sizes.size
}

data class PendingPassword(val uri: Uri, val name: String, val wrong: Boolean)

class AppVm(app: Application) : AndroidViewModel(app) {
    private val lumen = app as LumenApp
    val engine get() = lumen.engine
    val recents get() = lumen.recents

    var doc by mutableStateOf<ViewerDoc?>(null)
        private set
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
    var password by mutableStateOf<PendingPassword?>(null)
    var recentList by mutableStateOf(recents.list())
        private set
    var update by mutableStateOf<UpdateInfo?>(null)
    private var checkedUpdate = false

    fun refreshRecents() {
        recentList = recents.list()
    }

    /** fromPicker = escolhido pelo seletor do Android (permissão permanente); senão, recebido de outro app. */
    fun open(uri: Uri, fromPicker: Boolean) = viewModelScope.launch {
        loading = true
        try {
            val name = withContext(Dispatchers.IO) { displayName(getApplication(), uri) }
            val ready = withContext(Dispatchers.IO) { prepareUri(getApplication(), uri, fromPicker) }
            openPrepared(ready, name, null)
        } catch (e: Exception) {
            error = "Não foi possível abrir o arquivo.\n${e.message ?: e.javaClass.simpleName}"
        } finally {
            loading = false
        }
    }

    fun openRecent(r: RecentDoc) = viewModelScope.launch {
        loading = true
        try {
            openPrepared(Uri.parse(r.uri), r.name, null)
        } catch (e: Exception) {
            error = "Não foi possível abrir “${r.name}”. Ele pode ter sido movido ou apagado."
        } finally {
            loading = false
        }
    }

    fun submitPassword(pwd: String) = viewModelScope.launch {
        val p = password ?: return@launch
        password = null
        loading = true
        try {
            openPrepared(p.uri, p.name, pwd)
        } catch (e: Exception) {
            error = "Não foi possível abrir o arquivo.\n${e.message ?: ""}"
        } finally {
            loading = false
        }
    }

    private suspend fun openPrepared(uri: Uri, name: String, pwd: String?) {
        val pdf = try {
            engine.open(getApplication(), uri, pwd)
        } catch (e: PasswordNeeded) {
            password = PendingPassword(uri, name, pwd != null)
            return
        }
        doc?.let { closeDoc() }
        val key = uri.toString()
        val start = recents.list().firstOrNull { it.uri == key }?.page?.coerceIn(0, pdf.sizes.size - 1) ?: 0
        recents.touch(key, name)
        doc = ViewerDoc(pdf, key, name, start)
        refreshRecents()
    }

    fun closeDoc() {
        val d = doc ?: return
        recents.setPage(d.uri, d.page)
        doc = null
        viewModelScope.launch { engine.close(d.pdf) }
        refreshRecents()
    }

    fun removeRecent(r: RecentDoc) {
        recents.remove(r.uri)
        refreshRecents()
    }

    fun search(d: ViewerDoc, q: String) = viewModelScope.launch {
        d.query = q
        d.hits.clear()
        d.hitIndex = -1
        if (q.isBlank()) return@launch
        d.searching = true
        try {
            val res = engine.search(d.pdf, q) { p -> d.searchPage = p }
            d.hits.addAll(res)
            d.hitIndex = res.indexOfFirst { it.page >= d.page }.let { if (it < 0 && res.isNotEmpty()) 0 else it }
        } finally {
            d.searching = false
        }
    }

    fun checkUpdate() {
        if (checkedUpdate) return
        checkedUpdate = true
        viewModelScope.launch {
            update = runCatching { Updater.check() }.getOrNull()
        }
    }

    override fun onCleared() {
        doc?.let { d -> recents.setPage(d.uri, d.page) }
        super.onCleared()
    }
}
