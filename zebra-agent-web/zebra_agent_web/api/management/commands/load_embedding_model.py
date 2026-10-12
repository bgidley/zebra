"""Django management command: set up in-database embeddings for memory search (#169).

Usage:
    python manage.py load_embedding_model [--strict]

Idempotent, Oracle only. Steps:

1. Ensure the ``embedding`` VECTOR columns exist.
2. Load the ONNX embedding model from OCI Object Storage with
   ``DBMS_VECTOR.LOAD_ONNX_MODEL_CLOUD`` (database resource principal), unless
   the schema already has it.
3. Smoke-test it (``VECTOR_EMBEDDING`` returns a 384-dimension vector).
4. Create/replace the embedding triggers and embed rows that have none.

Without ``--strict`` any failure is logged and the command exits 0, so a deploy
is never blocked: memory search falls back to keyword ranking until the model
loads (the container entrypoint re-runs this on every start). CI uses
``--strict`` so a broken setup fails the pipeline.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from zebra_agent_web import embeddings


class Command(BaseCommand):
    help = "Load the in-database embedding model and install memory embedding triggers."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero if the model cannot be loaded or tested.",
        )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        if not embeddings.is_oracle():
            self.stdout.write("Not an Oracle database — skipping embedding setup.")
            return
        try:
            self._setup()
        except Exception as e:  # noqa: BLE001 - see --strict
            if options["strict"]:
                raise CommandError(f"Embedding setup failed: {e}") from e
            self.stderr.write(
                f"WARNING: embedding setup failed, memory search will use keyword ranking: {e}"
            )
        finally:
            embeddings.reset_ready_cache()

    def _setup(self) -> None:
        from django.conf import settings

        conf = settings.ZEBRA_AGENT_SETTINGS
        name = embeddings.model_name()
        # Oracle DDL commits implicitly; the backfill UPDATE runs under autocommit.
        with connection.cursor() as cursor:
            added = embeddings.ensure_vector_columns(cursor)
            if added:
                self.stdout.write(f"Added embedding column to: {', '.join(added)}")

            if embeddings.model_loaded(cursor, name):
                self.stdout.write(f"Model {name} already loaded.")
            else:
                uri = conf["EMBEDDING_MODEL_URI"]
                self.stdout.write(f"Loading model {name} from {uri} ...")
                embeddings.load_model(cursor, name, uri, conf["EMBEDDING_MODEL_CREDENTIAL"] or None)
                self.stdout.write(f"Model {name} loaded.")

            dims = embeddings.smoke_test(cursor, name)
            if dims != embeddings.DIMENSIONS:
                raise RuntimeError(f"model {name} returned {dims} dimensions, expected 384")

            embeddings.install_triggers(cursor, name)
            counts = embeddings.backfill(cursor)
        summary = ", ".join(f"{table}={n}" for table, n in counts.items())
        self.stdout.write(f"Embedding triggers installed; backfilled rows: {summary}")
