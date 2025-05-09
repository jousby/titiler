"""rio-cogeo Extension."""

from attrs import define
from fastapi import Depends, Query
from typing_extensions import Annotated

from titiler.core.factory import FactoryExtension, TilerFactory
from titiler.core.resources.responses import JSONResponse

try:
    from rio_cogeo.cogeo import cog_info
    from rio_cogeo.models import Info
except ImportError:  # pragma: nocover
    cog_info = None  # type: ignore
    Info = None


@define
class cogValidateExtension(FactoryExtension):
    """Add /validate endpoint to a COG TilerFactory."""

    def register(self, factory: TilerFactory):
        """Register endpoint to the tiler factory."""

        assert (
            cog_info is not None
        ), "'rio-cogeo' must be installed to use CogValidateExtension"

        @factory.router.get(
            "/validate",
            response_model=Info,
            response_class=JSONResponse,
            operation_id=f"{factory.operation_prefix}validate",
        )
        def validate(
            src_path=Depends(factory.path_dependency),
            strict: Annotated[
                bool,
                Query(description="Treat warnings as errors"),
            ] = False,
        ):
            """Validate a COG"""
            return cog_info(src_path, strict=strict)
