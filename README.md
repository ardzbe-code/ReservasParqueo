# Automatización de reserva de parqueo — Corporate Experience

Este script hace login en la app y reserva el parqueo automáticamente,
todos los días, **solo si la fecha que se acaba de habilitar (hoy + 7
días) cae jueves o viernes**. Corre en GitHub Actions (disparado por un
cron externo), así que no depende de que tu computadora esté encendida.

## 1. Crear el repositorio

1. Entrá a GitHub con tu cuenta personal → "New repository"
2. Nombre: el que quieras (ej. `parqueo-auto`)
3. **Visibilidad: Private** (importante — este repo maneja tus
   credenciales indirectamente vía Secrets, y aunque los Secrets están
   cifrados, es buena práctica mantener el repo privado)
4. Creá el repo (no hace falta agregar README/gitignore, ya los tenemos)

## 2. Subir los archivos

En tu compu, dentro de la carpeta con estos archivos:

```bash
git init
git add reserve_parking.py requirements.txt README.md .github
git commit -m "Automatización de reserva de parqueo"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
git push -u origin main
```

(Reemplazá `TU_USUARIO/TU_REPO` por los datos reales de tu repo.)

**Nota:** el archivo `.env.example` es solo una plantilla de ejemplo —
no hace falta subirlo, y **nunca** subas un archivo `.env` real con tu
contraseña de verdad a GitHub. Las credenciales reales van en
"Secrets" (paso siguiente), no en ningún archivo del repo.

## 3. Configurar tus credenciales como "Secrets"

1. En tu repo en GitHub: **Settings → Secrets and variables →
   Actions → New repository secret**
2. Creá dos secrets:
   - `CORP_EMAIL` → tu correo de Corporate Experience
   - `CORP_PASSWORD` → tu contraseña de Corporate Experience

Estos quedan cifrados por GitHub, nunca son visibles (ni para vos
mismo) una vez guardados, y no aparecen en los logs.

## 4. Probarlo manualmente

1. En tu repo, andá a la pestaña **Actions**
2. Seleccioná el workflow "Reservar parqueo"
3. Hacé clic en **Run workflow** (botón a la derecha) para probarlo
4. Revisá el resultado en los logs de esa ejecución. Si algo falla, el
   log del script queda también disponible como "artifact" descargable
   al final de la ejecución.

**Importante:** si hoy + 7 días no cae jueves ni viernes, el script no
va a reservar nada — vas a ver un mensaje diciendo eso en el log, y
eso es lo esperado, no un error.

## 5. Cómo funciona la programación automática (cron-job.org)

**Nota histórica:** originalmente este workflow usaba el trigger nativo
`schedule` (cron) de GitHub Actions, pero en la práctica nunca disparó
de forma automática, incluso probando distintos horarios y con margen
de sobra. Por eso el disparo automático se movió a un servicio externo,
**cron-job.org**, que llama a la API de GitHub para ejecutar el
workflow todos los días a la hora exacta. El archivo
`.github/workflows/reserve_parking.yml` ya no tiene ningún trigger
`schedule` — solo `workflow_dispatch`, que es el que usa tanto el botón
manual como la llamada de la API.

### 5.1 Crear un Personal Access Token en GitHub

1. `github.com` → foto de perfil → **Settings**
2. Al final del menú izquierdo → **Developer settings**
3. **Personal access tokens → Fine-grained tokens → Generate new token**
4. Configuración:
   - **Repository access:** "Only select repositories" → elegí este repo
   - **Permissions → Actions:** **Read and write**
   - **Expiration:** la que prefieras (recordá renovarlo antes de que
     expire, o no vas a poder disparar el workflow hasta que generes
     uno nuevo)
5. Generá el token y guardalo en un lugar seguro (un gestor de
   contraseñas). GitHub solo lo muestra una vez.

### 5.2 Configurar el cronjob en cron-job.org

1. Creá una cuenta gratis en **cron-job.org** y hacé clic en
   **"Create cronjob"**.
2. **Title:** `Reservar parqueo`
3. **URL:**
   ```
   https://api.github.com/repos/TU_USUARIO/TU_REPO/actions/workflows/reserve_parking.yml/dispatches
   ```
4. **Schedule:** todos los días a las **5:55am hora de Costa Rica**
   (buscá el selector de zona horaria y poné `America/Costa_Rica`; si
   no está disponible, usá el equivalente en UTC: 11:55 UTC).
5. **Request method:** `POST`
6. **Headers:**
   ```
   Authorization: Bearer TU_TOKEN_AQUI
   Accept: application/vnd.github+json
   X-GitHub-Api-Version: 2022-11-28
   ```
7. **Body (JSON):**
   ```json
   {"ref":"main"}
   ```
8. **Content-Type:** `application/json`
9. Guardá y probá con el botón de **"Test run"** / **"Execute now"**
   del propio cron-job.org. Un `POST` exitoso responde **204 No
   Content** (eso es éxito, no un error). Un 401 indica problema con
   el token; un 404 indica que el nombre del repo o del archivo `.yml`
   no coincide exactamente.

### 5.3 Mantenimiento de esta parte

- Si el **Personal Access Token expira**, hay que generar uno nuevo y
  actualizar el header `Authorization` en cron-job.org.
- Si cambiás el **nombre del repo** o lo movés a otra cuenta, hay que
  actualizar la URL en cron-job.org.
- Podés revisar el historial de ejecuciones de cron-job.org desde su
  propio panel, y el resultado real de cada corrida en la pestaña
  **Actions** de GitHub (deberían aparecer como disparadas por API, no
  como "Manually run").

## 6. Mantenimiento general

- Si cambiás de carro, actualizá `VEHICLE_ID` en `reserve_parking.py`,
  hacé commit y push.
- Si cambia el lugar/lote de parqueo o el orden de prioridad, actualizá
  `PRIORITY_LOT_IDS` igual.
- Si la contraseña de Corporate Experience cambia, actualizá el Secret
  `CORP_PASSWORD` en GitHub (Settings → Secrets → Actions).
- Podés revisar el historial de ejecuciones en la pestaña **Actions**
  del repo en cualquier momento.
