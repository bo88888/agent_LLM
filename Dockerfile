FROM huo-infer-v8:v3
ENV LD_LIBRARY_PATH=/mnt/ww/opencv460/lib64:/usr/local/lib:$LD_LIBRARY_PATH
ENV OMP_NUM_THREADS=8
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace:/app
WORKDIR /workspace
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY . .
RUN chmod +x /workspace/services/algorithm_service/myprogram || true
CMD set -eu; \
    cd /workspace/services/algorithm_service; \
    chmod +x ./myprogram || true; \
    python -m uvicorn app:app --host 0.0.0.0 --port 8888 --reload --reload-dir /workspace/services/algorithm_service & \
    api_pid=$!; \
    trap 'kill "$api_pid" 2>/dev/null || true' EXIT; \
    retry_count=0; \
    until python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8888/docs', timeout=2).close()" >/dev/null 2>&1; do \
      retry_count=$((retry_count + 1)); \
      if [ "$retry_count" -ge 60 ]; then \
        echo "algorithm service not ready" >&2; \
        exit 1; \
      fi; \
      sleep 1; \
    done; \
    cd /workspace; \
    python main.py
