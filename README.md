# agroobservador_backend – Backend Stack

Infraestrutura inicial para o hackathon com FastAPI e um banco PostgreSQL/PostGIS que importa automaticamente os geopackages armazenados em `data/`.

## Estrutura

```
.
├── data/                     # Arquivos .gpkg usados para popular o banco
├── notebooks/                # Experimentação em notebooks/Jupyter
├── services/
│   └── backend/              # Código da API (FastAPI)
├── infra/
│   └── docker/               # Dockerfiles do banco e da API
├── docker-compose.yml        # Orquestração dos contêineres
└── .env.example              # Variáveis padrão (copie para .env se quiser customizar)
```

## Configuração

1. (Opcional) copie `cp .env.example .env` para ajustar usuário, senha ou portas.
2. Coloque seus geopackages em `data/`. O arquivo de exemplo `imoveis.gpkg` já está pronto.

> O contêiner do banco monta `./data` em `/opt/app/data`. No primeiro `docker compose up`, todos os `.gpkg` são importados via `ogr2ogr` e as extensões PostGIS são habilitadas automaticamente.

## Subindo a stack

```bash
docker compose up --build
```

Serviços expostos:

- API FastAPI: http://localhost:8000 (`GET /` e `/api/v1/health`)
- PostgreSQL/PostGIS: localhost:5432 (usuário/senha definidos nas variáveis)

A API usa `DATABASE_URL` para conectar no banco e um volume bind (`./services/backend/app`) para habilitar hot-reload com `uvicorn --reload`.

## Próximos passos

- Adicione modelos/rotas em `services/backend/app`.
- Caso precise reimportar os geopackages, remova o volume `pg_data` (`docker volume rm vazio_sanitario_pg_data` ou `docker compose down -v`) e suba novamente.
# agroobservador_backend
