# backend/app/main.py
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import auth as auth_router
from .routers import booking as booking_router
from .routers import users as users_router
from .routers import ops as ops_router
# se hai anche il router wa_local, puoi includerlo più sotto (commentato qui)
# from .routers import wa_local as wa_local_router
from .routers.manager import router as manager_router  # se esiste/serve

app = FastAPI(title="W8 x CAG", docs_url=None, redoc_url=None)

# --- Static frontend ---
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

# --- API Routers ---
app.include_router(auth_router.router)
app.include_router(booking_router.router)
app.include_router(users_router.router)
app.include_router(ops_router.router)
# app.include_router(wa_local_router.router)
# app.include_router(manager_router)  # monta solo se effettivamente usato

# --- Maintenance middleware (protegge TUTTE le pagine quando attivo) ---
@app.middleware("http")
async def maintenance_gate(request: Request, call_next):
    """
    Se MAINTENANCE_MODE=True:
      - consente solo API (/auth, /booking, /users, /ops, /wa-local), /ping
      - consente la pagina /frontend/maintenance.html e gli asset sotto /frontend/assets/
      - tutto il resto viene rediretto a /frontend/maintenance.html
    """
    if settings.MAINTENANCE_MODE:
        p = request.url.path

        # Endpoints sempre permessi (API + health)
        api_prefixes = (
            "/auth",
            "/booking",
            "/users",
            "/ops",
            "/wa-local",
            "/ping",
        )

        # Pagine/asset necessari per mostrare la pagina offline
        allowed_frontend = (
            "/frontend/maintenance.html",
            "/frontend/assets/",
            "/favicon.ico",
        )

        # Permetti anche l'OpenAPI in caso serva per test (facoltativo)
        openapi_paths = ("/openapi.json", "/docs", "/redoc")

        if (
            not p.startswith(api_prefixes)
            and not p.startswith(openapi_paths)
            and not p == allowed_frontend[0]
            and not p.startswith(allowed_frontend[1])
            and not p == allowed_frontend[2]
        ):
            # qualsiasi pagina/route non API -> redirect alla maintenance
            return RedirectResponse("/frontend/maintenance.html", status_code=302)

    return await call_next(request)

# --- URL corti (redirect) ---
@app.get("/", include_in_schema=False)
def root():
    # se maintenance attivo, il middleware sopra intercetta e redirige
    return RedirectResponse("/login", status_code=302)

@app.get("/login", include_in_schema=False)
@app.get("/login.html", include_in_schema=False)
def login_redirect():
    return RedirectResponse("/frontend/auth/login.html", status_code=302)

@app.get("/register", include_in_schema=False)
@app.get("/register.html", include_in_schema=False)
def register_redirect():
    return RedirectResponse("/frontend/auth/register.html", status_code=302)

@app.get("/reset", include_in_schema=False)
@app.get("/reset.html", include_in_schema=False)
def reset_redirect():
    return RedirectResponse("/frontend/auth/reset.html", status_code=302)

@app.get("/manager", include_in_schema=False)
def manager_redirect():
    return RedirectResponse("/frontend/dash/manager.html", status_code=302)

@app.get("/producer", include_in_schema=False)
def producer_redirect():
    return RedirectResponse("/frontend/dash/producer.html", status_code=302)

@app.get("/artist", include_in_schema=False)
def artist_redirect():
    return RedirectResponse("/frontend/dash/artist.html", status_code=302)

# favicon corto
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = FRONTEND_DIR / "assets" / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico))
    return RedirectResponse("/frontend/assets/logo.png", status_code=302)

@app.get("/ping")
def ping():
    return {"ok": True}