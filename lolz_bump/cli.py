def main() -> None:
    import logging

    from .app import main as run

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        run()
    except RuntimeError as exc:
        logging.error("startup_failed error=%s", exc)
        raise SystemExit(1) from exc
