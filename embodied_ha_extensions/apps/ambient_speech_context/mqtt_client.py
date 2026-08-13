from __future__ import annotations

import json
import os
import ssl
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as mqtt

from .contract import TRANSCRIPT_TOPIC
from .storage import AmbientSpeechStore


class MqttError(RuntimeError):
    pass


@dataclass(frozen=True)
class MqttCredentials:
    host: str
    port: int
    username: str = ""
    password: str = ""
    ssl: bool = False


def fetch_mqtt_credentials(
    token: str | None = None,
    url: str = "http://supervisor/services/mqtt",
    timeout: float = 10,
) -> MqttCredentials:
    supervisor_token = token if token is not None else os.environ.get("SUPERVISOR_TOKEN", "")
    if not supervisor_token:
        raise MqttError("supervisor_token_unavailable")
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
    except Exception as exc:
        raise MqttError("mqtt_service_unavailable") from exc
    data = body.get("data", {}) if isinstance(body, dict) else {}
    host = data.get("host")
    port = data.get("port", 1883)
    ssl_enabled = data.get("ssl", False)
    username = data.get("username", "")
    password = data.get("password", "")
    if (
        not isinstance(host, str)
        or not host
        or isinstance(port, bool)
        or not isinstance(port, int)
        or not 1 <= port <= 65535
        or not isinstance(ssl_enabled, bool)
        or not isinstance(username, str)
        or not isinstance(password, str)
    ):
        raise MqttError("mqtt_service_invalid")
    return MqttCredentials(host, port, username, password, ssl_enabled)


class TranscriptSubscriber:
    def __init__(
        self,
        store: AmbientSpeechStore,
        credentials: MqttCredentials,
        *,
        logger: Callable[[str], None] = print,
        client: Any | None = None,
    ) -> None:
        self.store = store
        self.credentials = credentials
        self.logger = logger
        self.fatal_error = False
        self.stopping = False
        self.client = client or mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            protocol=mqtt.MQTTv311,
            manual_ack=True,
        )
        if credentials.username:
            self.client.username_pw_set(credentials.username, credentials.password)
        if credentials.ssl:
            self.client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        self.client.reconnect_delay_set(min_delay=1, max_delay=60)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def _on_connect(
        self,
        client: Any,
        _userdata: Any,
        _flags: Any,
        reason_code: Any,
        _properties: Any,
    ) -> None:
        if reason_code != 0:
            self.logger(f"[ambient_speech_context] mqtt_connect_failed code={reason_code}")
            return
        result, _mid = client.subscribe(TRANSCRIPT_TOPIC, qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            self.fatal_error = True
            self.logger("[ambient_speech_context] mqtt_subscribe_failed")
            client.disconnect()
            return
        self.logger(f"[ambient_speech_context] mqtt_connected topic={TRANSCRIPT_TOPIC} qos=1")

    def _on_disconnect(
        self,
        _client: Any,
        _userdata: Any,
        _disconnect_flags: Any,
        reason_code: Any,
        _properties: Any,
    ) -> None:
        if not self.stopping and reason_code != 0:
            self.logger(f"[ambient_speech_context] mqtt_disconnected code={reason_code}")

    def _on_message(self, client: Any, _userdata: Any, message: Any) -> None:
        try:
            result = self.store.ingest(bytes(message.payload), retained=bool(message.retain))
        except Exception as exc:
            self.fatal_error = True
            self.logger(f"[ambient_speech_context] storage_failed error_type={type(exc).__name__}")
            client.disconnect()
            return

        event_id = result.event_id or "none"
        self.logger(
            "[ambient_speech_context] event "
            f"outcome={result.outcome} reason={result.reason} event_id={event_id}"
        )
        if message.qos > 0:
            client.ack(message.mid, message.qos)

    def run(self) -> int:
        try:
            self.client.connect(self.credentials.host, self.credentials.port, keepalive=30)
            self.client.loop_forever(retry_first_connection=True)
        except Exception as exc:
            self.logger(
                f"[ambient_speech_context] mqtt_runtime_failed error_type={type(exc).__name__}"
            )
            return 1
        return 1 if self.fatal_error else 0

    def stop(self) -> None:
        self.stopping = True
        self.client.disconnect()
