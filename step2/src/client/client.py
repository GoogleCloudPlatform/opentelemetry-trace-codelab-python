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
import random

import flask
import grpc
import structlog
from opentelemetry import propagate, trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.propagators.cloud_trace_propagator import CloudTraceFormatPropagator
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

import shakesapp_pb2
import shakesapp_pb2_grpc

app = flask.Flask(__name__)
FlaskInstrumentor().instrument_app(app)

queries = {
    "hello": 349,
    "world": 728,
    "to be, or not to be": 1,
    "insolence": 14,
}


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


class ClientConfigError(Exception):
    pass


class UnexpectedResultError(Exception):
    pass


SERVER_ADDR = os.environ.get("SERVER_ADDR", "")
if SERVER_ADDR == "":
    raise ClientConfigError("environment variable SERVER_ADDR is not set")
logger.info(f"server address is {SERVER_ADDR}")

# set up OpenTelemetry exporter for Cloud Trace.
# NOTE: SimpleSpanProcessor is for debugging use in general.
# we use it here for a demonstration purpose.
exporter = CloudTraceSpanExporter()
trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
propagate.set_global_textmap(CloudTraceFormatPropagator())
trace.set_tracer_provider(TracerProvider())


@app.route("/")
def main_handler():
    q, count = random.choice(list(queries.items()))

    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("client") as cur_span:
        channel = grpc.insecure_channel(SERVER_ADDR)
        stub = shakesapp_pb2_grpc.ShakespeareServiceStub(channel)
        logger.info(f"request to server with query: {q}")
        cur_span.add_event("server_call_start")
        resp = stub.GetMatchCount(shakesapp_pb2.ShakespeareRequest(query=q))
        cur_span.add_event("server_call_end")
        if count != resp.match_count:
            raise UnexpectedResultError(
                f"The expected count for '{q}' was {count}, but result was {resp.match_count } obtained"
            )
        result = str(resp.match_count)
        logger.info(f"matched count for '{q}' is {result}")
    return result


@app.route("/_healthz")
def healthz_handler():
    return "ok"


def main():
    app.run(host="0.0.0.0", port="8080")


if __name__ == "__main__":
    main()
