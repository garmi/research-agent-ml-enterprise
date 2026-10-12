import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run live HTTP network queries instead of recorded cassettes.",
    )


@pytest.fixture
def is_live(request):
    return request.config.getoption("--live")
