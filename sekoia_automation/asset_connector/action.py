import time
from collections import Counter
from threading import Timer
from typing import Any

from pydantic import BaseModel, ConfigDict

from sekoia_automation.action import Action
from sekoia_automation.exceptions import (
    AssetConnectorRateLimitError,
    AssetConnectorStoppedError,
)

from .connector import AssetConnector


class AssetConnectorActionArguments(BaseModel):
    """Arguments of the asset connector, plus the connector configuration to act for."""

    model_config = ConfigDict(extra="allow")

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
    connector checkpoint.
    """

    connector_class: type[AssetConnector]

    # The platform marks a run failed after 2 hours: keep time to stop cleanly.
    MAX_DURATION = 100 * 60

    def run(self, arguments: AssetConnectorActionArguments) -> dict[str, Any]:
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

        stats: Counter[str] = Counter()
        has_more = False
        try:
            while True:
                try:
                    connector.asset_fetch_cycle()
                    break
                except AssetConnectorRateLimitError as error:
                    stats.update(connector.cycle_stats)
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
            stats.update(connector.cycle_stats)
        except AssetConnectorStoppedError:
            stats.update(connector.cycle_stats)
            has_more = True
        except Exception as error:
            connector.log(
                message=f"Error while running asset connector "
                f"{connector.connector_name}: {error}",
                level="error",
            )
            raise
        finally:
            stop_timer.cancel()
            connector.stop()
            try:
                connector._send_logs_to_api()
            except Exception as error:
                self.log(f"Unable to send the connector logs: {error}", "warning")

        return {
            "fetched": stats["fetched"],
            "pushed_batches": stats["pushed_batches"],
            "failed_batches": stats["failed_batches"],
            "has_more": has_more,
        }
