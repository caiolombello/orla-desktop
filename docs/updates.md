# Consulta experimental de updates

Disponível no checkout fonte e no ZIP da release 0.2.5, em `scripts/updates.py`. Execute no diretório extraído do bundle; o `.plasmoid` sozinho não contém a CLI nem uma interface de updates. A release 0.2.4 não incluía esse comando. Esta primeira fatia de U1 é uma CLI Linux com Python 3.10+ e biblioteca padrão. Ela consulta releases públicas do repositório oficial por HTTPS e compara a versão informada. O desktop não precisa estar aberto.

```bash
python3 scripts/updates.py check --installed-version 0.2.5 --channel beta
```

Substitua `--installed-version` pela versão que deseja comparar. O comando não detecta a versão instalada ou em execução. `stable` exclui a marcação de pré-release do GitHub e sufixos SemVer; `beta` inclui ambos. As alphas atuais, como `v0.2.4`, usam a marcação de pré-release do GitHub mesmo sem sufixo. Portanto, o canal estável pode retornar `no_release`.

O stdout contém um objeto JSON com `status`, `reason`, `source`, `installed_version`, `available_version`, `available_url`, `channel` e `checked_at` UTC. Versões seguem SemVer estrito; metadados de build não alteram a precedência.

| Estado | Significado |
|---|---|
| `update_available` | Existe uma versão elegível mais recente |
| `up_to_date` | A versão informada alcança ou supera a mais recente do canal |
| `no_release` | A consulta terminou sem release elegível no canal |
| `unavailable` | Entrada, rede, protocolo, resposta ou consulta incompleta impedem a comparação |
| `rate_limited` | O GitHub recusou a consulta com 403/429 |

Os três primeiros estados retornam código 0; os dois últimos retornam 2. A consulta não baixa pacotes, instala, grava cache, usa tokens ou altera a configuração da sessão. Há somente uma fonte fixa; redirects são recusados. Respostas/URLs incompatíveis produzem erro seguro, sem conteúdo bruto do servidor.

Limites: até duas páginas de 50 releases, 256 KiB por resposta e 384 KiB no total. Um teto cheio é tratado como consulta incompleta. O trabalho de rede ocorre em processos próprios, com deadline de até 5 segundos por requisição e orçamento total de 12 segundos; encerrar e recolher os recursos do último processo pode acrescentar até 0,5 segundo ao retorno (até 5,5/12,5 segundos). Não há tentativa automática após falha.

Execute esta CLI como processo independente. Seu transporte usa `fork` no Linux e não oferece uma API para importar em uma aplicação Qt com várias threads. O parâmetro interno `fetcher` é uma fixture síncrona cooperativa para testes, sem a garantia de deadline do transporte de produção.

```bash
python3 -m unittest discover -s tests -p 'test_updates.py' -v
```

Os 17 testes offline passaram em Python 3.14.7; a revisão independente repetiu o resultado. A cobertura inclui canais, precedência, respostas inválidas/grandes, paginação incompleta, URLs hostis, falhas de protocolo/rede e encerramento de um worker bloqueado com PID morto e reapado. A consulta anônima com o transporte final comparou `0.2.3` no canal beta e retornou `update_available`, versão `0.2.4`. Isso verifica somente a consulta e comparação, sem instalar ou validar um pacote. A CI executa os testes offline em processo próprio.

U1 completo ainda exige cache, última consulta persistente, canal configurável e UI integrada. U2 exige compatibilidade, autenticidade dos pacotes, preservação da configuração e recuperação após atualização interrompida.

Fontes: [API de releases GitHub](https://docs.github.com/en/rest/releases/releases?apiVersion=2022-11-28#list-releases), [paginação](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api) e [limites de consultas](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#exceeding-the-rate-limit).
