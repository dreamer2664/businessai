#!/bin/sh
# Download the thinking model (llama.cpp server + a small instruct model, both free/open). Re-runnable.
#   default: Qwen2.5-1.5B-Instruct Q4_K_M (~940 MB, needs ~1.3 GB RAM)  — override with BAI_MODEL_URL
set -e
cd "$(dirname "$0")/.."
mkdir -p release/llm && cd release/llm
LLAMA_TAG=b10826
if [ ! -x llama-server ]; then
  echo "fetching llama.cpp $LLAMA_TAG ..."
  curl -fsSL -o llama.tgz "https://github.com/ggml-org/llama.cpp/releases/download/$LLAMA_TAG/llama-$LLAMA_TAG-bin-ubuntu-x64.tar.gz"
  tar xzf llama.tgz --strip-components=1 && rm llama.tgz
fi
URL="${BAI_MODEL_URL:-https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf}"
if [ ! -s model.gguf ]; then
  echo "fetching model (~1 GB, once) ..."
  curl -fL --progress-bar -o model.gguf "$URL"
fi
echo "thinking model ready: $(du -m model.gguf | cut -f1) MB. The agent starts it by itself."
