import os
import uuid
import base64
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, session
from sqlalchemy import or_
from models import db, Cliente, Producto, Cotizacion, CotizacionItem, Contador
from pdf_generator import generar_pdf_cotizacion
from link_extractor import extraer_datos_producto
from image_extractor import extraer_datos_imagen
from empresa_config import (
    EMPRESA, USUARIOS, COLORES, LOGO_COMPLETO, LOGO_ICONO,
    COBRA_IVA, TASA_IVA, NOTA_IVA,
    FOLIO_PREFIJO, FOLIO_INICIAL, FOLIO_DIGITOS, NOMBRE_BD,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
PRODUCT_IMGS_DIR = os.path.join(DATA_DIR, "product_imgs")
os.makedirs(PRODUCT_IMGS_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(DATA_DIR, NOMBRE_BD)}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cambia-esta-llave-en-produccion")

db.init_app(app)

# ---------- Acceso ----------
# Los usuarios se definen en empresa_config.py. Las contraseñas reales se
# configuran como variables de entorno en Render — nunca quedan escritas
# en el código.

@app.context_processor
def datos_de_marca():
    """Pone los datos de la empresa, colores y logos a disposición de
    todas las plantillas HTML, para no repetirlos en cada pantalla."""
    return {
        "EMPRESA": EMPRESA, "COLORES": COLORES,
        "LOGO_COMPLETO": LOGO_COMPLETO, "LOGO_ICONO": LOGO_ICONO,
        "COBRA_IVA": COBRA_IVA, "TASA_IVA": TASA_IVA, "NOTA_IVA": NOTA_IVA,
    }

@app.before_request
def exigir_login():
    rutas_publicas = {"login", "static", "product_imagen_servida"}
    if request.endpoint in rutas_publicas or request.endpoint is None:
        return
    if not session.get("usuario_nombre"):
        return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("usuario_nombre"):
        return redirect(url_for("index"))
    if request.method == "POST":
        intento = request.form.get("password", "")
        for datos in USUARIOS:
            real = os.environ.get(datos["env_var"], "")
            if real and secrets.compare_digest(intento, real):
                session["usuario_nombre"] = datos["nombre"]
                saludo = datos.get("saludo") or "Bienvenido"
                flash(f"{saludo}, {datos['nombre']}", "bienvenida")
                return redirect(url_for("index"))
        flash("Contraseña incorrecta.", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("usuario_nombre", None)
    flash("Sesión cerrada.", "success")
    return redirect(url_for("login"))

@app.template_filter("moneda")
def formato_moneda(valor):
    """Formatea un número con separador de miles y 2 decimales: 1234.5 -> 1,234.50"""
    try:
        return "{:,.2f}".format(float(valor or 0))
    except (TypeError, ValueError):
        return "0.00"

def _numero_mas_alto_usado():
    """El número de folio más alto que se ha usado: el mayor entre el
    contador guardado y los folios que existen en la base."""
    mayor = FOLIO_INICIAL - 1
    contador = db.session.get(Contador, "folio_cotizacion")
    if contador:
        mayor = max(mayor, contador.valor)
    for (folio,) in db.session.query(Cotizacion.folio).all():
        if folio and folio.startswith(FOLIO_PREFIJO):
            numero = folio[len(FOLIO_PREFIJO):]
            if numero.isdigit():
                mayor = max(mayor, int(numero))
    return mayor


def siguiente_folio(reservar=False):
    """Siguiente folio: SIC-0001, SIC-0002... Con reservar=True además lo
    marca como usado (al guardar la cotización), así que si se borra la
    última cotización su folio no se vuelve a usar."""
    numero = _numero_mas_alto_usado() + 1
    if reservar:
        contador = db.session.get(Contador, "folio_cotizacion")
        if not contador:
            contador = Contador(nombre="folio_cotizacion", valor=0)
            db.session.add(contador)
        contador.valor = numero
    return f"{FOLIO_PREFIJO}{str(numero).zfill(FOLIO_DIGITOS)}"


# ---------- Home ----------
@app.route("/")
def index():
    pendientes = Cotizacion.query.filter(
        Cotizacion.estatus.in_(["borrador", "enviada"])
    ).count()
    aprobadas = Cotizacion.query.filter_by(estatus="aprobada").count()
    total_clientes = Cliente.query.filter_by(activo=True).count()
    ultimas = Cotizacion.query.order_by(Cotizacion.fecha.desc()).limit(8).all()
    return render_template(
        "index.html",
        pendientes=pendientes,
        aprobadas=aprobadas,
        total_clientes=total_clientes,
        ultimas=ultimas,
    )

# ---------- Clientes ----------
@app.route("/clientes")
def clientes_lista():
    clientes = Cliente.query.filter_by(activo=True).order_by(Cliente.nombre).all()
    return render_template("clientes.html", clientes=clientes)

@app.route("/clientes/nuevo", methods=["GET", "POST"])
def clientes_nuevo():
    if request.method == "POST":
        cliente = Cliente(
            nombre=request.form["nombre"],
            contacto_nombre=request.form.get("contacto_nombre"),
            rfc=request.form.get("rfc", "").upper().strip(),
            regimen_fiscal=request.form.get("regimen_fiscal"),
            uso_cfdi=request.form.get("uso_cfdi"),
            telefono=request.form.get("telefono"),
            email=request.form.get("email"),
        )
        db.session.add(cliente)
        db.session.commit()
        flash("Cliente guardado.", "success")
        return redirect(url_for("clientes_lista"))
    return render_template("cliente_form.html", cliente=None)

@app.route("/clientes/<int:id>/editar", methods=["GET", "POST"])
def clientes_editar(id):
    cliente = Cliente.query.get_or_404(id)
    if request.method == "POST":
        cliente.nombre = request.form["nombre"]
        cliente.contacto_nombre = request.form.get("contacto_nombre")
        cliente.rfc = request.form.get("rfc", "").upper().strip()
        cliente.regimen_fiscal = request.form.get("regimen_fiscal")
        cliente.uso_cfdi = request.form.get("uso_cfdi")
        cliente.telefono = request.form.get("telefono")
        cliente.email = request.form.get("email")
        db.session.commit()
        flash("Cliente actualizado.", "success")
        return redirect(url_for("clientes_lista"))
    return render_template("cliente_form.html", cliente=cliente)

@app.route("/clientes/<int:id>/eliminar", methods=["POST"])
def clientes_eliminar(id):
    """Borra un cliente por completo. Si ya tiene cotizaciones asociadas,
    no lo dejamos borrar (rompería esas cotizaciones) — hay que borrar o
    reasignar esas cotizaciones primero."""
    cliente = Cliente.query.get_or_404(id)
    if cliente.cotizaciones:
        flash(
            f"No se puede eliminar: \"{cliente.nombre}\" tiene "
            f"{len(cliente.cotizaciones)} cotización(es) asociada(s). "
            "Elimina esas cotizaciones primero.",
            "danger",
        )
        return redirect(url_for("clientes_lista"))
    db.session.delete(cliente)
    db.session.commit()
    flash(f"Cliente \"{cliente.nombre}\" eliminado.", "success")
    return redirect(url_for("clientes_lista"))

# ---------- Productos (catálogo opcional) ----------
@app.route("/productos")
def productos_lista():
    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    return render_template("productos.html", productos=productos)

@app.route("/productos/nuevo", methods=["GET", "POST"])
def productos_nuevo():
    if request.method == "POST":
        costo = float(request.form.get("costo", 0) or 0)
        margen = float(request.form.get("margen_utilidad", 25) or 25)
        precio_manual = request.form.get("precio")
        precio = float(precio_manual) if precio_manual else round(costo * (1 + margen / 100), 2)
        producto = Producto(
            nombre=request.form["nombre"],
            descripcion=request.form.get("descripcion"),
            clave_sat=request.form.get("clave_sat"),
            unidad_sat=request.form.get("unidad_sat"),
            clave_unidad_desc=request.form.get("clave_unidad_desc"),
            costo=costo,
            margen_utilidad=margen,
            precio=precio,
            imagen_url=request.form.get("imagen_url"),
            link_referencia=request.form.get("link_referencia"),
        )
        db.session.add(producto)
        db.session.commit()
        flash("Producto guardado.", "success")
        return redirect(url_for("productos_lista"))
    return render_template("producto_form.html", producto=None)

@app.route("/productos/<int:id>/editar", methods=["GET", "POST"])
def productos_editar(id):
    producto = Producto.query.get_or_404(id)
    if request.method == "POST":
        costo = float(request.form.get("costo", 0) or 0)
        margen = float(request.form.get("margen_utilidad", 25) or 25)
        precio_manual = request.form.get("precio")
        producto.nombre = request.form["nombre"]
        producto.descripcion = request.form.get("descripcion")
        producto.clave_sat = request.form.get("clave_sat")
        producto.unidad_sat = request.form.get("unidad_sat")
        producto.clave_unidad_desc = request.form.get("clave_unidad_desc")
        producto.costo = costo
        producto.margen_utilidad = margen
        producto.precio = float(precio_manual) if precio_manual else round(costo * (1 + margen / 100), 2)
        producto.imagen_url = request.form.get("imagen_url")
        producto.link_referencia = request.form.get("link_referencia")
        db.session.commit()
        flash("Producto actualizado.", "success")
        return redirect(url_for("productos_lista"))
    return render_template("producto_form.html", producto=producto)

# ---------- Cotizaciones ----------
@app.route("/cotizaciones")
def cotizaciones_lista():
    filtro = request.args.get("estatus")
    busqueda = request.args.get("q", "").strip()
    query = Cotizacion.query
    if filtro:
        query = query.filter_by(estatus=filtro)
    if busqueda:
        like = f"%{busqueda}%"
        query = (
            query.join(Cliente, Cotizacion.cliente_id == Cliente.id)
            .outerjoin(CotizacionItem, CotizacionItem.cotizacion_id == Cotizacion.id)
            .filter(
                or_(
                    Cotizacion.folio.ilike(like),
                    Cliente.nombre.ilike(like),
                    CotizacionItem.nombre.ilike(like),
                )
            )
            .distinct()
        )
    cotizaciones = query.order_by(Cotizacion.fecha.desc()).all()
    return render_template("cotizaciones.html", cotizaciones=cotizaciones, filtro=filtro, busqueda=busqueda)

@app.route("/cotizaciones/nueva", methods=["GET", "POST"])
def cotizaciones_nueva():
    if request.method == "POST":
        nombres_check = request.form.getlist("nombre")
        if len(nombres_check) > 40:
            flash("Una cotización puede tener máximo 40 productos.", "danger")
            return redirect(url_for("cotizaciones_nueva"))

        cotizacion = Cotizacion(
            folio=siguiente_folio(reservar=True),
            cliente_id=request.form["cliente_id"],
            vigencia_dias=int(request.form.get("vigencia_dias", 5) or 5),
            referencia_cliente=request.form.get("referencia_cliente"),
            vendedor=request.form.get("vendedor") or EMPRESA["vendedor_default"],
            estatus="borrador",
            notas=request.form.get("notas", ""),
        )
        db.session.add(cotizacion)
        db.session.flush()

        claves = request.form.getlist("clave")
        nombres = request.form.getlist("nombre")
        notas_item = request.form.getlist("nota")
        imagenes = request.form.getlist("imagen_url")
        links = request.form.getlist("link_referencia")
        unidades = request.form.getlist("unidad")
        cantidades = request.form.getlist("cantidad")
        costos = request.form.getlist("costo")
        margenes = request.form.getlist("margen_utilidad")
        precios = request.form.getlist("precio_unit")

        for i, nombre in enumerate(nombres):
            if not nombre.strip():
                continue
            item = CotizacionItem(
                cotizacion_id=cotizacion.id,
                orden=i,
                clave=claves[i] if i < len(claves) else "",
                nombre=nombre,
                nota=notas_item[i] if i < len(notas_item) else "",
                imagen_url=imagenes[i] if i < len(imagenes) else "",
                link_referencia=links[i] if i < len(links) else "",
                unidad=unidades[i] if i < len(unidades) else "pza",
                cantidad=float(cantidades[i] or 1),
                costo=float(costos[i] or 0),
                margen_utilidad=float(margenes[i] or 0),
                precio_unit=float(precios[i] or 0),
            )
            db.session.add(item)

        db.session.commit()
        flash(f"Cotización {cotizacion.folio} creada.", "success")
        return redirect(url_for("cotizaciones_detalle", id=cotizacion.id))

    clientes = Cliente.query.filter_by(activo=True).order_by(Cliente.nombre).all()
    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    productos_json = [
        {
            "id": p.id, "nombre": p.nombre, "descripcion": p.descripcion or "",
            "precio": float(p.precio), "costo": float(p.costo),
            "margen_utilidad": float(p.margen_utilidad),
            "imagen_url": p.imagen_url or "", "unidad": p.clave_unidad_desc or "pza",
        }
        for p in productos
    ]
    return render_template(
        "cotizacion_form.html", clientes=clientes, productos=productos,
        productos_json=productos_json, folio=siguiente_folio(),
        vendedor_default=EMPRESA["vendedor_default"],
    )

@app.route("/cotizaciones/<int:id>")
def cotizaciones_detalle(id):
    cotizacion = Cotizacion.query.get_or_404(id)
    return render_template("cotizacion_detalle.html", c=cotizacion)

@app.route("/cotizaciones/<int:id>/editar", methods=["GET", "POST"])
def cotizaciones_editar(id):
    """Edita una cotización ya guardada — por ejemplo, si el cliente pide
    un cambio y no hace falta volver a capturar todo desde cero. Al
    guardar, se reemplazan los productos de la cotización por los que
    queden en el formulario (se borran los viejos y se crean los nuevos,
    conservando el mismo folio)."""
    cotizacion = Cotizacion.query.get_or_404(id)

    if request.method == "POST":
        nombres_check = request.form.getlist("nombre")
        if len(nombres_check) > 40:
            flash("Una cotización puede tener máximo 40 productos.", "danger")
            return redirect(url_for("cotizaciones_editar", id=id))

        cotizacion.cliente_id = request.form["cliente_id"]
        cotizacion.vigencia_dias = int(request.form.get("vigencia_dias", 5) or 5)
        cotizacion.referencia_cliente = request.form.get("referencia_cliente")
        cotizacion.vendedor = request.form.get("vendedor") or EMPRESA["vendedor_default"]
        cotizacion.notas = request.form.get("notas", "")

        for item_viejo in list(cotizacion.items):
            db.session.delete(item_viejo)
        db.session.flush()

        claves = request.form.getlist("clave")
        nombres = request.form.getlist("nombre")
        notas_item = request.form.getlist("nota")
        imagenes = request.form.getlist("imagen_url")
        links = request.form.getlist("link_referencia")
        unidades = request.form.getlist("unidad")
        cantidades = request.form.getlist("cantidad")
        costos = request.form.getlist("costo")
        margenes = request.form.getlist("margen_utilidad")
        precios = request.form.getlist("precio_unit")

        for i, nombre in enumerate(nombres):
            if not nombre.strip():
                continue
            item = CotizacionItem(
                cotizacion_id=cotizacion.id,
                orden=i,
                clave=claves[i] if i < len(claves) else "",
                nombre=nombre,
                nota=notas_item[i] if i < len(notas_item) else "",
                imagen_url=imagenes[i] if i < len(imagenes) else "",
                link_referencia=links[i] if i < len(links) else "",
                unidad=unidades[i] if i < len(unidades) else "pza",
                cantidad=float(cantidades[i] or 1),
                costo=float(costos[i] or 0),
                margen_utilidad=float(margenes[i] or 0),
                precio_unit=float(precios[i] or 0),
            )
            db.session.add(item)

        db.session.commit()
        flash(f"Cotización {cotizacion.folio} actualizada.", "success")
        return redirect(url_for("cotizaciones_detalle", id=cotizacion.id))

    clientes = Cliente.query.filter_by(activo=True).order_by(Cliente.nombre).all()
    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    productos_json = [
        {
            "id": p.id, "nombre": p.nombre, "descripcion": p.descripcion or "",
            "precio": float(p.precio), "costo": float(p.costo),
            "margen_utilidad": float(p.margen_utilidad),
            "imagen_url": p.imagen_url or "", "unidad": p.clave_unidad_desc or "pza",
        }
        for p in productos
    ]
    items_json = [
        {
            "clave": it.clave or "", "nombre": it.nombre, "nota": it.nota or "",
            "imagen_url": it.imagen_url or "", "link_referencia": it.link_referencia or "",
            "unidad": it.unidad or "pza", "cantidad": float(it.cantidad),
            "costo": float(it.costo), "margen_utilidad": float(it.margen_utilidad),
            "precio": float(it.precio_unit),
        }
        for it in sorted(cotizacion.items, key=lambda x: x.orden)
    ]
    return render_template(
        "cotizacion_form.html", clientes=clientes, productos=productos,
        productos_json=productos_json, folio=cotizacion.folio,
        vendedor_default=EMPRESA["vendedor_default"],
        cotizacion=cotizacion, items_json=items_json,
    )

@app.route("/cotizaciones/<int:id>/estatus/<nuevo_estatus>", methods=["POST"])
def cotizaciones_cambiar_estatus(id, nuevo_estatus):
    cotizacion = Cotizacion.query.get_or_404(id)
    validos = ["borrador", "enviada", "aprobada", "cancelada"]
    if nuevo_estatus not in validos:
        flash("Estatus no válido.", "danger")
        return redirect(url_for("cotizaciones_detalle", id=id))

    cotizacion.estatus = nuevo_estatus
    db.session.commit()
    flash(f"Cotización marcada como {nuevo_estatus}.", "success")
    return redirect(url_for("cotizaciones_detalle", id=id))

@app.route("/cotizaciones/<int:id>/eliminar", methods=["POST"])
def cotizaciones_eliminar(id):
    """Borra una cotización por completo (sus líneas se borran solas por
    la relación en cascada)."""
    cotizacion = Cotizacion.query.get_or_404(id)
    folio = cotizacion.folio

    db.session.delete(cotizacion)
    db.session.commit()
    flash(f"Cotización {folio} eliminada.", "success")
    return redirect(url_for("cotizaciones_lista"))

@app.route("/cotizaciones/<int:id>/pdf")
def cotizaciones_pdf(id):
    cotizacion = Cotizacion.query.get_or_404(id)
    ruta_pdf = generar_pdf_cotizacion(cotizacion)
    return send_file(ruta_pdf, as_attachment=True, download_name=f"{cotizacion.folio}.pdf")

@app.route("/cotizaciones/<int:id>/pdf/vista-previa")
def cotizaciones_pdf_preview(id):
    """Muestra el PDF en el navegador (sin forzar descarga), para revisarlo
    antes de mandarlo o de decidir si hay que corregir algo."""
    cotizacion = Cotizacion.query.get_or_404(id)
    ruta_pdf = generar_pdf_cotizacion(cotizacion)
    return send_file(ruta_pdf, as_attachment=False, download_name=f"{cotizacion.folio}.pdf")

# ---------- API auxiliares ----------
@app.route("/api/productos/<int:id>")
def api_producto(id):
    p = Producto.query.get_or_404(id)
    return jsonify({
        "precio": float(p.precio), "nombre": p.nombre, "costo": float(p.costo),
        "margen_utilidad": float(p.margen_utilidad), "imagen_url": p.imagen_url or "",
    })

@app.route("/api/importar-link", methods=["POST"])
def api_importar_link():
    """Intenta traer nombre, imagen y precio de un link de producto.
    Best-effort: el front siempre debe permitir editar el resultado."""
    url = request.json.get("url", "").strip()
    if not url.startswith("http"):
        return jsonify({"error": "Ese no parece un link válido."}), 400
    datos = extraer_datos_producto(url)
    return jsonify(datos)

@app.route("/api/importar-imagen", methods=["POST"])
def api_importar_imagen():
    """Recibe una imagen (pegada o arrastrada) en base64, la analiza con
    un modelo de IA con visión, y regresa nombre/descripción/precio.
    También guarda la imagen en el servidor para poder usarla en el PDF
    de la cotización."""
    body = request.json or {}
    image_b64 = body.get("image_base64", "")
    media_type = body.get("media_type", "image/png")

    if not image_b64:
        return jsonify({"error": "No llegó ninguna imagen."}), 400

    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception:
        return jsonify({"error": "La imagen no se pudo leer."}), 400

    if len(image_bytes) > 8 * 1024 * 1024:
        return jsonify({"error": "La imagen es demasiado pesada (máximo 8 MB)."}), 400

    datos = extraer_datos_imagen(image_bytes, media_type)

    imagen_url = None
    if not datos.get("error"):
        ext = "png" if "png" in media_type else "jpg"
        nombre_archivo = f"{uuid.uuid4().hex}.{ext}"
        ruta = os.path.join(PRODUCT_IMGS_DIR, nombre_archivo)
        bytes_a_guardar = datos.pop("imagen_bytes", None) or image_bytes
        with open(ruta, "wb") as f:
            f.write(bytes_a_guardar)
        imagen_url = url_for("product_imagen_servida", filename=nombre_archivo, _external=True)
    else:
        datos.pop("imagen_bytes", None)

    datos["imagen_url"] = imagen_url
    return jsonify(datos)

@app.route("/product-imgs/<filename>")
def product_imagen_servida(filename):
    from werkzeug.utils import secure_filename
    return send_file(os.path.join(PRODUCT_IMGS_DIR, secure_filename(filename)))
@app.route("/api/subir-imagen", methods=["POST"])
def api_subir_imagen():
    """Sube una imagen SIN analizarla con IA — solo la guarda y regresa su
    URL. Para cuando no hay internet suficiente para el análisis automático,
    o cuando se prefiere no gastar en la API; el usuario captura nombre y
    precio a mano."""
    body = request.json or {}
    image_b64 = body.get("image_base64", "")
    media_type = body.get("media_type", "image/png")

    if not image_b64:
        return jsonify({"error": "No llegó ninguna imagen."}), 400

    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception:
        return jsonify({"error": "La imagen no se pudo leer."}), 400

    if len(image_bytes) > 8 * 1024 * 1024:
        return jsonify({"error": "La imagen es demasiado pesada (máximo 8 MB)."}), 400

    ext = "png" if "png" in media_type else "jpg"
    nombre_archivo = f"{uuid.uuid4().hex}.{ext}"
    ruta = os.path.join(PRODUCT_IMGS_DIR, nombre_archivo)
    with open(ruta, "wb") as f:
        f.write(image_bytes)
    imagen_url = url_for("product_imagen_servida", filename=nombre_archivo, _external=True)

    return jsonify({"imagen_url": imagen_url, "error": None})

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(debug=debug_mode, host="0.0.0.0", port=port)
else:
    with app.app_context():
        db.create_all()
