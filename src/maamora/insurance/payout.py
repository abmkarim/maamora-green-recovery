"""Fonction de paiement linéaire entre déclencheur et sortie."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt


def payout(index: npt.ArrayLike, trigger: float, exit_: float, sum_insured: float
           ) -> np.ndarray:
    """Paiement d'une couverture sécheresse (indice bas = sinistre).

    0 si indice >= déclencheur, capital total si indice <= sortie, linéaire entre les deux.
    """
    if not trigger > exit_:
        raise ValueError("le déclencheur doit être strictement supérieur à la sortie")
    x = np.asarray(index, dtype=float)
    frac = np.clip((trigger - x) / (trigger - exit_), 0.0, 1.0)
    return sum_insured * frac
