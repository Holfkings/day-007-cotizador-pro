"""CotizadorPro — motor de cotizaciones comerciales.

Paquete publico: ``Cotizador`` (fachada), ``catalogo``, ``clientes`` y
``motor`` (calculo). El acceso a persistencia vive en :mod:`cotizador.db`.
"""

from cotizador.fachada import Cotizador
from cotizador.modelo import (
    Cliente,
    EstadoCotizacion,
    ItemCotizacion,
    Cotizacion,
    Producto,
)

__all__ = [
    "Cotizador",
    "Cliente",
    "Cotizacion",
    "EstadoCotizacion",
    "ItemCotizacion",
    "Producto",
]

__version__ = "1.0.0"