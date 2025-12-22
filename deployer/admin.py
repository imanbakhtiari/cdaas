from django.contrib import admin
from .models import Repository, Build, Deployment


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'url',
        'branch',
        'nexus_repository',
        'kubernetes_namespace',
        'created_at',
    )
    search_fields = ('name', 'url', 'nexus_repository')
    fieldsets = (
        (
            'Repository',
            {
                'fields': (
                    'name',
                    'url',
                    'branch',
                    'username',
                    'password',
                )
            },
        ),
        (
            'Nexus Registry',
            {
                'fields': (
                    'nexus_registry',
                    'nexus_repository',
                    'nexus_username',
                    'nexus_password',
                )
            },
        ),
        (
            'Kubernetes',
            {
                'fields': (
                    'kubernetes_namespace',
                    'kubeconfig',
                )
            },
        ),
    )


@admin.register(Build)
class BuildAdmin(admin.ModelAdmin):
    list_display = ('id', 'repository', 'status', 'image', 'created_at')
    list_filter = ('status',)


@admin.register(Deployment)
class DeploymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'build', 'kubernetes_namespace', 'status', 'created_at')
