import signal
import time
from threading import Timer
from typing import Any

from pydantic import BaseModel, ConfigDict

from sekoia_automation.action import Action
from sekoia_automation.exceptions import (
    AssetConnectorPushError,
    AssetConnectorRateLimitError,
    AssetConnectorStoppedError,
)

from .connector import AssetConnector


class AssetConnectorActionArguments(BaseModel):
    """Arguments of the asset connector, plus the connector configuration to act for."""

    # The arguments hold the Sekoia.io API key and the configuration token
    model_config = ConfigDict(extra="allow", hide_input_in_errors=True)

    asset_connector_uuid: str
    connector_configuration_token: str


class AssetConnectorAction(Action):
    """
    Run one fetch cycle of an asset connector as an action.

    It lets the platform run an asset connector where only actions can run,
    such as an on-premise playbook runner. The action receives the arguments
    of the connector plus:
      * `asset_connector_uuid`: the connector configuration to push assets to.
      * `connector_configuration_token`: the token sending the connector logs.

    Assets, checkpoint and logs belong to the connector configuration, as if
    the connector itself had run the cycle. The action returns counters only.

    A cycle stopped before its end (time limit, rate limit, SIGTERM) returns
    `has_more: true`: the platform runs the action again, resuming from the
    connector checkpoint. A cycle can only be split across runs if the
    checkpoint saved by `update_checkpoint` after a push covers the pushed
    assets and no more: `get_assets` yields the assets in checkpoint order
    and moves its cursor per yielded asset, not per page read ahead. A
    connector committing once per complete cycle must finish a cycle within
    `MAX_DURATION`, otherwise every run starts again from the same checkpoint.

    A batch the API refuses (HTTP 400, 422) is dropped and counted in
    `failed_batches`. Any other batch that could not be pushed fails the run,
    with its counters, and returns `has_more: false`: the checkpoint stays
    before the batch and the next scheduled run resumes from it.

    Stopping interrupts the pushes to Sekoia.io, not a `get_assets` blocked in
    its own HTTP call: the connector owns the timeouts of its requests.

    Only synchronous `AssetConnector` subclasses are supported.
    """

    connector_class: type[AssetConnector]

    # The platform marks a run failed after 2 hours: keep time to stop cleanly.
    MAX_DURATION = 100 * 60

    # Arguments validated in `run`: `validate_call` would put them in its errors
    def run(self, arguments: dict) -> dict[str, Any]:
        # The connector registers its own SIGINT/SIGTERM handlers: restore the
        # previous ones once done, the process may run other actions
        previous_handlers = {
            signum: signal.getsignal(signum)
            for signum in (signal.SIGINT, signal.SIGTERM)
        }
        try:
            return self._run_cycle(
                AssetConnectorActionArguments.model_validate(arguments)
            )
        finally:
            for signum, handler in previous_handlers.items():
                # None: a handler not installed from Python, it cannot be restored
                if handler is not None:
                    signal.signal(signum, handler)

    def _run_cycle(self, arguments: AssetConnectorActionArguments) -> dict[str, Any]:
        asset_connector_uuid = arguments.asset_connector_uuid
        token = arguments.connector_configuration_token
        configuration = arguments.model_dump(
            exclude={"asset_connector_uuid", "connector_configuration_token"}
        )

        # Drives the push endpoint and the User-Agent of the connector
        self.module._connector_configuration_uuid = asset_connector_uuid

        connector = self.connector_class(module=self.module, data_path=self.data_path)
        connector.configuration = configuration  # type: ignore[assignment]
        connector._token = token
        base_url = (
            connector.configuration.sekoia_base_url or connector.production_base_url
        ).rstrip("/")
        connector.logs_url = (  # type: ignore[misc]
            f"{base_url}/api/v1/symphony/connector-configurations/"
            f"{asset_connector_uuid}/logs"
        )

        deadline = time.time() + self.MAX_DURATION
        stop_timer = Timer(self.MAX_DURATION, connector.stop)
        stop_timer.daemon = True
        stop_timer.start()
        connector._logs_timer.start()

        has_more = False
        try:
            while True:
                try:
                    connector.asset_fetch_cycle()
                    break
                except AssetConnectorRateLimitError as error:
                    connector.log(
                        message=f"Rate limit hit, pausing for {error.retry_after} "
                        f"seconds",
                        level="warning",
                    )
                    if time.time() + error.retry_after >= deadline:
                        has_more = True
                        break
                    if connector._stop_event.wait(error.retry_after):
                        has_more = True
                        break
        except AssetConnectorStoppedError:
            connector.log(
                message="Fetch cycle stopped before its end, the next run resumes "
                "from the last committed checkpoint",
                level="warning",
            )
            has_more = True
        except AssetConnectorPushError:
            # Fail the run without raising, so that the counters are returned.
            # No `has_more`: a lasting error (revoked key, deleted configuration)
            # would make the platform rerun the action at once, in a loop.
            self.error("A batch of assets could not be pushed to Sekoia.io")
            connector.log(
                message="A batch of assets could not be pushed to Sekoia.io, the "
                "next run resumes from the last committed checkpoint",
                level="warning",
            )
        except Exception as error:
            # An error log is sent at once and raises when the logs API is down:
            # keep the real error
            try:
                connector.log(
                    message=f"Error while running asset connector "
                    f"{connector.connector_name}: {error}",
                    level="error",
                )
            except Exception as log_error:
                self.log(f"Unable to send the connector logs: {log_error}", "warning")
            raise
        finally:
            stop_timer.cancel()
            connector.stop()
            try:
                connector._send_logs_to_api()
            except Exception as error:
                self.log(f"Unable to send the connector logs: {error}", "warning")

        # The counters of the last cycle: a cycle retried after a rate limit
        # fetches again the assets of the rate-limited batch
        return {**connector.cycle_stats, "has_more": has_more}
