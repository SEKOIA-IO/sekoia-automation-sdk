import asyncio
import json
import time
from abc import abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import aiohttp
from aiolimiter import AsyncLimiter

from sekoia_automation.aio.helpers import get_or_create_event_loop
from sekoia_automation.exceptions import (
    AssetConnectorPushError,
    AssetConnectorRateLimitError,
    AssetConnectorStoppedError,
)

from .mixin import AssetConnectorBase
from .models.connector import AssetItem, AssetList
from .utils import (
    REJECTED_BATCH_STATUSES,
    TASK_PENDING_STATUSES,
    parse_retry_after,
    push_429_message,
    push_error_message,
)


class AsyncAssetConnector(AssetConnectorBase):
    """
    Async base class for all asset connectors.

    Asset connectors are used to collect data from
    an asset and send it to the Sekoia.io platform.

    This async version uses AsyncGenerator for asset fetching
    and aiohttp for HTTP requests.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter: AsyncLimiter | None = None

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[aiohttp.ClientSession, None]:
        """
        Get the aiohttp session with rate limiting.

        Yields:
            aiohttp.ClientSession: The HTTP session
        """
        if self._session is None:
            self._session = aiohttp.ClientSession(headers=self._http_header)

        if self._rate_limiter:
            async with self._rate_limiter:
                yield self._session
        else:
            yield self._session

    async def post_assets_to_api(
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
        request_body = assets.model_dump(exclude_none=True)
        asset_count = len(request_body.get("items", []))

        # Perform the API request with retry logic
        status_code: int | None = None
        response_text: str | None = None
        response_json: dict | None = None
        retry_after_header: str | None = None

        try:
            for attempt in self._retry():
                with attempt:
                    async with self.session() as session:
                        async with session.post(
                            asset_connector_api_url,
                            json=request_body,
                            timeout=aiohttp.ClientTimeout(total=30),
                        ) as response:
                            status_code = response.status
                            response_text = await response.text()
                            retry_after_header = response.headers.get("Retry-After")
                            if status_code >= 500:
                                response.raise_for_status()

                            if status_code == 200:
                                try:
                                    response_json = json.loads(response_text)
                                except json.JSONDecodeError as e:
                                    self.log_exception(
                                        e,
                                        message="Failed to parse JSON response from "
                                        "Sekoia.io asset connector API",
                                    )
                                    return None
        except (aiohttp.ClientError, TimeoutError) as ex:
            if not self.running:
                raise AssetConnectorStoppedError() from ex
            if isinstance(ex, TimeoutError):
                self.log_exception(
                    ex,
                    message="Timeout while pushing assets to Sekoia.io asset "
                    "connector API",
                )
                return None
            # A server error outlasting the retries is reported with the others
            if not isinstance(ex, aiohttp.ClientResponseError):
                raise

        # Check if response was successfully obtained
        if status_code is None:
            self.log(
                message="Failed to get response from Sekoia.io asset connector API",
                level="error",
            )
            return None

        # Handle rate limiting (HTTP 429)
        if status_code == 429:
            retry_after = parse_retry_after(retry_after_header, self.rate_limit_wait)
            self.log(
                message=push_429_message(response_text, retry_after),
                level="warning",
            )
            raise AssetConnectorRateLimitError(retry_after=retry_after)

        # Handle non-200 responses
        if status_code != 200:
            await self._log_api_error(status_code, response_text)
            self._batch_rejected = status_code in REJECTED_BATCH_STATUSES
            return None

        # Update checkpoint on success
        await self.update_checkpoint()

        self.log(
            message=f"Successfully posted {asset_count} assets "
            f"to Sekoia.io asset connector API",
            level="info",
        )
        return response_json

    async def _log_api_error(self, status_code: int, response_text: str | None) -> None:
        """
        Log API error details from response.

        Args:
            status_code: HTTP status code
            response_text: Raw response text
        """
        self.log(
            message=push_error_message(
                self.handle_api_error(status_code), response_text
            ),
            level="error",
        )

    async def wait_for_push_task(self, task_id: str) -> None:
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
                async with self.session() as session:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        status_code = response.status
                        payload = await response.text()
            except (TimeoutError, aiohttp.ClientError) as ex:
                self.log_exception(
                    ex,
                    message=f"Unable to get the status of the asset push task "
                    f"{task_id}",
                )
                self._disable_task_wait()
                return

            if status_code != 200:
                self.log(
                    message=(
                        f"Unable to get the status of the asset push task {task_id} "
                        f"- {self.handle_api_error(status_code)}"
                    ),
                    level="error",
                )
                self._disable_task_wait()
                return

            try:
                task = json.loads(payload)
            except json.JSONDecodeError as ex:
                self.log_exception(
                    ex,
                    message=f"Failed to parse the status of the asset push task "
                    f"{task_id}",
                )
                self._disable_task_wait()
                return

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

            await asyncio.sleep(interval)
            interval = min(interval * 2, self.task_poll_interval)

    async def push_assets_to_sekoia(self, assets: AssetList) -> bool:
        """
        Push assets to the Sekoia.io asset connector API.
        Args:
            assets (AssetList): List of assets to push.
        Returns:
            bool: False if the assets could not be pushed.
        """

        if not assets:
            return True

        url = self.asset_connector_endpoint

        self.log(
            message=f"Pushing assets to Sekoia.io asset connector API at {url}",
            level="info",
        )

        response = await self.post_assets_to_api(
            assets=assets,
            asset_connector_api_url=url,
        )

        if response is None:
            self.log(
                message=f"Failed to push assets to Sekoia.io "
                f"asset connector API at {url}",
                level="error",
            )
            return False

        # The push endpoint returns the task tracking the ingestion of the assets.
        # Older platforms - and pushes the platform could not create a task for -
        # return nothing: there is then nothing to wait for.
        if task_id := response.get("task_id"):
            await self.wait_for_push_task(task_id)

        return True

    @abstractmethod
    async def update_checkpoint(self) -> None:
        """
        Update the checkpoint for the connector.
        This method should be implemented in the subclass.
        """
        raise NotImplementedError("This method should be implemented in a subclass")

    @abstractmethod
    async def reset_checkpoint(self) -> None:
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

    async def _check_schema_and_reset_if_needed(self) -> None:
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
            await self.reset_checkpoint()

        # Persist the schema before scheduling the jitter: if the connector
        # crashes in between, the next start must not detect the same change
        # again, reset the checkpoint a second time and restart the wait.
        self._save_schema(current_fields)

        if reset_needed:
            self._schedule_reset_jitter()

    @abstractmethod
    async def get_assets(
        self,
    ) -> AsyncGenerator[AssetItem, None]:
        """
        Get assets from the connector.
        It can be a Device, User, Software or a vulnerability asset.
        Yields:
            AssetItem: Asset item ( DeviceOSCFModel, UserOCSFModel, etc. )
        """
        # Make this an async generator by using yield
        # This will never actually execute, but satisfies the type checker
        if False:  # pragma: no cover
            yield  # type: ignore[unreachable, misc]
        raise NotImplementedError("This method should be implemented in a subclass")

    async def _pause_between_batches(self) -> None:
        """
        Wait the configured inter-batch interval before the next batch push.

        The wait ends as soon as the connector is stopped: the batch is then not
        pushed, and the cycle raises AssetConnectorStoppedError.
        """
        interval = self.batch_push_interval
        if interval > 0:
            await asyncio.to_thread(self._stop_event.wait, interval)

    async def asset_fetch_cycle(self) -> None:
        """
        Fetch assets from the connector and push them to Sekoia.io, once.

        The cycle:
          1. Retrieves assets from the connector.
          2. Batches the retrieved assets.
          3. Sends the batch to Sekoia.io.

        Its counters are kept in `cycle_stats`.

        If the connector is stopped, the cycle raises AssetConnectorStoppedError
        at the next asset or batch: subclasses committing their checkpoint once
        the cycle returns never commit an interrupted cycle. The cycle then
        drops the `get_assets` generator, which runs its `finally` blocks: commit
        the checkpoint in `update_checkpoint` only, never in `get_assets`.

        A batch the API refuses (HTTP 400, 422) is dropped and counted in
        `failed_batches`. Any other batch that could not be pushed raises
        AssetConnectorPushError: the next cycle resumes from the last committed
        checkpoint, before it.

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

        self.cycle_stats = {"fetched": 0, "pushed_batches": 0, "failed_batches": 0}

        await self._check_schema_and_reset_if_needed()

        # If a checkpoint reset was scheduled, wait out the deterministic
        # jitter before starting the full re-fetch. This spreads the burst
        # across all configurations of the same connector.
        pending = self._pending_reset_jitter_seconds()
        if pending > 0:
            self.log(
                message=(
                    f"Waiting {pending:.0f}s before the post-reset "
                    "full fetch (reset jitter)."
                ),
                level="info",
            )
            if not await asyncio.to_thread(self._wait_reset_jitter, pending):
                raise AssetConnectorStoppedError()
        self._clear_reset_jitter()

        assets = []
        async for asset in self.get_assets():
            if not self.running:
                raise AssetConnectorStoppedError()

            assets.append(asset)
            self.cycle_stats["fetched"] += 1

            if len(assets) >= self.batch_size:
                await self._push_batch(assets)
                assets = []

        # A `get_assets` checking `running` ends normally once stopped
        if not self.running:
            raise AssetConnectorStoppedError()

        if assets:
            await self._push_batch(assets)

    async def _push_batch(self, assets: list[AssetItem]) -> None:
        if self.cycle_stats["pushed_batches"] or self.cycle_stats["failed_batches"]:
            await self._pause_between_batches()

        if not self.running:
            raise AssetConnectorStoppedError()

        batch = AssetList(version=self.OCSF_SCHEMA_VERSION, items=assets)
        self._batch_rejected = False
        if await self.push_assets_to_sekoia(batch):
            self.cycle_stats["pushed_batches"] += 1
            return

        self.cycle_stats["failed_batches"] += 1
        # Stopping on a batch the API refuses would block the connector on it
        if not self._batch_rejected:
            # Going on would commit a checkpoint past the assets of this batch
            raise AssetConnectorPushError()

    async def _wait(self, seconds: float) -> None:
        # Wait in a worker thread with the timeout passed to Event.wait itself:
        # the thread returns cleanly after `seconds` (or immediately when stop()
        # is signalled), so no thread is leaked per pause.
        await asyncio.to_thread(self._stop_event.wait, seconds)

    async def async_run(self) -> None:
        """
        Async main loop that continuously fetches and pushes assets.
        """
        try:
            while self.running:
                try:
                    processing_start = time.time()
                    await self.asset_fetch_cycle()

                    # If no assets were fetched, pause the connector until the
                    # next cycle
                    delta_sleep = self.frequency - (time.time() - processing_start)
                    if self.cycle_stats["fetched"] == 0 and delta_sleep > 0:
                        self.log(
                            message=f"Next run in the future. "
                            f"Waiting {delta_sleep} seconds"
                        )
                        await self._wait(delta_sleep)
                except AssetConnectorStoppedError:
                    return
                except AssetConnectorPushError:
                    # The push error is already logged: retry at the next cycle,
                    # not at once, so a lasting error does not refetch and repost
                    # in a loop
                    self.log(
                        message=f"Next run in the future. "
                        f"Waiting {self.frequency} seconds",
                        level="warning",
                    )
                    await self._wait(self.frequency)
                except AssetConnectorRateLimitError as e:
                    self.log(
                        message=f"Rate limit hit, pausing connector "
                        f"for {e.retry_after} seconds",
                        level="warning",
                    )
                    await self._wait(e.retry_after)
                except Exception as e:
                    self.log_exception(
                        e,
                        message=f"Error while running asset connector "
                        f"{self.connector_name}",
                    )
        finally:
            # Clean up session on exit
            if self._session:
                await self._session.close()
                self._session = None

    def run(self) -> None:
        """
        Synchronous entry point that runs the async main loop.
        """
        loop = get_or_create_event_loop()
        loop.run_until_complete(self.async_run())
