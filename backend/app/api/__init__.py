"""HTTP layer: thin routers over the service layer.

Each module owns one area of ``planning/API_CONTRACT.md``: health, portfolio, watchlist and
chat. ``deps`` exposes the objects created by ``app.main.create_app``.
"""
