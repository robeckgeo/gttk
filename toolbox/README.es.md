[English](README.md) | **Español**

# Guía de instalación de la caja de herramientas GTTK para ArcGIS Pro

Esta guía explica cómo instalar y configurar la caja de herramientas de Python de GTTK para
ArcGIS Pro.

## Contenido

- [Requisitos previos](#requisitos-previos)
- [Instalación de OSGeo4W](#instalación-de-osgeo4w-dependencia-obligatoria)
  - [Instrucciones de instalación](#instrucciones-de-instalación)
  - [Configuración posterior a la instalación](#configuración-posterior-a-la-instalación)
  - [Verificar la instalación](#verificar-la-instalación)
  - [Instalar QGIS con OSGeo4W](#instalar-qgis-con-osgeo4w)
  - [Solución de problemas](#solución-de-problemas)
- [Configuración del entorno de Python](#configuración-del-entorno-de-python)
- [Agregar la caja de herramientas](#agregar-la-caja-de-herramientas)
- [Idioma de la caja de herramientas](#idioma-de-la-caja-de-herramientas)
- [Referencia rápida](#referencia-rápida)

---

## Requisitos previos

- **ArcGIS Pro** instalado en el equipo
- **Privilegios de administrador** para instalar OSGeo4W
- **GTTK** clonado o descargado en el equipo

---

## Instalación de OSGeo4W (dependencia obligatoria)

**REQUISITO CRÍTICO**: para que la caja de herramientas funcione correctamente, debe tener
instalado un entorno GDAL independiente. La biblioteca GDAL incluida con ArcGIS Pro usa
ajustes internos que pueden anular las optimizaciones aplicadas mediante la API de Python de
GDAL.

Para evitarlo, GTTK incluye una herramienta especializada (`gttk optimize-arc`) que ejecuta
las utilidades de línea de comandos de GDAL (`gdal_translate`, `gdal_calc.py`, `gdalwarp`,
`gdaladdo`) como subprocesos en un entorno OSGeo4W aislado. Así se obtienen resultados
óptimos manteniendo la compatibilidad con ArcGIS Pro.

GTTK usa OSGeo4W, que da acceso a las funciones y códecs de compresión más recientes de GDAL
sin interferir con el GDAL interno de ArcGIS Pro. Otra ventaja del instalador de OSGeo4W es
que ofrece el software SIG libre [QGIS](https://qgis.org) (véase
[Instalar QGIS con OSGeo4W](#instalar-qgis-con-osgeo4w) más abajo).

> **Nota**: para quien usa la línea de comandos, `gttk optimize-arc` también está disponible
> como herramienta independiente. Consulte el README principal.

### Instrucciones de instalación

#### Paso 1: Descargar el instalador de OSGeo4W

Descargue el instalador adecuado para su sistema:

- **Windows de 64 bits (recomendado)**: [OSGeo4W-v2-setup.exe](http://download.osgeo.org/osgeo4w/v2/osgeo4w-setup.exe)
- **Página oficial de descargas**: [https://trac.osgeo.org/osgeo4w/](https://trac.osgeo.org/osgeo4w/)

> **Nota**: el instalador v2 es la versión moderna y recomendada. Evite el instalador v1
> heredado salvo que tenga un motivo concreto.

#### Paso 2: Ejecutar el instalador

1. **Ejecute** el `osgeo4w-setup.exe` descargado con privilegios de administrador (clic
   derecho → "Ejecutar como administrador").

2. **Elija el tipo de instalación**:
   - **"Express Install"** para una instalación estándar y rápida (recomendada para la
     mayoría de los usuarios), o
   - **"Advanced Install"** para controlar los paquetes uno por uno (usuarios con
     experiencia).

#### Paso 3: Seleccionar paquetes (Express Install)

Si usa la instalación exprés, seleccione:

- ☑ **QGIS Desktop**: incluye QGIS y sus dependencias básicas
- ☑ **GDAL**: Geospatial Data Abstraction Library (requisito principal)

#### Paso 3 alternativo: Seleccionar paquetes (Advanced Install)

Con la instalación avanzada tendrá más control sobre los paquetes:

**Paquetes obligatorios:**

- ☑ **gdal**: biblioteca GDAL (elija la última versión estable)
- ☑ **gdal-python**: enlaces de Python para GDAL
- ☑ **python3-core**: intérprete de Python

**Paquetes recomendados:**

- ☑ **qgis**: aplicación de escritorio QGIS (véase más abajo)
- ☑ **qgis-grass-plugin**: integración con GRASS GIS (opcional)
- ☑ **gdal-ecw**: compatibilidad con el formato ECW (si lo necesita)
- ☑ **gdal-mrsid**: compatibilidad con el formato MrSID (si lo necesita)

**Códecs avanzados** (para disponer de todas las opciones de compresión):

- ☑ **gdal-jxl**: códec JPEG XL
- ☑ **gdal-zstd**: compresión ZSTD
- ☑ **gdal-lerc**: compresión LERC

#### Paso 4: Elegir la ubicación de instalación

- **Ubicación predeterminada**: `C:\OSGeo4W` (recomendada)
- **Ubicación personalizada**: elija una ruta sin espacios ni caracteres especiales
- **Importante**: anote esta ruta; la necesitará para configurar GTTK

#### Paso 5: Completar la instalación

1. Revise los paquetes seleccionados
2. Haga clic en **"Next"** para descargar e instalar
3. Espere a que termine la instalación (puede tardar varios minutos)
4. Haga clic en **"Finish"** al terminar

---

### Configuración posterior a la instalación

#### Configurar GTTK para usar OSGeo4W

Tras la instalación, indique a GTTK dónde está OSGeo4W:

1. **Abra** `config.toml` en el directorio raíz del proyecto GTTK

2. **Localice** la sección `[paths]`:

   ```toml
   [paths]
   # Path to OSGeo4W installation (required for ArcGIS Toolbox)
   osgeo4w = "C:/OSGeo4W"
   ```

3. **Actualice** la ruta `osgeo4w` si instaló OSGeo4W en otra ubicación:

   ```toml
   [paths]
   osgeo4w = "C:/Su/Ruta/Personalizada/OSGeo4W"
   ```

---

### Verificar la instalación

Abra **OSGeo4W Shell** (búsquelo en el menú Inicio) y ejecute:

```bash
# Versión de GDAL
gdalinfo --version

# Controladores disponibles
gdalinfo --formats

# Versión de los enlaces de Python de GDAL
python3 -c "from osgeo import gdal; print(gdal.__version__)"
```

Debería ver:

- Una lista larga de controladores compatibles, entre ellos GTiff y COG
- Una versión de GDAL para Python igual a la de la biblioteca (3.11 o superior, o la última
  disponible)

---

### Instalar QGIS con OSGeo4W

QGIS es una herramienta excelente y muy valiosa en los flujos de trabajo SIG, pero las
instalaciones independientes de QGIS pueden carecer de las dependencias completas de OSGeo4W
que GTTK necesita. El instalador de OSGeo4W ofrece:

- **Un entorno GDAL completo**: todas las bibliotecas, utilidades y dependencias de GDAL
- **Los códecs de compresión más recientes**: JPEG XL (JXL), ZSTD y LERC
- **QGIS como opción**: QGIS figura entre los paquetes seleccionables, así que tendrá ambos
- **Enlaces de Python**: los enlaces de GDAL para Python, para scripts y automatización
- **Actualizaciones coherentes**: un mecanismo de actualización centralizado para todas las
  herramientas geoespaciales
- **Compatibilidad probada**: ampliamente usado en entornos profesionales y gubernamentales

**Ventajas de tener ArcGIS Pro y QGIS:**

- Acceso a herramientas propietarias y de código abierto
- QGIS destaca en ciertas tareas (simbología, integración con PostgreSQL/PostGIS, modelado
  ráster con GDAL, etc.)
- ArcGIS ofrece un amplio conjunto de herramientas cartográficas adoptadas por la industria y
  los gobiernos, además del entorno ArcPy (que usa la caja de herramientas de GTTK)
- Compatibilidad con flujos de análisis que en ArcGIS Pro requieren extensiones con licencia
  adicional (p. ej., Spatial Analyst)
- Cientos de complementos desarrollados por la comunidad
- Transparencia del código abierto y apoyo de la comunidad

---

### Solución de problemas

**Problemas frecuentes y soluciones:**

1. **Error "GDAL not found" en la caja de herramientas de ArcGIS Pro**:
   - Compruebe que la ruta `osgeo4w` de `config.toml` apunta a la ubicación correcta
   - La ruta debe ser el directorio raíz de OSGeo4W (p. ej., `C:/OSGeo4W`)
   - Reinicie ArcGIS Pro después de cambiar la configuración

2. **Errores de códec no disponible (JXL, ZSTD, etc.)**:
   - Vuelva a ejecutar el instalador de OSGeo4W y seleccione los paquetes de códecs avanzados
   - Compruebe que están instalados en `C:\OSGeo4W\bin\gdal\plugins`

3. **Errores de permisos durante la instalación**:
   - Ejecute el instalador como administrador
   - En equipos administrados por una institución, consulte a su departamento de informática
   - Si es necesario, instale en un directorio con permisos de escritura para el usuario

4. **Conflictos de PATH con otras instalaciones de GDAL**:
   - GTTK usa una ruta explícita en su configuración para evitar conflictos
   - NO agregue OSGeo4W al PATH del sistema si tiene otras instalaciones de GDAL
   - GTTK usará la ruta indicada en `config.toml`

5. **`ModuleNotFoundError: No module named 'tifffile'` al cargar la caja de herramientas**:
   - ArcGIS Pro está usando su entorno predeterminado `arcgispro-py3`; el mensaje de error de la
     caja de herramientas indica qué intérprete está en uso
   - Abra el **Administrador de paquetes**, active el entorno clonado y reinicie ArcGIS Pro
   - Tras una actualización de ArcGIS Pro, vuelva a clonar el entorno y reinstale los paquetes

**Ayuda adicional:**

- Guía de usuario de OSGeo4W: [https://trac.osgeo.org/osgeo4w/wiki/TracGuide](https://trac.osgeo.org/osgeo4w/wiki/TracGuide)
- Documentación de GDAL: [https://gdal.org/](https://gdal.org/)
- Incidencias de GTTK: [abra un issue en GitHub](https://github.com/robeckgeo/gttk/issues)

---

## Configuración del entorno de Python

**DEPENDENCIA CRÍTICA**: GTTK necesita el módulo `tifffile` para cargarse, y *Validar
metadatos* necesita `jsonpath-ng` para las reglas PROJJSON. Ninguno de los dos está incluido en
el entorno conda predeterminado de ArcGIS Pro (`arcgispro-py3`), que no se puede modificar, así
que deben instalarse en un entorno clonado.

### Preparar el entorno

1. **En ArcGIS Pro, abra el menú Proyecto** y entre en el **Administrador de paquetes**
   (*Package Manager*). Desde ahí se administran los entornos conda de ArcPy. El entorno
   predeterminado es `arcgispro-py3`.

2. **Clone el entorno predeterminado** en uno nuevo (p. ej., `arcgispro-gttk`). Puede tardar
   un rato. Si la clonación falla, es posible que necesite ayuda de su departamento de
   informática. Si ya tiene un entorno clonado (distinto de `arcgispro-py3`), puede usarlo.

3. **Active el entorno clonado** y abra la pestaña **Agregar paquetes** del Administrador de
   paquetes.

4. **Busque "tifffile"** e instálelo; después haga lo mismo con **"jsonpath-ng"**. Ambos
   están disponibles en los canales de conda predeterminados.

5. **Asegúrese de que ese mismo entorno esté activo** cuando ejecute las herramientas de GTTK
   desde la caja de herramientas. Tras actualizar ArcGIS Pro, vuelva a clonar el entorno: un
   clon creado con una versión anterior no se conserva, y Pro vuelve en silencio al entorno
   predeterminado.

---

## Agregar la caja de herramientas

1. **Agregue la caja de herramientas**: en su proyecto de ArcGIS Pro, abra el panel
   **Catálogo**, haga clic derecho en **Cajas de herramientas** y elija **Agregar caja de
   herramientas**. Navegue hasta la carpeta `toolbox` del directorio raíz del proyecto y
   selecciónela.

2. **Localícela**: la caja de herramientas `GTTK_Toolbox.pyt` aparecerá en la carpeta Cajas
   de herramientas. Expándala para usar las herramientas.

   <img src="../images/arcgis_toolbox_list.png" alt="Lista de herramientas de GTTK_Toolbox.pyt">

---

## Idioma de la caja de herramientas

La caja de herramientas se muestra en español o en inglés. Cada vez que ArcGIS Pro la carga,
elige el idioma en este orden y lo indica en la primera línea de mensajes de cada ejecución:

1. La variable de entorno `GTTK_LANG` (`en` o `es`).
2. `config.toml`: `[gui] language = "auto"` (predeterminado), `"en"` o `"es"`.
3. El idioma elegido en ArcGIS Pro en **Opciones > Idioma** (solo se ofrece si está
   instalado un paquete de idioma de Esri).
4. El idioma de visualización de Windows.

Para forzar un idioma, escriba `language = "es"` (o `"en"`) en `config.toml` y, en el panel
Catálogo, haga clic derecho en la caja de herramientas → **Actualizar**. Se traducen las
etiquetas, las listas de opciones, los mensajes y el panel de ayuda de los parámetros; los
informes y la salida de GDAL permanecen en inglés. La interfaz de ArcGIS Pro en español
requiere el paquete de idioma de Esri (My Esri), que GTTK no necesita.

---

## Referencia rápida

| Paso | Acción |
|------|--------|
| 1 | Instalar OSGeo4W con GDAL |
| 2 | Configurar la ruta de OSGeo4W en `config.toml` |
| 3 | Clonar el entorno de Python de ArcGIS Pro |
| 4 | Instalar `tifffile` y `jsonpath-ng` en el entorno clonado |
| 5 | Agregar la caja de herramientas al proyecto de ArcGIS Pro |
| 6 | (Opcional) Fijar el idioma con `[gui] language` en `config.toml` |
