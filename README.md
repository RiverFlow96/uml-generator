# UML Class Diagram Generator — Excalidraw + PNG

Script de Python para analizar proyectos **Python y Java** sin ejecutar su código y generar automáticamente un **diagrama UML de clases**.

El resultado puede exportarse como:

- **PNG**: imagen del diagrama.
- **`.excalidraw`**: archivo editable directamente en Excalidraw, generado únicamente si el usuario lo confirma al finalizar.

El análisis de Python utiliza el módulo estándar `ast`, mientras que el análisis de Java utiliza un parser estructural basado en expresiones regulares y recorrido de bloques. Por tanto, el proyecto **no necesita ejecutarse** para ser analizado.

---

## Características

El generador identifica, entre otros elementos:

- Clases.
- Interfaces, `enum` y `record` de Java.
- Atributos declarados en clases.
- Atributos de instancia creados mediante `self.x` en Python.
- Métodos y constructores.
- Parámetros de métodos.
- Tipos de parámetros y valores de retorno.
- Visibilidad UML.
- Métodos `static` / `staticmethod` / `classmethod` / `property` / `async` cuando pueden identificarse.
- Herencia.
- Asociaciones mediante anotaciones o tipos.
- Composición mediante instanciación explícita.
- Dependencias mediante parámetros, retornos o creación/uso de objetos.
- Exclusión automática de directorios que normalmente no forman parte del código fuente del proyecto.
- Exclusión mediante patrones `glob` definidos por el usuario.

---

## Requisitos

### Python

Se recomienda utilizar **Python 3.10 o superior**, ya que el proyecto utiliza características modernas del lenguaje como:

- `list[str]`
- `str | None`
- `dataclasses`
- `ast.unparse`
- `Path`

El análisis Python utiliza únicamente módulos de la biblioteca estándar.

### Generación de PNG

Para crear el PNG es necesario disponer de **una** de estas opciones:

1. `CairoSVG` — opción recomendada cuando se trabaja dentro de un entorno Python.
2. `rsvg-convert` — conversor SVG del sistema.
3. ImageMagick (`magick` o `convert`).

La generación de `.excalidraw` no requiere ninguna de estas dependencias.

---

# Instalación

Existen varias formas de instalar y ejecutar el proyecto. No es obligatorio utilizar `uv`.

## Opción A — Con `uv`

Si utilizas [`uv`](https://docs.astral.sh/uv/), la forma recomendada de configurar el proyecto es:

```bash
uv init
uv add cairosvg
```

Después puedes ejecutar el script con:

```bash
uv run python uml_excalidraw.py /ruta/al/proyecto
```

Si el repositorio ya tiene un `pyproject.toml`, normalmente basta con:

```bash
uv add cairosvg
```

### Instalación de `uv`

La instalación de `uv` depende del sistema operativo. Consulta la documentación oficial para instalar la versión apropiada para tu plataforma:

```text
https://docs.astral.sh/uv/
```

---

## Opción B — Sin `uv`, usando `venv` + `pip`

Esta es la alternativa estándar cuando no quieres depender de `uv`.

### Linux / macOS

Desde la carpeta del proyecto:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install cairosvg
```

Después:

```bash
python uml_excalidraw.py /ruta/al/proyecto
```

Para salir del entorno virtual:

```bash
deactivate
```

### Windows — PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install cairosvg
```

Después:

```powershell
python .\uml_excalidraw.py C:\ruta\al\proyecto
```

Para salir:

```powershell
deactivate
```

### Windows — CMD

```cmd
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install cairosvg
```

Después:

```cmd
python uml_excalidraw.py C:\ruta\al\proyecto
```

---

## Opción C — Sin entorno virtual

También puedes instalar `CairoSVG` directamente en la instalación de Python del usuario, aunque para proyectos reales suele ser preferible utilizar un entorno virtual.

### Linux / macOS

```bash
python3 -m pip install --user cairosvg
```

### Windows

```powershell
py -m pip install --user cairosvg
```

Luego puedes ejecutar el script normalmente:

```bash
python uml_excalidraw.py /ruta/al/proyecto
```

En Windows:

```powershell
py .\uml_excalidraw.py C:\ruta\al\proyecto
```

> Si tu distribución de Python impide instalar paquetes globalmente o mediante `--user`, utiliza `venv`.

---

## Opción D — Sin instalar `CairoSVG`

El script intenta generar el PNG utilizando automáticamente, en este orden:

```text
CairoSVG → rsvg-convert → ImageMagick
```

Por tanto, puedes ejecutar el análisis sin instalar `CairoSVG` siempre que tengas un conversor SVG alternativo disponible en el sistema.

La generación del archivo `.excalidraw` no necesita un conversor de imágenes.

Si no existe ningún conversor, el programa seguirá analizando el proyecto y podrá generar el `.excalidraw`, pero mostrará que el PNG no pudo generarse.

---

# Uso básico

La sintaxis general es:

```bash
python uml_excalidraw.py /ruta/al/proyecto
```

En Linux/macOS puede utilizarse `python3`:

```bash
python3 uml_excalidraw.py /ruta/al/proyecto
```

En Windows también es habitual utilizar el lanzador `py`:

```powershell
py .\uml_excalidraw.py C:\ruta\al\proyecto
```

Ejemplo Linux:

```bash
python3 uml_excalidraw.py ./mi_proyecto
```

Ejemplo Windows:

```powershell
py .\uml_excalidraw.py .\mi_proyecto
```

El resultado se crea por defecto dentro del proyecto analizado:

```text
mi_proyecto/
└── uml_class_diagram.png
```

Al finalizar el análisis, el programa pregunta si también debe crear:

```text
uml_class_diagram.excalidraw
```

---

## Especificar la salida

Puedes definir una ruta base diferente mediante `-o` o `--output`:

```bash
python uml_excalidraw.py /ruta/al/proyecto -o docs/uml
```

Se generarán:

```text
docs/
└── uml.png
```

Y, si se confirma la creación del archivo editable:

```text
docs/
└── uml.excalidraw
```

### Importante

La opción `-o` representa una **ruta base**, no necesariamente un archivo con extensión.

Por ejemplo:

```bash
-o docs/mi_diagrama
```

produce:

```text
docs/mi_diagrama.png
docs/mi_diagrama.excalidraw
```

Si se proporciona una extensión, el script la elimina y utiliza igualmente `.png` y `.excalidraw` como extensiones finales.

---

## Ocultar atributos y métodos privados/protegidos

Por defecto se incluyen miembros privados y protegidos.

Para ocultarlos utiliza:

```bash
python uml_excalidraw.py /ruta/al/proyecto --no-private
```

Esto afecta a miembros cuya visibilidad puede determinarse a partir de las convenciones de Python o los modificadores de Java.

En Python se utilizan estas convenciones:

| Nombre | Visibilidad UML |
|---|---|
| `nombre` | `+` público |
| `_nombre` | `#` protegido |
| `__nombre` | `-` privado |
| `__nombre__` | `+` tratado como público/especial |

En Java se interpretan los modificadores:

| Java | UML |
|---|---|
| `public` | `+` |
| `protected` | `#` |
| `private` | `-` |
| sin modificador | `~` |

---

## Excluir archivos o directorios

Puedes excluir rutas utilizando uno o varios patrones `glob` mediante `--exclude`.

Ejemplo:

```bash
python uml_excalidraw.py ./mi_proyecto --exclude 'tests/*'
```

Puedes repetir la opción:

```bash
python uml_excalidraw.py ./mi_proyecto \
  --exclude 'tests/*' \
  --exclude '**/test_*.py'
```

Los patrones son relativos al directorio raíz del proyecto.

En PowerShell:

```powershell
py .\uml_excalidraw.py .\mi_proyecto `
  --exclude 'tests/*' `
  --exclude '**/test_*.py'
```

---

## Directorios ignorados automáticamente

El analizador evita recorrer directorios que normalmente contienen dependencias generadas, cachés, configuraciones o repositorios, entre ellos:

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
```

También se excluye automáticamente **el propio script generador**, si el archivo se encuentra dentro del proyecto analizado. Esto evita que las clases internas del generador aparezcan en el UML del proyecto objetivo.

---

# Ejecutarlo como un comando de Bash / Linux

El script incluye un *shebang* al inicio:

```python
#!/usr/bin/env python3
```

Esto permite ejecutarlo como programa en sistemas Unix/Linux.

## Método 1 — Hacer ejecutable el propio `.py`

Desde la carpeta donde está el script:

```bash
chmod +x uml_excalidraw.py
```

Después:

```bash
./uml_excalidraw.py /ruta/al/proyecto
```

Esta es la solución más sencilla. El `python3` indicado en el *shebang* debe existir en el sistema.

### Ventaja

No necesitas crear otro archivo Bash.

### Limitación

Debes escribir la ruta del script (`./uml_excalidraw.py`) o tener el archivo dentro de un directorio incluido en `PATH`.

---

## Método 2 — Crear un comando global mediante un wrapper Bash

Una forma más cómoda es crear un archivo ejecutable llamado, por ejemplo:

```text
uml-excalidraw
```

Contenido:

```bash
#!/usr/bin/env bash

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/uml_excalidraw.py" "$@"
```

Guárdalo junto al script y dale permisos:

```bash
chmod +x uml-excalidraw
```

Ahora puedes ejecutarlo desde esa carpeta:

```bash
./uml-excalidraw /ruta/al/proyecto
```

La parte importante es:

```bash
"$@"
```

porque permite que todos los argumentos introducidos después del comando se pasen al script Python.

Por ejemplo:

```bash
./uml-excalidraw ./mi_proyecto -o docs/uml --no-private
```

equivale a:

```bash
python3 /ruta/al/script/uml_excalidraw.py ./mi_proyecto -o docs/uml --no-private
```

---

## Método 3 — Convertirlo en un comando disponible desde cualquier carpeta

Puedes colocar el wrapper en un directorio personal de comandos, por ejemplo:

```bash
mkdir -p ~/.local/bin
```

Copia el comando:

```bash
cp uml-excalidraw ~/.local/bin/uml-excalidraw
chmod +x ~/.local/bin/uml-excalidraw
```

Asegúrate de que `~/.local/bin` esté en tu `PATH`:

```bash
echo "$PATH"
```

En muchos sistemas Linux modernos ya está incluido. Si no lo está, añade al archivo de configuración de tu shell, por ejemplo `~/.bashrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Después recarga la configuración:

```bash
source ~/.bashrc
```

Ahora el comando debería poder ejecutarse desde cualquier ubicación:

```bash
uml-excalidraw /ruta/al/proyecto
```

También puedes comprobar qué ejecutable se está utilizando:

```bash
command -v uml-excalidraw
```

---

## Método 4 — Comando global utilizando `uv`

Si el proyecto depende de `uv`, el wrapper puede encargarse de ejecutarlo:

```bash
#!/usr/bin/env bash

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1
exec uv run python uml_excalidraw.py "$@"
```

Con esto puedes instalar el wrapper en `~/.local/bin` y utilizar:

```bash
uml-excalidraw /ruta/al/proyecto
```

El usuario no necesita activar manualmente `.venv`.

> En este caso, `uv` sí debe estar instalado en el sistema.

---

## Método 5 — Comando global sin `uv`, usando el entorno virtual del proyecto

Si prefieres `venv` + `pip`, el wrapper puede utilizar directamente el Python del entorno virtual.

Por ejemplo:

```bash
#!/usr/bin/env bash

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/uml_excalidraw.py" "$@"
```

Después:

```bash
chmod +x uml-excalidraw
```

Y:

```bash
uml-excalidraw /ruta/al/proyecto
```

Este método evita tener que ejecutar previamente:

```bash
source .venv/bin/activate
```

El comando utiliza directamente el intérprete del entorno virtual.

---

# Crear un comando en Windows

Windows no utiliza el sistema de permisos `chmod` de Linux, por lo que las estrategias son diferentes.

## Método 1 — Ejecutar directamente con `py`

La forma más simple es:

```powershell
py .\uml_excalidraw.py C:\ruta\al\proyecto
```

O utilizando `python`:

```powershell
python .\uml_excalidraw.py C:\ruta\al\proyecto
```

---

## Método 2 — Crear un `.cmd`

Puedes crear un archivo:

```text
uml-excalidraw.cmd
```

Contenido:

```bat
@echo off
py "%~dp0uml_excalidraw.py" %*
```

Después puedes ejecutar:

```cmd
uml-excalidraw.cmd C:\ruta\al\proyecto
```

`%~dp0` hace referencia al directorio donde está ubicado el archivo `.cmd`, por lo que no necesitas escribir manualmente la ruta completa del script.

También se pasan todos los argumentos con `%*`.

---

## Método 3 — Crear un comando de PowerShell

Puedes crear un archivo:

```text
uml-excalidraw.ps1
```

Con este contenido:

```powershell
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& py "$ScriptDir\uml_excalidraw.py" $args
exit $LASTEXITCODE
```

Luego:

```powershell
.\uml-excalidraw.ps1 C:\ruta\al\proyecto
```

El wrapper devuelve el mismo código de salida que el programa Python.

> Dependiendo de la política de ejecución configurada en Windows, PowerShell puede impedir inicialmente la ejecución de scripts `.ps1`. En ese caso puedes utilizar el `.cmd` o ajustar la política de ejecución de PowerShell según las políticas de seguridad de tu equipo.

---

## Método 4 — Añadir el comando de Windows al `PATH`

Una vez creado `uml-excalidraw.cmd`, puedes colocar el archivo en un directorio personal de herramientas, por ejemplo:

```text
C:\Users\TU_USUARIO\bin\
```

Después añade ese directorio al `PATH` de Windows.

Una vez actualizado el `PATH`, podrás escribir desde cualquier terminal:

```cmd
uml-excalidraw C:\ruta\al\proyecto
```

Para comprobar dónde se encuentra el comando:

```cmd
where uml-excalidraw
```

En PowerShell también puedes utilizar:

```powershell
Get-Command uml-excalidraw
```

---

# Solución multiplataforma recomendada

Si el objetivo es distribuir el proyecto a usuarios de **Linux y Windows**, hay varias posibilidades.

## Opción 1 — Distribuir el script Python

La opción más sencilla es entregar:

```text
uml-generator/
├── uml_excalidraw.py
├── pyproject.toml
├── README.md
└── ...
```

El usuario instala Python y las dependencias, y ejecuta el script.

Linux:

```bash
python3 uml_excalidraw.py ./proyecto
```

Windows:

```powershell
py .\uml_excalidraw.py .\proyecto
```

### Ventajas

- Fácil de mantener.
- El mismo código funciona en ambos sistemas.
- No requiere compilar una versión específica del programa.

### Desventajas

- El usuario necesita Python.
- Debe instalar las dependencias necesarias.

---

## Opción 2 — Distribuirlo como ejecutable con PyInstaller

Puedes crear un ejecutable independiente utilizando **PyInstaller**.

Instalación:

```bash
python -m pip install pyinstaller
```

Con `uv`:

```bash
uv add --dev pyinstaller
```

Comando de compilación básico:

```bash
python -m PyInstaller --onefile --console --name UML_Excalidraw uml_excalidraw.py
```

Si se quiere incluir CairoSVG y sus recursos detectables por PyInstaller, puede ser necesario añadir sus módulos/recursos explícitamente según la versión instalada.

El ejecutable se coloca normalmente en:

```text
dist/UML_Excalidraw
```

En Windows será normalmente:

```text
dist/UML_Excalidraw.exe
```

### Importante: PyInstaller no produce un único ejecutable universal

Para distribuir en varias plataformas debes construir el programa en cada plataforma objetivo.

Por ejemplo:

```text
Linux  → UML_Excalidraw
Windows → UML_Excalidraw.exe
```

Un ejecutable generado para Linux no se convierte automáticamente en un ejecutable nativo de Windows, y viceversa.

---

## Opción 3 — Ejecutable + comando del sistema

Para una distribución cómoda, puedes combinar PyInstaller con un comando del sistema.

### Linux

Después de generar:

```text
dist/UML_Excalidraw
```

puedes instalarlo en un directorio incluido en el `PATH`, por ejemplo:

```bash
mkdir -p ~/.local/bin
cp dist/UML_Excalidraw ~/.local/bin/uml-excalidraw
chmod +x ~/.local/bin/uml-excalidraw
```

Entonces:

```bash
uml-excalidraw /ruta/al/proyecto
```

### Windows

Puedes colocar:

```text
UML_Excalidraw.exe
```

en un directorio que esté dentro del `PATH` de Windows. Después:

```cmd
uml-excalidraw.exe C:\ruta\al\proyecto
```

De esta forma el usuario no necesita instalar Python ni ejecutar `python` manualmente.

---

## Opción 4 — Distribución mediante releases para cada sistema

Una estructura práctica para GitHub Releases puede ser:

```text
UML-Excalidraw-v1.0.0-linux-x86_64.tar.gz
UML-Excalidraw-v1.0.0-windows-x86_64.zip
```

Cada paquete puede contener su ejecutable y documentación.

Por ejemplo:

```text
UML-Excalidraw/
├── UML_Excalidraw(.exe)
├── README.md
└── ...
```

Esto permite que el usuario descargue directamente la versión correspondiente a su sistema operativo.

---

# Tabla de métodos de ejecución

| Método | Linux | Windows | Requiere Python | Requiere `uv` | Requiere instalación de dependencias |
|---|:---:|:---:|:---:|:---:|:---:|
| `python3 uml_excalidraw.py` | ✅ | — | ✅ | ❌ | ✅/opcional para PNG |
| `py uml_excalidraw.py` | — | ✅ | ✅ | ❌ | ✅/opcional para PNG |
| `uv run ...` | ✅ | ✅ | Gestionado por `uv` | ✅ | Gestionada por `uv` |
| `venv` + `pip` | ✅ | ✅ | ✅ | ❌ | ✅/opcional para PNG |
| Script ejecutable con shebang | ✅ | — | ✅ | ❌ | ✅/opcional para PNG |
| Wrapper Bash | ✅ | Con Git Bash/WSL | ✅ | ❌/✅ | ✅/opcional para PNG |
| `.cmd` / `.ps1` | — | ✅ | ✅ | ❌/✅ | ✅/opcional para PNG |
| PyInstaller | ✅ | ✅ | ❌ para el usuario final | ❌ | Incluidas en el ejecutable según configuración |

---

# Ejemplos

## Proyecto Python

Supongamos el siguiente proyecto:

```text
mi_proyecto/
├── models.py
├── services.py
└── main.py
```

Ejecuta:

```bash
python uml_excalidraw.py ./mi_proyecto
```

El script recorre recursivamente los archivos `.py`, identifica las clases y analiza sus relaciones.

---

## Proyecto Java

Para un proyecto Java:

```text
mi_proyecto/
├── src/
│   ├── Usuario.java
│   ├── Admin.java
│   └── Servicio.java
└── README.md
```

El mismo comando funciona:

```bash
python uml_excalidraw.py ./mi_proyecto
```

El analizador considera los archivos con extensión:

```text
.py
.java
```

Los demás archivos se ignoran.

---

## Proyecto mixto Python + Java

También es posible analizar un directorio que contenga ambos lenguajes:

```text
proyecto/
├── python_app/
│   ├── usuario.py
│   └── servicio.py
└── java_app/
    ├── Usuario.java
    └── Servicio.java
```

Ejemplo:

```bash
python uml_excalidraw.py ./proyecto -o docs/uml
```

---

# Qué detecta el analizador de Python

El código Python se analiza mediante:

```python
ast.parse(...)
```

Esto significa que **el proyecto analizado no se importa ni se ejecuta**.

## Clases

Detecta declaraciones del tipo:

```python
class Usuario:
    pass
```

También conserva el módulo y el nombre cualificado de la clase.

---

## Atributos de clase

Ejemplo:

```python
class Usuario:
    nombre: str = ""
    edad = 18
```

El UML puede representar información equivalente a:

```text
+ nombre: str = ""
+ edad: int = 18
```

Cuando el tipo no puede inferirse de forma suficiente, se utiliza `Any`.

---

## Atributos de instancia

También se detectan atributos creados desde métodos mediante `self`:

```python
class Usuario:
    def __init__(self, nombre: str):
        self.nombre = nombre
        self.activo = True
```

El atributo se incorpora a la clase aunque no exista previamente una declaración de atributo en el cuerpo de la clase.

---

## Métodos

Se detectan funciones definidas dentro de las clases, incluyendo funciones asíncronas.

Ejemplo:

```python
class Servicio:
    def crear(self, usuario: Usuario) -> bool:
        ...

    async def sincronizar(self) -> None:
        ...
```

La representación incluye nombre, parámetros y retorno.

También se identifican decoradores relevantes:

- `@staticmethod`
- `@classmethod`
- `@property`

---

## Herencia

Ejemplo:

```python
class Admin(Usuario):
    pass
```

Se genera una relación UML de **herencia** desde `Admin` hacia `Usuario`.

---

## Asociaciones

Las anotaciones de tipo permiten inferir asociaciones.

Ejemplo:

```python
class Pedido:
    cliente: Cliente
```

Se interpreta como una relación entre `Pedido` y `Cliente`.

---

## Composición

Se intenta identificar composición cuando un atributo recibe una instancia creada directamente.

Ejemplo:

```python
class Pedido:
    def __init__(self):
        self.cliente = Cliente()
```

Se registra una relación de tipo **composición**.

---

## Dependencias

También se detectan dependencias por uso de clases en:

- parámetros de métodos;
- valores de retorno;
- expresiones de creación de objetos como `Clase(...)`.

Ejemplo:

```python
class Servicio:
    def procesar(self, pedido: Pedido) -> Resultado:
        logger = Logger()
```

El análisis puede inferir dependencias hacia `Pedido`, `Resultado` y `Logger`, siempre que dichas clases puedan resolverse dentro del proyecto analizado.

---

# Qué detecta el analizador de Java

La parte Java no utiliza un parser completo del lenguaje. En cambio, realiza un análisis estructural del texto fuente.

Se identifican declaraciones de:

```java
class Usuario { }
interface Repositorio { }
enum Estado { }
record UsuarioDTO(...) { }
```

También intenta obtener:

- paquete;
- clases anidadas;
- herencia mediante `extends`;
- implementación de interfaces mediante `implements`;
- campos;
- modificadores de visibilidad;
- métodos;
- parámetros;
- tipos de retorno;
- creación de objetos mediante `new Clase(...)`;
- algunas composiciones explícitas mediante `this.campo = new Clase(...)`.

---

# Tipos de relaciones UML

El sistema maneja actualmente los siguientes tipos de relación:

| Relación | Prioridad | Representación |
|---|---:|---|
| Herencia | 100 | Flecha con triángulo |
| Composición | 80 | Rombo sólido |
| Agregación | 70 | Rombo |
| Asociación | 60 | Flecha |
| Dependencia | 40 | Flecha discontinua |

Cuando entre dos clases existen varias evidencias de relación, se conserva la relación con mayor prioridad.

---

# Formato generado por Excalidraw

El builder produce una escena JSON compatible con Excalidraw con elementos como:

- rectángulos para clases;
- textos para nombres, atributos y métodos;
- líneas de separación UML;
- flechas para relaciones;
- marcadores UML para composición y herencia.

El resultado `.excalidraw` es editable en Excalidraw.

---

# Generación del PNG

Internamente, el proceso es:

```text
Modelo UML
    ↓
Escena Excalidraw
    ↓
SVG en memoria
    ↓
Conversor SVG → PNG
```

El código primero intenta utilizar `CairoSVG`.

Si no está disponible, busca:

```text
rsvg-convert
```

y posteriormente:

```text
magick
convert
```

La implementación utiliza un archivo SVG temporal únicamente cuando necesita recurrir a un conversor externo, y lo elimina al terminar.

---

# Salida del programa

Durante el análisis se muestran estadísticas similares a:

```text
Analizando proyecto: /ruta/proyecto
  Archivos analizados : 9
  Archivos ignorados  : 14
  Clases encontradas  : 6
  Relaciones          : 7
```

Si existen problemas de lectura o sintaxis, también se muestran:

```text
  Errores             : 2
    - archivo.py:15: sintaxis no válida
```

Al finalizar se informa el resultado de cada archivo generado.

---

# Códigos de salida

El programa devuelve diferentes códigos para facilitar su integración con scripts y herramientas externas.

| Código | Significado |
|---:|---|
| `0` | Ejecución correcta y PNG generado |
| `1` | No se encontraron clases o no fue posible generar el PNG |
| `2` | El directorio del proyecto no existe o no es válido |

---

# Estructura recomendada del proyecto

Una estructura sencilla puede ser:

```text
uml-generator/
├── uml_excalidraw.py
├── pyproject.toml
├── README.md
└── .gitignore
```

Si utilizas `uv`, puedes tener además:

```text
uml-generator/
├── .python-version
├── .venv/
├── uv.lock
└── ...
```

Los entornos virtuales y archivos generados por herramientas como `uv` no deberían incluirse en el repositorio cuando corresponda.

---

# Opciones de línea de comandos

Resumen de la interfaz actual:

```text
usage: uml_excalidraw.py [-h] [-o OUTPUT] [--no-private]
                         [--exclude PATRON]
                         project
```

### `project`

Directorio raíz del proyecto Python/Java que se desea analizar.

### `-o`, `--output`

Ruta base de los archivos de salida.

### `--no-private`

Oculta atributos y métodos privados/protegidos.

### `--exclude PATRON`

Excluye archivos que coincidan con un patrón `glob` relativo al proyecto. Puede utilizarse varias veces.

### `-h`, `--help`

Muestra la ayuda integrada de `argparse`.

---

# Ejemplos rápidos

### Analizar un proyecto Python

```bash
python uml_excalidraw.py ~/proyectos/app
```

### Analizar y guardar en `docs/uml`

```bash
python uml_excalidraw.py ~/proyectos/app -o ~/proyectos/app/docs/uml
```

### Excluir tests

```bash
python uml_excalidraw.py ~/proyectos/app --exclude 'tests/*'
```

### Ocultar miembros privados/protegidos

```bash
python uml_excalidraw.py ~/proyectos/app --no-private
```

### Combinar opciones

```bash
python uml_excalidraw.py ~/proyectos/app \
  -o ~/proyectos/app/docs/uml \
  --no-private \
  --exclude 'tests/*' \
  --exclude '**/test_*.py'
```

### Usando `uv`

```bash
uv run python uml_excalidraw.py ~/proyectos/app -o ~/proyectos/app/docs/uml
```

### Usando el comando global

```bash
uml-excalidraw ~/proyectos/app -o ~/proyectos/app/docs/uml
```

---

# Importar el resultado en Excalidraw

Cuando se haya generado el archivo:

```text
uml.excalidraw
```

puede abrirse en Excalidraw para continuar editando manualmente el diagrama.

El objetivo del formato es conservar la estructura como elementos editables, a diferencia de trabajar únicamente con el PNG.

---

# Limitaciones conocidas

Este proyecto utiliza análisis estático y heurístico. Por esa razón, el diagrama generado debe considerarse una **representación aproximada del código fuente**, no un sustituto de un parser semántico completo.

## Python

Algunas construcciones dinámicas de Python no pueden resolverse de forma segura mediante `ast` y heurísticas simples. Por ejemplo:

- tipos determinados dinámicamente en tiempo de ejecución;
- asignaciones complejas;
- alias dinámicos;
- importaciones y referencias difíciles de resolver estáticamente;
- relaciones implícitas que no aparecen en atributos, anotaciones o llamadas detectables.

## Java

El parser Java es deliberadamente ligero y no pretende cubrir todas las reglas del lenguaje.

Puede haber limitaciones con:

- sintaxis Java extremadamente compleja;
- construcciones nuevas del lenguaje que no coincidan con los patrones actuales;
- genéricos especialmente complejos;
- anotaciones con sintaxis poco habitual;
- declaraciones ambiguas;
- casos avanzados de clases anidadas;
- código Java cuya estructura no pueda recuperarse correctamente mediante el análisis textual.

Para proyectos Java de gran complejidad, un parser basado en un AST completo sería más preciso.

---

# Principio de seguridad

Una característica importante del proyecto es que el código fuente analizado **no se ejecuta**.

Para Python se utiliza:

```python
ast.parse(source)
```

y se inspecciona la estructura sintáctica resultante.

Para Java se realiza un procesamiento textual del archivo fuente.

Por tanto, el generador no necesita iniciar el proyecto objetivo, importar sus módulos ni ejecutar constructores, servicios u otras operaciones del código analizado.

Esto reduce el riesgo de que analizar un proyecto provoque efectos secundarios derivados de su ejecución.

> Nota: leer y procesar archivos nunca sustituye una política completa de seguridad. El script sigue teniendo acceso de lectura al contenido del directorio que se le indique.

---

# Flujo interno del programa

El procesamiento general sigue este flujo:

```text
                 ┌─────────────────────┐
                 │ Directorio proyecto │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Buscar .py y .java  │
                 └──────────┬──────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │ Analizar código fuente    │
              │ Python → AST              │
              │ Java   → parser heurístico│
              └────────────┬──────────────┘
                           │
                           ▼
                 ┌─────────────────────┐
                 │ ClassInfo + métodos │
                 │ + atributos         │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Inferir relaciones  │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ ExcalidrawBuilder   │
                 └──────────┬──────────┘
                            │
                 ┌──────────┴──────────┐
                 ▼                     ▼
       ┌─────────────────┐   ┌─────────────────┐
       │ Escena          │   │ SvgRenderer     │
       │ Excalidraw JSON │   │ SVG en memoria  │
       └────────┬────────┘   └────────┬────────┘
                │                     │
                ▼                     ▼
       .excalidraw opcional         PNG
```

---

# Componentes principales del código

## `FieldInfo`

Representa un atributo UML.

Guarda información como:

- nombre;
- tipo;
- visibilidad;
- valor por defecto;
- origen (`class` o `instance`).

## `MethodInfo`

Representa un método UML.

Incluye:

- nombre;
- visibilidad;
- parámetros;
- retorno;
- `static`;
- `classmethod`;
- `property`;
- `async`.

## `ClassInfo`

Es la estructura principal de una clase detectada.

Contiene:

- nombre;
- módulo;
- nombre cualificado;
- archivo;
- línea;
- bases/herencia;
- atributos;
- métodos;
- relaciones asociadas a campos;
- tipos utilizados;
- tipo de declaración Java cuando corresponde.

## `Relation`

Representa una relación entre dos clases.

Los tipos soportados actualmente son:

```text
inheritance
composition
aggregation
association
dependency
```

## `ProjectAnalyzer`

Se encarga de descubrir archivos, analizarlos y construir las clases y relaciones.

## `ExcalidrawBuilder`

Convierte la información UML en una escena compatible con Excalidraw y calcula la distribución visual de las clases.

## `SvgRenderer`

Convierte la escena en una representación SVG.

## `export_png()`

Busca un conversor disponible y transforma el SVG en PNG.

## `main()`

Controla:

- argumentos de línea de comandos;
- validación del proyecto;
- análisis;
- generación;
- salida de consola;
- confirmación del `.excalidraw`.

---

# Dependencias resumidas

| Componente | ¿Obligatorio? | Para qué sirve |
|---|:---:|---|
| Python 3.10+ | ✅ | Ejecutar el generador |
| `ast` | ✅ | Análisis sintáctico de Python; forma parte de Python |
| `CairoSVG` | ❌ | Generar PNG desde SVG dentro de Python |
| `rsvg-convert` | ❌ | Alternativa del sistema para generar PNG |
| ImageMagick | ❌ | Otra alternativa para generar PNG |
| `uv` | ❌ | Gestión de entorno y dependencias |
| PyInstaller | ❌ | Crear ejecutables para distribución |

El usuario final solo necesita una de las rutas disponibles para generar PNG. Si ninguna está disponible, aún puede generarse el análisis UML y el archivo `.excalidraw`.

---

# Recomendación de distribución

Para desarrollo personal o universitario:

```text
Python + venv
```

o:

```text
uv
```

Para usarlo repetidamente en Linux como una herramienta local:

```text
Python/venv + wrapper Bash + ~/.local/bin
```

Para entregar la herramienta a personas que no quieren instalar Python:

```text
PyInstaller + ejecutable específico para cada plataforma
```

Una distribución completa para Linux y Windows puede mantener el mismo código fuente y publicar dos artefactos independientes:

```text
Linux  → UML_Excalidraw
Windows → UML_Excalidraw.exe
```

---

# Estado del proyecto

El generador actual está pensado como una herramienta práctica para obtener rápidamente una representación visual de la estructura de proyectos Python y Java.

Su prioridad es:

```text
código fuente → análisis estático → UML aproximado → Excalidraw / PNG
```

No pretende ser un compilador, intérprete ni analizador semántico completo de Python o Java.

---

# Contribuciones y mejoras futuras

Algunas extensiones naturales para el proyecto serían:

- detección más precisa de imports y módulos;
- parser Java basado en AST;
- resolución de tipos más robusta;
- cardinalidades UML (`1`, `0..1`, `*`, etc.);
- agregación y composición más precisas;
- detección de interfaces y clases abstractas con mayor detalle;
- paquetes UML;
- agrupación por módulos;
- filtros por lenguaje;
- selección de clases concretas;
- layouts más avanzados;
- mejor posicionamiento automático de relaciones;
- generación directa de formatos UML adicionales;
- instalador multiplataforma;
- integración con GitHub Releases.

---

# Licencia

Añade aquí la licencia elegida para el proyecto, por ejemplo:

```text
MIT License
```

Si el repositorio aún no tiene una licencia definida, esta sección debe actualizarse antes de publicar formalmente el proyecto.

---

# Autor

Añade aquí la información del autor o autores del proyecto.

```text
Autor: ______________________________
GitHub: _____________________________
```
