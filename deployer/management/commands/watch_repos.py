import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from deployer.models import Repository, Build, Deployment
from deployer.utils import (
    detect_language,
    generate_dockerfile,
    write_repository_manifest,
    extract_repo_slug,
)


class Command(BaseCommand):
    help = (
        'Watch repositories, generate Dockerfiles, push images to Nexus, '
        'and deploy to Kubernetes using a stored kubeconfig.'
    )

    def handle(self, *args, **options):
        repos = Repository.objects.all()
        for repo in repos:
            self.stdout.write(f"Processing {repo.name} ({repo.url}) branch={repo.branch}")
            image_reference = None
            build: Build | None = None
            log_messages: list[str] = [
                f"Git URL: {repo.url}",
                f"Branch: {repo.branch}",
            ]
            tempdir = tempfile.mkdtemp(prefix='deployer_')
            current_revision = None
            try:
                clone_cmd = ['git', 'clone', '--depth', '1', '--branch', repo.branch, repo.url, tempdir]
                log_messages.append('Cloning repository...')
                clone_proc = subprocess.run(clone_cmd, capture_output=True, text=True)
                if clone_proc.returncode != 0:
                    error_msg = clone_proc.stderr.strip() or clone_proc.stdout.strip()
                    log_messages.append(f"Failed to clone repository: {error_msg}")
                    raise RuntimeError('Clone failed')
                log_messages.append('Repository cloned successfully.')

                current_revision = self._get_head_revision(tempdir)
                log_messages.append(f"Latest commit: {current_revision}")

                if repo.last_revision and repo.last_revision == current_revision:
                    self.stdout.write(
                        self.style.NOTICE(f"No changes in {repo.name}; skipping CI/CD pipeline.")
                    )
                    continue

                build = Build.objects.create(
                    repository=repo,
                    status='running',
                    commit=current_revision,
                )
                log_messages.insert(0, f"Started build for {repo.name} (commit {current_revision})")

                framework = detect_language(tempdir)
                log_messages.append(f"Detected framework: {framework}")

                dockerfile_path = Path(tempdir) / 'Dockerfile'
                if not dockerfile_path.exists():
                    content = generate_dockerfile(framework)
                    dockerfile_path.write_text(content, encoding='utf-8')
                    log_messages.append('Dockerfile created automatically.')
                else:
                    log_messages.append('Dockerfile already present; no changes made.')

                if repo.nexus_registry and (repo.nexus_repository or repo.name):
                    try:
                        image_reference, output = self._build_and_push_image(repo, tempdir, build)
                        build.image = image_reference
                        log_messages.append(f"Image pushed to {image_reference}")
                        if output:
                            log_messages.append(output)
                    except Exception as exc:  # noqa: BLE001
                        log_messages.append(f"Image build/push failed: {exc}")
                        raise
                else:
                    log_messages.append('Nexus registry or repository missing; skipping image push.')

                if image_reference and repo.kubeconfig:
                    deployment = Deployment.objects.create(
                        build=build,
                        kubernetes_namespace=repo.kubernetes_namespace or 'default',
                        status='running',
                    )
                    try:
                        deploy_msg = self._deploy_to_cluster(repo, image_reference)
                        deployment.status = 'success'
                        deployment.save(update_fields=['status'])
                        log_messages.append(deploy_msg)
                    except Exception as exc:  # noqa: BLE001
                        deployment.status = 'failed'
                        deployment.save(update_fields=['status'])
                        log_messages.append(f"Kubernetes deployment failed: {exc}")
                        raise
                elif not repo.kubeconfig:
                    log_messages.append('No kubeconfig configured; skipping Kubernetes deployment.')
                else:
                    log_messages.append('Image not available; skipping deployment.')

                if build:
                    build.status = 'success'
            except Exception as exc:  # noqa: BLE001
                if build:
                    build.status = 'failed'
                else:
                    build = Build.objects.create(
                        repository=repo,
                        status='failed',
                        commit=current_revision,
                    )
                log_messages.append(f"Pipeline terminated: {exc}")
            finally:
                shutil.rmtree(tempdir, ignore_errors=True)

                if build:
                    try:
                        manifest_path = write_repository_manifest(repo, image_reference)
                        log_messages.append(f"Manifest exported to {manifest_path}")
                    except Exception as exc:  # noqa: BLE001
                        log_messages.append(f"Failed to write manifest: {exc}")

                    build.log = "\n".join(filter(None, log_messages)).strip()
                    build.save(update_fields=['status', 'log', 'image', 'commit'])

                    if build.status == 'success' and build.commit:
                        repo.last_revision = build.commit
                        repo.save(update_fields=['last_revision'])
                        self.stdout.write(self.style.SUCCESS(f"{repo.name} processed successfully."))
                    elif build.status == 'failed':
                        self.stdout.write(self.style.ERROR(f"{repo.name} failed. See build log for details."))

    def _build_and_push_image(self, repo, context_dir: str, build: Build) -> tuple[str, str]:
        """Build a Docker image from context_dir and push it to Nexus."""
        registry = self._normalize_registry(repo.nexus_registry)
        if not registry:
            raise ValueError('Nexus registry is empty.')

        repository_name = (repo.nexus_repository or '').strip()
        if not repository_name:
            derived_slug = extract_repo_slug(repo.url)
            if derived_slug:
                repository_name = derived_slug
            else:
                repository_name = slugify(repo.name) or f"repository-{repo.pk}"

        tag = (build.commit or str(build.id))[:12]
        image_reference = f"{registry}/{repository_name}:{tag}"
        outputs: list[str] = []

        if repo.nexus_username and repo.nexus_password:
            login_cmd = [
                'docker',
                'login',
                registry,
                '-u',
                repo.nexus_username,
                '--password-stdin',
            ]
            try:
                login_proc = subprocess.run(
                    login_cmd,
                    input=repo.nexus_password,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError as exc:  # pragma: no cover - depends on host env
                raise RuntimeError('Docker CLI not found. Ensure Docker is installed.') from exc
            if login_proc.returncode != 0:
                raise RuntimeError(login_proc.stderr.strip() or 'Docker login failed.')
            outputs.append(login_proc.stdout.strip())

        build_cmd = ['docker', 'build', '-t', image_reference, context_dir]
        try:
            build_proc = subprocess.run(build_cmd, capture_output=True, text=True)
        except FileNotFoundError as exc:  # pragma: no cover - depends on host env
            raise RuntimeError('Docker CLI not found. Ensure Docker is installed.') from exc
        if build_proc.returncode != 0:
            raise RuntimeError(build_proc.stderr.strip() or 'Docker build failed.')
        outputs.append(build_proc.stdout.strip())

        push_cmd = ['docker', 'push', image_reference]
        push_proc = subprocess.run(push_cmd, capture_output=True, text=True)
        if push_proc.returncode != 0:
            raise RuntimeError(push_proc.stderr.strip() or 'Docker push failed.')
        outputs.append(push_proc.stdout.strip())

        combined_output = "\n".join(filter(None, outputs)).strip()
        return image_reference, combined_output

    def _deploy_to_cluster(self, repo, image_reference: str) -> str:
        """Apply a simple Deployment manifest using the stored kubeconfig."""
        kubeconfig_body = (repo.kubeconfig or '').strip()
        if not kubeconfig_body:
            raise ValueError('Repository does not have a kubeconfig configured.')

        app_name = slugify(repo.name) or f"app-{repo.pk}"
        namespace = repo.kubernetes_namespace or 'default'

        manifest = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_name}
  namespace: {namespace}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {app_name}
  template:
    metadata:
      labels:
        app: {app_name}
    spec:
      containers:
      - name: {app_name}
        image: {image_reference}
        ports:
        - containerPort: 8000
"""

        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as manifest_file:
            manifest_file.write(manifest)
            manifest_path = manifest_file.name

        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as kubeconfig_file:
            kubeconfig_file.write(kubeconfig_body)
            kubeconfig_file.flush()
            kubeconfig_path = kubeconfig_file.name

        cmd = ['kubectl', '--kubeconfig', kubeconfig_path, 'apply', '-f', manifest_path]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError as exc:  # pragma: no cover - depends on host env
            raise RuntimeError('kubectl not found. Ensure the Kubernetes CLI is installed.') from exc
        finally:
            for tmp in (manifest_path, kubeconfig_path):
                try:
                    os.remove(tmp)
                except FileNotFoundError:
                    pass

        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or 'kubectl apply failed.')

        return proc.stdout.strip() or f"Kubectl applied manifest for namespace {namespace}."

    @staticmethod
    def _normalize_registry(registry: str | None) -> str:
        if not registry:
            return ''
        value = registry.strip().rstrip('/')
        if value.startswith('http://') or value.startswith('https://'):
            value = value.split('://', 1)[1]
        return value

    @staticmethod
    def _get_head_revision(repo_path: str) -> str:
        cmd = ['git', '-C', repo_path, 'rev-parse', 'HEAD']
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or 'Unable to determine repository revision.')
        return proc.stdout.strip()
