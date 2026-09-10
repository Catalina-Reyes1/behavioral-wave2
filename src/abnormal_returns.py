import numpy as np
import pandas as pd


def calculate_abnormal_returns(
    df: pd.DataFrame, train_ratio: float = 0.70
) -> tuple[pd.DataFrame, dict]:
    """Estima el modelo con Train y aplica sus parametros a toda la muestra."""
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio debe estar entre 0 y 1.")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Los datos deben tener un indice de fechas (DatetimeIndex).")

    # Limpiar retornos y ordenar fechas antes de la division cronologica.
    result = df.dropna(subset=["NVDA_Return", "VOO_Return"]).sort_index().copy()
    if result.index.hasnans or result.index.has_duplicates:
        raise ValueError("Las fechas deben ser validas y unicas.")
    if not np.isfinite(result[["NVDA_Return", "VOO_Return"]].to_numpy()).all():
        raise ValueError("Los retornos deben ser finitos.")
    n_train = int(len(result) * train_ratio)
    n_test = len(result) - n_train
    if n_train < 3 or n_test < 1:
        raise ValueError("Se necesitan al menos 3 observaciones Train y 1 Test.")

    train = result.iloc[:n_train]
    x = train["VOO_Return"].to_numpy()
    y = train["NVDA_Return"].to_numpy()
    design = np.column_stack([np.ones(n_train), x])
    if np.linalg.matrix_rank(design) < 2:
        raise ValueError("VOO_Return debe variar en Train para estimar beta.")

    # MCO con intercepto: alpha y beta se estiman una sola vez, solo con Train.
    alpha, beta = np.linalg.lstsq(design, y, rcond=None)[0]
    train_residuals = y - (alpha + beta * x)
    # Volatilidad muestral de los residuos de Train; Test no interviene.
    sigma_epsilon = float(np.std(train_residuals, ddof=1))
    if not np.isfinite(sigma_epsilon) or sigma_epsilon <= 0:
        raise ValueError("Sigma epsilon debe ser positiva para calcular CAR_Z.")

    result["Expected_Return"] = alpha + beta * result["VOO_Return"]
    result["AR"] = result["NVDA_Return"] - result["Expected_Return"]
    # CAR suma cinco retornos anormales consecutivos, incluso en el corte Train/Test.
    result["CAR_5"] = result["AR"].rolling(window=5, min_periods=5).sum()
    result["CAR_Z"] = result["CAR_5"] / (sigma_epsilon * np.sqrt(5))
    result["Sample"] = ["Train"] * n_train + ["Test"] * n_test

    summary = {
        "alpha": float(alpha),
        "beta": float(beta),
        "sigma_epsilon": sigma_epsilon,
        "n_train": n_train,
        "n_test": n_test,
        "test_start": result.index[n_train],
    }
    return result, summary
