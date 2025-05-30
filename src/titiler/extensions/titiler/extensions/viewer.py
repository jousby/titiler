"""titiler Viewer Extensions."""

import jinja2
from attrs import define
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from titiler.core.factory import FactoryExtension, TilerFactory

jinja2_env = jinja2.Environment(
    loader=jinja2.ChoiceLoader([jinja2.PackageLoader(__package__, "templates")])
)
DEFAULT_TEMPLATES = Jinja2Templates(env=jinja2_env)


@define
class cogViewerExtension(FactoryExtension):
    """Add /viewer endpoint to the TilerFactory."""

    templates: Jinja2Templates = DEFAULT_TEMPLATES

    def register(self, factory: TilerFactory):
        """Register endpoint to the tiler factory."""

        @factory.router.get(
            "/viewer",
            response_class=HTMLResponse,
            operation_id=f"{factory.operation_prefix}getViewer",
        )
        def cog_viewer(request: Request):
            """COG Viewer."""
            return self.templates.TemplateResponse(
                request,
                name="cog_viewer.html",
                context={
                    "tilejson_endpoint": factory.url_for(
                        request, "tilejson", tileMatrixSetId="WebMercatorQuad"
                    ),
                    "info_endpoint": factory.url_for(request, "info_geojson"),
                    "statistics_endpoint": factory.url_for(request, "statistics"),
                    "viewer_enabled": getattr(factory, "add_viewer", False),
                },
                media_type="text/html",
            )


@define
class stacViewerExtension(FactoryExtension):
    """Add /viewer endpoint to the TilerFactory."""

    templates: Jinja2Templates = DEFAULT_TEMPLATES

    def register(self, factory: TilerFactory):
        """Register endpoint to the tiler factory."""

        @factory.router.get(
            "/viewer",
            response_class=HTMLResponse,
            operation_id=f"{factory.operation_prefix}getViewer",
        )
        def stac_viewer(request: Request):
            """STAC Viewer."""
            return self.templates.TemplateResponse(
                request,
                name="stac_viewer.html",
                context={
                    "tilejson_endpoint": factory.url_for(
                        request, "tilejson", tileMatrixSetId="WebMercatorQuad"
                    ),
                    "info_endpoint": factory.url_for(request, "info_geojson"),
                    "statistics_endpoint": factory.url_for(request, "asset_statistics"),
                },
                media_type="text/html",
            )
