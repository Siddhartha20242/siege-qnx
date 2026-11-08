# Siege's host tools in a container: read the results, run the tests, build reports and CI gates.
# It needs no QNX and no licence. It does NOT contain the QNX SDP or a QNX image (neither may be
# redistributed); to build and boot QNX, see docs/docker.md and docker/builder/.
#
#   docker build -t siege .
#   docker run --rm siege                  # ./siege show
#   docker run --rm siege show secpol
#   docker run --rm siege selftest
FROM python:3.12-slim
RUN pip install --no-cache-dir numpy==1.26.4
WORKDIR /siege
COPY . .
ENTRYPOINT ["./siege"]
CMD ["show"]
