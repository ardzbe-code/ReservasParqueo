#!/usr/bin/env python3
"""
Automatiza la reserva de parqueo en Corporate Experience.

Lógica:
- Las reservas se habilitan cada día a las 6am, un día a la vez, para la
  fecha que cae exactamente 7 días después.
- Este script está pensado para correr TODOS los días a las 6:05am (via
  cron / Task Scheduler). Cada vez que corre, calcula la fecha que se
  acaba de habilitar (hoy + 7 días) y, SOLO SI esa fecha es jueves o
  viernes, hace login y reserva el parqueo para ese día.
- Si la fecha habilitada no es jueves/viernes, no hace nada.

Credenciales: se leen de variables de entorno (nunca quedan en este
archivo). Ver .env.example para el formato, y README.md para cómo
cargarlas antes de correr el script.
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta

import requests

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

BASE_URL = "https://baclatam.corporateparking.parso.cr/api"
LOGIN_URL = f"{BASE_URL}/auth/sign_in"
RESERVE_URL = f"{BASE_URL}/parking_reservations/multiples"

# Días de la semana en los que querés reservar (0=lunes ... 6=domingo)
# 3 = jueves, 4 = viernes
DIAS_DESEADOS = {1, 3, 4}

# Datos específicos de tu cuenta/vehículo/lote.
# Si alguno cambia (cambiaste de carro, de lote, etc.) actualizalos acá.
PARKING_LOT_ID = 2
VEHICLE_ID = 16597
REASON = "Jornada Laboral"
HORA_ENTRADA = "08:00:00"  # hora de entrada que se manda en cada reserva

# Días de anticipación con los que se habilita cada reserva
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
    """Hace login y devuelve los headers de autenticación (access-token,
    client, uid) que hay que reenviar en la siguiente petición."""
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


def reservar(auth_headers, fecha):
    """Reserva el parqueo para la fecha dada (objeto date)."""
    fecha_str = fecha.strftime("%Y-%m-%d")
    entry_time = f"{fecha_str}T{HORA_ENTRADA}.000"

    payload = {
        "parking_reservation": {
            "parking_lot_id": PARKING_LOT_ID,
            "reason": REASON,
            "vehicle_id": VEHICLE_ID,
            "entry_time": entry_time,
        },
        "dates": [fecha_str],
    }

    resp = requests.post(RESERVE_URL, json=payload, headers=auth_headers)

    if resp.ok:
        log.info(f"Reserva exitosa para {fecha_str}. Respuesta: {resp.text}")
    else:
        log.error(
            f"Falló la reserva para {fecha_str}. "
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
            f"jueves/viernes (día {dia_semana}). No se hace nada."
        )
        return

    log.info(f"La fecha {fecha_objetivo} SÍ es un día deseado. Reservando...")
    auth_headers = login()
    reservar(auth_headers, fecha_objetivo)


if __name__ == "__main__":
    main()
