# Behavioral Wave

Proyecto de Finanzas Conductuales.

## Objetivo
Construir un indicador de "onda conductual" para TSLA y evaluar si olas extremas de atención/sentimiento, al comenzar a agotarse, se asocian con reversión de corto plazo.

## Activo y benchmark
- Activo: TSLA
- Mercado: VOO (proxy del S&P 500)
- Tasa libre de riesgo: se incorporará en la fase CAPM

## Flujo
1. Descargar precios TSLA y VOO.
2. Calcular retornos diarios.
3. Incorporar noticias/atención/sentimiento.
4. Construir IOC.
5. Calcular AR y CAR.
6. Generar señales.
7. Backtest 70/30 fuera de muestra.
8. Incluir costos.
9. Exportar resultados al HTML.
