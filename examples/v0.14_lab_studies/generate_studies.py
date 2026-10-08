#!/usr/bin/env python3
"""Generate only invented data and local figures; never build or render decks."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


DISCLOSURE = "Invented synthetic nonclinical illustration; no measured empirical findings."
LIGHT = {"bg": "#FFFFFF", "text": "#171717", "muted": "#666666", "a": "#171717", "b": "#315A74"}
DARK = {"bg": "#000000", "text": "#F2F2F2", "muted": "#B8B8B8", "a": "#67D8E5", "b": "#E0B877"}


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")


def values(array: np.ndarray) -> list:
    return np.round(array, 8).tolist()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def new_plot(*, dark: bool = False, panel: bool = False, strip: bool = False, wide: bool = False,
             label_pt: int = 23):
    colors = DARK if dark else LIGHT
    size = (10.2, 3.4) if wide else (4.6, 3.5) if panel else (7.4, 2.8) if strip else (7.4, 3.6)
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": label_pt,
        "axes.labelsize": label_pt, "xtick.labelsize": label_pt - 2, "ytick.labelsize": label_pt - 2,
        "legend.fontsize": label_pt - 3, "axes.linewidth": 1,
        "text.color": colors["text"], "axes.labelcolor": colors["text"],
        "xtick.color": colors["text"], "ytick.color": colors["text"],
        "axes.edgecolor": colors["muted"], "axes.facecolor": colors["bg"],
        "figure.facecolor": colors["bg"], "savefig.facecolor": colors["bg"],
    })
    fig, ax = plt.subplots(figsize=size, layout="constrained")
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(length=4, pad=5)
    return fig, ax, colors


def png_bytes(fig, *, horizontal_ylabel: bool = False) -> bytes:
    if horizontal_ylabel:
        for ax in fig.axes:
            ax.yaxis.label.set(rotation=0, horizontalalignment="left", verticalalignment="bottom", clip_on=False)
            ax.yaxis.set_label_coords(0, 1.03)
        # Freeze the solved layout before tight cropping measures outside labels.
        fig.canvas.draw()
        fig.set_layout_engine("none")
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=180, bbox_inches="tight", pad_inches=0.035,
                **({"bbox_extra_artists": [artist for ax in fig.axes
                    for artist in (ax.yaxis.label, ax.get_legend()) if artist is not None]} if horizontal_ylabel else {}),
                metadata={"Software": "synthetic_lab_studies", "Description": DISCLOSURE})
    plt.close(fig)
    return buffer.getvalue()


def native_chart(categories, series, axis_title, colors, maximum=None) -> dict:
    options = {
        "catAxisLabelFontSize": 16, "valAxisLabelFontSize": 16,
        "legendFontSize": 16, "dataLabelFormatCode": "0.00",
        "valAxisMinVal": 0, "valAxisTitle": axis_title,
        "showValue": True, "showLegend": len(series) > 1, "chartColors": colors,
    }
    if maximum is not None:
        options["valAxisMaxVal"] = maximum
    return {"type": "bar", "categories": categories, "series": series,
            "options": options, "synthetic": True, "disclosure": DISCLOSURE}


def calibration(config: dict) -> dict[str, bytes]:
    rng = np.random.default_rng(config["seed"])
    train_x = np.repeat(config["training_levels"], config["training_repeats"]).astype(float)
    test_x = np.repeat(config["holdout_levels"], config["holdout_repeats"]).astype(float)
    train_noise = rng.normal(size=len(train_x))
    test_noise = rng.normal(size=len(test_x))

    def response(x, noise, sd):
        return config["offset"] + config["gain"] * x + config["curvature"] * x**2 + sd * noise

    def fit(sd):
        train_y = response(train_x, train_noise, sd)
        test_y = response(test_x, test_noise, sd)
        offset = float(np.mean(train_y - train_x))
        affine = np.polyfit(train_y, train_x, 1)
        quadratic = np.polyfit(train_y, train_x, 2)
        predicted = {
            "Offset": test_y - offset,
            "Affine": np.polyval(affine, test_y),
            "Quadratic": np.polyval(quadratic, test_y),
        }
        candidates = {}
        for name, estimate in predicted.items():
            residual = estimate - test_x
            rmse = float(np.sqrt(np.mean(residual**2)))
            maximum = float(np.max(np.abs(residual)))
            candidates[name] = {
                "prediction": values(estimate), "residual": values(residual),
                "n": len(test_x), "rmse": round(rmse, 8), "max_absolute": round(maximum, 8),
                "passes_toy_screen": bool(rmse <= config["screen_rmse_limit"]
                                          and maximum <= config["screen_max_abs_limit"]),
            }
        return train_y, test_y, candidates, {
            "offset": offset, "affine_descending_powers": values(affine),
            "quadratic_descending_powers": values(quadratic),
        }

    train_y, test_y, candidates, coefficients = fit(config["noise_sd"])
    sweep_sd = [config["noise_sd"] * factor for factor in (1, 2, 4)]
    sweep = [{"noise_sd": sd, "candidates": fit(sd)[2]} for sd in sweep_sd]
    ledger = {
        "schema_version": "calibration_synthetic/v1", "synthetic": True,
        "disclosure": DISCLOSURE, "seed": config["seed"], "units": "AU (arbitrary simulation units)",
        "design": config, "training_input": values(train_x), "training_response": values(train_y),
        "holdout_input": values(test_x), "holdout_response": values(test_y),
        "coefficients": coefficients, "candidates": candidates, "noise_sweep": sweep,
        "sweep_pairing": "Same standard-normal draws, scaled noise SD; one split per setting.",
    }
    result = {"data/synthetic_data.json": json_bytes(ledger)}
    names = list(candidates)
    chart = native_chart(names, [{"name": "Holdout RMSE (AU)",
                                 "values": [round(candidates[n]["rmse"], 3) for n in names]}],
                         "Holdout RMSE (AU)", ["171717"])
    chart["sources"] = ["SYN-C | computed synthetic data"]
    result["data/rmse_chart.json"] = json_bytes(chart)

    fig, ax, color = new_plot(wide=True, label_pt=34)
    ax.scatter(train_x, train_y, s=48, color=color["a"], label="Data")
    ax.plot([0, 100], [0, 100], "--", color=color["b"], lw=2, label="Identity")
    ax.set(xlabel="Input (AU)", ylabel="Response (AU)", xlim=(-3, 103), ylim=(-3, 123))
    ax.set_xticks([0, 50, 100])
    ax.set_yticks([0, 60, 120])
    legend = ax.legend(frameon=False, loc="lower right", bbox_to_anchor=(1, 1.03),
                       ncol=2, handlelength=1, columnspacing=0.8, handletextpad=0.4,
                       borderaxespad=0)
    legend.set_in_layout(False)
    result["assets/response.png"] = png_bytes(fig, horizontal_ylabel=True)

    for name in ("Affine", "Quadratic"):
        fig, ax, color = new_plot(panel=True, label_pt=29)
        ax.scatter(test_x, candidates[name]["residual"], s=40, color=color["a"])
        ax.axhline(0, color=color["muted"], lw=1)
        for limit in (-3, 3):
            ax.axhline(limit, color=color["b"], ls="--", lw=1.5)
        ax.set(xlabel="Input (AU)", ylabel="Residual (AU)", xlim=(0, 100), ylim=(-4, 4))
        ax.set_xticks([0, 50, 100])
        ax.set_yticks([-3, 0, 3])
        result[f"assets/{name.lower()}_residuals.png"] = png_bytes(fig)

    fig, ax, color = new_plot(strip=True, label_pt=28)
    for index, setting in enumerate(sweep):
        residual = setting["candidates"]["Quadratic"]["residual"]
        jitter = np.linspace(-0.09, 0.09, len(residual))
        ax.scatter(index + jitter, residual, s=30, color=color["a"])
    ax.axhline(0, lw=1, color=color["muted"])
    ax.set_xticks([0, 1, 2], [f"{sd:.2f}" for sd in sweep_sd])
    ax.set(xlabel="Noise SD (AU)", ylabel="Residual (AU)", xlim=(-0.5, 2.5))
    result["assets/noise_sensitivity.png"] = png_bytes(fig, horizontal_ylabel=True)
    return result


def contrast(config: dict) -> dict[str, bytes]:
    rng = np.random.default_rng(config["seed"])
    time = np.asarray(config["time_steps"], dtype=float)
    n = config["trace_count"]
    conditions = {}
    for condition in ("dark", "light"):
        drift = config[f"{condition}_drift_per_step"] * time
        offsets = rng.normal(0, 0.008, (n, 1))
        noise = rng.normal(0, config["noise_sd"], (n, len(time)))
        raw = config[f"{condition}_baseline"] + offsets + drift + noise
        corrected = raw - drift
        raw_change = np.abs(raw[:, -1] - raw[:, 0])
        corrected_change = np.abs(corrected[:, -1] - corrected[:, 0])
        conditions[condition] = {
            "raw": values(raw), "oracle_corrected": values(corrected),
            "absolute_endpoint_change_raw": values(raw_change),
            "absolute_endpoint_change_corrected": values(corrected_change),
            "mean_endpoint_change_raw": round(float(raw_change.mean()), 8),
            "mean_endpoint_change_corrected": round(float(corrected_change.mean()), 8),
        }
    ledger = {
        "schema_version": "contrast_synthetic/v1", "synthetic": True, "disclosure": DISCLOSURE,
        "seed": config["seed"], "design": config, "time": values(time),
        "units": "Dimensionless contrast and dimensionless toy time",
        "conditions": conditions,
        "correction_boundary": "Oracle subtracts the known injected drift; no independent estimator exists.",
    }
    result = {"data/synthetic_data.json": json_bytes(ledger)}
    chart = native_chart(["Dark", "Light"], [
        {"name": "Raw", "values": [round(conditions[c]["mean_endpoint_change_raw"], 4) for c in conditions]},
        {"name": "Oracle", "values": [round(conditions[c]["mean_endpoint_change_corrected"], 4) for c in conditions]},
    ], "Absolute endpoint change", ["67D8E5", "E0B877"], maximum=0.3)
    chart["sources"] = ["SYN-D | computed synthetic paired changes"]
    result["data/endpoint_chart.json"] = json_bytes(chart)

    for condition, data in conditions.items():
        fig, ax, color = new_plot(dark=True, panel=True, label_pt=32)
        raw = np.asarray(data["raw"])
        ax.plot(time, raw.T, color=color["a"], lw=0.7, alpha=0.25)
        ax.plot(time, raw.mean(axis=0), color=color["a"], lw=3)
        ax.set(xlabel="Toy time", ylabel="Contrast", ylim=(0, 1), xlim=(0, 60))
        ax.set_xticks([0, 30, 60])
        ax.set_yticks([0, 0.5, 1])
        result[f"assets/{condition}_raw.png"] = png_bytes(fig)

    dark = conditions["dark"]
    fig, ax, color = new_plot(dark=True, wide=True, label_pt=38)
    ax.plot(time, np.mean(dark["raw"], axis=0), color=color["a"], lw=3, label="Raw")
    ax.plot(time, np.mean(dark["oracle_corrected"], axis=0), color=color["b"], lw=3,
            ls="--", label="Oracle")
    ax.axhline(config["dark_baseline"], color=color["muted"], lw=1, ls=":")
    ax.set(xlabel="Toy time", ylabel="Contrast", ylim=(0, 1), xlim=(0, 60))
    ax.set_xticks([0, 30, 60])
    ax.set_yticks([0, 0.5, 1])
    ax.legend(frameon=False, loc="upper left", ncol=2)
    result["assets/oracle_overlay.png"] = png_bytes(fig)

    fig, ax, color = new_plot(dark=True)
    corrected = np.asarray(dark["oracle_corrected"])
    deviations = corrected - corrected[:, :1]
    ax.axhspan(-config["illustrative_tolerance"], config["illustrative_tolerance"],
               color=color["a"], alpha=0.08)
    ax.plot(time, deviations.T, lw=1, color=color["a"], alpha=0.6)
    ax.axhline(0, lw=1, color=color["muted"])
    ax.set(xlabel="Toy time", ylabel="Change", ylim=(-0.1, 0.1), xlim=(0, 60))
    ax.set_xticks([0, 30, 60])
    ax.set_yticks([-0.08, 0, 0.08])
    result["assets/corrected_deviations.png"] = png_bytes(fig)
    return result


def river(config: dict) -> dict[str, bytes]:
    rng = np.random.default_rng(config["seed"])
    time = np.arange(config["time_start"], config["time_end"] + config["time_step"] / 2,
                     config["time_step"])
    centers = rng.normal(config["pulse_centers"], config["center_jitter_sd"],
                         (config["realization_count"], 2))
    traces = np.full((config["realization_count"], len(time)), config["baseline"])
    for pulse, amplitude in enumerate(config["pulse_amplitudes"]):
        traces += amplitude * np.exp(-0.5 * ((time - centers[:, pulse, None]) / config["pulse_width"])**2)
    traces += rng.normal(0, config["noise_sd"], traces.shape)
    dense_peak = traces.max(axis=1) - config["baseline"]
    schedules = {}
    for key in ("schedule_a", "schedule_b"):
        times = np.asarray(config[key])
        indices = np.rint((times - config["time_start"]) / config["time_step"]).astype(int)
        assert np.allclose(time[indices], times), "Sampling times must lie on the dense grid."
        sampled = traces[:, indices]
        fraction = (sampled.max(axis=1) - config["baseline"]) / dense_peak
        schedules[key] = {
            "times": times.tolist(), "samples_per_realization": len(times),
            "values": values(sampled), "peak_fraction": values(fraction),
            "mean_peak_fraction": round(float(fraction.mean()), 8),
        }
    ledger = {
        "schema_version": "river_synthetic/v1", "synthetic": True, "disclosure": DISCLOSURE,
        "seed": config["seed"], "design": config, "time": values(time),
        "units": "AU response and dimensionless toy time", "pulse_centers": values(centers),
        "dense_traces": values(traces), "dense_peak_above_baseline": values(dense_peak),
        "schedules": schedules, "display_realization_index": 0,
        "selection_boundary": "B aligns to authored event centers; not a fair test of unknown timing.",
    }
    result = {"data/synthetic_data.json": json_bytes(ledger)}
    chart = native_chart(["A / phase 0", "B / phase 6"], [{
        "name": "Mean peak fraction",
        "values": [round(schedules[k]["mean_peak_fraction"], 4) for k in schedules],
    }], "Retained peak fraction", ["315A74"], maximum=1)
    chart["sources"] = ["SYN-R | computed synthetic ratios"]
    result["data/retention_chart.json"] = json_bytes(chart)

    for overlay in (False, True):
        fig, ax, color = new_plot()
        ax.plot(time, traces[0], lw=2, color=color["a"], label="Dense")
        if overlay:
            for index, (key, data) in enumerate(schedules.items()):
                ax.plot(data["times"], data["values"][0], lw=1.5, marker="o" if index == 0 else "s",
                        ms=7, color=color["b"] if index == 0 else "#B42318",
                        ls="--" if index == 0 else ":", label="A" if index == 0 else "B")
            ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.02),
                      ncol=3, handlelength=1)
        ax.set(xlabel="Toy time", ylabel="Signal (AU)", ylim=(0, 1.1), xlim=(0, 72))
        ax.set_xticks([0, 24, 48, 72])
        ax.set_yticks([0, 0.5, 1])
        result[f"assets/{'sampling_overlay' if overlay else 'pulse_trace'}.png"] = png_bytes(fig)

    fig, ax, color = new_plot(label_pt=24)
    paired = np.column_stack([schedules[k]["peak_fraction"] for k in schedules])
    ax.plot([0, 1], paired.T, lw=1.2, marker="o", ms=4, color=color["b"], alpha=0.6)
    ax.set_xticks([0, 1], ["A / phase 0", "B / phase 6"])
    ax.set(ylabel="Peak fraction", ylim=(0, 1.05), xlim=(-0.25, 1.25))
    ax.set_yticks([0, 0.5, 1])
    result["assets/paired_retention.png"] = png_bytes(fig)
    return result


def generate() -> dict[str, bytes]:
    config = json.loads((ROOT / "study_config.json").read_text(encoding="utf-8"))
    output = {}
    for folder, function, key in (
        ("white_calibration", calibration, "calibration"),
        ("dark_contrast", contrast, "contrast"),
        ("light_river_report", river, "river"),
    ):
        output.update({f"{folder}/{path}": data for path, data in function(config[key]).items()})
    manifest = {
        "schema_version": "synthetic_figure_manifest/v1", "synthetic": True,
        "disclosure": DISCLOSURE,
        "source_sha256": {path: sha256((ROOT / path).read_bytes())
                          for path in ("generate_studies.py", "study_config.json", "requirements.txt")},
        "runtime": {"numpy": np.__version__, "matplotlib": matplotlib.__version__,
                    "backend": "Agg", "font": "DejaVu Sans"},
        "seed_policy": "Independent PCG64 generators, seeds 1401/1402/1403; no global RNG.",
        "reproduction": "python3 scripts/python_runtime.py examples/v0.14_lab_studies/generate_studies.py --check",
        "artifacts": [{"path": path, "sha256": sha256(data), "bytes": len(data)}
                      for path, data in sorted(output.items())],
        "artifact_scope": "synthetic figures and data only",
        "figure_generation_status": "generated; deck build, render and review are outside this manifest",
    }
    output["generation_manifest.json"] = json_bytes(manifest)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Recompute and compare bytes without rewriting artifacts.")
    args = parser.parse_args()
    output = generate()
    if args.check:
        different = [path for path, data in output.items()
                     if not (ROOT / path).is_file() or (ROOT / path).read_bytes() != data]
        if different:
            print(json.dumps({"reproduction_pass": False, "different": different}, indent=2))
            return 1
        print(f"Deterministic byte check passed: {len(output)} generated files. No decks built.")
    else:
        for path, data in output.items():
            target = ROOT / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        print(f"Generated {len(output)} synthetic figure/data files. No decks built.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
