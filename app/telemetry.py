"""Traces + métriques — [FOURNI], hérité du brief de remédiation.

Trois primitives, déjà branchées sur ``/v1`` :

* un **tracer** OpenTelemetry (spans ``analyse.requete`` → ``llm.appel``) ;
* un **logger** structuré (structlog, JSON) ;
* depuis le 24/09, traces et journaux sont aussi **conservés sur disque** (``ops/traces.jsonl``,
  ``ops/logs.jsonl``) : la console et Jaeger (stockage en mémoire) perdent tout à l'arrêt ;
* un **journal de métriques** (``MetricsStore``) : une ligne JSON par requête
  servie — version, latence, erreur, score de confiance, coût, nombre d'appels
  LLM. C'est ce fichier que lisent le tableau de bord (``ops/dashboard.py``) et
  la surveillance du déploiement (``ops/deploy.py``).

Lire ``docs/schema_remediation.md`` pour savoir comment l'exploiter.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import structlog
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import Tracer

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_METRIQUES_DEFAUT = RACINE / "ops" / "metrics.jsonl"
CHEMIN_TRACES_DEFAUT = RACINE / "ops" / "traces.jsonl"
CHEMIN_LOGS_DEFAUT = RACINE / "ops" / "logs.jsonl"


class _SortieDouble:
    """Écrit chaque ligne de journal sur la console ET à la fin d'un fichier JSONL."""

    def __init__(self, chemin: Path) -> None:
        self.chemin = chemin
        self._verrou = threading.Lock()

    def write(self, texte: str) -> None:
        sys.stdout.write(texte)
        if texte.strip():
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            with self._verrou, self.chemin.open("a", encoding="utf-8") as f:
                f.write(texte if texte.endswith("\n") else texte + "\n")

    def flush(self) -> None:
        sys.stdout.flush()


def configure_logging(level: str = "INFO", logs_path: Path | str | None = None) -> None:
    fabrique = (structlog.PrintLoggerFactory(file=_SortieDouble(Path(logs_path)))
                if logs_path else structlog.PrintLoggerFactory())
    structlog.configure(
        logger_factory=fabrique,
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=False,
    )


@dataclass
class Mesure:
    """Une requête servie, telle qu'elle est journalisée."""

    ts: float
    version: str
    route: str
    latence_ms: float
    erreur: bool = False
    score: float | None = None
    cout_eur: float = 0.0
    appels_llm: int = 0
    tokens: int = 0
    tokens_entree: int = 0     # brique 23 : le partage entrée/sortie, sans lui le coût réel est incalculable
    tokens_sortie: int = 0
    tronque: bool = False
    request_id: str | None = None  # 24/09 : relie la ligne à la réponse, à la trace et aux journaux

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class MetricsStore:
    """Journal de métriques en JSONL, thread-safe, lisible à chaud."""

    def __init__(self, chemin: Path | str | None = None) -> None:
        self.chemin = Path(chemin or os.environ.get("METRICS_PATH", CHEMIN_METRIQUES_DEFAUT))
        self._verrou = threading.Lock()

    def enregistrer(self, mesure: Mesure) -> None:
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        with self._verrou, self.chemin.open("a", encoding="utf-8") as f:
            f.write(json.dumps(mesure.to_dict(), ensure_ascii=False) + "\n")

    def lire(self, depuis_s: float | None = None, version: str | None = None) -> list[Mesure]:
        """Mesures des ``depuis_s`` dernières secondes (toutes si None)."""
        if not self.chemin.exists():
            return []
        seuil = time.time() - depuis_s if depuis_s else None
        mesures: list[Mesure] = []
        for ligne in self._lignes():
            m = Mesure(**ligne)
            if seuil is not None and m.ts < seuil:
                continue
            if version is not None and m.version != version:
                continue
            mesures.append(m)
        return mesures

    def purger(self) -> None:
        if self.chemin.exists():
            self.chemin.unlink()

    def _lignes(self) -> Iterator[dict[str, Any]]:
        with self._verrou, self.chemin.open(encoding="utf-8") as f:
            for ligne in f:
                ligne = ligne.strip()
                if ligne:
                    try:
                        yield json.loads(ligne)
                    except json.JSONDecodeError:
                        continue


@dataclass
class Telemetry:
    tracer: Tracer
    logger: Any
    metriques: MetricsStore
    spans: list[Any] = field(default_factory=list)


def build_telemetry(
    *,
    span_exporter: SpanExporter | None = None,
    span_exporters: list[SpanExporter] | None = None,
    metrics_path: Path | str | None = None,
    logs_path: Path | str | None = None,
    level: str = "INFO",
    service_name: str = "mardik",
) -> Telemetry:
    configure_logging(level, logs_path)
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    exporteurs = span_exporters if span_exporters is not None else [span_exporter or ConsoleSpanExporter()]
    for exporteur in exporteurs:
        provider.add_span_processor(SimpleSpanProcessor(exporteur))
    tracer = provider.get_tracer(service_name)
    return Telemetry(
        tracer=tracer,
        logger=structlog.get_logger(service_name),
        metriques=MetricsStore(metrics_path),
    )


_defaut: Telemetry | None = None


def exporteurs_depuis_mode(mode: str) -> list[SpanExporter]:
    """``OTEL_TRACES`` : une liste séparée par des virgules parmi ``console``, ``otlp`` (collecteur,
    ex. Jaeger — conception Chantier 2 §7), ``fichier`` (``TRACES_PATH``, conservé sur disque) ; ``off`` = rien."""
    exporteurs: list[SpanExporter] = []
    for nom in (m.strip().lower() for m in mode.split(",")):
        if nom == "console":
            exporteurs.append(ConsoleSpanExporter())
        elif nom == "otlp":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            endpoint = os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces"
            )
            exporteurs.append(OTLPSpanExporter(endpoint=endpoint))
        elif nom == "fichier":
            exporteurs.append(FichierSpanExporter(os.environ.get("TRACES_PATH", CHEMIN_TRACES_DEFAUT)))
    return exporteurs


def build_default_telemetry() -> Telemetry:
    """Télémétrie de production : spans selon ``OTEL_TRACES`` (défaut ``console,fichier``), journaux sur la
    console et dans ``ops/logs.jsonl`` (``LOGS_PATH`` ; ``off`` = console seule), métriques dans ``ops/metrics.jsonl``."""
    global _defaut
    if _defaut is None:
        logs = os.environ.get("LOGS_PATH", str(CHEMIN_LOGS_DEFAUT))
        _defaut = build_telemetry(
            span_exporters=exporteurs_depuis_mode(os.environ.get("OTEL_TRACES", "console,fichier")),
            logs_path=None if logs.lower() == "off" else logs,
            level=os.environ.get("LOG_LEVEL", "INFO"),
            service_name=os.environ.get("OTEL_SERVICE_NAME", "mardik"),
        )
    return _defaut


class NoopSpanExporter(SpanExporter):
    def export(self, spans):  # type: ignore[override]
        from opentelemetry.sdk.trace.export import SpanExportResult

        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


class FichierSpanExporter(SpanExporter):
    """Une ligne JSON par span, ajoutée à un fichier : la trace survit à l'arrêt du processus et de Jaeger.
    Seuls le nom, les identifiants, les horodatages et les attributs sont écrits — jamais le texte analysé."""

    def __init__(self, chemin: Path | str) -> None:
        self.chemin = Path(chemin)
        self._verrou = threading.Lock()

    def export(self, spans):  # type: ignore[override]
        from opentelemetry.sdk.trace.export import SpanExportResult

        lignes = []
        for span in spans:
            ctx = span.get_span_context()
            lignes.append(json.dumps({
                "nom": span.name,
                "trace_id": format(ctx.trace_id, "032x"),
                "span_id": format(ctx.span_id, "016x"),
                "parent_id": format(span.parent.span_id, "016x") if span.parent else None,
                "debut": (span.start_time or 0) / 1e9,
                "duree_ms": round(((span.end_time or 0) - (span.start_time or 0)) / 1e6, 3),
                "statut": span.status.status_code.name,
                "attributs": dict(span.attributes or {}),
            }, ensure_ascii=False))
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        with self._verrou, self.chemin.open("a", encoding="utf-8") as f:
            f.write("".join(ligne + "\n" for ligne in lignes))
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None
