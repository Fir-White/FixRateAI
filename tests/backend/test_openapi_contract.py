"""Schema HTTP checks without PostgreSQL lifespan or mocked business handlers."""
import warnings

from fastapi.testclient import TestClient

from app.main import create_app


def openapi_document():
    # Without the client context, schema delivery needs no PostgreSQL lifespan.
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        response = TestClient(create_app()).get("/openapi.json")
    assert response.status_code == 200
    assert not any("Duplicate Operation ID" in str(item.message) for item in captured)
    return response.json()


def test_published_openapi_has_globally_unique_operation_ids():
    document = openapi_document()
    operations = [operation for path in document["paths"].values()
                  for method, operation in path.items()
                  if method in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}]
    identifiers = [operation["operationId"] for operation in operations]
    assert identifiers and len(identifiers) == len(set(identifiers))


def without_schema_titles(value):
    # FastAPI derives presentation titles from each operation ID. They are
    # annotations; property names, types, references and constraints must match.
    if isinstance(value, dict):
        return {key: without_schema_titles(item) for key, item in value.items()
                if not (key == "title" and isinstance(item, str))}
    if isinstance(value, list):
        return [without_schema_titles(item) for item in value]
    return value


def test_job_aliases_keep_equivalent_input_and_response_schemas():
    paths = openapi_document()["paths"]
    for suffix, methods in [("", ("get", "post")), ("/{job_id}", ("get", "patch")),
                            ("/{job_id}/transitions", ("post",)), ("/{job_id}/history", ("get",))]:
        for method in methods:
            canonical = paths["/api/v1/maintenance_jobs" + suffix][method]
            alias = paths["/api/v1/maintenance/jobs" + suffix][method]
            assert canonical["operationId"] != alias["operationId"]
            for key in ("parameters", "requestBody", "responses"):
                assert without_schema_titles(canonical.get(key)) == without_schema_titles(alias.get(key))
