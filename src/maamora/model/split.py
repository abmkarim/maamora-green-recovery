"""Découpes temporelles : entraînement / test et validation interne."""

from __future__ import annotations

from collections.abc import Sequence


def temporal_split(months: Sequence[str], n_train: int, n_test: int
                   ) -> tuple[list[str], list[str]]:
    """Les `n_train` premiers mois en entraînement, les `n_test` derniers en test.

    Lève une erreur si la fenêtre ne contient pas exactement `n_train + n_test` mois.
    """
    ms = sorted(set(months))
    if len(ms) != n_train + n_test:
        raise ValueError(f"{len(ms)} mois disponibles, {n_train} + {n_test} attendus")
    train, test = ms[:n_train], ms[n_train:]
    assert max(train) < min(test)
    return train, test


def inner_split(train_months: Sequence[str], n_val: int) -> tuple[list[str], list[str]]:
    """Validation interne temporelle : les `n_val` derniers mois de l'entraînement."""
    ms = sorted(train_months)
    if not 0 < n_val < len(ms):
        raise ValueError("n_val doit être compris entre 1 et len(train_months) - 1")
    return ms[:-n_val], ms[-n_val:]
