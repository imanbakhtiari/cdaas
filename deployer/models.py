from django.db import models


class Repository(models.Model):
    name = models.CharField(max_length=200)
    url = models.URLField()
    branch = models.CharField(max_length=100, default='master')
    username = models.CharField(max_length=200, blank=True, null=True)
    password = models.CharField(max_length=200, blank=True, null=True)
    nexus_registry = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Hostname (and optional port) of the Nexus Docker registry.",
    )
    nexus_repository = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Repository or project within Nexus where images will be pushed.",
    )
    nexus_username = models.CharField(max_length=200, blank=True, null=True)
    nexus_password = models.CharField(max_length=200, blank=True, null=True)
    kubernetes_namespace = models.CharField(max_length=200, default='default')
    kubeconfig = models.TextField(
        blank=True,
        null=True,
        help_text="Paste the kubeconfig YAML used for deployments.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.url})"

    @property
    def registry_domain(self) -> str:
        if not self.nexus_registry:
            return ''
        value = self.nexus_registry.strip().rstrip('/')
        if value.startswith('http://') or value.startswith('https://'):
            value = value.split('://', 1)[1]
        return value


class Build(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='builds')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    image = models.CharField(max_length=300, blank=True, null=True)
    log = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Build {self.id} - {self.repository.name} - {self.status}"


class Deployment(models.Model):
    build = models.ForeignKey(Build, on_delete=models.CASCADE, related_name='deployments')
    kubernetes_namespace = models.CharField(max_length=200, default='default')
    status = models.CharField(max_length=50, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Deployment {self.id} - {self.build}" 
