# Trabajo de Aplicación II · Behavioral Finance (UFT)

Equipo: González, Reyes, Tapia, Guerra · Prof. Aliro Sanhueza · Entrega: 20/11/2026

## Qué abrir

- **En línea:** https://catalina-reyes1.github.io/behavioral-wave2/cliente.html
- **Sin internet:** descomprimir el .zip, abrir `app/index.html` (el HTML de la Evaluación 1) y entrar a **«Para el cliente →»** en el menú. También se puede abrir `app/cliente.html` directamente. Los archivos de `app/` deben quedar juntos.
- Repositorio: https://github.com/Catalina-Reyes1/behavioral-wave2

## Qué hay en el .zip

| Archivo | Qué es |
|---|---|
| `app/index.html`, `app/app.js`, `app/style.css` | HTML de la Evaluación 1 (solo se agregó el link «Para el cliente →» al menú). |
| `app/cliente.html`, `app/cliente.js` | Hoja nueva del Trabajo II. |
| `app/data/cliente.js` | Cifras de la hoja nueva, generadas por `src/oos_cliente.py`. |
| `app/data/series.json`, `events.json`, `overview.json`, `snapshot.js` | Datos de la Evaluación 1 (precios de NVDA, IOC, señales y operaciones). |
| `app/vendor/` | Librería de gráficos (Plotly), local. |
| `src/oos_cliente.py` | Código que calcula R²oos, MDA, Anatolyev y Gerko, Clark y West y el backtest. |
| `.github/workflows/trabajo2-cliente.yml` | Workflow que descarga ^IRX y VOO y vuelve a correr el código. |
| `data/trabajo2/irx_voo.csv` | Tasa de letras del Tesoro de EE.UU. a 13 semanas (^IRX) y precio de VOO usados. |

Para reproducir: `pip install -r requirements.txt` y `python -m src.oos_cliente` (usa el CSV incluido) o `python -m src.oos_cliente --descargar` (vuelve a bajar ^IRX y VOO).

## Diseño fuera de muestra

- Activo NVDA; referencia de mercado VOO. Horizonte: 5 sesiones.
- Train: 31/08/2015 a 12/05/2023 (se fijaron las reglas y el umbral IOC de 65,39). Test: 15/05/2023 a 08/09/2026 (832 sesiones, 30 señales: 14 de compra y 16 de venta).
- Ventana recursiva: cada pronóstico usa solo información conocida al cierre del día de la señal.
- Corrección respecto de la Evaluación 1: la señal del día t usa las visitas de Wikipedia del día t (horario UTC), que se completan después del cierre. Por eso se entra al cierre de t+1: retorno = P(t+6)/P(t+1) − 1.
- Costos: 0,10% por lado (también para comprar y mantener). La caja rinde ^IRX; Sharpe en exceso de esa tasa.

## Cifras vigentes (Test)

| Prueba | Resultado | ¿Aprueba? |
|---|---|---|
| R²oos = 1 − ECM indicador / ECM media histórica | +5,1% en las 30 señales (Clark y West p = 0,038); −0,12% en las 826 sesiones | A medias |
| MDA = aciertos / señales | 63,3% (19/30). Binomial vs 50%: p = 0,100. Alzas en las mismas ventanas: 70,0%. Alzas en todas las ventanas de 5 sesiones de Test: 58,5% | No |
| Anatolyev y Gerko, una cola | EP = 0,29; p = 0,384 | No |

| Desempeño (15/05/2023 a 08/09/2026) | Comprar y mantener NVDA | Estrategia IOC | IOC solo compras | Ref. VOO |
|---|---|---|---|---|
| Retorno total | +697,4% | −21,7% | +27,6% | +94,2% |
| Retorno anualizado | +87,5% | −7,2% | +7,7% | +22,3% |
| Volatilidad | 48,3% | 19,2% | 11,1% | 14,6% |
| Sharpe (en exceso de ^IRX) | 1,45 | −0,51 | 0,32 | 1,15 |
| Máxima caída | −36,9% | −47,1% | −15,3% | −18,7% |
| Tiempo invertido | 100,0% | 9,0% | 4,8% | 100,0% |
| Operaciones | 1 | 15 | 8 | 1 |

**Veredicto: ¿Aprueba? No.** No se recomienda como estrategia. La señal de compra (+1) merece seguimiento: +1,89% por operación en Train y +5,00% en Test.

## Nota sobre el README

`README.md` es de la Evaluación 1 y conserva cifras de una versión anterior (período desde 2017). Las cifras vigentes del sitio son las de la página web (período 2015–2026, 2.771 sesiones, 93 eventos) y las de este archivo.
