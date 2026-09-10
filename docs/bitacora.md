# Bitácora

## 2026-09-09
- Se reinicia la implementación técnica desde cero.
- Se conserva el diseño conceptual ya acordado.
- Activo piloto: TSLA.
- Benchmark: VOO como proxy del S&P 500.
- La primera tarea técnica es descargar precios diarios y calcular retornos.

### Bloque financiero completado
- Precios y retornos diarios de TSLA y VOO disponibles.
- Modelo de mercado estimado con el 70% inicial (Train); alpha y beta congelados para Test.
- Retornos esperados, AR, CAR_5 y CAR_Z guardados en `data/processed/market_model.csv`.
- Esta etapa conserva `src/abnormal_returns.py` y su metodología sin cambios.

### Inicio de información conductual: GDELT
- GDELT DOC 2.0 elegido como fuente pública inicial. Consulta literal: `Tesla`; no se buscan menciones aisladas de Elon Musk. Puede incluir usos de Tesla ajenos a la empresa: queda pendiente evaluar la precisión temática.
- `src/gdelt_data.py` consulta `TimelineVolRaw` (conteos de artículos, no porcentajes) y `TimelineTone` (tono promedio de la cobertura), sin suavizado. La documentación indica resolución diaria para consultas de más de una semana: [documentación oficial](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/).
- La [actualización oficial de mayo de 2018](https://blog.gdeltproject.org/doc-2-0-updates-1-5-year-searching-and-updated-mobile-interface/) amplió los timelines desde 2017. En la comprobación realizada se recibió HTTP 200 con conteos diarios de Tesla desde el 2019-01-01. Esto verifica acceso a esa ventana, no certifica todavía el histórico completo de volumen y tono.
- Descarga automática en ventanas de hasta 365 días desde 2019-01-01. Fechas UTC `YYYY-MM-DD`, incluidos fines de semana. Se excluye el día UTC actual por estar incompleto. Una ventana final corta se amplía hacia atrás para conservar resolución diaria; los solapamientos idénticos se deduplican y los contradictorios se rechazan.
- Se requieren fechas coincidentes para volumen y tono. Los días ausentes no se rellenan ni se convierten en ceros. Con conteo cero, el tono se deja vacío porque no existe un promedio definido. `News_Tone` es tono de la cobertura, no sentimiento de inversionistas.
- Archivo esperado: `data/raw/tsla_gdelt.csv`, con `Date`, `News_Count`, `News_Tone`. Las respuestas originales y parámetros se conservan en `data/raw/gdelt_responses/`. `tsla_gdelt.metadata.json` registra fechas solicitadas y obtenidas, días faltantes y consultas. Las respuestas guardadas se reutilizan para reproducir resultados y reanudar descargas.
- Se manejan timeout, errores HTTP/red, respuesta vacía, JSON y columnas inesperadas. Hay pausas de al menos seis segundos entre consultas y dos reintentos con esperas de 30 y 60 segundos. Una descarga fallida no reemplaza un CSV anterior ni presenta sus estadísticas como actuales. Solo ante un rechazo explícito de antigüedad se intenta `timespan=3m`, documentando la limitación; las ventanas no eluden restricciones históricas del servidor.
- `TimelineSourceCountry` desglosa cobertura por país de la fuente, no por número de medios. Contar países con cobertura positiva podría medir amplitud geográfica, pero exige validar exhaustividad, estabilidad y tratamiento de países ausentes. La consulta de comprobación recibió HTTP 429. **Source_Breadth pendiente; no se genera la columna.**
- La descarga completa recibió HTTP 429 de GDELT, también al reintentar con ventanas anuales y esperas de 30 y 60 segundos. **No se generó `tsla_gdelt.csv`: sigue pendiente obtener y validar el histórico real.** No se generaron datos sintéticos como sustituto. La extensión puede ejecutarse manualmente con `python -m src.gdelt_data`; ya no se ejecuta desde `main.py`.
- Nueve pruebas automatizadas pasaron con `python -m unittest discover -s tests -v`. Cubren validación, fechas, ventanas, duplicados, errores, caché, cobertura parcial, conservación del CSV ante fallos y orden de ejecución en `main.py`. Usan respuestas simuladas y no sustituyen la validación de la descarga real.
- GDELT se integró inicialmente después del bloque financiero. Su ejecución automática fue desactivada para el MVP; el módulo se conserva como extensión futura.
- La etapa inicial de GDELT no incluyó IOC, señales ni backtesting.

### MVP: Wikimedia Pageviews e IOC v1
- GDELT quedó implementado y probado, pero la API respondió HTTP 429 al intentar obtener el histórico completo. No se inventaron ni rellenaron datos. No es una dependencia obligatoria del MVP y `src/gdelt_data.py` permanece intacto.
- Para garantizar una entrega reproducible se adoptó Wikimedia Pageviews como proxy inicial de atención pública. Se usa la [API oficial per-article](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html) con proyecto `en.wikipedia`, artículo `Tesla,_Inc.`, acceso `all-access`, agente `user` y granularidad `daily`. Las visitas no representan personas únicas ni sentimiento de inversionistas.
- `src/wikimedia_attention.py` consulta desde 2019-01-01 hasta el último día UTC completo y conserva la última fecha efectivamente publicada por la API. Usa `requests`, User-Agent descriptivo, timeout y reintentos para errores transitorios. El histórico cabe en una solicitud, reduciendo la carga sobre la API.
- Serie cruda: `data/raw/tsla_wikipedia_pageviews.csv` (`Date`, `Pageviews`). Se conservan además la respuesta JSON original y metadatos con URL, parámetros, fecha de descarga y fechas faltantes. Esto permite reconstruir el cálculo sin volver a consultar una fuente que puede revisar sus datos.
- Las fechas se convierten a datetime, se ordenan y se guardan como `YYYY-MM-DD`. Se utiliza calendario diario, incluidos fines de semana. Si falta una fecha dentro del período, queda explícitamente como NaN: no se imputa, interpola ni convierte en cero. Tampoco se crean observaciones posteriores a la última fecha publicada.
- `Log_Pageviews = log(1 + Pageviews)`. La referencia usa `shift(1).rolling(60, min_periods=60)`: media y desviación estándar muestral (`ddof=1`) de los 60 días calendario anteriores, excluyendo t. Se exige la ventana completa. Las primeras 60 observaciones y las ventanas afectadas por faltantes no tienen z-score. Si sigma es cero, el resultado queda como NaN, sin infinito ni valor arbitrario.
- `Attention_Z = (Log_Pageviews - media_pasada) / sigma_pasada`; `IAA = max(Attention_Z, 0)`; `IOC = 100 * tanh(IAA / 2)`. **IOC v1 mide intensidad de atención anormal positiva**, entre 0 y aproximadamente 100; no mide dirección positiva/negativa. La futura dirección de una eventual sobre-reacción se determinará con el signo de CAR, sin implementarla todavía.
- `IOC_Velocity` es la primera diferencia diaria de IOC y `IOC_Acceleration` la diferencia de esa velocidad. Se preservan los NaN de calentamiento: velocidad comienza después del primer IOC válido y aceleración un día después.
- Resultado: `data/processed/attention_wave.csv`, con `Date`, `Pageviews`, `Log_Pageviews`, `Attention_Z`, `IAA`, `IOC`, `IOC_Velocity`, `IOC_Acceleration`.
- Descarga real verificada: **2019-01-01 a 2026-09-08, 2.808 observaciones, sin fechas faltantes**. Promedio de visitas: 8.186,86. Máximo de visitas: 64.512 el 2021-01-08. Máximo IOC: 99,991960 el 2023-07-14.
- `python main.py` ejecuta el bloque financiero y luego Wikimedia; muestra las estadísticas solicitadas y las últimas cinco observaciones. `python -m src.wikimedia_attention` permite ejecutar solo esta etapa. No se modificaron `config.py` ni `abnormal_returns.py`.
- Pasaron 16 pruebas con `python -m unittest discover -s tests -v`: fórmulas verificadas contra cálculo independiente, exclusión del día actual, invariancia del pasado ante cambios futuros, fechas faltantes, sigma cero, errores de API e integración sin invocar GDELT.
- Ejecución real de `main.py` completada con código de salida 0: descarga financiera, modelo de mercado y Wikimedia, sin consultas a GDELT. Ambos CSV de atención se contrastaron con la respuesta oficial guardada y el recálculo; no hay huecos ni infinitos. Primer IOC válido: 2019-03-02, después de 60 días de referencia.
- Sentimiento y propagación quedan como extensiones posteriores del IOC. No se implementaron señales, backtest, HTML ni variables ficticias.

### Integración de atención y retornos anormales: eventos y señales
- `src/signals.py` lee `data/processed/market_model.csv` y `data/processed/attention_wave.csv`. Realiza una unión izquierda por Date, ordenada, conservando únicamente el calendario del mercado y sus etiquetas Sample originales. No vuelve a dividir Train/Test ni recalcula el modelo financiero o el IOC.
- Los umbrales se estiman una sola vez con las filas **Train del mercado unido**: percentil 90 de IOC, percentil 90 de CAR_Z y percentil 10 de CAR_Z. Se usa interpolación lineal y se excluyen NaN por variable, sin eliminar filas del calendario. Los tres valores quedan congelados para Test y se incluyen como columnas constantes en el CSV para su auditoría. No se optimizan percentiles con Test. Los eventos Train son de calibración dentro de muestra, no una evaluación fuera de muestra.
- `Wave_Extreme = IOC >= IOC_Extreme_Threshold`. `Wave_Exhaustion` requiere que IOC disminuya respecto de la sesión anterior y que el IOC de esa sesión haya alcanzado el umbral extremo. Los desplazamientos se realizan **después de unir sobre días de mercado**: el lunes se compara con la sesión anterior, no con el domingo. `IOC_Velocity` se conserva tal como fue calculada en la serie diaria de atención; no sustituye esta condición.
- `Positive_Overreaction = CAR_Z >= CAR_Positive_Threshold`; `Negative_Overreaction = CAR_Z <= CAR_Negative_Threshold`. Agotamiento más sobre-reacción positiva genera `Signal = -1` (posible reversión negativa); agotamiento más sobre-reacción negativa genera `Signal = +1` (posible reversión positiva). En otro caso, Signal es cero. No se agregan filtros, sentimiento ni reglas adicionales. Si los percentiles de CAR_Z coinciden, se informa un error por dirección ambigua.
- `Trade_Signal = Signal.shift(1)` sobre el calendario de mercado: la señal observada en t se habilita desde la siguiente sesión. La primera fila queda NaN porque no tiene señal anterior. El desplazamiento continúa en el límite Train/Test; un evento en la última fila Train puede aparecer como Trade_Signal en la primera fila Test. Los conteos se asignan por la fecha del evento Signal, no por la fecha desplazada. Es una convención de disponibilidad para esta etapa, no una simulación de ejecuciones ni una garantía sobre horarios de publicación de la fuente.
- Los días de mercado sin atención se conservan con NaN; no se imputan datos y no generan un nuevo evento. No se salta el hueco al desplazar señales. La observación de mercado del 2026-09-09 todavía no tiene Pageviews en los archivos de entrada validados.
- Resultado: `data/processed/behavioral_signals.csv`, con Date, Sample, TSLA_Return, VOO_Return, AR, CAR_5, CAR_Z, Pageviews, Attention_Z, IOC, IOC_Velocity, los tres umbrales, las cuatro condiciones booleanas, Signal y Trade_Signal.
- Ejecución sobre los CSV validados: IOC_Extreme_Threshold = 68,94083239; CAR_Positive_Threshold = 1,12192713; CAR_Negative_Threshold = -1,14386452. Se generaron **58 eventos: 47 Train y 11 Test; 32 alcistas (+1) y 26 bajistas (-1)**.
- `main.py` ejecuta esta etapa después de Wikimedia. `python -m src.signals` permite reproducirla directamente desde los CSV existentes, sin descargar nuevamente precios o atención. La terminal muestra los umbrales, conteos y las últimas diez fechas con eventos.
- Las pruebas verifican los umbrales, las dos direcciones, el uso de la siguiente sesión, el cruce Train/Test, los fines de semana, los faltantes, el CSV y que alterar Test no modifica los umbrales ni los resultados de Train.
- No se modificaron `abnormal_returns.py`, `wikimedia_attention.py` ni `config.py`. No se implementaron costos, retornos acumulados, backtest ni HTML.

### Evaluación económica fija: CAPM y backtest de eventos

- `src/capm_model.py` incorpora [^IRX de Yahoo Finance](https://finance.yahoo.com/quote/%5EIRX/), rendimiento anualizado porcentual del Treasury Bill a 13 semanas, mediante `yfinance`. Se conserva su Close original en `data/raw/irx.csv`. Se consulta un margen de 30 días anterior al inicio para disponer de observaciones pasadas al comenzar la muestra.
- Aproximación solicitada: `RF_Daily = (IRX_Annual_Percent / 100) / 252`; no es una conversión exacta de la cotización de descuento del Treasury Bill. La tasa se une al calendario antes de aplicar exclusivamente `ffill`. No se usa backward fill; si no existe una tasa previa, queda NaN. `RF_Observation_Date` permite auditar la fecha de origen de cada tasa utilizada.
- `TSLA_Excess = TSLA_Return - RF_Daily`; `Market_Excess = VOO_Return - RF_Daily`. MCO con intercepto estima alpha CAPM y beta CAPM exclusivamente con filas Train completas. Se conservan Sample y el corte existentes. Los parámetros quedan congelados para toda la muestra. Sigma epsilon CAPM es la desviación estándar muestral (`ddof=1`) de los residuos Train.
- `CAPM_Expected_Return = RF_Daily + alpha_capm + beta_capm * Market_Excess`; `CAPM_AR = TSLA_Return - CAPM_Expected_Return`. Se guarda `data/processed/capm_model.csv`, incluyendo el Market Model original para comparar ambos modelos sobre los mismos retornos. Resultado de la ejecución completa: alpha CAPM 0,00138014; beta CAPM 1,49307335; sigma 0,03539911; 1.351 observaciones Train y 580 Test válidas; ninguna fecha de mercado sin tasa.
- `src/backtest.py` utiliza las filas donde `Trade_Signal` vale +1 o -1 como entradas. **No desplaza nuevamente la señal.** Para una entrada en la fila i, evalúa exactamente i, i+1, i+2, i+3 e i+4 del calendario de mercado: `Forward_Return_5D = producto(1 + TSLA_Return) - 1`. No modifica señales, percentiles, Train/Test ni horizonte después de ver Test.
- `Strategy_Gross_Return = Trade_Signal * Forward_Return_5D`; así, un corto gana cuando TSLA cae. Se descuentan exclusivamente 0,001 por entrada y 0,001 por salida: `Transaction_Cost = 0.002`; `Strategy_Net_Return = Strategy_Gross_Return - Transaction_Cost`. **No se incluyen costos de préstamo de acciones para cortos**, una limitación de la evaluación.
- Los retornos normales de cinco sesiones son `producto(1 + Expected_Return) - 1` para Market Model y `producto(1 + CAPM_Expected_Return) - 1` para CAPM. Se evalúan ex post con los retornos VOO y tasas del horizonte; no se utilizan para construir ni seleccionar las señales.
- Se define explícitamente el retorno anormal de la estrategia **después de costos**: `Abnormal_Strategy_MarketModel = Strategy_Net_Return - Trade_Signal * MarketModel_Normal_5D`; análogamente para CAPM. Equivale a multiplicar por la dirección la diferencia entre retorno TSLA y retorno normal, y restar 0,002.
- Los solapamientos se mantienen como operaciones separadas; no se compensan posiciones, asigna capital, reduce exposición ni seleccionan eventos. Date y Sample corresponden a la entrada. IOC y CAR_Z se conservan en esa fecha; las columnas adicionales `Signal_Date`, `Signal_Sample`, `Signal_IOC` y `Signal_CAR_Z` identifican la información del evento que originó la entrada y no intervienen en el cálculo futuro de retornos.
- Se registra `Exit_Date`, `Status` y `Crosses_Sample_Boundary`. Una entrada sin cinco sesiones futuras queda `Incomplete_Horizon`; si faltan retornos dentro del horizonte queda `Missing_Returns`. Ambas se conservan en el archivo con resultados NaN y se excluyen del resumen económico; no se acorta la operación ni se reemplazan retornos faltantes por cero.
- Las etiquetas Sample no se modifican. Para los resúmenes separados, un evento debe tener señal, entrada y las cinco sesiones dentro de la misma muestra. Los cruces se conservan en Total y se reportan como `Boundary_Events`, sin contaminar la evaluación separada Train/Test. Con los datos actuales no hubo cruces ni eventos incompletos: las 58 operaciones se evalúan íntegramente.
- `data/processed/backtest_events.csv` conserva los eventos y todos los retornos requeridos. `results/backtest_summary.csv` presenta Train, Test y Total: operaciones, porcentaje ganador neto, media bruta/neta, mediana neta, desviación estándar muestral neta, compuesto neto de eventos y medias anormales netas frente a ambos modelos. Los retornos se guardan en decimales; `Win_Rate_Pct` se expresa en porcentaje. Una operación ganadora tiene retorno neto estrictamente positivo.
- El acumulado `Cumulative_Event_Net_Return = producto(1 + Strategy_Net_Return) - 1` es una estadística descriptiva de los eventos. **No es una curva de capital de una cartera realizable**, porque las operaciones se solapan y no se modela asignación de capital. El uso de retornos diarios cierre a cierre desde la fila de entrada es la aproximación solicitada; no demuestra que una orden real colocada en t+1 pueda capturar todo ese retorno. Tampoco se modela el horario efectivo de publicación de Pageviews.
- En Test se aplica el [test t bilateral de una muestra](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_1samp.html), H0: media igual a cero, para retorno neto y los dos retornos anormales netos. Se reportan t-statistic y p-value sin ajustar por solapamientos. **Son pruebas nominales**: el supuesto de independencia puede fallar entre eventos solapados; no se presentan como evidencia concluyente. Con menos de dos observaciones o desviación cero se informa NaN.

| Resultado | Train | Test | Total |
|---|---:|---:|---:|
| Operaciones | 47 | 11 | 58 |
| Ganadoras netas | 38,30% | 63,64% | 43,10% |
| Retorno bruto medio | -2,3554% | 2,7432% | -1,3885% |
| Retorno neto medio | -2,5554% | 2,5432% | -1,5885% |
| Mediana neta | -1,7024% | 1,4923% | -0,6547% |
| Desviación neta | 7,9067% | 3,8524% | 7,5578% |
| Compuesto neto de eventos (no cartera) | -74,6177% | 30,8904% | -66,7770% |
| Anormal neto medio vs Market Model | -2,0878% | 1,9144% | -1,3288% |
| Anormal neto medio vs CAPM | -2,0783% | 1,9097% | -1,3220% |

| Test: hipótesis de media cero | t-statistic | p-value bilateral |
|---|---:|---:|
| Retorno neto | 2,189474 | 0,053383 |
| Anormal neto vs Market Model | 1,759907 | 0,108920 |
| Anormal neto vs CAPM | 1,760739 | 0,108773 |

- Test tiene retorno neto promedio positivo, pero ninguna de las tres pruebas rechaza H0 al nivel nominal del 5%. Train y Total tienen pérdidas promedio netas. Estos resultados se conservan sin modificar reglas ni buscar percentiles o horizontes alternativos. Los 11 eventos Test y sus solapamientos limitan la fuerza de la conclusión.
- `main.py` ejecuta mercado → retornos anormales → Wikimedia → señales → CAPM → backtest, con la sección `BEHAVIORAL WAVE BACKTEST`. La ejecución real completa terminó con código 0. Pasaron **35 pruebas** automatizadas, incluyendo forward fill causal, invariancia de parámetros al cambiar Test, signos de cortos, costos, cinco sesiones sin doble desplazamiento, eventos solapados/incompletos, cruces de muestra y tests estadísticos.
- Los CSV originales de mercado, atención y tasas permiten reconstruir los resultados. Una nueva descarga puede revisar ligeramente precios ajustados; se valida que señales y CAPM usen la misma versión del mercado antes de evaluar. Los parámetros se vuelven a estimar solo en Train cuando se regenera el flujo; nunca se ajustan con Test.
- No se modificaron las metodologías de `abnormal_returns.py`, `wikimedia_attention.py` ni `signals.py`. GDELT permanece desactivado. No se construyó HTML.

### Presentación web final: Behavioral Wave

- Se reemplazó el prototipo de `app/index.html` por una página única en español, con navegación superior fija: Inicio, La Ola, IOC, Mercado, Señales, Resultados, Metodología y Manual. Incluye portada con KPI, hipótesis conceptual, interpretación del IOC, gráfico histórico, modelos normales, lógica de señales, comparación Train/Test, estadística, costos y conclusión.
- Diseño con fondo blanco y secundario `#F5F5F7`, texto `#1D1D1F`/`#6E6E73` y azul `#0071E3`. Tipografías del sistema; no se descargan fuentes. Verde y rojo se reservan para retornos positivos y negativos. Los marcadores de señales usan azul/gris y triángulos de distinta orientación para no confundir dirección con rentabilidad realizada.
- `app/style.css` incorpora composiciones para escritorio, tablet y móvil, navegación compacta, tablas desplazables, foco de teclado visible, enlace para saltar al contenido, movimiento reducido y estilos de impresión. Las animaciones son apariciones discretas; no hay animaciones continuas.
- `src/export_web_data.py` lee exclusivamente los CSV y metadatos existentes; no llama a descargadores ni ejecuta modelos, señales o backtest. Exporta `app/data/overview.json`, `series.json` y `events.json`. Las cifras del HTML se cargan desde esa exportación, incluyendo resultados negativos, p-values, sesiones, eventos, costos y fechas. Los NaN se serializan como `null`, sin inventar observaciones.
- Como el CSV del Market Model no contiene columnas alpha/beta/sigma, el exportador recupera algebraicamente alpha y beta desde dos pares de VOO_Return y Expected_Return ya guardados y sigma desde CAR_5/CAR_Z. Valida las relaciones contra toda la muestra; **no reestima una regresión ni vuelve a calcular los indicadores**. Los umbrales se leen directamente de las columnas constantes de señales. Los costos de entrada/salida se leen como constantes del código validado sin ejecutarlo y se contrastan con Transaction_Cost. El horizonte se verifica mediante las fechas de los eventos existentes.
- La procedencia incluye rutas y hashes SHA-256 de los archivos usados. La exportación es determinista para la misma entrada. `app/data/snapshot.js` contiene exactamente el mismo conjunto de datos, para abrir la página con doble clic cuando el navegador bloquea fetch sobre `file://`; bajo HTTP se leen los JSON directamente.
- El gráfico usa [Plotly.js 4.0.0](https://plotly.com/javascript/getting-started/) guardado localmente en `app/vendor/`, junto con su licencia MIT. La carpeta app completa es autosuficiente: no necesita conexión a CDN, fuentes externas, un framework o servicios de mercado al presentar. El gráfico separa precio ajustado TSLA e IOC en dos bandas con un eje temporal compartido, evita confundir sus escalas y muestra las fechas de Signal, no las de Trade_Signal.
- Interacciones implementadas: fecha/precio/IOC al pasar el mouse, zoom horizontal por arrastre, restablecimiento por doble clic, períodos Todo/Train/Test/1 año, fechas inicial/final y opción de ocultar marcadores. Se preservan los fines de semana de la atención y los períodos sin IOC válido.
- Train negativo y Test positivo reciben espacio equivalente. La tabla completa incluye Total y el compuesto de eventos, identificado explícitamente como **no representativo de una cartera**. Se mantienen las limitaciones por costos de préstamo no incluidos, ejecución cierre a cierre, muestra Test pequeña y solapamientos. No se presenta correlación como causalidad ni el indicador como una anomalía demostrada o estrategia probadamente rentable.
- Verificación: **40 pruebas Python aprobadas** (35 previas y 5 nuevas de exportación). Las pruebas nuevas contrastan JSON con CSV, parámetros recuperados con resultados guardados, fechas y precios, NaN, determinismo, integridad de entradas y existencia de archivos/enlaces/secciones. Se comprobó la sintaxis de app.js y snapshot.js, y mediante un DOM simulado se probaron la carga HTTP/file, las cifras, tablas, cuatro trazas, 58 marcadores, períodos, validación de fechas, visibilidad de señales y menú móvil. El servidor HTTP local entregó correctamente los archivos de la página.
- **Limitación de verificación visual:** el navegador integrado no estuvo disponible en esta sesión (ningún navegador expuesto por el runtime). No se realizaron capturas ni una inspección visual real en escritorio/tablet/móvil. Los controles se comprobaron de forma simulada y los estilos responsive están implementados; no se presenta esa comprobación como una prueba de renderizado visual.
- Se verificaron hashes antes/después: `config.py`, `main.py`, los cinco módulos financieros/conductuales y sus CSV de resultados permanecen intactos. No se ejecutó el flujo financiero ni se modificó GitHub.

#### Abrir y reproducir la página

Desde la carpeta `behavioral-wave`, para exportar otra vez **los mismos resultados existentes**:

```powershell
python -m src.export_web_data
```

Puede abrirse `app/index.html` por doble clic, conservando juntos todos los archivos de `app/`. También puede servirse localmente:

```powershell
python -m http.server 8000 --bind 127.0.0.1 --directory app
```

Abrir `http://127.0.0.1:8000`. Para detener el servidor, usar Ctrl+C. No es necesario ejecutar `main.py` para presentar o exportar el estudio ya validado.


## 2026-09-09 — Auditoría técnica y académica final

Se auditó la muestra principal congelada 2017-04-03–2026-09-08: 2.371 sesiones, 70 eventos (53 Train / 17 Test). El alcance fue verificar y explicar, no mejorar el resultado. La ampliación histórica previa buscó aumentar observaciones y potencia de evaluación; todas las reglas permanecieron congeladas.

- Se identificó el problema del tooltip: Signal −1 del 03/11/2021 y Signal +1 del 09/11/2021 aparecían agrupadas mediante hover unificado sin fecha individual. El 05/11 tiene IOC 32,468647 y ninguna señal. Los CSV y JSON eran consistentes; no se modificó signals.py.
- Se cambió a hover individual con fecha, precio, IOC, CAR_Z, Sample y entrada t+1. Los 70 eventos siguen presentes.
- La auditoría independiente reconstruyó 3.506 días de atención, AR/CAR y CAPM sobre 2.371 sesiones, 70 operaciones y el resumen. Tolerancia absoluta 1e−9; máximo error IOC inferior a 3e−10. Se documentaron cinco IOC, cuatro señales y tres operaciones completas.
- Perturbar Test no cambia parámetros ni señales Train. El primer Trade_Signal NaN se conserva: no hay sesión previa, no es una orden.
- END_DATE estaba abierto. Se fijó el corte inclusivo pedido, 2026-09-08, y se adaptó el end exclusivo de Yahoo; si las fuentes no cubren ese extremo, main.py se detiene antes de guardar. Esto protege el estudio sin cambiar fórmulas ni resultados.
- Se completaron las explicaciones web de IOC propio del proyecto, Wikimedia, selectividad, valor económico y eficiencia. La robustez 2019–2026 usa únicamente results/pre_expansion/, sin recalcular ni elegir el mejor período.
- README quedó como manual para el grupo. docs/auditoria_final.md contiene evidencia, limitaciones y revisión de los nueve criterios del profesor.
- Validación: 52 pruebas Python aprobadas (40 existentes + 12 nuevas) y dos escenarios JavaScript simulados HTTP/file. No hubo navegador integrado disponible; queda pendiente revisión visual real de escritorio/móvil y hover. No se declara renderizado verificado.
- Se preservaron hashes de 25 archivos de datos, modelos y workflow. No se ejecutó el pipeline financiero real ni se alteraron los CSV. Se regeneraron únicamente las exportaciones web necesarias. No se tocó .github/workflows/static.yml, ni se hizo commit o push.

La conclusión no cambia: 17 Test, 52,94% ganadoras, neto medio +1,684%, p = 0,342869; los excesos frente a Market Model y CAPM tampoco son significativos. No se afirma una anomalía explotable. La evaluación cierre a cierre no garantiza disponibilidad de Pageviews al precio de entrada; esa limitación, el solapamiento y el costo de préstamo de cortos omitido quedan explícitos.

## 2026-09-10 (v2)

### Cambio de activo: de TSLA a NVDA (rehecho sobre el estado actual del repo, post-auditoria)
- Se rehizo el cambio de TSLA a NVDA porque la primera versión se armó contra un clon anterior al commit "Auditoria final y mejoras de Behavioral Wave"; ese commit agregó `src/audit_final.py`, `tests/test_final_audit.py`, `docs/auditoria_final.md` y los tres JSON de evidencia en `docs/`, que la primera versión no tenía y por lo tanto los habría borrado al subirse encima.
- Renombrados TSLA→NVDA y Tesla→NVIDIA en: `config.py`, `main.py`, `README.md`, `app/app.js`, `app/index.html`, y en `src/`: `gdelt_data.py`, `backtest.py`, `wikimedia_attention.py`, `market_data.py`, `export_web_data.py`, `history_period.py`, `signals.py`, `capm_model.py`, `abnormal_returns.py`; y en `tests/`: `test_capm_backtest.py`, `test_web_export.py`, `test_gdelt_data.py`, `test_signals.py`. Incluye columnas con guión bajo (`TSLA_Price`, `TSLA_Return`, etc.) y la clave `tsla_first_price` en `src/history_period.py` (ambas se pierden con un regex de límite de palabra porque `_` no es un límite; se reemplazaron aparte).
- `app/app.js` y `app/index.html`: mismo hallazgo que la primera vez, `row.TSLA_Price` (dato funcional del gráfico) y todo el texto de portada/leyendas quedaban rotos si no se tocaban; corregidos.
- `src/wikimedia_attention.py`: `ARTICLE` pasa a `"Nvidia"` (título real del artículo en Wikipedia en inglés, sin sufijo de desambiguación; un reemplazo ingenuo de "Tesla"→"NVIDIA" habría dejado `"NVIDIA,_Inc."`, que no existe como tal).
- `src/gdelt_data.py`: ruta de salida por defecto `data/raw/tsla_gdelt.csv` → `data/raw/nvda_gdelt.csv` (función opcional, no la llama `main.py`).
- **Deliberadamente NO se tocaron** `src/audit_final.py`, `tests/test_final_audit.py`, `docs/auditoria_final.md`, `docs/audit_calculations.json`, `docs/audit_input_hashes.json`, `docs/audit_web_checks.json`: son la auditoría independiente de Jordi sobre la entrega **congelada de TSLA** (su propio docstring dice "archivos congelados"). Renombrarlos a ciegas habría dejado un informe que afirma verificar NVDA sin haberlo hecho. Esa auditoría hay que rehacerla — manifest de hashes, casos y texto — sobre los datos reales de NVDA una vez estén generados; queda pendiente y es criterio de Jordi, no un renombrado mecánico.
- `config.py`: `START_DATE`, `ATTENTION_START_DATE`, `MARKET_DOWNLOAD_START` vuelven a `None` a propósito (NVDA cotiza desde antes que TSLA y su artículo de Wikipedia existe desde antes, así que las fechas resueltas para TSLA no sirven); `END_DATE` se conserva porque es un corte fijo del estudio, no depende del activo (así lo señala también la excepción documentada en `audit_final.audit_hashes`).
- Se eliminaron `data/raw/tsla_wikipedia_pageviews.metadata.json` y `.response.json` (huérfanos). No se tocó `data/raw/history_discovery/*` (nombres genéricos, se sobrescriben solos al correr `python -m src.history_period`) ni `results/pre_expansion/` ni las entradas previas de esta bitácora.
- Pruebas: `python3 -m unittest discover -s tests -v` → 52 pruebas, 36 aprobadas, 5 omitidas (necesitan los CSV reales generados, ya era así en el repo de Jordi sin tocar nada), 10 errores + 1 falla. De esos 11: 9 ya fallaban igual en el repo de Jordi sin ningún cambio mío (`test_final_audit.py`, necesitan los CSV reales); los otros 2 (`test_gdelt_data.test_main_runs_attention_after_financial_output_without_gdelt` y `test_final_audit.test_incomplete_frozen_period_stops_before_writing`) son consecuencia directa y esperada de dejar las tres fechas en `None` — el propio `main.py` exige correr `python -m src.history_period` antes, que es justo el comportamiento de seguridad buscado.
- **Pendiente, requiere conexión real a internet** (este entorno no tiene acceso a Yahoo Finance/Wikimedia/GDELT): correr `python -m src.history_period` y luego `python main.py` para generar los datos reales de NVDA. Después de eso, `src/audit_final.py` y `docs/auditoria_final.md` quedan pendientes de rehacer para NVDA (ver punto anterior).
