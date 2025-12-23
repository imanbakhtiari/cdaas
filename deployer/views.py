from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import RepositoryForm
from django.db.models import Count, Q

from .models import Repository, Build


def index(request):
    repos = Repository.objects.all().order_by('-created_at')
    builds = Build.objects.select_related('repository').order_by('-created_at')[:20]
    editing_repo_id = ''
    if request.method == 'POST':
        repo_id = request.POST.get('repo_id')
        repo_instance = Repository.objects.filter(pk=repo_id).first() if repo_id else None
        form = RepositoryForm(request.POST, instance=repo_instance)
        editing_repo_id = repo_id or ''
        if form.is_valid():
            repo = form.save()
            if repo_instance:
                messages.success(request, f"Repository '{repo.name}' updated.")
            else:
                messages.success(request, f"Repository '{repo.name}' added.")
            return redirect(reverse('deployer:index'))
        messages.error(request, 'Please fix the errors below.')
    else:
        form = RepositoryForm()

    stats = {
        'repositories': repos.count(),
        'registries_ready': repos.filter(~Q(nexus_registry=''), ~Q(nexus_registry=None)).count(),
        'kubeconfigs_ready': repos.filter(~Q(kubeconfig=''), ~Q(kubeconfig=None)).count(),
        'recent_builds': Build.objects.count(),
    }
    return render(
        request,
        'deployer/index.html',
        {
            'repos': repos,
            'form': form,
            'builds': builds,
            'stats': stats,
            'editing_repo_id': editing_repo_id,
        },
    )
