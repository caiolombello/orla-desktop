# Perfil de texto dos complementos

O perfil normativo do contrato experimental de complementos é
**`orla-addon-text-16.0.0-r1`**. Sua composição é fixa: categorias gerais
Unicode **16.0.0** Letter (L), Mark (M), Number (N), Punctuation (P) e Symbol
(S), mais o espaço ASCII **U+0020**. Todas as outras posições são recusadas,
incluindo controles, caracteres de formato, uso privado, separadores,
não atribuídos, não caracteres e surrogates U+D800–U+DFFF.

A classificação não depende da versão de Python, Qt, PCRE ou do sistema. Um
caractere que só foi atribuído em uma versão posterior do Unicode continua
recusado. Por exemplo, U+088F fica fora deste perfil. As adições do Unicode 16,
como U+1C89, U+10D40, U+11BC0 e U+1E5D0, são aceitas mesmo quando a tabela
Unicode do interpretador é anterior. Espaço ASCII, emoji e marcas combinantes
permitidas não são normalizados, removidos ou substituídos.

## Aplicação e limites

O parser exige `str` exata, texto não vazio e limites em **escalares Unicode**,
não bytes, unidades UTF-16 ou grafemas. No manifesto: nome 80, descrição 240,
autor 120 e licença 80 escalares. Origem continua limitada a 512 caracteres
na forma ASCII recebida. ID, namespace e versões mantêm os limites e padrões
ASCII já definidos; a presença no perfil não amplia esses padrões.

A origem continua sendo HTTPS ASCII sem credenciais, query ou fragmento,
com as mesmas regras de host, porta, escapes e caracteres proibidos. O texto
obtido por decodificação percent-encoded UTF-8 estrita também precisa estar
neste perfil. Essa verificação não introduz outro limite de comprimento do
texto decodificado e não altera as regras de URL existentes. Abrir uma origem
continua sendo responsabilidade do chamador; o perfil não autentica o site.

O limite de 65.536 bytes do arquivo e o de 262.144 bytes do envelope de gestão
são independentes dos limites de escalares. Não há truncamento para caber.
Regras de exportação de leituras, relógios, identidade da fonte e renderer
continuam iguais. O mesmo predicado é usado por `addon_format.text`, pela
origem decodificada e pelo estado QML que valida List/Inspect antes de
publicar metadados ou admitir uma aprovação de Install.

## Compatibilidade experimental

O `formatVersion` continua `0.1-experimental`; não foi acrescentado campo de
negociação, método ou envelope de transporte. Este documento fixa a
interpretação de texto antes dependente do runtime. Atualizar Python ou Qt
não pode ampliar ou reduzir a classificação silenciosamente.

Bytes existentes fora do perfil são recusados pelo parser com o código
finito `format`; o gerenciador também recusa os respectivos metadados. Não há
reparo, normalização, reempacotamento ou migração automática. Objetos,
recibos, hashes, gerações e consentimentos anteriores não são reescritos.
Um erro desconhecido ou posterior a uma mutação continua exigindo releitura,
sem repetir a mutação automaticamente. Toda instalação/atualização exige
inspeção e consentimento para os bytes exatos; instalar não ativa o pacote.

Uma futura ampliação exige decisão explícita do contrato, novo identificador
de perfil, dados oficiais fixados, revisão das consequências para arquivos
existentes e novas provas de paridade nos runtimes suportados. Não se adota
uma tabela mais nova durante atualização de dependências. Uma revisão do
perfil não concede consentimento para bytes diferentes e não autoriza
reescrever estado do usuário.

## Fonte canônica e reprodução offline

A única fonte de intervalos mantida no checkout é
[`scripts/data/addon-text-unicode16.json`](../scripts/data/addon-text-unicode16.json).
Ela contém o identificador, proveniência com URLs/tamanhos/SHA-256, texto
integral Unicode License V3, 736 intervalos inclusivos e o hash do vetor de
referência. São **154.810 posições aceitas**. O vetor de 139.264 bytes cobre
0x110000 posições: bit n no byte n//8, do menos para o mais significativo;
surrogates ficam em zero. SHA-256:

`073f8a36bcfd6b250cd5e0d07aa5641086829a58495758444ea70695c5a904ef`

Fontes oficiais fixadas:

- [UnicodeData 16.0.0](https://www.unicode.org/Public/16.0.0/ucd/UnicodeData.txt):
  2.175.362 bytes, `ff58e5823bd095166564a006e47d111130813dcf8bf234ef79fa51a870edb48f`.
- [ReadMe 16.0.0](https://www.unicode.org/Public/16.0.0/ucd/ReadMe.txt):
  693 bytes, `14cafa23788d3a20dd21d6b0cdcb8d6dab520781fcd9ad9392f3b88ea607e633`.
- [Unicode License V3](https://www.unicode.org/license.txt), cópia fixada com
  copyright 1991–2026: 1.995 bytes,
  `e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96`.
  A URL da licença pode mudar; a reprodução aceita somente esses bytes.

Com Python 3.10 ou posterior, sem rede nem bibliotecas adicionais:

```sh
python3 -B scripts/generate_addon_text_profile.py --check
python3 -B scripts/generate_addon_text_profile.py
python3 -B scripts/generate_addon_text_profile.py --from-ucd /diretorio/ucd-fixada --check
```

O diretório UCD deve conter exatamente as entradas usadas pelo importador:
`UnicodeData-16.0.0.txt`, `ReadMe-16.0.0.txt`, `UNICODE-LICENSE.txt`, com os
hashes acima. Arquivos extras não são adotados. O modo `--from-ucd` sem
`--check` regenera a fonte canônica e os dois consumidores; não baixa nada.
`--check` compara os resultados sem escrever. Dados corrompidos, duplicados,
fora de ordem, com proveniência distinta ou com vetor divergente são recusados.

O gerador emite um bloco embutido em `addon_format.py` e o helper puro
`AddonText.js`. Ambos levam o aviso Unicode integral nos comentários. O
runtime não lê o JSON canônico nem a UCD; basta distribuir esses consumidores
com o restante do pacote. O kit de contribuição inclui gerador, JSON e esta
documentação para conferir a reprodução offline. Os testes comparam o
`text()` Python real e `State.plain()` QML real ao vetor fixo, incluindo todas
as 1.112.064 posições escalares, surrogates, fronteiras e os fluxos públicos.

Este perfil trata classificação e interoperabilidade de texto. Ele não
qualifica serviço nativo, instalação, Plasma/Wayland, produtor ou composição
de configurações; essas validações permanecem separadas.
