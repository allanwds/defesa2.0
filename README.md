# Defesa Civil M'Boi Mirim (defesa2.0)

Sistema web de cadastro e análise de ocorrências da Defesa Civil de M'Boi Mirim, desenvolvido no Projeto Integrador da UNIVESP. Esta versão inclui um **dashboard com Machine Learning** em `/dashboard/`.

| Módulo | O que faz |
|---|---|
| `ocorrencias/` | Cadastro, lista, relatórios em PDF e gráficos |
| `api/` | API REST somente leitura (`/api/ocorrencias/`) |
| `dashboard/` | Dashboard com previsões de demanda, tipo provável de ocorrência, mapa e auditoria dos modelos |
| `ml/` | Limpeza dos dados, variáveis, modelos e notebooks de análise |

## Como iniciar a ferramenta

Os passos abaixo rodam tudo em um banco SQLite local, sem tocar no banco de produção.

### 1. Pré-requisitos

- Git
- [uv](https://docs.astral.sh/uv/), que instala o Python e as dependências. No macOS e Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`

O Python precisa ser 3.11 ou superior. O `python3` que vem com o macOS (3.9) é antigo demais, por isso o `uv` baixa uma versão adequada no passo seguinte.

### 2. Instalar

O dashboard está na branch `feat/dashboard-ml`, que não é a padrão do repositório:

```bash
git clone --branch feat/dashboard-ml https://github.com/allanwds/defesa2.0.git
cd defesa2.0

uv venv --python 3.13 .venv-local
source .venv-local/bin/activate

grep -v '^psycopg2==' requirements.txt > requirements-local.txt
echo psycopg2-binary >> requirements-local.txt
uv pip install -r requirements-local.txt -r ml/requirements.txt
```

No Windows, ative o ambiente com `.venv-local\Scripts\activate`. Sem o `uv`, use `python3.13 -m venv .venv-local` e `pip install` com os mesmos arquivos.

### 3. Criar o banco local e importar as ocorrências

```bash
export USE_SQLITE=1

python manage.py migrate --run-syncdb
curl -o ocorrencias.json https://defesa2-0.onrender.com/api/ocorrencias/
python manage.py importar_dados ocorrencias.json
```

O serviço do Render hiberna quando fica parado, então o `curl` pode levar cerca de um minuto na primeira vez. O comando `importar_dados` só roda em SQLite.

### 4. Treinar os modelos e gerar as previsões

```bash
python manage.py gerar_previsoes
```

Para simular outra data de referência, use `--como-de AAAA-MM-DD`.

### 5. Criar um usuário e subir o servidor

```bash
python manage.py createsuperuser
python manage.py runserver
```

Abra http://localhost:8000/, entre com o usuário criado e clique em **Dashboard ML**, ou acesse direto http://localhost:8000/dashboard/.

Em cada novo terminal, ative o ambiente e exporte `USE_SQLITE=1` antes de rodar o servidor.

## O que o dashboard mostra

- **Ocorrências por mês**, com os meses de cadastro incompleto em cinza.
- **Próxima semana**: previsão por distrito, disponível só quando o cadastro está em dia.
- **Demanda semanal esperada por mês**, com faixa entre o 10º e o 90º percentil.
- **Tipo provável de ocorrência**, por área de risco e época do ano.
- **Motivos, áreas de risco e mapa** das ocorrências, com filtros por distrito e ano.
- **Auditoria do modelo**: semanas já conhecidas, previstas só com o que existia antes delas, comparadas a uma referência simples.

## Limites dos modelos

A base tem poucos meses com cadastro completo (ver o alerta no topo do dashboard). Os modelos são Random Forest e superam a referência simples por margem pequena; a classificação do tipo de ocorrência é fraca. Use os resultados como apoio à decisão. O que mais melhora o desempenho é cadastrar os meses que faltam e rodar `gerar_previsoes` de novo.

## Como as previsões chegam ao site

1. `gerar_previsoes` lê as ocorrências do banco, aplica a limpeza de `ml/limpeza.py`, treina os modelos de `ml/modelos.py` e grava o resultado nas tabelas do app `dashboard`.
2. O site apenas lê essas tabelas. Por isso o pandas e o scikit-learn são necessários só onde o comando roda.

## Produção

Sem a variável `USE_SQLITE`, o projeto usa o banco PostgreSQL configurado em `defesacivil_sqlite/settings.py`. Para publicar o dashboard:

```bash
python manage.py migrate
python manage.py gerar_previsoes
```

Rode `gerar_previsoes` fora do plano gratuito do Render, que hiberna e tem pouca memória, e repita sempre que novas ocorrências forem cadastradas.

## Notebooks de análise

Em `ml/notebooks/`: análise exploratória, modelos de base, efeito da chuva e reconstrução da série. A documentação da API está em `README_INTEGRACAO.md`.
