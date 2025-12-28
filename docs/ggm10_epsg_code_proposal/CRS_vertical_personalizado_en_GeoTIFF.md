# CRS vertical personalizado en GeoTIFF: un estudio de caso

**Fecha:** Diciembre de 2025  
**Asunto:** Documentación sobre las limitaciones en el almacenamiento de un datum vertical personalizado en el formato GeoTIFF  
**Ejemplo:** Geoide Gravimétrico Mexicano 2010 (GGM10)  

## Resumen ejecutivo

Este documento describe el comportamiento de un sistema de referencia de coordenadas vertical personalizado (no-EPSG) en el formato GeoTIFF. Demuestra cómo la información del datum se transforma durante el ciclo de escritura/lectura y explora las implicaciones para las organizaciones que emplean este tipo de datum vertical.

## Antecedentes

El Instituto Nacional de Estadística y Geografía (INEGI) de México utiliza el Geoide Gravimétrico Mexicano 2010 (GGM10) como su datum vertical oficial. Este datum no cuenta actualmente con un código EPSG, lo que requiere el uso de definiciones WKT personalizadas al trabajar con datos de elevación.

## La definición del CRS vertical personalizado

### Definición completa WKT2_2019

El datum vertical GGM10 puede ser descrito completamente utilizando el formato WKT2:

```wkt
VERTCRS["GGM10 height",
    VDATUM["Geoide Gravimétrico Mexicano 2010"],
    CS[vertical,1],
        AXIS["gravity-related height (H)",up,
            LENGTHUNIT["metre",1]],
    USAGE[
        SCOPE["Geodesy, engineering survey, topographic mapping."],
        AREA["Mexico - onshore and offshore."],
        BBOX[14.02,-118.98,32.98,-86.02]],
    ID["INEGI","GGM2010"]]
```

### CRS compuesto con componente horizontal

Cuando se combina con un CRS horizontal (p. ej., Mexico ITRF2008 / UTM zona 13N), la definición completa se convierte en:

```wkt
COMPOUNDCRS["Mexico ITRF2008 / UTM zone 13N + GGM10 height",
    PROJCRS["Mexico ITRF2008 / UTM zone 13N",
        BASEGEOGCRS["Mexico ITRF2008",
            DATUM["Mexico ITRF2008",
                ELLIPSOID["GRS 1980",6378137,298.257222101,
                    LENGTHUNIT["metre",1]]],
            PRIMEM["Greenwich",0,
                ANGLEUNIT["degree",0.0174532925199433]],
            ID["EPSG",6365]],
        CONVERSION["UTM zone 13N",
            METHOD["Transverse Mercator",
                ID["EPSG",9807]],
            PARAMETER["Latitude of natural origin",0,
                ANGLEUNIT["degree",0.0174532925199433],
                ID["EPSG",8801]],
            PARAMETER["Longitude of natural origin",-105,
                ANGLEUNIT["degree",0.0174532925199433],
                ID["EPSG",8802]],
            PARAMETER["Scale factor at natural origin",0.9996,
                SCALEUNIT["unity",1],
                ID["EPSG",8805]],
            PARAMETER["False easting",500000,
                LENGTHUNIT["metre",1],
                ID["EPSG",8806]],
            PARAMETER["False northing",0,
                LENGTHUNIT["metre",1],
                ID["EPSG",8807]]],
        CS[Cartesian,2],
            AXIS["(E)",east,
                ORDER[1],
                LENGTHUNIT["metre",1]],
            AXIS["(N)",north,
                ORDER[2],
                LENGTHUNIT["metre",1]],
        USAGE[
            SCOPE["Engineering survey, topographic mapping."],
            AREA["Mexico between 108°W and 102°W, onshore and offshore."],
            BBOX[14.05,-108,31.79,-102]],
        ID["EPSG",6368]],
    VERTCRS["GGM10 height",
        VDATUM["Geoide Gravimétrico Mexicano 2010"],
        CS[vertical,1],
            AXIS["gravity-related height (H)",up,
                LENGTHUNIT["metre",1]],
        USAGE[
            SCOPE["Geodesy, engineering survey, topographic mapping."],
            AREA["Mexico - onshore and offshore."],
            BBOX[14.02,-118.98,32.98,-86.02]],
        ID["INEGI","GGM2010"]]]
```

## Comportamiento observado en GeoTIFF

### Lo que se escribe

Usando la API de Python de GDAL, la definición completa de WKT2 puede ser analizada y escrita exitosamente en un archivo GeoTIFF:

```python
from osgeo import osr, gdal

# Parse custom vertical CRS
vert_srs = osr.SpatialReference()
vert_srs.ImportFromWkt(custom_ggm10_wkt)

# Verify parsing was successful
print(vert_srs.GetName())  # Output: "GGM10 height"
print(vert_srs.GetAttrValue("VERT_DATUM"))  # Output: "Geoide Gravimétrico Mexicano 2010"

# Create compound CRS and write to GeoTIFF
compound_srs = osr.SpatialReference()
compound_srs.SetCompoundCS(name, horizontal_srs, vert_srs)
ds.SetProjection(compound_srs.ExportToWkt(['FORMAT=WKT2_2019']))
```

En esta etapa, toda la información del datum se conserva en memoria.

### Lo que se lee de vuelta

Cuando el mismo archivo es leído usando gdalinfo o la API de GDAL:

```bash
$ gdalinfo -wkt_format WKT2_2019 elevation.tif
```

El componente vertical se devuelve como:

```wkt
VERTCRS["GGM10 height",
    VDATUM["unknown"],
    CS[vertical,1],
        AXIS["up",up,
            LENGTHUNIT["metre",1,
                ID["EPSG",9001]]]]
```

**Diferencias clave:**

- `VDATUM["Geoide Gravimétrico Mexicano 2010"]` → `VDATUM["unknown"]`
- `AXIS["gravity-related height (H)",up]` → `AXIS["up",up]`
- Se pierden los metadatos de `USAGE`, `SCOPE`, `AREA` y `BBOX`.
- Se pierde el ID personalizado `ID["INEGI","GGM2010"]`.

### Salida WKT1

Al consultar con el formato WKT1:

```bash
$ gdalinfo elevation.tif
```

La salida muestra:

```wkt
VERT_CS["GGM10 height",
    VERT_DATUM["unknown",2005],
    UNIT["metre",1,
        AUTHORITY["EPSG","9001"]],
    AXIS["Up",UP]]
```

El código numérico 2005 es el valor de GeoKey para "otro datum vertical/ortométrico", un valor genérico de respaldo.

## Explicación técnica

### Mecanismo de almacenamiento GeoKey

GeoTIFF almacena la información del sistema de referencia de coordenadas usando GeoKeys numéricas (etiquetas TIFF 34735-34737). Este sistema fue diseñado para codificar eficientemente los sistemas de coordenadas definidos por EPSG:

Cada datum, elipsoide y componente del sistema de coordenadas tiene un identificador numérico.

Las descripciones de texto se almacenan por separado en la etiqueta 34737 (GeoAsciiParamsTag).

El sistema funciona excelentemente para componentes registrados en EPSG.

### Limitación para un datum personalizado

En el caso de un datum vertical personalizado sin código EPSG:

No existe una GeoKey numérica para representar "Geoide Gravimétrico Mexicano 2010".

GDAL utiliza códigos genéricos de respaldo (p. ej., VerticalDatumGeoKey = 32767 para "definido por el usuario").

El VerticalCSTypeGeoKey utiliza por defecto el valor 2005 ("otro").

La información detallada (nombre del datum, descripción del eje, área de uso) no puede ser codificada.

Esta es una **limitación del formato**, no un error de software. La especificación GeoTIFF fue diseñada en torno a los códigos EPSG.

## Comparación con un datum codificado por EPSG

A modo de comparación, así es como se comporta el Datum Vertical Norteamericano de 1988 (NAVD88) (EPSG:5703):

### Entrada WKT2

```wkt
VERTCRS["NAVD88 height",
    VDATUM["North American Vertical Datum 1988"],
    CS[vertical,1],
        AXIS["gravity-related height (H)",up,
            LENGTHUNIT["metre",1]],
    ID["EPSG",5703]]
```

### Salida desde GeoTIFF

```wkt
VERTCRS["NAVD88 height",
    VDATUM["North American Vertical Datum 1988"],
    CS[vertical,1],
        AXIS["gravity-related height (H)",up,
            LENGTHUNIT["metre",1]],
    USAGE[
        SCOPE["Geodesy, engineering survey, topographic mapping."],
        AREA["Mexico - onshore. United States (USA) - CONUS and Alaska - onshore - Alabama; Alaska; Arizona; Arkansas; California; Colorado; Connecticut; Delaware; Florida; Georgia; Idaho; Illinois; Indiana; Iowa; Kansas; Kentucky; Louisiana; Maine; Maryland; Massachusetts; Michigan; Minnesota; Mississippi; Missouri; Montana; Nebraska; Nevada; New Hampshire; New Jersey; New Mexico; New York; North Carolina; North Dakota; Ohio; Oklahoma; Oregon; Pennsylvania; Rhode Island; South Carolina; South Dakota; Tennessee; Texas; Utah; Vermont; Virginia; Washington; West Virginia; Wisconsin; Wyoming."],
        BBOX[14.51,172.42,71.4,-66.91]],
    ID["EPSG",5703]]
```

Toda la información se conserva (con información de USAGE añadida) porque EPSG:5703 tiene asignaciones de GeoKey definidas.

## Soluciones alternativas actuales

### 1. Almacenamiento de metadatos

El software puede almacenar la definición WKT2 completa en un campo de metadatos personalizado de GDAL:

```python
ds.SetMetadataItem('COMPOUND_CRS_WKT2', full_wkt2_string)
```

Esto preserva la información, pero requiere que las aplicaciones la recuperen explícitamente:

```python
full_wkt = ds.GetMetadataItem('COMPOUND_CRS_WKT2')
```

Los metadatos son visibles en la salida de gdalinfo bajo GDAL_METADATA (etiqueta 42112).

### 2. Archivos externos complementarios (sidecar)

Los archivos de Metadatos Auxiliares Persistentes (PAM) de GDAL, .aux.xml, pueden almacenar información adicional del CRS, aunque esto requiere la gestión de archivos separados.

### 3. Formatos alternativos

Formatos como GeoPackage soportan cadenas WKT completas directamente y no están limitados por la codificación de GeoKey. Sin embargo, esto requiere abandonar el uso de GeoTIFF.

## Implicaciones

### Para productores de datos (INEGI)

Los datos de elevación de México distribuidos con el datum vertical GGM10 enfrentan desafíos de interoperabilidad:

Los usuarios internacionales pueden no entender "VERT_DATUM[unknown]".

Es posible que el software no reconozca el datum vertical.

Los flujos de procesamiento automatizado pueden fallar o producir resultados incorrectos.

La riqueza de los metadatos (USAGE, SCOPE, AREA) se pierde en la distribución.

### Para desarrolladores de software

Las aplicaciones que trabajan con este tipo de datum vertical deben:

- Implementar un manejo especial para sistemas verticales no-EPSG.
- Considerar el almacenamiento del WKT completo en campos de metadatos personalizados.
- Documentar claramente las limitaciones para los usuarios finales.
- Potencialmente, ofrecer formatos de archivo alternativos.

### Para usuarios finales

Al trabajar con datos que emplean un datum vertical personalizado, los usuarios deben:

- Ser conscientes de que la información del datum puede estar incompleta en las cabeceras de GeoTIFF.
- Verificar la existencia de etiquetas de metadatos personalizadas o archivos auxiliares.
- Considerar la documentación del datum proporcionada por los productores de datos.
- Entender que las transformaciones de coordenadas pueden no funcionar automáticamente.

## Camino a seguir

### A corto plazo: documentación y metadatos

La solución alternativa de metadatos demostrada (COMPOUND_CRS_WKT2) proporciona una solución práctica dentro de las limitaciones actuales de GeoTIFF. Los productores de datos pueden adoptar este enfoque para preservar la información del datum.

### A largo plazo: registro en EPSG

La solución más robusta es el registro en EPSG de un datum personalizado. Para el GGM10, esto implicaría:

1. Una presentación formal al Conjunto de Datos de Parámetros Geodésicos (Geodetic Parameter Dataset) de EPSG.
2. La asignación de código(s) oficial(es) de EPSG para:
  - El datum vertical GGM10.
  - El CRS vertical GGM10.
  - Los parámetros de transformación entre GGM10 y otros datum verticales.
3. Reconocimiento universal por todo el software basado en GDAL.

El registro en EPSG proporciona:
- Estandarización y reconocimiento internacional.
- Soporte automático por parte del software sin necesidad de código personalizado.
- Preservación de todos los metadatos a través de la codificación GeoKey.
- Distribución y uso de datos simplificados.

### Futuras versiones de GeoTIFF

La comunidad de GeoTIFF podría considerar un soporte mejorado para el datum vertical en futuras versiones de la especificación. Los enfoques potenciales podrían incluir:

- Rangos de GeoKey extendidos para un datum personalizado.
- Almacenamiento opcional de cadenas WKT como fuente primaria del CRS.
- Enfoques híbridos que mantengan la compatibilidad con versiones anteriores.

Sin embargo, cualquier cambio requeriría una cuidadosa consideración de la compatibilidad retroactiva y el impacto en el ecosistema.

## Conclusión

La transformación de la información de un datum vertical personalizado en archivos GeoTIFF es el resultado de la dependencia del formato en la codificación numérica de GeoKey. Aunque existen soluciones alternativas, la solución más efectiva a largo plazo es el registro formal en EPSG de los datum personalizados como el GGM10.

Este estudio de caso demuestra el valor de la estandarización geodésica internacional y los beneficios prácticos del registro en EPSG para las agencias cartográficas nacionales de todo el mundo.

## Apéndice: comandos de prueba

### Creación de un GeoTIFF con GGM10 usando el GeoTIFF ToolKit (GTTK)

```bash
python gttk optimize \
    -i input_dem.tif \
    -o output_dem.tif \
    -t dem \
    -s GGM10 \
    --verbose
```

### Inspección del resultado

```bash
# Ver en formato WKT2
gdalinfo -wkt_format WKT2_2019 output_dem.tif

# Ver en formato WKT1 (por defecto)
gdalinfo output_dem.tif

# Ver todos los metadatos, incluyendo campos personalizados
gdalinfo -mdd all output_dem.tif | grep COMPOUND_CRS_WKT2
gdalinfo -mdd all output_dem.tif | findstr /I CUSTOM_CRS_WKT2  # Windows cmd
```

### Recuperación programática del WKT completo

```python
from osgeo import gdal

ds = gdal.Open('output_dem.tif')

# CRS estándar (limitado por la codificación GeoKey)
standard_wkt = ds.GetSpatialRef().ExportToWkt(['FORMAT=WKT2_2019'])

# CRS completo desde metadatos personalizados (si están almacenados)
full_wkt = ds.GetMetadataItem('COMPOUND_CRS_WKT2')

if full_wkt:
    print("La información completa del datum vertical está disponible en los metadatos")
```

*Este documento fue preparado para facilitar la discusión dentro de la comunidad geoespacial sobre el soporte de un datum vertical personalizado en GeoTIFF. Las preguntas y comentarios son bienvenidos.*
