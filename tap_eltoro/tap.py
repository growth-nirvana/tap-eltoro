"""ElToro tap class."""

from __future__ import annotations

import sys

from singer_sdk import Tap
from singer_sdk import typing as th  # JSON schema typing helpers

# TODO: Import your custom stream types here:
from tap_eltoro import streams

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class TapElToro(Tap):
    """ElToro tap class."""

    name = "tap-eltoro"

    config_jsonschema = th.PropertiesList(
        th.Property(
            "environment",
            th.StringType(nullable=False),
            required=True,
            title="Environment",
            description="The environment to connect to (development or production)",
            allowed_values=["development", "production"],
        ),
        th.Property(
            "client_id",
            th.StringType(nullable=False),
            required=True,
            secret=True,
            title="Client ID",
            description="OAuth2 Client ID for authentication",
        ),
        th.Property(
            "client_secret",
            th.StringType(nullable=False),
            required=True,
            secret=True,
            title="Client Secret",
            description="OAuth2 Client Secret for authentication",
        ),
        th.Property(
            "base_url",
            th.StringType(nullable=False),
            title="Base URL",
            description="The base URL for the API service (environment-specific)",
        ),
        th.Property(
            "org_id",
            th.StringType(nullable=True),
            title="Organization ID",
            description="El Toro Organization ID for API requests (optional - if not provided, stats will be fetched for all accessible organizations)",
        ),
        th.Property(
            "organization_ids",
            th.ArrayType(th.StringType()),
            title="Organization IDs",
            description="List of specific Organization IDs to fetch stats for (optional - if not provided, stats will be fetched for all accessible organizations)",
        ),
        th.Property(
            "scope",
            th.StringType(nullable=True),
            title="OAuth2 Scope",
            description="Optional OAuth2 scope for token requests",
        ),
        th.Property(
            "start_date",
            th.DateTimeType(nullable=True),
            description="The earliest record date to sync",
        ),
        th.Property(
            "lookback_window_days",
            th.IntegerType(nullable=True),
            default=14,
            title="Lookback Window Days",
            description="Number of days to look back from the last bookmark to ensure no data is missed",
        ),
        th.Property(
            "request_timeout",
            th.IntegerType(nullable=True),
            default=60,
            title="Request Timeout",
            description="Request timeout in seconds",
        ),
        th.Property(
            "max_retries",
            th.IntegerType(nullable=True),
            default=3,
            title="Max Retries",
            description="Maximum number of retries for failed requests",
        ),
        th.Property(
            "retry_backoff_base",
            th.NumberType(nullable=True),
            default=2.0,
            title="Retry Backoff Base",
            description="Base for exponential backoff retry delays",
        ),
        th.Property(
            "user_agent",
            th.StringType(nullable=True),
            description=(
                "A custom User-Agent header to send with each request. Default is "
                "'<tap_name>/<tap_version>'"
            ),
        ),
    ).to_dict()

    @override
    def discover_streams(self) -> list[streams.ElToroStream]:
        """Return a list of discovered streams.

        Returns:
            A list of discovered streams.
        """
        return [
            streams.OrganizationsStream(self),
            streams.StatsStream(self),
        ]


if __name__ == "__main__":
    TapElToro.cli()
