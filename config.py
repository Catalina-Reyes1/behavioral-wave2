ASSET = "NVDA"
MARKET = "VOO"
# Estas tres fechas eran las resueltas para TSLA (python -m src.history_period).
# NVDA tiene disponibilidad de datos distinta a TSLA (cotiza desde antes y su
# artículo de Wikipedia existe desde antes): se dejan en None a propósito para
# que main.py exija correr `python -m src.history_period` de nuevo y no se
# reutilicen por error fechas calculadas para otra empresa.
START_DATE = "2015-08-31"
ATTENTION_START_DATE = "2015-07-01"
MARKET_DOWNLOAD_START = "2015-08-28"
# Último día inclusivo del estudio principal congelado para la entrega (no depende del activo).
END_DATE = "2026-09-08"
TRAIN_RATIO = 0.70
TRANSACTION_COST = 0.001  # 0.10% por operación, provisional
