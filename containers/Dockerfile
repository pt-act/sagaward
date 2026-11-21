# ---------------------------------------------------------------------------
# Builder stage: compile the Go tools here so the Go toolchain (~225MB) and the
# module/build caches never reach the runtime image. The resulting binaries are
# statically linked and copied into the final stage.
# ---------------------------------------------------------------------------
# S-6/S-7: the base is a build-time ARG so a locally built/pinned Kali base can
# replace the rolling tag without editing the file. The default stays the rolling
# tag (the project's base); pin it in CI with --build-arg KALI_BASE=...@sha256:...
ARG KALI_BASE=kalilinux/kali-rolling:latest
FROM ${KALI_BASE} AS gobuilder

RUN apt-get update && \
    apt-get install -y kali-archive-keyring && \
    apt-get update && \
    apt-get install -y --no-install-recommends golang-go git ca-certificates

ENV GOBIN=/out/bin
# S-6/S-7: every Go tool is pinned to a released module version; `@latest` made
# the builder stage non-reproducible.
RUN mkdir -p /out/bin && \
    go install -v github.com/projectdiscovery/httpx/cmd/httpx@v1.12.0 && \
    go install -v github.com/projectdiscovery/katana/cmd/katana@v1.8.0 && \
    go install -v github.com/projectdiscovery/cvemap/cmd/vulnx@v1.0.0 && \
    go install -v github.com/jaeles-project/gospider@v1.1.6 && \
    go install -v github.com/projectdiscovery/interactsh/cmd/interactsh-client@v1.4.1 && \
    go install -v golang.org/x/vuln/cmd/govulncheck@v1.10.0

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM ${KALI_BASE}

LABEL description="AI Agent Penetration Testing Environment with Comprehensive Automated Tools"

RUN apt-get update && \
    apt-get install -y kali-archive-keyring && \
    apt-get update && \
    apt-get upgrade -y

# The fence's isolation design (apf-isolation 0.2.5): the agent gets NO sudo.
# Upstream's sandbox grants passwordless root escalation to pentester — that posture is exactly
# what the fence exists to harden against (the observation-channel residual's
# compensation: revoke sudo, harden the image's binary permissions).
RUN useradd -m -s /bin/bash pentester && \
    touch /home/pentester/.hushlogin

RUN mkdir -p /home/pentester/tools /app/certs && \
    chown -R pentester:pentester /app/certs /home/pentester/tools

# S-6/S-7: Kali rolling is a moving snapshot, so apt versions cannot be pinned
# without a snapshot mirror; the base image digest (KALI_BASE) is the pin. The
# curl/npm/pipx/pip downloads below are pinned by version and checksum.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget curl git vim nano unzip tar \
    apt-transport-https ca-certificates gnupg lsb-release \
    software-properties-common \
    gcc libc6-dev \
    python3 python3-pip python3-venv python3-setuptools \
    net-tools dnsutils whois \
    file xxd \
    jq parallel ripgrep grep \
    less procps htop \
    iproute2 iputils-ping netcat-traditional \
    nmap ncat ndiff \
    sqlmap nuclei subfinder naabu ffuf \
    nodejs npm pipx \
    golang-go \
    libcap2-bin \
    gdb \
    libnss3-tools \
    chromium fonts-liberation


RUN setcap cap_net_raw,cap_net_admin,cap_net_bind_service+eip $(which nmap)

USER pentester
RUN openssl ecparam -name prime256v1 -genkey -noout -out /app/certs/ca.key && \
    openssl req -x509 -new -key /app/certs/ca.key \
    -out /app/certs/ca.crt \
    -days 3650 \
    -subj "/C=US/ST=CA/O=Security Testing/CN=Testing Root CA" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign" && \
    openssl pkcs12 -export \
    -out /app/certs/ca.p12 \
    -inkey /app/certs/ca.key \
    -in /app/certs/ca.crt \
    -passout pass:"" \
    -name "Testing Root CA" && \
    chmod 644 /app/certs/ca.crt && \
    chmod 600 /app/certs/ca.key && \
    chmod 600 /app/certs/ca.p12

USER root
RUN cp /app/certs/ca.crt /usr/local/share/ca-certificates/ca.crt && \
    update-ca-certificates

# S-6/S-7: pin the uv version; the installer verifies the release's own checksum.
ARG UV_VERSION=0.13.9
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_VERSION="${UV_VERSION}" sh

USER pentester
WORKDIR /tmp

# Go tools are built in the gobuilder stage; copy the static binaries only.
COPY --from=gobuilder --chown=pentester:pentester /out/bin/ /home/pentester/go/bin/

RUN nuclei -update-templates

RUN pipx install arjun==2.2.7 && \
    pipx install dirsearch==0.5.0 && \
    pipx inject dirsearch 'setuptools<81' && \
    pipx install wafw00f==2.4.2

ENV NPM_CONFIG_PREFIX=/home/pentester/.npm-global
RUN mkdir -p /home/pentester/.npm-global

RUN npm install -g retire@6.1.1 && \
    npm install -g eslint@10.15.0 && \
    npm install -g js-beautify@2.0.3 && \
    npm install -g @ast-grep/cli@0.51.3 && \
    npm install -g tree-sitter-cli@0.27.2 && \
    npm install -g agent-browser@0.26.0 && \
    npm cache clean --force && \
    # ast-grep ships two identical binaries (`ast-grep` and `sg`); dedupe (~52MB)
    ln -sf ast-grep /home/pentester/.npm-global/lib/node_modules/@ast-grep/cli/sg

ENV AGENT_BROWSER_EXECUTABLE_PATH=/usr/bin/chromium
ENV AGENT_BROWSER_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
ENV AGENT_BROWSER_ARGS="--disable-blink-features=AutomationControlled,--no-first-run,--no-default-browser-check,--lang=en-US"
ENV AGENT_BROWSER_SCREENSHOT_DIR=/workspace/.agent-browser-screenshots
ENV AGENT_BROWSER_IDLE_TIMEOUT_MS=180000
USER root
RUN set -eu; \
    { \
        for var in AGENT_BROWSER_EXECUTABLE_PATH AGENT_BROWSER_USER_AGENT \
                   AGENT_BROWSER_ARGS AGENT_BROWSER_SCREENSHOT_DIR \
                   AGENT_BROWSER_IDLE_TIMEOUT_MS; do \
            eval "value=\${$var}"; \
            printf 'export %s="${%s:-%s}"\n' "$var" "$var" "$value"; \
        done; \
    } > /tmp/agent-browser.sh; \
    install -m 0644 /tmp/agent-browser.sh /etc/profile.d/agent-browser.sh; \
    rm /tmp/agent-browser.sh; \
    env -i bash -lc 'test "${AGENT_BROWSER_IDLE_TIMEOUT_MS}" = "180000"'
USER pentester
RUN /home/pentester/.npm-global/bin/agent-browser doctor --offline --quick

RUN set -eux; \
    TS_PARSER_DIR="/home/pentester/.tree-sitter/parsers"; \
    mkdir -p "${TS_PARSER_DIR}"; \
    for repo in tree-sitter-java tree-sitter-javascript tree-sitter-python tree-sitter-go tree-sitter-bash tree-sitter-json tree-sitter-yaml tree-sitter-typescript; do \
        if [ "$repo" = "tree-sitter-yaml" ]; then \
            repo_url="https://github.com/tree-sitter-grammars/${repo}.git"; \
        else \
            repo_url="https://github.com/tree-sitter/${repo}.git"; \
        fi; \
        case "$repo" in \
            tree-sitter-java) repo_ref="e10607b45ff745f5f876bfa3e94fbcc6b44bdc11" ;; \
            tree-sitter-javascript) repo_ref="58404d8cf191d69f2674a8fd507bd5776f46cb11" ;; \
            tree-sitter-python) repo_ref="26855eabccb19c6abf499fbc5b8dc7cc9ab8bc64" ;; \
            tree-sitter-go) repo_ref="2346a3ab1bb3857b48b29d779a1ef9799a248cd7" ;; \
            tree-sitter-bash) repo_ref="a06c2e4415e9bc0346c6b86d401879ffb44058f7" ;; \
            tree-sitter-json) repo_ref="254c42a6476413b776221e03982ac8ae159eeb72" ;; \
            tree-sitter-yaml) repo_ref="a1c4812a73ec5e089de8e441fdea3a921e8d5079" ;; \
            tree-sitter-typescript) repo_ref="75b3874edb2dc714fb1fd77a32013d0f8699989f" ;; \
        esac; \
        if [ ! -d "${TS_PARSER_DIR}/${repo}" ]; then \
            git clone "${repo_url}" "${TS_PARSER_DIR}/${repo}"; \
            git -C "${TS_PARSER_DIR}/${repo}" checkout "${repo_ref}"; \
        fi; \
    done; \
    if [ -d "${TS_PARSER_DIR}/tree-sitter-typescript/typescript" ]; then \
        ln -sfn "${TS_PARSER_DIR}/tree-sitter-typescript/typescript" "${TS_PARSER_DIR}/tree-sitter-typescript-typescript"; \
    fi; \
    if [ -d "${TS_PARSER_DIR}/tree-sitter-typescript/tsx" ]; then \
        ln -sfn "${TS_PARSER_DIR}/tree-sitter-typescript/tsx" "${TS_PARSER_DIR}/tree-sitter-typescript-tsx"; \
    fi; \
    tree-sitter init-config >/dev/null 2>&1 || true; \
    TS_CONFIG="/home/pentester/.config/tree-sitter/config.json"; \
    mkdir -p "$(dirname "${TS_CONFIG}")"; \
    [ -f "${TS_CONFIG}" ] || printf '{}\n' > "${TS_CONFIG}"; \
    TMP_CFG="$(mktemp)"; \
    jq --arg p "${TS_PARSER_DIR}" '.["parser-directories"] = ((.["parser-directories"] // []) + [$p] | unique)' "${TS_CONFIG}" > "${TMP_CFG}"; \
    mv "${TMP_CFG}" "${TS_CONFIG}"

WORKDIR /home/pentester/tools
# S-6/S-7: pin each clone to a commit so the tools do not drift under the build.
RUN git clone https://github.com/aravind0x7/JS-Snooper.git && \
    git -C JS-Snooper checkout 932704cbce1a04ebe89a558f395a6e474e01b15b && \
    chmod +x JS-Snooper/js_snooper.sh && \
    git clone https://github.com/xchopath/jsniper.sh.git && \
    git -C jsniper.sh checkout 65d0b508dc88e6de3dfe6ac60e6d89eca22be686 && \
    chmod +x jsniper.sh/jsniper.sh && \
    git clone https://github.com/ticarpi/jwt_tool.git && \
    git -C jwt_tool checkout 3bc7407cf2222d6a821dcc19c776e5a1b1cb9a9b && \
    chmod +x jwt_tool/jwt_tool.py

USER root

# Install trufflehog into a pentester-owned dir on PATH so its runtime self-update
# (which replaces the binary in place) succeeds: as non-root `pentester` it cannot
# overwrite a root-owned binary under /usr/local/bin, which otherwise fails with
# "cannot move binary" and aborts the scan. Pin the initial version for
# reproducible builds; self-update then pulls fresh detectors at runtime.
ARG TRUFFLEHOG_VERSION=3.99.2
RUN curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /home/pentester/.local/bin "v${TRUFFLEHOG_VERSION}" && \
    chown -R pentester:pentester /home/pentester/.local
# S-6/S-7: the release tag was resolved from `releases/latest` at build time, so
# the binary changed under the build. Pin the version and verify the tarball.
ARG GITLEAKS_VERSION=8.30.1
ARG GITLEAKS_SHA256_X64=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
ARG GITLEAKS_SHA256_ARM64=e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080
RUN set -eux; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
        x86_64) GITLEAKS_ARCH="x64"; GITLEAKS_SHA256="${GITLEAKS_SHA256_X64}" ;; \
        aarch64|arm64) GITLEAKS_ARCH="arm64"; GITLEAKS_SHA256="${GITLEAKS_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${GITLEAKS_ARCH}.tar.gz" -o /tmp/gitleaks.tgz; \
    echo "${GITLEAKS_SHA256}  /tmp/gitleaks.tgz" | sha256sum -c -; \
    tar -xzf /tmp/gitleaks.tgz -C /tmp; \
    install -m 0755 /tmp/gitleaks /usr/local/bin/gitleaks; \
    rm -f /tmp/gitleaks /tmp/gitleaks.tgz

ARG TRIVY_VERSION=0.76.1
ARG TRIVY_SHA256_X86=c7cbe3137fb8a48a17574bede3dd6beb16742d1e9772929940fc90082c39d9c0
ARG TRIVY_SHA256_AARCH64=e174dff2a6dba5e3ae41f8d0537a6324405bd08132497340304c6b20e0f16a1f
RUN set -eux; \
    case "$(uname -m)" in \
        x86_64) TRIVY_ARCH="64bit"; TRIVY_SHA256="${TRIVY_SHA256_X86}" ;; \
        aarch64|arm64) TRIVY_ARCH="ARM64"; TRIVY_SHA256="${TRIVY_SHA256_AARCH64}" ;; \
        *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-${TRIVY_ARCH}.tar.gz" -o /tmp/trivy.tgz; \
    echo "${TRIVY_SHA256}  /tmp/trivy.tgz" | sha256sum -c -; \
    tar -xzf /tmp/trivy.tgz -C /tmp trivy; \
    install -m 0755 /tmp/trivy /usr/local/bin/trivy; \
    rm -f /tmp/trivy /tmp/trivy.tgz; \
    trivy --version

RUN apt-get install -y wapiti

# CVE-2026-111497: out-of-bounds write in the brotli decoder, fixed in brotli
# 1.2.1 / Debian 1.2.0-4.1. kali-rolling still ships 1.2.0-4, and node, curl and
# python3 in this image all load the shared libbrotlidec, so every HTTP client here
# would decode a malicious `Content-Encoding: br` response with the vulnerable
# code. Install the fixed Debian packages until Kali picks them up.
ARG BROTLI_DEB_VERSION=1.2.0-4.1
ARG BROTLI_SHA256_LIBBROTLI1_AMD64=2d58db32250aa535e27c62e98451debd43b539aa026066806432e842d5b56c00
ARG BROTLI_SHA256_PYTHON3_BROTLI_AMD64=3b62003bf956337d2ae672b40174cd303e740ea0e013d8405e503a4b5abaf061
ARG BROTLI_SHA256_LIBBROTLI1_ARM64=ff90055f0c42dc39fdf8f12d7f68c7da32da2ec90d0a49eb39e80b764988ee02
ARG BROTLI_SHA256_PYTHON3_BROTLI_ARM64=0923c03d9293e45cd8f744f1de5103b97603f0ae0c54b275d8f03ebf87b29750
RUN set -eux; \
    ARCH="$(dpkg --print-architecture)"; \
    case "$ARCH" in \
        amd64) LIBBROTLI1_SHA256="${BROTLI_SHA256_LIBBROTLI1_AMD64}"; PYTHON3_BROTLI_SHA256="${BROTLI_SHA256_PYTHON3_BROTLI_AMD64}" ;; \
        arm64) LIBBROTLI1_SHA256="${BROTLI_SHA256_LIBBROTLI1_ARM64}"; PYTHON3_BROTLI_SHA256="${BROTLI_SHA256_PYTHON3_BROTLI_ARM64}" ;; \
        *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;; \
    esac; \
    for pkg in libbrotli1 python3-brotli; do \
        curl -fsSL "https://deb.debian.org/debian/pool/main/b/brotli/${pkg}_${BROTLI_DEB_VERSION}_${ARCH}.deb" -o "/tmp/${pkg}.deb"; \
    done; \
    echo "${LIBBROTLI1_SHA256}  /tmp/libbrotli1.deb" | sha256sum -c -; \
    echo "${PYTHON3_BROTLI_SHA256}  /tmp/python3-brotli.deb" | sha256sum -c -; \
    dpkg -i /tmp/libbrotli1.deb /tmp/python3-brotli.deb; \
    rm -f /tmp/libbrotli1.deb /tmp/python3-brotli.deb; \
    test "$(dpkg-query -W -f='${Version}' libbrotli1)" = "${BROTLI_DEB_VERSION}"; \
    node -e 'const z=require("zlib");z.brotliDecompressSync(z.brotliCompressSync(Buffer.from("ok")))'

ARG OPENGREP_VERSION=1.31.0
ARG OPENGREP_SHA256_X86=dbbe3c2058dbe600c449a8ba22ea79a1643a6660658400090d0323a8d0d31147
ARG OPENGREP_SHA256_AARCH64=2b713a29a00237f85408b83002fc111db5b94c7fa8d263f0a93184a960655d9d
RUN set -eux; \
    case "$(uname -m)" in \
        x86_64) OPENGREP_ARCH="x86"; OPENGREP_SHA256="${OPENGREP_SHA256_X86}" ;; \
        aarch64|arm64) OPENGREP_ARCH="aarch64"; OPENGREP_SHA256="${OPENGREP_SHA256_AARCH64}" ;; \
        *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/opengrep/opengrep/releases/download/v${OPENGREP_VERSION}/opengrep_manylinux_${OPENGREP_ARCH}" -o /tmp/opengrep; \
    echo "${OPENGREP_SHA256}  /tmp/opengrep" | sha256sum -c -; \
    install -m 0755 /tmp/opengrep /usr/local/bin/opengrep; \
    rm -f /tmp/opengrep; \
    opengrep --version

# Opengrep ships no rule registry of its own; bake the community ruleset so
# scans run offline. Keep only rule YAML and LICENSE; drop tests, fixtures,
# tooling, and rules marked with a proprietary license.
ARG OPENGREP_RULES_REF=f1d2b562b414783763fd02a6ed2736eaed622efa
RUN set -eux; \
    mkdir -p /opt/opengrep-rules; \
    curl -fsSL "https://codeload.github.com/opengrep/opengrep-rules/tar.gz/${OPENGREP_RULES_REF}" \
        | tar -xz --strip-components=1 -C /opt/opengrep-rules; \
    cd /opt/opengrep-rules; \
    rm -rf .github scripts stats; \
    find . -maxdepth 1 -type f ! -name LICENSE -delete; \
    find . -mindepth 2 -type f \( ! \( -name '*.yaml' -o -name '*.yml' \) -o -name '*.test.yaml' -o -name '*.test.yml' -o -name '.*' \) -delete; \
    grep -rlZ 'license: proprietary' . | xargs -0 -r rm -f; \
    find . -type d -empty -delete; \
    chmod -R a+rX /opt/opengrep-rules

# Sagaward-authored rules that close gaps in the community ruleset.
COPY containers/opengrep-rules/ /opt/opengrep-rules/sagaward/
RUN chmod -R a+rX /opt/opengrep-rules/sagaward

USER pentester

RUN pipx install bandit==1.9.4

RUN npm install -g jshint@2.13.6

USER root

RUN apt-get autoremove -y && \
    apt-get autoclean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && \
    # Purge non-English locales (~160MB)
    find /usr/share/locale -mindepth 1 -maxdepth 1 -type d \
        ! -name 'en' ! -name 'en_US' ! -name 'C' -exec rm -rf {} + && \
    # Remove package documentation and man pages not needed at runtime (~95MB)
    rm -rf /usr/share/doc/* /usr/share/doc-base/* /usr/share/man/*

ENV PATH="/home/pentester/go/bin:/home/pentester/.local/bin:/home/pentester/.npm-global/bin:/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

WORKDIR /app

ARG CAIDO_VERSION=0.56.0
ARG CAIDO_SHA256_X86_64=1bc13f1ad558cd333924890d9d09b73f1cdf6726b7855265cd4c4ddece0211d3
ARG CAIDO_SHA256_AARCH64=5fe8c37ac0435ce5924014cf035902686051be86831824744e435636a62d3689
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        CAIDO_ARCH="x86_64"; CAIDO_SHA256="${CAIDO_SHA256_X86_64}"; \
    elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then \
        CAIDO_ARCH="aarch64"; CAIDO_SHA256="${CAIDO_SHA256_AARCH64}"; \
    else \
        echo "Unsupported architecture: $ARCH" && exit 1; \
    fi && \
    wget -O caido-cli.tar.gz "https://caido.download/releases/v${CAIDO_VERSION}/caido-cli-v${CAIDO_VERSION}-linux-${CAIDO_ARCH}.tar.gz" && \
    echo "${CAIDO_SHA256}  caido-cli.tar.gz" | sha256sum -c - && \
    tar -xzf caido-cli.tar.gz && \
    chmod +x caido-cli && \
    rm caido-cli.tar.gz && \
    mv caido-cli /usr/local/bin/

ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

RUN mkdir -p /workspace && chown -R pentester:pentester /workspace /app

USER pentester
RUN python3 -m venv /app/.venv && \
    /app/.venv/bin/pip install --no-cache-dir caido-sdk-client==0.3.2 && \
    /app/.venv/bin/pip install --no-cache-dir \
        requests==2.34.2 httpx==0.28.1 beautifulsoup4==4.15.0 lxml==6.1.3 pyjwt==2.15.1 cryptography==50.0.2 && \
    /app/.venv/bin/pip install --no-cache-dir -r /home/pentester/tools/jwt_tool/requirements.txt && \
    printf '%s\n' \
        '#!/bin/bash' \
        'exec /app/.venv/bin/python /home/pentester/tools/jwt_tool/jwt_tool.py "$@"' \
        > /home/pentester/.local/bin/jwt_tool && \
    chmod +x /home/pentester/.local/bin/jwt_tool

COPY --chown=pentester:pentester sagaward/tools/proxy/caido_api.py /opt/sagaward-python/caido_api.py
ENV PYTHONPATH=/opt/sagaward-python

# Login shells (e.g. `bash -lc`) source /etc/profile, which on Debian/Kali
# hard-resets PATH and drops the image's ENV PATH entries. Re-add the same
# directories here — including /app/.venv/bin — so `python3`/`pip` resolve to
# the venv (which ships requests, httpx, bs4, lxml, pyjwt, cryptography, and the
# Caido SDK) instead of the externally-managed system interpreter.
RUN echo 'export PATH="/home/pentester/go/bin:/home/pentester/.local/bin:/home/pentester/.npm-global/bin:/app/.venv/bin:$PATH"' >> /home/pentester/.bashrc && \
    echo 'export PATH="/home/pentester/go/bin:/home/pentester/.local/bin:/home/pentester/.npm-global/bin:/app/.venv/bin:$PATH"' >> /home/pentester/.profile

USER root
COPY containers/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER pentester
WORKDIR /workspace

ENTRYPOINT ["docker-entrypoint.sh"]
