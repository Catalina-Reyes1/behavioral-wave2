# Behavioral Wave

Proyecto universitario de Finanzas Conductuales sobre NVIDIA (NVDA), con VOO como aproximación al S&P 500.

## Qué estudiamos

¿Una ola extraordinaria de atención pública, cuando empieza a agotarse después de un movimiento extremo del precio, anticipa una reversión de corto plazo?

La atención es limitada: un activo que destaca puede entrar en el conjunto de alternativas que consideran los inversionistas. Este fundamento está relacionado con [Barber y Odean (2008), *All That Glitters*](https://academic.oup.com/rfs/article-abstract/21/2/785/1607197). El proyecto estudia una hipótesis de atención y posible sobre-reacción; no demuestra que las visitas causen compras ni identifica directamente comportamiento de rebaño.

## Qué mide el IOC

Usamos visitas diarias al artículo **NVIDIA, Inc.** de Wikipedia en inglés: `en.wikipedia`, `NVIDIA,_Inc.`, `all-access`, agente `user`, granularidad `daily`. [Wikimedia Pageviews](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html) ofrece una fuente pública, histórica y reproducible de atención online. Las visitas no son personas únicas y no todos los visitantes son inversionistas.

El IOC es un indicador construido para este trabajo, **no un indicador académico estándar**:

1. `Log_Pageviews = log(1 + Pageviews)`.
2. Comparar el valor actual con la media y desviación estándar muestral de los **60 días calendario anteriores**. `shift(1)` excluye el día actual; la desviación usa `ddof=1`.
3. `Attention_Z = (Log_Pageviews - media_pasada) / sigma_pasada`.
4. `IAA = max(Attention_Z, 0)`.
5. `IOC = 100 * tanh(IAA / 2)`.

La escala 0–100 facilita interpretar intensidad; tanh no crea capacidad predictiva. Ejemplo conceptual: **20 → 45 → 72 → 91 → 80** representa expansión y posterior agotamiento de atención. No son datos del estudio.

El IOC **no mide sentimiento, optimismo, pesimismo ni causalidad**. `IOC_Velocity` y `IOC_Acceleration` son sus primeras y segundas diferencias diarias; no agregan reglas de entrada.

## AR, CAR y los dos modelos de retorno normal

El **Market Model** estima solamente con Train:

`NVDA_Return = alpha + beta * VOO_Return + epsilon`

Después congela alpha, beta y la desviación muestral de los residuos Train. `Expected_Return = alpha + beta * VOO_Return`; **AR** es el retorno observado menos el esperado. **CAR_5** suma cinco AR consecutivos y `CAR_Z = CAR_5 / (sigma_epsilon * sqrt(5))`.

El segundo modelo es **CAPM**. Usa `RF_Daily = (^IRX / 100) / 252`, aproximación diaria del rendimiento anualizado del Treasury Bill de 13 semanas. Estima con Train los excesos de NVDA y VOO sobre esa tasa. Las tasas faltantes solo pueden arrastrarse desde fechas anteriores. CAPM sirve como segunda referencia para evaluar retornos anormales; no modifica las señales.

## Cómo se genera y evalúa una señal

Los umbrales se calculan una sola vez con Train: percentil 90 de IOC y percentiles 90/10 de CAR_Z. Test no participa en su estimación.

Una ola se agota si el IOC de la **sesión de mercado previa** estaba sobre su umbral y el IOC actual cae. Si además CAR_Z es extremadamente positivo, `Signal = -1`: posible reversión bajista. Si CAR_Z es extremadamente negativo, `Signal = +1`: posible reversión alcista. En otro caso, `Signal = 0`.

`Signal` se observa en t. `Trade_Signal = Signal.shift(1)` la sitúa en la siguiente sesión de mercado t+1, sin volver a desplazarla en el backtest. El primer Trade_Signal es NaN porque no hay sesión anterior: no representa una operación. No se rellena artificialmente.

Cada evento dura **cinco sesiones**, contando la fila de entrada. Se compone el retorno de NVDA y se multiplica por la dirección (+1 larga, −1 corta). Se descuentan **0,10% de entrada + 0,10% de salida = 0,20%**. El retorno anormal neto resta además el retorno normal compuesto, ajustado por la dirección, de cada modelo.

Los eventos solapados se conservan por separado. El retorno compuesto de eventos es descriptivo: **no es el rendimiento de una cartera implementable**.

## Muestra y resultados principales

Período principal congelado: **03/04/2017–08/09/2026**, con **2.371 sesiones**. La atención cruda comienza el 02/02/2017 para completar 60 días previos; los precios incluyen el cierre del 31/03/2017 para calcular el primer retorno.

División cronológica: **1.659 sesiones Train (70%) / 712 Test (30%)**. Test comienza el **03/11/2023**. No hay división aleatoria ni ajuste de reglas mirando Test.

| Resultado | Train | Test |
|---|---:|---:|
| Eventos y operaciones completas | 53 | 17 |
| Ganadoras después de costos | 39,62% | 52,94% |
| Retorno neto promedio por evento | −2,276% | +1,684% |
| p-value bilateral del neto medio | No se usa como evaluación fuera de muestra | 0,342869 |

En Test, el retorno anormal neto medio es **+0,460% frente al Market Model** (p = **0,795918**) y **+0,464% frente a CAPM** (p = **0,794057**). Ninguno es significativo al 5%. Fuente: [resumen guardado](results/backtest_summary.csv).

**70 eventos no significa 70 sesiones**: son episodios selectivos encontrados dentro de las 2.371 sesiones. Exigen atención extraordinaria, agotamiento y un movimiento anormal extremo simultáneamente.

La web también muestra los resultados **ya archivados** de 2019–2026: 1.931 sesiones, 58 eventos, 11 Test, neto medio Test +2,54% y p = 0,0534. No se recalculan ni se elige ese período por su resultado. Las muestras se solapan y sus cortes Train/Test difieren: no son dos validaciones independientes.

## Abrir y usar la página

URL pública: **https://jgonzalezg13-ai.github.io/behavioral-wave/**. Los cambios locales de esta auditoría todavía no están publicados: no se hizo commit ni push.

También se puede abrir `app/index.html` por doble clic, conservando juntos los archivos de `app/`. La biblioteca Plotly y el snapshot son locales. Otra opción, desde la carpeta del proyecto:

```powershell
python -m http.server 8000 --bind 127.0.0.1 --directory app
```

Abrir `http://127.0.0.1:8000`; detener con Ctrl+C.

En la página:

1. Leer el IOC como intensidad de atención.
2. Usar los filtros Todo / Train / Test y el rango de fechas del gráfico.
3. Pasar sobre cada marcador para ver la fecha real del evento, NVDA, IOC, CAR_Z, Sample y la entrada t+1. Dos eventos cercanos mantienen sus fechas propias.
4. Comparar Train y Test y revisar p-values, costos y limitaciones antes de interpretar una posible reversión.

## Ejecutar el proyecto

Desde la carpeta `behavioral-wave`, con Python compatible con las dependencias (esta auditoría utilizó Python 3.14):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Con el entorno activado, basta `python main.py`. El pipeline descarga NVDA/VOO y Wikimedia, calcula Market Model → IOC → señales → CAPM → backtest y exporta la web. Requiere conexión y disponibilidad de Yahoo/Wikimedia. **GDELT no se ejecuta automáticamente**: su implementación se conserva como extensión futura tras HTTP 429.

Las fechas están centralizadas en `config.py`. El corte final es inclusivo; `main.py` adapta el límite exclusivo de Yahoo y se detiene antes de guardar si las fuentes no cubren el período congelado. No se debe ejecutar el descubrimiento histórico para esta entrega: la muestra ya está fijada. Las revisiones de proveedores o versiones futuras de dependencias pueden cambiar una nueva descarga; los CSV archivados y sus hashes son la referencia exacta de esta entrega.

Para presentar o actualizar solamente los JSON usando los resultados existentes, sin descargar ni reestimar:

```powershell
.\.venv\Scripts\python.exe -m src.export_web_data
```

Para validar:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m src.audit_final
```

**52 pruebas Python aprobadas** y dos escenarios de JavaScript simulados (HTTP y archivo local). La auditoría independiente solo escribe evidencia en `docs/`. No cambia los CSV. El detalle está en [auditoria_final.md](docs/auditoria_final.md); no sustituye la revisión visual en navegador, que sigue pendiente.

## Estructura de carpetas

| Ruta | Contenido |
|---|---|
| `config.py`, `main.py` | Fechas y coordinación del pipeline |
| `src/` | Descargas, modelos, atención, señales, backtest, exportación y auditoría |
| `data/raw/` | Datos de origen y metadatos de descarga |
| `data/processed/` | Modelos, onda de atención, señales y operaciones |
| `results/backtest_summary.csv` | Resultados separados Train/Test/Total |
| `results/pre_expansion/` | Resultados históricos archivados, sin recalcular |
| `app/` | Página, estilos, JavaScript y biblioteca gráfica local |
| `app/data/` | JSON y snapshot derivados de los CSV |
| `tests/` | Pruebas de cálculo, integración, integridad y web |
| `docs/` | Bitácora, auditoría y evidencia numérica |

## Limitaciones y valor económico

La herramienta puede servir como alerta complementaria para un inversionista minorista o variable de investigación en modelos institucionales de riesgo, timing o ejecución. No reemplaza el análisis fundamental ni genera una recomendación automática; su utilidad incremental no está demostrada.

Las principales limitaciones son: solo NVDA y un artículo en inglés; atención no equivale a sentimiento; 17 eventos Test; operaciones solapadas que limitan la independencia del t-test; comparación de períodos no independiente; aproximación de RF y del retorno normal; ausencia de costos de préstamo de acciones para cortos. El backtest no simula capital, margen ni cartera.

La evaluación usa retornos cierre a cierre desde la fila t+1. Aunque no hay retornos futuros en la construcción de señales, esto no demuestra una ejecución real a ese precio: faltan validaciones de horarios UTC de Pageviews, demora de publicación y disponibilidad de cada dato antes de enviar una orden. No se alteró la metodología para resolver esa limitación.

## Conclusión

Behavioral Wave es una herramienta conductual prometedora para identificar episodios de atención y posible sobre-reacción, pero la evidencia actual **no permite afirmar una anomalía robusta y explotable**. Los resultados Test positivos no son estadísticamente significativos frente a cero ni frente a los dos modelos de retorno normal. No permiten rechazar la eficiencia de mercado y tampoco prueban eficiencia perfecta. Las reglas permanecieron congeladas aunque Train es negativo y Test no significativo.
