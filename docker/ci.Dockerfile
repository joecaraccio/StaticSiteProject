# Runs .github/workflows locally with act, so local CI and GitHub CI cannot drift.
#
# act starts sibling containers on the host daemon, so this image only needs the
# act binary and the docker CLI.
FROM docker:cli

# ACT_VERSION pins a release tag (e.g. v0.2.75). Left empty, the installer takes
# the latest, which is convenient but not reproducible — pin it once you have a
# version you are happy with.
ARG ACT_VERSION=""

RUN apk add --no-cache bash curl git \
    && curl -fsSL https://raw.githubusercontent.com/nektos/act/master/install.sh \
       | bash -s -- -b /usr/local/bin ${ACT_VERSION} \
    && act --version

WORKDIR /repo
ENTRYPOINT ["act"]
# Default: the same job GitHub runs on a push.
CMD ["push", "--job", "check"]
