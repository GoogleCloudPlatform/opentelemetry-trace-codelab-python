# Copyright 2021 Yoshi Yamaguchi
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import time

import requests
import structlog
from opentelemetry import propagate, trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.propagators.cloud_trace_propagator import CloudTraceFormatPropagator
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

RequestsInstrumentor().instrument()


# Structured log configuration
def field_name_modifier(_, __, event_dict):
    """Replace log level field name 'level' with 'serverity' to meet
    Cloud Logging's data model.
    Make sure to call this processor after structlog.stdlib.add_log_level.
    https://cloud.google.com/logging/docs/reference/v2/rpc/google.logging.v2?hl=en#google.logging.v2.LogEntry
    """
    event_dict["severity"] = event_dict["level"]
    del event_dict["level"]
    return event_dict


def get_json_logger():
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            field_name_modifier,
            structlog.processors.TimeStamper("iso"),
            structlog.processors.JSONRenderer(),
        ]
    )
    return structlog.get_logger()


logger = get_json_logger()


def check_client_connection(healthz_url):
    with requests.get(healthz_url) as resp:
        logger.info(f"/_healthz response: {resp.text}")
        if str(resp.text) == "ok":
            logger.info("confirmed connection ot clientservice")
            return True
    return False


def call_client(url):
    logger.info("call_client start")
    try:
        with requests.get(url) as resp:
            logger.info(f"count: {resp.text}")
        logger.info("call_client end")
    except requests.HTTPError as e:
        logger.warn(f"HTTP request error: {e}")


def main():
    target = os.environ.get("CLIENT_ADDR", "0.0.0.0:8080")

    exporter = CloudTraceSpanExporter()
    trace.get_tracer_provider().add_span_processor(
        SimpleSpanProcessor(exporter)
    )
    tracer = trace.get_tracer(__name__)
    propagate.set_global_textmap(CloudTraceFormatPropagator())
    trace.set_tracer_provider(TracerProvider())

    # connectivity check to client service
    healthz = f"http://{target}/_healthz"
    logger.info(f"check connectivity: {healthz}")
    wait_interval = 1.0
    while not check_client_connection(healthz):
        if wait_interval > 30:
            logger.error("exponential backoff exceeded the threshold")
            return
        logger.warning(f"not connected. wait for {wait_interval}sec and retry.")
        time.sleep(wait_interval)
        wait_interval *= 3

    # start request loop to client service
    logger.info("start client request loop")
    addr = f"http://{target}"
    while True:
        with tracer.start_as_current_span("loadgen") as root_span:
            root_span.add_event(name="request_start")
            logger.info("start request to client")
            call_client(addr)
            root_span.add_event(name="request_end")
            logger.info("end request to client")
        time.sleep(2.0)


if __name__ == "__main__":
    main()
