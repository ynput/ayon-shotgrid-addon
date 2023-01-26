"""
A Shotgird Events listener leecher for Ayon.

This service will continually run and query the EventLogEntry table from
Shotgrid and converts them to Ayon events, and can be configured from the Ayon
Addon settings page.
"""
import os
import sys
import time
import signal
import socket
from typing import Any, Callable, Union

import ayon_api
from nxtools import logging
import shotgun_api3


# Probably could allow this to be configured via the Addon settings
# And do a query where we alread filter these out.
# Clearly not working, since these are ftrack specific ones.
IGNORE_TOPICS = {}


class ShotgridListener:
    def __init__(self):
        """ Ensure both Ayon and Shotgrid connections are available.

        Set up common needed attributes and handle shotgrid connection
        closure via signal handlers.

        Args:
            func (Callable, None): In case we want to override the default
                function we cast to the processed events.
        """
        logging.info("Initializing the Shotgrid Processor.")

        # Grab all the `handlers` from `processor/handlers` and map them to 
        # the events that are meant to trigger them
        self.handlers_map = None

        try:
            self.settings = ayon_api.get_addon_settings(
                os.environ["AY_ADDON_NAME"],
                os.environ["AY_ADDON_VERSION"]
            )
            self.shotgird_url = self.settings["shotgrid_server"]
            self.shotgrid_script_name = self.settings["shotgrid_script_name"]
            self.shotgrid_api_key = self.settings["shotgrid_api_key"]

            try:
                self.shotgrid_polling_frequency = int(
                    self.settings["service_settings"]["polling_frequency"]
                )
            except Exception:
                self.shotgrid_polling_frequency = 10

        except Exception as e:
            logging.error("Unable to get Addon settings from the server.")
            logging.error(e)
            raise e

        try:
            self.shotgrid_session = shotgun_api3.Shotgun(
                self.shotgird_url,
                script_name=self.shotgrid_script_name,
                api_key=self.shotgrid_api_key
            )
            self.shotgrid_session.connect()
        except Exception as e:
            logging.error("Unable to connect to Shotgrid Instance:")
            logging.error(e)
            raise e

        signal.signal(signal.SIGINT, self._signal_teardown_handler)
        signal.signal(signal.SIGTERM, self._signal_teardown_handler)

    def _signal_teardown_handler(self, signalnum, frame):
        logging.warning("Process stop requested. Terminating process.")
        self.shotgrid_session.close()
        logging.warning("Termination finished.")
        sys.exit(0)

    def start_processing(self):
        """ Main loop querying the Shotgrid database for new events

        Since Shotgrid does not have an event hub per se, we need to query
        the "EventLogEntry table and send these as Ayon events for processing.
        """

        # Enroll `shotgrid.leech` events
        logging.info("Start enrolling for Ayon `shotgrid.leech` Events...")

        while True:
            logging.info("Querying for new `shotgrid.leech` events...")

            try:
                payload = {
                    "sourceTopic": "shotgrid.leech",
                    "targetTopic": "shotgrid.proc",
                    "sender": socket.gethostname(),
                    "description": "Event processing",
                    "sequential": True,
                }
                # while we fix ayon-python-api
                ayon_server_connection = ayon_api.get_server_api_connection()
                # ayon_api.dispatch_event
                response = ayon_server_connection.enroll_event(
                    "enroll",
                    json=payload
                )
                if response.status_code == 204:
                    return None
                elif response.status_code >= 400:
                    logging.error(response)
                    return None

                    return response.json()
                
                events = self.shotgrid_session.find(
                    "EventLogEntry",
                    filters,
                    fields,
                    order,
                    limit=50,
                )
                if events:
                    logging.info(f"Query returned {len(events)} events.")

                    for event in events:
                        if not event:
                            continue

                        last_event_id = self.func(event)

                    logging.debug(f"Last event ID is... {last_event_id}")

            except Exception as err:
                logging.error(err)

            logging.info(
                f"Waiting {self.shotgrid_polling_frequency} seconds..."
            )
            time.sleep(self.shotgrid_polling_frequency)

    def send_shotgrid_event_to_ayon(self, payload: dict[str, Any]) -> int:
        """ Send the Shotgrid event as an Ayon event.

        Args:
            payload (dict): The Event data.

        Returns:
            int: The Shotgrid Event ID.
        """
        logging.info("Processing Shotgrid Event")
        if payload["event_type"] in IGNORE_TOPICS:
            return

        description = f"Leeched {payload['event_type']}"
        user_name = payload.get("user", {}).get("name")

        if user_name:
            description = f"Leeched {payload['event_type']} by {user_name}"

        # fix non serializable datetime
        payload["created_at"] = payload["created_at"].isoformat()

        logging.info(description)

        # while we fix ayon-python-api
        ayon_server_connection = ayon_api.get_server_api_connection()
        # ayon_api.dispatch_event
        ayon_server_connection.dispatch_event(
            "shotgrid.leech",
            sender=socket.gethostname(),
            event_hash=payload["id"],
            project_name=payload.get("project", {}).get("name", "Undefined"),
            username=payload.get("user", {}).get("name", "Undefined"),
            dependencies=payload["id"] - 1,
            description=description,
            summary=None,
            payload=payload,
        )
        logging.info("Dispatched event", payload['event_type'])

        return payload["id"]

