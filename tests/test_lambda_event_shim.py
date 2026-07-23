from scripts._lambda_event_shim import build_api_gateway_event_v2, lambda_response_to_http


def test_build_api_gateway_event_v2_shape():
    event = build_api_gateway_event_v2(
        "POST",
        "/orchestra",
        "foo=bar",
        {"Authorization": "Bearer token"},
        b'{"jsonrpc": "2.0"}',
    )

    assert event["version"] == "2.0"
    assert event["routeKey"] == "POST /orchestra"
    assert event["rawPath"] == "/orchestra"
    assert event["rawQueryString"] == "foo=bar"
    assert event["headers"] == {"Authorization": "Bearer token"}
    assert event["requestContext"]["http"]["method"] == "POST"
    assert event["requestContext"]["http"]["path"] == "/orchestra"
    assert event["body"] == '{"jsonrpc": "2.0"}'


def test_build_api_gateway_event_v2_handles_missing_body():
    event = build_api_gateway_event_v2("GET", "/orchestra", "", {}, None)

    assert event["body"] is None


def test_build_api_gateway_event_v2_handles_empty_body():
    event = build_api_gateway_event_v2("GET", "/orchestra", "", {}, b"")

    assert event["body"] is None


def test_lambda_response_to_http_defaults():
    status_code, headers, body = lambda_response_to_http({})

    assert status_code == 200
    assert headers == {}
    assert body == b""


def test_lambda_response_to_http_translates_response():
    status_code, headers, body = lambda_response_to_http(
        {
            "statusCode": 401,
            "headers": {"content-type": "application/json", "www-authenticate": "Bearer"},
            "body": '{"message": "nope"}',
        }
    )

    assert status_code == 401
    assert headers == {"content-type": "application/json", "www-authenticate": "Bearer"}
    assert body == b'{"message": "nope"}'
