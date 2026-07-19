from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import collect, settings_api
from app.web import pages

app = FastAPI(title="Work History Summary", version="0.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(collect.router)
app.include_router(settings_api.router)
app.include_router(pages.router)
