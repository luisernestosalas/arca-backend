# ARCA Backend — FastAPI + PostgreSQL + Redis

Motor de simulación de resiliencia estructural. Levanta en un comando.

## Levantar en local

```bash
# 1. Clonar y entrar al directorio
cd arca-backend

# 2. Copiar variables de entorno
cp .env.example .env

# 3. Levantar todos los servicios
docker compose up --build

# La API queda disponible en:
# http://localhost:8000
# Docs interactivas: http://localhost:8000/docs
```

## Ejecutar tests

```bash
docker compose exec api python -m pytest tests/ -v
```

## Endpoints principales

### Crear un sujeto
```bash
curl -X POST http://localhost:8000/api/v1/subjects/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "NovaPay SAS",
    "industry": "fintech",
    "stage": "series_a",
    "country_code": "CO"
  }'
```

### Ejecutar simulación completa
```bash
curl -X POST http://localhost:8000/api/v1/simulations/ \
  -H "Content-Type: application/json" \
  -d '{
    "subject_id": "<UUID del sujeto>",
    "dim_scores": {
      "D1": 58, "D2": 45, "D3": 72,
      "D4": 63, "D5": 81, "D6": 55, "D7": 68
    },
    "metrics": {
      "revenue_usd": 480000,
      "cash_usd": 350000,
      "monthly_burn_usd": 25000,
      "runway_months": 14,
      "customer_revenues": [200000, 80000, 60000, 40000, 100000]
    },
    "n_simulations": 10000
  }'
```

### Verificar un certificado (público)
```bash
curl http://localhost:8000/api/v1/certifications/verify/<CERT_UUID>
```

## Conectar a Supabase (producción)

1. Crear proyecto en supabase.com
2. Ejecutar `scripts/init.sql` en el SQL Editor de Supabase
3. En `.env`, reemplazar `DATABASE_URL` con la URL de conexión de Supabase
4. Activar RLS en el dashboard de Supabase para cada tabla

## Estructura del proyecto

```
arca-backend/
├── app/
│   ├── api/v1/endpoints/   # Rutas FastAPI
│   ├── core/               # Configuración
│   ├── db/                 # Sesión async SQLAlchemy
│   ├── models/             # Modelos ORM (PostgreSQL)
│   ├── schemas/            # Schemas Pydantic (validación)
│   └── services/
│       ├── simulation_engine.py    # Motor Monte Carlo
│       └── anti_manipulation.py   # Sistema antimanipulación
├── scripts/
│   └── init.sql            # Schema PostgreSQL / Supabase
├── tests/
│   └── test_engine.py      # 15 tests del motor + antimanipulación
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```
