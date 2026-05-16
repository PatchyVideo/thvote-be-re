import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import OperationalError


def test_lifespan_raises_on_db_failure():
    """Startup must raise RuntimeError if the DB is unreachable."""
    from src.main import create_app
    from starlette.testclient import TestClient

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=OperationalError("connect failed", None, None)
    )
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_maker = MagicMock(return_value=mock_session)

    with patch("src.main.get_session_maker", return_value=mock_maker):
        app = create_app()
        with pytest.raises(RuntimeError, match="Database connection failed"):
            with TestClient(app):
                pass
