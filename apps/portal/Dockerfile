FROM python:3.12-slim

RUN useradd --create-home --uid 1000 portal
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY password_rules.py auth_flow.py browser_session.py tool_links.py app.py ./
COPY .streamlit ./.streamlit

USER portal
EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
