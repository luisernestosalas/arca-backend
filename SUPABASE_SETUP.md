# Guía de setup Supabase para ARCA

Pasos en orden para tener Supabase completamente configurado.
Tiempo estimado: 20 minutos.

---

## Paso 1 — Crear el proyecto

1. Ir a https://supabase.com y crear cuenta (gratis)
2. Click **New project**
3. Completar:
   - **Name:** `arca-production`
   - **Database password:** guardar en un gestor de contraseñas, la necesitas después
   - **Region:** `South America (São Paulo)` — la más cercana a Colombia
   - **Plan:** Free tier es suficiente para el MVP
4. Esperar ~2 minutos a que el proyecto se inicialice

---

## Paso 2 — Obtener las credenciales

Ir a **Settings → API** en el panel de Supabase y copiar:

| Variable en .env          | Dónde encontrarla en Supabase                  |
|---------------------------|------------------------------------------------|
| `SUPABASE_URL`            | Project URL                                    |
| `SUPABASE_ANON_KEY`       | Project API keys → `anon` `public`             |
| `SUPABASE_SERVICE_KEY`    | Project API keys → `service_role` `secret`     |
| `SUPABASE_JWT_SECRET`     | Settings → API → JWT Settings → JWT Secret     |

Ir a **Settings → Database → Connection string → URI**:
- Seleccionar modo **Transaction** (para conexiones pooled)
- Reemplazar `[YOUR-PASSWORD]` con la contraseña del paso 1
- Ese string va en `DATABASE_URL` del `.env`

---

## Paso 3 — Ejecutar el schema SQL

1. En el panel de Supabase, ir a **SQL Editor**
2. Click **New query**
3. Copiar y pegar el contenido completo de `scripts/init.sql`
4. Click **Run** (o Ctrl+Enter)
5. Verificar que todas las tablas aparecen en **Table Editor**

Deberías ver: `tenants`, `subjects`, `submissions`, `simulations`,
`certifications`, `industry_benchmarks`, `audit_log`

---

## Paso 4 — Configurar Authentication

### 4.1 Habilitar proveedores de auth

Ir a **Authentication → Providers**:

- **Email:** habilitado por defecto ✓
- **Google** (opcional): necesitas OAuth credentials de Google Cloud Console
- Para MVP, solo Email es suficiente

### 4.2 Configurar Email templates

Ir a **Authentication → Email Templates**:

Plantilla de confirmación — personalizar con branding ARCA:

```html
<h2>Confirma tu cuenta ARCA</h2>
<p>Haz click en el enlace para confirmar tu email:</p>
<p><a href="{{ .ConfirmationURL }}">Confirmar cuenta</a></p>
<p style="color: #6b7280; font-size: 12px;">
  ARCA — Arquitectura de Riesgo y Certificación Anticipatoria
</p>
```

### 4.3 Configurar URL de redirect

Ir a **Authentication → URL Configuration**:
- **Site URL:** `https://tu-app.vercel.app` (o `http://localhost:3000` en dev)
- **Redirect URLs:** añadir `http://localhost:3000/**` para desarrollo

### 4.4 Crear primer usuario admin

Ir a **Authentication → Users → Add user**:
- Email: tu email
- Password: contraseña segura
- Auto Confirm User: ✓

O via SQL Editor:
```sql
-- Insertar usuario admin directamente
SELECT auth.create_user(
  '{"email": "admin@tudominio.com", "password": "tu-password-seguro", "email_confirm": true}'::jsonb
);
```

---

## Paso 5 — Configurar Row Level Security (RLS)

El schema ya tiene RLS habilitado en las tablas principales.
Activar las políticas en **Authentication → Policies**:

### Para `certifications` (verificación pública):
```sql
-- Ya incluida en init.sql — verificar que existe:
SELECT * FROM pg_policies WHERE tablename = 'certifications';
```

### Para `subjects` (aislamiento por tenant):
Descomentar en init.sql o ejecutar en SQL Editor:
```sql
-- Política: cada usuario ve solo los subjects de su tenant
CREATE POLICY "subjects_owner_access"
  ON subjects FOR ALL
  USING (
    tenant_id IN (
      SELECT id FROM tenants
      WHERE id::text = auth.uid()::text
    )
  );
```

### Para `simulations` y `certifications` (acceso del propietario):
```sql
CREATE POLICY "simulations_owner_access"
  ON simulations FOR ALL
  USING (
    subject_id IN (
      SELECT id FROM subjects
      WHERE tenant_id::text = auth.uid()::text
    )
  );
```

---

## Paso 6 — Configurar Storage

### 6.1 Crear el bucket (automático al arrancar la API)

Al arrancar la API con las variables de Supabase configuradas,
el bucket `certificates` se crea automáticamente via `ensure_bucket_exists()`.

Para crearlo manualmente: **Storage → New bucket**:
- **Name:** `certificates`
- **Public bucket:** ✓ (para que los certificados sean verificables públicamente)
- **File size limit:** 5MB
- **Allowed MIME types:** `application/pdf`

### 6.2 Políticas de Storage

Ir a **Storage → Policies → certificates**:

**Lectura pública** (cualquiera puede ver/descargar certificados):
```sql
CREATE POLICY "certificates_public_read"
  ON storage.objects FOR SELECT
  USING (bucket_id = 'certificates');
```

**Escritura solo autenticada** (solo el backend con service_key puede subir):
```sql
CREATE POLICY "certificates_service_write"
  ON storage.objects FOR INSERT
  WITH CHECK (
    bucket_id = 'certificates'
    AND auth.role() = 'service_role'
  );
```

---

## Paso 7 — Actualizar .env con credenciales reales

```bash
# En arca-backend/
cp .env.example .env
# Editar .env con los valores del Paso 2
```

```env
APP_ENV=production
PUBLIC_BASE_URL=https://tu-api.railway.app

SUPABASE_URL=https://abcdefghijkl.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc...
SUPABASE_JWT_SECRET=tu-jwt-secret-de-supabase-settings

DATABASE_URL=postgresql+asyncpg://postgres.abcdefghijkl:[PASSWORD]@aws-0-sa-east-1.pooler.supabase.com:6543/postgres
```

---

## Paso 8 — Verificar la conexión

```bash
# Con Docker
docker compose up --build

# Verificar health
curl http://localhost:8000/api/v1/health

# Crear usuario de prueba y obtener token
# (usando el email del paso 4.4)

# Verificar un certificado público (sin token)
curl http://localhost:8000/api/v1/certifications/verify/00000000-0000-0000-0000-000000000001
```

---

## Flujo de autenticación en el frontend

```javascript
// Con Supabase JS Client en Next.js
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
)

// Login
const { data, error } = await supabase.auth.signInWithPassword({
  email: 'user@example.com',
  password: 'password',
})

// El token JWT queda en data.session.access_token
// Pasarlo en el header Authorization a la API de ARCA:
const response = await fetch('http://localhost:8000/api/v1/simulations/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${data.session.access_token}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ ... })
})
```

---

## Límites del free tier de Supabase

| Recurso              | Límite free    | Suficiente para MVP |
|----------------------|----------------|---------------------|
| Filas en DB          | Sin límite     | ✓                   |
| Storage              | 1 GB           | ~200,000 PDFs de 5KB|
| Bandwidth            | 5 GB/mes       | ✓                   |
| Auth MAU             | 50,000/mes     | ✓                   |
| Edge Functions       | 500,000 inv/mes| ✓                   |
| Conexiones DB        | 60 directas    | Usar Transaction pooler |

Para producción real (>100 clientes activos), el plan Pro a $25/mes
desbloquea backups diarios, más conexiones y soporte.

---

## Troubleshooting frecuente

**Error: "invalid JWT"**
→ Verificar que `SUPABASE_JWT_SECRET` coincide exactamente con el valor
en Settings → API → JWT Settings → JWT Secret (sin espacios)

**Error: "connection refused" a PostgreSQL**
→ En producción usar Transaction pooler (puerto 6543), no Direct (puerto 5432)
→ Direct connection solo para migraciones con Alembic

**Error: "new row violates row-level security policy"**
→ Las políticas RLS están bloqueando el insert
→ Usar el service_role key en el backend (nunca el anon key para writes)

**Storage: "Bucket not found"**
→ El bucket se crea al arrancar la API si SUPABASE_URL y SUPABASE_SERVICE_KEY están configurados
→ O crearlo manualmente en el dashboard: Storage → New bucket → certificates
