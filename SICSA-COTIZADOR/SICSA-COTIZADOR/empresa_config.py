# =====================================================================
#  CONFIGURACIÓN DE LA EMPRESA
#  Todo lo que cambia de una empresa a otra vive en este archivo:
#  datos fiscales, folio, usuarios, logos y colores. Para hacer otra
#  copia del cotizador para una empresa distinta, basta con cambiar
#  este archivo y los logos en static/img/.
# =====================================================================

# ---------- Datos que salen impresos en el PDF ----------
EMPRESA = {
    "nombre": "SICSA",                                       # nombre corto (pantallas, notas)
    "razon_social": "SERVICIO INDUSTRIAL DE COMEDORES SA DE CV",  # encabezado del PDF
    "responsable": "",          # opcional: si se llena, sale junto al RFC en el PDF
    "rfc": "SIC701029BL4",
    "direccion": "General Treviño Ote. 629/B, Monterrey Centro, CP 64000, Monterrey, N.L.",
    "vendedor_default": "SICSA",
}

# ---------- Folio de cotización ----------
# Quedan como SIC-0001, SIC-0002...
FOLIO_PREFIJO = "SIC-"
FOLIO_INICIAL = 1        # número de la primera cotización
FOLIO_DIGITOS = 4        # 4 -> 0001

# ---------- Base de datos ----------
NOMBRE_BD = "sicsa_cotizador.db"

# ---------- Usuarios ----------
# Cada usuario entra con su propia contraseña. La contraseña real NO se
# escribe aquí: se configura en Render como variable de entorno con el
# nombre indicado en "env_var".
#   saludo: "Bienvenido" o "Bienvenida"
USUARIOS = [
    {"nombre": "Juan Antonio", "env_var": "PASSWORD_JOSE", "saludo": "Bienvenido"},
    {"nombre": "Elías Ruiz", "env_var": "PASSWORD_ELIAS", "saludo": "Bienvenido"},
]

# ---------- Logos (archivos dentro de static/img/) ----------
LOGO_COMPLETO = "logo_sicsa.png"   # logo horizontal: PDF y pantalla de entrada
LOGO_ICONO = "icono_chef.png"      # versión cuadrada: encabezado de la app

# ---------- Colores ----------
COLORES = {
    "principal": "#67838E",         # gris azulado de las letras SICS
    "principal_oscuro": "#3E525A",  # textos fuertes, encabezado de tabla del PDF
    "acento": "#DE232A",            # rojo de la A
    "acento_oscuro": "#B81C22",     # rojo al pasar el mouse por los botones
    "texto_suave": "#5B6B72",
    "fondo_claro": "#F3F6F7",
    "fondo_alterno": "#F7F9FA",
    "borde": "#E1E7EA",
    "gris_tenue": "#8C9AA0",
}
