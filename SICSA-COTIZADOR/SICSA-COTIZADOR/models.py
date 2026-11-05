from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Cliente(db.Model):
    __tablename__ = "clientes"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    contacto_nombre = db.Column(db.String(150))
    rfc = db.Column(db.String(13))
    regimen_fiscal = db.Column(db.String(10))
    uso_cfdi = db.Column(db.String(10))
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(150))
    activo = db.Column(db.Boolean, default=True)

    cotizaciones = db.relationship("Cotizacion", backref="cliente", lazy=True)


class Producto(db.Model):
    """Catálogo opcional, útil para productos que se repiten seguido
    (ej. tijeras, papelería). No es obligatorio usarlo: en una cotización
    puedes agregar productos ad-hoc sin que estén dados de alta aquí."""
    __tablename__ = "productos"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.String(300))
    clave_sat = db.Column(db.String(10))
    unidad_sat = db.Column(db.String(10))
    clave_unidad_desc = db.Column(db.String(50))
    costo = db.Column(db.Numeric(10, 2), default=0)
    margen_utilidad = db.Column(db.Numeric(5, 2), default=25)  # % por defecto
    precio = db.Column(db.Numeric(10, 2), nullable=False, default=0)  # precio de venta
    imagen_url = db.Column(db.String(500))
    link_referencia = db.Column(db.String(500))
    activo = db.Column(db.Boolean, default=True)

    @property
    def precio_sugerido(self):
        return round(float(self.costo) * (1 + float(self.margen_utilidad) / 100), 2)


class Cotizacion(db.Model):
    __tablename__ = "cotizaciones"

    id = db.Column(db.Integer, primary_key=True)
    folio = db.Column(db.String(20), unique=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    vigencia_dias = db.Column(db.Integer, default=5)
    referencia_cliente = db.Column(db.String(50))  # "No. Proveedor" que asigna el cliente
    vendedor = db.Column(db.String(100))
    # estatus: borrador -> enviada -> aprobada  (o cancelada)
    estatus = db.Column(db.String(20), default="borrador")
    notas = db.Column(db.Text)

    items = db.relationship(
        "CotizacionItem", backref="cotizacion", lazy=True,
        cascade="all, delete-orphan", order_by="CotizacionItem.orden"
    )

    @property
    def subtotal(self):
        return sum(item.importe for item in self.items)

    @property
    def iva(self):
        return round(self.subtotal * 0.16, 2)

    @property
    def total(self):
        return round(self.subtotal + self.iva, 2)


class CotizacionItem(db.Model):
    """Cada línea es autónoma: trae su propio nombre, imagen, costo y margen.
    Puede (opcionalmente) referenciar un Producto del catálogo, pero no es
    obligatorio — así se pueden cotizar productos nuevos sobre la marcha."""
    __tablename__ = "cotizacion_items"

    id = db.Column(db.Integer, primary_key=True)
    cotizacion_id = db.Column(db.Integer, db.ForeignKey("cotizaciones.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=True)

    orden = db.Column(db.Integer, default=0)
    clave = db.Column(db.String(10))  # ej. "1A", "1B", "2", "3A" — editable a mano
    nombre = db.Column(db.String(250), nullable=False)
    nota = db.Column(db.String(300))  # ej. "Para: Monitor Dell U2415 · Modelo: XYZ"
    imagen_url = db.Column(db.String(500))
    link_referencia = db.Column(db.String(500))
    unidad = db.Column(db.String(20), default="pza")

    cantidad = db.Column(db.Numeric(10, 2), nullable=False, default=1)
    costo = db.Column(db.Numeric(10, 2), default=0)
    margen_utilidad = db.Column(db.Numeric(5, 2), default=25)
    precio_unit = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    producto = db.relationship("Producto")

    @property
    def importe(self):
        return round(float(self.cantidad) * float(self.precio_unit), 2)


class Contador(db.Model):
    """Guarda el último número de folio usado, para que un folio nunca se
    repita aunque se borre la última cotización."""
    __tablename__ = "contadores"

    nombre = db.Column(db.String(30), primary_key=True)
    valor = db.Column(db.Integer, nullable=False, default=0)
