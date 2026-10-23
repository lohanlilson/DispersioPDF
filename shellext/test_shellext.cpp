// Testa a LumenShell.dll como o Explorador faz: carrega a DLL, cria a miniatura e o painel de visualização
// numa thread STA e salva as imagens (BMP) para conferência. Uso: test_shellext <dll> <pdf> <pasta_saida>
#define NOMINMAX
#include <windows.h>
#include <shlwapi.h>
#include <thumbcache.h>
#include <propsys.h>
#include <shobjidl.h>
#include <cstdio>
#include <string>
#pragma comment(lib, "shlwapi.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "user32.lib")

static const CLSID CLSID_LumenThumb = {0x6e1f4d3a, 0x8c2b, 0x4a57, {0x9b, 0x1e, 0x3d, 0x5c, 0x7a, 0x9f, 0x0b, 0x21}};
static const CLSID CLSID_LumenPreview = {0x7f2a5e4b, 0x9d3c, 0x4b68, {0xac, 0x2f, 0x4e, 0x6d, 0x8b, 0x0a, 0x1c, 0x32}};
typedef HRESULT(STDAPICALLTYPE* GetClassObjectFn)(REFCLSID, REFIID, void**);

static int SaveBmp(HBITMAP hb, const std::wstring& path, int* inked) {
    BITMAP bm;
    GetObject(hb, sizeof(bm), &bm);
    BITMAPINFOHEADER bih = {sizeof(bih), bm.bmWidth, -bm.bmHeight, 1, 32, BI_RGB};
    std::string px((size_t)bm.bmWidth * bm.bmHeight * 4, '\0');
    HDC dc = GetDC(nullptr);
    GetDIBits(dc, hb, 0, bm.bmHeight, &px[0], (BITMAPINFO*)&bih, DIB_RGB_COLORS);
    ReleaseDC(nullptr, dc);
    int ink = 0;
    for (size_t i = 0; i < px.size(); i += 4) {
        unsigned char b = px[i], g = px[i + 1], r = px[i + 2];
        if (r < 200 || g < 200 || b < 200) ++ink;
    }
    *inked = ink;
    BITMAPFILEHEADER bfh = {0x4D42};
    bfh.bfOffBits = sizeof(bfh) + sizeof(bih);
    bfh.bfSize = bfh.bfOffBits + (DWORD)px.size();
    FILE* f = _wfopen(path.c_str(), L"wb");
    if (!f) return 0;
    fwrite(&bfh, sizeof(bfh), 1, f);
    fwrite(&bih, sizeof(bih), 1, f);
    fwrite(px.data(), 1, px.size(), f);
    fclose(f);
    return bm.bmWidth * 10000 + bm.bmHeight;
}

int wmain(int argc, wchar_t** argv) {
    if (argc < 4) { wprintf(L"uso: test_shellext <dll> <pdf> <saida>\n"); return 2; }
    CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);  // o Explorador chama as extensões em STA
    HMODULE dll = LoadLibraryW(argv[1]);
    if (!dll) { wprintf(L"falha ao carregar a DLL (%lu)\n", GetLastError()); return 3; }
    auto getco = (GetClassObjectFn)GetProcAddress(dll, "DllGetClassObject");
    if (!getco) { wprintf(L"DllGetClassObject não exportado\n"); return 4; }
    std::wstring out = argv[3];
    int fails = 0;

    // ---- miniatura
    {
        IClassFactory* cf = nullptr;
        HRESULT hr = getco(CLSID_LumenThumb, IID_PPV_ARGS(&cf));
        IInitializeWithStream* init = nullptr;
        if (SUCCEEDED(hr)) hr = cf->CreateInstance(nullptr, IID_PPV_ARGS(&init));
        IStream* st = nullptr;
        if (SUCCEEDED(hr)) hr = SHCreateStreamOnFileEx(argv[2], STGM_READ | STGM_SHARE_DENY_NONE, 0, FALSE, nullptr, &st);
        if (SUCCEEDED(hr)) hr = init->Initialize(st, STGM_READ);
        IThumbnailProvider* tp = nullptr;
        if (SUCCEEDED(hr)) hr = init->QueryInterface(IID_PPV_ARGS(&tp));
        HBITMAP hb = nullptr;
        WTS_ALPHATYPE at;
        DWORD t0 = GetTickCount();
        if (SUCCEEDED(hr)) hr = tp->GetThumbnail(256, &hb, &at);
        DWORD ms = GetTickCount() - t0;
        int ink = 0, dim = 0;
        if (SUCCEEDED(hr) && hb) dim = SaveBmp(hb, out + L"\\miniatura.bmp", &ink);
        wprintf(L"miniatura: hr=0x%08lx tamanho=%dx%d pixels_com_conteudo=%d tempo=%lums\n", hr, dim / 10000, dim % 10000, ink, ms);
        if (FAILED(hr) || !hb || dim / 10000 > 256 || dim % 10000 > 256 || ink < 50) ++fails;
        if (hb) DeleteObject(hb);
        if (tp) tp->Release();
        if (st) st->Release();
        if (init) init->Release();
        if (cf) cf->Release();
    }

    // ---- painel de visualização
    {
        WNDCLASSW wc = {};
        wc.lpfnWndProc = DefWindowProcW;
        wc.hInstance = GetModuleHandleW(nullptr);
        wc.lpszClassName = L"HostTeste";
        RegisterClassW(&wc);
        HWND host = CreateWindowW(L"HostTeste", L"host", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 0, 0, 520, 760, nullptr, nullptr,
                                  wc.hInstance, nullptr);
        RECT rc;
        GetClientRect(host, &rc);
        IClassFactory* cf = nullptr;
        HRESULT hr = getco(CLSID_LumenPreview, IID_PPV_ARGS(&cf));
        IInitializeWithStream* init = nullptr;
        if (SUCCEEDED(hr)) hr = cf->CreateInstance(nullptr, IID_PPV_ARGS(&init));
        IStream* st = nullptr;
        if (SUCCEEDED(hr)) hr = SHCreateStreamOnFileEx(argv[2], STGM_READ | STGM_SHARE_DENY_NONE, 0, FALSE, nullptr, &st);
        if (SUCCEEDED(hr)) hr = init->Initialize(st, STGM_READ);
        IPreviewHandler* ph = nullptr;
        if (SUCCEEDED(hr)) hr = init->QueryInterface(IID_PPV_ARGS(&ph));
        if (SUCCEEDED(hr)) hr = ph->SetWindow(host, &rc);
        if (SUCCEEDED(hr)) hr = ph->DoPreview();
        DWORD end = GetTickCount() + 6000;
        while (GetTickCount() < end) {
            MSG m;
            while (PeekMessageW(&m, nullptr, 0, 0, PM_REMOVE)) { TranslateMessage(&m); DispatchMessageW(&m); }
            Sleep(20);
        }
        HWND child = nullptr;
        IOleWindow* ow = nullptr;
        if (SUCCEEDED(hr) && SUCCEEDED(ph->QueryInterface(IID_PPV_ARGS(&ow)))) { ow->GetWindow(&child); ow->Release(); }
        int ink = 0, dim = 0;
        if (child) {
            RECT cr;
            GetClientRect(child, &cr);
            HDC sdc = GetDC(nullptr);
            HDC mdc = CreateCompatibleDC(sdc);
            HBITMAP hb = CreateCompatibleBitmap(sdc, cr.right, cr.bottom);
            HGDIOBJ old = SelectObject(mdc, hb);
            SendMessageW(child, WM_PRINTCLIENT, (WPARAM)mdc, PRF_CLIENT);
            SelectObject(mdc, old);
            dim = SaveBmp(hb, out + L"\\visualizacao.bmp", &ink);
            DeleteObject(hb);
            DeleteDC(mdc);
            ReleaseDC(nullptr, sdc);
        }
        wprintf(L"visualizacao: hr=0x%08lx janela=%p tamanho=%dx%d pixels_com_conteudo=%d\n", hr, child, dim / 10000, dim % 10000, ink);
        if (FAILED(hr) || !child || ink < 200) ++fails;
        if (ph) { ph->Unload(); ph->Release(); }
        if (st) st->Release();
        if (init) init->Release();
        if (cf) cf->Release();
        DestroyWindow(host);
    }
    // a DLL deve poder ser descarregada depois que tudo foi liberado
    typedef HRESULT(STDAPICALLTYPE * CanUnloadFn)();
    Sleep(500);
    auto canunload = (CanUnloadFn)GetProcAddress(dll, "DllCanUnloadNow");
    wprintf(L"DllCanUnloadNow=%s\n", canunload && canunload() == S_OK ? L"S_OK" : L"S_FALSE");
    wprintf(fails ? L"FALHOU\n" : L"OK\n");
    return fails ? 1 : 0;
}
