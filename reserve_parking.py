#!/usr/bin/env python3
"""
Automatiza la reserva de parqueo en Corporate Experience.

Logica:
- Las reservas se habilitan cada dia a las 6am, un dia a la vez, para la
  fecha que cae exactamente 7 dias despues.
- Este script esta pensado para correr TODOS los dias a las 6:05am (via
  GitHub Actions / cron / Task Scheduler). Cada vez que corre, calcula
  la fecha que se acaba de habilitar (hoy + 7 dias) y, SOLO SI esa
  fecha es jueves o viernes:
    1. Hace login.
    2. Consulta disponibilidad real de espacios para esa fecha.
    3. Prueba, EN ORDEN DE PRIORIDAD, los parking lots preferidos y
       reserva en el primero que tenga cupo disponible.
- Si la fecha habilitada no es jueves/viernes, o si ninguno de los
  parking lots preferidos tiene cupo, no reserva nada (y lo deja
  registrado en el log).

Credenciales: se leen de variables de entorno (nunca quedan en este
archivo). Ver .env.example / Secrets de GitHub Actions.
"""

import os
import sys
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

# Dias de la semana en los que queres reservar (0=lunes ... 6=domingo)
# 3 = jueves, 4 = viernes
DIAS_DESEADOS = {2, 3, 4}

# Parking lots preferidos, EN ORDEN DE PRIORIDAD. El script prueba el
# primero; si no tiene cupo, prueba el siguiente, y asi sucesivamente.
PRIORITY_LOT_IDS = [2, 10, 9]

VEHICLE_ID = 16597
REASON = "Jornada Laboral"
HORA_ENTRADA = "08:00:00"       # hora de entrada que se manda en la reserva
HORA_ENTRADA_CORTA = "08:00"    # mismo valor pero formato HH:MM para el chequeo de disponibilidad

# Dias de anticipacion con los que se habilita cada reserva
DIAS_ANTICIPACION = 7

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
    """Hace login y devuelve los headers de autenticacion (access-token,
    client, uid) que hay que reenviar en las siguientes peticiones."""
    email = os.environ.get("CORP_EMAIL")
    password = os.environ.get("CORP_PASSWORD")

    if not email or not password:
        log.error("Faltan las variables de entorno CORP_EMAIL y/o CORP_PASSWORD.")
        sys.exit(1)

    resp = requests.post(LOGIN_URL, json={"email": email, "password": password})
    resp.raise_for_status()

    auth_headers = {
        "access-token": resp.headers["access-token"],
        "client": resp.headers["client"],
        "uid": resp.headers["uid"],
        "token-type": resp.headers.get("token-type", "Bearer"),
    }
    log.info("Login exitoso.")
    return auth_headers


def consultar_disponibilidad(auth_headers, fecha):
    """Consulta disponibilidad real para la fecha dada y devuelve una lista
    de dicts {parking_lot_id, name, total} para esa fecha."""
    fecha_str = fecha.strftime("%Y-%m-%d")
    fecha_iso = f"{fecha_str}T00:00:00.000Z"

    params = {
        "start_date": fecha_iso,
        "end_date": fecha_iso,
        "entry_time": HORA_ENTRADA_CORTA,
    }

    resp = requests.get(AVAILABILITY_URL, params=params, headers=auth_headers)
    resp.raise_for_status()
    data = resp.json()

    if not data.get("success") or not data.get("availables"):
        log.warning(f"Respuesta de disponibilidad inesperada: {data}")
        return []

    # La respuesta viene como una lista con un elemento por fecha consultada.
    dia = data["availables"][0]
    return dia.get("availability", [])


def elegir_lot_disponible(disponibilidad):
    """Recorre PRIORITY_LOT_IDS en orden y devuelve el primer
    parking_lot_id que tenga cupo (total > 0). Devuelve None si ninguno
    tiene cupo."""
    disponibilidad_por_id = {d["parking_lot_id"]: d for d in disponibilidad}

    for lot_id in PRIORITY_LOT_IDS:
        info = disponibilidad_por_id.get(lot_id)
        if info is None:
            log.warning(f"Parking lot {lot_id} no aparece en la respuesta de disponibilidad.")
            continue
        if info.get("total", 0) > 0:
            log.info(f"Cupo disponible en lot {lot_id} ({info.get('name')}): {info['total']} espacios.")
            return lot_id
        else:
            log.info(f"Sin cupo en lot {lot_id} ({info.get('name')}).")

    return None


def reservar(auth_headers, fecha, parking_lot_id):
    """Reserva el parqueo para la fecha dada en el parking_lot_id indicado."""
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

    if resp.ok:
        log.info(f"Reserva exitosa para {fecha_str} en lot {parking_lot_id}. Respuesta: {resp.text}")
    else:
        log.error(
            f"Fallo la reserva para {fecha_str} en lot {parking_lot_id}. "
            f"Status: {resp.status_code}. Respuesta: {resp.text}"
        )
        resp.raise_for_status()


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

    log.info(f"La fecha {fecha_objetivo} SI es un dia deseado. Verificando disponibilidad...")
    auth_headers = login()

    disponibilidad = consultar_disponibilidad(auth_headers, fecha_objetivo)
    if not disponibilidad:
        log.error("No se pudo obtener informacion de disponibilidad. No se reserva nada.")
        return

    lot_elegido = elegir_lot_disponible(disponibilidad)

    if lot_elegido is None:
        log.warning(
            f"Ninguno de los parking lots preferidos {PRIORITY_LOT_IDS} "
            f"tiene cupo para {fecha_objetivo}. No se reserva nada."
        )
        return

    reservar(auth_headers, fecha_objetivo, lot_elegido)


if __name__ == "__main__":
    main()
