#!/usr/bin/env python3
"""
Automatiza la reserva de parqueo en Corporate Experience.

Logica:
- Las reservas se habilitan cada dia a las 6am, un dia a la vez, para la
  fecha que cae exactamente 7 dias despues.
- Este script arranca a las 5:55am (disparado por cron-job.org via la
  API de GitHub) y REINTENTA cada cierto tiempo hasta las 6:05am (10
  minutos de ventana).
- Cada intento:
    1. Verifica si YA existe una reserva APROBADA para la fecha
       objetivo (chequeando /api/reservations). Si ya existe, termina
       exitosamente sin hacer nada mas.
    2. Si no existe, consulta disponibilidad real y elige, en orden de
       prioridad, el primer parking lot preferido que tenga cupo.
    3. Hace el POST de la reserva. OJO: la API a veces responde
       success:true aunque el cupo ya lo haya tomado otro usuario
       (race condition) - por eso, despues del POST, se vuelve a
       consultar /api/reservations para CONFIRMAR que la reserva
       realmente quedo creada para esa fecha. Si no se confirma, se
       trata como fallo y se reintenta.
- Sigue reintentando hasta que:
    a) se confirme una reserva real, o
    b) ya no quede cupo en NINGUN parking lot preferido, o
    c) se acabe la ventana de tiempo de reintentos.
- Si la fecha que se habilita (hoy + 7 dias) no es un dia deseado, no
  hace nada.

Credenciales: se leen de variables de entorno (nunca quedan en este
archivo). Ver README.md / Secrets de GitHub Actions.
"""

import os
import sys
import time
import logging
from datetime import datetime, timedelta

import requests

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------

BASE_URL = "https://baclatam.corporateparking.parso.cr/api"
LOGIN_URL = f"{BASE_URL}/auth/sign_in"
RESERVE_URL = f"{BASE_URL}/parking_reservations/multiples"
AVAILABILITY_URL = f"{BASE_URL}/parking_spaces/availability"
RESERVATIONS_URL = f"{BASE_URL}/reservations"

# Dias de la semana en los que queres reservar (0=lunes ... 6=domingo)
# 3 = jueves, 4 = viernes
DIAS_DESEADOS = {2, 3}

# Parking lots preferidos, EN ORDEN DE PRIORIDAD.
PRIORITY_LOT_IDS = [2, 10, 9, 3]

VEHICLE_ID = 16597
REASON = "Jornada Laboral"
HORA_ENTRADA = "08:00:00"       # hora de entrada que se manda en la reserva
HORA_ENTRADA_CORTA = "08:00"    # mismo valor pero formato HH:MM

# Dias de anticipacion con los que se habilita cada reserva
DIAS_ANTICIPACION = 7

# --- Configuracion de reintentos ---
MINUTOS_MAX_REINTENTO = 2
SEGUNDOS_ENTRE_INTENTOS = 30   # espera cuando NO hay cupo en ningun lot
SEGUNDOS_ESPERA_CONFIRMACION = 60  # espera despues del POST antes de verificar

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reserve_parking.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Funciones
# ---------------------------------------------------------------------------

def login():
    email = os.environ.get("CORP_EMAIL")
    password = os.environ.get("CORP_PASSWORD")

    if not email or not password:
        log.error("Faltan las variables de entorno CORP_EMAIL y/o CORP_PASSWORD.")
        sys.exit(1)

    resp = requests.post(LOGIN_URL, json={"email": email, "password": password})
    resp.raise_for_status()

    auth_headers = extraer_tokens(resp)
    log.info("Login exitoso.")
    return auth_headers


def extraer_tokens(resp):
    return {
        "access-token": resp.headers.get("access-token"),
        "client": resp.headers.get("client"),
        "uid": resp.headers.get("uid"),
        "token-type": resp.headers.get("token-type", "Bearer"),
    }


def actualizar_tokens(auth_headers, resp):
    nuevos = extraer_tokens(resp)
    if nuevos["access-token"] and nuevos["client"] and nuevos["uid"]:
        auth_headers.update(nuevos)


def consultar_disponibilidad(auth_headers, fecha):
    fecha_str = fecha.strftime("%Y-%m-%d")
    fecha_iso = f"{fecha_str}T00:00:00.000Z"

    params = {
        "start_date": fecha_iso,
        "end_date": fecha_iso,
        "entry_time": HORA_ENTRADA_CORTA,
    }

    resp = requests.get(AVAILABILITY_URL, params=params, headers=auth_headers)
    resp.raise_for_status()
    actualizar_tokens(auth_headers, resp)
    data = resp.json()

    if not data.get("success") or not data.get("availables"):
        log.warning(f"Respuesta de disponibilidad inesperada: {data}")
        return []

    dia = data["availables"][0]
    return dia.get("availability", [])


def elegir_lot_disponible(disponibilidad):
    disponibilidad_por_id = {d["parking_lot_id"]: d for d in disponibilidad}

    for lot_id in PRIORITY_LOT_IDS:
        info = disponibilidad_por_id.get(lot_id)
        if info is None:
            continue
        if info.get("total", 0) > 0:
            log.info(f"Cupo disponible en lot {lot_id} ({info.get('name')}): {info['total']} espacios.")
            return lot_id
        else:
            log.info(f"Sin cupo en lot {lot_id} ({info.get('name')}).")

    return None


def buscar_reserva_confirmada(auth_headers, fecha):
    """Consulta /api/reservations y busca una reserva APROBADA cuyo
    entry_time caiga en la fecha objetivo, para el vehiculo configurado.
    Devuelve el dict de la reserva si la encuentra, o None."""
    fecha_str = fecha.strftime("%Y-%m-%d")

    resp = requests.get(RESERVATIONS_URL, headers=auth_headers)
    resp.raise_for_status()
    actualizar_tokens(auth_headers, resp)
    data = resp.json()

    if not data.get("success"):
        log.warning(f"Respuesta de /reservations inesperada: {data}")
        return None

    for reserva in data.get("reservations", []):
        entry_time = reserva.get("entry_time", "")
        entry_fecha = entry_time[:10]  # "YYYY-MM-DD"
        vehicle_id = reserva.get("vehicle", {}).get("id")
        estado = reserva.get("status")

        if entry_fecha == fecha_str and vehicle_id == VEHICLE_ID and estado == "APPROVED":
            return reserva

    return None


def reservar(auth_headers, fecha, parking_lot_id):
    """Envia el POST de reserva. Devuelve True/False segun el status
    HTTP, pero OJO: un True aqui NO garantiza que el cupo haya quedado
    realmente asignado (ver buscar_reserva_confirmada)."""
    fecha_str = fecha.strftime("%Y-%m-%d")
    entry_time = f"{fecha_str}T{HORA_ENTRADA}.000"

    payload = {
        "parking_reservation": {
            "parking_lot_id": parking_lot_id,
            "reason": REASON,
            "vehicle_id": VEHICLE_ID,
            "entry_time": entry_time,
        },
        "dates": [fecha_str],
    }

    resp = requests.post(RESERVE_URL, json=payload, headers=auth_headers)
    actualizar_tokens(auth_headers, resp)

    if resp.ok:
        log.info(f"POST de reserva respondio OK para lot {parking_lot_id}. Respuesta: {resp.text}")
        return True
    else:
        log.warning(
            f"POST de reserva fallo (HTTP) para lot {parking_lot_id}. "
            f"Status: {resp.status_code}. Respuesta: {resp.text}"
        )
        return False


def intentar_reservar_con_reintentos(auth_headers, fecha_objetivo):
    inicio = datetime.now()
    limite = inicio + timedelta(minutes=MINUTOS_MAX_REINTENTO)
    intento = 0

    while datetime.now() < limite:
        intento += 1
        log.info(f"--- Intento #{intento} ---")

        # 0. Por si ya quedo reservado en un intento anterior (o por otra via)
        try:
            ya_reservado = buscar_reserva_confirmada(auth_headers, fecha_objetivo)
        except requests.RequestException as e:
            log.warning(f"Error consultando /reservations: {e}")
            ya_reservado = None

        if ya_reservado:
            espacio = ya_reservado.get("parking_space", {}).get("parking_space_label")
            lot_nombre = ya_reservado.get("parking_lot", {}).get("name")
            log.info(
                f"Reserva CONFIRMADA para {fecha_objetivo}: lot '{lot_nombre}', "
                f"espacio '{espacio}' (id reserva {ya_reservado.get('id')})."
            )
            return True

        # 1. Ver disponibilidad y elegir lot
        try:
            disponibilidad = consultar_disponibilidad(auth_headers, fecha_objetivo)
        except requests.RequestException as e:
            log.warning(f"Error consultando disponibilidad: {e}")
            disponibilidad = []

        lot_elegido = elegir_lot_disponible(disponibilidad) if disponibilidad else None

        if lot_elegido is None:
            log.warning(
                "Sin cupo disponible en ningun lot preferido "
                f"{PRIORITY_LOT_IDS}. No tiene sentido seguir reintentando "
                "ahora mismo, se detiene el script."
            )
            return False

        # 2. Intentar reservar
        try:
            reservar(auth_headers, fecha_objetivo, lot_elegido)
        except requests.RequestException as e:
            log.warning(f"Error en el POST de reserva: {e}")
            time.sleep(SEGUNDOS_ENTRE_INTENTOS)
            continue

        # 3. Esperar un poco y CONFIRMAR contra /reservations (el POST
        #    puede decir success aunque el cupo ya lo tomo otro).
        time.sleep(SEGUNDOS_ESPERA_CONFIRMACION)

        try:
            confirmada = buscar_reserva_confirmada(auth_headers, fecha_objetivo)
        except requests.RequestException as e:
            log.warning(f"Error confirmando la reserva: {e}")
            confirmada = None

        if confirmada:
            espacio = confirmada.get("parking_space", {}).get("parking_space_label")
            lot_nombre = confirmada.get("parking_lot", {}).get("name")
            log.info(
                f"Reserva CONFIRMADA para {fecha_objetivo}: lot '{lot_nombre}', "
                f"espacio '{espacio}' (id reserva {confirmada.get('id')})."
            )
            return True
        else:
            log.warning(
                f"El POST respondio success pero NO se confirmo la reserva "
                f"en lot {lot_elegido} (probablemente el cupo lo tomo otro "
                f"usuario primero). Reintentando..."
            )
            # No dormimos de mas aqui: ya esperamos SEGUNDOS_ESPERA_CONFIRMACION.
            # Volvemos directo a chequear disponibilidad fresca.

    return False


def main():
    hoy = datetime.now().date()
    fecha_objetivo = hoy + timedelta(days=DIAS_ANTICIPACION)

    dia_semana = fecha_objetivo.weekday()  # 0=lunes ... 6=domingo

    if dia_semana not in DIAS_DESEADOS:
        log.info(
            f"La fecha que se habilita hoy ({fecha_objetivo}) no es "
            f"jueves/viernes (dia {dia_semana}). No se hace nada."
        )
        return

    log.info(
        f"La fecha {fecha_objetivo} SI es un dia deseado. "
        f"Reintentando hasta por {MINUTOS_MAX_REINTENTO} minutos..."
    )
    auth_headers = login()

    exito = intentar_reservar_con_reintentos(auth_headers, fecha_objetivo)

    if not exito:
        log.error(
            f"No se logro CONFIRMAR una reserva para {fecha_objetivo} en "
            f"ninguno de los lots preferidos {PRIORITY_LOT_IDS} dentro de "
            f"la ventana de {MINUTOS_MAX_REINTENTO} minutos."
        )


if __name__ == "__main__":
    main()
