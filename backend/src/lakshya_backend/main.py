from fastapi import FastAPI

app = FastAPI(title="Lakshya API")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check for Docker and uptime monitors."""
    return {"status": "ok"}
