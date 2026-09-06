#!/bin/sh
# Thinking model: llama.cpp server + a small open instruct model (both free). Re-runnable.
#   sh scripts/get_model.sh            download prebuilt server + model (default Qwen2.5-1.5B-Instruct Q4_K_M, ~940 MB)
#   sh scripts/get_model.sh --test     start the server by hand for 20 s and show its output (use when /status says NOT RUNNING)
#   sh scripts/get_model.sh --build    compile llama.cpp here instead (needs: sudo apt install -y build-essential cmake libcurl4-openssl-dev)
# Override the model with BAI_MODEL_URL=<any GGUF url>.
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd)
mkdir -p release/llm state/logs
LLAMA_TAG=b10826
URL="${BAI_MODEL_URL:-https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf}"

fetch_model() {
  if [ ! -s release/llm/model.gguf ]; then
    echo "fetching model (~1 GB, once) ..."
    curl -fL --progress-bar -o release/llm/model.gguf.part "$URL" && mv release/llm/model.gguf.part release/llm/model.gguf
  fi
}

case "$1" in
  --test)
    echo "starting release/llm/llama-server for 20 s (output below and in state/logs/llm.log) ..."
    LD_LIBRARY_PATH="$ROOT/release/llm:$LD_LIBRARY_PATH" timeout 20 release/llm/llama-server -m release/llm/model.gguf \
      --host 127.0.0.1 --port 8099 -c 1024 -t 2 --no-warmup 2>&1 | tee state/logs/llm.log | tail -25 || true
    echo "--- If you see 'GLIBC' / 'GLIBCXX' / 'not found' / 'Illegal instruction' above: run  sh scripts/get_model.sh --build"
    echo "--- If you see 'server is listening' it works; the agent will start it by itself."
    exit 0 ;;
  --build)
    command -v cmake >/dev/null || { echo "need cmake + a compiler:  sudo apt install -y build-essential cmake libcurl4-openssl-dev"; exit 1; }
    SRC=$HOME/.cache/bai/llama.cpp-src
    mkdir -p "$(dirname "$SRC")"
    if [ ! -d "$SRC" ]; then
      echo "fetching llama.cpp source ..."
      curl -fsSL -o /tmp/llama-src.tgz "https://github.com/ggml-org/llama.cpp/archive/refs/tags/$LLAMA_TAG.tar.gz"
      mkdir -p "$SRC" && tar xzf /tmp/llama-src.tgz -C "$SRC" --strip-components=1 && rm /tmp/llama-src.tgz
    fi
    echo "building llama-server (5-15 min on a laptop) ..."
    cmake -S "$SRC" -B "$SRC/build" -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF -DGGML_NATIVE=ON -DBUILD_SHARED_LIBS=OFF >/dev/null
    cmake --build "$SRC/build" --target llama-server -j "$(nproc)" 2>&1 | grep -E "error|Built target llama-server" || true
    rm -f release/llm/llama-server release/llm/*.so*
    cp "$SRC/build/bin/llama-server" release/llm/llama-server
    fetch_model
    echo "built. test it:  sh scripts/get_model.sh --test"
    exit 0 ;;
esac

if [ ! -x release/llm/llama-server ]; then
  echo "fetching prebuilt llama.cpp $LLAMA_TAG ..."
  curl -fsSL -o /tmp/llama.tgz "https://github.com/ggml-org/llama.cpp/releases/download/$LLAMA_TAG/llama-$LLAMA_TAG-bin-ubuntu-x64.tar.gz"
  tar xzf /tmp/llama.tgz -C release/llm --strip-components=1 && rm /tmp/llama.tgz
  chmod +x release/llm/llama-server
fi
fetch_model
# quick check: does the prebuilt binary run here at all?
if ! LD_LIBRARY_PATH="$ROOT/release/llm:$LD_LIBRARY_PATH" release/llm/llama-server --version >/dev/null 2>state/logs/llm.log; then
  echo "!! the prebuilt server does not run on this system:"; tail -3 state/logs/llm.log
  echo "   -> run:  sudo apt install -y build-essential cmake libcurl4-openssl-dev && sh scripts/get_model.sh --build"
  exit 1
fi
echo "thinking model ready: $(du -m release/llm/model.gguf | cut -f1) MB, server $(LD_LIBRARY_PATH="$ROOT/release/llm" release/llm/llama-server --version 2>&1 | head -1)"
echo "restart the agent so it picks it up:  systemctl --user restart businessai"
