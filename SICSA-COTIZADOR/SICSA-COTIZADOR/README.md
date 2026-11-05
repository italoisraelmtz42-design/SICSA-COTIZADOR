# SICSA Cotizador

Sistema de cotizaciones para **SERVICIO INDUSTRIAL DE COMEDORES SA DE CV (SICSA)**.
Cotiza rápido, genera el PDF con la marca de la empresa y lleva el estatus de
cada cotización (borrador → enviada → aprobada, o cancelada).

Es una copia del N|B Cotizador con la marca de SICSA y sin la parte de
facturación (solo se hacen cotizaciones).

## Cambiar datos de la empresa

Todo lo que es propio de la empresa está en **`empresa_config.py`**:

- Datos fiscales que salen en el PDF (razón social, RFC, dirección).
- Prefijo y número inicial del folio (`SIC-0001`, `SIC-0002`...).
- Usuarios que pueden entrar.
- Nombres de los archivos de logo (en `static/img/`).
- Colores de las pantallas y del PDF.

Para otra empresa basta con cambiar ese archivo y los logos.

## Cómo correrlo localmente

1. Instala las dependencias:
   ```
   pip install -r requirements.txt --break-system-packages
   ```
   (quita `--break-system-packages` si usas un entorno virtual)

2. (Opcional) Carga un cliente y un producto de ejemplo:
   ```
   python3 seed.py
   ```

3. Define la contraseña del usuario y levanta el servidor:
   ```
   export PASSWORD_JOSE=contraseña-de-jose
   export PASSWORD_ELIAS=contraseña-de-elias
   python3 app.py
   ```

4. Abre en el navegador: `http://localhost:5000`

## Estructura del proyecto

```
SICSA-COTIZADOR/
├── app.py               # Rutas de Flask (clientes, productos, cotizaciones, login)
├── empresa_config.py    # Datos de la empresa, folio, usuarios, logos y colores
├── models.py            # Modelos de base de datos (SQLAlchemy)
├── pdf_generator.py     # Generación del PDF de cotización
├── image_extractor.py   # Lee nombre/precio de una foto con IA (OpenAI)
├── link_extractor.py    # Intenta leer nombre/imagen/precio de un link
├── seed.py              # Datos de ejemplo
├── static/img/          # logo_sicsa.png (horizontal) e icono_chef.png (cuadrado)
└── templates/           # Pantallas HTML
```

## Flujo de trabajo

1. Da de alta los clientes (y, si quieres, productos frecuentes en `/productos`).
2. Crea una cotización: elige cliente y agrega productos. Puedes escribirlos a
   mano, elegirlos del catálogo, pegar un link o pegar/arrastrar una foto
   (la IA intenta leer nombre y precio).
3. Revisa la vista previa, descarga el PDF y mándalo al cliente.
4. Marca la cotización como enviada, aprobada o cancelada según avance.

## Desplegar en Render (mismo patrón que N|B Cotizador)

1. **Sube el proyecto a un repo nuevo de GitHub** (ej. `SICSA-COTIZADOR`).
   No lo subas al repo de N|B: cada empresa debe tener su repo y su servicio.

2. **En Render**, crea un nuevo "Web Service" apuntando a ese repo. Render
   detecta `requirements.txt` y `Procfile` automáticamente.

3. **Agrega un disco persistente** (sin esto se pierden los datos en cada deploy):
   - "Disks" → "Add Disk", móntalo en `/var/data`.

4. **Variables de entorno**:
   - `DATA_DIR` → `/var/data`
   - `SECRET_KEY` → una cadena aleatoria larga (distinta a la de N|B)
   - `PASSWORD_JOSE` → contraseña de José Antonio
   - `PASSWORD_ELIAS` → contraseña de Elías Ruiz
     (si agregas más usuarios en `empresa_config.py`, cada uno lleva su variable)
   - `OPENAI_API_KEY` → la misma llave de OpenAI que usa N|B Cotizador
   - `FLASK_DEBUG` → `false`

5. Las tablas se crean solas al arrancar. Render te da una URL tipo
   `https://sicsa-cotizador.onrender.com`.

## Notas técnicas

- Base de datos: SQLite (`sicsa_cotizador.db` dentro de `DATA_DIR`).
- El folio es automático y nunca se repite, aunque se borre la última cotización.
- IVA fijo en 16%. Máximo 40 productos por cotización; el PDF reparte 8 por hoja.
- La importación por link no es 100% confiable (Amazon, Mercado Libre y otros
  sitios la bloquean); siempre se puede corregir a mano antes de guardar.
