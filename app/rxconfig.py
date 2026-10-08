import os
import reflex as rx

config = rx.Config(
    app_name="ui",
    api_url=os.getenv("REFLEX_API_URL", "http://localhost:8002"),
    backend_port=8002,
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(),
    ],
    db_url="sqlite:///reflex.db",
)