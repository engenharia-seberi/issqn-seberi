# Cálculo de ISSQN – Prefeitura Municipal de Seberi

App de página única que reproduz a planilha `Cálculo ISSQN.xlsx`:

```
R$/m²           = CUB × fator de cálculo (35%)
Base de cálculo = R$/m² × área da edificação
ISSQN           = Base de cálculo × alíquota (3%)
```

O valor do CUB vem de `cub.js`, gerado automaticamente a partir da
"Série Histórica – Valor" mais recente em <https://sinduscon-rs.com.br/cub-rs/>.

## Arquivos

| Arquivo | Função |
|---|---|
| `index.html` | O app (abre direto com dois cliques ou pelo GitHub Pages) |
| `cub.js` | Tabela do CUB/RS desde 2007 — gerada, não editar à mão |
| `scripts/atualizar_cub.py` | Busca o PDF mais recente no Sinduscon-RS e regrava `cub.js` |
| `.github/workflows/atualizar-cub.yml` | Roda o script de segunda a sexta, 09h (Brasília) |

## Hospedar no GitHub Pages

1. Criar um repositório no GitHub e enviar o conteúdo desta pasta.
2. **Settings → Pages**: Source = *Deploy from a branch*, branch `main`, pasta `/ (root)`.
3. **Settings → Actions → General → Workflow permissions**: marcar *Read and write permissions*
   (necessário para a rotina gravar o `cub.js`).
4. Em **Actions → Atualizar CUB/RS → Run workflow** dá para forçar uma atualização a qualquer momento.

## Atualizar o CUB manualmente (no computador)

```bash
pip install -r requirements.txt
python scripts/atualizar_cub.py
```

Se o Sinduscon mudar o layout do PDF ou da página, o script falha sem alterar o
`cub.js` (o app continua com o último valor válido e o campo do CUB aceita digitação manual).
