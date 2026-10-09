# Ollama Install — Rocky Linux 8 (Sapphire Rapids Xeon)

## Install dependency
```bash
sudo dnf install -y zstd
```

## Install Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

## Workaround: disable AMX backend (fixes segfault on crash during model warmup)
Sapphire Rapids Xeons trigger a segfault in Ollama's AMX-accelerated CPU backend.
Fix: rename the AMX library so Ollama falls back to AVX512 (cascadelake/skylakex).

```bash
sudo mv /usr/local/lib/ollama/libggml-cpu-sapphirerapids.so \
        /usr/local/lib/ollama/libggml-cpu-sapphirerapids.so.disabled

sudo systemctl restart ollama
```

⚠️ **Re-apply this rename after every Ollama update** — updates re-extract the library and re-enable the crash.

## 6. Verify and run
```bash
systemctl status ollama
ollama pull phi4-mini
ollama run phi4-mini
```

Done. No `AMX model buffer size` line should appear in `journalctl -u ollama`, and the model should respond without segfaulting.