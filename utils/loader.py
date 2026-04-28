import csv
import os
from typing import Callable, Dict, List, Optional, Tuple


AirportRecord = Dict[str, object]    # {'code','name','city','country','lat','lon'}
RouteRecord   = Tuple[str, str, int] # (src_code, dst_code, frequency)


def load_flights(
    csv_path: str,
    progress_cb: Optional[Callable[[str, float], None]] = None,
) -> Tuple[List[AirportRecord], List[RouteRecord]]:
    # Lee el CSV en una sola pasada y retorna aeropuertos únicos + rutas deduplicadas

    def _cb(msg: str, pct: float):
        if progress_cb:
            progress_cb(msg, pct)

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"No se encontró el archivo: {csv_path}")

    # Contar filas primero para poder calcular el porcentaje de progreso
    _cb("Contando registros…", 0.02)
    with open(csv_path, encoding='utf-8', errors='replace') as f:
        total_rows = sum(1 for _ in f) - 1  # restar cabecera
    total_rows = max(total_rows, 1)

    _cb(f"Leyendo {total_rows:,} registros…", 0.05)

    airports_dict: Dict[str, AirportRecord]      = {}
    route_freq   : Dict[Tuple[str, str], int]    = {}

    # Reportar progreso ~20 veces durante la lectura sin saturar la cola
    report_every = max(1, total_rows // 20)

    with open(csv_path, newline='', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):

            if i % report_every == 0:
                pct = 0.05 + 0.80 * (i / total_rows)
                _cb(f"Procesando fila {i:,} / {total_rows:,}…", pct)

            src_code = row.get('Source Airport Code', '').strip()
            dst_code = row.get('Destination Airport Code', '').strip()

            # Saltar registros inválidos o auto-loops
            if not src_code or not dst_code or src_code == dst_code:
                continue

            # Registrar aeropuerto origen si no se ha visto antes
            if src_code not in airports_dict:
                try:
                    airports_dict[src_code] = {
                        'code'   : src_code,
                        'name'   : row['Source Airport Name'].strip(),
                        'city'   : row['Source Airport City'].strip(),
                        'country': row['Source Airport Country'].strip(),
                        'lat'    : float(row['Source Airport Latitude']),
                        'lon'    : float(row['Source Airport Longitude']),
                    }
                except (ValueError, KeyError):
                    continue

            # Registrar aeropuerto destino si no se ha visto antes
            if dst_code not in airports_dict:
                try:
                    airports_dict[dst_code] = {
                        'code'   : dst_code,
                        'name'   : row['Destination Airport Name'].strip(),
                        'city'   : row['Destination Airport City'].strip(),
                        'country': row['Destination Airport Country'].strip(),
                        'lat'    : float(row['Destination Airport Latitude']),
                        'lon'    : float(row['Destination Airport Longitude']),
                    }
                except (ValueError, KeyError):
                    continue

            # Clave canónica (par ordenado) para deduplicar rutas en O(1)
            key = (src_code, dst_code) if src_code < dst_code else (dst_code, src_code)
            route_freq[key] = route_freq.get(key, 0) + 1

    _cb("Construyendo listas de salida…", 0.88)

    airports: List[AirportRecord] = list(airports_dict.values())
    routes  : List[RouteRecord]   = [
        (a, b, freq)
        for (a, b), freq in route_freq.items()
        if a in airports_dict and b in airports_dict
    ]

    _cb("Carga completada.", 1.0)
    print(f"[Loader] Aeropuertos únicos : {len(airports):,}")
    print(f"[Loader] Rutas únicas       : {len(routes):,}")

    return airports, routes