import time
from abc import abstractmethod
from collections.abc import Generator
from functools import cached_property

import requests
from requests import Response

from sekoia_automation.exceptions import AssetConnectorRateLimitError

from .mixin import AssetConnectorMixin
from .models.connector import AssetItem, AssetList
from .utils import parse_retry_after


class AssetConnector(AssetConnectorMixin):
    """
    Base class for all asset connectors.

    Asset connectors are used to collect data from
    an asset and send it to the Sekoia.io platform.
    """

    @cached_property
    def _http_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(self._http_header)
        return session

    def post_assets_to_api(
        self, assets: AssetList, asset_connector_api_url: str
    ) -> dict[str, str] | None:
        """
        Post assets to the Sekoia.io asset connector API.
        Args:
            assets (AssetList): List of assets to post.
            asset_connector_api_url (str): URL of the asset connector API.
        Returns:
            dict[str, str] | None: Response from the API or None if an error occurred.
        """

        # Serialize the assets to a dictionary
        assets_object_to_dict = assets.model_dump(exclude_none=True)
        asset_items = assets_object_to_dict.get("items", [])

        request_body = assets_object_to_dict

        try:
            for attempt in self._retry():
                with attempt:
                    res: Response = self._http_session.post(
                        asset_connector_api_url,
                        json=request_body,
                        timeout=30,
                    )
        except requests.Timeout as ex:
            self.log_exception(
                ex,
                message="Timeout while pushing assets to Sekoia.io asset connector API",
            )
            return None

        if res.status_code == 429:
            retry_after = parse_retry_after(
                res.headers.get("Retry-After"), self.rate_limit_wait
            )
            self.log(
                message=(
                    "Asset connector push rate limited (HTTP 429). "
                    f"Waiting {retry_after} seconds before refetching."
                ),
                level="warning",
            )
            raise AssetConnectorRateLimitError(retry_after=retry_after)

        if res.status_code != 200:
            error_message = self.handle_api_error(res.status_code)
            # In case the response body is empty or not a json
            if res:
                error_response = res.json()
                error_message = error_response.get("message", "")
                error_code = error_response.get("code", "")
                body_message = f" - {error_code} : {error_message}"
            else:
                body_message = res.text or ""

            self.log(
                message=(
                    "Error while pushing assets to Sekoia.io "
                    f"- {error_message} : {body_message}"
                ),
                level="error",
            )
            return None

        self.update_checkpoint()

        self.log(
            message=f"Successfully posted {len(asset_items)} assets "
            f"to Sekoia.io asset connector API",
            level="info",
        )
        return res.json()

    def push_assets_to_sekoia(self, assets: AssetList) -> None:
        """
        Push assets to the Sekoia.io asset connector API.
        Args:
            assets (AssetList): List of assets to push.
        Returns:
            None: If the assets were successfully pushed.
        """

        if not assets:
            return

        url = self.asset_connector_endpoint

        self.log(
            message=f"Pushing assets to Sekoia.io asset connector API at {url}",
            level="info",
        )

        response = self.post_assets_to_api(
            assets=assets,
            asset_connector_api_url=url,
        )

        if response is None:
            self.log(
                message=f"Failed to push assets to Sekoia.io "
                f"asset connector API at {url}",
                level="error",
            )
            return

    @abstractmethod
    def update_checkpoint(self) -> None:
        """
        Update the checkpoint for the connector.
        This method should be implemented in the subclass.
        """
        raise NotImplementedError("This method should be implemented in a subclass")

    @abstractmethod
    def reset_checkpoint(self) -> None:
        """
        Reset the checkpoint so all assets will be re-fetched from scratch.

        Default no-op for backward compatibility: subclasses that declare field
        mappings (via :meth:`get_mapped_fields`) should override this to clear
        their checkpoint. If a mapping change is detected but this is not
        overridden, a warning is logged and no reset happens.
        """
        raise NotImplementedError(
            "reset_checkpoint must be implemented to support schema-change refetching"
        )

    def _check_schema_and_reset_if_needed(self) -> None:
        """Compare the current field-mapping fingerprint against the stored one.

        When a difference is detected the checkpoint is reset via
        :meth:`reset_checkpoint` so that the next fetch cycle re-collects all
        assets with the updated mapping.  Both the new fingerprint and the
        full field mapping dict are persisted to ``asset_schema_fields.json``.

        On the very first run (no fingerprint stored yet) the data is saved
        without triggering a reset.
        """
        current_fields = self.get_mapped_fields()
        # No declared mapping (default for connectors that don't override
        # get_mapped_fields): schema-change detection is inert, skip entirely.
        if not current_fields:
            return

        current_fingerprint = self._compute_schema_fingerprint()

        with self.schema_store as store:
            stored_fingerprint = store.get("fingerprint")
            stored_fields: dict[str, str] = store.get("fields", {})

        if stored_fingerprint == current_fingerprint:
            return

        if stored_fingerprint is not None:
            diff = {
                "added": {
                    k: v for k, v in current_fields.items() if k not in stored_fields
                },
                "removed": {
                    k: v for k, v in stored_fields.items() if k not in current_fields
                },
                "changed": {
                    k: {"from": stored_fields[k], "to": v}
                    for k, v in current_fields.items()
                    if k in stored_fields and stored_fields[k] != v
                },
            }
            self.log(
                message=(
                    "Field mapping change detected — "
                    f"{diff}. Resetting checkpoint to re-fetch all assets."
                ),
                level="info",
            )
            self.reset_checkpoint()

        with self.schema_store as store:
            store["fingerprint"] = current_fingerprint
            store["fields"] = current_fields

    @abstractmethod
    def get_assets(
        self,
    ) -> Generator[AssetItem, None, None]:
        """
        Get assets from the connector.
        It can be a Device, User, Software or a vulnerability asset.
        Yields:
            AssetItem: Asset item ( DeviceOSCFModel, UserOCSFModel, etc. )
        """
        raise NotImplementedError("This method should be implemented in a subclass")

    def asset_fetch_cycle(self) -> None:
        """
        Continuously fetch assets from the connector and push them to Sekoia.io.

        This method runs in a loop until the connector is stopped. On each cycle, it:
          1. Retrieves assets from the connector.
          2. Batches the retrieved assets.
          3. Sends the batch to Sekoia.io.
          4. Waits for the next cycle according to the configured frequency.

        If no assets are fetched during a cycle, the method sleeps for a short
        interval to avoid overwhelming the API with repeated requests.

        Note:
            This implementation assumes the connector provides a checkpointing
            mechanism to prevent re-fetching the same assets.
        """

        self.log(
            message=f"Starting a new asset fetch cycle "
            f"for connector {self.connector_name}",
            level="info",
        )

        self._check_schema_and_reset_if_needed()

        # save the starting time processing
        processing_start = time.time()

        assets = []
        total_number_of_assets = 0
        for asset in self.get_assets():
            assets.append(asset)
            total_number_of_assets += 1

            if len(assets) >= self.batch_size:
                batch = AssetList(version=self.OCSF_SCHEMA_VERSION, items=assets)
                self.push_assets_to_sekoia(batch)
                assets = []

        if assets:
            final_batch = AssetList(version=self.OCSF_SCHEMA_VERSION, items=assets)
            self.push_assets_to_sekoia(final_batch)

        # save the end time processing
        processing_end = time.time()
        processing_time = processing_end - processing_start

        # Compute the remaining sleeping time.
        # If greater than 0 and no messages where fetched, pause the connector
        delta_sleep = self.frequency - processing_time
        if total_number_of_assets == 0 and delta_sleep > 0:
            self.log(message=f"Next run in the future. Waiting {delta_sleep} seconds")

            time.sleep(delta_sleep)

    def run(self) -> None:
        while self.running:
            try:
                self.asset_fetch_cycle()
            except AssetConnectorRateLimitError as e:
                self.log(
                    message=f"Rate limit hit, pausing connector "
                    f"for {e.retry_after} seconds",
                    level="warning",
                )
                self._stop_event.wait(e.retry_after)
            except Exception as e:
                self.log_exception(
                    e,
                    message=f"Error while running asset connector "
                    f"{self.connector_name}",
                )
