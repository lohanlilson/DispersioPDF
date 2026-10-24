package io.github.lohanlilson.lumenpdf

import android.content.Context
import androidx.compose.runtime.mutableStateOf

/** Preferências do app (guardadas no aparelho); mudar o valor já salva. */
class Prefs(ctx: Context) {
    private val sp = ctx.getSharedPreferences("prefs", Context.MODE_PRIVATE)

    private val _theme = mutableStateOf(sp.getString("tema", "sistema") ?: "sistema")
    var theme: String   // sistema | claro | escuro
        get() = _theme.value
        set(v) { _theme.value = v; sp.edit().putString("tema", v).apply() }

    private val _night = mutableStateOf(sp.getBoolean("noturno", false))
    var nightPages: Boolean
        get() = _night.value
        set(v) { _night.value = v; sp.edit().putBoolean("noturno", v).apply() }

    private val _remember = mutableStateOf(sp.getBoolean("lembrar_pagina", true))
    var rememberPage: Boolean
        get() = _remember.value
        set(v) { _remember.value = v; sp.edit().putBoolean("lembrar_pagina", v).apply() }

    private val _fields = mutableStateOf(sp.getBoolean("destacar_campos", true))
    var highlightFields: Boolean
        get() = _fields.value
        set(v) { _fields.value = v; sp.edit().putBoolean("destacar_campos", v).apply() }

    private val _update = mutableStateOf(sp.getBoolean("atualizar", true))
    var autoUpdate: Boolean
        get() = _update.value
        set(v) { _update.value = v; sp.edit().putBoolean("atualizar", v).apply() }

    private val _hl = mutableStateOf(sp.getLong("cor_destaque", 0xFFFFD400))
    var highlightColor: Long
        get() = _hl.value
        set(v) { _hl.value = v; sp.edit().putLong("cor_destaque", v).apply() }

    private val _screen = mutableStateOf(sp.getBoolean("tela_ligada", false))
    var keepScreenOn: Boolean
        get() = _screen.value
        set(v) { _screen.value = v; sp.edit().putBoolean("tela_ligada", v).apply() }

    var tsaDefault: Boolean
        get() = sp.getBoolean("sign_tsa", true)
        set(v) { sp.edit().putBoolean("sign_tsa", v).apply() }
}
