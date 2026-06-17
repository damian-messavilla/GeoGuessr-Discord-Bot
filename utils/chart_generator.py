"""Diagramm-Generator für den GeoGuessr Discord Stats Bot.

Erzeugt Discord-kompatible Diagramme im dunklen Design mit matplotlib.
Alle Diagramme werden als temporäre PNG-Dateien gespeichert und der Pfad
wird zurückgegeben. Der Aufrufer ist dafür verantwortlich, die Datei
nach dem Senden zu löschen.
"""

import logging
import tempfile
from datetime import datetime, timedelta
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Nicht-interaktives Backend für Serverbetrieb

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
import matplotlib.dates as mdates
from matplotlib.collections import LineCollection
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Farbpalette – Discord-kompatibles dunkles Design
# ---------------------------------------------------------------------------
COLOR_BG = "#2b2d31"
COLOR_TEXT = "#ffffff"
COLOR_GRID = "#3f4147"
COLOR_WIN = "#57F287"
COLOR_LOSS = "#ED4245"
COLOR_ACCENT = "#5865F2"
COLOR_SECONDARY = "#FEE75C"

# Heatmap-Farbskala (0 Spiele → viele Spiele)
HEATMAP_COLORS = ["#2b2d31", "#0e4429", "#006d32", "#26a641", "#39d353"]

# Standardabmessungen und Auflösung
FIG_WIDTH = 10
FIG_HEIGHT = 6
FIG_DPI = 100


def _setup_style() -> None:
    """Konfiguriert die globalen matplotlib-Stilparameter für das dunkle Discord-Design."""
    plt.rcParams.update({
        "figure.facecolor": COLOR_BG,
        "axes.facecolor": COLOR_BG,
        "axes.edgecolor": COLOR_GRID,
        "axes.labelcolor": COLOR_TEXT,
        "axes.grid": True,
        "grid.color": COLOR_GRID,
        "grid.alpha": 0.5,
        "text.color": COLOR_TEXT,
        "xtick.color": COLOR_TEXT,
        "ytick.color": COLOR_TEXT,
        "font.family": "sans-serif",
        "font.size": 11,
        "legend.facecolor": COLOR_BG,
        "legend.edgecolor": COLOR_GRID,
        "legend.labelcolor": COLOR_TEXT,
        "savefig.facecolor": COLOR_BG,
        "savefig.edgecolor": COLOR_BG,
    })


# Stil beim Laden des Moduls anwenden
_setup_style()


# ---------------------------------------------------------------------------
# Hilfsfunktionen (intern)
# ---------------------------------------------------------------------------

def _parse_datetime(value: str | datetime | None) -> Optional[datetime]:
    """Versucht einen ISO-Datetime-String oder ein datetime-Objekt zu parsen.

    Gibt ``None`` zurück, falls der Wert ungültig ist.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        if isinstance(value, str):
            # Für Diagramme reicht die Sekundengenauigkeit.
            # Schneidet Mikrosekunden und Zeitzonen-Suffixe ab (z.B. .0, .000Z),
            # da fromisoformat in älteren Python-Versionen damit Probleme hat.
            if len(value) >= 19:
                value = value[:19]
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        logger.warning("Konnte Datum nicht parsen: %s", value)
        return None


def _save_figure(fig: plt.Figure, path: Optional[str] = None) -> str:
    """Speichert die Figur als PNG und gibt den Dateipfad zurück.

    Falls kein *path* angegeben ist, wird eine temporäre Datei erstellt.
    """
    if path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        path = tmp.name
        tmp.close()
    fig.savefig(
        path,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
        pad_inches=0.3,
        dpi=FIG_DPI,
    )
    plt.close(fig)
    return path


def _draw_no_data(fig: plt.Figure, ax: plt.Axes) -> None:
    """Zeichnet einen Platzhaltertext, wenn keine Daten vorhanden sind."""
    ax.text(
        0.5, 0.5,
        "Keine Daten vorhanden",
        transform=ax.transAxes,
        ha="center", va="center",
        fontsize=18,
        color=COLOR_TEXT,
        alpha=0.6,
    )
    ax.set_xticks([])
    ax.set_yticks([])


def _german_weekday_short(dt: datetime) -> str:
    """Gibt den deutschen Kurzwochentag für ein Datum zurück."""
    days = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    return days[dt.weekday()]


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def generate_activity_chart(
    games: list[dict],
    path: Optional[str] = None,
) -> str:
    """Erzeugt ein Liniendiagramm der Spielaktivität der letzten 7 Tage.

    Zusätzlich wird ein kleines Balkendiagramm mit der Stundenverteilung
    (0–23 h) als Subplot darunter angezeigt.

    Args:
        games: Liste von Spiel-Dicts mit ``played_at`` (ISO-String).
        path: Optionaler Zieldateipfad; andernfalls wird eine
              temporäre Datei erzeugt.

    Returns:
        Pfad zur gespeicherten PNG-Datei.
    """
    try:
        fig, (ax_main, ax_hours) = plt.subplots(
            2, 1,
            figsize=(FIG_WIDTH, FIG_HEIGHT),
            gridspec_kw={"height_ratios": [3, 1]},
        )
        fig.subplots_adjust(hspace=0.45)

        # Zeitraum: letzte 7 Tage (einschließlich heute) in 3-Stunden-Blöcken
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = today - timedelta(days=6)
        
        interval_hours = 3
        date_range = [start_date + timedelta(hours=i) for i in range(0, 7 * 24, interval_hours)]

        # Daten parsen und filtern
        parsed_dates: list[datetime] = []
        for g in games or []:
            dt = _parse_datetime(g.get("played_at"))
            if dt is not None:
                parsed_dates.append(dt)

        # Spiele pro Bin (3 Stunden) zählen
        counts_per_bin = []
        for d in date_range:
            bin_end = d + timedelta(hours=interval_hours)
            count = sum(
                1 for dt in parsed_dates
                if d <= dt < bin_end
            )
            counts_per_bin.append(count)

        # Stunden-Verteilung (gesamte 7 Tage)
        start_of_range = date_range[0]
        hour_counts = [0] * 24
        for dt in parsed_dates:
            if dt >= start_of_range:
                hour_counts[dt.hour] += 1

        has_data = any(c > 0 for c in counts_per_bin)

        # --- Hauptdiagramm (Linie + Fläche) ---
        if not has_data:
            _draw_no_data(fig, ax_main)
        else:
            x = np.arange(len(date_range))
            y = np.array(counts_per_bin, dtype=float)

            # Linie zeichnen
            ax_main.plot(
                x, y,
                color=COLOR_ACCENT,
                linewidth=2.5,
                zorder=3,
            )
            # Marker auf den Datenpunkten
            ax_main.scatter(
                x, y,
                color=COLOR_ACCENT,
                s=50,
                zorder=4,
                edgecolors=COLOR_TEXT,
                linewidths=0.8,
            )

            # Fläche unter der Kurve mit Gradient
            gradient = np.linspace(0, 1, 256).reshape(1, -1)
            gradient = np.vstack([gradient] * 2)
            cmap = mcolors.LinearSegmentedColormap.from_list(
                "fill_grad",
                [(0, COLOR_ACCENT + "00"), (1, COLOR_ACCENT + "55")],
            )
            # Fläche als halbtransparentes Fill
            ax_main.fill_between(
                x, y, 0,
                color=COLOR_ACCENT,
                alpha=0.15,
                zorder=1,
            )

            ax_main.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
            ax_main.set_ylim(bottom=0)

        # X-Achsen-Beschriftung: Nur Mitternacht und 12:00 Uhr beschriften
        ticks = []
        labels = []
        for i, d in enumerate(date_range):
            if d.hour == 0:
                ticks.append(i)
                labels.append(f"{_german_weekday_short(d)} {d.strftime('%d.%m')}")
            elif d.hour == 12:
                ticks.append(i)
                labels.append("12:00")

        ax_main.set_xticks(ticks)
        ax_main.set_xticklabels(labels, fontsize=9)
        ax_main.set_ylabel("Spiele")
        ax_main.set_title(
            "📊 Spielaktivität — Letzte 7 Tage",
            fontsize=14,
            fontweight="bold",
            pad=12,
        )

        # --- Stundenverteilung (Subplot) ---
        if not any(h > 0 for h in hour_counts):
            _draw_no_data(fig, ax_hours)
        else:
            hours = np.arange(24)
            ax_hours.bar(
                hours,
                hour_counts,
                color=COLOR_SECONDARY,
                alpha=0.8,
                width=0.7,
            )
            ax_hours.set_xticks(hours)
            ax_hours.set_xticklabels(
                [str(h) for h in hours],
                fontsize=7,
            )
            ax_hours.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
            ax_hours.set_xlim(-0.5, 23.5)
            ax_hours.set_ylim(bottom=0)

        ax_hours.set_title(
            "Aktivste Stunden",
            fontsize=10,
            fontweight="bold",
            pad=6,
        )

        return _save_figure(fig, path)

    except Exception:
        logger.exception("Fehler beim Erzeugen des Aktivitätsdiagramms")
        # Fallback: leeres Diagramm mit Fehlermeldung erzeugen
        fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
        _draw_no_data(fig, ax)
        ax.set_title("📊 Spielaktivität — Fehler", fontsize=14, fontweight="bold")
        return _save_figure(fig, path)


def generate_elo_chart(
    games: list[dict],
    path: Optional[str] = None,
) -> str:
    """Erzeugt ein Elo-Verlaufsdiagramm mit farblich getrennten Segmenten.

    Steigende Abschnitte werden grün, fallende rot dargestellt.
    Markierungen für aktuellen, minimalen und maximalen Elo-Wert.

    Args:
        games: Liste von Spiel-Dicts mit ``played_at`` und ``elo_after``,
               aufsteigend nach ``played_at`` sortiert.
        path: Optionaler Zieldateipfad.

    Returns:
        Pfad zur gespeicherten PNG-Datei.
    """
    try:
        fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))

        # Daten parsen und filtern (None-Werte überspringen)
        valid_games: list[tuple[datetime, float]] = []
        for g in games or []:
            dt = _parse_datetime(g.get("played_at"))
            elo = g.get("elo_after")
            if dt is not None and elo is not None:
                try:
                    valid_games.append((dt, float(elo)))
                except (ValueError, TypeError):
                    continue

        if not valid_games:
            _draw_no_data(fig, ax)
            ax.set_title("📈 Elo-Verlauf", fontsize=14, fontweight="bold")
            return _save_figure(fig, path)

        # Daten vorbereiten
        times = [g[0] for g in valid_games]
        elos = np.array([g[1] for g in valid_games])
        x = np.arange(len(elos))

        start_elo = elos[0]
        current_elo = elos[-1]
        min_elo = elos.min()
        max_elo = elos.max()
        min_idx = int(elos.argmin())
        max_idx = int(elos.argmax())
        net_change = current_elo - start_elo

        # Farbig segmentierte Linie (grün = steigend, rot = fallend)
        if len(elos) >= 2:
            points = np.column_stack([x, elos]).reshape(-1, 1, 2)
            segments = np.concatenate([points[:-1], points[1:]], axis=1)

            # Steigung pro Segment bestimmen
            slopes = np.diff(elos)
            colors = [COLOR_WIN if s >= 0 else COLOR_LOSS for s in slopes]

            lc = LineCollection(segments, colors=colors, linewidths=2.5, zorder=3)
            ax.add_collection(lc)
            ax.set_xlim(x[0], x[-1])
            elo_margin = max((max_elo - min_elo) * 0.15, 10)
            ax.set_ylim(min_elo - elo_margin, max_elo + elo_margin)
        else:
            # Einzelner Punkt
            ax.scatter(
                x, elos,
                color=COLOR_ACCENT,
                s=80,
                zorder=4,
            )
            ax.set_xlim(-0.5, 0.5)
            ax.set_ylim(elos[0] - 50, elos[0] + 50)

        # Startlinie (gestrichelt)
        ax.axhline(
            y=start_elo,
            color=COLOR_TEXT,
            linestyle="--",
            linewidth=1,
            alpha=0.4,
            zorder=1,
            label=f"Start: {int(start_elo)}",
        )

        # Annotationen: Min, Max, Aktuell
        annotation_style = dict(
            fontsize=9,
            fontweight="bold",
            zorder=5,
            bbox=dict(
                boxstyle="round,pad=0.3",
                facecolor=COLOR_BG,
                edgecolor=COLOR_GRID,
                alpha=0.9,
            ),
        )

        # Aktueller Elo
        ax.annotate(
            f"Aktuell: {int(current_elo)}",
            xy=(x[-1], current_elo),
            xytext=(15, 15),
            textcoords="offset points",
            color=COLOR_ACCENT,
            arrowprops=dict(arrowstyle="->", color=COLOR_ACCENT, lw=1.2),
            **annotation_style,
        )

        # Minimum (nur wenn es sich vom aktuellen unterscheidet)
        if min_idx != len(elos) - 1:
            ax.annotate(
                f"Min: {int(min_elo)}",
                xy=(x[min_idx], min_elo),
                xytext=(-15, -25),
                textcoords="offset points",
                color=COLOR_LOSS,
                arrowprops=dict(arrowstyle="->", color=COLOR_LOSS, lw=1.2),
                **annotation_style,
            )

        # Maximum (nur wenn es sich vom aktuellen unterscheidet)
        if max_idx != len(elos) - 1:
            ax.annotate(
                f"Max: {int(max_elo)}",
                xy=(x[max_idx], max_elo),
                xytext=(-15, 20),
                textcoords="offset points",
                color=COLOR_WIN,
                arrowprops=dict(arrowstyle="->", color=COLOR_WIN, lw=1.2),
                **annotation_style,
            )

        # Marker auf den Datenpunkten
        ax.scatter(
            x, elos,
            color=COLOR_ACCENT,
            s=20,
            zorder=4,
            alpha=0.6,
        )

        # X-Achse: Zeitstempel als Beschriftung (max. ~10 Ticks)
        if len(times) > 1:
            num_ticks = min(len(times), 10)
            tick_indices = np.linspace(0, len(times) - 1, num_ticks, dtype=int)
            ax.set_xticks(tick_indices)
            ax.set_xticklabels(
                [times[i].strftime("%d.%m. %H:%M") for i in tick_indices],
                fontsize=8,
                rotation=25,
                ha="right",
            )
        else:
            ax.set_xticks([0])
            ax.set_xticklabels([times[0].strftime("%d.%m. %H:%M")], fontsize=8)

        ax.set_ylabel("Elo")

        # Titel + Untertitel mit Netto-Veränderung
        sign = "+" if net_change >= 0 else ""
        change_color = COLOR_WIN if net_change >= 0 else COLOR_LOSS
        ax.set_title(
            "📈 Elo-Verlauf",
            fontsize=14,
            fontweight="bold",
            pad=20,
        )
        ax.text(
            0.5, 1.02,
            f"Gesamt: {sign}{int(net_change)} Elo",
            transform=ax.transAxes,
            ha="center",
            fontsize=11,
            color=change_color,
            fontweight="bold",
        )

        ax.legend(loc="lower right", fontsize=9)

        return _save_figure(fig, path)

    except Exception:
        logger.exception("Fehler beim Erzeugen des Elo-Diagramms")
        fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
        _draw_no_data(fig, ax)
        ax.set_title("📈 Elo-Verlauf — Fehler", fontsize=14, fontweight="bold")
        return _save_figure(fig, path)


def generate_winrate_chart(
    stats_by_mode: list[dict],
    path: Optional[str] = None,
) -> str:
    """Erzeugt ein horizontales Balkendiagramm mit Win/Loss-Ratio pro Spielmodus.

    Bei nur 1–2 Modi wird zusätzlich ein Kreisdiagramm mit der
    Gesamtverteilung angezeigt.

    Args:
        stats_by_mode: Liste von Dicts mit ``game_mode``, ``wins``,
                       ``losses``.
        path: Optionaler Zieldateipfad.

    Returns:
        Pfad zur gespeicherten PNG-Datei.
    """
    try:
        # Daten bereinigen und sortieren
        valid_modes: list[dict] = []
        for s in stats_by_mode or []:
            mode = s.get("game_mode")
            wins = s.get("wins", 0) or 0
            losses = s.get("losses", 0) or 0
            if mode is not None:
                valid_modes.append({
                    "game_mode": str(mode),
                    "wins": int(wins),
                    "losses": int(losses),
                })

        # Nach Gesamtanzahl absteigend sortieren
        valid_modes.sort(key=lambda m: m["wins"] + m["losses"], reverse=True)

        show_pie = len(valid_modes) in (1, 2)

        if show_pie and valid_modes:
            fig, (ax_bar, ax_pie) = plt.subplots(
                1, 2,
                figsize=(FIG_WIDTH, FIG_HEIGHT),
                gridspec_kw={"width_ratios": [3, 1]},
            )
            fig.subplots_adjust(wspace=0.4)
        else:
            fig, ax_bar = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
            ax_pie = None

        if not valid_modes:
            _draw_no_data(fig, ax_bar)
            ax_bar.set_title(
                "🏆 Win/Loss-Ratio nach Spielmodus",
                fontsize=14, fontweight="bold",
            )
            return _save_figure(fig, path)

        # Daten vorbereiten
        modes = [m["game_mode"] for m in valid_modes]
        wins = np.array([m["wins"] for m in valid_modes])
        losses = np.array([m["losses"] for m in valid_modes])
        totals = wins + losses

        y = np.arange(len(modes))
        bar_height = 0.35

        # Horizontale Balken
        bars_wins = ax_bar.barh(
            y - bar_height / 2,
            wins,
            bar_height,
            color=COLOR_WIN,
            label="Siege",
            zorder=3,
        )
        bars_losses = ax_bar.barh(
            y + bar_height / 2,
            losses,
            bar_height,
            color=COLOR_LOSS,
            label="Niederlagen",
            zorder=3,
        )

        # Win-Prozent anzeigen
        for i, (w, l, total) in enumerate(zip(wins, losses, totals)):
            pct = (w / total * 100) if total > 0 else 0
            max_val = max(w, l)
            ax_bar.text(
                max_val + 0.5,
                y[i],
                f"{pct:.0f}%",
                va="center",
                fontsize=10,
                fontweight="bold",
                color=COLOR_SECONDARY,
                zorder=5,
            )

        ax_bar.set_yticks(y)
        ax_bar.set_yticklabels(modes)
        ax_bar.set_xlabel("Anzahl Spiele")
        ax_bar.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        ax_bar.invert_yaxis()  # Meiste Spiele oben
        ax_bar.legend(loc="lower right", fontsize=9)
        ax_bar.set_title(
            "🏆 Win/Loss-Ratio nach Spielmodus",
            fontsize=14,
            fontweight="bold",
            pad=12,
        )

        # Kreisdiagramm (nur bei 1–2 Modi)
        if ax_pie is not None:
            total_wins = int(wins.sum())
            total_losses = int(losses.sum())
            if total_wins + total_losses > 0:
                ax_pie.pie(
                    [total_wins, total_losses],
                    labels=["Siege", "Niederlagen"],
                    colors=[COLOR_WIN, COLOR_LOSS],
                    autopct="%1.0f%%",
                    startangle=90,
                    textprops={"color": COLOR_TEXT, "fontsize": 10},
                    wedgeprops={"edgecolor": COLOR_BG, "linewidth": 2},
                )
                ax_pie.set_title(
                    "Gesamt",
                    fontsize=11,
                    fontweight="bold",
                    pad=10,
                )
            else:
                _draw_no_data(fig, ax_pie)

        return _save_figure(fig, path)

    except Exception:
        logger.exception("Fehler beim Erzeugen des Winrate-Diagramms")
        fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
        _draw_no_data(fig, ax)
        ax.set_title(
            "🏆 Win/Loss-Ratio — Fehler",
            fontsize=14, fontweight="bold",
        )
        return _save_figure(fig, path)


def generate_heatmap(
    games: list[dict],
    year: int,
    path: Optional[str] = None,
) -> str:
    """Erzeugt eine GitHub-ähnliche Aktivitäts-Heatmap für ein ganzes Jahr.

    52–53 Spalten (Wochen) × 7 Zeilen (Mo–So). Die Farbskala reicht
    von dunkel (0 Spiele) bis leuchtend grün (viele Spiele).

    Args:
        games: Liste von Spiel-Dicts mit ``played_at`` (ISO-String).
        year: Das Kalenderjahr, für das die Heatmap erstellt wird.
        path: Optionaler Zieldateipfad.

    Returns:
        Pfad zur gespeicherten PNG-Datei.
    """
    try:
        # Spiele pro Tag zählen
        day_counts: dict[str, int] = {}
        for g in games or []:
            dt = _parse_datetime(g.get("played_at"))
            if dt is not None and dt.year == year:
                key = dt.strftime("%Y-%m-%d")
                day_counts[key] = day_counts.get(key, 0) + 1

        total_games = sum(day_counts.values())

        # Wochen-/Tagesmatrix aufbauen
        # Start: Montag der KW, die den 1. Januar enthält
        jan1 = datetime(year, 1, 1)
        # Offset zum Montag derselben Woche
        start = jan1 - timedelta(days=jan1.weekday())

        dec31 = datetime(year, 12, 31)
        end = dec31 + timedelta(days=(6 - dec31.weekday()))

        num_weeks = ((end - start).days + 1) // 7
        data = np.zeros((7, num_weeks), dtype=int)

        current = start
        for week in range(num_weeks):
            for day in range(7):
                d = current + timedelta(weeks=week, days=day)
                if d.year == year:
                    key = d.strftime("%Y-%m-%d")
                    data[day, week] = day_counts.get(key, 0)

        # Benutzerdefinierte Colormap erstellen
        cmap = mcolors.LinearSegmentedColormap.from_list(
            "heatmap_cmap",
            HEATMAP_COLORS,
            N=256,
        )

        # Maximalen Wert bestimmen (mindestens 1 für Normalisierung)
        max_count = max(data.max(), 1)
        norm = mcolors.Normalize(vmin=0, vmax=max_count)

        fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))

        cell_size = 0.85
        gap = 0.15

        # Zellen zeichnen
        for week in range(num_weeks):
            for day in range(7):
                count = data[day, week]
                color = cmap(norm(count))

                rect = mpatches.FancyBboxPatch(
                    (week * (cell_size + gap), (6 - day) * (cell_size + gap)),
                    cell_size,
                    cell_size,
                    boxstyle="round,pad=0.02",
                    facecolor=color,
                    edgecolor="none",
                    linewidth=0,
                )
                ax.add_patch(rect)

        # Achsenlimits
        ax.set_xlim(-0.5, num_weeks * (cell_size + gap))
        ax.set_ylim(-0.5, 7 * (cell_size + gap))
        ax.set_aspect("equal")
        ax.invert_yaxis()

        # Tagesbeschriftungen (Mo, Mi, Fr)
        day_labels = {0: "Mo", 2: "Mi", 4: "Fr"}
        for day_idx, label in day_labels.items():
            ax.text(
                -0.8,
                (6 - day_idx) * (cell_size + gap) + cell_size / 2,
                label,
                ha="right",
                va="center",
                fontsize=8,
                color=COLOR_TEXT,
                alpha=0.8,
            )

        # Monatsbeschriftungen oben
        current_month = -1
        for week in range(num_weeks):
            d = start + timedelta(weeks=week)
            if d.year == year and d.month != current_month:
                current_month = d.month
                month_names = [
                    "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                    "Jul", "Aug", "Sep", "Okt", "Nov", "Dez",
                ]
                ax.text(
                    week * (cell_size + gap),
                    -0.5,
                    month_names[current_month - 1],
                    ha="left",
                    va="bottom",
                    fontsize=8,
                    color=COLOR_TEXT,
                    alpha=0.8,
                )

        # Achsen ausblenden
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(False)

        # Titel + Untertitel
        ax.set_title(
            f"🔥 Aktivitäts-Heatmap {year}",
            fontsize=14,
            fontweight="bold",
            pad=20,
        )
        ax.text(
            0.5, 1.02,
            f"Gesamt: {total_games} Spiele",
            transform=ax.transAxes,
            ha="center",
            fontsize=11,
            color=COLOR_TEXT,
            alpha=0.7,
        )

        if total_games == 0:
            ax.text(
                0.5, 0.5,
                "Keine Daten vorhanden",
                transform=ax.transAxes,
                ha="center",
                va="center",
                fontsize=16,
                color=COLOR_TEXT,
                alpha=0.5,
                zorder=10,
            )

        return _save_figure(fig, path)

    except Exception:
        logger.exception("Fehler beim Erzeugen der Heatmap")
        fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
        _draw_no_data(fig, ax)
        ax.set_title(
            f"🔥 Aktivitäts-Heatmap — Fehler",
            fontsize=14, fontweight="bold",
        )
        return _save_figure(fig, path)
