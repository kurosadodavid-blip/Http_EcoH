# API Ecohidroponía

Backend inicial para monitoreo de sistemas hidropónicos con FastAPI y PostgreSQL.

## Incluye
- 11 tablas: usuarios, sistemas_hidroponicos, dispositivos, sensores, mediciones,
  cultivos, etapas_cultivo, historial_etapas, umbrales, alertas y actividades_cultivo.
- Registro de usuarios e inicio de sesión con token Bearer.
- Registro y consulta de sistemas, dispositivos, sensores y cultivos.
- Recepción de mediciones y consulta histórica.
- Evaluación básica de umbrales y generación de alertas sin duplicar una alerta activa del mismo sensor/tipo.
- Resumen del cultivo para que la app móvil pueda mostrar últimas lecturas y alertas.
- Documentación interactiva en /docs.

## 1. Crear PostgreSQL en Render
1. En Render, crea una base de datos PostgreSQL.
2. Abre la base y copia **Internal Database URL** si la API también estará alojada en Render y ambas están en la misma región.
3. Si la API se ejecuta fuera de Render, utiliza **External Database URL**.
4. No publiques esa URL en GitHub ni la compartas: contiene credenciales.

## 2. Crear el servicio web
1. Sube el contenido de esta carpeta a un repositorio de GitHub.
2. En Render, crea un Web Service conectado al repositorio.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. En Environment agrega:
   - `DATABASE_URL`: pega la URL de PostgreSQL de Render.
   - `SECRET_KEY`: una cadena aleatoria larga y privada.
   - `ACCESS_TOKEN_MINUTES`: `1440`
   - `CORS_ORIGINS`: `*` para pruebas; en producción web limita los dominios.

También puedes usar el archivo `render.yaml` como punto de partida para Render Blueprint.

## 3. Ejecutar localmente (opcional)
1. Instala Python.
2. Ejecuta `pip install -r requirements.txt`.
3. Copia `.env.example` a `.env` y coloca tu URL de conexión.
4. Instala y carga las variables de entorno con tu método habitual; por ejemplo:
   - PowerShell: `$env:DATABASE_URL="tu_url"`
   - PowerShell: `$env:SECRET_KEY="una_clave_larga"`
5. Ejecuta: `uvicorn main:app --reload`

## 4. Probar
Abre `https://TU-SERVICIO.onrender.com/docs`.

### Registrar usuario
POST `/usuarios`
```json
{
  "nombre": "David",
  "correo": "usuario@ejemplo.com",
  "contraseña": "UnaClaveSegura123"
}
```

### Iniciar sesión
POST `/auth/login` usa formulario OAuth2:
- username: correo
- password: contraseña

Copia el `access_token` y pulsa **Authorize** en `/docs`. Usa el token como Bearer.

### Crear sistema
POST `/sistemas`
```json
{
  "nombre": "Sistema NFT de lechugas",
  "ubicacion": "Casa",
  "fecha_instalacion": "2026-11-11",
  "estado": "activo"
}
```

### Crear dispositivo
POST `/dispositivos`
```json
{
  "id_sistema": 1,
  "nombre": "ESP32 principal",
  "identificador": "ESP32-ECO-001",
  "estado": "desconectado"
}
```

### Crear sensor
POST `/sensores`
```json
{
  "id_dispositivo": 1,
  "nombre": "Sensor de pH",
  "tipo_sensor": "ph",
  "unidad_medida": "pH",
  "estado": "activo"
}
```

### Enviar medición
POST `/mediciones`
```json
{
  "id_sensor": 1,
  "valor": 6.5,
  "calidad_dato": "valido"
}
```
Este endpoint está abierto para que el dispositivo pueda enviar lecturas. Antes de conectar hardware real, agrega autenticación por API key o firma por dispositivo. No lo expongas sin protección en producción.

## Notas importantes
- Las tablas se crean automáticamente al iniciar la API (`create_all`). Para un sistema en producción se recomienda migrar a Alembic.
- Se insertan las etapas iniciales de cultivo al arrancar.
- Los umbrales no se inventan ni se cargan automáticamente: deben configurarse con valores agronómicos verificados para cada cultivo/etapa.
- La evaluación automática de alertas usa por ahora umbrales generales (`id_etapa` vacío). La selección por etapa y asociación precisa de sensor a cultivo se debe completar cuando se defina qué sensor mide cada cultivo.
- El endpoint `/mediciones` no tiene login de usuario para permitir el envío desde IoT; debe protegerse con una credencial propia del dispositivo antes de producción.
- El resumen del cultivo muestra sensores asociados al sistema; si un sistema tiene varios cultivos, se recomienda añadir una relación explícita sensor-cultivo para atribuir cada lectura sin ambigüedad.
- No hay control de bombas/actuadores en esta primera versión.
