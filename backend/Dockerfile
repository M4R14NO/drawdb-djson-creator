FROM python:3.12-slim
WORKDIR /app
COPY sql_to_djson.py .
COPY main.py .
RUN pip install fastapi uvicorn python-multipart
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]