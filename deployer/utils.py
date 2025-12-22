from pathlib import Path
import textwrap
from typing import Optional

from django.conf import settings
from django.utils.text import slugify


def detect_language(repo_path: str) -> str:
    """Detect simple python web frameworks: django, flask, fastapi, or 'python' or 'unknown'."""
    p = Path(repo_path)
    files = {f.name for f in p.rglob('*') if f.is_file()}

    # Check for Django (manage.py or settings.py)
    if 'manage.py' in files or any('settings.py' == f for f in files):
        return 'django'

    # Check for FastAPI (looking for typical file names and imports)
    for f in p.rglob('*.py'):
        try:
            text = f.read_text(encoding='utf-8')
        except Exception:
            continue
        if 'FastAPI(' in text or 'from fastapi' in text:
            return 'fastapi'

    # Check for Flask
    for f in p.rglob('*.py'):
        try:
            text = f.read_text(encoding='utf-8')
        except Exception:
            continue
        if 'Flask(' in text or 'from flask' in text:
            return 'flask'

    # fallback: python if requirements.txt present or pyproject.toml
    if (p / 'requirements.txt').exists() or (p / 'pyproject.toml').exists():
        return 'python'

    return 'unknown'


def generate_dockerfile(framework: str) -> str:
    """Return a Dockerfile tailored for the detected framework."""
    if framework == 'django':
        return '''FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["gunicorn", "-b", ":8000", "project.wsgi:application"]
'''
    if framework == 'flask':
        return '''FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV FLASK_APP=app.py
CMD ["gunicorn", "-b", ":8000", "app:app"]
'''
    if framework == 'fastapi':
        return '''FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
'''
    # generic python
    return '''FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "http.server", "8000"]
'''


def write_repository_manifest(repository, image_reference: Optional[str] = None) -> Path:
    """Persist a YAML manifest that captures repo/Nexus/Kubernetes settings."""
    manifest_dir = Path(settings.BASE_DIR) / 'deployer_manifests'
    manifest_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(repository.name) or f"repository-{repository.pk}"
    manifest_path = manifest_dir / f"{slug}.yaml"

    kubeconfig_body = (repository.kubeconfig or '').strip()
    if kubeconfig_body:
        kubeconfig_block = textwrap.indent(kubeconfig_body, '    ')
    else:
        kubeconfig_block = '    # kubeconfig not provided\n'

    manifest_content = [
        "repository:",
        f"  name: {repository.name}",
        f"  url: {repository.url}",
        f"  branch: {repository.branch}",
        "nexus:",
        f"  registry: {repository.nexus_registry or ''}",
        f"  repository: {repository.nexus_repository or ''}",
        f"  username: {repository.nexus_username or ''}",
        f"  password: {repository.nexus_password or ''}",
        f"  image: {image_reference or ''}",
        "kubernetes:",
        f"  namespace: {repository.kubernetes_namespace or 'default'}",
        "  kubeconfig: |-",
    ]

    manifest_path.write_text(
        "\n".join(manifest_content) + "\n" + kubeconfig_block.rstrip() + "\n",
        encoding='utf-8',
    )
    return manifest_path
