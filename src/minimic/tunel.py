"""El túnel al portero vive en ``tecladoia.tunel`` (lo usan los cuatro teclados).
Este módulo queda para quien importe de aquí."""

from tecladoia.tunel import (  # noqa: F401
    LATIDO_S, ORIGEN_REMOTO, PLAZO_DE_CONEXION_S, REINTENTO_S, Tunel,
    analizar_portero, se_puede_usar_el_origen,
)

__all__ = ["Tunel", "analizar_portero", "se_puede_usar_el_origen"]
