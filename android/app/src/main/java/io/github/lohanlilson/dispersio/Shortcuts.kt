package io.github.lohanlilson.dispersio

import android.content.Context
import android.content.Intent
import androidx.core.content.pm.ShortcutInfoCompat
import androidx.core.content.pm.ShortcutManagerCompat
import androidx.core.graphics.drawable.IconCompat

/** Atalhos do ícone: "Escanear" e "Abrir PDF" (fixos, em res/xml/shortcuts.xml) + os 2 últimos documentos. */
object Shortcuts {
    const val SCAN = "io.github.lohanlilson.dispersio.ESCANEAR"
    const val OPEN = "io.github.lohanlilson.dispersio.ABRIR"
    const val RECENT = "io.github.lohanlilson.dispersio.RECENTE"
    // atalhos fixados na tela inicial antes da troca de nome
    const val OLD_SCAN = "io.github.lohanlilson.lumenpdf.ESCANEAR"
    const val OLD_OPEN = "io.github.lohanlilson.lumenpdf.ABRIR"
    const val OLD_RECENT = "io.github.lohanlilson.lumenpdf.RECENTE"
    const val EXTRA_URI = "uri"

    fun updateRecents(ctx: Context, list: List<RecentDoc>) = runCatching {
        val items = list.take(2).mapIndexed { i, r ->
            val label = r.name.removeSuffix(".pdf").removeSuffix(".PDF")
            ShortcutInfoCompat.Builder(ctx, "recente_${r.key}")
                .setShortLabel(label.take(24))
                .setLongLabel(label.take(40))
                .setIcon(IconCompat.createWithResource(ctx, R.drawable.ic_shortcut_doc))
                .setRank(i)
                .setIntent(Intent(RECENT).setClass(ctx, MainActivity::class.java).putExtra(EXTRA_URI, r.uri)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP))
                .build()
        }
        ShortcutManagerCompat.setDynamicShortcuts(ctx, items)
    }
}
