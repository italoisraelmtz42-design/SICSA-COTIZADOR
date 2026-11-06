"""
Generador de PDF de documentos — diseño de SICSA (basado en el de N|B).

generar_pdf_documento() dibuja el diseño completo (encabezado con logo,
badge de folio, tabla de productos, tarjeta de notas con ícono, tarjeta
de totales) a partir de datos simples. generar_pdf_cotizacion() es un
wrapper delgado que arma esos datos a partir del modelo de base de datos.
Los colores, el logo y los datos fiscales salen de empresa_config.py.

Esto evita duplicar el código de diseño: si mañana se agrega un tercer
tipo de documento, solo hay que armar sus datos y llamar a la misma
función.
"""
import os
import re
import math
from io import BytesIO
import requests
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Table, TableStyle, Paragraph, Image as RLImage
from reportlab.lib.styles import ParagraphStyle

from empresa_config import EMPRESA, COLORES, LOGO_COMPLETO, COBRA_IVA, TASA_IVA, NOTA_IVA

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
OUTPUT_DIR = os.path.join(DATA_DIR, "pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

LOGO_PATH = os.path.join(BASE_DIR, "static", "img", LOGO_COMPLETO)
PRODUCT_IMGS_DIR = os.path.join(DATA_DIR, "product_imgs")

PAGE_W, PAGE_H = letter
ROWS_POR_HOJA = 8  # cuántos productos caben cómodamente en una hoja

# ---------- Paleta (sale de COLORES en empresa_config.py) ----------
NAVY = HexColor(COLORES["principal_oscuro"])   # textos fuertes y encabezado de tabla
ACCENT = HexColor(COLORES["acento"])           # línea y detalle del folio
PRINCIPAL = HexColor(COLORES["principal"])     # franja superior e ícono de notas
SLATE = HexColor(COLORES["texto_suave"])
LIGHT_BG = HexColor(COLORES["fondo_claro"])
ROW_ALT = HexColor(COLORES["fondo_alterno"])
LINE = HexColor(COLORES["borde"])
GREY_MUTED = HexColor(COLORES["gris_tenue"])

cell_style = ParagraphStyle("cell", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=SLATE)
item_style = ParagraphStyle("item", fontName="Helvetica-Bold", fontSize=8, leading=10, alignment=1, textColor=NAVY)


def money(v):
    return f"${v:,.2f}"


def _imagen_producto(url, max_w=44, max_h=40):
    """Descarga la imagen de un producto y la regresa como flowable Image
    ya ajustada a un rectángulo, lista para meterse en una celda de tabla.
    Si no hay link o falla la descarga, regresa None (celda vacía).

    Nota importante: si la imagen es una que guardamos nosotros mismos
    (URL con /product-imgs/...), la leemos directo del disco en vez de
    pedírsela al servidor por internet. Con un solo proceso (worker), si
    el servidor se pide una imagen a sí mismo por HTTP se queda esperando
    su propia respuesta y nunca contesta — se traba hasta que truena por
    tiempo agotado. Leer del disco evita ese problema por completo."""
    if not url:
        return None
    try:
        match = re.search(r"/product-imgs/([^/?]+)$", url)
        if match:
            ruta_local = os.path.join(PRODUCT_IMGS_DIR, match.group(1))
            if not os.path.exists(ruta_local):
                return None
            with open(ruta_local, "rb") as f:
                contenido = f.read()
        else:
            r = requests.get(url, timeout=6)
            r.raise_for_status()
            contenido = r.content
        buf = BytesIO(contenido)
        probe = ImageReader(buf)
        iw, ih = probe.getSize()
        ratio = min(max_w / iw, max_h / ih)
        buf.seek(0)
        return RLImage(buf, width=iw * ratio, height=ih * ratio)
    except Exception:
        return None


def generar_pdf_documento(
    ruta_salida,
    tipo_doc,           # ej. "COTIZACIÓN"
    folio,
    fecha_str,
    vigencia_dias,
    referencia_cliente,
    vendedor,
    cliente_nombre,
    cliente_contacto,
    items,               # lista de dicts: clave, nombre, nota, imagen_url, unidad, cantidad, precio_unit, importe
    subtotal,
    iva,
    total,
    nota_titulo=None,
    nota_texto=None,
):
    """Dibuja el documento completo con el diseño de la empresa y lo
    guarda en ruta_salida. Es agnóstico al tipo de documento — solo
    cambia el texto del badge (ej. "COTIZACIÓN SIC-0001") y de dónde
    vienen los datos.

    Si hay más productos de los que caben en una hoja (ROWS_POR_HOJA),
    el documento se reparte en varias páginas, repitiendo el encabezado
    y el panel de cliente en cada una, con "Hoja X de Y" abajo. Las
    notas y la tarjeta de totales solo se dibujan en la última hoja."""

    c = canvas.Canvas(ruta_salida, pagesize=letter)

    total_hojas = max(1, math.ceil(len(items) / ROWS_POR_HOJA)) if items else 1
    bloques = [items[i:i + ROWS_POR_HOJA] for i in range(0, len(items), ROWS_POR_HOJA)] or [[]]

    def dibujar_encabezado(num_hoja):
        """Dibuja la franja superior, badge de folio, franja de datos y
        panel de cliente (todo lo que se repite en cada hoja). Regresa
        la coordenada Y en la que debe empezar la tabla de productos."""
        band_h = 92
        # Encabezado claro: el logo de SICSA tiene trazos negros y letras
        # grises, así que va sobre blanco y no sobre una franja oscura.
        c.setFillColor(PRINCIPAL)
        c.rect(0, PAGE_H - 6, PAGE_W, 6, fill=1, stroke=0)
        c.setFillColor(ACCENT)
        c.rect(0, PAGE_H - band_h - 3, PAGE_W, 3, fill=1, stroke=0)

        logo_h = 52
        logo_w = 0
        if os.path.exists(LOGO_PATH):
            logo = ImageReader(LOGO_PATH)
            iw, ih = logo.getSize()
            logo_w = min(logo_h * iw / ih, 190)
            c.drawImage(logo, 40, PAGE_H - band_h + 22, width=logo_w, height=logo_h,
                         mask="auto", preserveAspectRatio=True, anchor="w")

        badge_w, badge_h = 130, 46
        tx = 40 + logo_w + 18
        max_txt_w = (PAGE_W - 40 - badge_w - 14) - tx

        # Línea divisoria entre logo y datos fiscales
        c.setStrokeColor(LINE)
        c.setLineWidth(0.8)
        c.line(tx - 9, PAGE_H - band_h + 22, tx - 9, PAGE_H - band_h + 22 + logo_h)

        # Razón social (si es muy larga, la letra se achica para que quepa)
        razon = EMPRESA.get("razon_social") or EMPRESA["nombre"]
        tam = 9.5
        while tam > 7 and c.stringWidth(razon, "Helvetica-Bold", tam) > max_txt_w:
            tam -= 0.25
        c.setFont("Helvetica-Bold", tam)
        c.setFillColor(NAVY)
        c.drawString(tx, PAGE_H - 42, razon)

        c.setFont("Helvetica", 7.8)
        c.setFillColor(SLATE)
        linea_rfc = f"RFC {EMPRESA['rfc']}"
        if EMPRESA.get("responsable"):
            linea_rfc = f"{EMPRESA['responsable']}  ·  {linea_rfc}"
        c.drawString(tx, PAGE_H - 55, linea_rfc)

        # Dirección: se parte en dos renglones por palabras si no cabe
        l1, l2 = "", ""
        for pal in EMPRESA["direccion"].split():
            if not l2 and c.stringWidth((l1 + " " + pal).strip(), "Helvetica", 7.8) <= max_txt_w:
                l1 = (l1 + " " + pal).strip()
            else:
                l2 = (l2 + " " + pal).strip()
        c.drawString(tx, PAGE_H - 66, l1)
        if l2:
            c.drawString(tx, PAGE_H - 76, l2)

        # Badge de tipo de documento + folio, arriba a la derecha
        bx = PAGE_W - 40 - badge_w
        by = PAGE_H - band_h + 24
        c.setFillColor(LIGHT_BG)
        c.roundRect(bx, by, badge_w, badge_h, 8, fill=1, stroke=0)
        c.setFillColor(ACCENT)
        c.roundRect(bx, by, 4, badge_h, 2, fill=1, stroke=0)
        c.setFillColor(SLATE)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(bx + badge_w / 2 + 2, by + 30, tipo_doc)
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(bx + badge_w / 2 + 2, by + 11, folio)

        # ============ FRANJA DE DATOS ============
        strip_h = 54
        strip_y = PAGE_H - band_h - 14 - strip_h
        c.setFillColor(LIGHT_BG)
        c.roundRect(40, strip_y, PAGE_W - 80, strip_h, 10, fill=1, stroke=0)

        info_cols = [
            ("FECHA", fecha_str),
            ("VIGENCIA", f"{vigencia_dias} DÍAS"),
            ("NO. PROVEEDOR", referencia_cliente or "—"),
            ("VENDEDOR", vendedor or EMPRESA["vendedor_default"]),
        ]
        seg_w = (PAGE_W - 80) / len(info_cols)
        for i, (label, value) in enumerate(info_cols):
            cx = 40 + i * seg_w + 22
            c.setFont("Helvetica-Bold", 6.8)
            c.setFillColor(GREY_MUTED)
            c.drawString(cx, strip_y + strip_h - 20, label)
            c.setFont("Helvetica-Bold", 10.5)
            c.setFillColor(NAVY)
            c.drawString(cx, strip_y + 15, value)
            if i < len(info_cols) - 1:
                dx = 40 + (i + 1) * seg_w
                c.setStrokeColor(LINE)
                c.setLineWidth(0.7)
                c.line(dx, strip_y + 10, dx, strip_y + strip_h - 10)

        # ============ PANEL DE CLIENTE ============
        panel_y = strip_y - 20
        panel_h = 34
        c.setFillColor(LIGHT_BG)
        c.roundRect(40, panel_y - panel_h + 12, PAGE_W - 80, panel_h, 8, fill=1, stroke=0)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(SLATE)
        c.drawString(56, panel_y - 4, "CLIENTE")
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(NAVY)
        c.drawString(56, panel_y - 18, cliente_nombre.upper())

        c.setFont("Helvetica", 7.5)
        c.setFillColor(SLATE)
        c.drawString(320, panel_y - 4, "CONTACTO")
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(NAVY)
        c.drawString(320, panel_y - 18, cliente_contacto or "—")

        # Indicador de hoja (solo si hay más de una)
        if total_hojas > 1:
            c.setFont("Helvetica-Bold", 8)
            c.setFillColor(SLATE)
            c.drawRightString(PAGE_W - 40, 24, f"Hoja {num_hoja} de {total_hojas}")

        return panel_y - panel_h - 6

    for idx_hoja, bloque_items in enumerate(bloques, start=1):
        table_top = dibujar_encabezado(idx_hoja)

        # ============ TABLA DE PRODUCTOS (de esta hoja) ============
        col_widths = [40, 55, 220, 40, 40, 68, 69]
        headers = ["ITEM", "IMAGEN", "CONCEPTO", "UNIDAD", "CANT.", "P. UNITARIO", "IMPORTE"]

        table_data = [headers]
        offset = sum(len(b) for b in bloques[:idx_hoja - 1])
        for idx, item in enumerate(bloque_items, start=offset + 1):
            concepto_txt = f"<b>{item['nombre']}</b>"
            if item.get("nota"):
                concepto_txt += "<br/>" + item["nota"]
            img_flowable = _imagen_producto(item.get("imagen_url"))
            table_data.append([
                Paragraph(item.get("clave") or str(idx), item_style),
                img_flowable if img_flowable else "",
                Paragraph(concepto_txt, cell_style),
                item.get("unidad") or "pza",
                f"{float(item['cantidad']):g}",
                money(float(item["precio_unit"])),
                money(float(item["importe"])),
            ])

        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7.5),
            ("TOPPADDING", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 9),
            ("FONTSIZE", (0, 1), (-1, -1), 7.5),
            ("ALIGN", (0, 0), (1, -1), "CENTER"),
            ("VALIGN", (1, 1), (1, -1), "MIDDLE"),
            ("ALIGN", (3, 0), (4, -1), "CENTER"),
            ("ALIGN", (5, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 1), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 7),
            ("LINEBELOW", (0, 0), (-1, -2), 0.6, LINE),
            ("LINEBELOW", (0, -1), (-1, -1), 0.6, LINE),
            ("TEXTCOLOR", (5, 1), (-1, -1), NAVY),
            ("FONTNAME", (5, 1), (-1, -1), "Helvetica-Bold"),
        ]
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), ROW_ALT))
        tbl.setStyle(TableStyle(style_cmds))

        w, h = tbl.wrapOn(c, PAGE_W - 80, PAGE_H)
        tbl.drawOn(c, 40, table_top - h)

        y_after_table = table_top - h - 24
        es_ultima_hoja = idx_hoja == len(bloques)

        if not es_ultima_hoja:
            c.setFont("Helvetica-Oblique", 7.5)
            c.setFillColor(GREY_MUTED)
            c.drawString(40, max(y_after_table, 40), "Continúa en la siguiente hoja...")
            c.showPage()
            continue

        # ============ TARJETA DE NOTAS + TARJETA DE TOTALES (solo última hoja) ============
        card_w, card_h = 260, 92
        card_x = PAGE_W - 40 - card_w
        card_y = min(36, y_after_table - card_h)
        card_y = max(card_y, 36) if y_after_table - card_h >= 36 else y_after_table - card_h

        note_w = card_x - 40 - 16
        note_h = card_h
        note_x = 40
        note_y = card_y

        c.setFillColor(LIGHT_BG)
        c.roundRect(note_x, note_y, note_w, note_h, 10, fill=1, stroke=0)

        icon_r = 8
        icon_cx, icon_cy = note_x + 18, note_y + note_h - 20
        c.setFillColor(PRINCIPAL)
        c.circle(icon_cx, icon_cy, icon_r, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(icon_cx, icon_cy - 3.2, "i")

        tx0 = note_x + 34
        c.setFont("Helvetica-Bold", 8.3)
        c.setFillColor(NAVY)
        titulo_nota = nota_titulo or "Notas"
        c.drawString(tx0, note_y + note_h - 17, titulo_nota)

        c.setFont("Helvetica", 7.6)
        c.setFillColor(SLATE)
        texto_nota = nota_texto or f"{tipo_doc.capitalize()} generada por {EMPRESA['nombre']}."
        palabras = texto_nota.split()
        linea1, linea2, actual = "", "", 1
        for palabra in palabras:
            candidato = (linea1 if actual == 1 else linea2) + " " + palabra
            if c.stringWidth(candidato.strip(), "Helvetica", 7.6) < note_w - 50:
                if actual == 1:
                    linea1 = candidato.strip()
                else:
                    linea2 = candidato.strip()
            else:
                if actual == 1:
                    actual = 2
                    linea2 = palabra
                else:
                    break
        c.drawString(tx0, note_y + note_h - 32, linea1)
        if linea2:
            c.drawString(tx0, note_y + note_h - 43, linea2)

        c.setStrokeColor(LINE)
        c.setLineWidth(0.7)
        c.line(note_x + 16, note_y + 26, note_x + note_w - 16, note_y + 26)

        if COBRA_IVA:
            c.setFont("Helvetica", 7.3)
            c.setFillColor(SLATE)
            c.drawString(note_x + 16, note_y + 14, "Precios en pesos mexicanos (MXN).")
        else:
            # Leyenda fija de IVA: sale siempre, aunque la cotización
            # tenga sus propias notas.
            c.setFont("Helvetica-Bold", 7.3)
            c.setFillColor(NAVY)
            c.drawString(note_x + 16, note_y + 14, NOTA_IVA)
            ancho = c.stringWidth(NOTA_IVA + "  ", "Helvetica-Bold", 7.3)
            c.setFont("Helvetica", 7.3)
            c.setFillColor(SLATE)
            c.drawString(note_x + 16 + ancho, note_y + 14, "Precios en pesos mexicanos (MXN).")
        c.drawString(note_x + 16, note_y + 4,
                      f"{tipo_doc.capitalize()} válida por {vigencia_dias} días naturales a partir de la fecha de emisión.")

        # ---- Tarjeta de totales ----
        c.setFillColor(LIGHT_BG)
        c.roundRect(card_x, card_y, card_w, card_h, 10, fill=1, stroke=0)

        pad = 18
        c.setFont("Helvetica", 8.5)
        c.setFillColor(SLATE)
        c.drawString(card_x + pad, card_y + card_h - 22, "Subtotal")
        c.drawRightString(card_x + card_w - pad, card_y + card_h - 22, money(subtotal))

        if COBRA_IVA:
            c.drawString(card_x + pad, card_y + card_h - 38, f"IVA ({TASA_IVA * 100:.2f}%)")
            c.drawRightString(card_x + card_w - pad, card_y + card_h - 38, money(iva))
        else:
            c.drawString(card_x + pad, card_y + card_h - 38, "IVA")
            c.drawRightString(card_x + card_w - pad, card_y + card_h - 38, "No incluido")

        c.setStrokeColor(LINE)
        c.setLineWidth(0.7)
        c.line(card_x + pad, card_y + card_h - 48, card_x + card_w - pad, card_y + card_h - 48)

        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(NAVY)
        c.drawString(card_x + pad, card_y + 20, "TOTAL")
        c.setFont("Helvetica-Bold", 16)
        c.setFillColor(NAVY)
        c.drawRightString(card_x + card_w - pad, card_y + 17, money(total))

    c.save()
    return ruta_salida


# ---------- Wrappers específicos por tipo de documento ----------

def generar_pdf_cotizacion(cotizacion):
    ruta = os.path.join(OUTPUT_DIR, f"{cotizacion.folio}.pdf")
    items = [
        {
            "clave": item.clave, "nombre": item.nombre, "nota": item.nota,
            "imagen_url": item.imagen_url, "unidad": item.unidad,
            "cantidad": item.cantidad, "precio_unit": item.precio_unit,
            "importe": item.importe,
        }
        for item in cotizacion.items
    ]
    return generar_pdf_documento(
        ruta_salida=ruta,
        tipo_doc="COTIZACIÓN",
        folio=cotizacion.folio,
        fecha_str=cotizacion.fecha.strftime("%d / %m / %Y"),
        vigencia_dias=cotizacion.vigencia_dias,
        referencia_cliente=cotizacion.referencia_cliente,
        vendedor=cotizacion.vendedor,
        cliente_nombre=cotizacion.cliente.nombre,
        cliente_contacto=cotizacion.cliente.contacto_nombre,
        items=items,
        subtotal=cotizacion.subtotal,
        iva=cotizacion.iva,
        total=cotizacion.total,
        nota_texto=cotizacion.notas,
    )
