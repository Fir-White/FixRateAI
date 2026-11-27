import gzip
from contextlib import closing

from fastapi.testclient import TestClient

from app.main import create_app


def test_precompressed_assets_negotiate_without_changing_identity_or_ranges(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    compressed = tmp_path / "compressed"
    compressed.mkdir()
    name = "index-23456789.js"
    source = b"export const data = ['item'];\n" * 300
    (assets / name).write_bytes(source)
    packed = gzip.compress(source)
    (compressed / f"{name}.gz").write_bytes(packed)

    with closing(TestClient(create_app(frontend_dist=tmp_path))) as client:
        url = f"/assets/{name}"
        body = client.get(url, headers={"Accept-Encoding": "gzip"})
        assert body.status_code == 200
        assert body.content == source
        assert body.headers["content-encoding"] == "gzip"
        assert int(body.headers["content-length"]) == len(packed)
        assert body.headers["content-type"].startswith("text/javascript")
        assert body.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert body.headers["vary"] == "Accept-Encoding"

        plain = client.get(url, headers={"Accept-Encoding": "gzip;q=0, br"})
        assert plain.content == source and "content-encoding" not in plain.headers
        assert plain.headers["vary"] == "Accept-Encoding"
        assert plain.headers["etag"] != body.headers["etag"]
        revalidated = client.get(url, headers={"Accept-Encoding": "gzip", "If-None-Match": body.headers["etag"]})
        assert revalidated.status_code == 304
        assert revalidated.headers["vary"] == "Accept-Encoding"
        partial = client.get(url, headers={"Accept-Encoding": "gzip", "Range": "bytes=0-5"})
        assert partial.status_code == 206
        assert partial.content == source[:6] and "content-encoding" not in partial.headers
