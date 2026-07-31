# The corp-deployment image: avs as a service (Studio UI or webhook server).
#
# Fail-closed by construction: the default command binds the Studio to
# 0.0.0.0, and the CLI refuses that bind unless AVS_STUDIO_TOKEN (or the
# AVS_STUDIO_TOKEN_FILE secret mount) is set — an unconfigured container
# exits with the instruction instead of serving an unauthenticated UI.
#
#   docker build -t avs .
#   docker run -p 8433:8433 \
#     -v /srv/team-workspace:/workspace \
#     -e AVS_STUDIO_TOKEN_FILE=/run/secrets/studio-token \
#     -e ANTHROPIC_API_KEY_FILE=/run/secrets/anthropic-key \
#     avs
#
# Webhook mode instead:  docker run … avs serve --port 8422
# Air-gapped evaluation: docker run … avs studio . --host 0.0.0.0 --provider mock
#
# The image ships no keys, no proxy, no telemetry endpoint; every model
# call bills the credentials YOU mount. Full outbound-host list:
# editions/enterprise/procurement/network-egress.md.

FROM python:3.12-slim

# git: reviews, adopt, and the build loop all drive it. Nothing else.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home avs

COPY . /src
RUN pip install --no-cache-dir /src && rm -rf /src

USER avs
WORKDIR /workspace
EXPOSE 8433 8422

ENTRYPOINT ["avs"]
CMD ["studio", ".", "--host", "0.0.0.0"]
