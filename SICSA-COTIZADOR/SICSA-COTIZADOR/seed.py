"""Carga datos de ejemplo para probar el cotizador. Solo agrega datos si
las tablas están vacías, así que no borra nada si se corre de nuevo."""
from app import app
from models import db, Cliente, Producto

with app.app_context():
    db.create_all()

    if Cliente.query.count() == 0:
        db.session.add_all([
            Cliente(nombre="Cliente de Ejemplo SA de CV", contacto_nombre="Juan Pérez",
                     rfc="CEJ010101AB1", regimen_fiscal="601", uso_cfdi="G03",
                     telefono="8112345678"),
        ])

    if Producto.query.count() == 0:
        db.session.add_all([
            Producto(nombre="Servicio de comedor (por comensal)", descripcion="Desayuno o comida",
                       clave_sat="90101500", unidad_sat="E48", clave_unidad_desc="servicio",
                       costo=80.00, margen_utilidad=25, precio=100.00),
        ])

    db.session.commit()
    print("Base de datos lista con datos de ejemplo.")
