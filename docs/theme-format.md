# Temas declarativos experimentais / Experimental declarative themes

**PT-BR:** `0.1-experimental` é a versão deste formato de dados, independente da
versão do Orla. Pode mudar antes da estabilização. Esta entrega é uma base
portátil de X1/DX2: valida e empacota dados, sem instalar nem aplicar temas no
dock. Editor, galeria/prévia, contraste/foco no Plasma, importação com recuperação
e teste por contribuidor externo continuam pendentes. C1, X1 e DX2 não estão
concluídos por este validador.

**EN:** `0.1-experimental` versions this data format independently of the Orla app.
It may change before stabilization. This portable X1/DX2 foundation validates and
packs data without installing or applying themes to the dock. The editor,
gallery/preview, Plasma contrast/focus checks, recoverable import and an outside
contributor trial remain pending. This validator does not complete C1, X1 or DX2.

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
