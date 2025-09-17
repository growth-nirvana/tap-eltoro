"""REST client handling, including ElToroStream base class."""

from __future__ import annotations

import decimal
import random
import sys
import time
import typing as t
from functools import cached_property
from importlib import resources

import requests
from singer_sdk.exceptions import RetriableAPIError
from singer_sdk.helpers.jsonpath import extract_jsonpath
from singer_sdk.pagination import BaseAPIPaginator  # noqa: TC002
from singer_sdk.streams import RESTStream

from tap_eltoro.auth import ElToroAuthenticator

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if t.TYPE_CHECKING:
    from singer_sdk.helpers.types import Auth, Context


# TODO: Delete this is if not using json files for schema definition
SCHEMAS_DIR = resources.files(__package__) / "schemas"


class ElToroStream(RESTStream):
    """ElToro stream class."""

    # Update this value if necessary or override `parse_response`.
    records_jsonpath = "$[*]"

    # Update this value if necessary or override `get_new_paginator`.
    next_page_token_jsonpath = "$.next_page"  # noqa: S105

    @override
    @property
    def url_base(self) -> str:
        """Return the API URL root, configurable via tap settings."""
        base_url = self.config.get("base_url")
        if base_url:
            return base_url
        
        # Default URLs based on environment
        environment = self.config.get("environment", "production")
        if environment == "development":
            return "https://platform.api.dev.eltoro.com"
        else:
            return "https://platform.api.eltoro.com"

    @override
    @cached_property
    def authenticator(self) -> Auth:
        """Return a new authenticator object.

        Returns:
            An authenticator instance.
        """
        return ElToroAuthenticator(
            client_id=self.config["client_id"],
            client_secret=self.config["client_secret"],
            auth_endpoint="https://auth.api.eltoro.com/auth/realms/eltoro/protocol/openid-connect/token",
            oauth_scopes=self.config.get("scope", ""),
        )

    @property
    @override
    def http_headers(self) -> dict:
        """Return the http headers needed.

        Returns:
            A dictionary of HTTP headers.
        """
        headers = {
            "AUTHORIZATION": f"Bearer {self.authenticator.access_token}",
            "ACCEPT": "application/json",
            "CONTENT-TYPE": "application/json",
        }
        
        # Add custom user agent if specified
        if self.config.get("user_agent"):
            headers["USER-AGENT"] = self.config["user_agent"]
            
        return headers

    def _make_request_with_retries(
        self, 
        prepared_request: requests.PreparedRequest, 
        context: Context | None
    ) -> requests.Response:
        """Make HTTP request with retry logic and error handling."""
        max_retries = self.config.get("max_retries", 3)
        backoff_base = self.config.get("retry_backoff_base", 2.0)
        
        for attempt in range(max_retries + 1):
            try:
                response = self.requests_session.send(
                    prepared_request,
                    timeout=self.timeout,
                )
                
                # Handle 401 - refresh token and retry once
                if response.status_code == 401 and attempt == 0:
                    self.logger.info("Received 401, refreshing access token...")
                    self.authenticator.update_access_token()
                    # Update authorization header with new token
                    prepared_request.headers["AUTHORIZATION"] = f"Bearer {self.authenticator.access_token}"
                    continue
                
                # Handle rate limiting (429) and server errors (5xx)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < max_retries:
                        # Calculate backoff delay with jitter
                        delay = (backoff_base ** attempt) + random.uniform(0, 1)
                        self.logger.warning(
                            f"Request failed with status {response.status_code}. "
                            f"Retrying in {delay:.2f} seconds... (attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        raise RetriableAPIError(
                            f"Request failed after {max_retries + 1} attempts with status {response.status_code}"
                        )
                
                return response
                
            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    delay = (backoff_base ** attempt) + random.uniform(0, 1)
                    self.logger.warning(
                        f"Request failed with exception: {e}. "
                        f"Retrying in {delay:.2f} seconds... (attempt {attempt + 1}/{max_retries + 1})"
                    )
                    time.sleep(delay)
                    continue
                else:
                    raise
        
        return response

    @override
    def request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        **kwargs,
    ) -> requests.Response:
        """Make an HTTP request with authentication and retry logic."""
        # Prepare the request
        prepared_request = self.requests_session.prepare_request(
            requests.Request(
                method=method,
                url=url,
                params=params,
                headers={**self.http_headers, **(headers or {})},
                **kwargs,
            )
        )
        
        # Make request with retries
        return self._make_request_with_retries(prepared_request, None)

    @override
    @property
    def timeout(self) -> int:
        """Return request timeout from config."""
        return self.config.get("request_timeout", 60)

    @override
    def get_new_paginator(self) -> BaseAPIPaginator | None:
        """Create a new pagination helper instance.

        If the source API can make use of the `next_page_token_jsonpath`
        attribute, or it contains a `X-Next-Page` header in the response
        then you can remove this method.

        If you need custom pagination that uses page numbers, "next" links, or
        other approaches, please read the guide: https://sdk.meltano.com/en/v0.25.0/guides/pagination-classes.html.

        Returns:
            A pagination helper instance, or ``None`` to indicate pagination
            is not supported.
        """
        return super().get_new_paginator()

    @override
    def get_url_params(
        self,
        context: Context | None,
        next_page_token: t.Any | None,
    ) -> dict[str, t.Any]:
        """Return a dictionary of values to be used in URL parameterization.

        Args:
            context: The stream context.
            next_page_token: The next page index or value.

        Returns:
            A dictionary of URL query parameters.
        """
        params: dict = {}
        if next_page_token:
            params["page"] = next_page_token
        if self.replication_key:
            params["sort"] = "asc"
            params["order_by"] = self.replication_key
        return params

    @override
    def prepare_request_payload(
        self,
        context: Context | None,
        next_page_token: t.Any | None,
    ) -> dict | None:
        """Prepare the data payload for the REST API request.

        By default, no payload will be sent (return None).

        Args:
            context: The stream context.
            next_page_token: The next page index or value.

        Returns:
            A dictionary with the JSON body for a POST requests.
        """
        # TODO: Delete this method if no payload is required. (Most REST APIs.)
        return None

    @override
    def parse_response(self, response: requests.Response) -> t.Iterable[dict]:
        """Parse the response and return an iterator of result records.

        Args:
            response: The HTTP ``requests.Response`` object.

        Yields:
            Each record from the source.
        """
        # TODO: Parse response body and return a set of records.
        yield from extract_jsonpath(
            self.records_jsonpath,
            input=response.json(parse_float=decimal.Decimal),
        )

    @override
    def post_process(
        self,
        row: dict,
        context: Context | None = None,
    ) -> dict | None:
        """As needed, append or transform raw data to match expected structure.

        Note: As of SDK v0.47.0, this method is automatically executed for all stream types.
        You should not need to call this method directly in custom `get_records` implementations.

        Args:
            row: An individual record from the stream.
            context: The stream context.

        Returns:
            The updated record dictionary, or ``None`` to skip the record.
        """
        # TODO: Delete this method if not needed.
        return row
