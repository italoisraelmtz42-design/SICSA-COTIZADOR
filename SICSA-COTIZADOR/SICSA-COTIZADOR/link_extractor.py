"""
Intenta extraer nombre, imagen y precio de la página de un producto a partir
de su link. Esto es "best-effort": funciona bien en muchos sitios (los que
usan metadatos estándar Open Graph), pero varios sitios grandes (Amazon,
Mercado Libre, etc.) bloquean este tipo de lectura automática o cambian su
código seguido. Por eso SIEMPRE se debe poder editar el resultado a mano
antes de guardar — nunca confíes ciegamente en lo que regresa esta función.
"""
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

PRECIO_REGEX = re.compile(r"[\$]?\s*([\d]{1,3}(?:[,.]\d{3})*(?:\.\d{1,2})?)")


def _meta(soup, *names):
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def extraer_datos_producto(url, timeout=8):
    """Devuelve un dict con nombre, imagen_url, precio (puede venir en None
    si no se pudo determinar) y un campo 'confiable' indicando si se
    encontraron metadatos explícitos de precio (más confiable) o si se
    intentó adivinar con una expresión regular sobre el texto (poco confiable)."""
    resultado = {
        "nombre": None, "imagen_url": None, "precio": None,
        "confiable": False, "error": None,
    }
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
    except Exception as e:
        resultado["error"] = f"No se pudo abrir el link: {e}"
        return resultado

    soup = BeautifulSoup(r.text, "html.parser")

    resultado["nombre"] = _meta(soup, "og:title", "twitter:title") or (
        soup.title.string.strip() if soup.title and soup.title.string else None
    )
    resultado["imagen_url"] = _meta(soup, "og:image", "twitter:image")

    # Metadatos de precio explícitos (poco comunes pero cuando existen son confiables)
    precio_meta = _meta(
        soup, "product:price:amount", "og:price:amount", "twitter:data1"
    )
    if precio_meta:
        match = PRECIO_REGEX.search(precio_meta.replace(",", ""))
        if match:
            resultado["precio"] = float(match.group(1).replace(",", ""))
            resultado["confiable"] = True

    # Si no hubo metadato explícito, no adivinamos con regex sobre todo el
    # HTML — es demasiado propenso a error (puede agarrar cualquier número).
    # Mejor dejar el precio en None y que el usuario lo capture a mano.

    return resultado
