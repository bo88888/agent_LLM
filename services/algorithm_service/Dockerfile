FROM huo-infer-v8:v2
ENV LD_LIBRARY_PATH=/mnt/ww/opencv460/lib64:/usr/local/lib:$LD_LIBRARY_PATH
ENV OMP_NUM_THREADS=8
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY . .
RUN chmod +x myprogram || true
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app"]
