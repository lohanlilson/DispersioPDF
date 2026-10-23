package io.github.lohanlilson.lumenpdf

import android.app.Activity
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.automirrored.filled.RotateRight
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.FileCopy
import androidx.compose.material.icons.filled.SelectAll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.google.mlkit.vision.documentscanner.GmsDocumentScannerOptions
import com.google.mlkit.vision.documentscanner.GmsDocumentScanning
import com.google.mlkit.vision.documentscanner.GmsDocumentScanningResult
import kotlinx.coroutines.launch

/** Abre o scanner de documentos do Google; devolve o PDF gerado. */
@Composable
fun rememberScanner(onPdf: (Uri) -> Unit): () -> Unit {
    val ctx = LocalContext.current
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartIntentSenderForResult()) { r ->
        if (r.resultCode == Activity.RESULT_OK) {
            GmsDocumentScanningResult.fromActivityResultIntent(r.data)?.pdf?.uri?.let(onPdf)
        }
    }
    return {
        val act = ctx.findActivity()
        if (act != null) {
            val opts = GmsDocumentScannerOptions.Builder()
                .setGalleryImportAllowed(true)
                .setPageLimit(60)
                .setResultFormats(GmsDocumentScannerOptions.RESULT_FORMAT_PDF)
                .setScannerMode(GmsDocumentScannerOptions.SCANNER_MODE_FULL)
                .build()
            GmsDocumentScanning.getClient(opts).getStartScanIntent(act)
                .addOnSuccessListener { launcher.launch(IntentSenderRequest.Builder(it).build()) }
                .addOnFailureListener {
                    Toast.makeText(ctx, "O scanner precisa do Google Play Services atualizado: ${it.message}", Toast.LENGTH_LONG).show()
                }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OrganizeScreen(vm: AppVm, d: ViewerDoc, onClose: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val sel = remember { mutableStateListOf<Int>() }
    var confirmDelete by remember { mutableStateOf(false) }
    var warnSigned by remember { mutableStateOf<(() -> Unit)?>(null) }
    var addMenu by remember { mutableStateOf(false) }
    var warned by remember { mutableStateOf(false) }
    val n = d.pageCount

    fun guarded(action: () -> Unit) {
        if (d.signatures.isNotEmpty() && !warned) warnSigned = action else action()
    }
    fun insertAt() = (sel.maxOrNull()?.plus(1)) ?: n

    val pickPdf = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { u ->
        if (u != null) scope.launch {
            val f = vm.cacheCopy(u)
            val at = insertAt()
            guarded { vm.pages(d, "inserir as páginas") { doc, keep -> Editor.insertPdf(doc, f, at, keep) } }
        }
    }
    val scan = rememberScanner { u ->
        scope.launch {
            val f = vm.cacheCopy(u, "escaneado.pdf")
            val at = insertAt()
            guarded { vm.pages(d, "inserir a digitalização") { doc, keep -> Editor.insertPdf(doc, f, at, keep) } }
        }
    }

    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text(if (sel.isEmpty()) "Organizar páginas" else "${sel.size} selecionada(s)") },
                    navigationIcon = { IconButton(onClose) { Icon(Icons.Filled.Close, "Fechar") } },
                    actions = {
                        IconButton({ if (sel.size == n) sel.clear() else { sel.clear(); sel.addAll(0 until n) } }) {
                            Icon(Icons.Filled.SelectAll, "Selecionar todas")
                        }
                    },
                )
            },
            bottomBar = {
                Surface(shadowElevation = 8.dp) {
                    Row(Modifier.fillMaxWidth().navigationBarsPadding().padding(6.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
                        val has = sel.isNotEmpty() && !d.busy
                        OrgButton(Icons.AutoMirrored.Filled.RotateRight, "Girar", has) {
                            val pages = sel.toList()
                            guarded { vm.pages(d, "girar") { doc, _ -> Editor.rotate(doc, pages, 90) } }
                        }
                        OrgButton(Icons.AutoMirrored.Filled.ArrowBack, "Antes", has && sel.min() > 0) {
                            val s = sel.sorted()
                            val order = (0 until n).toMutableList()
                            for (i in s) { val k = order.indexOf(i); if (k > 0) { order.removeAt(k); order.add(k - 1, i) } }
                            guarded {
                                vm.pages(d, "mover") { doc, _ -> Editor.reorder(doc, order) }
                                sel.clear(); sel.addAll(s.map { order.indexOf(it) })
                            }
                        }
                        OrgButton(Icons.AutoMirrored.Filled.ArrowForward, "Depois", has && sel.max() < n - 1) {
                            val s = sel.sortedDescending()
                            val order = (0 until n).toMutableList()
                            for (i in s) { val k = order.indexOf(i); if (k < n - 1) { order.removeAt(k); order.add(k + 1, i) } }
                            guarded {
                                vm.pages(d, "mover") { doc, _ -> Editor.reorder(doc, order) }
                                sel.clear(); sel.addAll(s.map { order.indexOf(it) })
                            }
                        }
                        OrgButton(Icons.Filled.FileCopy, "Extrair", has) {
                            val pages = sel.sorted()
                            scope.launch {
                                val f = vm.extract(d, pages)
                                Toast.makeText(ctx, "${pages.size} página(s) salvas em “${f.name}”", Toast.LENGTH_LONG).show()
                                onClose()
                                vm.open(Uri.fromFile(f), fromPicker = false)
                            }
                        }
                        OrgButton(Icons.Filled.Delete, "Excluir", has && sel.size < n) { confirmDelete = true }
                        Box {
                            OrgButton(Icons.Filled.Add, "Inserir", !d.busy) { addMenu = true }
                            DropdownMenu(addMenu, { addMenu = false }) {
                                DropdownMenuItem(text = { Text("Páginas de outro PDF…") }, onClick = { addMenu = false; pickPdf.launch(arrayOf("application/pdf")) })
                                DropdownMenuItem(text = { Text("Escanear com a câmera…") }, onClick = { addMenu = false; scan() })
                                DropdownMenuItem(text = { Text("Página em branco") }, onClick = {
                                    addMenu = false
                                    val at = insertAt()
                                    guarded { vm.pages(d, "inserir a página") { doc, _ -> Editor.insertBlank(doc, at) } }
                                })
                            }
                        }
                    }
                }
            },
        ) { pad ->
            Box(Modifier.fillMaxSize().padding(pad)) {
                if (d.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                LazyVerticalGrid(
                    GridCells.Adaptive(112.dp),
                    contentPadding = PaddingValues(12.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    itemsIndexed(d.pdf.sizes, key = { i, _ -> "${d.pdf.id}#$i" }) { i, sz ->
                        PageThumb(vm, d, i, sz, i in sel) { if (i in sel) sel.remove(i) else sel.add(i) }
                    }
                }
            }
        }
    }
    if (confirmDelete) AlertDialog(
        onDismissRequest = { confirmDelete = false },
        title = { Text("Excluir páginas") },
        text = { Text("Excluir ${sel.size} página(s)? Dá para desfazer depois.") },
        confirmButton = {
            TextButton({
                confirmDelete = false
                val pages = sel.toList()
                sel.clear()
                guarded { vm.pages(d, "excluir as páginas") { doc, _ -> Editor.delete(doc, pages) } }
            }) { Text("Excluir") }
        },
        dismissButton = { TextButton({ confirmDelete = false }) { Text("Cancelar") } },
    )
    warnSigned?.let { act ->
        AlertDialog(
            onDismissRequest = { warnSigned = null },
            title = { Text("Documento assinado") },
            text = { Text("Mudar as páginas de um documento assinado invalida as assinaturas digitais. Continuar?") },
            confirmButton = { TextButton({ warnSigned = null; warned = true; act() }) { Text("Continuar") } },
            dismissButton = { TextButton({ warnSigned = null }) { Text("Cancelar") } },
        )
    }
}

@Composable
private fun OrgButton(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, enabled: Boolean, onClick: () -> Unit) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        IconButton(onClick, enabled = enabled) { Icon(icon, label) }
        Text(label, style = MaterialTheme.typography.labelSmall,
            color = if (enabled) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.38f))
    }
}

@Composable
private fun PageThumb(vm: AppVm, d: ViewerDoc, i: Int, sz: PageSize, selected: Boolean, onClick: () -> Unit) {
    val pdf = d.pdf
    val bmp by produceState<ImageBitmap?>(null, pdf, i) { value = vm.engine.render(pdf, i, 260).asImageBitmap() }
    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.clickable(onClick = onClick)) {
        Box(Modifier.fillMaxWidth().aspectRatio(1f / sz.ratio.coerceIn(0.3f, 3f))
            .shadow(if (selected) 6.dp else 2.dp, RoundedCornerShape(4.dp))
            .background(Color.White)
            .border(if (selected) 3.dp else 0.dp, MaterialTheme.colorScheme.primary, RoundedCornerShape(4.dp))) {
            bmp?.let { Image(it, "Página ${i + 1}", Modifier.fillMaxSize(), contentScale = ContentScale.Fit) }
            if (selected) Box(Modifier.align(Alignment.TopEnd).padding(4.dp).size(22.dp)
                .background(MaterialTheme.colorScheme.primary, CircleShape), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Check, null, tint = Color.White, modifier = Modifier.size(16.dp))
            }
        }
        Text("${i + 1}", style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(top = 4.dp))
    }
}
