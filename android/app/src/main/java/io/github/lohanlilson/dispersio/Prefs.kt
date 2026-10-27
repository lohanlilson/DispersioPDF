package io.github.lohanlilson.dispersio

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

    private val _autosave = mutableStateOf(sp.getBoolean("salvar_auto", true))
    /** salva sozinho alguns segundos depois de editar, ao sair do app e ao fechar o documento */
    var autosave: Boolean
        get() = _autosave.value
        set(v) { _autosave.value = v; sp.edit().putBoolean("salvar_auto", v).apply() }

    private val _pay = mutableStateOf(sp.getBoolean("boletos", true))
    /** mostra boletos, Pix e notas fiscais encontrados no documento */
    var detectPayments: Boolean
        get() = _pay.value
        set(v) { _pay.value = v; sp.edit().putBoolean("boletos", v).apply() }

    private val _orient = mutableStateOf(sp.getBoolean("posicao_paginas", true))
    /** avisa quando há páginas de lado ou de cabeça para baixo */
    var detectOrientation: Boolean
        get() = _orient.value
        set(v) { _orient.value = v; sp.edit().putBoolean("posicao_paginas", v).apply() }

    private val _offerTr = mutableStateOf(sp.getBoolean("oferecer_traducao", true))
    var offerTranslation: Boolean
        get() = _offerTr.value
        set(v) { _offerTr.value = v; sp.edit().putBoolean("oferecer_traducao", v).apply() }

    private val _trTo = mutableStateOf(sp.getString("traduzir_para", "") ?: "")
    /** idioma da tradução; vazio = idioma do celular */
    var translateTo: String
        get() = _trTo.value
        set(v) { _trTo.value = v; sp.edit().putString("traduzir_para", v).apply() }

    var articlesEnglish: Boolean
        get() = sp.getBoolean("artigos_ingles", true)
        set(v) { sp.edit().putBoolean("artigos_ingles", v).apply() }

    var tsaDefault: Boolean
        get() = sp.getBoolean("sign_tsa", true)
        set(v) { sp.edit().putBoolean("sign_tsa", v).apply() }
}
