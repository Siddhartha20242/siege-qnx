# Siege's host tools in a container: read the results, run the tests, build reports and CI gates.
# It needs no QNX and no licence. It does NOT contain the QNX SDP or a QNX image (neither may be
# redistributed); to build and boot QNX, see docs/docker.md and docker/builder/.
#
#   docker build -t siege .
#   docker run --rm siege                  # ./siege show
#   docker run --rm siege show secpol
#   docker run --rm siege selftest
# The base image is pinned by tag only: a digest could not be looked up from the author's machine.
FROM python:3.12-slim
RUN pip install --no-cache-dir numpy==1.26.4
ENV PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home siege
WORKDIR /siege
COPY --chown=siege:siege . .
USER siege
ENTRYPOINT ["./siege"]
CMD ["show"]
