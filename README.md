# PerfilLab: Instagram con cookies, Big Five con Gemini y Benford

Proyecto académico Python con interfaz Tkinter, extracción mediante Playwright y análisis separados.

- Instagram: navegación normal en Chromium y cookies propias. No usa API oficial de Meta ni reproduce peticiones a endpoints internos. Lee el DOM y los datos recibidos por la página.
- Big Five: API oficial de Google Gemini mediante `google-genai`. Recibe únicamente biografía y pies de publicaciones/reels. No recibe cookies, credenciales, listas de seguidores, imágenes ni videos.
- Benford: cálculo local del primer dígito, chi-cuadrado, p-valor y tres gráficos.

## Instalar y abrir

En PowerShell, dentro de esta carpeta:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe gui.py
```

Copia `.env.example` a `.env` si todavía no existe. Nunca sobrescribas una configuración existente sin conservarla.

```dotenv
GEMINI_API_KEY=tu_clave_local
GEMINI_MODEL=gemini-flash-latest
```

Obtén tu clave en https://aistudio.google.com/apikey y reinicia el programa al modificar `.env`. El modelo es configurable y la disponibilidad/cuota depende de tu cuenta de Google. No compartas el archivo `.env`.

## Sesión de Instagram

Pulsa **Iniciar sesión**. Introduce tus credenciales directamente en Chromium y completa allí cualquier verificación. Al guardar la sesión en `.auth/instagram.json`, la ventana se cierra automáticamente. Esa sesión tiene prioridad sobre `INSTAGRAM_COOKIES` en `.env`.

HTTP 429 significa límite de solicitudes y no demuestra que una cookie sea incorrecta. El programa conserva datos parciales y respeta una pausa persistente; no intenta eludir restricciones. Una cuenta privada solo puede aportar lo que permita ver tu sesión.

## Big Five con Gemini

Escribe el perfil y pulsa **Recopilar y analizar**, o **Gemini: datos guardados** si ya existe `output/instagram_report_<usuario>.json`.

El segundo botón evita nuevas consultas a Instagram y guarda `instagram_report_<usuario>_gemini.json`, conservando el informe original. También puede ejecutarse:

```powershell
.\.venv\Scripts\python.exe main.py --reanalyze jhonatan.coronel
```

El modelo produce apertura, responsabilidad, extraversión, amabilidad y neuroticismo. Cada dimensión incluye una estimación 0-100 o null, justificación, confianza declarada y citas de los textos. Las citas se contrastan con la entrada; no se aceptan citas inventadas. Una puntuación requiere dos fuentes citadas distintas. Se exigen 100 palabras y dos fuentes antes de llamar a Gemini. Son controles del proyecto, no criterios de validación psicológica.

La entrada se limita a 80.000 caracteres; el JSON indica si fue truncada. Se eliminan enlaces y menciones. Solo se usa texto: no se transcribe el audio ni se interpreta la apariencia de las personas en fotos/videos. Las instrucciones presentes en publicaciones se tratan como datos, no como órdenes.

**Es una estimación exploratoria, no una evaluación psicométrica validada ni un diagnóstico.** La confianza declarada por el modelo no es una probabilidad calibrada. La falta de evidencia deja el score en null. No usar para decisiones sobre personas.

Si falta la clave, aparece `not_configured`; no se simula éxito ni se sustituye Gemini por el diccionario local. Los errores de cuota, acceso, modelo, red o formato quedan explícitos. Se hace un intento y un timeout de 60 segundos. Detener evita iniciar el análisis si ya se canceló; una llamada en curso puede tardar hasta su timeout.

`big_five.py` permanece únicamente para la demostración sintética y compatibilidad con informes históricos. Los análisis de tus ejecuciones anteriores son locales y están identificados como `local_lexicon_v1`; no son respuestas de Gemini.

## Benford

La tabla muestra seguidores/seguidos, con métricas individuales y tooltip. El selector permite usar seguidores de seguidores o seguidos de seguidos. Los conteos abreviados o ausentes no se estiman. Cero no participa en el primer dígito.

P(d) = log10(1 + 1/d), d=1..9. Chi-cuadrado = suma de (observado-esperado)^2/esperado; 8 grados de libertad.

| Etiqueta | Regla |
| --- | --- |
| Compatible con Benford | p >= 0,05 |
| Desviación estadística moderada | 0,01 <= p < 0,05 |
| Desviación estadística fuerte | p < 0,01 |
| No clasificable | Muestra incompleta, métricas ausentes o alguna frecuencia esperada < 5 |

Se necesitan al menos 110 conteos positivos para que todas las frecuencias esperadas sean >=5. Los nombres moderada/fuerte son convenciones de significación, no tamaños del efecto. Benford no determina si un usuario es bot o humano. La idoneidad de los conteos y su independencia no están garantizadas.

## Evidencias de esta entrega

Los archivos originales del usuario se conservan en `output/`: 25 contenidos y una recopilación con 415 seguidores y 240 seguidos. Son resultados reales guardados el 27 de octubre de 2026; se incluyen JSON, CSV y medios descargados. El estado `complete` significa que el extractor recibió el final de la lista; no certifica que el servidor exponga todas las cuentas. Los conteos pueden variar entre momentos.

`output/live_check_20261027_211159/` contiene la prueba real pequeña con 2 seguidores y 2 seguidos y un video. La primera prueba fallida también queda registrada por separado. Los archivos de `output/qa/` son pruebas automatizadas y capturas sintéticas, identificadas como tales.

Gemini se probó con respuestas simuladas: **no se realizó una llamada real porque no se proporcionó clave API**. El informe PDF de entrega distingue estas evidencias. Los resultados reales previos no se modificaron para atribuirlos a Gemini.

## Repetir las pruebas automatizadas

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:RUN_BROWSER_TESTS='1'
$env:RUN_GUI_TESTS='1'
.\.venv\Scripts\python.exe -m pytest tests instagram/test_parsers.py -q
```

Las pruebas automatizadas de Chromium interceptan el tráfico y usan fixtures sintéticos. Las de Gemini no utilizan tus claves. La integración real con el proveedor requiere clave, cuota y modelo disponible.

## Archivos principales

- `gui.py`: interfaz, hilos, cancelación, tablas, tooltips y gráficos.
- `main.py`: flujos y exportación, reanálisis sin scraping.
- `instagram/browser.py`: sesión y navegación; admite JSON servido como text/javascript y enlaces actuales de seguidores.
- `gemini_analysis.py`: entrada acotada, SDK oficial, esquema estructurado, validación de citas y errores seguros.
- `benford.py`: cálculos y reglas de calidad.
- `tests/`: pruebas locales y de integración simulada.

El ZIP no contiene `.env`, `.auth`, claves ni entornos Python. Sí contiene los resultados y medios reales solicitados para la entrega. No incluye los ZIP antiguos.

Referencias: https://googleapis.github.io/python-genai/ ; https://playwright.dev/python/docs/auth ; https://itl.nist.gov/div898/handbook/eda/section3/eda35f.htm
