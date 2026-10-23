// LumenShell.dll — extensões do Explorador do Windows para o Lumen PDF:
//   * IThumbnailProvider: miniatura do arquivo .pdf com a primeira página;
//   * IPreviewHandler:    painel de visualização (Alt+P) com as páginas do documento.
// A renderização usa o mecanismo de PDF do próprio Windows (Windows.Data.Pdf, Windows 10+), sem dependências.
// O trabalho WinRT roda numa thread MTA própria: o Explorador chama as extensões em threads STA.

#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shlwapi.h>
#include <shlobj.h>
#include <thumbcache.h>
#include <propsys.h>
#include <shobjidl.h>
#include <ocidl.h>

#include <algorithm>
#include <atomic>
#include <memory>
#include <mutex>
#include <new>
#include <string>
#include <thread>
#include <vector>

#include <winrt/base.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Storage.Streams.h>
#include <winrt/Windows.Data.Pdf.h>
#include <winrt/Windows.Graphics.Imaging.h>
#include <winrt/Windows.UI.h>

using std::max;
using std::min;

#pragma comment(lib, "windowsapp.lib")
#pragma comment(lib, "shlwapi.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "uuid.lib")

// {6E1F4D3A-8C2B-4A57-9B1E-3D5C7A9F0B21}
static const CLSID CLSID_LumenThumb = {0x6e1f4d3a, 0x8c2b, 0x4a57, {0x9b, 0x1e, 0x3d, 0x5c, 0x7a, 0x9f, 0x0b, 0x21}};
// {7F2A5E4B-9D3C-4B68-AC2F-4E6D8B0A1C32}
static const CLSID CLSID_LumenPreview = {0x7f2a5e4b, 0x9d3c, 0x4b68, {0xac, 0x2f, 0x4e, 0x6d, 0x8b, 0x0a, 0x1c, 0x32}};

static HINSTANCE g_hInst = nullptr;
static std::atomic<long> g_refs{0};

namespace wdp = winrt::Windows::Data::Pdf;
namespace wss = winrt::Windows::Storage::Streams;
namespace wgi = winrt::Windows::Graphics::Imaging;

// ------------------------------------------------------------------ renderização (WinRT)
struct Rendered {
    UINT w = 0, h = 0;
    std::vector<uint8_t> bgra;
};

static bool ReadAll(IStream* s, std::vector<uint8_t>& out) {
    out.clear();
    std::vector<uint8_t> buf(1 << 16);
    for (;;) {
        ULONG got = 0;
        HRESULT hr = s->Read(buf.data(), (ULONG)buf.size(), &got);
        if (got) out.insert(out.end(), buf.begin(), buf.begin() + got);
        if (FAILED(hr)) return false;
        if (hr == S_FALSE || got == 0) break;
        if (out.size() > (size_t)1024 * 1024 * 1024) return false;
    }
    return !out.empty();
}

static wdp::PdfDocument LoadPdf(const std::vector<uint8_t>& data) {
    wss::InMemoryRandomAccessStream ms;
    wss::DataWriter dw(ms);
    dw.WriteBytes(winrt::array_view<const uint8_t>(data.data(), data.data() + data.size()));
    dw.StoreAsync().get();
    dw.FlushAsync().get();
    dw.DetachStream();
    ms.Seek(0);
    return wdp::PdfDocument::LoadFromStreamAsync(ms).get();
}

// box: tamanho máximo do lado maior (miniatura) ou largura fixa (fitWidth = true)
static Rendered RenderPage(const wdp::PdfDocument& doc, UINT index, UINT box, bool fitWidth) {
    Rendered r;
    wdp::PdfPage page = doc.GetPage(index);
    auto sz = page.Size();
    wdp::PdfPageRenderOptions opt;
    if (fitWidth || sz.Width >= sz.Height) opt.DestinationWidth(box);
    else opt.DestinationHeight(box);
    opt.BackgroundColor(winrt::Windows::UI::Color{255, 255, 255, 255});
    wss::InMemoryRandomAccessStream out;
    page.RenderToStreamAsync(out, opt).get();
    out.Seek(0);
    auto dec = wgi::BitmapDecoder::CreateAsync(out).get();
    auto px = dec.GetPixelDataAsync(wgi::BitmapPixelFormat::Bgra8, wgi::BitmapAlphaMode::Ignore, wgi::BitmapTransform(),
                                    wgi::ExifOrientationMode::IgnoreExifOrientation,
                                    wgi::ColorManagementMode::DoNotColorManage).get();
    auto arr = px.DetachPixelData();
    r.w = dec.PixelWidth();
    r.h = dec.PixelHeight();
    r.bgra.assign(arr.begin(), arr.end());
    return r;
}

template <class F>
static void RunInMta(F&& f) {
    std::thread t([&] {
        winrt::init_apartment(winrt::apartment_type::multi_threaded);
        f();
        winrt::uninit_apartment();
    });
    t.join();
}

static HBITMAP MakeDib(const Rendered& r) {
    if (!r.w || !r.h || r.bgra.size() < (size_t)r.w * r.h * 4) return nullptr;
    BITMAPINFO bi = {};
    bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth = (LONG)r.w;
    bi.bmiHeader.biHeight = -(LONG)r.h;  // de cima para baixo
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    bi.bmiHeader.biCompression = BI_RGB;
    void* bits = nullptr;
    HBITMAP hb = CreateDIBSection(nullptr, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
    if (!hb || !bits) return nullptr;
    auto* p = static_cast<uint8_t*>(bits);
    memcpy(p, r.bgra.data(), (size_t)r.w * r.h * 4);
    for (size_t i = 0; i < (size_t)r.w * r.h; ++i) p[i * 4 + 3] = 255;
    return hb;
}

// ------------------------------------------------------------------ miniatura
class ThumbProvider : public IInitializeWithStream, public IThumbnailProvider {
    std::atomic<long> m_ref{1};
    std::vector<uint8_t> m_data;

public:
    ThumbProvider() { ++g_refs; }
    virtual ~ThumbProvider() { --g_refs; }

    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        static const QITAB qit[] = {QITABENT(ThumbProvider, IInitializeWithStream),
                                    QITABENT(ThumbProvider, IThumbnailProvider), {0}};
        return QISearch(this, qit, riid, ppv);
    }
    IFACEMETHODIMP_(ULONG) AddRef() override { return ++m_ref; }
    IFACEMETHODIMP_(ULONG) Release() override {
        long r = --m_ref;
        if (!r) delete this;
        return r;
    }

    IFACEMETHODIMP Initialize(IStream* stream, DWORD) override {
        if (!stream) return E_INVALIDARG;
        if (!m_data.empty()) return HRESULT_FROM_WIN32(ERROR_ALREADY_INITIALIZED);
        return ReadAll(stream, m_data) ? S_OK : E_FAIL;
    }

    IFACEMETHODIMP GetThumbnail(UINT cx, HBITMAP* phbmp, WTS_ALPHATYPE* alpha) override {
        if (!phbmp || !alpha) return E_POINTER;
        *phbmp = nullptr;
        *alpha = WTSAT_RGB;
        Rendered r;
        bool ok = false;
        RunInMta([&] {
            try {
                auto doc = LoadPdf(m_data);
                if (doc.PageCount() > 0) {
                    r = RenderPage(doc, 0, cx ? cx : 256, false);
                    ok = true;
                }
            } catch (...) {
                ok = false;
            }
        });
        if (!ok) return E_FAIL;
        *phbmp = MakeDib(r);
        return *phbmp ? S_OK : E_OUTOFMEMORY;
    }
};

// ------------------------------------------------------------------ painel de visualização
static const UINT WM_PAGE_READY = WM_APP + 41;
static const wchar_t* kPreviewClass = L"LumenPdfPreviewWnd";
static const int kMargin = 12;
static const UINT kMaxPages = 40;

struct PreviewPage {
    UINT w, h;
    HBITMAP bmp;
};

struct PreviewState {
    std::mutex m;
    std::vector<PreviewPage> pages;
    std::atomic<bool> cancel{false};
    std::atomic<bool> done{false};
    std::atomic<bool> failed{false};
    UINT total = 0;
    std::atomic<HWND> hwnd{nullptr};
    ~PreviewState() {
        for (auto& p : pages)
            if (p.bmp) DeleteObject(p.bmp);
    }
};

class PreviewHandler;

class PreviewHandler : public IInitializeWithStream,
                       public IPreviewHandler,
                       public IObjectWithSite,
                       public IOleWindow,
                       public IPreviewHandlerVisuals {
    std::atomic<long> m_ref{1};
    std::vector<uint8_t> m_data;
    HWND m_parent = nullptr, m_hwnd = nullptr;
    RECT m_rc = {};
    IUnknown* m_site = nullptr;
    std::shared_ptr<PreviewState> m_state;
    COLORREF m_bg = RGB(243, 243, 246);
    COLORREF m_text = RGB(90, 90, 100);
    HFONT m_font = nullptr;
    int m_scroll = 0;

public:
    PreviewHandler() { ++g_refs; }
    virtual ~PreviewHandler() {
        Unload();
        if (m_site) m_site->Release();
        if (m_font) DeleteObject(m_font);
        --g_refs;
    }

    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        static const QITAB qit[] = {QITABENT(PreviewHandler, IInitializeWithStream),
                                    QITABENT(PreviewHandler, IPreviewHandler),
                                    QITABENT(PreviewHandler, IObjectWithSite),
                                    QITABENT(PreviewHandler, IOleWindow),
                                    QITABENT(PreviewHandler, IPreviewHandlerVisuals), {0}};
        return QISearch(this, qit, riid, ppv);
    }
    IFACEMETHODIMP_(ULONG) AddRef() override { return ++m_ref; }
    IFACEMETHODIMP_(ULONG) Release() override {
        long r = --m_ref;
        if (!r) delete this;
        return r;
    }

    // IInitializeWithStream
    IFACEMETHODIMP Initialize(IStream* stream, DWORD) override {
        if (!stream) return E_INVALIDARG;
        return ReadAll(stream, m_data) ? S_OK : E_FAIL;
    }

    // IObjectWithSite
    IFACEMETHODIMP SetSite(IUnknown* site) override {
        if (m_site) m_site->Release();
        m_site = site;
        if (m_site) m_site->AddRef();
        return S_OK;
    }
    IFACEMETHODIMP GetSite(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        *ppv = nullptr;
        return m_site ? m_site->QueryInterface(riid, ppv) : E_FAIL;
    }

    // IOleWindow
    IFACEMETHODIMP GetWindow(HWND* phwnd) override {
        if (!phwnd) return E_INVALIDARG;
        *phwnd = m_hwnd ? m_hwnd : m_parent;
        return S_OK;
    }
    IFACEMETHODIMP ContextSensitiveHelp(BOOL) override { return E_NOTIMPL; }

    // IPreviewHandlerVisuals
    IFACEMETHODIMP SetBackgroundColor(COLORREF c) override {
        m_bg = c;
        if (m_hwnd) InvalidateRect(m_hwnd, nullptr, FALSE);
        return S_OK;
    }
    IFACEMETHODIMP SetFont(const LOGFONTW* lf) override {
        if (!lf) return E_INVALIDARG;
        if (m_font) DeleteObject(m_font);
        m_font = CreateFontIndirectW(lf);
        return S_OK;
    }
    IFACEMETHODIMP SetTextColor(COLORREF c) override {
        m_text = c;
        return S_OK;
    }

    // IPreviewHandler
    IFACEMETHODIMP SetWindow(HWND parent, const RECT* rc) override {
        if (!parent || !rc) return E_INVALIDARG;
        m_parent = parent;
        m_rc = *rc;
        if (m_hwnd) {
            SetParent(m_hwnd, m_parent);
            Layout();
        }
        return S_OK;
    }
    IFACEMETHODIMP SetRect(const RECT* rc) override {
        if (!rc) return E_INVALIDARG;
        m_rc = *rc;
        Layout();
        return S_OK;
    }
    IFACEMETHODIMP DoPreview() override {
        if (m_hwnd || !m_parent) return E_FAIL;
        RegisterWndClass();
        m_hwnd = CreateWindowExW(0, kPreviewClass, nullptr, WS_CHILD | WS_VISIBLE | WS_VSCROLL | WS_CLIPSIBLINGS,
                                 m_rc.left, m_rc.top, m_rc.right - m_rc.left, m_rc.bottom - m_rc.top, m_parent,
                                 nullptr, g_hInst, this);
        if (!m_hwnd) return HRESULT_FROM_WIN32(GetLastError());
        StartRendering();
        return S_OK;
    }
    IFACEMETHODIMP Unload() override {
        if (m_state) {
            m_state->cancel = true;
            m_state->hwnd = nullptr;
            m_state.reset();
        }
        if (m_hwnd) {
            SetWindowLongPtrW(m_hwnd, GWLP_USERDATA, 0);
            DestroyWindow(m_hwnd);
            m_hwnd = nullptr;
        }
        m_data.clear();
        m_data.shrink_to_fit();
        return S_OK;
    }
    IFACEMETHODIMP SetFocus() override {
        if (m_hwnd) ::SetFocus(m_hwnd);
        return S_OK;
    }
    IFACEMETHODIMP QueryFocus(HWND* phwnd) override {
        if (!phwnd) return E_INVALIDARG;
        *phwnd = ::GetFocus();
        return S_OK;
    }
    IFACEMETHODIMP TranslateAccelerator(MSG* msg) override {
        IPreviewHandlerFrame* frame = nullptr;
        HRESULT hr = S_FALSE;
        if (m_site && SUCCEEDED(m_site->QueryInterface(IID_PPV_ARGS(&frame)))) {
            hr = frame->TranslateAccelerator(msg);
            frame->Release();
        }
        return hr;
    }

private:
    static void RegisterWndClass() {
        WNDCLASSEXW wc = {sizeof(wc)};
        if (GetClassInfoExW(g_hInst, kPreviewClass, &wc)) return;
        wc.style = CS_HREDRAW | CS_VREDRAW;
        wc.lpfnWndProc = WndProc;
        wc.hInstance = g_hInst;
        wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
        wc.lpszClassName = kPreviewClass;
        RegisterClassExW(&wc);
    }

    void Layout() {
        if (!m_hwnd) return;
        SetWindowPos(m_hwnd, nullptr, m_rc.left, m_rc.top, m_rc.right - m_rc.left, m_rc.bottom - m_rc.top,
                     SWP_NOZORDER | SWP_NOACTIVATE);
        UpdateScroll();
        InvalidateRect(m_hwnd, nullptr, FALSE);
    }

    void StartRendering() {
        auto st = std::make_shared<PreviewState>();
        st->hwnd = m_hwnd;
        m_state = st;
        RECT rc;
        GetClientRect(m_hwnd, &rc);
        // renderiza com folga e reduz na tela (nítido ao aumentar o painel, sem renderizar de novo)
        UINT width = (UINT)max(700, min(1500, (int)((rc.right - rc.left) * 1.6)));
        auto data = std::make_shared<std::vector<uint8_t>>(m_data);
        ++g_refs;  // mantém a DLL carregada enquanto a thread trabalha
        std::thread([st, data, width] {
            winrt::init_apartment(winrt::apartment_type::multi_threaded);
            try {
                auto doc = LoadPdf(*data);
                UINT total = doc.PageCount();
                {
                    std::lock_guard<std::mutex> lk(st->m);
                    st->total = total;
                }
                for (UINT i = 0; i < total && i < kMaxPages && !st->cancel; ++i) {
                    Rendered r = RenderPage(doc, i, width, true);
                    HBITMAP bmp = MakeDib(r);
                    {
                        std::lock_guard<std::mutex> lk(st->m);
                        st->pages.push_back({r.w, r.h, bmp});
                    }
                    if (HWND h = st->hwnd) PostMessageW(h, WM_PAGE_READY, 0, 0);
                }
            } catch (...) {
                st->failed = true;
            }
            st->done = true;
            if (HWND h = st->hwnd) PostMessageW(h, WM_PAGE_READY, 0, 0);
            winrt::uninit_apartment();
            --g_refs;
        }).detach();
    }

    int ContentHeight(int clientW) {
        if (!m_state) return 0;
        std::lock_guard<std::mutex> lk(m_state->m);
        int w = max(40, clientW - 2 * kMargin);
        int y = kMargin;
        for (auto& p : m_state->pages) y += (int)((double)p.h * w / p.w) + kMargin;
        return y + 40;
    }

    void UpdateScroll() {
        if (!m_hwnd) return;
        RECT rc;
        GetClientRect(m_hwnd, &rc);
        int h = ContentHeight(rc.right);
        int page = rc.bottom;
        m_scroll = max(0, min(m_scroll, max(0, h - page)));
        SCROLLINFO si = {sizeof(si), SIF_RANGE | SIF_PAGE | SIF_POS};
        si.nMin = 0;
        si.nMax = max(0, h - 1);
        si.nPage = (UINT)max(0, page);
        si.nPos = m_scroll;
        SetScrollInfo(m_hwnd, SB_VERT, &si, TRUE);
    }

    void ScrollTo(int y) {
        RECT rc;
        GetClientRect(m_hwnd, &rc);
        int maxy = max(0, ContentHeight(rc.right) - rc.bottom);
        y = max(0, min(y, maxy));
        if (y != m_scroll) {
            m_scroll = y;
            SetScrollPos(m_hwnd, SB_VERT, m_scroll, TRUE);
            InvalidateRect(m_hwnd, nullptr, FALSE);
        }
    }

    void Paint(HDC target) {
        RECT rc;
        GetClientRect(m_hwnd, &rc);
        int W = rc.right, H = rc.bottom;
        if (W <= 0 || H <= 0) return;
        HDC dc = CreateCompatibleDC(target);
        HBITMAP buf = CreateCompatibleBitmap(target, W, H);
        HGDIOBJ oldBuf = SelectObject(dc, buf);
        HBRUSH bg = CreateSolidBrush(m_bg);
        FillRect(dc, &rc, bg);
        DeleteObject(bg);
        SetBkMode(dc, TRANSPARENT);
        SetTextColor(dc, m_text);
        HGDIOBJ oldFont = SelectObject(dc, m_font ? (HGDIOBJ)m_font : GetStockObject(DEFAULT_GUI_FONT));
        int pw = max(40, W - 2 * kMargin);
        int y = kMargin - m_scroll;
        std::wstring msg;
        if (m_state) {
            std::lock_guard<std::mutex> lk(m_state->m);
            HDC src = CreateCompatibleDC(dc);
            SetStretchBltMode(dc, HALFTONE);
            SetBrushOrgEx(dc, 0, 0, nullptr);
            HBRUSH shadow = CreateSolidBrush(RGB(200, 200, 208));
            for (auto& p : m_state->pages) {
                int ph = (int)((double)p.h * pw / p.w);
                if (y + ph >= 0 && y <= H && p.bmp) {
                    RECT sh = {kMargin + 2, y + 2, kMargin + pw + 2, y + ph + 2};
                    FillRect(dc, &sh, shadow);
                    HGDIOBJ old = SelectObject(src, p.bmp);
                    StretchBlt(dc, kMargin, y, pw, ph, src, 0, 0, p.w, p.h, SRCCOPY);
                    SelectObject(src, old);
                }
                y += ph + kMargin;
            }
            DeleteObject(shadow);
            DeleteDC(src);
            if (m_state->failed && m_state->pages.empty())
                msg = L"Não foi possível exibir a pré-visualização deste PDF (ele pode estar protegido por senha).";
            else if (m_state->pages.empty())
                msg = L"Carregando…";
            else if (m_state->done && m_state->total > m_state->pages.size())
                msg = L"Mostrando " + std::to_wstring(m_state->pages.size()) + L" de " +
                      std::to_wstring(m_state->total) + L" páginas — abra no Lumen PDF para ver o documento completo.";
        }
        if (!msg.empty()) {
            RECT tr = {kMargin, m_state && !m_state->pages.empty() ? y : H / 2 - 20, W - kMargin, 0};
            tr.bottom = tr.top + 40;
            DrawTextW(dc, msg.c_str(), -1, &tr, DT_CENTER | DT_WORDBREAK);
        }
        SelectObject(dc, oldFont);
        BitBlt(target, 0, 0, W, H, dc, 0, 0, SRCCOPY);
        SelectObject(dc, oldBuf);
        DeleteObject(buf);
        DeleteDC(dc);
    }

    static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
        if (msg == WM_NCCREATE) {
            auto* cs = reinterpret_cast<CREATESTRUCTW*>(lp);
            SetWindowLongPtrW(hwnd, GWLP_USERDATA, (LONG_PTR)cs->lpCreateParams);
        }
        auto* self = reinterpret_cast<PreviewHandler*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
        if (!self) return DefWindowProcW(hwnd, msg, wp, lp);
        switch (msg) {
        case WM_ERASEBKGND:
            return 1;
        case WM_PAINT: {
            PAINTSTRUCT ps;
            HDC dc = BeginPaint(hwnd, &ps);
            self->Paint(dc);
            EndPaint(hwnd, &ps);
            return 0;
        }
        case WM_PRINTCLIENT:
            self->Paint((HDC)wp);
            return 0;
        case WM_PAGE_READY:
            self->UpdateScroll();
            InvalidateRect(hwnd, nullptr, FALSE);
            return 0;
        case WM_SIZE:
            self->UpdateScroll();
            InvalidateRect(hwnd, nullptr, FALSE);
            return 0;
        case WM_MOUSEWHEEL: {
            int delta = GET_WHEEL_DELTA_WPARAM(wp);
            self->ScrollTo(self->m_scroll - delta * 90 / WHEEL_DELTA);
            return 0;
        }
        case WM_LBUTTONDOWN:
            ::SetFocus(hwnd);
            return 0;
        case WM_KEYDOWN: {
            RECT rc;
            GetClientRect(hwnd, &rc);
            switch (wp) {
            case VK_DOWN: self->ScrollTo(self->m_scroll + 60); return 0;
            case VK_UP: self->ScrollTo(self->m_scroll - 60); return 0;
            case VK_NEXT: case VK_SPACE: self->ScrollTo(self->m_scroll + rc.bottom - 40); return 0;
            case VK_PRIOR: self->ScrollTo(self->m_scroll - rc.bottom + 40); return 0;
            case VK_HOME: self->ScrollTo(0); return 0;
            case VK_END: self->ScrollTo(1 << 28); return 0;
            }
            break;
        }
        case WM_VSCROLL: {
            SCROLLINFO si = {sizeof(si), SIF_ALL};
            GetScrollInfo(hwnd, SB_VERT, &si);
            int y = self->m_scroll;
            switch (LOWORD(wp)) {
            case SB_LINEUP: y -= 40; break;
            case SB_LINEDOWN: y += 40; break;
            case SB_PAGEUP: y -= (int)si.nPage; break;
            case SB_PAGEDOWN: y += (int)si.nPage; break;
            case SB_THUMBTRACK: case SB_THUMBPOSITION: y = si.nTrackPos; break;
            case SB_TOP: y = 0; break;
            case SB_BOTTOM: y = si.nMax; break;
            }
            self->ScrollTo(y);
            return 0;
        }
        }
        return DefWindowProcW(hwnd, msg, wp, lp);
    }
};

// ------------------------------------------------------------------ fábrica de classes e exportações
template <class T>
class Factory : public IClassFactory {
    std::atomic<long> m_ref{1};

public:
    Factory() { ++g_refs; }
    virtual ~Factory() { --g_refs; }
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        static const QITAB qit[] = {QITABENT(Factory, IClassFactory), {0}};
        return QISearch(this, qit, riid, ppv);
    }
    IFACEMETHODIMP_(ULONG) AddRef() override { return ++m_ref; }
    IFACEMETHODIMP_(ULONG) Release() override {
        long r = --m_ref;
        if (!r) delete this;
        return r;
    }
    IFACEMETHODIMP CreateInstance(IUnknown* outer, REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        *ppv = nullptr;
        if (outer) return CLASS_E_NOAGGREGATION;
        T* obj = new (std::nothrow) T();
        if (!obj) return E_OUTOFMEMORY;
        HRESULT hr = obj->QueryInterface(riid, ppv);
        obj->Release();
        return hr;
    }
    IFACEMETHODIMP LockServer(BOOL lock) override {
        if (lock) ++g_refs; else --g_refs;
        return S_OK;
    }
};

STDAPI DllGetClassObject(REFCLSID clsid, REFIID riid, void** ppv) {
    if (!ppv) return E_POINTER;
    *ppv = nullptr;
    IClassFactory* f = nullptr;
    if (IsEqualCLSID(clsid, CLSID_LumenThumb)) f = new (std::nothrow) Factory<ThumbProvider>();
    else if (IsEqualCLSID(clsid, CLSID_LumenPreview)) f = new (std::nothrow) Factory<PreviewHandler>();
    else return CLASS_E_CLASSNOTAVAILABLE;
    if (!f) return E_OUTOFMEMORY;
    HRESULT hr = f->QueryInterface(riid, ppv);
    f->Release();
    return hr;
}

STDAPI DllCanUnloadNow() { return g_refs.load() == 0 ? S_OK : S_FALSE; }

BOOL APIENTRY DllMain(HINSTANCE h, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_hInst = h;
        DisableThreadLibraryCalls(h);
    }
    return TRUE;
}
