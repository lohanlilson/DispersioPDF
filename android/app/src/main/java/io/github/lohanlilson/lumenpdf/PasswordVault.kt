package io.github.lohanlilson.lumenpdf

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyPermanentlyInvalidatedException
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_STRONG
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.spec.X509EncodedKeySpec
import javax.crypto.Cipher
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine

/**
 * Guarda a senha do certificado (.pfx) protegida pela digital/rosto.
 * Par de chaves RSA no Android Keystore: guardar usa só a chave pública (sem pedir a digital);
 * para ler é preciso a chave privada, liberada pelo sistema só depois da biometria.
 * Se uma digital nova for cadastrada no aparelho, o Android invalida a chave e a senha é pedida de novo.
 */
object PasswordVault {
    private const val ALIAS = "lumen-senha-certificado"
    private const val TRANSFORM = "RSA/ECB/PKCS1Padding"
    /** nos testes do emulador (sem digital cadastrada) a chave é criada sem exigir biometria */
    var requireAuth = true

    private fun sp(ctx: Context) = ctx.getSharedPreferences("cofre", Context.MODE_PRIVATE)
    private fun ks() = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    fun available(ctx: Context): Boolean = !requireAuth ||
        BiometricManager.from(ctx).canAuthenticate(BIOMETRIC_STRONG) == BiometricManager.BIOMETRIC_SUCCESS

    fun has(ctx: Context, pfxName: String) = sp(ctx).contains(pfxName) && ks().containsAlias(ALIAS)

    fun forget(ctx: Context, pfxName: String) = sp(ctx).edit().remove(pfxName).apply()

    fun forgetAll(ctx: Context) {
        sp(ctx).edit().clear().apply()
        runCatching { ks().deleteEntry(ALIAS) }
    }

    private fun key(): java.security.KeyStore.PrivateKeyEntry {
        val ks = ks()
        (ks.getEntry(ALIAS, null) as? KeyStore.PrivateKeyEntry)?.let { return it }
        val gen = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_RSA, "AndroidKeyStore")
        val spec = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setKeySize(2048)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_RSA_PKCS1)
            .setDigests(KeyProperties.DIGEST_SHA256)
            .apply {
                if (requireAuth) {
                    setUserAuthenticationRequired(true)
                    if (android.os.Build.VERSION.SDK_INT >= 30) setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG)
                    else @Suppress("DEPRECATION") setUserAuthenticationValidityDurationSeconds(-1)
                    setInvalidatedByBiometricEnrollment(true)
                }
            }
            .build()
        gen.initialize(spec)
        gen.generateKeyPair()
        return ks.getEntry(ALIAS, null) as KeyStore.PrivateKeyEntry
    }

    /** Guarda a senha (não pede a digital). */
    fun store(ctx: Context, pfxName: String, password: String) {
        // chave pública "comum" (a do Keystore exigiria autenticação em alguns aparelhos)
        val pub = KeyFactory.getInstance("RSA").generatePublic(X509EncodedKeySpec(key().certificate.publicKey.encoded))
        val c = Cipher.getInstance(TRANSFORM).apply { init(Cipher.ENCRYPT_MODE, pub) }
        val enc = c.doFinal(password.toByteArray(Charsets.UTF_8))
        sp(ctx).edit().putString(pfxName, Base64.encodeToString(enc, Base64.NO_WRAP)).apply()
    }

    sealed class Result {
        data class Ok(val password: String) : Result()
        data object Cancelled : Result()
        data class Failed(val message: String) : Result()
    }

    private fun decrypt(cipher: Cipher, ctx: Context, pfxName: String): String {
        val enc = Base64.decode(sp(ctx).getString(pfxName, "") ?: "", Base64.NO_WRAP)
        return String(cipher.doFinal(enc), Charsets.UTF_8)
    }

    /** Pede a digital e devolve a senha guardada. */
    suspend fun unlock(act: FragmentActivity, pfxName: String): Result {
        val cipher = try {
            Cipher.getInstance(TRANSFORM).apply { init(Cipher.DECRYPT_MODE, key().privateKey as PrivateKey) }
        } catch (e: KeyPermanentlyInvalidatedException) {
            forgetAll(act)
            return Result.Failed("Uma digital nova foi cadastrada no aparelho. Digite a senha do certificado de novo.")
        } catch (e: Exception) {
            return Result.Failed(e.message ?: e.javaClass.simpleName)
        }
        if (!requireAuth) return runCatching { Result.Ok(decrypt(cipher, act, pfxName)) }.getOrElse { Result.Failed(it.message ?: "") }
        return suspendCoroutine { cont ->
            val prompt = BiometricPrompt(act, ContextCompat.getMainExecutor(act), object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(r: BiometricPrompt.AuthenticationResult) {
                    val c = r.cryptoObject?.cipher
                    cont.resume(if (c == null) Result.Failed("Sem acesso à chave") else
                        runCatching { Result.Ok(decrypt(c, act, pfxName)) }.getOrElse { Result.Failed(it.message ?: "") })
                }

                override fun onAuthenticationError(code: Int, msg: CharSequence) {
                    cont.resume(if (code == BiometricPrompt.ERROR_USER_CANCELED || code == BiometricPrompt.ERROR_NEGATIVE_BUTTON ||
                        code == BiometricPrompt.ERROR_CANCELED) Result.Cancelled else Result.Failed(msg.toString()))
                }
            })
            val info = BiometricPrompt.PromptInfo.Builder()
                .setTitle("Assinar com certificado")
                .setSubtitle(pfxName)
                .setNegativeButtonText("Digitar a senha")
                .setAllowedAuthenticators(BIOMETRIC_STRONG)
                .build()
            prompt.authenticate(info, BiometricPrompt.CryptoObject(cipher))
        }
    }
}
