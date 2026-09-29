# UML Class Diagram Generator — Especificación técnica y general

> Documento de referencia del proyecto `uml_excalidraw.py`.
>
> Esta documentación describe el comportamiento y la implementación de la versión actual del script proporcionado para el proyecto. Se centra tanto en el uso general como en los detalles técnicos necesarios para mantener, ampliar o diagnosticar la herramienta.

---

## 1. Descripción general

`uml_excalidraw.py` es una herramienta de línea de comandos escrita en Python que analiza de forma estática un proyecto que contenga código **Python y/o Java** y genera un diagrama UML de clases.

El programa **no ejecuta el proyecto analizado**. Para Python utiliza el AST (`ast`) y para Java realiza un análisis estructural basado en texto, expresiones regulares y control de llaves, paréntesis, corchetes y genéricos.

El flujo general es:

```text
Proyecto Python / Java
        ↓
Búsqueda de archivos .py / .java
        ↓
Exclusión de archivos y directorios
        ↓
Análisis de las clases
        ↓
Construcción del modelo interno
        ↓
Inferencia de relaciones UML
        ↓
Organización automática del diagrama
        ↓
Escena Excalidraw
        ↓
SVG en memoria
        ↓
PNG
```

El resultado puede ser:

- una imagen `.png` para visualizar o compartir;
- un archivo `.excalidraw` editable en Excalidraw.

---

## 2. Objetivos del proyecto

La herramienta está diseñada para:

- documentar la estructura de proyectos de software;
- visualizar clases, atributos y métodos;
- mostrar relaciones entre clases;
- crear diagramas automáticamente sin dibujarlos a mano;
- producir una versión gráfica y una versión editable;
- funcionar con proyectos que mezclen Python y Java;
- mantener el diagrama relativamente ordenado incluso cuando contiene muchas clases.

El resultado es una **representación automática basada en el código fuente**, por lo que no pretende sustituir una revisión humana en proyectos complejos o en código altamente dinámico.

---

## 3. Archivo principal y ejecución

El archivo de aplicación es:

```text
uml_excalidraw.py
```

El script se ejecuta directamente con Python.

Ejemplo básico:

```bash
python3 uml_excalidraw.py
```

Esto analiza el directorio actual.

También puede indicarse otra carpeta:

```bash
python3 uml_excalidraw.py /ruta/al/proyecto
```

El nombre usado en este documento es `uml_excalidraw.py`, aunque el archivo fuente proporcionado durante el desarrollo puede haber tenido un nombre temporal diferente.

---

## 4. Requisitos

### 4.1. Python

La implementación utiliza características modernas de Python, incluyendo:

- `dataclasses`;
- anotaciones de tipos modernas;
- `ast`;
- `pathlib`;
- `argparse`.

El README del proyecto establece **Python 3.10 o superior** como requisito.

### 4.2. Conversión a PNG

El programa crea internamente un SVG y después intenta convertirlo a PNG.

El orden de preferencia es:

1. **CairoSVG**.
2. `rsvg-convert`.
3. ImageMagick (`magick` o `convert`).

CairoSVG puede instalarse con:

```bash
python3 -m pip install cairosvg
```

También puede instalarse mediante `uv`:

```bash
uv add cairosvg
```

Si no hay ninguno de los tres conversores disponibles, el análisis y la construcción del diagrama siguen siendo posibles, pero la exportación PNG falla y el programa devuelve código de salida `1`.

El archivo SVG intermedio **no se conserva en disco** durante la exportación normal.

---

## 5. Bibliotecas y módulos utilizados

El script utiliza solamente bibliotecas estándar de Python salvo el conversor opcional de PNG.

### Bibliotecas estándar

- `argparse`: interfaz de línea de comandos.
- `ast`: análisis sintáctico de Python.
- `json`: creación del archivo Excalidraw.
- `math`: geometría, tamaños y cálculos del layout.
- `os`: recorrido de directorios.
- `re`: análisis estructural y búsqueda de patrones, especialmente en Java.
- `shutil`: localización de programas externos.
- `subprocess`: ejecución de conversores externos.
- `sys`: interacción con terminal y código de salida.
- `tempfile`: archivo SVG temporal cuando se usa un conversor externo.
- `collections.defaultdict`: agrupación de relaciones y conexiones.
- `dataclasses`: modelos de datos.
- `fnmatch`: patrones de exclusión.
- `pathlib.Path`: manejo de rutas.
- `xml.sax.saxutils.escape`: escape del texto para SVG.

### Dependencia opcional

- `cairosvg`: conversión directa de SVG a PNG desde memoria.

---

## 6. Estructura interna del programa

El programa está dividido conceptualmente en seis bloques:

```text
Configuración
   ↓
Modelo de datos
   ↓
Análisis de código fuente
   ↓
Modelo visual y layout
   ↓
Escena Excalidraw
   ↓
SVG / PNG + CLI
```

Las clases principales son:

```text
FieldInfo
MethodInfo
ClassInfo
Relation
ProjectAnalyzer
ClassModel
Box
EdgePath
Block
DiagramLayout
ExcalidrawBuilder
SvgRenderer
```

---

# 7. Configuración global

## 7.1. Directorios ignorados automáticamente

La búsqueda no entra en estos directorios:

```text
.git
.hg
.svn
.venv
venv
env
ENV
__pycache__
.mypy_cache
.pytest_cache
.ruff_cache
node_modules
dist
build
.tox
.idea
.vscode
site-packages
target
out
```

Además, durante el recorrido se ignoran directorios cuyo nombre:

- termina en `.egg-info`;
- comienza por `.`.

## 7.2. Clases ignoradas por defecto

Por defecto se excluye la clase Java:

```text
Main
```

La lista puede reemplazarse mediante `--ignore-class`.

## 7.3. Tipos ignorados por defecto

Por defecto se ignora:

```text
Scanner
```

principalmente para evitar que una línea como:

```java
Scanner scanner = new Scanner(System.in);
```

introduzca ruido innecesario en el UML.

La lista puede reemplazarse mediante `--ignore-type`.

---

# 8. Parámetros visuales

El programa define constantes para el tamaño del texto, cajas y layout.

| Constante | Valor | Propósito |
|---|---:|---|
| `FONT_SIZE` | 14 | Texto general |
| `TITLE_FONT_SIZE` | 18 | Nombre de clase |
| `STEREOTYPE_FONT_SIZE` | 12 | Estereotipos |
| `LABEL_FONT_SIZE` | 11 | Etiquetas de relaciones |
| `LINE_HEIGHT` | 19.0 | Altura aproximada de líneas |
| `CHAR_WIDTH` | 8.6 | Anchura estimada de carácter monoespaciado |
| `PAD_X` | 14 | Margen horizontal interno |
| `PAD_Y` | 8 | Margen vertical interno |
| `BOX_MIN_WIDTH` | 220 | Anchura mínima de una clase |
| `BOX_MAX_WIDTH` | 560 | Anchura máxima calculada |
| `HORIZONTAL_GAP` | 70 | Separación horizontal |
| `BASE_VERTICAL_GAP` | 90 | Separación vertical base |
| `LANE_SPACING` | 12 | Separación entre lanes de relaciones |
| `CANVAS_MARGIN` | 60 | Margen del lienzo |
| `BLOCK_GAP` | 100 | Separación entre componentes |
| `DEFAULT_MAX_ROW_WIDTH` | 3200 | Anchura máxima de una fila de layout |

La fuente declarada para el renderizado SVG es:

```text
DejaVu Sans Mono, Menlo, Consolas, Courier New, monospace
```

---

# 9. Modelo de datos

## 9.1. `FieldInfo`

Representa un atributo.

Campos:

```python
name: str
type_name: str = ""
visibility: str = "+"
default: str | None = None
source: str = "instance"
```

`source` puede representar:

- `class`: atributo declarado en el cuerpo de la clase;
- `instance`: atributo creado dentro de un método (`self.x` / `this.x`);
- `enum`: constante de un enum.

La visibilidad se expresa con la convención UML:

```text
+ público
- privado
# protegido
~ package / visibilidad de paquete en Java
```

## 9.2. `MethodInfo`

Representa un método o constructor.

Campos:

```python
name
visibility
parameters
return_type
is_static
is_classmethod
is_property
is_async
is_abstract
```

Estos datos permiten mostrar modificadores y características especiales en la caja UML.

## 9.3. `ClassInfo`

Es el modelo principal de una clase detectada.

Contiene:

```text
name
module
qualname
file
lineno
kind
is_abstract
extra_stereotypes
bases
interfaces
imports
fields
methods
field_relations
used_types
pending
```

`kind` puede ser:

```text
class
interface
enum
record
```

`qualname` identifica de manera más precisa a la clase y permite representar clases anidadas.

## 9.4. `Relation`

Representa una relación entre dos clases.

Campos:

```python
source
 target
kind
label
multiplicity
```

Tipos de relación reconocidos:

```text
inheritance
realization
composition
aggregation
association
dependency
```

La prioridad utilizada para consolidar relaciones entre un mismo par de clases es:

| Relación | Prioridad |
|---|---:|
| inheritance | 100 |
| realization | 95 |
| composition | 80 |
| aggregation | 70 |
| association | 60 |
| dependency | 40 |

Cuando varias relaciones describen el mismo par `source → target`, se conserva la de mayor prioridad. Las etiquetas y multiplicidades disponibles pueden conservarse al fusionar relaciones.

---

# 10. Descubrimiento de archivos

`ProjectAnalyzer.analyze()` inicia la lectura del proyecto recorriendo el árbol de directorios.

Solo se consideran archivos cuyo nombre termina en:

```text
.py
.java
```

La búsqueda es recursiva.

Los nombres se ordenan de forma estable usando una comparación insensible a mayúsculas/minúsculas.

Cada archivo queda clasificado como:

- analizado (`scanned_files`);
- ignorado (`ignored_files`).

El propio archivo del generador se excluye cuando se detecta que su ruta coincide con `Path(__file__)`.

---

# 11. Exclusiones definidas por el usuario

La opción `--exclude` acepta patrones tipo glob.

Ejemplo:

```bash
python3 uml_excalidraw.py ./mi_proyecto --exclude 'tests/*'
```

Puede repetirse:

```bash
python3 uml_excalidraw.py ./mi_proyecto \
    --exclude 'tests/*' \
    --exclude '**/test_*.py'
```

La comprobación considera:

- la ruta relativa completa;
- el nombre del archivo;
- un tratamiento especial para patrones que empiezan por `**/`.

---

# 12. Nombres de módulos

Para Python, el nombre del módulo se obtiene a partir de la ruta relativa al proyecto y se eliminan extensiones.

Un `__init__.py` no se incluye como último componente del módulo.

Para Java, primero se intenta obtener el `package` declarado en el archivo. Cuando no existe, se usa la estructura de directorios relativa al proyecto como alternativa.

---

# 13. Lectura de archivos

El programa intenta leer archivos primero como:

```text
utf-8-sig
```

Si existe un error de decodificación, reintenta con:

```text
latin-1
```

Cuando un archivo no puede leerse, el error se registra y el procesamiento continúa con los siguientes archivos.

---

# 14. Análisis de Python

Python se analiza con el módulo estándar `ast`.

El código fuente se convierte en un árbol sintáctico con:

```python
ast.parse(source, filename=str(path))
```

Si existe un `SyntaxError`, el archivo se registra como error y no se analiza.

## 14.1. Importaciones

Se recogen importaciones mediante `_collect_python_imports()`.

Se contemplan:

```python
import paquete
import paquete.subpaquete
import paquete as alias

from paquete import Clase
from paquete import Clase as Alias
```

También se tienen en cuenta imports relativos.

Los imports se guardan para ayudar a resolver relaciones internas posteriormente.

## 14.2. Clases detectadas

El parser recorre clases de nivel superior y también puede localizar clases anidadas.

La clase anidada conserva una cualificación basada en la cadena de clases exteriores.

Ejemplo conceptual:

```text
modulo.ClaseExterior.ClaseInterior
```

## 14.3. Herencia y clases especiales

Se inspeccionan las clases base.

La herramienta puede reconocer como `enum` las clases que heredan de alguno de estos tipos:

```text
Enum
IntEnum
StrEnum
Flag
IntFlag
```

Puede tratar una clase derivada de `Protocol` como `interface`.

Puede marcar una clase como abstracta cuando:

- hereda de `ABC`;
- utiliza `ABCMeta` como metaclase;
- contiene un método marcado con `abstractmethod`.

## 14.4. `dataclass`

Si la clase posee un decorador `dataclass`, se añade el estereotipo:

```text
«dataclass»
```

## 14.5. Atributos de clase

Se reconocen asignaciones como:

```python
class Usuario:
    nombre: str
    edad = 20
```

El tipo puede obtenerse de una anotación o inferirse de determinados valores.

## 14.6. Atributos de instancia

Se analizan asignaciones realizadas sobre `self`, por ejemplo:

```python
self.usuario = usuario
self.cliente: Cliente = cliente
```

Los atributos nuevos encontrados dentro de métodos se representan como atributos de instancia.

## 14.7. Inferencia básica del tipo de valor

Cuando no existe una anotación explícita, se reconocen algunos casos frecuentes:

```text
llamada a Clase(...)       → nombre de la clase/llamada
None                      → None
bool/int/float/str/etc.   → tipo del valor Python
list / comprensión       → list
set / comprensión        → set
dict / comprensión       → dict
tuple                    → tuple
```

La inferencia no pretende resolver todos los tipos posibles del lenguaje Python.

## 14.8. Métodos Python

Se analizan `FunctionDef` y `AsyncFunctionDef`.

Se muestran:

- nombre;
- visibilidad;
- parámetros;
- tipos anotados;
- retorno;
- `staticmethod`;
- `classmethod`;
- `property`;
- `cached_property`;
- `async`;
- `abstractmethod`.

No se muestran métodos que correspondan a:

- setters;
- deleters;
- `overload`.

Los nombres ocultos pueden filtrarse mediante `--no-private`.

Los parámetros `self` y `cls` se omiten de la firma visible.

Se mantienen argumentos posicionales, `*args`, argumentos keyword-only y `**kwargs`.

## 14.9. Valores por defecto

Los valores por defecto de parámetros se obtienen intentando descompilar el AST con `ast.unparse()` y se recortan para evitar textos excesivamente largos.

## 14.10. Expresiones y objetos utilizados

Las llamadas a clases dentro de métodos se registran como tipos utilizados.

Esto permite crear dependencias aunque la clase usada no sea un atributo.

---

# 15. Análisis de Java

Java no se procesa con un parser Java externo. Se utiliza un analizador estructural propio.

La implementación combina:

- expresiones regulares;
- texto enmascarado;
- seguimiento de llaves;
- seguimiento de paréntesis;
- seguimiento de corchetes;
- reconocimiento limitado de genéricos.

## 15.1. Enmascarado del código

Antes del análisis estructural se crean vistas del código para evitar que comentarios y literales confundan las llaves y otros símbolos.

Se contemplan:

```text
// comentarios
/* comentarios */
"cadenas"
'caracteres'
```

El texto enmascarado conserva su longitud y sus saltos de línea para que las posiciones y números de línea sigan siendo utilizables.

## 15.2. Declaraciones Java

Se reconocen:

```text
class
interface
enum
record
```

Las declaraciones se estudian mediante la expresión estructural equivalente a:

```text
(class|interface|enum|record) Nombre
```

También se detectan clases anidadas mediante sus intervalos de llaves.

## 15.3. `package` e imports

Se analiza el `package` y los imports no estáticos.

Los imports quedan almacenados en el `ClassInfo` para ayudar a resolver tipos.

## 15.4. Clases abstractas

Una clase Java se marca como abstracta cuando se detecta el modificador `abstract` asociado a su declaración.

## 15.5. `extends` e `implements`

Java mantiene por separado:

```text
bases
interfaces
```

Por tanto:

- `extends` alimenta las relaciones de herencia;
- `implements` alimenta las relaciones de realización (`realization`).

## 15.6. Records

Cuando se detecta un `record`, sus componentes se incorporan como atributos de instancia.

Ejemplo conceptual:

```java
record Usuario(String nombre, int edad) {}
```

produce atributos equivalentes a:

```text
- nombre: String
- edad: int
```

## 15.7. Enums

El analizador intenta identificar las constantes del enum antes de procesar sus miembros.

Las constantes se almacenan como campos con `source="enum"`.

Ejemplo:

```java
enum Estado {
    ACTIVO,
    INACTIVO
}
```

produce entradas equivalentes a:

```text
+ ACTIVO
+ INACTIVO
```

## 15.8. Campos Java

Se reconocen declaraciones de campos con sus modificadores principales:

```text
public
protected
private
static
final
transient
volatile
abstract
synchronized
native
strictfp
```

La visibilidad se calcula antes de eliminar los modificadores del texto.

## 15.9. Parámetros Java

Los parámetros se muestran como:

```text
nombre: Tipo
```

También se procesan anotaciones y algunos modificadores comunes.

## 15.10. Métodos y constructores Java

Se obtiene:

- visibilidad;
- nombre;
- parámetros;
- retorno;
- `static`;
- `abstract`.

Un método cuyo nombre coincide con el de su clase se considera constructor y no recibe tipo de retorno.

Los constructores aparecen primero en el listado de métodos.

## 15.11. Inicializadores y objetos creados

Las expresiones `new Tipo(...)` se registran como usos de tipos.

Cuando una asignación inicializa un campo con un objeto nuevo, se puede representar composición.

También existen detecciones específicas para:

```java
this.campo = new Clase(...);
```

además de casos donde un campo recibe un parámetro, utilizados para inferir agregación cuando el campo puede resolverse.

---

# 16. Resolución de nombres entre clases

Una de las fases más importantes ocurre después de analizar todos los archivos.

## 16.1. Índice por nombre corto

Se crea un índice:

```text
nombre corto → lista de nombres cualificados
```

Esto permite buscar una clase cuando solo se conoce su nombre simple.

## 16.2. Resolución cualificada

La resolución intenta, en orden general:

1. encontrar directamente el nombre completo;
2. buscar dentro de los espacios de nombres de clases anidadas;
3. utilizar los imports del archivo;
4. comprobar nombres cualificados por sufijo;
5. buscar por nombre corto cuando la coincidencia es única;
6. preferir una coincidencia dentro del mismo módulo cuando existe una única.

Esto reduce las relaciones incorrectas producidas por nombres repetidos.

Si no existe una resolución suficientemente clara, no se genera la relación interna.

---

# 17. Relaciones UML

La inferencia se realiza después de conocer todas las clases.

## 17.1. Herencia

Se crea cuando una clase deriva de otra clase detectada.

En un caso Python, por ejemplo:

```python
class Administrador(Usuario):
    pass
```

produce una relación de herencia.

En Java se usa `extends`.

## 17.2. Realización

Se utiliza cuando una clase implementa o realiza una interfaz.

En Java procede de `implements`.

En algunos casos Python también puede clasificarse una relación como realización si la clase objetivo está identificada como interfaz.

## 17.3. Composición

Se considera composición cuando el código crea directamente una instancia que queda asociada a un atributo.

Python:

```python
self.cliente = Cliente()
```

Java:

```java
this.cliente = new Cliente();
```

También se consideran determinadas inicializaciones de campos con `new`.

## 17.4. Agregación

Se utiliza cuando un objeto es entregado desde fuera y queda almacenado como parte de la clase.

Python puede detectar, por ejemplo:

```python
self.cliente = cliente
```

cuando `cliente` tiene una anotación de tipo resoluble.

Java puede identificar patrones donde `this.campo` recibe un parámetro del método, intentando resolver posteriormente el tipo del campo.

## 17.5. Asociación

Se crea a partir de atributos tipados que hacen referencia a otra clase.

Ejemplo:

```python
class Pedido:
    cliente: Cliente
```

## 17.6. Dependencia

Puede surgir por:

- parámetros;
- tipos de retorno;
- creación de objetos;
- tipos usados dentro de métodos;
- referencias encontradas durante el análisis.

Las dependencias son la relación de prioridad más baja y son las primeras que pueden eliminarse con `--no-dependencies`.

---

# 18. Multiplicidad

La estructura `Relation` permite representar multiplicidad.

Actualmente se utiliza principalmente:

```text
0..*
```

cuando el atributo se identifica como una colección o array.

El detector considera patrones asociados a tipos como:

```text
list
set
tuple
dict
map
queue
deque
stack
vector
collection
iterable
sequence
```

y arrays representados mediante `[]`.

Ejemplo conceptual:

```python
clientes: list[Cliente]
```

puede generar una asociación con multiplicidad `0..*`.

---

# 19. Eliminación de relaciones duplicadas

Las relaciones se almacenan con una clave:

```text
(source, target)
```

Si el mismo par de clases produce varias relaciones:

- se conserva la de mayor prioridad;
- si la nueva relación es de mayor prioridad pero no tiene etiqueta, puede recuperar la etiqueta de la anterior;
- si la existente no tiene etiqueta y la nueva sí, se conserva la nueva etiqueta.

Esto evita llenar el diagrama con múltiples flechas entre las mismas clases.

---

# 20. Modelo visual de una clase

Después del análisis, cada `ClassInfo` se convierte en un `ClassModel`.

El modelo visual contiene:

```text
título
estereotipo
líneas de atributos
líneas de métodos
ancho
alto
alto de cabecera
alto del compartimento de atributos
alto del compartimento de métodos
```

## 20.1. Estructura visual

Una caja UML se divide aproximadamente en:

```text
┌──────────────────────────────┐
│        estereotipo           │
│         Nombre               │
├──────────────────────────────┤
│ atributos                    │
├──────────────────────────────┤
│ métodos                      │
└──────────────────────────────┘
```

## 20.2. Atributos

Los atributos siguen un formato similar a:

```text
+ nombre: Tipo
```

Los valores por defecto de atributos de clase pueden mostrarse como:

```text
+ nombre: Tipo = valor
```

Las constantes de enum se muestran principalmente como nombre y valor opcional.

## 20.3. Métodos

Se muestran modificadores especiales como estereotipos:

```text
«abstract»
«static»
«classmethod»
«property»
«async»
```

Pueden aparecer combinados.

Una firma larga se divide en varias líneas para mantener la caja dentro del ancho máximo previsto.

---

# 21. Layout automático

El layout se implementa en `DiagramLayout`.

La clase se describe internamente como un layout **estilo Sugiyama** con routing ortogonal.

## 21.1. Componentes conectados

Primero se construye un grafo de adyacencia no dirigido a partir de las relaciones.

Después se calculan componentes conectados.

Esto permite separar el proyecto en grupos independientes.

Las clases aisladas se tratan como un bloque de cuadrícula.

## 21.2. Jerarquía

Para herencia y realización se considera una dirección jerárquica:

```text
base / interfaz
       ↓
subclase / implementación
```

Para las demás relaciones se utiliza una dirección general de propietario hacia elemento usado.

## 21.3. Ruptura de ciclos

Antes de calcular capas se eliminan temporalmente las aristas de retroceso del grafo de layering cuando forman ciclos.

Esto permite construir una estructura acíclica para la organización vertical sin eliminar la relación original del diagrama final.

## 21.4. Capas

Se utiliza un cálculo de capas basado en caminos largos para colocar nodos conectados en niveles.

Las raíces jerárquicas se ajustan para quedar próximas a sus descendientes.

## 21.5. Reducción de cruces

Las clases dentro de cada capa se reordenan mediante barridos repetidos y cálculo de posiciones promedio de sus vecinos.

El objetivo es reducir cruces de líneas sin modificar las relaciones reales.

## 21.6. División en filas

Cuando una capa supera `max_row_width`, se divide visualmente en varias filas.

La separación horizontal utiliza `HORIZONTAL_GAP`.

## 21.7. Posicionamiento

Las clases se posicionan intentando mantener:

- el orden calculado;
- las distancias mínimas;
- la cercanía respecto a los centros de las clases conectadas.

Se realizan varios barridos arriba/abajo para estabilizar la posición.

## 21.8. Routing de relaciones

Las relaciones pueden clasificarse según su situación relativa:

```text
side
arch
vertical
```

Las líneas pueden usar:

- segmentos horizontales;
- segmentos verticales;
- puntos intermedios;
- lanes entre filas.

Los extremos de varias relaciones se distribuyen a lo largo de un lado de la caja para evitar que coincidan todos en el mismo punto.

## 21.9. Lanes

Cuando varias relaciones atraviesan el mismo espacio entre filas, el algoritmo divide el espacio en lanes.

`LANE_SPACING` controla la separación entre lanes.

El número de lanes influye en la altura necesaria entre filas.

## 21.10. Bloques independientes

Los componentes conectados se empaquetan como bloques.

Los bloques se ordenan por tamaño y se organizan en filas respetando `DEFAULT_MAX_ROW_WIDTH` o el valor proporcionado por `--max-width`.

---

# 22. Escena Excalidraw

`ExcalidrawBuilder` convierte el layout en una escena compatible con Excalidraw.

La escena contiene:

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "https://excalidraw.com",
  "elements": [...],
  "appState": {...},
  "files": {}
}
```

## 22.1. Elementos de clase

Cada clase se representa con:

- un rectángulo;
- líneas divisorias;
- texto para el estereotipo;
- texto para el nombre;
- texto para atributos;
- texto para métodos.

Las partes de una clase comparten un identificador de grupo.

## 22.2. Relaciones

Las relaciones se representan mediante elementos `arrow` con varios puntos.

Las puntas utilizadas son:

| Tipo | Inicio | Final |
|---|---|---|
| inheritance | — | triángulo vacío |
| realization | — | triángulo vacío |
| composition | rombo sólido | — |
| aggregation | rombo vacío | — |
| association | — | flecha |
| dependency | — | flecha |

`realization` y `dependency` utilizan línea discontinua.

## 22.3. Etiquetas

Las relaciones reciben como etiqueta principal el nombre del campo o, según el caso, la información asociada disponible.

Las multiplicidades, cuando existen, se añaden a la etiqueta.

Las dependencias no muestran etiqueta de relación en el renderizador final.

---

# 23. Identificadores y bindings de Excalidraw

Las cajas reciben identificadores internos.

Las relaciones se enlazan con sus cajas mediante:

- `startBinding`;
- `endBinding`.

Los bindings guardan:

```text
elementId
focus
gap
fixedPoint
mode
```

Esto facilita que las relaciones queden asociadas a las clases dentro de Excalidraw.

Los elementos también incorporan campos de estado compatibles con el formato de Excalidraw, incluyendo versión, nonce, grupos y estado de bloqueo.

---

# 24. Renderizado SVG

`SvgRenderer` convierte la escena interna en SVG.

El documento SVG incluye:

- dimensiones completas del canvas;
- fondo blanco;
- rectángulos para clases;
- paths para líneas y flechas;
- polígonos para puntas especiales;
- texto escapado XML.

## 24.1. Rectángulos

Las clases se dibujan con:

- fondo claro;
- borde oscuro;
- grosor de borde `2`;
- esquinas redondeadas.

## 24.2. Líneas

Las rutas se construyen como:

```text
M x1 y1 L x2 y2 L x3 y3 ...
```

Esto permite representar rutas con múltiples segmentos.

## 24.3. Texto

El texto se dibuja con una fuente monoespaciada y se escapan caracteres XML para evitar que contenido del proyecto rompa el SVG.

Los espacios se convierten en espacios no separables para conservar la indentación de firmas largas.

## 24.4. Flechas y símbolos

El renderizador dibuja directamente:

- triángulos vacíos;
- rombos sólidos;
- rombos vacíos;
- puntas de flecha.

Esto evita depender exclusivamente de markers SVG para todos los tipos de relación.

---

# 25. Exportación PNG

La función `export_png()` recibe el SVG generado en memoria y la ruta final del PNG.

El factor `scale`:

- tiene un valor predeterminado de `2.0`;
- tiene un mínimo efectivo de `0.25`;
- queda limitado según las dimensiones del diagrama para evitar un tamaño extremo superior a aproximadamente `20000` unidades en la dimensión mayor.

## 25.1. CairoSVG

Es la primera opción.

Se utiliza directamente sobre bytes del SVG, sin necesidad de guardar el SVG en disco.

## 25.2. rsvg-convert

Si CairoSVG no está disponible, se crea un SVG temporal y se intenta localizar:

```text
rsvg-convert
```

## 25.3. ImageMagick

Como tercer intento se busca:

```text
magick
convert
```

Si el conversor externo falla, se devuelve un mensaje indicando el problema.

El archivo temporal utilizado para el SVG externo se elimina finalmente cuando es posible.

---

# 26. Interfaz de línea de comandos

La interfaz se construye mediante `argparse`.

## 26.1. Sintaxis general

```bash
python3 uml_excalidraw.py [proyecto] [opciones]
```

## 26.2. Argumento `project`

Es opcional.

Predeterminado:

```text
.
```

Ejemplo:

```bash
python3 uml_excalidraw.py
```

## 26.3. `-o`, `--output`

Define la ruta base de salida, sin necesidad de indicar una extensión.

Ejemplo:

```bash
python3 uml_excalidraw.py ./mi_proyecto -o docs/uml
```

Puede pasarse incluso una ruta que termine en `.png` o `.excalidraw`; el programa elimina esa extensión para calcular la ruta base.

Las rutas relativas se resuelven respecto al **directorio de trabajo actual**, no respecto al proyecto analizado.

Predeterminado:

```text
./uml_class_diagram
```

## 26.4. `--no-private`

Oculta miembros privados y protegidos.

Por defecto se incluyen.

En Python:

- nombres `_x` se consideran protegidos;
- nombres `__x` se consideran privados;
- nombres especiales `__x__` se conservan como públicos/especiales.

En Java se filtran campos y métodos de visibilidad `private` y `protected`.

## 26.5. `--no-dependencies`

Elimina las relaciones de tipo:

```text
dependency
```

después de haber terminado el análisis.

Su finalidad es reducir el ruido visual en diagramas grandes.

## 26.6. `--exclude PATTERN`

Excluye rutas que coincidan con un patrón.

Puede repetirse.

## 26.7. `--ignore-class NAME`

Añade nombres de clases Java a la lista de clases que no se representan.

Puede repetirse.

Cuando se utiliza esta opción, la lista suministrada sustituye la configuración predeterminada, por lo que una clase como `Main` deja de ignorarse automáticamente a menos que vuelva a incluirse en la lista.

## 26.8. `--ignore-type NAME`

Define tipos Java que no deben generar determinadas relaciones/atributos de ruido, como el tratamiento especial de `Scanner`.

Puede repetirse y sustituye la lista predeterminada.

## 26.9. `--max-width`

Controla la anchura máxima de las filas de layout.

Predeterminado:

```text
3200
```

Ejemplo:

```bash
python3 uml_excalidraw.py . --max-width 2500
```

## 26.10. `--scale`

Controla el factor de escala usado al crear el PNG.

Predeterminado:

```text
2.0
```

Ejemplo:

```bash
python3 uml_excalidraw.py . --scale 1.5
```

## 26.11. `--excalidraw`

Fuerza la creación del archivo `.excalidraw` sin mostrar una pregunta interactiva.

## 26.12. `--no-excalidraw`

Evita completamente la creación del `.excalidraw` sin mostrar una pregunta.

`--excalidraw` y `--no-excalidraw` son mutuamente excluyentes.

---

# 27. Comportamiento de la salida Excalidraw

Si no se especifica `--excalidraw` ni `--no-excalidraw`, el programa decide según el entorno.

### Terminal interactiva

Pregunta al usuario:

```text
Create the .excalidraw file? [Y/n]:
```

Se consideran afirmativas las respuestas vacía, `y`, `yes`, `s`, `si` y `sí`.

### Entorno no interactivo

Cuando la entrada estándar no es interactiva, el archivo `.excalidraw` se crea automáticamente.

---

# 28. Archivos de salida

Si la base es:

```text
uml_class_diagram
```

se pueden obtener:

```text
uml_class_diagram.png
uml_class_diagram.excalidraw
```

Con:

```bash
python3 uml_excalidraw.py ./mi_proyecto -o docs/diagrama
```

la salida será:

```text
docs/
├── diagrama.png
└── diagrama.excalidraw
```

El directorio padre se crea automáticamente cuando no existe.

---

# 29. Mensajes de ejecución

Durante el procesamiento, el programa informa de:

```text
Analysing project: ...
Files analysed : N
Files ignored  : N
Classes found  : N
Relations      : N
```

Cuando existen errores:

```text
Errors         : N
  - ...
```

Después informa de la generación del PNG e indica el conversor usado.

Si el PNG no puede generarse, informa de las alternativas disponibles.

---

# 30. Códigos de salida

La función principal devuelve los siguientes casos relevantes.

| Código | Situación |
|---:|---|
| `0` | La generación principal termina correctamente y el PNG fue creado |
| `1` | No se encontraron clases o falló la creación del PNG |
| `2` | El directorio del proyecto no existe o no es válido |

Los errores individuales de lectura o sintaxis de archivos no detienen necesariamente todo el análisis: se almacenan y el proceso continúa.

---

# 31. Comportamiento cuando no hay clases

Si ningún archivo produce una clase válida, se muestra:

```text
No Python/Java classes were found in the project.
```

El proceso termina con código `1`.

---

# 32. Gestión de errores

El analizador intenta continuar ante errores locales.

### Error de lectura

Se registra en `errors` y se continúa con el siguiente archivo.

### Error sintáctico de Python

Se registra el número de línea y se ignora ese archivo para el modelo.

### Llaves desbalanceadas en Java

Se registra el archivo y la línea de la declaración problemática cuando es posible.

### Error de exportación

El PNG puede fallar sin impedir que se haya construido la escena interna.

---

# 33. Orden de los métodos

En Python, el constructor `__init__` se coloca primero.

En Java, un constructor se identifica por coincidir su nombre con el de la clase y se coloca antes que los demás métodos.

En la representación visual, el resto de los métodos conserva un orden derivado del análisis.

---

# 34. Recorte de texto

Para evitar que textos demasiado largos deformen el diagrama existen dos niveles principales de recorte.

### Tipos y anotaciones

Los tipos se pueden limitar a aproximadamente 60 caracteres durante el formateo.

### Valores y líneas

Las líneas visuales están limitadas por `MAX_CHARS`, calculado a partir de la anchura máxima de las cajas y la anchura estimada de caracteres.

Cuando un texto supera el límite se usa:

```text
…
```

Las firmas con muchos parámetros utilizan varias líneas en lugar de depender únicamente del recorte.

---

# 35. Convenciones UML visibles

La herramienta sigue estas convenciones básicas:

```text
+ público
- privado
# protegido
~ package
```

Los estereotipos usan la notación:

```text
«nombre»
```

Por ejemplo:

```text
«interface»
«enum»
«record»
«abstract»
«dataclass»
```

Además, algunos modificadores de método se muestran dentro de un único bloque de estereotipos.

---

# 36. Casos de uso recomendados

## 36.1. Diagrama rápido del proyecto actual

```bash
python3 uml_excalidraw.py
```

## 36.2. Diagrama de una carpeta concreta

```bash
python3 uml_excalidraw.py ./mi_proyecto
```

## 36.3. Sin atributos privados/protegidos

```bash
python3 uml_excalidraw.py ./mi_proyecto --no-private
```

## 36.4. Menos líneas de dependencia

```bash
python3 uml_excalidraw.py ./mi_proyecto --no-dependencies
```

## 36.5. Ignorar pruebas

```bash
python3 uml_excalidraw.py ./mi_proyecto --exclude 'tests/*'
```

## 36.6. Salida en documentación

```bash
python3 uml_excalidraw.py ./mi_proyecto -o docs/uml
```

## 36.7. Generación automática de Excalidraw

```bash
python3 uml_excalidraw.py ./mi_proyecto --excalidraw
```

## 36.8. Solo PNG

```bash
python3 uml_excalidraw.py ./mi_proyecto --no-excalidraw
```

## 36.9. PNG de mayor o menor escala

```bash
python3 uml_excalidraw.py ./mi_proyecto --scale 1
```

---

# 37. Ejemplo conceptual de análisis

Para un proyecto:

```text
mi_proyecto/
├── usuario.py
├── pedido.py
├── servicio.py
└── tests/
    └── test_pedido.py
```

con:

```python
class Usuario:
    pass
```

```python
class Pedido:
    cliente: Usuario
```

```python
class Servicio:
    def crear(self, usuario: Usuario) -> Pedido:
        return Pedido()
```

el resultado conceptual puede incluir:

```text
Usuario
   ↑
Pedido ───────→ Usuario
   ↑
Servicio - - -→ Pedido
      - - - - → Usuario
```

El archivo dentro de `tests/` puede excluirse mediante `--exclude`.

El diagrama final dependerá del conjunto completo de clases y relaciones detectadas.

---

# 38. Limitaciones conocidas del análisis

## 38.1. Python

El análisis es estático. Por ello puede no descubrir correctamente relaciones creadas exclusivamente mediante:

- metaprogramación;
- reflexión;
- asignaciones extremadamente dinámicas;
- tipos construidos en tiempo de ejecución;
- información que solo existe después de ejecutar el programa.

La herramienta no intenta ejecutar el proyecto para resolver estos casos.

## 38.2. Java

El analizador Java no utiliza un parser Java completo. Es un análisis estructural propio.

Por tanto, construcciones Java excepcionalmente complejas pueden no reconocerse con precisión total.

## 38.3. Ambigüedad de nombres

Cuando existe más de una clase con el mismo nombre corto y no puede resolverse de forma suficientemente clara, la relación puede omitirse.

## 38.4. Relaciones UML

La herramienta representa relaciones que puede deducir del texto fuente y del modelo construido. No pretende descubrir automáticamente toda la semántica arquitectónica de un sistema.

---

# 39. Consideraciones de mantenimiento

Los cambios importantes suelen corresponder a uno de estos bloques:

```text
ProjectAnalyzer
    → reconocimiento y relaciones

build_model
    → contenido y tamaño de cada caja

DiagramLayout
    → posición y routing

ExcalidrawBuilder
    → estructura editable

SvgRenderer
    → apariencia final del PNG

export_png
    → conversión a imagen

main
    → CLI y flujo de ejecución
```

Una modificación en el análisis no debería obligar a cambiar el renderizador si `ClassInfo` y `Relation` continúan siendo compatibles.

De forma similar, el layout trabaja sobre `ClassModel`, `Box` y `Relation`, por lo que puede cambiarse la posición de las cajas sin modificar la lógica que identifica clases.

---

# 40. Inventario de clases principales

## `ProjectAnalyzer`

Responsable de:

- recorrer el proyecto;
- leer archivos;
- analizar Python;
- analizar Java;
- indexar nombres;
- resolver nombres internos;
- inferir relaciones.

## `ClassModel`

Modelo visual listo para dibujarse.

## `DiagramLayout`

Responsable de:

- componentes;
- capas;
- ordenamiento;
- posiciones;
- filas;
- routing;
- tamaño final del canvas.

## `ExcalidrawBuilder`

Convierte el modelo visual en una escena Excalidraw.

## `SvgRenderer`

Convierte la escena en SVG.

## `FieldInfo`, `MethodInfo`, `ClassInfo`, `Relation`, `Box`, `EdgePath`, `Block`

Son contenedores de datos usados por las distintas fases.

---

# 41. Inventario de funciones y responsabilidades

## `ProjectAnalyzer`

```text
__init__
analyze
_iter_source_files
_is_excluded
_module_name
_parse_file
_build_name_index
_match_qualified
_resolve_internal
_is_many
_infer_relations
_merge_relation
_type_names
_type_names_from_display_signature
_truncate
_collect_python_imports
_walk_python_body
_extract_python_class
_skip_python_attr
_skip_hidden
_flatten_targets
_leaves
_param_annotations
_decorator_name
_method_info
_format_parameters
_names_from_method_signature
_called_class_name
_expr_name
_format_annotation
_infer_value_type
_safe_unparse
_visibility
_blank
_java_views
_blank_pattern
_find_matching_brace
_split_spans
_split_java_top_level
_has_top_level_assignment
_remove_angles
_java_visibility
_java_type_name
_parse_java_file
_parse_enum_constants
_parse_java_members
_parse_java_fields
_java_matching_paren
_parse_java_method
_format_java_parameters
```

## Funciones de modelo y visualización

```text
_clip
field_line
method_lines
build_model
```

## `DiagramLayout`

```text
__init__
run
_new_box
_components
_grid_block
_break_cycles
_layout_component
_order_layers
_resolve_row
_place_rows
_route
```

## `ExcalidrawBuilder`

```text
__init__
build
_add_class
_add_edges
_add_labels
_id
_base
_text
```

## `SvgRenderer`

```text
__init__
render
_render_path
_render_text
```

## Funciones de exportación y CLI

```text
export_png
display_path
main
```

---

# 42. Flujo técnico completo

El flujo real de la aplicación puede resumirse así:

```text
main()
 │
 ├─ procesa argumentos
 │
 ├─ valida el directorio
 │
 ├─ prepara la ruta de salida
 │
 ├─ crea ProjectAnalyzer
 │
 ├─ analyze()
 │   │
 │   ├─ recorre archivos
 │   ├─ filtra exclusiones
 │   ├─ analiza Python / Java
 │   ├─ construye clases
 │   └─ infiere relaciones
 │
 ├─ opcionalmente elimina dependencies
 │
 ├─ build_model() para cada clase
 │
 ├─ DiagramLayout.run()
 │   │
 │   ├─ componentes
 │   ├─ layering
 │   ├─ ordenamiento
 │   ├─ posicionamiento
 │   └─ routing
 │
 ├─ ExcalidrawBuilder.build()
 │
 ├─ SvgRenderer.render()
 │
 ├─ export_png()
 │
 └─ opcionalmente guarda .excalidraw
```

---

# 43. Dependencias entre módulos conceptuales

Aunque todo está implementado actualmente en un único script, las responsabilidades forman esta arquitectura lógica:

```text
                 ┌─────────────────────┐
                 │       CLI main      │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │  ProjectAnalyzer    │
                 │ Python + Java       │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ ClassInfo / Relation│
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │   build_model       │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │   DiagramLayout     │
                 └──────────┬──────────┘
                            │
                  ┌─────────┴─────────┐
                  ▼                   ▼
       ┌──────────────────┐  ┌─────────────────┐
       │ ExcalidrawBuilder│  │ Edge routing    │
       └─────────┬────────┘  └─────────────────┘
                 │
                 ▼
       ┌──────────────────┐
       │   SvgRenderer    │
       └─────────┬────────┘
                 │
                 ▼
       ┌──────────────────┐
       │   export_png     │
       └──────────────────┘
```

---

# 44. Características que no dependen de ejecución del proyecto

El programa no necesita:

- iniciar el servidor de la aplicación;
- ejecutar tests;
- importar el proyecto como módulo Python;
- compilar el proyecto Java;
- ejecutar una JVM;
- ejecutar scripts del proyecto.

La información proviene del código fuente y del análisis estructural implementado en el generador.

---

# 45. Seguridad del análisis

El diseño estático evita que el código del proyecto analizado sea ejecutado por el generador.

Esto significa que una clase con código como:

```python
os.remove(...)
```

o:

```java
Runtime.getRuntime()...
```

no se ejecuta durante el análisis normal.

La única ejecución externa que puede realizar el programa corresponde a herramientas del sistema usadas para convertir el SVG a PNG (`rsvg-convert`, `magick` o `convert`).

---

# 46. Decisiones de diseño relevantes

## No ejecutar proyectos

Se decidió basar el análisis en el código fuente para que la generación sea predecible y no dependa del estado de ejecución del proyecto.

## Mantener relaciones separadas del layout

`Relation` se crea antes del posicionamiento, lo que permite cambiar el layout sin cambiar la lógica de análisis.

## Separar escena Excalidraw y SVG

El mismo modelo visual puede convertirse en un archivo editable y también en una imagen.

## Eliminar dependencias de bajo nivel en diagramas grandes

La opción `--no-dependencies` permite conservar las relaciones estructurales más importantes y reducir el ruido visual.

---

# 47. Estructura recomendada del repositorio

La implementación actual puede convivir con una estructura sencilla como:

```text
proyecto/
├── uml_excalidraw.py
├── README.md
├── docs/
│   └── PROJECT_SPECIFICATION.md
└── uml_class_diagram.png
```

El archivo `PROJECT_SPECIFICATION.md` está pensado como documentación completa de referencia, mientras que `README.md` puede mantenerse como guía de usuario rápida.

---

# 48. Diferencia entre documentación general y técnica

El `README.md` debe centrarse en:

- qué hace la herramienta;
- requisitos básicos;
- instalación;
- ejemplos;
- uso habitual;
- opciones más importantes;
- archivos generados.

Este documento, en cambio, contiene:

- comportamiento interno;
- modelo de datos;
- reglas de detección;
- relaciones;
- detalles del layout;
- rendering;
- exportación;
- flujo de ejecución;
- códigos de salida;
- limitaciones;
- inventario de funciones.

---

# 49. Referencia rápida de CLI

```text
python3 uml_excalidraw.py [project]

Opciones:
  -o, --output PATH
  --no-private
  --no-dependencies
  --exclude PATTERN
  --ignore-class NAME
  --ignore-type NAME
  --max-width INT
  --scale FLOAT
  --excalidraw
  --no-excalidraw
```

Predeterminados principales:

```text
project       = .
output        = ./uml_class_diagram
max-width     = 3200
scale         = 2.0
ignored class = Main
ignored type  = Scanner
```

---

# 50. Ejemplo de ejecución completa

```bash
python3 uml_excalidraw.py ./mi_proyecto \
    --exclude 'tests/*' \
    --no-private \
    --no-dependencies \
    --max-width 3000 \
    --scale 2 \
    --excalidraw \
    -o ./docs/uml
```

La ejecución realiza, en orden:

1. analiza `./mi_proyecto`;
2. omite rutas que coincidan con `tests/*`;
3. oculta miembros privados y protegidos;
4. elimina las relaciones de dependencia del resultado final;
5. limita el layout a aproximadamente 3000 unidades por fila;
6. genera el PNG con escala `2`;
7. crea obligatoriamente `docs/uml.excalidraw`;
8. genera `docs/uml.png` si hay un conversor disponible.

---

# 51. Compatibilidad funcional resumida

| Función | Soporte |
|---|---|
| Proyectos Python | Sí |
| Proyectos Java | Sí |
| Proyectos mixtos | Sí |
| Subdirectorios | Sí |
| Clases anidadas Python | Sí |
| Clases anidadas Java | Sí |
| Interfaces Java | Sí |
| Enums Python | Sí |
| Enums Java | Sí |
| Records Java | Sí |
| `dataclass` | Sí |
| Clases abstractas | Sí |
| Herencia | Sí |
| Realización | Sí |
| Composición | Sí |
| Agregación | Sí |
| Asociación | Sí |
| Dependencia | Sí |
| Multiplicidad `0..*` | Sí |
| PNG | Sí, con conversor disponible |
| Excalidraw | Sí |
| Exclusiones | Sí |
| Ocultar privados | Sí |
| Omitir dependencias | Sí |
| Personalizar clases ignoradas | Sí |
| Personalizar tipos ignorados | Sí |
| Escala PNG | Sí |
| Ancho máximo del layout | Sí |

---

# 52. Conclusión

`uml_excalidraw.py` combina tres funciones principales en una sola herramienta:

```text
1. Analizar código fuente
2. Organizar automáticamente un modelo UML
3. Exportarlo como PNG y Excalidraw
```

Su parte de análisis distingue varias estructuras de Python y Java y trata de inferir relaciones entre las clases. El motor de layout organiza componentes conectados por capas, reduce cruces y utiliza rutas ortogonales para las conexiones. Finalmente, el modelo se transforma en una escena compatible con Excalidraw y en un SVG que puede convertirse a PNG.

La herramienta debe entenderse como un **generador automático de documentación estructural**, no como un compilador ni como un analizador semántico completo del lenguaje Python o Java.

---

# 53. Fuente de referencia de esta especificación

Esta documentación se elaboró a partir del código fuente actual de `uml_excalidraw.py` proporcionado para el proyecto y de su README asociado.

No se han añadido aquí funcionalidades externas que no estén respaldadas por esa implementación.
