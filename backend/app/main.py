from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .routers import auth as auth_router
from .routers import booking as booking_router
from .routers import users as users_router
from .routers import wa_local as wa_local_router
from .routers import ops as ops_router
from .routers.manager import router as manager_router
import os
app = FastAPI(title="W8 x CAG")
app.include_router(users_router.router)
app.include_router(auth_router.router)
app.include_router(booking_router.router)
app.include_router(wa_local_router.router)
app.include_router(ops_router.router)
app.include_router(manager_router)

frontend_dir = os.path.join(os.path.dirname(__file__), "../../frontend")
app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

@app.get("/ping")
def ping(): return {"ok": True}