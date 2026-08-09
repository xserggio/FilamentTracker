<div align="center">

<img src="brand/benchy-navy-tile.png" width="96" alt="Filament Tracker">

# Filament Tracker

**Lleva el control de tu filamento de impresión 3D: cuánto queda en cada rollo, qué
tienes de repuesto y a dónde ha ido cada gramo.**

Una aplicación de escritorio pequeña para Windows. Sin cuenta, sin nube y sin
telemetría — tus datos viven en un único archivo SQLite junto al ejecutable.

[English](README.md) · [Descargar](#descargar) · [Manual](#manual)

<img src="docs/dashboard.png" alt="Panel">

</div>

---

## Por qué

Casi todos acabamos con una hoja de cálculo: una fila por impresión, una fórmula por
rollo y un pequeño vértigo cada vez que cambias de bobina. Esta app es esa hoja de
cálculo, salvo que entiende lo que es un rollo — que tiene marca, que se acaba, que
lo sustituyes por otro que puede ser de otro fabricante, y que el PETG hay que
secarlo bastante más a menudo que el PLA.

## Qué hace

- **Nivel de cada rollo, al día.** Cada impresión que registras se descuenta del
  rollo que está puesto. Al abrir uno nuevo el contador arranca de cero sin perder
  el historial.
- **Rollos sin abrir.** El stock es stock: una bobina sin estrenar no registra
  rollo, ni fecha de apertura, ni contador de secado hasta el día que la abres.
- **Repuestos con identidad propia.** El stock no es un contador: cada repuesto
  tiene su marca, su tipo de bobina y su peso, así que tu negro puede ser Bambu Lab
  y sus dos repuestos eSUN.
- **Pesar en vez de estimar.** Pones el rollo en la báscula, escribes lo que marca,
  y la app resta el peso del carrete vacío según la marca y el tipo de bobina.
- **Temperaturas y densidad.** Boquilla y cama de ese filamento concreto, desde
  un catálogo de 53 fabricantes y 415 productos que va dentro de la app. Sin
  conexión, y diciendo si el dato es del producto, de la marca o simplemente el
  típico de ese plástico.
- **Precios y coste por impresión.** Opcional. Cada impresión se valora con el
  rollo que estaba puesto ese día, en cualquiera de las 178 divisas ISO.
- **Avisos de secado.** Intervalos por material, contados desde la apertura y
  reiniciados cada vez que registras un secado.
- **Impresiones fallidas.** Marcas una como fallida y corriges los gramos que
  realmente gastó — el material que no llegó a salir vuelve al rollo.
- **Lee lo que lamina Bambu Studio.** Laminas una placa y un aviso te ofrece
  apuntar la impresión con los gramos ya puestos y un rollo propuesto por cada
  color. Tú confirmas; él lo recuerda.
- **Agrupar impresiones en un proyecto.** Una casa son veinte impresiones;
  agrúpalas y las estadísticas cuentan la casa, sin que ninguna pieza pierda
  su nombre.
- **Estadísticas.** Gramos por mes, filamentos más usados, reparto por material,
  proyectos que más consumen y material desperdiciado.
- **Importación desde Excel.** Trae tu hoja de cálculo de una sentada.
- **Pestaña AMS.** Qué rollo hay en cada hueco ahora mismo, con la bobina externa.
- **Claro y oscuro.** Oscuro por defecto, y cualquiera de los dos puede seguir a Windows.
- **Ayuda dentro de la app.** La versión corta de este manual, a un clic.
- **Seis idiomas.** Español, inglés, francés, alemán, portugués e italiano.

## Descargar

**1.** Descarga **`FilamentTracker.exe`** de la
[última versión](../../releases/latest).

**2.** Doble clic donde lo hayas dejado.

Sin instalador, sin Python y sin línea de comandos. La primera vez que lo abras
aparecerá a su lado una carpeta `data` con tu base de datos dentro.

<details>
<summary><b>Windows dice «Windows protegió tu PC»</b></summary>

Es SmartScreen, y dice eso de cualquier programa que no haya pagado un certificado
de firma de código. Pulsa **Más información** y luego **Ejecutar de todas formas**.

Si prefieres no fiarte de mi palabra, el código está entero aquí y puedes
[compilar el ejecutable tú mismo](#compilar-el-ejecutable).
</details>

<details>
<summary><b>No pasa nada, o menciona WebView2</b></summary>

La app dibuja su interfaz con el runtime WebView2 de Microsoft. Windows 11 lo trae
de serie; algunas instalaciones de Windows 10 no. Si falta, la app te lo dice y te
ofrece abrir la [página de descarga](https://developer.microsoft.com/microsoft-edge/webview2/) —
instálalo y vuelve a abrirla.
</details>

<details>
<summary><b>Mover la app a otra carpeta u otro PC</b></summary>

Llévate la carpeta `data` con ella. Esa carpeta es tu base de datos; si la dejas
atrás, la app arrancará vacía.
</details>

---

## Manual

### El modelo en un párrafo

La app tiene tres cosas: **filamentos**, cada uno con un **rollo** puesto y con los
**repuestos** que tengas en el cajón, e **impresiones** que gastan gramos de un
filamento. Cada rollo y cada repuesto guardan su propia marca, tipo de bobina,
peso y precio, así que un mismo filamento puede pasar de un fabricante a otro sin
cambiar de nombre.

Los gramos que quedan en el rollo puesto son:

```
restante = peso del rollo − gramos impresos desde que se abrió + corrección manual
```

Las impresiones con fecha **anterior** a la apertura suman al total histórico del
filamento pero no tocan el rollo actual. Eso es lo que te permite estrenar una
bobina sin borrar el historial.

### Inventario

<img src="docs/inventory.png" alt="Inventario">

Una tarjeta por filamento, con el nivel del rollo puesto y una barra que pasa a
ámbar y luego a rojo según se vacía. Al pulsar en cualquier punto de la tarjeta se
abre su **ficha**: todos
los rollos que ha tenido, con su marca, cuánto se consumió de cada uno y cuántos
días duró, más la lista de impresiones que lo usaron.

El pie de la tarjeta tiene, en orden: los días que lleva abierto el rollo, el
contador de repuestos (`−` / número / `+`), un botón de **báscula**, uno de **gota**
y **Rollo nuevo**.

| Botón | Qué hace |
|---|---|
| `−` / `+` | Quita o añade un repuesto. Los nuevos heredan la marca y el tipo del rollo puesto. |
| el número | Abre la lista de repuestos: marca, tipo de bobina y peso, editables uno a uno. |
| ⚖ | Corregir los gramos restantes pesando el rollo. |
| 💧 | Registrar un secado. |
| Rollo nuevo | Estrenar una bobina, opcionalmente gastando uno de los repuestos. |

Arriba hay filtros: búsqueda por texto, material, orden, *solo bajos*, *con
repuesto* y *ver archivados*.

### Temperaturas y densidad

La ficha de cada filamento muestra la temperatura de boquilla y de cama, y la
densidad. No se escriben a mano: salen de un catálogo de **53 fabricantes, 415
productos y 3531 colores** construido a partir de
[SpoolmanDB](https://github.com/Donkie/SpoolmanDB) y empaquetado con la app, así
que nada de esto necesita conexión.

<img src="docs/detail.png" alt="Ficha de un filamento">

La búsqueda va de lo concreto a lo general, y dice de dónde ha salido el dato:

| Origen | Qué significa |
|---|---|
| el producto | el fabricante publica el dato de ese filamento exacto, p. ej. Bambu Lab PLA Matte |
| la marca | la gama propia de esa marca para ese material |
| típico | el rango habitual de ese plástico, lo haga quien lo haga |

Un rollo sin marca cae en el rango típico de su plástico, y la ficha dice cuál de
los tres orígenes está usando. En Ajustes hay un selector **°C / °F**; los datos se
guardan siempre en Celsius.

Los colores reales de la marca también aparecen en el selector de color: *Bambu
Lab · PLA Matte* propone los quince mates que vende de verdad en lugar de una
muestra en blanco.

### Un rollo que no has abierto

Un filamento que tienes pero no has estrenado no es un rollo al 100 %: es stock.
Marca **Sin abrir** al darlo de alta y no se registra ningún rollo — ni fecha de
apertura, ni contador de secado, ni barra de nivel. La tarjeta enseña lo que hay
en el cajón y su única acción es **Abrir rollo**.

Al abrir uno se descuenta del stock, así que dos bobinas sin abrir pasan a ser un
rollo puesto y un repuesto, no tres bobinas. El contador de secado arranca ese
día, que es cuando arranca de verdad.

Un filamento sin abrir no genera ningún aviso: no está bajo ni vacío, es que
todavía no hay nada puesto.

**Corregir uno que ya diste de alta.** Edita el filamento y ahí está la misma
casilla, siempre que no hayas impreso nada con el rollo puesto: esa bobina vuelve
al cajón con su marca, su peso y su precio. En cuanto has impreso con ella la
casilla desaparece, porque el rollo es la ventana en la que se cuentan esos gramos
y quitarlo los perdería.

### AMS

<img src="docs/ams.png" alt="AMS">

Qué rollo hay en cada hueco ahora mismo. La app no puede preguntárselo a la
impresora, así que esto lo llevas tú — un clic en un hueco para poner o quitar
un rollo. Todos los huecos se dibujan tengan algo o no, porque saber que uno
está libre vale tanto como saber qué hay en él, y la bobina externa siempre está.

Las unidades se eligen en la propia pestaña, de ninguna a cuatro, con cuatro
huecos cada una. Una bobina solo puede estar en un sitio, así que cargarla en
otro hueco la saca de donde estaba, y el selector te dice dónde está ya cada una.

### Registrar una impresión

`Nueva impresión` pide fecha, nombre del proyecto, una fila por color con sus
gramos, un enlace opcional a la página del modelo y notas. No hay límite de cuatro
colores.

<img src="docs/history.png" alt="Historial">

En el historial, cada fila tiene un botón de enlace (si guardaste una URL), un botón
**`!`**, uno de editar y otro de eliminar.

### Agrupar impresiones

Una casa son veinte impresiones. En el historial cada una sigue siendo lo que es
—una chimenea es una chimenea—, pero quieres que la casa cuente como la casa.

El **grupo** va por encima del nombre del proyecto y no lo sustituye. Filtra el
historial hasta ver lo que va junto y pulsa **Agrupar estas N**, que aparece al
lado de *Quitar filtros* y dice cuántas filas va a tocar. Le pones nombre y ya
está. No hay casillas que marcar porque no hace falta: buscar *casa UP* ya ha
dejado a la vista justo esas.

<img src="docs/history.png" alt="Historial">

Lo que cambia cuando las impresiones están en un grupo:

- **Estadísticas** cuenta el grupo en vez de las impresiones sueltas, así que
  *Proyectos que más consumen* enseña la casa con su peso real y sus colores, y al
  pulsarla el historial se filtra al grupo.
- **Buscar** el nombre del grupo encuentra sus piezas, se llame como se llame
  cada una.
- El desplegable **Todos los grupos** filtra el historial a uno, o a lo que no
  está en ninguno.
- Cada fila lleva una etiqueta con el nombre del grupo; al pulsarla, se filtra.

Lo demás no se mueve. Una impresión sin grupo se comporta igual que siempre, y el
grupo no es más que un nombre: si vacías el campo se desagrupa, y un grupo que se
queda sin impresiones desaparece. El mismo campo **Grupo** está en el formulario,
para archivar una impresión nueva al apuntarla.

### Después de laminar en Bambu Studio

Al laminar, Bambu Studio escribe la placa en una carpeta suya, y ahí están los
gramos de cada filamento que va a gastar. Filament Tracker lee esa carpeta y te
ofrece la impresión en vez de hacerte teclearla:

<img src="docs/slice.png" alt="El aviso que ofrece la impresión recién laminada">

**Apuntar impresión** abre el formulario de siempre con el nombre del proyecto,
los gramos y un rollo ya elegido por cada color. No se registra nada hasta que
das a Guardar, y antes puedes cambiar lo que quieras.

<img src="docs/sliceform.png" alt="El formulario relleno a partir del laminado">

**El color del laminado no es el rollo que tienes puesto.** Casi siempre eliges un
perfil porque es el único que existe — no hay Matte en Generic, así que
seleccionas el de Bambu Lab tengas el rollo que tengas — o cambias el color desde
la pantalla de la impresora y el laminador no se entera.

Así que lo que más pesa no es el color, sino **el hueco**. Una placa dice de qué
hueco salió cada color, y si la pestaña AMS dice qué había en ese hueco, ese es
el rollo que se usó, se eligiera lo que se eligiera en pantalla. Si no lo dice,
la propuesta va por material y línea de producto (un perfil *Matte* busca un
rollo mate) y el color solo desempata. La fila de la que no está seguro sale en
ámbar con *Comprueba el rollo*, y todas dicen de dónde sale su propuesta.

La pestaña AMS la llevas tú, así que no se da por buena sin más. Delante hay dos
comprobaciones que una pestaña desactualizada no puede pasar:

- **Tiene que ser anterior a la placa.** Cada hueco guarda el día que se cargó, y
  un rollo puesto después de laminar no estaba ahí cuando se laminó.
- **Tiene que cuadrar con la placa.** Un hueco que dice PLA donde la placa dice
  PETG está desactualizado para ese hueco, y se ignora.

Pasadas las dos, contesta el hueco — y si el color de la pantalla lo contradice
de plano, la fila sigue diciendo *Comprueba el rollo*, para que veas que las dos
cosas no coinciden y decidas.

**Aprende.** El rollo que confirmas queda apuntado contra esa combinación exacta
de material + perfil + color, así que la próxima vez que se lamine lo mismo ya no
hay nada que adivinar. En Ajustes › Bambu Studio está todo lo aprendido, y lo que
esté mal se olvida de un clic.

El aviso se puede apagar en Ajustes › Bambu Studio. *Ahora no* aparta ese laminado
durante la sesión y lo vuelve a ofrecer al siguiente arranque; la **×** lo descarta
para siempre. Un laminado que no llegaste a imprimir simplemente no se confirma nunca.

**Ver slices de Bambu.** El aviso solo ofrece la placa más reciente, y una sola
vez. En Historial, junto a *Nueva impresión*, **Ver slices de Bambu** lista todo
lo que sigue en la carpeta — así puedes apuntar uno que apartaste, o uno que laminaste con
la app cerrada. Solo aparece si hay una carpeta con placas dentro.

**La carpeta.** La encuentra sola, y en ese mismo panel se ve cuál está usando y
cuántas placas laminadas hay dentro — así, si el aviso no aparece nunca, puedes
ver si está leyendo una carpeta vacía o la que no es. Se cambia con **Elegir…** y
se vuelve a lo automático con **Que la busque él**.

Esto lee la carpeta temporal del propio Bambu Studio, que no es una interfaz
documentada. Si una versión futura la cambia de sitio, el aviso deja de aparecer y
ya está — no afecta a nada más.

### Impresiones fallidas

El botón **`!`** abre un diálogo corto que hace dos cosas: marca la impresión como
fallida y te deja **corregir los gramos realmente gastados**. Una impresión que se
cortó a la mitad no consumió lo previsto, así que pones lo que llegó a salir y eso
sustituye a las cifras originales — el material que no se gastó vuelve al rollo y
las estadísticas se recalculan. Un color a 0 g se elimina de la impresión.

Las fallidas siguen descontando material, porque se extruyó igual. Simplemente
quedan marcadas, se pueden filtrar con *solo fallidas* y alimentan el dato de
**material desperdiciado** en Estadísticas.

### Secado

Cada rollo guarda la fecha de su último secado. El contador arranca en la apertura
(una bobina recién abierta viene seca) y se reinicia cada vez que registras uno.

En la tarjeta aparece una gota: azul con los días transcurridos cuando va bien,
ámbar con *secar* al pasarse del límite. También sale en los avisos del Panel.

Los límites dependen del plástico y están en **Ajustes → Secado por material**. De
partida: PLA y sus variantes 60 días, PLA-CF/ABS/ASA 45, PETG 30, TPU y PC 14,
PA/Nylon/PVA 7.

Hay unos sesenta materiales en la lista, pero los fabricantes sacan nombres más
rápido de lo que ninguna lista puede seguir. Lo que no reconozca tira de **su
familia**, no de un número fijo: `PETG Rapid` es un PETG y le tocan 30 días,
`TPU-95A` es un TPU y le tocan 14, `PA6-CF` es una poliamida y le tocan 7. El campo
de material es texto libre, así que escribe lo que ponga en la caja — y si no estás
de acuerdo con el intervalo, se puede cambiar.

### Pesar un rollo

En el diálogo de la ⚖ escribes lo que marca la báscula con el rollo entero y la
**tara del carrete**; los gramos restantes salen solos.

Esa tara viene precargada según la **marca** y el **tipo de bobina** del rollo —
ambos son desplegables, y al cambiar cualquiera de los dos el número se actualiza.
Los valores de partida salen de [SpoolmanDB](https://github.com/Donkie/SpoolmanDB),
contrastados con [The Empty Spool](https://theemptyspool.cc/) y el foro de Bambu Lab:

| Marca | Plástico | Cartón |
|---|---|---|
| Bambu Lab | 250 g | 196 g |
| eSUN | 240 g | 170 g |
| Prusament | 193 g | — |
| Eryone | 187 g | — |
| Geeetech | 180 g | — |
| Overture | — | 155 g |
| Elegoo | 154 g | 154 g |
| Polymaker | — | 140 g |
| Sunlu | 130 g | — |
| Creality | 225 g | 120 g |
| Anycubic | 127 g | 125 g |
| Hatchbox | 251 g | — |
| JAYO | — | 120 g |
| Marca desconocida | 220 g | 160 g |

**Tómalos como punto de partida.** La dispersión es grande incluso dentro de una
misma marca —Bambu va de 196 a 253 g y eSUN de 161 a 253— porque cambian el molde
entre versiones. Por eso, en cuanto corriges la tara pesando un carrete tuyo, la app
guarda **tu** número para esa combinación de marca y tipo y lo usa a partir de
entonces. También se editan a mano en **Ajustes → Tara del carrete por marca**.

### Cuando las cuentas no cuadran

Si apuntas 1.075 g contra un rollo de 1.000, algo va mal, pero no lo que diría un
contador ingenuo. En esa bobina hay plástico, así que la app no enseña un cero y
lo llama vacío: dice que el libro se ha pasado, de cuánto, y no toca el número
hasta que decidas qué ha pasado.

Y lo pregunta, porque **pesar corrige el número venga de donde venga** y las
causas no son la misma cosa:

| Qué ha pasado | Qué lo arregla |
|---|---|
| El rollo traía más de lo que decía la etiqueta | Pesarlo — que un "1 kg" lleve 1.030 g es lo normal |
| Una impresión fue contra el color equivocado | Corregir esa impresión |
| Una fallida cuyos gramos nunca se bajaron | El botón **`!`** |
| **Cambiaste la bobina y no lo apuntaste** | **Abrir un rollo nuevo con la fecha del cambio** |

La última es la que merece pararse. Setenta y cinco gramos es muchísimo más que
la variación entre bobinas, y si la causa es un cambio no apuntado, pesar lo
empeora: suelda dos bobinas en el historial de un mismo rollo y le deja encima
una corrección permanente. Abrir el rollo nuevo con la fecha del cambio mueve
todo lo impreso desde entonces a ese rollo, y el descuadre suele desaparecer
solo.

Una corrección, una vez hecha, no se queda callada. El rollo la lleva con su
fecha en la ficha del filamento —*Pesado el 9 ago 26: +175 g sobre lo nominal,
llevaba 1.175 g*— y el coste por gramo se reparte sobre lo que el rollo llevaba
de verdad. Diez euros entre 1.175 g no son diez euros entre 1.000, y cada
impresión de ese rollo estaba cargada un quince por ciento de más.

### Precios y coste por impresión

Pon el precio de un rollo — en el filamento, en un rollo nuevo o en cada
repuesto — y el historial gana una columna de **Coste** y las estadísticas una
tarjeta de **Gastado**. Si no hay ningún precio, no aparece ninguna de las dos: la
app no enseña columnas de ceros.

Cada impresión se valora con **el rollo que estaba puesto ese día**, no con el
precio de hoy. Volver a comprar el mismo color a otro precio no puede reescribir
lo que costó el mes pasado, así que sustituir una bobina de 21,99 por otra de
34,99 deja intactas las impresiones antiguas y solo cobra la tarifa nueva de ahí
en adelante.

La divisa se elige en Ajustes y están **los 178 códigos ISO 4217 activos**, no
solo las principales. El nombre y el símbolo los pone el sistema, así que la
lista se lee «PLN · esloti polaco» en español y «PLN · Polish zloty» en inglés, y
el mismo número sale como 1.234,50 €, US$1,234.50 o 1235 JPY. No se convierte
nada ni se consulta ningún tipo de cambio: los precios se muestran en la moneda en
la que los metiste.

En estadísticas está además el valor de lo que tienes en la estantería: lo que
queda en los rollos abiertos más los repuestos.

### Estadísticas

<img src="docs/stats.png" alt="Estadísticas">

Gramos por mes, filamentos más usados, reparto por material, proyectos que más
consumen y material desperdiciado. Los KPIs del Panel y de aquí son clicables y te
llevan a la vista correspondiente con los filtros ya puestos.

### Importar desde Excel

**Ajustes → Importar desde Excel** lee una hoja exportada de Google Sheets con las
pestañas `Inventario`, `Historial de Impresiones` y `Respuestas de formulario 2`
(la forma que genera un formulario de Google). Las filas que comparten fecha y
proyecto se agrupan en una sola impresión multicolor. Volver a importar el mismo
archivo no duplica nada.

Si tu hoja tiene otra forma, `importer.py` son unas 150 líneas legibles.

### Copias de seguridad

Cada vez que arranca la app guarda una copia de la base de datos en `data/backups/`,
una por día, conservando las 10 últimas. Usa la API de backup de SQLite en vez de
copiar el archivo, así que la copia es consistente aunque haya una escritura a
medias. **Ajustes → Datos** enseña cuántas hay, permite forzar una y abrir la
carpeta.

### Tus datos

Todo vive en `data/filaments.db`, un archivo SQLite normal. No se envía nada a
ninguna parte. Para hacer copia, copia ese archivo. Para curiosear dentro, cualquier
visor de SQLite vale.

---

### Ayuda, y qué aspecto tiene

**Ayuda** lleva dentro de la app la versión corta de este manual: el modelo en un
párrafo, qué hace cada control de la tarjeta, secado, pesar un rollo, Bambu
Studio, la pestaña AMS y dónde viven los datos.

**Ajustes → Aspecto** cambia entre oscuro, claro o lo que tenga Windows, sin
reiniciar. El oscuro es el predeterminado.

<img src="docs/light.png" alt="El tema claro">

## Para desarrolladores

### Ejecutar desde el código

```bash
git clone https://github.com/xserggio/FilamentTracker.git
cd FilamentTracker
py -m pip install -r requirements.txt
py app.py
```

Python 3.10 o superior y las dos dependencias de `requirements.txt` (`pywebview` y
`openpyxl`).

### Compilar el ejecutable

```bash
py -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File build.ps1
```

Deja `dist/Filament Tracker.exe` con el icono de `brand/`.

`core.py` separa a propósito los recursos de solo lectura (`web/`, que PyInstaller
extrae a una carpeta temporal) de los datos que hay que conservar (la base de datos,
siempre junto al ejecutable). Sin esa distinción la base de datos acabaría en el
directorio temporal y desaparecería al cerrar.

## Estructura

```
app.py         ventana pywebview y puente con la interfaz
core.py        esquema SQLite, rutas, cálculo de restantes y estadísticas
catalog.py     catálogo de fabricantes, temperaturas y comparación de color
catalog.json   53 fabricantes, 415 productos, 3531 colores
importer.py    lectura del Excel
slicer.py      lee las placas que ha laminado Bambu Studio
build.ps1      empaquetado con PyInstaller
web/           index.html · style.css · app.js · i18n.js · icon.ico
brand/         logo en navy, negro y blanco (svg, png, ico)
tools/         generador del catálogo, datos, laminado y AMS de ejemplo, capturas
data/          tu base de datos (no está en el repo)
```

## Créditos

Los pesos de carretes vacíos, las temperaturas de impresión, las densidades y el
catálogo de colores de cada marca vienen de
[SpoolmanDB](https://github.com/Donkie/SpoolmanDB) (MIT), contrastados con
[The Empty Spool](https://theemptyspool.cc/). Los dos están mantenidos por la
comunidad. Construido sobre [pywebview](https://pywebview.flowrl.com/).

## Licencia

[MIT](LICENSE).
