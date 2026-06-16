from __future__ import annotations

from typing import Any


SUPPORTED_MODEL_PAIRS = {
    ("van_genuchten", "mualem"),
    ("van_genuchten", "burdine"),
    ("van_genuchten", "tabular"),
    ("brooks_corey", "mualem"),
    ("brooks_corey", "burdine"),
    ("brooks_corey", "tabular"),
    ("tabular", "tabular"),
}

RETENTION_MODEL_LABELS = {
    "van_genuchten": "van Genuchten",
    "brooks_corey": "Brooks-Corey",
    "gardner": "Gardner",
    "tabular": "Табличная кривая",
}

CONDUCTIVITY_MODEL_LABELS = {
    "mualem": "Mualem",
    "burdine": "Burdine",
    "corey": "Corey",
    "gardner": "Gardner",
    "tabular": "Табличная кривая",
}


def normalize_model_token(value: Any, default: str) -> str:
    raw = str(value if value not in (None, "") else default).strip().lower()
    return raw.replace("-", "_").replace(" ", "_")


def normalize_grid_dimension(value: Any, grid_plane: Any = None) -> str:
    raw = normalize_model_token(value, "1")
    plane = normalize_model_token(grid_plane, "xz")
    if raw in {"1", "1d", "1d_z", "z"}:
        return "1d_z"
    if raw in {"2", "2d"}:
        return "2d_xy" if plane == "xy" else "2d_xz"
    if raw in {"2d_xy", "xy"}:
        return "2d_xy"
    if raw in {"2d_xz", "xz"}:
        return "2d_xz"
    if raw in {"3", "3d", "3d_xyz", "xyz"}:
        return "3d_xyz"
    raise ValueError(
        "Неизвестная размерность сетки: "
        f"{value}. Допустимо: 1, 2 + grid_plane=XY/XZ, 2d_xy, 2d_xz, 3."
    )


def validate_soil_model_pair(retention_model: str, conductivity_model: str) -> None:
    if retention_model not in RETENTION_MODEL_LABELS:
        raise ValueError(
            "Неизвестная модель водоудерживания: "
            f"{retention_model}. Допустимо: {', '.join(sorted(RETENTION_MODEL_LABELS))}."
        )
    if conductivity_model not in CONDUCTIVITY_MODEL_LABELS:
        raise ValueError(
            "Неизвестная модель влагопроводности: "
            f"{conductivity_model}. Допустимо: {', '.join(sorted(CONDUCTIVITY_MODEL_LABELS))}."
        )
    if (retention_model, conductivity_model) not in SUPPORTED_MODEL_PAIRS:
        readable = ", ".join(
            f"{RETENTION_MODEL_LABELS[r]} + {CONDUCTIVITY_MODEL_LABELS[k]}"
            for r, k in sorted(SUPPORTED_MODEL_PAIRS)
        )
        raise ValueError(
            "Несовместимая или пока не проверенная пара моделей: "
            f"{RETENTION_MODEL_LABELS[retention_model]} + {CONDUCTIVITY_MODEL_LABELS[conductivity_model]}. "
            f"Сейчас разрешены только проверенные пары: {readable}."
        )


def model_pair_label(retention_model: str, conductivity_model: str) -> str:
    return f"{RETENTION_MODEL_LABELS[retention_model]} + {CONDUCTIVITY_MODEL_LABELS[conductivity_model]}"
