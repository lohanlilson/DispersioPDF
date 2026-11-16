package io.github.lohanlilson.dispersio

import org.junit.Assert.assertEquals
import org.junit.Test
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate

/** e-CNPJ: o certificado é da empresa, mas o responsável (nome e CPF) vem gravado nele e precisa aparecer. */
class AssinaturaTest {
    private val ecnpj = "MIIDoDCCAoigAwIBAgIBATANBgkqhkiG9w0BAQsFADBBMSowKAYDVQQDDCFFTVBSRVNBIFRFU1RFIExUREE6MTIzNDU2NzgwMDAxOTUxEzARBgNVBAoMCklDUC1CcmFzaWwwHhcNMjUwMTAxMDAwMDAwWhcNMzAwMTAxMDAwMDAwWjBBMSowKAYDVQQDDCFFTVBSRVNBIFRFU1RFIExUREE6MTIzNDU2NzgwMDAxOTUxEzARBgNVBAoMCklDUC1CcmFzaWwwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDHkXvpe9D0DBE5Vgy9vLq/8Is6NLCqpDh65aYtcjmz00IFs6//6OgdRdQHLzKcm6CuFRschjLbxkknZaT8gGq2ey69tw/GSZdQsF69oOv+4g/8b8B8iz7JYXkwCRh5qF/O2APrdDof+MT9Gw5tdEcYIrXPGotzVNXdmQXIMCFjki7y5KH3WqpdvZrSjvXUU0rXHaNr1cwWR2qz0xMMcFYbh2+8uVDeSLx/CkIp/D4cm0T6QFUGIs1IOCsIVEHzfysywDgr/2memnzXcl+hQBm2kTjU0Q5PtDBwpaip9fYnQzf3Lrz9zJ4o1oK8kCSPjDc4pqBYNYJI/CLYqB+ih7MZAgMBAAGjgaIwgZ8wgZwGA1UdEQSBlDCBkaBCBgVgTAEDBKA5BDcwMTAyMTk4MDEyMzQ1Njc4OTA5MDAwMDAwMDAwMDAxMjM0NTY3ODkgICAgICBTU1BHTyAgICAgoBgGBWBMAQMCoA8TDUpPQU8gREEgU0lMVkGgGQYFYEwBAwOgEAQOMTIzNDU2NzgwMDAxOTWBFmNvbnRhdG9AZW1wcmVzYS5jb20uYnIwDQYJKoZIhvcNAQELBQADggEBAGEFgzVd6eJGdkMZRuRuqe31PNWIda2lWGEL358gqGfMLYBwVUNLrluUNGNgspxyeuqVYVRavsu3GizJWC7SiAVki0m8Om0Gssr3mwJpxVN1sg4+h+64eoRoiiJ3FKiJoK5cO5sml2HMpNHoJiVI2rqLvM/7lNjxlER1XjYRZpjyCya0bVtahm8GZFcRAoX3NV589ATQgWp/WDHnRO9met4imMXNs4lPy3ClMn1dwA3P8ubKVVGwB6LWrznX63PhdAGRedEASqXAHAg6fdTKA9q1NZCn5Puvtzx9YkNdTU+Mv0RSVlfkHZMn6UpKxFAPIz6Inwk9826iFRyZgAR4W4w="

    @Test fun responsavelDoECnpj() {
        val der = java.util.Base64.getDecoder().decode(ecnpj)
        val c = CertificateFactory.getInstance("X.509").generateCertificate(der.inputStream()) as X509Certificate
        val icp = Certs.icpBrasil(c)
        assertEquals("e-CNPJ", icp.type)
        assertEquals("12.345.678/0001-95", icp.cnpj)
        assertEquals("JOAO DA SILVA", icp.responsible)
        assertEquals("123.456.789-09", icp.responsibleCpf)
        assertEquals("01/02/1980", icp.responsibleBirth)
        assertEquals("EMPRESA TESTE LTDA" to "12345678000195", Certs.splitName(Certs.cn(c)))
    }
}
