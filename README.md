# UML Class Diagram Generator — Excalidraw + PNG

Analiza proyectos **Python y Java** y genera automáticamente un **diagrama UML de clases** a partir de su código fuente, sin necesidad de ejecutar el proyecto.

Puedes obtener:

- 🖼️ **PNG** para visualizar o compartir fácilmente.
- ✏️ **`.excalidraw`** para abrir y editar el diagrama en [Excalidraw](https://excalidraw.com/).

![Ejemplo de diagrama UML generado](assets/uml_class_diagram.png)

---

## 📑 Contenido

- [¿Qué es este proyecto?](#-qué-es-este-proyecto)
- [Características](#-características)
- [Instalación](#-instalación)
- [Uso rápido](#-uso-rápido)
- [Opciones disponibles](#-opciones-disponibles)
- [Ejemplos](#-ejemplos)
- [¿Qué información aparece en el UML?](#-qué-información-aparece-en-el-uml)
- [Relaciones entre clases](#-relaciones-entre-clases)
- [Archivos generados](#-archivos-generados)
- [Limitaciones](#-limitaciones)
- [Preguntas frecuentes](#-preguntas-frecuentes)
- [Autor](#-autor)
- [Licencia](#-licencia)

---

# 📌 ¿Qué es este proyecto?

**UML Class Diagram Generator** es una herramienta que permite crear un diagrama UML de clases automáticamente a partir de un proyecto **Python o Java**.

En lugar de construir el diagrama manualmente, el programa analiza los archivos del proyecto y muestra visualmente las clases, sus atributos, métodos y relaciones.

### Flujo básico

```text
Proyecto Python / Java
        ↓
   Analizar código
        ↓
   Generar diagrama UML
        ↓
   PNG / Excalidraw
```

Está pensado principalmente para ayudarte a **entender, documentar y presentar la estructura de un proyecto**.

---

# ✨ Características

El generador puede identificar:

- Clases.
- Interfaces, `enum` y `record` de Java.
- Atributos.
- Métodos y constructores.
- Parámetros y tipos cuando están disponibles.
- Visibilidad de atributos y métodos.
- Herencia.
- Asociaciones entre clases.
- Composición y algunas dependencias.
- Archivos Python y Java dentro de subdirectorios.
- Exclusión de archivos o carpetas que no quieras analizar.

También intenta mantener el diagrama ordenado y ajustar el tamaño de las clases según la información que contienen.

---

# 🚀 Instalación

## Requisitos

Necesitas:

- **Python 3.10 o superior**.
- **CairoSVG** para generar el PNG desde Python.

Puedes instalar CairoSVG con:

### Linux / macOS

```bash
python3 -m pip install cairosvg
```

### Windows

```powershell
py -m pip install cairosvg
```

> Si ya utilizas un entorno virtual de Python, instala `cairosvg` dentro de ese entorno.

---

# ▶️ Uso rápido

Descarga o clona el repositorio y ejecuta el script indicando la carpeta del proyecto que quieres analizar.

### Linux / macOS

```bash
python3 uml_excalidraw.py /ruta/a/tu/proyecto
```

### Windows

```powershell
py .\uml_excalidraw.py C:\ruta\a\tu\proyecto
```

Por ejemplo:

```bash
python3 uml_excalidraw.py ./mi_proyecto
```

El programa buscará automáticamente los archivos:

```text
.py
.java
```

dentro de la carpeta indicada.

Al terminar, tendrás un archivo PNG con el diagrama y podrás elegir si también quieres guardar una versión editable para Excalidraw.

---

# ⚙️ Opciones disponibles

## Cambiar el nombre y ubicación de salida

Utiliza `-o` o `--output`:

```bash
python3 uml_excalidraw.py ./mi_proyecto -o ./docs/mi_diagrama
```

Esto generará:

```text
docs/
├── mi_diagrama.png
└── mi_diagrama.excalidraw
```

## Ocultar miembros privados y protegidos

Por defecto se muestran.

Para ocultarlos:

```bash
python3 uml_excalidraw.py ./mi_proyecto --no-private
```

## Excluir archivos o carpetas

Puedes indicarle al programa que ignore determinadas rutas:

```bash
python3 uml_excalidraw.py ./mi_proyecto --exclude 'tests/*'
```

También puedes usar varias exclusiones:

```bash
python3 uml_excalidraw.py ./mi_proyecto \
    --exclude 'tests/*' \
    --exclude '**/test_*.py'
```

## Ver todas las opciones

```bash
python3 uml_excalidraw.py --help
```

---

# 🧪 Ejemplos

## Proyecto Python

Supongamos que tienes:

```text
mi_proyecto/
├── usuario.py
├── administrador.py
└── servicio.py
```

Ejecuta:

```bash
python3 uml_excalidraw.py ./mi_proyecto
```

El programa analizará las clases de esos archivos y creará el diagrama correspondiente.

## Proyecto Java

También puedes utilizarlo con:

```text
mi_proyecto/
├── Usuario.java
├── Administrador.java
└── Servicio.java
```

Ejecuta:

```bash
python3 uml_excalidraw.py ./mi_proyecto
```

No necesitas utilizar un comando diferente para Java.

## Proyecto con Python y Java

También puedes analizar un proyecto que contenga ambos lenguajes:

```text
mi_proyecto/
├── python_app/
│   ├── usuario.py
│   └── servicio.py
└── java_app/
    ├── Usuario.java
    └── Servicio.java
```

---

# 📐 ¿Qué información aparece en el UML?

Cada clase se muestra aproximadamente con esta estructura:

```text
┌─────────────────────────────────────────────┐
│                NumeroComplejo               │
├─────────────────────────────────────────────┤
│ - parteImag: double                         │
│ - parteReal: double                         │
├─────────────────────────────────────────────┤
│ + NumeroComplejo(parteR: double, parteI...) │
│ + Conjugado(): NumeroComplejo               │
│ + Dividir(N: NumeroComplejo): NumeroComplejo│
│ + Multiplicar(N: NumeroComplejo): Num...    │
│ + Restar(N: NumeroComplejo): NumeroComplejo │
│ + Sumar(N: NumeroComplejo): NumeroComplejo  │
│ + toString(): String                        │
│ + ValorAbsoluto(): double                   │
└─────────────────────────────────────────────┘
```

## Nombre de la clase

Aparece en la parte superior.

## Atributos

Se muestran en la sección central.

Por ejemplo:

```text
- parteReal: double
```

indica:

- `-` → atributo privado.
- `parteReal` → nombre.
- `double` → tipo.

## Métodos

Se muestran en la parte inferior.

Por ejemplo:

```text
+ Sumar(N: NumeroComplejo): NumeroComplejo
```

indica:

- `+` → método público.
- `Sumar` → nombre.
- `N: NumeroComplejo` → parámetro.
- `NumeroComplejo` → valor de retorno.

---

# 🔗 Relaciones entre clases

Cuando el código permite identificar una relación entre clases, el generador también puede representarla en el diagrama.

### Herencia

Ejemplo:

```python
class Administrador(Usuario):
    ...
```

La relación indica que `Administrador` hereda de `Usuario`.

### Asociación

Puede aparecer cuando una clase utiliza otra como parte de sus atributos o tipos.

Ejemplo:

```python
class Pedido:
    cliente: Cliente
```

### Composición

Puede detectarse en situaciones donde una clase crea directamente una instancia de otra.

Ejemplo:

```python
self.cliente = Cliente()
```

### Dependencia

Puede aparecer cuando una clase utiliza otra en parámetros, retornos o determinadas expresiones del código.

> La detección de relaciones se basa en la información disponible en el código fuente, por lo que no todas las relaciones posibles de un proyecto pueden identificarse.

---

# 📂 Archivos generados

El programa puede generar dos archivos.

## PNG

```text
uml_class_diagram.png
```

Es una imagen normal que puedes:

- abrir;
- compartir;
- insertar en documentos;
- utilizar en presentaciones.

## Excalidraw

```text
uml_class_diagram.excalidraw
```

Puedes abrirlo en Excalidraw y modificar manualmente el diagrama.

Esto resulta especialmente útil cuando quieres ajustar la posición de las clases, agregar información o preparar el diagrama para una presentación.

---

# ⚠️ Limitaciones

El diagrama generado debe entenderse como una **representación automática de la estructura del código**, no como una descripción perfecta de todos los elementos del proyecto.

## Python

El programa puede tener dificultades con código muy dinámico o con relaciones que no puedan deducirse claramente del código fuente.

## Java

El soporte Java utiliza un análisis ligero, por lo que algunas construcciones especialmente complejas pueden no reconocerse correctamente.

En proyectos grandes o con código muy complejo, puede ser necesario **revisar el diagrama generado y realizar algunos ajustes manuales**.

---

# ❓ Preguntas frecuentes

<details>
<summary><strong>¿Necesito ejecutar el proyecto que quiero analizar?</strong></summary>

No. El generador analiza los archivos fuente y no necesita iniciar el proyecto para obtener la información básica de las clases.

</details>

<details>
<summary><strong>¿Puedo utilizarlo con proyectos que tengan muchas carpetas?</strong></summary>

Sí. El programa busca recursivamente archivos `.py` y `.java` dentro de la carpeta que indiques.

</details>

<details>
<summary><strong>¿Puedo analizar solo una parte de un proyecto?</strong></summary>

Sí. Puedes pasar directamente como entrada la carpeta que quieras analizar o utilizar `--exclude` para ignorar determinadas rutas.

</details>

<details>
<summary><strong>¿Puedo editar el resultado?</strong></summary>

Sí. Además del PNG, puedes generar un archivo `.excalidraw` y continuar editándolo en Excalidraw.

</details>

<details>
<summary><strong>¿El resultado siempre será exactamente igual al UML que haría una persona?</strong></summary>

No necesariamente. El programa intenta deducir la estructura y relaciones a partir del código disponible. Por eso conviene revisar el resultado, especialmente en proyectos complejos.

</details>

---

# 👤 Autor

**RiverFlow96**

[GitHub](https://github.com/RiverFlow96)

---

# 📄 Licencia

Actualmente no se declara una licencia para este proyecto.
