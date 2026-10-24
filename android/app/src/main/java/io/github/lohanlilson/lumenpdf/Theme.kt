package io.github.lohanlilson.lumenpdf

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Violet = Color(0xFF6D3CF0)
val VioletDark = Color(0xFF3C1896)
val Gold = Color(0xFFF2A93B)

private val Light = lightColorScheme(
    primary = Violet, onPrimary = Color.White,
    primaryContainer = Color(0xFFE9E1FF), onPrimaryContainer = Color(0xFF22005D),
    secondary = Gold, onSecondary = Color(0xFF2B1700),
    secondaryContainer = Color(0xFFFFE3BC), onSecondaryContainer = Color(0xFF2B1700),
    background = Color(0xFFF6F4FB), onBackground = Color(0xFF1C1B22),
    surface = Color(0xFFFFFFFF), onSurface = Color(0xFF1C1B22),
    surfaceVariant = Color(0xFFEDE9F5), onSurfaceVariant = Color(0xFF494554),
    outline = Color(0xFF7A7586),
)

private val Dark = darkColorScheme(
    primary = Color(0xFFBBA3FF), onPrimary = Color(0xFF2E0A82),
    primaryContainer = Color(0xFF4A23B8), onPrimaryContainer = Color(0xFFE9E1FF),
    secondary = Color(0xFFFFC874), onSecondary = Color(0xFF462A00),
    background = Color(0xFF15131C), onBackground = Color(0xFFE6E1EA),
    surface = Color(0xFF1D1A25), onSurface = Color(0xFFE6E1EA),
    surfaceVariant = Color(0xFF2A2633), onSurfaceVariant = Color(0xFFCAC4D3),
    outline = Color(0xFF948E9E),
)

@Composable
fun LumenTheme(theme: String = "sistema", content: @Composable () -> Unit) {
    val dark = when (theme) { "claro" -> false; "escuro" -> true; else -> isSystemInDarkTheme() }
    MaterialTheme(colorScheme = if (dark) Dark else Light, content = content)
}
