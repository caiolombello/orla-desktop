# Temas declarativos experimentais / Experimental declarative themes

**PT-BR:** `0.1-experimental` é a versão deste formato de dados, independente da
versão do Orla. Pode mudar antes da estabilização. O applet agora aceita JSON
colado explicitamente no painel recolhível **Tema JSON experimental** e permite
usar os dez tokens na prévia. Isso não instala um tema: aplicar salva somente a
aparência normal do perfil atual, sem documento ou metadados externos. O kit de
CLI continua validando e empacotando arquivos. Seção abaixo descreve o consumidor
no applet. Importação de arquivo, galeria, autoria guiada e qualificação nativa
de contraste/foco continuam pendentes. C1, X1 e DX2 seguem parciais.

**EN:** `0.1-experimental` versions this data format independently of the Orla app.
It may change before stabilization. The applet now accepts explicitly pasted JSON
in a collapsible **Experimental JSON theme** section and previews its ten tokens.
This does not install a theme: Apply saves only the current profile's ordinary
appearance, without the external document or metadata. The CLI kit still
validates and packs files. File import, gallery, guided authoring and native
contrast/focus qualification remain pending. C1, X1 and DX2 remain partial.

## Applet preview / Prévia no applet

In Appearance settings, expand **Experimental JSON theme**, paste a complete
`0.1-experimental` document and choose **Use in preview**. Parsing is explicit;
editing the text alone never previews it. The imported ten tokens replace the
current temporary appearance draft while retaining its valid base preset. You
can continue editing tokens, then use the existing Apply, Undo, Cancel or Escape
controls. Apply writes only the normalized appearance to the current profile.
Pending or invalid non-empty input blocks Apply and profile create/switch; an
invalid attempt preserves the most recent good preview. Clear JSON removes the
pending text/error while retaining that preview.

Declared name, author, version and license are shown as plain text. They are
unverified claims: identity, ownership and redistribution rights are not checked.
The document and metadata are not saved, installed or exported. The field accepts
pasted text only; there is no file chooser, URL, download, catalog or executable
content. The text widget can temporarily receive a larger clipboard paste; the
parser bounds its own work using a 65,536-byte-equivalent UTF-8 limit. Because Qt
has already decoded the text, this does not prove an original file's encoding or
strictly bound native clipboard memory.

See the [consumer validation record](validation/theme-consumer-0.2.6.md) for the
synthetic evidence and unqualified native behavior.

## Aparência portátil / Portable appearance

O módulo recolhível **Aparência portátil experimental**, na aba Aparência, exporta o estado salvo da aparência e a ordem/visibilidade dos sete widgets. A exportação não inclui apps fixados, nome/ID de perfil, eventos, contexto, caminhos ou dados de integrações. O campo de saída permite selecionar e copiar manualmente; não lê arquivos nem grava automaticamente no clipboard.

Para importar, use um perfil criado na aba Perfis, cole o documento e escolha **Usar na prévia**. Apenas colar não muda o dock. **Aplicar** salva aparência e widgets juntos no perfil atual; **Cancelar**, Escape ou fechar descartam a prévia; **Desfazer** restaura os dois campos enquanto o perfil/revisão não tiver mudado. Texto inválido não escreve e preserva a última prévia válida. As preferências anteriores podem ser exportadas; sua importação exige criar ou escolher um perfil explicitamente.

Este preset usa `kind: "orla-appearance-preset"` e `formatVersion: "0.1-experimental"`. É um documento separado do tema com autoria descrito abaixo. O [schema de preset](../themes/schema/appearance-preset-0.1-experimental.schema.json) exige `appearance` com os dez tokens/baseTheme e `widgets` com cada ID conhecido exatamente uma vez; a ordem da lista é a ordem da dock. Versão, campos extras, duplicatas, tipos/ranges inválidos e entrada acima dos limites do parser são rejeitados. O formato continua experimental.

The expandable **Experimental portable appearance** module exports saved appearance and the order/visibility of the seven widgets. Copy the selectable output manually. To import, explicitly create or choose a managed profile, paste the document and choose **Use in preview**. Apply commits appearance and widgets together; Cancel/Escape discard, and Undo restores both while the profile/revision is unchanged. This separate experimental preset contains presentation data only; it is not a theme with authorship or a profile backup.

## Autoria / Authoring

Copie um [exemplo claro](../themes/examples/essential.json) ou
[escuro](../themes/examples/mare.json), altere autoria, ID, licença e tokens.
Copy a [light](../themes/examples/essential.json) or
[dark](../themes/examples/mare.json) example and edit its author, ID, license and
tokens. These synthetic examples are licensed MIT; their IDs do not establish
domain ownership, trust or compatibility with an installed Orla version.

```bash
python3 scripts/themes.py validate themes/examples/mare.json
python3 scripts/themes.py validate themes/examples/mare.json --json
python3 scripts/themes.py pack themes/examples/mare.json --output /tmp/orla-theme-demo
python3 -m unittest discover -s tests -p 'test_themes.py' -v
```

No Linux, Python 3.10+ e biblioteca padrão bastam; nenhuma conta, Qt, API, IA ou
pacote pip. On Linux, Python 3.10+ and its standard library are sufficient. No
accounts, Qt, API, AI or pip packages are required. Commands read the explicit input; only `pack` writes
to the explicit output directory. Existing output files are preserved: choose a
new directory to pack again. The input and final output directory cannot be
symlinks. No archive extraction, discovery or installation occurs.

## Contrato / Contract

Use um objeto JSON com todos os campos abaixo, sem campos extras em qualquer
objeto. Use a JSON object with every field below and no additional object fields.

| Campo / Field | Regra / Rule |
|---|---|
| `formatVersion` | String literal `0.1-experimental` |
| `id` | 1–120 characters; lowercase ASCII reverse-domain labels, e.g. `org.example.my-theme`; labels start with a letter, contain letters/digits and internal single hyphens; at least two labels |
| `name`, `author` | 1–120 characters; plain text under the character rule below |
| `license` | 1–80 characters; explicit plain-text declaration, e.g. `MIT` or `GPL-3.0-or-later`; validation does not verify redistribution rights |
| `version` | Theme version, 1–32 characters; three numeric segments `major.minor.patch`, no leading zeros except `0`, no suffix |
| `tokens` | Object containing all ten tokens below |

Texto simples: letras ASCII e latinas `À–Ö`, `Ø–ö`, `ø–ÿ`, dígitos ASCII,
espaços internos e `.,_+-`. Não há espaços nas extremidades, controles,
marcação, expressões ou URLs. Esta restrição experimental ainda não cobre
todos os alfabetos. Plain text permits ASCII letters, Latin letters `À–Ö`,
`Ø–ö`, `ø–ÿ`, ASCII digits, internal spaces and `.,_+-`. Leading/trailing spaces,
controls, markup, expressions and URLs are rejected. This experimental character
set does not yet cover every alphabet.

| Token | Tipo e limites / Type and inclusive limits | Significado proposto / Proposed meaning |
|---|---|---|
| `foreground`, `muted`, `accent`, `surface`, `border` | Six hex digits prefixed by `#`; upper/lowercase accepted, output normalized to lowercase `#rrggbb` | Text, secondary text, accent, background and outline colors |
| `radius` | Finite JSON number, 0–32 | Corner radius in logical pixels |
| `spacing` | Finite JSON number, 0–16 | Tile spacing in logical pixels |
| `opacity` | Finite JSON number, 0.4–1 | Surface opacity, separate from RGB colors |
| `iconSize` | Finite JSON number, 24–64 | Icon size in logical pixels |
| `reducedMotion` | JSON boolean `true` or `false` | Request reduced animation |

Números podem ser fracionários; booleanos não são números. Não há tokens
opcionais/defaults implícitos. Numbers may be fractional; booleans are not
numbers. There are no optional tokens or implicit defaults. Assets, paths,
imports, fonts, URLs, QML, JavaScript and other code are unsupported. Adding such
fields fails validation rather than granting capabilities. Metadata is displayed
as text and is never evaluated. Future consumers must keep that rule.

Arquivo: UTF-8 estrito sem BOM, até 65.536 bytes, no máximo quatro níveis de
objetos/arrays (o tema válido usa dois). Chaves duplicadas, NaN, Infinity e números
que transbordam para infinito são rejeitados antes do consumo. File: strict UTF-8
without a BOM, at most 65,536 bytes and four object/array levels (a valid theme
uses two). Duplicate keys, NaN, Infinity and numbers overflowing to infinity are
rejected. Only regular input files are read, with bounded reads.

O [schema JSON](../themes/schema/theme-0.1-experimental.schema.json) descreve
exatamente os campos, tipos e valores aceitos após parse. Limites de bytes,
UTF-8, duplicatas e profundidade são regras obrigatórias do parser e não são
expressáveis apenas pelo JSON Schema; `x-maxBytes`/`x-maxDepth` são anotações.
The JSON Schema describes the same parsed field/type/value contract as the
runtime validator. Byte size, encoding, duplicate keys and depth are mandatory
parser rules beyond standard JSON Schema; its `x-maxBytes`/`x-maxDepth` keywords
are annotations. Use the CLI or Python parser for complete validation.

## API, erros e artefato / API, errors and artifact

The canonical Python implementation now ships in
`package/contents/code/theme_format.py`. The `scripts/themes.py` facade retains
the CLI and documented exports below, including when called from another working
directory. The format and validation rules are unchanged.

`from scripts import themes` exposes these experimental functions:

- `parse_theme(data: bytes) -> dict`: bounded strict decode, parse and validation.
- `load_theme(path: Path) -> dict`: bounded regular-file read and validation.
- `validate_theme(value: object) -> dict`: validate already parsed data.
- `canonical_bytes(value: object) -> bytes`: validate and produce canonical bytes.
- `pack_theme(source: Path, output_dir: Path) -> Path`: validate before creating an
  output directory and atomically publish one complete artifact without replacing
  existing files.

Validation returns a new dictionary; the caller's input is preserved. Failures
raise `ThemeError`, a `ValueError` subclass with `errors`, a list containing the
first `{field, code, message}` error. `field` uses a `$` root and slash-separated
known field names. Messages never echo rejected values. Example:

```json
{"valid":false,"formatVersion":"0.1-experimental","errors":[{"field":"$/tokens/opacity","code":"range","message":"Use a number from 0.4 to 1."}]}
```

**Base do leitor local / Local reader foundation:** o pacote também contém
`theme_file.py`, um leitor interno experimental de uma única URL `file:///`
absoluta e percent-encoded. O limite da URL é 16.384 bytes; host, query, fragmento,
escapes inválidos e controles são recusados antes de abrir o arquivo. O caminho
é decodificado uma vez em UTF-8 estrito e passa pelo leitor regular e parser de
65.536 bytes existentes. A CLI recebe uma URL e retorna somente
`{valid, formatVersion, theme}` ou `{valid, formatVersion, errors}`, com códigos
de saída 0/1/2 para sucesso, validação/I/O e uso inválido. O resultado não
acrescenta caminho, nome do arquivo ou conteúdo inválido aos erros.

The installed reader and parser run together with Python's standard library,
without the source checkout, Qt, launcher or optional integrations. This is a
foundation for a future chooser: no Import file button or D-Bus activation ships
in this increment, and it never saves appearance or configuration. Parent paths
may resolve symlinks; only the final opened path rejects a symlink. A concurrent
write is not an atomic snapshot, and the bounded read does not guarantee a hard
deadline for a stalled filesystem. The future service must own its worker and
timeout. Chooser focus/return on Wayland remains unqualified.

`validate --json` writes `{valid, formatVersion, theme}` on success or
`{valid, formatVersion, errors}` on failure. Exit statuses: `0` success, `1`
validation/I/O failure, `2` CLI usage error. Human errors go to stderr; JSON
validation results go to stdout. Codes are `type`, `size`, `utf8`, `json`, `depth`,
`duplicate_key`, `nonfinite`, `unknown_key`, `required`, `format_version`,
`length`, `format`, `range`, `file`, `exists` and `output`. Fix the indicated field
using the table; for file/output errors check the explicit path and permissions.

`pack` produces `<id>-<version>.orla-theme.json`: UTF-8, sorted keys, compact JSON,
lowercase RGB colors, integral numeric tokens represented as integers, and one
final newline. No timestamps, archive, signature, secret or application
configuration is included. Identical normalized data produces identical bytes
on repeated packs; arbitrary precision decimal equivalence is not promised.

`pack` escreve em arquivo temporário exclusivo no mesmo diretório, finaliza a
escrita/flush/fechamento e publica o arquivo completo por hardlink atômico sem
sobrescrita. Falha de escrita/flush não publica arquivo final parcial; a limpeza
remove somente o temporário criado pela operação, nunca um destino existente.
O diretório criado pode permanecer vazio. Caminhos com NUL ou Unicode não
codificável retornam erros estruturados `file`/`output`.

`pack` writes an exclusive same-directory temporary file, finishes
writing/flushing/closing it, then atomically publishes the complete file with a
non-replacing hardlink. A write/flush failure does not publish a partial final
artifact; cleanup removes only the temporary created by this operation and never
an existing destination. A newly created directory may remain empty. Paths with
NUL or unencodable Unicode return structured `file`/`output` errors. Filesystems
must support hardlinks; otherwise packing fails safely. Atomic visibility does
not promise durability across power loss: the tool does not fsync files or
directories. Permission changes or process/system termination may prevent
temporary cleanup.

Packing/validation proves structure, not appearance, accessibility, publisher
identity, license ownership or native compatibility.
