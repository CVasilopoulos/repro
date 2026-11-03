FROM python:3.12-slim
RUN useradd --uid 10001 --no-create-home gate && mkdir -p /ledger && chown gate:gate /ledger
COPY gate.py /gate/gate.py
USER gate
EXPOSE 3128
CMD ["python", "-u", "/gate/gate.py"]
