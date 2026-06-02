FROM python:3.13-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

COPY db/ db/
COPY routers/ routers/
COPY services/ services/
COPY *.py ./

CMD [ "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000" ]
