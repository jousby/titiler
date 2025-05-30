"""Test TiTiler mosaic Factory."""

import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional
from unittest.mock import patch

import attr
import morecantile
import numpy
from cogeo_mosaic.backends import FileBackend
from cogeo_mosaic.mosaic import MosaicJSON
from fastapi import FastAPI, Query
from rio_tiler.mosaic.methods import PixelSelectionMethod
from starlette.testclient import TestClient
from typing_extensions import Annotated

from titiler.core.dependencies import DefaultDependency
from titiler.core.resources.enums import OptionalHeader
from titiler.mosaic.factory import MosaicTilerFactory

from .conftest import DATA_DIR

assets = [os.path.join(DATA_DIR, asset) for asset in ["cog1.tif", "cog2.tif"]]
DEFAULT_TMS = morecantile.tms
NB_DEFAULT_TMS = len(DEFAULT_TMS.list())


@contextmanager
def tmpmosaic():
    """Create a Temporary MosaicJSON file."""
    fileobj = tempfile.NamedTemporaryFile(suffix=".json.gz", delete=False)
    fileobj.close()
    mosaic_def = MosaicJSON.from_urls(assets)
    with FileBackend(fileobj.name, mosaic_def=mosaic_def) as mosaic:
        mosaic.write(overwrite=True)

    try:
        yield fileobj.name
    finally:
        os.remove(fileobj.name)


def test_MosaicTilerFactory():
    """Test MosaicTilerFactory class."""
    mosaic = MosaicTilerFactory(
        optional_headers=[OptionalHeader.x_assets],
        router_prefix="mosaic",
    )
    assert len(mosaic.router.routes) == 18

    app = FastAPI()
    app.include_router(mosaic.router, prefix="/mosaic")
    client = TestClient(app)

    response = client.get("/openapi.json")
    assert response.status_code == 200

    response = client.get("/docs")
    assert response.status_code == 200

    with tmpmosaic() as mosaic_file:
        response = client.get(
            "/mosaic/",
            params={"url": mosaic_file},
        )
        assert response.status_code == 200
        assert response.json()["mosaicjson"]

        response = client.get(
            "/mosaic",
            params={"url": mosaic_file},
        )
        assert response.status_code == 200
        assert response.json()["mosaicjson"]

        response = client.get(
            "/mosaic/bounds",
            params={"url": mosaic_file},
        )
        assert response.status_code == 200
        assert len(response.json()["bounds"]) == 4
        assert response.json()["crs"]

        response = client.get(
            "/mosaic/info",
            params={"url": mosaic_file},
        )
        assert response.status_code == 200
        assert response.json()["bounds"]

        response = client.get(
            "/mosaic/info.geojson",
            params={"url": mosaic_file},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/geo+json"
        assert response.json()["type"] == "Feature"

        response = client.get(
            "/mosaic/point/-74.53125,45.9956935",
            params={"url": mosaic_file},
        )
        assert response.status_code == 200
        assert response.json()["coordinates"]
        v = response.json()["values"]
        assert len(v) == 1
        values = v[0][1]
        assert len(values) == 3
        assert values[0]

        # Masked values
        response = client.get(
            "/mosaic/point/-75.759,46.3847",
            params={"url": mosaic_file},
        )
        assert response.status_code == 200
        assert response.json()["coordinates"]
        v = response.json()["values"]
        assert len(v) == 1
        values = v[0][1]
        assert len(values) == 3
        assert values[0] is None

        response = client.get(
            "/mosaic/point/-7903683.846322423,5780349.220256353",
            params={"url": mosaic_file, "coord_crs": "epsg:3857"},
        )
        assert response.status_code == 200

        response = client.get(
            "/mosaic/tiles/WebMercatorQuad/7/37/45", params={"url": mosaic_file}
        )
        assert response.status_code == 200
        assert response.headers["X-Assets"]

        response = client.get(
            "/mosaic/tiles/WGS1984Quad/8/148/61", params={"url": mosaic_file}
        )
        assert response.status_code == 200
        assert response.headers["X-Assets"]

        # Buffer
        response = client.get(
            "/mosaic/tiles/WebMercatorQuad/7/37/45.npy",
            params={"url": mosaic_file, "buffer": 10},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-binary"
        npy_tile = numpy.load(BytesIO(response.content))
        assert npy_tile.shape == (4, 276, 276)  # mask + data

        response = client.get(
            "/mosaic/WebMercatorQuad/tilejson.json",
            params={
                "url": mosaic_file,
                "tile_format": "png",
                "minzoom": 6,
                "maxzoom": 9,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert (
            "http://testserver/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}@1x.png?url="
            in body["tiles"][0]
        )
        assert body["minzoom"] == 6
        assert body["maxzoom"] == 9

        response = client.get(
            "/mosaic/WebMercatorQuad/tilejson.json",
            params={
                "url": mosaic_file,
                "tile_format": "png",
                "minzoom": 6,
                "maxzoom": 9,
                "tileMatrixSetId": "WebMercatorQuad",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert (
            "http://testserver/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}@1x.png?url="
            in body["tiles"][0]
        )
        assert body["minzoom"] == 6
        assert body["maxzoom"] == 9
        assert "tileMatrixSetId" not in body["tiles"][0]

        response = client.get(
            "/mosaic/WebMercatorQuad/WMTSCapabilities.xml",
            params={
                "url": mosaic_file,
                "tile_format": "png",
                "minzoom": 6,
                "maxzoom": 9,
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/xml"

        response = client.post(
            "/mosaic/validate",
            json=MosaicJSON.from_urls(assets).model_dump(),
        )
        assert response.status_code == 200

        response = client.get(
            "/mosaic/tiles/WebMercatorQuad/7/36/45/assets",
            params={"url": mosaic_file},
        )
        assert response.status_code == 200
        assert all(
            filepath.split("/")[-1] in ["cog1.tif"] for filepath in response.json()
        )

        response = client.get(
            "/mosaic/tiles/WGS1984Quad/8/148/61/assets",
            params={"url": mosaic_file},
        )
        assert response.status_code == 200
        assert all(
            filepath.split("/")[-1] in ["cog1.tif", "cog2.tif"]
            for filepath in response.json()
        )

        response = client.get(
            "/mosaic/point/-71,46/assets", params={"url": mosaic_file}
        )
        assert response.status_code == 200
        assert all(
            filepath.split("/")[-1] in ["cog1.tif", "cog2.tif"]
            for filepath in response.json()
        )

        response = client.get(
            "/mosaic/point/-7903683.846322423,5780349.220256353/assets",
            params={"url": mosaic_file, "coord_crs": "epsg:3857"},
        )
        assert response.status_code == 200
        assert all(
            filepath.split("/")[-1] in ["cog1.tif", "cog2.tif"]
            for filepath in response.json()
        )

        response = client.get(
            "/mosaic/bbox/-75.9375,43.06888777416962,-73.125,45.089035564831015/assets",
            params={"url": mosaic_file},
        )
        assert response.status_code == 200
        assert all(
            filepath.split("/")[-1] in ["cog1.tif", "cog2.tif"]
            for filepath in response.json()
        )

        response = client.get(
            "/mosaic/bbox/-8453323.83211421,5322463.153553393,-8140237.76425813,5635549.221409473/assets",
            params={"url": mosaic_file, "coord_crs": "epsg:3857"},
        )
        assert response.status_code == 200
        assert all(
            filepath.split("/")[-1] in ["cog1.tif", "cog2.tif"]
            for filepath in response.json()
        )

        response = client.get(
            "/mosaic/bbox/10,10,11,11/assets",
            params={"url": mosaic_file},
        )
        assert response.status_code == 200
        assert response.json() == []

        # OGC Tileset
        response = client.get(f"/mosaic/tiles?url={mosaic_file}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        resp = response.json()
        assert len(resp["tilesets"]) == NB_DEFAULT_TMS

        first_tms = resp["tilesets"][0]
        first_id = DEFAULT_TMS.list()[0]
        assert first_id in first_tms["title"]
        assert len(first_tms["links"]) == 2  # no link to the tms definition

        response = client.get(f"/mosaic/tiles/WebMercatorQuad?url={mosaic_file}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        resp = response.json()
        # covers only 3 zoom levels
        assert len(resp["tileMatrixSetLimits"]) == 3


@dataclass
class BackendParams(DefaultDependency):
    """Backend options to overwrite min/max zoom."""

    minzoom: int = 4
    maxzoom: int = 8


def test_MosaicTilerFactory_BackendParams():
    """Test MosaicTilerFactory factory with Backend dependency."""
    mosaic = MosaicTilerFactory(
        backend=FileBackend,
        backend_dependency=BackendParams,
        router_prefix="/mosaic",
    )
    app = FastAPI()
    app.include_router(mosaic.router, prefix="/mosaic")
    client = TestClient(app)

    with tmpmosaic() as mosaic_file:
        response = client.get(
            "/mosaic/WebMercatorQuad/tilejson.json",
            params={"url": mosaic_file},
        )
        assert response.json()["minzoom"] == 4
        assert response.json()["maxzoom"] == 8


def _multiply_by_two(data, mask):
    mask.fill(255)
    data = data * 2
    return data, mask


def test_MosaicTilerFactory_PixelSelectionParams():
    """Test MosaicTilerFactory factory with a customized default PixelSelectionMethod."""
    mosaic = MosaicTilerFactory(router_prefix="/mosaic")
    mosaic_highest = MosaicTilerFactory(
        pixel_selection_dependency=lambda: PixelSelectionMethod.highest.value,
        router_prefix="/mosaic_highest",
    )

    app = FastAPI()
    app.include_router(mosaic.router, prefix="/mosaic")
    app.include_router(mosaic_highest.router, prefix="/mosaic_highest")
    client = TestClient(app)

    with tmpmosaic() as mosaic_file:
        response = client.get(
            "/mosaic/tiles/WebMercatorQuad/7/37/45.npy", params={"url": mosaic_file}
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-binary"
        npy_tile = numpy.load(BytesIO(response.content))
        assert npy_tile.shape == (4, 256, 256)  # mask + data

        response = client.get(
            "/mosaic_highest/tiles/WebMercatorQuad/7/37/45.npy",
            params={"url": mosaic_file},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-binary"
        npy_tile_highest = numpy.load(BytesIO(response.content))
        assert npy_tile_highest.shape == (4, 256, 256)  # mask + data

        assert (npy_tile != npy_tile_highest).any()


@patch("titiler.mosaic.factory.MOSAIC_STRICT_ZOOM", new=True)
def test_MosaicTilerFactory_strict_zoom():
    """Test MosaicTilerFactory factory with STRICT Zoom Mode"""
    mosaic = MosaicTilerFactory()
    app = FastAPI()
    app.include_router(mosaic.router)

    with TestClient(app) as client:
        with tmpmosaic() as mosaic_file:
            response = client.get(
                "/tiles/WebMercatorQuad/7/37/45.png", params={"url": mosaic_file}
            )
            assert response.status_code == 200

            response = client.get(
                "/tiles/WebMercatorQuad/6/18/22.png", params={"url": mosaic_file}
            )
            assert response.status_code == 400
            assert "Invalid ZOOM level 6" in response.text

            response = client.get(
                "/tiles/WebMercatorQuad/11/594/734.png", params={"url": mosaic_file}
            )
            assert response.status_code == 400
            assert "Invalid ZOOM level 11" in response.text


@dataclass
class AssetsAccessParams(DefaultDependency):
    """Backend options to overwrite min/max zoom."""

    limit: Annotated[int, Query()] = 10


@attr.s
class CustomBackend(FileBackend):
    """Custom FileBackend."""

    def get_assets(
        self, x: int, y: int, z: int, limit: Optional[int] = None
    ) -> List[str]:
        """Find assets."""
        assets = super().get_assets(x, y, z)

        if limit and len(assets) > limit:
            return assets[:limit]

        return assets


def test_MosaicTilerFactory_asset_accessor():
    """Test MosaicTilerFactory factory with Backend dependency."""
    mosaic = MosaicTilerFactory(
        backend=CustomBackend,
        router_prefix="/mosaic",
        assets_accessor_dependency=AssetsAccessParams,
    )
    app = FastAPI()
    app.include_router(mosaic.router, prefix="/mosaic")
    client = TestClient(app)

    with tmpmosaic() as mosaic_file:
        response = client.get(
            "/mosaic/tiles/WGS1984Quad/8/148/61/assets",
            params={"url": mosaic_file},
        )
        assert response.status_code == 200
        assert len(response.json()) == 2

        response = client.get(
            "/mosaic/tiles/WGS1984Quad/8/148/61/assets",
            params={"url": mosaic_file, "limit": 1},
        )
        assert response.status_code == 200
        assert len(response.json()) == 1
