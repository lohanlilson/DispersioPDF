import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val ver = Properties().apply { rootProject.file("version.properties").inputStream().use { load(it) } }

android {
    namespace = "io.github.lohanlilson.lumenpdf"
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.lohanlilson.lumenpdf"
        minSdk = 26
        targetSdk = 36
        versionCode = ver.getProperty("versionCode").toInt()
        versionName = ver.getProperty("versionName")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // celulares (ARM) e emulador do teste automático (x86_64)
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64") }
    }

    // Assinatura do APK: chave guardada nos segredos do GitHub (as atualizações precisam da mesma chave)
    val ks = System.getenv("LUMEN_KEYSTORE")
    signingConfigs {
        if (ks != null && file(ks).exists()) {
            create("release") {
                storeFile = file(ks)
                storePassword = System.getenv("LUMEN_KEYSTORE_PASS")
                keyAlias = System.getenv("LUMEN_KEY_ALIAS") ?: "lumen"
                keyPassword = System.getenv("LUMEN_KEY_PASS") ?: System.getenv("LUMEN_KEYSTORE_PASS")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.findByName("release") ?: signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlin {
        compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging {
        resources.excludes += setOf("META-INF/*.kotlin_module", "META-INF/versions/**", "META-INF/LICENSE*", "META-INF/NOTICE*")
    }
}

dependencies {
    val bom = platform("androidx.compose:compose-bom:2025.12.01")
    implementation(bom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.11.0")
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.4")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.4")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    // exibição: PDFium (mesmo motor do Chrome)
    implementation("io.legere:pdfiumandroid:1.0.35")
    // edição, formulários e assinatura: PDFBox (com BouncyCastle)
    implementation("com.tom-roush:pdfbox-android:2.0.27.0")
    // escanear documentos com a câmera (scanner do Google: bordas, perspectiva e filtros)
    implementation("com.google.android.gms:play-services-mlkit-document-scanner:16.0.0")

    debugImplementation("androidx.compose.ui:ui-tooling")
    androidTestImplementation(bom)
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
    androidTestImplementation("androidx.test:runner:1.7.0")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
    testImplementation("junit:junit:4.13.2")
}
