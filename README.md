# PerfilLab: Instagram con Playwright y cookies

Aplicación de escritorio en Python para recopilar los datos visibles de un perfil autorizado y realizar dos análisis locales: indicadores léxicos Big Five y ajuste a la Ley de Benford.

**No utiliza Gemini, API oficial de Meta ni claves API.** Playwright abre Chromium con cookies de sesión, navega por las páginas y lee el DOM y los datos que esas páginas reciben. No reproduce llamadas programadas a endpoints internos. El navegador sí hace las solicitudes normales del sitio. Los archivos multimedia se descargan desde las URL de CDN recibidas, sin enviarles las cookies de Instagram.

## Instalación en Windows

Requiere Python 3.10 o posterior con Tkinter. Desde PowerShell en la carpeta del proyecto:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
.\.venv\Scripts\python.exe gui.py
```

No es necesario activar el entorno. Si `.env` ya existe, consérvalo. No copies `.venv` entre equipos: créalo en el equipo de destino. Si `py` no existe, instala Python y vuelve a abrir la terminal.

## Sesión por cookies

Puedes elegir una de estas dos formas:

- Pulsa **Iniciar sesión**. Se abre Chromium para que introduzcas tú mismo tus credenciales y completes cualquier verificación. La sesión se guarda localmente en `.auth/instagram.json`; la aplicación no pide ni guarda tu contraseña.
- Completa `INSTAGRAM_COOKIES` en `.env` con la cadena `nombre=valor; nombre=valor` de tu sesión, incluyendo `sessionid`.

La sesión guardada en `.auth/instagram.json` tiene prioridad sobre `.env`. Para sustituirla, usa de nuevo **Iniciar sesión**; para volver al encabezado de `.env`, elimina solo ese archivo de sesión. Reinicia la app si cambias `.env`.

`.env` y `.auth/` contienen acceso a tu cuenta y se excluyen del ZIP y de Git. No los entregues al profesor ni los publiques. Una cookie no concede acceso a perfiles o listas que tu sesión no puede ver.

## Opción 1: Personalidad (Big Five)

1. Escribe el @handle y selecciona **Todo lo disponible**, o desmarca la opción para introducir un límite.
2. Pulsa **Recopilar y analizar**. Se lee la biografía, se recorren las páginas de publicaciones y reels, y se abren los contenidos encontrados para obtener descripciones y medios disponibles.
3. Los contenidos se deduplican por código; los recomendados de otros autores se excluyen del análisis. El límite se aplica al informe combinado; cada pestaña puede recorrerse hasta ese límite para poder unirlas.
4. Se descargan los medios disponibles y se ejecuta `big_five.py` localmente. El resumen muestra evidencia y el JSON conserva los datos y el método.

**Método Big Five:** diccionarios propios de palabras en español e inglés, separados en dos polos por dimensión. El índice es `100 * coincidencias_positivas / coincidencias_totales`. Solo se muestra con al menos 100 palabras de entrada, 5 coincidencias y 3 términos distintos para ese rasgo. En caso contrario se devuelve `null` (evidencia insuficiente). Las URL, menciones y hashtags se excluyen.

**Este índice no es una prueba psicológica ni un modelo de personalidad validado.** Describe coincidencias léxicas. No entiende negaciones, ironía, contexto o citas. No se debe inferir personalidad real o salud mental ni usarlo para decisiones sobre personas. La dimensión denominada neuroticismo no es un diagnóstico. El diccionario es visible y auditable en `big_five.py`.

## Opción 2: Ley de Benford

1. Selecciona el máximo de cuentas por lista; `0` recorre todo lo que la sesión permita ver, sujeto al límite de desplazamientos.
2. Pulsa **Recopilar seguidores y seguidos**. Playwright abre cada lista y la desplaza. Después visita los perfiles encontrados para obtener seguidores y seguidos de cada uno; consulta una sola vez las cuentas presentes en ambas listas.
3. Consulta las dos tablas. Al pasar el cursor sobre una fila se muestran sus detalles y, cuando corresponde, el error de sus métricas.
4. Selecciona **Seguidores de los seguidores** o **Seguidos de los seguidos** y pulsa **Calcular ajuste**.
5. La pestaña **Gráficos** presenta la distribución teórica, la observada y la comparación superpuesta.

La probabilidad teórica es `P(d) = log10(1 + 1/d)`, para d de 1 a 9. Se usa `chi² = suma((observado - esperado)^2 / esperado)`, con 8 grados de libertad y p-valor de cola superior. La interfaz usa alfa 0,05 y avisa cuando alguna frecuencia esperada es menor que 5. Se excluyen ceros, negativos, ausentes y conteos abreviados como `1.2K`; no se inventan cifras exactas.

**Un desajuste no demuestra que una cuenta sea falsa, fraudulenta o no orgánica.** Los conteos de redes sociales pueden estar acotados y relacionados entre sí. Una extracción parcial debe interpretarse como tal. La prueba es exploratoria y requiere comprobar los supuestos y la idoneidad de los datos.

### Indicador automático de ajuste

La interfaz y el JSON muestran una etiqueta para **el conjunto de datos seleccionado**, no para cada cuenta:

| Etiqueta | Regla del p-valor | Chi-cuadrado equivalente con 8 gl (aproximado) |
|---|---|---|
| Compatible con Benford | p ≥ 0,05 | χ² ≤ 15,507 |
| Desviación estadística moderada | 0,01 ≤ p < 0,05 | 15,507 < χ² ≤ 20,090 |
| Desviación estadística fuerte | p < 0,01 | χ² > 20,090 |

La decisión usa el p-valor sin redondear. Los nombres moderada/fuerte son una convención de presentación para niveles de significación; no miden por sí solos el tamaño del efecto y no son categorías de bots. Los valores críticos se pueden consultar en la [tabla de NIST](https://itl.nist.gov/div898/handbook/eda/section3/eda3674.htm).

Si la lista está incompleta, se interrumpieron las métricas, falta un dato o alguna frecuencia esperada es menor que 5, se muestra **No clasificable**. Con nueve dígitos, este último criterio requiere al menos 110 conteos positivos. El cálculo puede seguir mostrándose con su motivo, sin asignar una etiqueta de ajuste.

**Bot, casi bot o humano: no determinable con esta prueba.** Un p-valor no es la probabilidad de ser bot. Para construir ese clasificador se necesitarían señales de actividad y datos etiquetados con una validación independiente.

## Estados, bloqueos y cancelación

- `complete`: se confirmó el final disponible y, en Benford, se obtuvieron ambos conteos de las filas.
- `limit_reached`: se alcanzó el máximo solicitado de contenido.
- `partial`: se guardaron filas, pero hubo un error, datos ausentes o no se pudo confirmar el final.
- `failed`: no se obtuvo una muestra utilizable. Guardar un CSV vacío no es éxito.
- `not_requested`: una etapa se omitió después de una interrupción.

**Detener** cancela entre acciones del navegador y conserva lo obtenido. Una acción ya en curso puede tardar hasta su timeout en finalizar. El navegador se cierra al terminar la operación.

Ante `429`, se detienen las nuevas solicitudes. Se respeta `Retry-After` o, si falta, se usan 900 segundos. La espera se guarda en `.auth/cooldown.json` y persiste al reiniciar. El bloqueo del servidor puede durar más. Ante 401, 403, inicio de sesión o verificación requerida, se detiene el flujo. No hay rotación de IP/cookies, evasión de CAPTCHA ni parches de ocultación.

## Configuración

| Variable | Valor predeterminado | Uso |
|---|---|---|
| `INSTAGRAM_COOKIES` | vacío | Sesión propia, alternativa al inicio interactivo |
| `INSTAGRAM_REQUEST_INTERVAL_SECONDS` | 2 | Pausa entre acciones del navegador |
| `INSTAGRAM_RATE_LIMIT_COOLDOWN_SECONDS` | 900 | Espera si 429 no trae Retry-After |
| `PLAYWRIGHT_HEADLESS` | false | true ejecuta las extracciones sin mostrar Chromium |
| `PLAYWRIGHT_MAX_SCROLLS` | 300 | Máximo de desplazamientos por lista/pestaña |

El navegador carga varios recursos por página; la pausa entre acciones no equivale a un límite exacto de solicitudes HTTP.

## Archivos generados

- `output/instagram_report_<usuario>.json`: perfil, contenidos, estado y análisis Big Five local.
- `output/media/<usuario>/`: medios que el sitio proporcionó y se pudieron descargar.
- `output/benford_scan_<usuario>.csv` y `.json`: relaciones, conteos, errores y estadísticas de los dos conjuntos.

Repetir una extracción para el mismo usuario actualiza sus archivos de salida. Conserva una copia si necesitas comparar ejecuciones. Los contenidos inaccesibles, borrados o no entregados por Instagram no se pueden recuperar. Los resultados no incluyen cookies ni contraseñas.

## Consola

```powershell
.\.venv\Scripts\python.exe main.py --login
.\.venv\Scripts\python.exe main.py usuario --mode bigfive --limit 10
.\.venv\Scripts\python.exe main.py usuario --mode benford --limit 100
.\.venv\Scripts\python.exe main.py --reanalyze usuario
```

Omitir `--limit` solicita todo lo disponible. `--reanalyze` recalcula Big Five con el JSON guardado sin volver a consultar Instagram.

## Pruebas

Demostración sin cookies ni conexión a Instagram (los datos están marcados como sintéticos):

```powershell
.\.venv\Scripts\python.exe gui.py --demo
```

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests instagram/test_parsers.py -q
$env:RUN_BROWSER_TESTS = '1'
$env:RUN_GUI_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest tests instagram/test_parsers.py -q
```

Las pruebas de navegador usan Chromium real, pero interceptan todas las páginas y respuestas con datos sintéticos. No envían tráfico a Instagram. Cubren perfil, publicaciones, reels, listas, conteos y 429. Las demás pruebas cubren parsers, Benford, Big Five local, cookies, cancelación, deduplicación y archivos parciales. La compatibilidad con Instagram real depende de su página actual, la sesión y los límites del servidor; no se considera verificada por estas pruebas.

## Estructura

- `gui.py`: interfaz Tkinter, hilos de trabajo, eventos, tablas, tooltips y gráficos.
- `main.py`: coordinación, unión de contenidos, análisis local y exportaciones.
- `instagram/browser.py`: sesión Playwright, navegación, desplazamiento y control de bloqueos.
- `instagram/browser_data.py`: extracción de los datos que entrega el navegador y conteos exactos.
- `instagram/parsers.py` y `refs.py`: normalización de datos y referencias.
- `instagram/errors.py`: tipos de error compartidos.
- `instagram/media_download.py`: descarga de archivos desde CDN, sin cookies de Instagram.
- `big_five.py`: diccionarios y método léxico local, con evidencia por dimensión.
- `benford.py`: primer dígito, distribución teórica, chi-cuadrado y p-valor.
- `config.py`: configuración local.

La versión anterior está en el ZIP de respaldo `Scrapy-API-Gemini-corregido.zip` si ya lo generaste; no se incluye dentro del nuevo paquete. Los módulos del extractor HTTP anterior y el cliente Gemini se retiraron de esta versión.

En el ZIP entregado, `docs/` contiene el informe PDF y `docs/evidencia/` conserva el resultado JUnit y las capturas de la demostración. Estas evidencias usan datos sintéticos.

## Referencias

- [Playwright: autenticación y estado de sesión](https://playwright.dev/python/docs/auth)
- [Playwright: respuestas de red del navegador](https://playwright.dev/python/docs/network)
- [NIST: Ley de Benford](https://xlinux.nist.gov/dads/HTML/benfordslaw.html)
- [NIST: prueba de bondad de ajuste chi-cuadrado](https://itl.nist.gov/div898/handbook/eda/section3/eda35f.htm)
- [MDN: HTTP 429](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429)
