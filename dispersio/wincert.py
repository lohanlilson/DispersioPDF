"""Certificados instalados no Windows (repositório 'Pessoal' do usuário) — A1 importado ou A3 em token/cartão.

A chave privada nunca sai do Windows: o hash é assinado via CNG (NCryptSignHash). Se o certificado estiver em
token, o próprio driver (SafeNet, Watchdata, etc.) pede o PIN.
"""
import ctypes
import hashlib
import sys
from ctypes import wintypes
from datetime import datetime, timezone

from asn1crypto import x509 as asn1_x509

IS_WINDOWS = sys.platform == "win32"

CERT_STORE_PROV_SYSTEM_W = 10
CERT_SYSTEM_STORE_CURRENT_USER = 0x00010000
CERT_STORE_READONLY_FLAG = 0x00008000
CERT_KEY_PROV_INFO_PROP_ID = 2
CRYPT_ACQUIRE_ONLY_NCRYPT_KEY_FLAG = 0x00040000
CRYPT_ACQUIRE_COMPARE_KEY_FLAG = 0x00000004
BCRYPT_PAD_PKCS1 = 0x00000002


class CERT_CONTEXT(ctypes.Structure):
    _fields_ = [("dwCertEncodingType", wintypes.DWORD), ("pbCertEncoded", ctypes.POINTER(ctypes.c_ubyte)),
                ("cbCertEncoded", wintypes.DWORD), ("pCertInfo", ctypes.c_void_p), ("hCertStore", ctypes.c_void_p)]


PCCERT_CONTEXT = ctypes.POINTER(CERT_CONTEXT)


class BCRYPT_PKCS1_PADDING_INFO(ctypes.Structure):
    _fields_ = [("pszAlgId", wintypes.LPCWSTR)]


_HASH_ALG = {"sha1": "SHA1", "sha256": "SHA256", "sha384": "SHA384", "sha512": "SHA512"}


def _libs():
    crypt32 = ctypes.WinDLL("crypt32.dll")
    ncrypt = ctypes.WinDLL("ncrypt.dll")
    crypt32.CertOpenStore.restype = ctypes.c_void_p
    crypt32.CertOpenStore.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.LPCWSTR]
    crypt32.CertEnumCertificatesInStore.restype = PCCERT_CONTEXT
    crypt32.CertEnumCertificatesInStore.argtypes = [ctypes.c_void_p, PCCERT_CONTEXT]
    crypt32.CertDuplicateCertificateContext.restype = PCCERT_CONTEXT
    crypt32.CertDuplicateCertificateContext.argtypes = [PCCERT_CONTEXT]
    crypt32.CertGetCertificateContextProperty.argtypes = [PCCERT_CONTEXT, wintypes.DWORD, ctypes.c_void_p,
                                                          ctypes.POINTER(wintypes.DWORD)]
    crypt32.CryptAcquireCertificatePrivateKey.argtypes = [PCCERT_CONTEXT, wintypes.DWORD, ctypes.c_void_p,
                                                          ctypes.POINTER(ctypes.c_void_p),
                                                          ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.BOOL)]
    ncrypt.NCryptSignHash.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    ncrypt.NCryptSignHash.restype = ctypes.c_long
    ncrypt.NCryptFreeObject.argtypes = [ctypes.c_void_p]
    return crypt32, ncrypt


def _open_store(crypt32, name):
    return crypt32.CertOpenStore(CERT_STORE_PROV_SYSTEM_W, 0, None,
                                 CERT_SYSTEM_STORE_CURRENT_USER | CERT_STORE_READONLY_FLAG, name)


def _store_certs(crypt32, name, with_key_only=False):
    store = _open_store(crypt32, name)
    if not store:
        return []
    out = []
    ctx = crypt32.CertEnumCertificatesInStore(store, None)
    while ctx:
        der = bytes(ctx.contents.pbCertEncoded[:ctx.contents.cbCertEncoded])
        has_key = False
        if with_key_only:
            size = wintypes.DWORD(0)
            has_key = bool(crypt32.CertGetCertificateContextProperty(ctx, CERT_KEY_PROV_INFO_PROP_ID, None,
                                                                     ctypes.byref(size)))
        if not with_key_only or has_key:
            out.append((der, crypt32.CertDuplicateCertificateContext(ctx) if with_key_only else None))
        ctx = crypt32.CertEnumCertificatesInStore(store, ctx)
    return out


class WinCert:
    def __init__(self, der, ctx):
        self.der = der
        self.ctx = ctx
        self.cert = asn1_x509.Certificate.load(der)

    @property
    def name(self):
        return self.cert.subject.native.get("common_name", self.cert.subject.human_friendly)

    @property
    def issuer(self):
        return self.cert.issuer.native.get("common_name", self.cert.issuer.human_friendly)

    @property
    def not_after(self):
        return self.cert["tbs_certificate"]["validity"]["not_after"].native

    @property
    def expired(self):
        return self.not_after < datetime.now(timezone.utc)

    @property
    def can_sign(self):
        try:
            ku = self.cert.key_usage_value
            return ku is None or "digital_signature" in ku.native or "non_repudiation" in ku.native
        except Exception:
            return True

    def label(self):
        status = "VENCIDO" if self.expired else f"válido até {self.not_after:%d/%m/%Y}"
        return f"{self.name}  —  {self.issuer}  ({status})"


def list_certificates(include_expired=False):
    """Certificados do repositório Pessoal que possuem chave privada associada (A1 instalado ou A3 conectado)."""
    if not IS_WINDOWS:
        return []
    crypt32, _ = _libs()
    certs = [WinCert(der, ctx) for der, ctx in _store_certs(crypt32, "MY", with_key_only=True)]
    certs = [c for c in certs if c.can_sign and (include_expired or not c.expired)]
    certs.sort(key=lambda c: (c.expired, c.name))
    return certs


def _chain(cert):
    """Monta a cadeia (intermediárias e raiz) a partir dos repositórios do Windows, para embutir na assinatura."""
    crypt32, _ = _libs()
    pool = []
    for store in ("CA", "Root"):
        for der, _ in _store_certs(crypt32, store):
            try:
                pool.append(asn1_x509.Certificate.load(der))
            except Exception:
                pass
    chain, cur = [], cert
    for _ in range(6):
        if cur.self_signed != "no":
            break
        parent = next((c for c in pool if c.subject == cur.issuer), None)
        if parent is None or parent in chain:
            break
        chain.append(parent)
        cur = parent
    return chain


def sign_hash(ctx, digest, alg="sha256"):
    crypt32, ncrypt = _libs()
    key = ctypes.c_void_p()
    spec = wintypes.DWORD()
    free = wintypes.BOOL()
    if not crypt32.CryptAcquireCertificatePrivateKey(ctx, CRYPT_ACQUIRE_ONLY_NCRYPT_KEY_FLAG, None,
                                                     ctypes.byref(key), ctypes.byref(spec), ctypes.byref(free)):
        raise RuntimeError(f"Não foi possível acessar a chave privada (erro {ctypes.GetLastError()}). "
                           "Verifique se o token está conectado e o driver instalado.")
    try:
        pad = BCRYPT_PKCS1_PADDING_INFO(_HASH_ALG[alg])
        hbuf = ctypes.create_string_buffer(digest, len(digest))
        size = wintypes.DWORD(0)
        st = ncrypt.NCryptSignHash(key, ctypes.byref(pad), hbuf, len(digest), None, 0, ctypes.byref(size), BCRYPT_PAD_PKCS1)
        if st != 0:
            raise RuntimeError(f"Falha ao assinar (código 0x{st & 0xffffffff:08X}). PIN incorreto ou operação cancelada?")
        out = ctypes.create_string_buffer(size.value)
        st = ncrypt.NCryptSignHash(key, ctypes.byref(pad), hbuf, len(digest), out, size, ctypes.byref(size), BCRYPT_PAD_PKCS1)
        if st != 0:
            raise RuntimeError(f"Falha ao assinar (código 0x{st & 0xffffffff:08X}). PIN incorreto ou operação cancelada?")
        return out.raw[:size.value]
    finally:
        if free.value:
            ncrypt.NCryptFreeObject(key)


def make_signer(wincert, raw_sign=None):
    """Cria um signer do pyHanko que usa a chave do Windows. raw_sign(digest, alg) permite testes fora do Windows."""
    from asn1crypto import algos
    from pyhanko.sign.signers import Signer
    from pyhanko_certvalidator.registry import SimpleCertificateStore

    cert = wincert.cert
    try:
        chain = _chain(cert) if IS_WINDOWS else []
    except Exception:
        chain = []
    sign_fn = raw_sign or (lambda digest, alg: sign_hash(wincert.ctx, digest, alg))
    key_bytes = cert.public_key.bit_size // 8

    class WindowsStoreSigner(Signer):
        async def async_sign_raw(self, data, digest_algorithm, dry_run=False):
            if dry_run:
                return bytes(key_bytes)
            digest = hashlib.new(digest_algorithm, data).digest()
            return sign_fn(digest, digest_algorithm)

    return WindowsStoreSigner(
        signing_cert=cert,
        cert_registry=SimpleCertificateStore.from_certs([cert] + chain),
        signature_mechanism=algos.SignedDigestAlgorithm({"algorithm": "sha256_rsa"}),
    )
