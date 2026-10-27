"""Generate the final delivery PDF from recorded test results and saved runs."""
import json
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import benford
OUT = ROOT / 'output'
data = json.loads((OUT / 'benford_scan_jhonatan.coronel.json').read_text(encoding='utf-8'))
profile = json.loads((OUT / 'instagram_report_jhonatan.coronel.json').read_text(encoding='utf-8'))
gemini = json.loads((OUT / 'instagram_report_jhonatan.coronel_gemini.json').read_text(encoding='utf-8'))
suite = ET.parse(OUT / 'qa/gemini-tests.xml').getroot().find('testsuite')
assert all(suite.get(k) == '0' for k in ('errors', 'failures', 'skipped'))
pdfmetrics.registerFont(TTFont('Body', 'C:/Windows/Fonts/segoeui.ttf'))
pdfmetrics.registerFont(TTFont('Bold', 'C:/Windows/Fonts/segoeuib.ttf'))
pdfmetrics.registerFontFamily('Body', normal='Body', bold='Bold', italic='Body', boldItalic='Bold')
NAVY, BLUE, PALE = [colors.HexColor(x) for x in ('#172b45', '#175cd3', '#f1f5fb')]
W = A4[0] - 92
styles = {
    'body': ParagraphStyle('body', fontName='Body', fontSize=10.2, leading=15.5, spaceAfter=10, textColor=NAVY),
    'small': ParagraphStyle('small', fontName='Body', fontSize=8.7, leading=12.5, spaceAfter=8, textColor=NAVY),
    'title': ParagraphStyle('title', fontName='Bold', fontSize=25, leading=31, spaceAfter=15, textColor=NAVY),
    'h': ParagraphStyle('h', fontName='Bold', fontSize=13, leading=18, spaceBefore=10, spaceAfter=8, textColor=BLUE),
    'cell': ParagraphStyle('cell', fontName='Body', fontSize=9.2, leading=13.3, textColor=NAVY),
    'head': ParagraphStyle('head', fontName='Bold', fontSize=9.2, leading=13.3, textColor=colors.white),
}
story = []
def p(text, style='body'): story.append(Paragraph(text.replace('\n', '<br/>'), styles[style]))
def title(section, text):
    p(section.upper(), 'small'); p(text, 'title')
def table(headers, rows, widths):
    contents = [[Paragraph(escape(str(x)), styles['head']) for x in headers]]
    contents += [[Paragraph(escape(str(x)).replace('\n', '<br/>'), styles['cell']) for x in row] for row in rows]
    t = Table(contents, colWidths=widths, repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),BLUE), ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),
        ('VALIGN',(0,0),(-1,-1),'TOP'), ('TOPPADDING',(0,0),(-1,-1),9), ('BOTTOMPADDING',(0,0),(-1,-1),9),
        ('LEFTPADDING',(0,0),(-1,-1),9), ('RIGHTPADDING',(0,0),(-1,-1),9)]))
    story.append(t); story.append(Spacer(1,12))
def page(): story.append(PageBreak())

title('Entrega académica | 27 octubre 2026', 'PerfilLab\nBig Five con Gemini')
p('Informe técnico y evidencia de pruebas. Esta edición sustituye el informe anterior: incorpora Gemini y las ejecuciones reales guardadas por el usuario.')
table(['Área', 'Resultado verificable'], [
    ['Instagram', 'Extracción real con cookies. Perfil con 25 contenidos, biografía y conteos; 35 archivos multimedia guardados.'],
    ['Relaciones', f"{len(data['followers'])} seguidores y {len(data['following'])} seguidos en el archivo del usuario. Estado guardado: {data['status']}."],
    ['Pruebas automatizadas', f"{suite.get('tests')} aprobadas; 0 fallos, 0 errores y 0 omitidas. Chromium, Tkinter, cálculos y Gemini simulado."],
    ['Gemini real', 'PENDIENTE: el usuario todavía no dispone de clave. Se verificó el SDK con HTTP simulado; no se atribuyen resultados reales a Gemini.'],
], [130, W-130])
p('Contenido del ZIP', 'h')
p('Código, dependencias, instrucciones, pruebas reproducibles, este informe, JSON y CSV de las ejecuciones, imágenes y videos descargados, y evidencia QA. Un manifiesto SHA-256 permite comprobar la integridad de los archivos entregados.')
p('Las cookies, la clave API, .env, .auth y el entorno Python se excluyen del paquete. Los resultados personales incluidos corresponden a la entrega solicitada; no se publicaron ni se enviaron a terceros desde esta tarea.')
p('Qué significan los estados', 'h')
p('El estado de extracción y el estado de Gemini son independientes. Una extracción puede estar completa mientras Gemini muestra not_configured. Un límite elegido por el usuario produce un resultado parcial o limit_reached, no un fallo de autenticación.')
p('Los informes anteriores conservan su análisis léxico local original. El archivo terminado en _gemini.json registra el nuevo intento sin clave; no sustituye ni altera la evidencia histórica.', 'small')

page(); title('01 | Diseño y operación', 'Extracción y análisis separados')
table(['Módulo', 'Función'], [
    ['gui.py', 'Interfaz con dos pestañas. Hilo de trabajo, progreso, cancelación, tablas, tooltip, gráficos y botón Gemini: datos guardados.'],
    ['main.py', 'Coordina extracción y exportación; permite reanalizar el JSON sin volver a consultar Instagram.'],
    ['instagram/browser.py', 'Navegación normal en Chromium con cookies. Lee DOM y respuestas entregadas a la página. No reproduce llamadas internas.'],
    ['gemini_analysis.py', 'SDK oficial google-genai; entrada limitada, esquema JSON, validación de puntuaciones y citas, errores sin secretos.'],
    ['benford.py', 'Primer dígito, distribución teórica, chi-cuadrado, p-valor y controles de calidad de muestra.'],
    ['big_five.py', 'Método léxico histórico, conservado para demostración y pruebas. No sustituye a Gemini si la API falla.'],
], [140,W-140])
p('Correcciones verificadas con Instagram real', 'h')
p('Instagram entregó JSON con tipo text/javascript, que antes se ignoraba. También usó enlaces de seguidores con href="#" y un nombre accesible con el conteo. El extractor ahora admite ambas variantes y espera de forma acotada a los datos del perfil. La prueba de regresión reproduce estos cambios.')
p('Protección de la sesión y de los datos', 'h')
p('El inicio de sesión se completa manualmente; al guardar cookies la ventana se cierra. HTTP 429 activa una espera persistente y detiene nuevas consultas. La cancelación conserva resultados parciales. Las descargas multimedia usan las URL de CDN recibidas y no envían cookies a esos dominios.')
p('Gemini recibe solo la biografía y los pies de contenido. Se eliminan enlaces y menciones del texto y se usan IDs de fuente locales. No se envían listas de relaciones, cookies, fotos ni videos. Los propios textos aún pueden contener datos personales.', 'small')

page(); title('02 | Big Five', 'Configuración y límites de Gemini')
p('La aplicación usa el SDK oficial de Google y el modelo configurable GEMINI_MODEL, con valor inicial gemini-flash-latest. La clave se lee localmente desde GEMINI_API_KEY. La disponibilidad del modelo y la cuota dependen de la cuenta de Google.')
table(['Paso', 'Acción'], [
    ['1. Instalar', 'py -m venv .venv\n.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt\n.\\.venv\\Scripts\\python.exe -m playwright install chromium'],
    ['2. Configurar', 'Copia .env.example a .env si no existe. Completa GEMINI_API_KEY y reinicia la aplicación.'],
    ['3. Abrir', '.\\.venv\\Scripts\\python.exe gui.py'],
    ['4. Reutilizar datos', 'Escribe jhonatan.coronel y pulsa Gemini: datos guardados. Por consola: python main.py --reanalyze jhonatan.coronel'],
], [110,W-110])
p('Salida del modelo', 'h')
p('Cinco dimensiones: apertura, responsabilidad, extraversión, amabilidad y neuroticismo. Cada una devuelve score 0-100 o null, una justificación, confianza declarada y citas asociadas a sus fuentes. El programa rechaza puntuaciones fuera de rango y citas que no existen en la entrada. La confianza del modelo no es una probabilidad calibrada.')
p('Antes de enviar se requieren 100 palabras y dos fuentes. La entrada se limita a 80.000 caracteres y se registra si fue truncada. Una puntuación requiere citas de dos fuentes distintas. Son controles del proyecto, no criterios psicométricos validados. No se analiza imagen, apariencia ni audio.')
p('Errores y evidencia insuficiente', 'h')
p('La falta de clave produce not_configured. Una respuesta mal formada produce invalid_response. Los errores 400/401/403/404/429 y de conexión se muestran sin revelar credenciales. Se realiza un intento, con timeout de 60 segundos. Si falta evidencia, no se inventan puntuaciones.')
p('<b>La salida es exploratoria, no una prueba psicológica validada ni un diagnóstico.</b> Neuroticismo es el nombre de una dimensión teórica. No usar para decisiones sobre personas.')
p('Documentación del SDK: <link href="https://googleapis.github.io/python-genai/" color="#175cd3">googleapis.github.io/python-genai</link>. La llamada autenticada real permanece pendiente.', 'small')

page(); title('03 | Resultados guardados', 'Benford y evidencia de las pruebas')
p('En la extracción de contenidos se guardaron 25 elementos, de los cuales 10 tienen pie de texto no vacío, y 35 archivos multimedia. El perfil registró 416 seguidores y 242 seguidos. La extracción posterior de relaciones guardó 415 y 240; son capturas en momentos distintos y el final comunicado por el servidor no certifica visibilidad total.')
rows=[]
for rel, metric, label in [('followers','follower_count','Seguidores de seguidores'),('following','following_count','Seguidos de seguidos')]:
    a=benford.analyze_dataset(data,rel,metric)
    rows.append([label, str(a['sample_size']), f"{a['chi_square']:.4f}", f"{a['p_value']:.6f}",a['assessment']['label']])
table(['Conjunto','n válido','Chi²','p-valor','Interpretación'], rows, [132,49,65,67,W-313])
p('P(d)=log10(1+1/d). Chi-cuadrado compara las frecuencias observadas con n×P(d), con 8 grados de libertad. Se excluyen los ceros del primer dígito. Compatible: p≥0,05; desviación moderada: 0,01≤p&lt;0,05; fuerte: p&lt;0,01. Si hay datos incompletos o frecuencias esperadas menores que 5, no se clasifica el ajuste.')
p('<b>Estos resultados no identifican bots ni humanos.</b> Los umbrales describen significación estadística. No se ha demostrado que los conteos de esta red sean independientes o adecuados para Benford.')
p('Cobertura de las pruebas', 'h')
table(['Evidencia','Qué demuestra'], [
    ['Ejecuciones reales guardadas', 'La navegación con cookies y la extracción funcionaron en estas ejecuciones del perfil indicado. No garantiza futuras sesiones ni ausencia de bloqueos.'],
    ['Chromium y Tkinter', 'Fixtures interceptados para perfil, publicaciones, reels, listas, 429, formato actual y componentes de interfaz.'],
    ['Gemini simulado', 'El SDK construye la petición y procesa una respuesta controlada. Se prueban clave ausente, cuota/acceso, JSON inválido, citas inventadas y puntuaciones inválidas.'],
    ['Prueba pendiente', 'Gemini con clave real, modelo disponible y cuota suficiente. El archivo _gemini.json conserva este estado explícito.'],
], [145,W-145])
p(f"Resultado final: {suite.get('tests')} pruebas aprobadas. Evidencia JUnit: output/qa/gemini-tests.xml. Las capturas QA anteriores muestran demostraciones sintéticas de la versión previa; no son respuestas reales de Gemini.", 'small')

def footer(canvas, doc):
    canvas.setStrokeColor(colors.HexColor('#d9e2ef')); canvas.line(46,45,A4[0]-46,45)
    canvas.setFont('Body',8); canvas.setFillColor(NAVY)
    canvas.drawString(46,30,'PERFILLAB | Entrega Gemini y pruebas | 27 octubre 2026')
    canvas.drawRightString(A4[0]-46,30,str(doc.page))
destination=OUT/'pdf/PerfilLab_Entrega_Gemini_y_pruebas.pdf'
destination.parent.mkdir(parents=True,exist_ok=True)
SimpleDocTemplate(str(destination),pagesize=A4,leftMargin=46,rightMargin=46,topMargin=43,bottomMargin=61,
    title='PerfilLab - Entrega Gemini y pruebas',author='Proyecto PerfilLab').build(story,onFirstPage=footer,onLaterPages=footer)
print(destination)
