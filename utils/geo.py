import math


# Radio medio de la Tierra en kilómetros (valor estándar WGS-84 simplificado)
EARTH_RADIUS_KM = 6371.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Calcula la distancia del arco de gran círculo entre dos puntos geográficos
    phi1    = math.radians(lat1)
    phi2    = math.radians(lat2)
    d_phi   = math.radians(lat2 - lat1)
    d_lamba = math.radians(lon2 - lon1)

    # Término central de Haversine; a → 0 cuando los puntos coinciden
    a = (math.sin(d_phi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(d_lamba / 2) ** 2)

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_KM * c


def lat_lon_to_pixel(lat: float, lon: float,
                     canvas_w: int, canvas_h: int,
                     margin: int = 20) -> tuple[float, float]:
    # Proyección Mercator simplificada: convierte grados a píxeles del lienzo
    usable_w = canvas_w - 2 * margin
    usable_h = canvas_h - 2 * margin

    # Longitud → X lineal en [-180, 180]
    x = margin + (lon + 180.0) / 360.0 * usable_w

    # Latitud → Y usando la fórmula de Mercator; latitudes extremas se recortan a ±85.05°
    lat_rad   = math.radians(lat)
    mercator_y = math.log(math.tan(math.pi / 4 + lat_rad / 2))
    max_merc  = math.log(math.tan(math.pi / 4 + math.radians(85.05) / 2))
    y = margin + (1 - (mercator_y + max_merc) / (2 * max_merc)) * usable_h

    return x, y


def pixel_to_lat_lon(px: float, py: float,
                     canvas_w: int, canvas_h: int,
                     margin: int = 20) -> tuple[float, float]:
    # Inversa de lat_lon_to_pixel; útil para convertir clics del usuario a coordenadas
    usable_w = canvas_w - 2 * margin
    usable_h = canvas_h - 2 * margin

    lon = ((px - margin) / usable_w) * 360.0 - 180.0

    max_merc  = math.log(math.tan(math.pi / 4 + math.radians(85.05) / 2))
    mercator_y = max_merc - ((py - margin) / usable_h) * 2 * max_merc
    lat = math.degrees(2 * math.atan(math.exp(mercator_y)) - math.pi / 2)

    return lat, lon
