"""Seeded uncertainty and multiple-testing helpers."""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np


def percentile_bootstrap_ci(
    values: Sequence[float],
    *,
    resamples: int = 5000,
    seed: int = 0,
    confidence: float = 0.95,
) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return 0.0, 0.0
    if array.size == 1:
        return float(array[0]), float(array[0])
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, array.size, size=(resamples, array.size))
    estimates = np.mean(array[indices], axis=1)
    alpha = (1.0 - confidence) / 2.0
    lower, upper = np.quantile(estimates, [alpha, 1.0 - alpha])
    return float(lower), float(upper)


def paired_bootstrap_ci(
    left: Sequence[float],
    right: Sequence[float],
    *,
    resamples: int = 5000,
    seed: int = 0,
    confidence: float = 0.95,
) -> tuple[float, float]:
    if len(left) != len(right):
        raise ValueError("paired bootstrap inputs must have equal length")
    differences = np.asarray(left, dtype=float) - np.asarray(right, dtype=float)
    return percentile_bootstrap_ci(
        differences,
        resamples=resamples,
        seed=seed,
        confidence=confidence,
    )


def paired_sign_randomization_pvalue(
    differences: Sequence[float],
    *,
    draws: int = 10000,
    seed: int = 0,
) -> float:
    array = np.asarray(differences, dtype=float)
    nonzero = array[array != 0.0]
    if nonzero.size == 0:
        return 1.0
    observed = abs(float(np.mean(nonzero)))
    rng = np.random.default_rng(seed)
    extreme = 0
    batch = 2048
    completed = 0
    while completed < draws:
        size = min(batch, draws - completed)
        signs = rng.choice(np.array([-1.0, 1.0]), size=(size, nonzero.size))
        statistics = np.abs(np.mean(signs * nonzero, axis=1))
        extreme += int(np.sum(statistics >= observed - 1e-15))
        completed += size
    return (extreme + 1.0) / (draws + 1.0)


def holm_correction(pvalues: Sequence[float]) -> list[float]:
    count = len(pvalues)
    order = sorted(range(count), key=lambda index: (pvalues[index], index))
    adjusted = [0.0] * count
    running = 0.0
    for rank, index in enumerate(order):
        candidate = min(1.0, (count - rank) * float(pvalues[index]))
        running = max(running, candidate)
        adjusted[index] = running
    return adjusted


def wins_ties_losses(differences: Iterable[float], *, tolerance: float = 1e-12) -> tuple[int, int, int]:
    wins = ties = losses = 0
    for value in differences:
        if value > tolerance:
            wins += 1
        elif value < -tolerance:
            losses += 1
        else:
            ties += 1
    return wins, ties, losses
