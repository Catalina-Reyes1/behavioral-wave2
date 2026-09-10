# Auditoría final de Behavioral Wave

Fecha de revisión: 09/09/2026. Estudio principal: **03/04/2017–08/09/2026**. Esta auditoría verifica la entrega existente; no selecciona ni optimiza el período o las reglas.

## Dictamen y alcance

**Integridad numérica aprobada sobre los archivos congelados.** Se contrastaron la serie diaria de atención completa, las 2.371 sesiones financieras y las 70 operaciones. Los resultados financieros no se reescribieron. La incidencia de noviembre de 2021 corresponde a la presentación del gráfico, no a señales opuestas en una observación.

**Cierre visual pendiente:** no hubo un navegador integrado disponible (`agent.browsers.list()` devolvió `[]`). Se validaron sintaxis, datos, enlaces y controles mediante ejecución JavaScript con DOM y Plotly simulados, pero no se realizaron capturas ni pruebas reales de hover o renderizado en escritorio/móvil. No se declara una inspección visual que no se hizo.

La evidencia completa está en [audit_calculations.json](audit_calculations.json), los hashes de entrada en [audit_input_hashes.json](audit_input_hashes.json) y los dos escenarios web en [audit_web_checks.json](audit_web_checks.json). El verificador independiente es [src/audit_final.py](../src/audit_final.py). Usa sumas escalares, `math`, `statistics` y la distribución t; no llama al pipeline para producir los valores auditados. Solo invoca funciones productivas en copias para probar perturbaciones de Test.

## A. Integridad y diagnóstico del tooltip

| Comprobación | Resultado |
|---|---|
| Date única, válida y ordenada en los CSV principales | Aprobada; sin duplicados |
| Calendario de señales y CAPM frente a Market Model | Igualdad exacta de fechas y Sample |
| Sample cronológico | 1.659 Train / 712 Test; Test comienza 2023-11-03 |
| Signal | Solo −1, 0, +1; ninguna observación satisface ambas direcciones |
| Trade_Signal | Solo −1, 0, +1 en las filas con dato; una excepción inicial NaN |
| Señales → entrada | Coinciden con `Signal.shift(1)` sobre sesiones de mercado |
| Datos de atención y financieros unidos | Valores iguales a los archivos fuente en cada fecha |
| CSV → events.json → series.json → snapshot.js | Coinciden con la exportación determinista; sin eventos añadidos ni omitidos |

**Excepción explícita del dominio:** el primer `Trade_Signal` es NaN porque no existe una observación previa para `shift(1)`. Por tanto, no es correcto afirmar que todas las celdas del CSV sean −1/0/+1 sin esa salvedad. Es ausencia de orden, no una señal inválida; no se rellenó ni se cambió la metodología. Desde la segunda fila todas las celdas cumplen el dominio solicitado.

Registros reales alrededor del tooltip (los números se muestran con diez decimales; los archivos conservan mayor precisión):

| Date | Sample | IOC | CAR_Z | Signal | Trade_Signal |
| --- | --- | --- | --- | --- | --- |
| 2021-10-27 | Train | 97.3781872779 | 2.3149811286 | -1 | 0.0000000000 |
| 2021-10-28 | Train | 91.2932940943 | 2.2408640726 | -1 | -1.0000000000 |
| 2021-10-29 | Train | 80.0469882601 | 2.4059817582 | -1 | -1.0000000000 |
| 2021-11-01 | Train | 84.0434167201 | 1.9209817828 | 0 | -1.0000000000 |
| 2021-11-02 | Train | 86.7718562620 | 1.5510667323 | 0 | 0.0000000000 |
| 2021-11-03 | Train | 66.3883832479 | 1.5676255779 | -1 | 0.0000000000 |
| 2021-11-04 | Train | 54.1146690571 | 1.3459669572 | 0 | -1.0000000000 |
| 2021-11-05 | Train | 32.4686469070 | 0.7835122265 | 0 | 0.0000000000 |
| 2021-11-08 | Train | 97.7860990978 | -0.9396772577 | 0 | 0.0000000000 |
| 2021-11-09 | Train | 71.5676210210 | -1.9671546872 | 1 | 0.0000000000 |
| 2021-11-10 | Train | 60.1109947022 | -1.5939740656 | 1 | 1.0000000000 |
| 2021-11-11 | Train | 65.7869628308 | -1.7366639886 | 0 | 1.0000000000 |
| 2021-11-12 | Train | 33.8679846332 | -2.1011162472 | 0 | 0.0000000000 |


Los valores reportados identifican de forma inequívoca estos registros:

- **03/11/2021:** Signal −1, IOC 66,3883832479 y CAR_Z +1,5676255779; su entrada Trade_Signal −1 es **04/11/2021**.
- **09/11/2021:** Signal +1, IOC 71,5676210210 y CAR_Z −1,9671546872; su entrada Trade_Signal +1 es **10/11/2021**.
- **05/11/2021:** IOC diario 32,4686469070; **Signal = 0 y Trade_Signal = 0**. No hay evento en esa fecha.

**Causa identificada:** `app.js` utilizaba `hovermode: "x unified"` sobre cuatro trazas, incluidas dos trazas dispersas de eventos +1/−1. Ese modo puede reunir puntos próximos de trazas distintas dentro de su distancia de hover; la etiqueta de eventos no mostraba su propia fecha. Así, dos eventos cercanos podían aparecer junto a la lectura diaria bajo una referencia temporal común. La correspondencia exacta de los números con 03/11 y 09/11, la consistencia de los archivos y esa configuración ubican el problema en la presentación. No hubo error de `signals.py` ni duplicación en la exportación. El comportamiento del modo está descrito en la [referencia oficial de Plotly](https://plotly.com/javascript/reference/layout/#layout-hovermode). El diagnóstico es de datos y código; no se reprodujo el gesto original físicamente por la limitación de navegador indicada.

**Corrección:** `hovermode: "closest"`, distancia de hover 12 y tooltip individual con fecha del evento, precio TSLA, IOC, tipo de Signal, CAR_Z, Sample y fecha/Trade_Signal de entrada t+1. La exportación incorpora `TSLA_Price`, `Entry_Date` y `Entry_Trade_Signal` tomados de los CSV y del siguiente día de mercado. Las líneas de precio e IOC también muestran su fecha propia. **Se conservan los 70 marcadores reales**. La columna de la tabla `Trade_Signal en t` no debe confundirse con la entrada del evento mostrado: puede reflejar una señal anterior.

## B. Auditoría independiente del IOC

Se recalcularon las **3506 observaciones diarias** desde Pageviews crudos. La ventana contiene exactamente los 60 días calendario de t−60 a t−1, nunca t. Se utiliza desviación muestral `ddof=1`, no 60 sesiones bursátiles. Los primeros 60 días de calentamiento permanecen sin IOC; no se imputan. Las fechas de Pageviews son consecutivas y sus conteos coinciden con el CSV procesado.

`L = log(1 + Pageviews)`; `Z = (L − media_60) / sigma_60`; `IAA = max(Z, 0)`; `IOC = 100 × tanh(IAA / 2)`.

Selección y referencia histórica:

| Caso | Fecha | Pageviews | Inicio referencia | Fin referencia |
| --- | --- | --- | --- | --- |
| Normal | 2017-04-19 | 7233 | 2017-02-18 | 2017-04-18 |
| Extremo | 2017-04-04 | 17168 | 2017-02-03 | 2017-04-03 |
| Máximo | 2017-11-17 | 29940 | 2017-09-18 | 2017-11-16 |
| Evento | 2017-07-05 | 9571 | 2017-05-06 | 2017-07-04 |
| Cerca del tooltip | 2021-11-05 | 11278 | 2021-09-06 | 2021-11-04 |


Cálculo escalar independiente y comparación:

| Fecha | log(1 + PV) | Media 60 | Sigma 60 | Attention_Z | IAA | IOC calculado | IOC guardado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2017-04-19 | 8.8865474125 | 8.8723617005 | 0.2302916227 | 0.0615989059 | 0.0615989059 | 3.0789717773 | 3.0789717773 |
| 2017-04-04 | 9.7508607111 | 8.6540804551 | 0.5200243174 | 2.1090941699 | 2.1090941699 | 78.3567893635 | 78.3567893635 |
| 2017-11-17 | 10.3069840575 | 8.8988639813 | 0.1187618814 | 11.8566669659 | 11.8566669659 | 99.9985817856 | 99.9985817856 |
| 2017-07-05 | 9.1665974490 | 8.8173729726 | 0.1387625799 | 2.5167049830 | 2.5167049830 | 85.0609270918 | 85.0609270918 |
| 2021-11-05 | 9.3306978686 | 9.1385449990 | 0.2851973670 | 0.6737540100 | 0.6737540100 | 32.4686469070 | 32.4686469070 |


Tolerancia absoluta: **1e−9**, sin tolerancia relativa. Error máximo IOC en toda la serie: **2.981295e-10**; error máximo Attention_Z: **4.573408e-11**. También coinciden velocidad y aceleración; el mayor error de las columnas auditadas es **5.945822e-10**. Estas diferencias son de redondeo numérico, no cambios de fórmula.

**El día actual no entra en su propia referencia.** Al reemplazar todos los Pageviews posteriores al 05/11/2021 por 99.999.999, ningún indicador hasta esa fecha cambia.

## C. Auditoría de señales

Umbrales recalculados independientemente con cuantiles lineales **solo sobre las filas Train**, excluyendo NaN por variable:

- `IOC_Extreme_Threshold` = **68.299931564994**.
- `CAR_Positive_Threshold` = **1.123153860369**.
- `CAR_Negative_Threshold` = **-1.117096633370**.

Para cada fila se verificaron las cuatro banderas, agotamiento y dirección. El IOC previo se toma de la sesión de mercado anterior después de la unión, mientras que el IOC y su velocidad diaria provienen de la serie calendario. Las condiciones direccionales no se superponen porque el umbral negativo es estrictamente menor que el positivo.

Cuatro casos manuales, dos por dirección:

| Date | IOC_Prev | IOC | CAR_Z | Signal | Entry_Date | Trade_Signal |
| --- | --- | --- | --- | --- | --- | --- |
| 2021-10-29 | 91.2932940943 | 80.0469882601 | 2.4059817582 | -1 | 2021-11-01 | -1 |
| 2021-11-03 | 86.7718562620 | 66.3883832479 | 1.5676255779 | -1 | 2021-11-04 | -1 |
| 2021-11-09 | 97.7860990978 | 71.5676210210 | -1.9671546872 | 1 | 2021-11-10 | 1 |
| 2021-11-10 | 71.5676210210 | 60.1109947022 | -1.5939740656 | 1 | 2021-11-11 | 1 |


En los cuatro casos, `IOC_Prev >= IOC_Extreme_Threshold` y `IOC < IOC_Prev`. En las dos señales −1, CAR_Z excede el percentil 90; en las dos +1, cae por debajo del percentil 10. Cada entrada aparece exactamente en la siguiente sesión. El segundo +1 del 10/11 es un evento independiente aunque ya entre una señal anterior; no se fusionó ni se eliminó.

Total: **70 eventos**, **53 Train**, **17 Test**, **42 señales +1** y **28 señales −1**. No se cambiaron percentiles ni reglas después de ver resultados.

## D. Auditoría AR/CAR y CAPM

El ajuste independiente usa la identidad escalar de MCO: beta = suma de productos centrados / suma de cuadrados centrados; alpha = media(TSLA) − beta × media(VOO). La desviación se obtiene de los residuos **Train** con divisor n−1, conforme al código congelado; no se sustituyó por el error estándar de regresión con divisor n−2.

- Alpha Market Model: **0.001484849404161**.
- Beta Market Model: **1.482177571805223**.
- Sigma epsilon Train: **0.034251223589449**.
- Alpha CAPM: **0.001517449981021**.
- Beta CAPM: **1.482622983002636**.
- Sigma epsilon CAPM Train: **0.034250181643281**.

En las 2.371 sesiones se reconstruyeron `Expected_Return = alpha + beta × VOO_Return`, `AR = TSLA_Return − Expected_Return`, suma de los cinco AR hasta t y `CAR_Z = CAR_5 / (sigma × sqrt(5))`. Se conservan los cuatro NaN iniciales de CAR. El CAR puede cruzar el corte Train/Test porque usa únicamente retornos ya observados.

| Date | VOO_Return | TSLA_Return | Expected_Return | AR | CAR_5 | CAR_Z |
| --- | --- | --- | --- | --- | --- | --- |
| 2017-04-07 | -0.0008792811 | 0.0128556380 | 0.0001815987 | 0.0126740393 | 0.0823386750 | 1.0750849476 |
| 2021-11-03 | 0.0060277682 | 0.0357167380 | 0.0104190723 | 0.0252976657 | 0.1200614085 | 1.5676255779 |
| 2021-11-05 | 0.0034012198 | -0.0063581699 | 0.0065260611 | -0.0128842310 | 0.0600076848 | 0.7835122265 |
| 2021-11-09 | -0.0035013745 | -0.1199030325 | -0.0037048094 | -0.1161982232 | -0.1506605696 | -1.9671546872 |
| 2023-11-03 | 0.0092476610 | 0.0066359079 | 0.0151915251 | -0.0085556171 | -0.0296137930 | -0.3866632916 |


Error máximo Market Model en estas identidades y toda la muestra: **1.121325e-14**. Para CAPM se reconstruyó RF desde la última observación de IRX cuya fecha no excediera cada sesión; se verificó también `RF_Observation_Date`. No hay backward fill. Coinciden las tasas, parámetros congelados, retornos esperados y AR de CAPM.

**Prueba de aislamiento:** se sustituyeron los retornos TSLA/VOO de Test por 100/−50, CAR_Z por 10.000, IOC por 100 y las tasas IRX posteriores al corte por 500. Los parámetros y todas las filas Train de Market Model/CAPM permanecieron idénticos; tampoco cambiaron los tres umbrales ni las señales Train. Las perturbaciones fueron en memoria, sin guardar CSV.

## E. Auditoría independiente del backtest

Se reconstruyeron las **70 operaciones**, no solamente los ejemplos. Todas tienen cinco sesiones completas y ninguna cruza el corte en esta muestra. `Date` en backtest es la entrada; `Signal_Date` identifica el evento anterior. `IOC` y `CAR_Z` de esa tabla son de entrada, mientras `Signal_IOC` y `Signal_CAR_Z` conservan los del evento. Ambas parejas fueron contrastadas contra señales.

`Forward_Return_5D = producto(1 + r_i) − 1`, incluyendo las filas entrada…entrada+4. No se vuelve a desplazar Trade_Signal. `Gross = dirección × Forward`; `Net = Gross − 0.002`.

| Date | Exit_Date | Sample | Trade_Signal | Forward_Return_5D | Strategy_Gross_Return | Transaction_Cost | Strategy_Net_Return |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2017-07-06 | 2017-07-12 | Train | 1.0000000000 | 0.0074291781 | 0.0074291781 | 0.0020000000 | 0.0054291781 |
| 2018-08-06 | 2018-08-10 | Train | -1.0000000000 | 0.0210242507 | -0.0210242507 | 0.0020000000 | -0.0230242507 |
| 2024-01-18 | 2024-01-24 | Test | 1.0000000000 | -0.0358153612 | -0.0358153612 | 0.0020000000 | -0.0378153612 |


Los cinco retornos diarios empleados, expresados como fracciones:

- **2017-07-06 → 2017-07-12**, dirección +1: -0.055825591745, +0.014214882526, +0.009035213547, +0.035342527955, +0.007028925342.
- **2018-08-06 → 2018-08-10**, dirección -1: -0.017749896606, +0.109886235877, -0.024316999264, -0.048306898446, +0.008625279558.
- **2024-01-18 → 2024-01-24**, dirección +1: -0.017026203280, +0.001463080760, -0.015976244642, +0.001628334928, -0.006263735117.

La operación corta del ejemplo pierde porque TSLA sube: +2,102425% del activo se transforma en −2,102425% bruto y −2,302425% neto. El signo sería favorable al corto cuando el retorno del activo fuera negativo. La operación Test del ejemplo también pierde; no se omitieron resultados negativos.

Los retornos normales se componen durante esas mismas cinco sesiones. `Abnormal_Strategy = Strategy_Net_Return − dirección × Normal_5D`, es decir, **anormal después de costos** y con dirección aplicada también al retorno normal:

| Date | MarketModel_Normal_5D | CAPM_Normal_5D | Abnormal_Strategy_MarketModel | Abnormal_Strategy_CAPM |
| --- | --- | --- | --- | --- |
| 2017-07-06 | 0.0149482315 | 0.0150168404 | -0.0095190534 | -0.0095876623 |
| 2018-08-06 | 0.0043339958 | 0.0043046338 | -0.0186902549 | -0.0187196169 |
| 2024-01-18 | 0.0485700279 | 0.0482343340 | -0.0863853891 | -0.0860496952 |


También se verificaron todos los campos del resumen Train/Test/Total: operaciones, porcentaje ganador neto, media bruta/neta, mediana neta, desviación muestral, compuesto de eventos y medias anormales. El t bilateral Test se calculó como `media / (s / sqrt(n))`, con **16 grados de libertad**, y `p = 2 × cola_t(abs(t))`:

| Métrica Test | t-statistic | p-value bilateral |
| --- | --- | --- |
| Net | 0.9775049161 | 0.3428686008 |
| MarketModel | 0.2629861345 | 0.7959177323 |
| CAPM | 0.2654446581 | 0.7940566676 |


Los retornos futuros solo entran en esta evaluación y en el retorno normal ex post condicionado al mercado; no alimentan señales ni parámetros. No son predicciones conocidas al entrar. Los eventos solapados permanecen independientes como registros, pero no se presume independencia estadística: el t-test reportado es nominal y su inferencia está limitada por ese solapamiento. El compuesto de eventos no es rentabilidad de una cartera con capital y exposición definidos.

**Limitación de ejecución:** el retorno de la fila t+1 mide cierre(t) → cierre(t+1). El desplazamiento evita usar el retorno evaluado para formar Signal, pero no prueba que se pudiera entrar al cierre(t) con las visitas completas del día ya publicadas. Falta validar cortes UTC, disponibilidad histórica de Pageviews y demora de publicación, y modelar precios realmente ejecutables. Esta limitación de implementabilidad se declara; no se cambiaron entradas ni reglas para corregirla en esta entrega. Tampoco se incluyen costos de préstamo de acciones para cortos, margen o una simulación de cartera.

## F–M. Web y discusión académica

La página utiliza los CSV exportados para todos sus KPI, tablas y trazas; no escribe resultados financieros nuevos en HTML/JavaScript. Se añadieron:

- Explicación de IOC como construcción del proyecto y de tanh como escala, con ejemplo conceptual 20 → 45 → 72 → 91 → 80. Intensidad no equivale a sentimiento, optimismo, pesimismo ni causalidad.
- Justificación de Wikimedia como proxy público, diario, histórico y reproducible. No se afirma que todos los visitantes inviertan ni que las visitas sean personas únicas. [Documentación de Wikimedia](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html).
- GDELT como extensión futura tras HTTP 429; sin noticias, sentimiento o propagación inventados.
- Bloque de selectividad: 2.371 sesiones, 70 eventos, 53 Train y 17 Test. Los eventos no son el tamaño de la muestra financiera.
- Sección **Valor económico**, accesible desde el menú: alerta complementaria para minoristas y posible variable de investigación institucional. Utilidad potencial, sin rentabilidad demostrada ni recomendación automática.
- Discusión de eficiencia de mercado: no hay evidencia suficiente de retornos anormales sistemáticos después de costos frente a los modelos utilizados. El contraste depende del modelo de retorno normal; no rechazar no demuestra eficiencia perfecta.
- Conclusión principal con **17 Test**, **52,94%** ganadoras, neto medio **+1,684%**, **p = 0,342869**; Market Model **+0,460%**, p **0,795918**, y CAPM **+0,464%**, p **0,794057**. No significativos al 5%.

El fundamento de atención limitada se conecta con [Barber y Odean (2008)](https://academic.oup.com/rfs/article-abstract/21/2/785/1607197), sin presentar el IOC como un indicador validado por ese artículo. El proyecto no mide directamente rebaño, creencias o causalidad.

### Robustez archivada, sin reestimar

| Período | Sesiones | Eventos | Operaciones Test | Neto medio Test | p-value |
|---|---:|---:|---:|---:|---:|
| Principal 2017–2026 | 2371 | 70 | 17 | +1,68% | 0,3429 |
| Reciente 2019–2026 | 1931 | 58 | 11 | +2.54% | 0.0534 |

La segunda fila se lee exclusivamente de `results/pre_expansion/`. Tiene una estimación mayor y menos eventos, pero tampoco alcanza significancia al 5%. No se reemplaza el análisis principal ni se elige 2019 por los resultados. Hay solapamiento y distintos cortes de estimación: no es una validación independiente ni una prueba de estabilidad con parámetros comunes. Una mayor relevancia en una era de atención digital es solo una hipótesis futura, no una conclusión comprobada.

## N. Manual y reproducibilidad

Se reescribió [README.md](../README.md) para el grupo: problema, teoría, indicadores, señales, evaluación, resultados, carpetas, límites, comandos y [URL pública](https://jgonzalezg13-ai.github.io/behavioral-wave/). No se publicó esta auditoría: no hubo commit ni push.

Para reproducir comprobaciones sin descargar ni cambiar los resultados:

```powershell
python -m unittest discover -s tests -v
python -m src.audit_final
```

Para exportar nuevamente los mismos resultados guardados:

```powershell
python -m src.export_web_data
```

La ejecución real de `main.py` no se repitió en esta auditoría para no sobrescribir los resultados congelados con revisiones de proveedores. Su integración se probó con fuentes simuladas. Se corrigió un test antiguo que no simulaba las descargas/descubrimiento añadidos durante la ampliación histórica.

## P. Validación final y correcciones

**52 pruebas Python aprobadas**: 40 existentes y 12 nuevas en `tests/test_final_audit.py`. Cobertura nueva: fechas únicas, dominio y exclusión mutua, t+1, cinco IOC independientes, AR/CAR/CAPM, todas las operaciones y resumen, perturbaciones Test, CSV/JSON/snapshot, coherencia de entradas del tooltip, ausencia de evento el 05/11, hashes, textos web y conservación del período ante fuentes incompletas. Las pruebas de error HTTP/timeout usan respuestas simuladas, no fallos reales de descarga en esta auditoría.

**Dos escenarios JavaScript aprobados**, HTTP y apertura local con snapshot: carga de datos, KPI, tabla de robustez, diez eventos recientes, 70 marcadores, etiquetas/entradas de noviembre, filtro Test, fechas personalizadas, visibilidad y menú. `tests/web_ui_check.mjs` simula DOM/Plotly; sus resultados no son evidencia de renderizado real.

| Hallazgo | Corrección / estado |
|---|---|
| Tooltip unificado con eventos de fechas distintas sin fecha propia | Hover individual y campos explícitos; sin eliminar eventos |
| Falta de contexto académico y comparación archivada en la web | Bloques IOC, Wikimedia, selectividad, valor, eficiencia y robustez; KPI derivados de datos |
| README describía etapas ya terminadas como futuras | Manual actualizado y límites explícitos |
| `END_DATE = None` permitía cambiar el período al ejecutar después | Corte inclusivo 2026-09-08 centralizado; Yahoo recibe end exclusivo 2026-09-09 |
| Una fuente podría acortar silenciosamente el corte congelado | `main.py` se detiene antes de guardar si el extremo común no coincide |
| Test de integración antiguo no aislaba las nuevas fuentes | Mocks completos, sin descarga ni escritura de datos reales |
| Primer Trade_Signal NaN | Conservado y documentado; no existe sesión previa ni orden |
| Resultados no significativos y ejecución aproximada | Limitaciones declaradas; ninguna optimización o modificación de reglas |
| Navegador integrado no disponible | Pendiente inspección visual real, incluidas fechas 03/11, 05/11 y 09/11/2021 y vista móvil |

### Conservación de resultados y cambios concretos

El manifiesto previo confirma SHA-256 idéntico para **25 archivos**: todos los CSV financieros/de atención y archivos históricos incluidos, los cinco módulos `abnormal_returns.py`, `wikimedia_attention.py`, `signals.py`, `capm_model.py`, `backtest.py`, y `.github/workflows/static.yml`. La excepción declarada del manifiesto es `config.py`, exclusivamente para fijar el corte final que pidió el usuario. `main.py` adapta inclusividad y valida cobertura; no modifica cálculos.

Archivos modificados o añadidos en esta auditoría:

- `config.py`, `main.py`: protección del período congelado.
- `src/export_web_data.py`: contexto de cada evento y lectura de robustez archivada.
- `src/audit_final.py`: verificación independiente de solo lectura sobre resultados.
- `app/index.html`, `app/style.css`, `app/app.js`: contenido académico, estilos y tooltip.
- `app/data/overview.json`, `app/data/events.json`, `app/data/snapshot.js`: regenerados desde CSV. `series.json` se reexportó con contenido idéntico.
- `tests/test_gdelt_data.py`, `tests/test_final_audit.py`, `tests/web_ui_check.mjs`: integración y regresiones.
- `README.md`, `docs/bitacora.md`, este informe y tres evidencias JSON de auditoría.

**Reglas congeladas confirmadas:** IOC y tanh; ventana previa de 60 días; shift(1); IAA positiva; percentiles 90/90/10; Wave_Exhaustion; señales ±1; entrada t+1; cinco sesiones; costo total 0,20%; Train/Test cronológico 70/30; Market Model y CAPM. Se mantuvo el período principal solicitado. No se tocó el workflow, no hubo commit ni push.

La confirmación de integridad es numérica y de trazabilidad, no una certificación de rentabilidad o ejecución. Antes de entregar queda una revisión visual humana en navegador. La baja potencia, los solapamientos, un único activo/proxy, revisiones de proveedores y disponibilidad temporal para ejecutar permanecen limitaciones académicas reales; no se resuelven escogiendo otro período o afinando reglas.

## O. Auditoría contra la pauta del profesor

| CRITERIO PROFESOR | ESTADO | DÓNDE SE CUMPLE |
|---|---|---|
| 1. Fundamento conductual | Cumplido como hipótesis; causalidad no probada | README, web La ola/IOC, referencia de atención limitada y este informe F–M |
| 2. Serie de tiempo / HTML | Implementado y validado en datos/ejecución simulada; falta inspección visual real | CSV diarios, app/data, gráfico de app/index.html, tests/web_ui_check.mjs |
| 3. Evaluación fuera de muestra | Cumplida técnicamente; potencia limitada a 17 Test | Corte 2023-11-03, parámetros congelados, pruebas de perturbación y backtest_summary.csv |
| 4. Al menos dos modelos de retorno normal | Cumplido | Market Model y CAPM; src/abnormal_returns.py, src/capm_model.py; auditoría D/E |
| 5. Costos de transacción | Cumplido para el supuesto 0,20%; préstamo de cortos no incluido | src/backtest.py, CSV de operaciones y limitaciones web/README |
| 6. Discusión de eficiencia de mercado | Cumplido, sin rechazarla con evidencia insuficiente | Web #eficiencia, README y resultados/p-values del informe |
| 7. Valor económico | Cumplido como discusión de utilidad potencial; rentabilidad incremental no demostrada | Web #valor y README |
| 8. Manual de uso | Cumplido | README, web #manual, comandos y URL pública; publicación de estos cambios pendiente por instrucción |
| 9. Discusión honesta de limitaciones | Cumplido | Solapamientos, significancia, proxy, muestra, riesgo de ejecución, costos omitidos y QA visual declarados |
