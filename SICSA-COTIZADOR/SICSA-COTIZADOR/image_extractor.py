"""
Extrae nombre, descripción y precio de una foto de producto (captura de
pantalla, foto tomada con el celular, etc.) usando el modelo de visión de
OpenAI (GPT-4.1-mini). La API key se configura en Render como
OPENAI_API_KEY.

A diferencia de la extracción por link, aquí SÍ podemos confiar más en el
resultado porque un modelo de visión "lee" la imagen igual que lo haría
una persona — pero aun así, el resultado se debe poder editar a mano
antes de guardar, sobre todo cuando la imagen trae varios precios (ej.
normal vs. con descuento vs. meses sin intereses).

También le pedimos al modelo las coordenadas de dónde está el producto
dentro de la imagen, para recortar automáticamente y quedarnos solo con
la foto del producto — no con toda la captura de pantalla (que suele
traer menús, precios de otros productos, botones, etc.).
"""
import os
import json
import base64
from io import BytesIO

MODEL = "gpt-4.1-mini"


def _recortar_imagen(image_bytes, recorte):
    """Recorta la imagen a la zona del producto usando las coordenadas
    (fracciones de 0 a 1) que regresó el modelo. Si algo sale mal o el
    recorte no tiene sentido, regresa None y nos quedamos con la original."""
    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        x0 = float(recorte.get("x0"))
        y0 = float(recorte.get("y0"))
        x1 = float(recorte.get("x1"))
        y1 = float(recorte.get("y1"))
    except (TypeError, ValueError):
        return None

    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        return None

    area = (x1 - x0) * (y1 - y0)
    if area > 0.92:
        return None

    try:
        img = Image.open(BytesIO(image_bytes))
        ancho, alto = img.size
        caja = (
            int(x0 * ancho), int(y0 * alto),
            int(x1 * ancho), int(y1 * alto),
        )
        if caja[2] - caja[0] < 20 or caja[3] - caja[1] < 20:
            return None
        recortada = img.crop(caja)
        formato = (img.format or "PNG")
        buf = BytesIO()
        recortada.save(buf, format=formato)
        return buf.getvalue()
    except Exception:
        return None


def extraer_datos_imagen(image_bytes, media_type="image/png"):
    """Recibe los bytes de una imagen y regresa un dict con nombre,
    descripcion, precio (o None), confiable (bool) y imagen_bytes (los
    bytes ya recortados al producto, o los originales si no se pudo
    recortar). Si falta la API key o algo falla, regresa un mensaje de
    error claro en vez de tronar."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "nombre": None, "descripcion": None, "precio": None,
            "confiable": False, "imagen_bytes": image_bytes,
            "error": "Falta configurar OPENAI_API_KEY en el servidor.",
        }

    try:
        import openai
    except ImportError:
        return {
            "nombre": None, "descripcion": None, "precio": None,
            "confiable": False, "imagen_bytes": image_bytes,
            "error": "Falta instalar la librería 'openai' en el servidor.",
        }

    try:
        client = openai.OpenAI(api_key=api_key)
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        prompt = (
            "Esta imagen es la foto o captura de pantalla de un producto que "
            "se va a cotizar. Extrae la información y responde SOLO con un "
            "objeto JSON válido, sin texto antes ni después, con esta forma "
            "exacta:\n"
            '{"nombre": "nombre corto y claro del producto", '
            '"descripcion": "detalles relevantes: modelo, color, tamaño, etc. o null", '
            '"precio": numero_decimal_o_null, '
            '"confiable": true_o_false, '
            '"recorte": {"x0": num, "y0": num, "x1": num, "y1": num}}\n\n'
            "Reglas para nombre/descripción/precio:\n"
            "- Si la imagen muestra varios precios (normal, tachado, con "
            "descuento, meses sin intereses, por color), usa el precio "
            "principal que se vería primero (normalmente el más grande o "
            "el que está marcado como precio actual/de venta), y pon "
            "\"confiable\": false porque hay ambigüedad.\n"
            "- Si no hay ningún precio visible en la imagen, \"precio\" debe "
            "ser null.\n"
            "- Si el precio es claro y único, pon \"confiable\": true.\n"
            "- No inventes datos que no se vean en la imagen.\n\n"
            "Reglas para \"recorte\" (MUY importantes, léelas con cuidado):\n"
            "El recorte debe contener ÚNICAMENTE el producto físico principal "
            "que se está cotizando — nada más. Antes de dar las coordenadas, "
            "identifica primero los bordes reales del producto (dónde "
            "empieza y dónde termina el objeto en sí) y ajusta la caja lo "
            "más pegada posible a esos bordes, sin margen de sobra.\n"
            "EXCLUYE siempre del recorte, aunque estén muy cerca del "
            "producto:\n"
            "  • Texto, precios, etiquetas, marcas de agua o logotipos "
            "sobrepuestos en la imagen.\n"
            "  • Botones, menús, barras de navegación, iconos o cualquier "
            "elemento de interfaz de la pantalla capturada.\n"
            "  • Otros productos, variantes de color, o miniaturas "
            "adicionales que aparezcan junto al producto principal — elige "
            "solo el más grande o el que esté en primer plano/centrado.\n"
            "  • Fondo, mesa, manos, empaque exterior u otros objetos que "
            "no sean el producto que se vende (a menos que el empaque "
            "mismo sea justo lo que se está cotizando).\n\n"
            "Patrón muy común (páginas de producto tipo tienda en línea): "
            "la foto principal del producto está en un recuadro grande, "
            "normalmente del lado izquierdo de la pantalla, casi siempre "
            "cuadrado o vertical, con una fila de fotos miniatura pequeñas "
            "justo debajo o al lado (esas miniaturas NO se incluyen, son "
            "solo referencia). Del lado derecho suele haber texto: título "
            "del producto, calificación con estrellas, precio, botones de "
            "compra — nada de eso se incluye en el recorte, sin importar "
            "qué tan cerca esté de la foto. Ubica las coordenadas exactas "
            "de ese recuadro grande de la foto principal (sus bordes reales, "
            "no un área aproximada) y usa esas coordenadas.\n\n"
            "Pista clave para diferenciar foto de texto: la foto real del "
            "producto tiene tonos continuos de fotografía — sombras, "
            "reflejos, degradados de color, texturas — como cualquier foto "
            "tomada con cámara. El texto (títulos, precios, reseñas, "
            "características) se ve como letras nítidas y planas sobre "
            "fondo liso, sin sombras ni degradados, aunque a veces ese "
            "bloque de texto parezca visualmente \"cargado\" de detalle. Si "
            "dudas entre dos zonas, la que se vea como una fotografía real "
            "(no como letras) es la correcta — nunca recortes un bloque de "
            "texto por más denso que se vea.\n"
            "Si la imagen ya es una foto de producto limpia (fondo blanco, "
            "sin nada más alrededor), usa x0:0, y0:0, x1:1, y1:1. Si la "
            "imagen es una captura de pantalla con mucho contenido "
            "alrededor, el recorte normalmente debe ser una fracción "
            "pequeña del total — no tengas miedo de recortar agresivo."
        )

        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=350,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_b64}",
                            "detail": "high",
                        },
                    },
                ],
            }],
        )

        texto = response.choices[0].message.content.strip()
        texto = texto.replace("```json", "").replace("```", "").strip()
        datos = json.loads(texto)

        imagen_final = image_bytes
        recorte = datos.get("recorte")
        if isinstance(recorte, dict):
            recortada = _recortar_imagen(image_bytes, recorte)
            if recortada:
                imagen_final = recortada

        return {
            "nombre": datos.get("nombre"),
            "descripcion": datos.get("descripcion"),
            "precio": datos.get("precio"),
            "confiable": bool(datos.get("confiable", False)),
            "imagen_bytes": imagen_final,
            "error": None,
        }
    except json.JSONDecodeError:
        return {
            "nombre": None, "descripcion": None, "precio": None,
            "confiable": False, "imagen_bytes": image_bytes,
            "error": "No se pudo interpretar la respuesta del modelo. Captura los datos a mano.",
        }
    except Exception as e:
        return {
            "nombre": None, "descripcion": None, "precio": None,
            "confiable": False, "imagen_bytes": image_bytes,
            "error": f"Error al analizar la imagen: {e}",
        }
