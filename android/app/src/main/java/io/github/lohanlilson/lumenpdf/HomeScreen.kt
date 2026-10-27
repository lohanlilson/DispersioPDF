package io.github.lohanlilson.lumenpdf

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material.icons.filled.Science
import androidx.compose.material.icons.filled.DocumentScanner
import androidx.compose.material.icons.filled.MergeType
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.SystemUpdate
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun HomeScreen(vm: AppVm) {
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        if (uri != null) vm.open(uri, fromPicker = true)
    }
    LaunchedEffect(Unit) {
        vm.refreshRecents()
        vm.checkUpdate()
    }
    Scaffold(
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { picker.launch(arrayOf("application/pdf")) },
                icon = { Icon(Icons.Filled.FolderOpen, null) },
                text = { Text("Abrir PDF") },
                containerColor = MaterialTheme.colorScheme.primary,
                contentColor = MaterialTheme.colorScheme.onPrimary,
            )
        },
    ) { pad ->
        LazyColumn(
            Modifier.fillMaxSize().padding(bottom = pad.calculateBottomPadding()),
            contentPadding = PaddingValues(bottom = 96.dp),
        ) {
            item { Hero() }
            item { QuickActions(vm) }
            item {
                Text("Recentes", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.padding(start = 20.dp, top = 20.dp, bottom = 8.dp))
            }
            if (vm.recentList.isEmpty()) {
                item {
                    Text("Nenhum documento aberto ainda.\nToque em “Abrir PDF” ou abra um PDF pelo WhatsApp, e-mail ou Arquivos e escolha o Dispersio PDF.",
                        style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp))
                }
            }
            items(vm.recentList, key = { it.uri }) { r -> RecentRow(vm, r) }
        }
    }
    if (vm.showSettings) SettingsScreen(vm) { vm.showSettings = false }
    if (vm.showArticles) ArticlesScreen(vm) { vm.showArticles = false }
}

@Composable
private fun Hero() {
    Box(
        Modifier.fillMaxWidth()
            .background(Brush.linearGradient(listOf(Color(0xFF3C1896), Color(0xFF8250FF))))
            .statusBarsPadding()
            .padding(horizontal = 20.dp, vertical = 22.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Image(painterResource(R.drawable.lumen_logo), null, Modifier.size(52.dp))
            Spacer(Modifier.width(14.dp))
            Column {
                Text("Dispersio PDF", color = Color.White, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                Text("Leia, comente, preencha e assine seus PDFs", color = Color.White.copy(alpha = 0.85f),
                    style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

@Composable
private fun RecentRow(vm: AppVm, r: RecentDoc) {
    val ctx = LocalContext.current
    var menu by remember { mutableStateOf(false) }
    val thumb by produceState<ImageBitmap?>(null, r.uri) {
        value = vm.engine.thumbnail(ctx, Uri.parse(r.uri), vm.recents.thumbFile(r.uri))?.asImageBitmap()
    }
    val fmt = remember { SimpleDateFormat("dd/MM/yyyy HH:mm", Locale("pt", "BR")) }
    Card(
        onClick = { vm.openRecent(r) },
        modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 5.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(1.dp),
    ) {
        Row(Modifier.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(48.dp, 64.dp).shadow(2.dp, RoundedCornerShape(4.dp)).clip(RoundedCornerShape(4.dp))
                .background(Color.White), contentAlignment = Alignment.Center) {
                val t = thumb
                if (t != null) Image(t, null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                else Image(painterResource(R.drawable.pdf_doc), null, Modifier.size(36.dp))
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(r.name, style = MaterialTheme.typography.bodyLarge, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text("${fmt.format(Date(r.openedAt))} · pág. ${r.page + 1}", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Box {
                IconButton({ menu = true }) { Icon(Icons.Filled.MoreVert, "Opções") }
                DropdownMenu(menu, { menu = false }) {
                    DropdownMenuItem(text = { Text("Remover dos recentes") }, onClick = { menu = false; vm.removeRecent(r) })
                }
            }
        }
    }
}

@Composable
private fun QuickActions(vm: AppVm) {
    val merge = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { list: List<Uri> ->
        if (list.size >= 2) vm.mergeAndOpen(list) else if (list.size == 1) vm.open(list[0], fromPicker = true)
    }
    val scan = rememberScanner { vm.openScanned(it) }
    val photos = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(60)) { list: List<Uri> ->
        if (list.isNotEmpty()) vm.imagesToPdf(list)
    }
    Column(Modifier.padding(horizontal = 14.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            ActionCard(Icons.Filled.DocumentScanner, "Escanear", "Câmera → PDF", Modifier.weight(1f)) { scan() }
            ActionCard(Icons.Filled.MergeType, "Juntar PDFs", "Vários em um", Modifier.weight(1f)) { merge.launch(arrayOf("application/pdf")) }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            ActionCard(Icons.Filled.PhotoLibrary, "Fotos → PDF", "Da galeria", Modifier.weight(1f)) {
                photos.launch(androidx.activity.result.PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
            }
            ActionCard(Icons.Filled.Settings, "Preferências", "Tema, nome, rubrica…", Modifier.weight(1f)) { vm.showSettings = true }
        }
        ActionCard(Icons.Filled.Science, "Artigos científicos", "Pesquise, baixe e traduza PDFs de pesquisa", Modifier.fillMaxWidth()) { vm.showArticles = true }
    }
}

@Composable
private fun ActionCard(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, sub: String, modifier: Modifier, onClick: () -> Unit) {
    Card(onClick = onClick, modifier = modifier, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(28.dp))
            Spacer(Modifier.width(10.dp))
            Column {
                Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                Text(sub, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}
