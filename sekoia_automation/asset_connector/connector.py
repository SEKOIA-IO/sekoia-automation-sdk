import time
from abc import abstractmethod
from collections.abc import Generator
from functools import cached_property

import requests
from requests import Response

from sekoia_automation.exceptions import (
    AssetConnectorRateLimitError,
)

from .mixin import AssetConnectorBase
from .models.connector import AssetItem, AssetList
from .utils import (
    TASK_PENDING_STATUSES,
    parse_retry_after,
    pop_refused_item,
    push_429_message,
    push_error_message,
)


class AssetConnector(AssetConnectorBase):
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

        while True:
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
                    message="Timeout while pushing assets "
                    "to Sekoia.io asset connector API",
                )
                return None

            if res.status_code != 413:
                break

            refused_item = pop_refused_item(res.text, asset_items)
            if refused_item is None:
                break

            self.log(message=refused_item, level="error")
            if not asset_items:
                self.update_checkpoint()
                return {}

        if res.status_code == 429:
            retry_after = parse_retry_after(
                res.headers.get("Retry-After"), self.rate_limit_wait
            )
            self.log(
                message=push_429_message(res.text, retry_after),
                level="warning",
            )
            raise AssetConnectorRateLimitError(retry_after=retry_after)

        if res.status_code != 200:
            self.log(
                message=push_error_message(
                    self.handle_api_error(res.status_code), res.text
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

    def wait_for_push_task(self, task_id: str) -> None:
        """
        Poll the Task API until an asset push task reaches a terminal status.

        The platform ingests pushed assets asynchronously and tracks that work
        with a task. Waiting for it tells us whether the assets really landed
        on Sekoia.io instead of merely being accepted by the API.

        The outcome is only reported: the checkpoint has already been updated
        by the push itself, so a failed task does not trigger a re-push.

        Args:
            task_id (str): UUID of the task returned by the push endpoint.
        """
        if self._skip_task_wait:
            return

        url = f"{self.task_endpoint}/{task_id}"
        deadline = time.time() + self.task_poll_timeout
        # Most tasks complete in about a second: poll fast first, then back off
        # to the configured interval so a slow platform is not hammered.
        interval = min(1.0, self.task_poll_interval)

        while self.running:
            try:
                res: Response = self._http_session.get(url, timeout=30)
            except requests.RequestException as ex:
                self.log_exception(
                    ex,
                    message=f"Unable to get the status of the asset push task "
                    f"{task_id}",
                )
                self._disable_task_wait()
                return

            if res.status_code != 200:
                self.log(
                    message=(
                        f"Unable to get the status of the asset push task {task_id} "
                        f"- {self.handle_api_error(res.status_code)}"
                    ),
                    level="error",
                )
                self._disable_task_wait()
                return

            task = res.json()
            status = task.get("status")

            if status not in TASK_PENDING_STATUSES:
                self._log_task_outcome(task_id, task, status)
                return

            if time.time() >= deadline:
                self.log(
                    message=(
                        f"Asset push task {task_id} is still {status} after "
                        f"{self.task_poll_timeout} seconds. Not waiting for the "
                        f"push tasks of the remaining batches of this cycle"
                    ),
                    level="warning",
                )
                self._disable_task_wait()
                return

            self._stop_event.wait(interval)
            interval = min(interval * 2, self.task_poll_interval)

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

        # The push endpoint returns the task tracking the ingestion of the assets.
        # Older platforms - and pushes the platform could not create a task for -
        # return nothing: there is then nothing to wait for.
        if task_id := response.get("task_id"):
            self.wait_for_push_task(task_id)

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
        """Reset the checkpoint when the declared field mappings changed.

        When a difference is detected the checkpoint is reset via
        :meth:`reset_checkpoint` so that the next fetch cycle re-collects all
        assets with the updated mapping.  Both the new fingerprint and the
        full field mapping dict are persisted to ``asset_schema_fields.json``.

        On the very first run (no fingerprint stored yet) the data is saved
        without triggering a reset.
        """
        change = self._detect_schema_change()
        if change is None:
            return

        current_fields, reset_needed = change
        if reset_needed:
            self.reset_checkpoint()

        # Persist the schema before scheduling the jitter: if the connector
        # crashes in between, the next start must not detect the same change
        # again, reset the checkpoint a second time and restart the wait.
        self._save_schema(current_fields)

        if reset_needed:
            self._schedule_reset_jitter()

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

    def _pause_between_batches(self) -> None:
        """
        Wait the configured inter-batch interval before the next batch push.

        The wait ends as soon as the connector is stopped. The cycle is not
        abandoned for all that: the assets already fetched still have to be
        pushed, otherwise they would be lost while the checkpoint may already
        have moved past them. The remaining batches are pushed without pause.
        """
        interval = self.batch_push_interval
        if interval > 0:
            self._stop_event.wait(interval)

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

        # Waiting for push tasks is a per-cycle privilege: it is given back on
        # every cycle and withdrawn as soon as the platform stops answering.
        self._skip_task_wait = False

        self._check_schema_and_reset_if_needed()

        # If a checkpoint reset was scheduled, wait out the jitter before
        # starting the full re-fetch. This spreads the burst across all
        # configurations of the same connector.
        pending = self._pending_reset_jitter_seconds()
        if pending > 0:
            self.log(
                message=(
                    f"Waiting {pending:.0f}s before the post-reset "
                    "full fetch (reset jitter)."
                ),
                level="info",
            )
            if not self._wait_reset_jitter(pending):
                return
        self._clear_reset_jitter()

        # save the starting time processing
        processing_start = time.time()

        assets = []
        total_number_of_assets = 0
        pushed_batches = 0
        for asset in self.get_assets():
            assets.append(asset)
            total_number_of_assets += 1

            if len(assets) >= self.batch_size:
                if pushed_batches:
                    self._pause_between_batches()
                batch = AssetList(version=self.OCSF_SCHEMA_VERSION, items=assets)
                self.push_assets_to_sekoia(batch)
                pushed_batches += 1
                assets = []

        if assets:
            if pushed_batches:
                self._pause_between_batches()
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
