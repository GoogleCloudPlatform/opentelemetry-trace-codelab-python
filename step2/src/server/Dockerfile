# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM python:3.8-slim-buster as base

FROM base as builder
RUN apt-get -qq update \
    && apt-get install -y --no-install-recommends \
        wget

RUN GRPC_HEALTH_PROBE_VERSION=v0.3.6 && \
    wget -qO/bin/grpc_health_probe https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 && \
    chmod +x /bin/grpc_health_probe

RUN pip install poetry
COPY . /src
WORKDIR /src
RUN poetry build

FROM base as runner
COPY --from=builder /src/dist/*.whl /
COPY --from=builder /bin/grpc_health_probe /bin/grpc_health_probe
RUN pip install /*.whl && rm /*.whl

EXPOSE 5050

CMD [ "python", "-m", "server" ]