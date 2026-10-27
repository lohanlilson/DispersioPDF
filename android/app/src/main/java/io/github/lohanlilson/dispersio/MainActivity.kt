package io.github.lohanlilson.dispersio

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.fragment.app.FragmentActivity

/** FragmentActivity: a janela de digital/rosto (BiometricPrompt) precisa dela. */
class MainActivity : FragmentActivity() {
    private val vm: AppVm by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (savedInstanceState == null) handle(intent)
        setContent { DispersioTheme(vm.prefs.theme) { DispersioRoot(vm) } }
    }

    override fun onStop() {
        super.onStop()
        vm.flushAutosave()   // saiu do app sem salvar: grava antes que o Android encerre o processo
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handle(intent)
    }

    @Suppress("DEPRECATION")
    private fun handle(i: Intent?) {
        val uri: Uri? = when (i?.action) {
            Intent.ACTION_VIEW -> i.data
            Intent.ACTION_SEND ->
                if (Build.VERSION.SDK_INT >= 33) i.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
                else i.getParcelableExtra(Intent.EXTRA_STREAM)
            Shortcuts.SCAN, Shortcuts.OLD_SCAN -> { vm.pendingAction = "scan"; null }
            Shortcuts.OPEN, Shortcuts.OLD_OPEN -> { vm.pendingAction = "open"; null }
            Shortcuts.RECENT, Shortcuts.OLD_RECENT -> {
                val key = i.getStringExtra(Shortcuts.EXTRA_URI)
                vm.recents.list().firstOrNull { it.uri == key }?.let { vm.openRecent(it) }
                null
            }
            else -> null
        }
        if (uri != null) vm.open(uri, fromPicker = false)
    }
}
