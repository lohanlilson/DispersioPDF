# Dispersio PDF

Leitor e editor de PDF completo em Python (PySide6 + PyMuPDF), com layout no estilo dos leitores profissionais:
abas de documentos, painel **Todas as ferramentas** à esquerda, barra rápida flutuante, painéis de miniaturas /
marcadores / comentários / anexos à direita e controles de página e zoom flutuantes.

## Gerar o instalador (Windows)

1. Instale o Python (marcando "Add python.exe to PATH").
2. Dê dois cliques em `build.bat`. Ele cria o ambiente, instala as dependências, gera o executável e o
   instalador (instala o Inno Setup automaticamente via winget, se faltar).
3. O resultado fica em `Saida\DispersioPDF-Setup-<versão>.exe`.

O instalador: permite escolher a pasta (padrão: Arquivos de Programas), instalar para todos ou só para o usuário,
criar atalho na Área de Trabalho, registra o programa para abrir .pdf e, ao final, abre a tela do Windows para
defini-lo como leitor padrão (o Windows 10/11 exige que o usuário confirme). Aparece em "Adicionar ou remover
programas" com desinstalador.

## Atualização automática (GitHub)

O programa consulta a última Release de `UPDATE_REPO` (em `dispersio/__init__.py`) e oferece a atualização.
Para publicar uma versão nova:

1. Aumente `__version__` em `dispersio/__init__.py` e descreva as novidades no `CHANGELOG.md` (`## 1.0.1`).
2. Envie para a branch `main`. O GitHub Actions (`.github/workflows/publicar.yml`) gera no Windows o
   instalador, o patch da versão anterior e o `versao.json`, e cria a Release `v1.0.1`.

## Atualizações por patch (manual)

1. Aumente `__version__` em `dispersio/__init__.py` (ex.: 1.0.0 → 1.0.1).
2. Rode `gerar_patch.bat` e informe a versão anterior (ex.: 1.0.0).
3. Será criado `Saida\DispersioPDF-Atualizacao-1.0.0-para-1.0.1.exe`, que contém **só os arquivos alterados**,
   encontra a pasta onde o programa está instalado, fecha o programa se estiver aberto e substitui os arquivos.

Cada build fica guardado em `releases\<versão>` — **não apague essa pasta**, ela é a base para os próximos patches.

## Rodar sem instalar

`executar.bat` (depois de rodar o `build.bat` uma vez).

### Opcionais
| Recurso | Requisito |
|---|---|
| OCR | Já incluído (português e inglês) |
| Word/Excel → PDF | Embutido para .docx/.xlsx/.csv/.txt; outros formatos (.doc, .ppt, .odt…) usam o Office ou LibreOffice se existirem |
| Certificado A3 (token) | Driver do token (ex.: SafeNet `eTPKCS11.dll`) |
| Ler em voz alta | Vozes do Windows (já incluídas) |

## Funcionalidades

**Leitura** — abas múltiplas, rolagem contínua, página dupla, zoom (Ctrl+roda, ajustar largura/página), busca com
destaque e navegação (F3), miniaturas, marcadores, links clicáveis, modo de leitura (Ctrl+H), tela cheia, tema escuro,
inverter cores, ler em voz alta, imprimir, propriedades/metadados, arquivos recentes, arrastar e soltar.

**Comentar** — nota, destacar, sublinhar, tachar, caixa de texto, desenho à mão livre, retângulo, elipse, seta, linha,
carimbos (Aprovado, Pago, Confidencial… ou personalizado), mover/editar/recolorir/excluir, painel e resumo de comentários,
nivelar.

**Editar** — editar texto existente, adicionar texto, imagens e links, marca d'água (texto ou imagem), cabeçalho/rodapé/
numeração (inclusive Bates), cor de fundo, cortar páginas.

**Organizar** — grade de páginas com arrastar e soltar, girar, excluir, inserir em branco ou de arquivo, extrair, dividir
(a cada N páginas, intervalos, marcadores ou tamanho), combinar arquivos.

**Converter** — PDF → Word, Excel (tabelas), imagens (PNG/JPG/TIFF), texto; imagens/Office/TXT → PDF; comprimir; OCR.

**Proteger** — senha AES-256 com permissões, remover senha, ocultar (tarja) área, localizar e ocultar (texto, CPF, CNPJ,
e-mail, telefone), aplicar ocultações, remover informações ocultas.

**Assinar e formulários** — preencher e assinar (assinatura digitada, desenhada ou imagem), assinatura digital PAdES com
certificado A1 (.pfx) ou A3 (PKCS#11), validação de assinaturas, preencher formulários, criar campos (texto, caixa de
seleção, lista).

**Comparar** — relatório de diferenças de texto página a página.

## Estrutura

```
main.py                 ponto de entrada
dispersio/mainwindow.py  janela, abas, menus e todas as ferramentas
dispersio/doctab.py      documento aberto: desfazer/refazer, salvar, operações de página
dispersio/viewer.py      renderização, seleção, busca e ferramentas de comentário
dispersio/panels.py      painéis laterais, barra rápida, organizador
dispersio/dialogs.py     diálogos
dispersio/ops.py         operações de PDF sem interface (testáveis)
dispersio/signing.py     assinatura digital e validação (pyHanko)
dispersio/theme.py       temas claro/escuro
dispersio/icons.py       ícones vetoriais
```

## Atalhos principais
Ctrl+O abrir · Ctrl+S salvar · Ctrl+P imprimir · Ctrl+F localizar · Ctrl+Z/Y desfazer/refazer · V selecionar · H mão ·
Ctrl+Shift+H destacar · Ctrl+E editar texto · F4 miniaturas · Delete excluir comentário · F1 lista completa.

## Limitações conhecidas
- A edição de texto substitui o trecho usando fontes padrão (Helvetica/Times/Courier); fontes incorporadas do original são aproximadas.
- A validação mostra integridade e signatário; a confiança na cadeia ICP-Brasil depende das raízes instaladas.
- PyMuPDF é licenciado AGPL — uso interno é livre; para distribuir comercialmente sem abrir o código, é preciso licença comercial da Artifex.
