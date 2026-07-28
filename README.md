# Automatización de reserva de parqueo — Corporate Experience

Este script hace login en la app y reserva el parqueo automáticamente,
todos los días, **solo si la fecha que se acaba de habilitar (hoy + 7
días) cae jueves o viernes**. Corre en GitHub Actions, así que no
depende de que tu computadora esté encendida.

## 1. Crear el repositorio

1. Entrá a GitHub con tu cuenta personal → "New repository"
2. Nombre: el que quieras (ej. `parqueo-auto`)
3. **Visibilidad: Private** (importante — este repo va a manejar tus
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
3. Hacé clic en **Run workflow** (botón a la derecha) para probarlo ya
   mismo, sin esperar al cron
4. Revisá el resultado en los logs de esa ejecución. Si algo falla, el
   log del script queda también disponible como "artifact" descargable
   al final de la ejecución.

**Importante:** si hoy + 7 días no cae jueves ni viernes, el script no
va a reservar nada — vas a ver un mensaje diciendo eso en el log, y
eso es lo esperado, no un error.

## 5. Cómo funciona la programación automática

El archivo `.github/workflows/reserve_parking.yml` ya tiene el cron
configurado para correr todos los días a las **6:05am hora de Costa
Rica** (12:05 UTC). No hay que hacer nada más — mientras el repo
exista y los Secrets estén configurados, corre solo.

**Nota sobre GitHub Actions:** los horarios de `cron` en GitHub
Actions son "mejor esfuerzo" — en momentos de mucha carga en GitHub
puede haber un par de minutos de retraso. Si los cupos de parqueo son
muy limitados y esto te preocupa, avisame y podemos explorar
alternativas (por ejemplo correr cada minuto entre 6:05 y 6:10 como
red de seguridad).

## 6. Mantenimiento

- Si cambiás de carro, actualizá `VEHICLE_ID` en `reserve_parking.py`,
  hacé commit y push.
- Si cambia el lugar/lote de parqueo, actualizá `PARKING_LOT_ID` igual.
- Si la contraseña de Corporate Experience cambia, actualizá el Secret
  `CORP_PASSWORD` en GitHub (Settings → Secrets → Actions).
- Podés revisar el historial de ejecuciones en la pestaña **Actions**
  del repo en cualquier momento.
